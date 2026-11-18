import json
import time, random, logging
from contextvars import ContextVar
provider_trace = ContextVar("provider_trace",default=None)
import urllib.request
from google import genai
from .config import settings

class ProviderConfigurationError(RuntimeError): pass
class ProviderResponseError(RuntimeError): pass
class ProviderSafetyError(RuntimeError): pass
class GroqAPIError(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__('Groq request failed')
class AllProvidersUnavailable(RuntimeError):
    def __init__(self,failures):
        self.failures=failures
        codes=[r.get('http_status') for r in failures]
        self.code=429 if codes and all(c==429 for c in codes) else None
        super().__init__('Configured AI providers could not complete the request')

_call_deadline=ContextVar('ai_call_deadline',default=None)
_pair_required=ContextVar('ai_pair_required',default=False)

def provider_model(provider):
    return {'gemini':settings.gemini_model,'groq':settings.groq_model,'ollama':settings.ollama_model}[provider]

def configured_providers():
    return {'gemini':bool(settings.gemini_api_key and settings.gemini_model),'groq':bool(settings.groq_api_key and settings.groq_model),'ollama':bool(settings.ollama_base_url and settings.ollama_model)}

def _remaining_deadline():
    return _call_deadline.get() or time.perf_counter()+settings.ai_timeout_seconds

def _blocked(value):
    value=str(getattr(value,'name',value)).upper().rsplit('.',1)[-1]
    return value in {'SAFETY','BLOCKLIST','PROHIBITED_CONTENT','SPII','IMAGE_SAFETY','CONTENT_FILTER','RECITATION','MODEL_ARMOR'}


def provider_error_detail(error):
    if isinstance(error,ProviderSafetyError): return 'The AI provider declined this request. Please use a safe, non-abusive message.'
    if isinstance(error,AllProvidersUnavailable): return 'Gemini and Groq could not complete this request. Check backend keys, model access and quotas, or retry shortly.'
    if isinstance(error,GroqAPIError): return 'Groq is unavailable or its backend key, model access or quota needs attention. Please retry shortly.'
    if isinstance(error,ProviderConfigurationError):
        return 'The selected AI provider needs a backend API key. Configure GEMINI_API_KEY or GROQ_API_KEY in Render Environment.'
    if isinstance(error,ProviderResponseError): return str(error)
    import httpx
    if isinstance(error,(TimeoutError,httpx.TimeoutException)): return 'The AI provider timed out. Please retry with a shorter message.'
    if isinstance(error,httpx.NetworkError): return 'The backend could not reach the AI provider. Please retry shortly.'
    from google.genai.errors import APIError
    if isinstance(error,APIError):
        return {
            400:'Gemini rejected the request configuration or API key. Check the backend key and selected model.',
            401:'Gemini API key is invalid. Update GEMINI_API_KEY on the backend.',
            403:'Gemini access denied. Check API key restrictions and Google project permissions.',
            404:'Gemini model is unavailable for this project. Check GEMINI_MODEL on the backend.',
            429:'Gemini quota or rate limit reached. Wait and retry, or check Google AI Studio quota.',
        }.get(error.code,'Gemini is temporarily unavailable. Please retry shortly.')
    return 'AI provider unavailable. Check the server API key, model, quota, or retry shortly.'

MODES = {
    "normal": "friendly playful teasing",
    "sarcastic": "clever sarcastic banter",
    "savage": "sharp confident comedic comeback",
    "brutal": "very sharp but still comedic",
    "vulgar": "strong adult profanity may be used",
    "funny": "meme-like funny comeback",
    "deadpan": "dry understated humor",
    "intelligent": "witty clever wordplay",
    "respectful": "firm but non-abusive comeback",
}
LANGUAGES = {
    "same": "the same language as the incoming message",
    "english": "English", "hindi": "Hindi", "kannada": "Kannada",
    "malayalam": "Malayalam", "tamil": "Tamil", "telugu": "Telugu",
    "bengali": "Bengali", "marathi": "Marathi", "punjabi": "Punjabi",
    "urdu": "Urdu",
}

def _prompt(message, cfg, sender_name, context, input_language, reply_language, script_mode):
    profanity = {
        "off": "no profanity",
        "light": "mild profanity allowed",
        "heavy": "strong adult profanity allowed",
    }[cfg.profanity_level]
    history = ""
    if context:
        history = "\nRecent conversation:\n" + "\n".join(
            f"{x['direction']}: {x['text']}" for x in context[-10:]
        )
    target = LANGUAGES.get(reply_language, "the same language as the incoming message")
    script = "normal native script" if script_mode == "native" else "English/Roman letters (Romanized script)"
    return f"""You are RoastBot, a fast multilingual chat-comeback assistant.
Style: {MODES[cfg.roast_mode]}. Intensity: {cfg.intensity}/10. Profanity: {profanity}.
Intensity guidance: {"gentle friendly teasing; no personal put-downs" if cfg.intensity<=3 else "pointed playful banter" if cfg.intensity<=6 else "sharp confident punchline" if cfg.intensity<=8 else "cutting, punchy comedic comeback; no threats or hateful attacks"}.
Mode distinction: respectful stays courteous with a firm witty boundary; deadpan uses a flat one-line observation; intelligent uses wordplay; funny uses a surprising comparison; sarcastic uses irony. Do not use the same generic comeback for every mode.
Speak as the recipient replying to the incoming message, not as someone repeating its accusation.
Reply language: {target}. Script: {script}. Input language: {input_language}.
Custom personality: {cfg.custom_instructions or "none"}.
Profanity setting overrides mode and custom voice: when off, do not swear even in vulgar mode.
Keep the comeback natural and conversational, normally 1-2 sentences, under {cfg.max_reply_length} characters.

Return EXACTLY two lines:
REPLY: <the comeback>
MEANING: <natural English meaning of the comeback>

Do not add labels other than REPLY: and MEANING:.
Never produce threats, slurs, hateful attacks, doxxing, or attacks based on protected traits.
If the message is a genuine crisis, emergency, grief, or request for serious help, respond supportively instead of roasting.
{history}
Sender: {sender_name}
Message: {message}"""

def _gemini(prompt):
    if not settings.gemini_api_key:
        raise ProviderConfigurationError("Missing backend Gemini key")
    import httpx
    from google.genai import types
    from google.genai.errors import APIError
    started=time.perf_counter(); deadline=min(started+settings.ai_timeout_seconds,_remaining_deadline())
    trace={'provider':'gemini','model':settings.gemini_model,'attempts':0,'input_tokens':None,'output_tokens':None,'thinking_tokens':None,'total_tokens':None}
    provider_trace.set(trace)
    thinking=(types.ThinkingConfig(thinking_budget=0) if settings.gemini_model.startswith('gemini-2.5')
              else types.ThinkingConfig(thinking_level='minimal' if settings.gemini_model in ('gemini-3.5-flash-lite','gemini-3.1-flash-lite') else 'low') if settings.gemini_model.startswith('gemini-3') else None)
    for attempt in range(settings.ai_max_attempts):
        remaining=deadline-time.perf_counter()
        if remaining<=0: raise TimeoutError('AI request deadline exceeded')
        trace['attempts']=attempt+1
        try:
            # SDK defaults can retry five times; disable nested retries and bound ours.
            options=types.HttpOptions(timeout=int(min(remaining,settings.ai_attempt_timeout_seconds)*1000),retry_options=types.HttpRetryOptions(attempts=1))
            with genai.Client(api_key=settings.gemini_api_key,http_options=options) as client:
                response=client.models.generate_content(model=settings.gemini_model,contents=prompt,config=types.GenerateContentConfig(thinking_config=thinking,max_output_tokens=1536,temperature=0.8))
            if _blocked(getattr(getattr(response,'prompt_feedback',None),'block_reason',None)) or any(_blocked(getattr(c,'finish_reason',None)) for c in (getattr(response,'candidates',None) or [])):
                raise ProviderSafetyError('Provider safety block')
            trace.pop('http_status',None)
            trace['uncertain_attempts']=attempt
            usage=getattr(response,'usage_metadata',None)
            if usage:
                for key,field in [('input_tokens','prompt_token_count'),('output_tokens','candidates_token_count'),('thinking_tokens','thoughts_token_count'),('total_tokens','total_token_count')]:
                    trace[key]=getattr(usage,field,None)
            trace['latency_ms']=round((time.perf_counter()-started)*1000)
            result=(response.text or '').strip()
            if not result: raise ProviderResponseError('Gemini returned no usable reply. Try a different safe message.')
            return result
        except Exception as error:
            code=getattr(error,'code',None)
            trace['http_status']=code if isinstance(code,int) else None
            trace['latency_ms']=round((time.perf_counter()-started)*1000)
            transient=(isinstance(error,APIError) and code in (408,500,502,503,504)) or isinstance(error,(httpx.ConnectError,httpx.TimeoutException))
            if not transient or attempt+1>=settings.ai_max_attempts: raise
            delay=min(.5*2**attempt+random.uniform(0,.2),max(0,deadline-time.perf_counter()))
            if deadline-time.perf_counter()<=delay: raise
            time.sleep(delay)


def _ollama(prompt):
    payload = json.dumps({
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.8, "num_predict": 240},
    }).encode()
    req = urllib.request.Request(
        settings.ollama_base_url.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode()).get("response", "").strip()

