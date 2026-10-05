import json
import urllib.request
from google import genai
from .config import settings

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
Reply language: {target}. Script: {script}. Input language: {input_language}.
Custom personality: {cfg.custom_instructions or "none"}.
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
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to backend/.env.")
    from google.genai import types
    with genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=settings.ai_timeout_seconds * 1000)) as client:
        thinking = (types.ThinkingConfig(thinking_budget=0) if settings.gemini_model.startswith("gemini-2.5")
                    else types.ThinkingConfig(thinking_level="minimal"))
        response = client.models.generate_content(
            model=settings.gemini_model, contents=prompt,
            config=types.GenerateContentConfig(thinking_config=thinking, max_output_tokens=480, temperature=0.8),
        )
        result = (response.text or "").strip()
        if not result: raise RuntimeError("AI returned no reply")
        return result

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

def ask(prompt):
    if settings.ai_provider == "ollama":
        return _ollama(prompt)
    return _gemini(prompt)

def _parse_pair(raw):
    reply = ""
    meaning = ""
    for line in raw.splitlines():
        if line.upper().startswith("REPLY:"):
            reply = line.split(":", 1)[1].strip()
        elif line.upper().startswith("MEANING:"):
            meaning = line.split(":", 1)[1].strip()
    if not reply:
        raise RuntimeError("AI returned an invalid reply format")
    if not meaning:
        raise RuntimeError("AI returned no English meaning")
    return reply, meaning

def generate(message, cfg, sender_name="Someone", context=None,
             input_language="auto", reply_language="same", script_mode="roman"):
    raw = ask(_prompt(message, cfg, sender_name, context, input_language, reply_language, script_mode))
    reply, _ = _parse_pair(raw)
    return reply[:cfg.max_reply_length].rstrip()

def generate_with_meaning(message, cfg, sender_name="Someone", context=None,
                          input_language="auto", reply_language="same", script_mode="roman"):
    raw = ask(_prompt(message, cfg, sender_name, context, input_language, reply_language, script_mode))
    reply, meaning = _parse_pair(raw)
    return reply[:cfg.max_reply_length].rstrip(), meaning.strip()

def english_meaning(text, source_language, cfg):
    # Kept for compatibility with older integrations. New roast requests use one call.
    prompt = f"Translate this chat reply into natural English. Return only the meaning.\nReply: {text}"
    return ask(prompt).strip()