def _groq(prompt):
    import httpx
    if not settings.groq_api_key: raise ProviderConfigurationError('Missing backend Groq key')
    started=time.perf_counter();deadline=min(started+settings.ai_timeout_seconds,_remaining_deadline())
    trace={'provider':'groq','model':settings.groq_model,'attempts':0,'input_tokens':None,'output_tokens':None,'thinking_tokens':None,'total_tokens':None}
    provider_trace.set(trace)
    payload={'model':settings.groq_model,'messages':[{'role':'user','content':prompt}],'temperature':0.8,'max_completion_tokens':1536,'stream':False}
    if settings.groq_model.startswith('openai/gpt-oss-'):payload.update(reasoning_effort='low',include_reasoning=False)
    for attempt in range(settings.ai_max_attempts):
        remaining=deadline-time.perf_counter()
        if remaining<=0:raise TimeoutError('AI request deadline exceeded')
        trace['attempts']=attempt+1
        try:
            with httpx.Client(timeout=min(remaining,settings.ai_attempt_timeout_seconds),follow_redirects=False) as client:
                response=client.post('https://api.groq.com/openai/v1/chat/completions',headers={'Authorization':'Bearer '+settings.groq_api_key},json=payload)
            if response.status_code>=400:raise GroqAPIError(response.status_code)
            try:
                data=response.json();choice=data['choices'][0];message=choice['message']
                if message.get('refusal') or _blocked(choice.get('finish_reason')):raise ProviderSafetyError('Provider safety block')
                result=message.get('content')
                if not isinstance(result,str) or not result.strip():raise ValueError()
                usage=data.get('usage') or {}
                if not isinstance(usage,dict):raise ValueError()
            except (ValueError,KeyError,IndexError,TypeError,AttributeError):raise ProviderResponseError('Groq returned no usable reply. Please retry.') from None
            for key,field in [('input_tokens','prompt_tokens'),('output_tokens','completion_tokens'),('total_tokens','total_tokens')]:trace[key]=usage.get(field)
            detail=usage.get('completion_tokens_details') or {}
            trace['thinking_tokens']=detail.get('reasoning_tokens') if isinstance(detail,dict) else None
            trace.pop('http_status',None);trace['uncertain_attempts']=attempt;trace['latency_ms']=round((time.perf_counter()-started)*1000)
            return result.strip()
        except Exception as error:
            code=getattr(error,'code',None);trace['http_status']=code if isinstance(code,int) else None;trace['latency_ms']=round((time.perf_counter()-started)*1000)
            transient=(isinstance(error,GroqAPIError) and code in (408,500,502,503,504)) or isinstance(error,(httpx.ConnectError,httpx.TimeoutException))
            if not transient or attempt+1>=settings.ai_max_attempts:raise
            delay=min(.5*2**attempt+random.uniform(0,.2),max(0,deadline-time.perf_counter()))
            if deadline-time.perf_counter()<=delay:raise
            time.sleep(delay)


def _can_fallback(error):
    import httpx
    from google.genai.errors import APIError
    if isinstance(error,ProviderSafetyError):return False
    if isinstance(error,(ProviderConfigurationError,ProviderResponseError,TimeoutError,httpx.NetworkError,httpx.TimeoutException)):return True
    return isinstance(error,(APIError,GroqAPIError)) and getattr(error,'code',None) in (400,401,403,404,408,429,500,502,503,504)


def ask(prompt):
    provider_trace.set(None)
    if settings.ai_provider=='ollama':return _ollama(prompt)
    primary=settings.ai_provider;secondary='groq' if primary=='gemini' else 'gemini'
    chain=[primary]
    if settings.ai_fallback_enabled and configured_providers()[secondary]:chain.append(secondary)
    began=time.perf_counter();deadline=began+settings.ai_timeout_seconds;outcomes=[]
    for index,provider in enumerate(chain):
        if time.perf_counter()>=deadline:break
        reserved=min(settings.ai_attempt_timeout_seconds,settings.ai_timeout_seconds/2) if index==0 and len(chain)>1 else 0
        token=_call_deadline.set(deadline-reserved)
        provider_trace.set({'provider':provider,'model':provider_model(provider),'attempts':0})
        try:
            raw={'gemini':_gemini,'groq':_groq}[provider](prompt)
            if _pair_required.get():_parse_pair(raw)
        except Exception as error:
            trace=dict(provider_trace.get() or {})
            trace.update(provider=provider,model=provider_model(provider),status='failed',error_type=type(error).__name__)
            trace['http_status']=getattr(error,'code',None) if isinstance(getattr(error,'code',None),int) else None
            outcomes.append(trace)
            provider_trace.set({**trace,'primary_provider':primary,'fallback_used':index>0,'providers':outcomes,'attempts':sum(r.get('attempts',0) for r in outcomes)})
            if not _can_fallback(error) or len(chain)==1:raise
        else:
            trace=dict(provider_trace.get() or {});trace['attempts']=max(1,trace.get('attempts',0))
            outcomes.append({**trace,'status':'healthy'})
            provider_trace.set({**trace,'primary_provider':primary,'fallback_used':index>0,'providers':outcomes,'attempts':sum(r.get('attempts',0) for r in outcomes),'latency_ms':round((time.perf_counter()-began)*1000)})
            return raw
        finally:_call_deadline.reset(token)
    raise AllProvidersUnavailable(outcomes) from None


def _ask_pair(prompt):
    token=_pair_required.set(True)
    try:return ask(prompt)
    finally:_pair_required.reset(token)

def _parse_pair(raw):
    raw = raw.strip()
    if raw.startswith('```'):
        lines = raw.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == '```':
            raw = '\n'.join(lines[1:-1]).strip()
    if raw.startswith('{'):
        try:
            data=json.loads(raw);reply=data['reply'];meaning=data['english_meaning']
            if isinstance(reply,str) and isinstance(meaning,str) and reply.strip() and meaning.strip(): return reply.strip(),meaning.strip()
        except (ValueError,KeyError,TypeError): pass
    reply = ""
    meaning = ""
    for line in raw.splitlines():
        if line.strip().upper().startswith("REPLY:"):
            reply = line.split(":", 1)[1].strip()
        elif line.strip().upper().startswith("MEANING:"):
            meaning = line.split(":", 1)[1].strip()
    if not reply:
        raise ProviderResponseError("The AI provider returned an unexpected reply format. Please retry.")
    if not meaning:
        raise ProviderResponseError("The AI provider returned an incomplete reply without English meaning. Please retry.")
    return reply, meaning

def generate(message, cfg, sender_name="Someone", context=None,
             input_language="auto", reply_language="same", script_mode="roman"):
    raw = _ask_pair(_prompt(message, cfg, sender_name, context, input_language, reply_language, script_mode))
    reply, _ = _parse_pair(raw)
    return reply[:cfg.max_reply_length].rstrip()

def generate_with_meaning(message, cfg, sender_name="Someone", context=None,
                          input_language="auto", reply_language="same", script_mode="roman"):
    raw = _ask_pair(_prompt(message, cfg, sender_name, context, input_language, reply_language, script_mode))
    reply, meaning = _parse_pair(raw)
    return reply[:cfg.max_reply_length].rstrip(), meaning.strip()

def english_meaning(text, source_language, cfg):
    # Kept for compatibility with older integrations. New roast requests use one call.
    prompt = f"Translate this chat reply into natural English. Return only the meaning.\nReply: {text}"
    return ask(prompt).strip()
