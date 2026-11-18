"""Provider failover contracts; all upstream calls in this file are test doubles."""
import json,time,uuid
from types import SimpleNamespace
import httpx,pytest
from test_api import client,AUTH
from app import ai,main,store
from app.config import settings
from app.models import BotSettings

@pytest.fixture
def dual(monkeypatch):
    monkeypatch.setattr(settings,'ai_provider','gemini');monkeypatch.setattr(settings,'ai_fallback_enabled',True)
    monkeypatch.setattr(settings,'gemini_api_key','local-test-gemini-key');monkeypatch.setattr(settings,'groq_api_key','local-test-groq-key')
    monkeypatch.setattr(ai.time,'sleep',lambda _:None)

def provider(monkeypatch,name,result,calls,code=None):
    def run(prompt):
        calls.append((name,prompt));ai.provider_trace.set({'provider':name,'model':ai.provider_model(name),'attempts':1,'input_tokens':10,'output_tokens':5,'total_tokens':15})
        if isinstance(result,Exception):raise result
        return result
    monkeypatch.setattr(ai,'_'+name,run)

@pytest.mark.parametrize('error',[ai.GroqAPIError(503),ai.GroqAPIError(429),ai.GroqAPIError(401),ai.GroqAPIError(404),httpx.ConnectError('private-provider-token'),httpx.ReadTimeout('private-provider-token'),ai.ProviderConfigurationError('private-provider-token')])
def test_gemini_failure_recovers_with_groq(dual,monkeypatch,error):
    calls=[];provider(monkeypatch,'gemini',error,calls);provider(monkeypatch,'groq','REPLY: safe comeback\nMEANING: safe meaning',calls)
    assert ai.generate_with_meaning('You are late again.',BotSettings())==('safe comeback','safe meaning')
    trace=ai.provider_trace.get();assert [n for n,_ in calls]==['gemini','groq'] and calls[0][1]==calls[1][1]
    assert trace['provider']=='groq' and trace['fallback_used'] and trace['attempts']==2
    assert 'private-provider-token' not in json.dumps(trace)

def test_healthy_primary_never_calls_backup(dual,monkeypatch):
    calls=[];provider(monkeypatch,'gemini','REPLY: first\nMEANING: first',calls);provider(monkeypatch,'groq',RuntimeError('Do not call'),calls)
    assert ai.generate_with_meaning('safe',BotSettings())[0]=='first'
    assert [n for n,_ in calls]==['gemini'] and not ai.provider_trace.get()['fallback_used']

def test_reverse_failover_and_disabled_revert_switch(dual,monkeypatch):
    monkeypatch.setattr(settings,'ai_provider','groq');calls=[]
    provider(monkeypatch,'groq',ai.GroqAPIError(503),calls);provider(monkeypatch,'gemini','REPLY: recovered\nMEANING: recovered',calls)
    assert ai.generate_with_meaning('safe',BotSettings())[0]=='recovered'
    assert [n for n,_ in calls]==['groq','gemini']
    monkeypatch.setattr(settings,'ai_fallback_enabled',False);calls.clear()
    with pytest.raises(ai.GroqAPIError):ai.generate_with_meaning('safe',BotSettings())
    assert [n for n,_ in calls]==['groq']

def test_missing_backup_key_leaves_primary_error_clear(dual,monkeypatch):
    monkeypatch.setattr(settings,'groq_api_key','');calls=[]
    provider(monkeypatch,'gemini',ai.GroqAPIError(503),calls);provider(monkeypatch,'groq',RuntimeError('Do not call'),calls)
    with pytest.raises(ai.GroqAPIError):ai.generate_with_meaning('safe',BotSettings())
    assert [n for n,_ in calls]==['gemini']

@pytest.mark.parametrize('raw',['','unlabelled reply','REPLY: reply without meaning','{"reply":"valid","english_meaning":""}'])
def test_invalid_primary_pair_fails_over(dual,monkeypatch,raw):
    calls=[];provider(monkeypatch,'gemini',raw,calls);provider(monkeypatch,'groq','REPLY: reply\nMEANING: meaning',calls)
    assert ai.generate_with_meaning('safe',BotSettings())==('reply','meaning')
    assert [n for n,_ in calls]==['gemini','groq']

@pytest.mark.parametrize('error',[ai.ProviderSafetyError('blocked'),RuntimeError('programming error')])
def test_policy_blocks_and_programming_errors_do_not_failover(dual,monkeypatch,error):
    calls=[];provider(monkeypatch,'gemini',error,calls);provider(monkeypatch,'groq','REPLY: no\nMEANING: no',calls)
    with pytest.raises(type(error)):ai.generate_with_meaning('safe',BotSettings())
    assert [n for n,_ in calls]==['gemini']

def test_deadline_reserves_time_for_backup_and_is_not_reset(dual,monkeypatch):
    clock=[100.0];monkeypatch.setattr(ai.time,'perf_counter',lambda:clock[0]);limits=[]
    def first(prompt):
        limits.append(ai._call_deadline.get());clock[0]=118;raise TimeoutError()
    def second(prompt):limits.append(ai._call_deadline.get());return 'REPLY: yes\nMEANING: yes'
    monkeypatch.setattr(ai,'_gemini',first);monkeypatch.setattr(ai,'_groq',second)
    assert ai.generate_with_meaning('safe',BotSettings())[0]=='yes'
    assert limits==[118.0,130.0] and ai._call_deadline.get() is None

@pytest.mark.parametrize('status,expected',[(503,2),(429,1),(401,1),(404,1)])
def test_groq_http_contract_retries_and_redaction(dual,monkeypatch,status,expected):
    original=httpx.Client;requests=[]
    def handle(req):requests.append(req);return httpx.Response(status,json={'error':{'message':'private-response-secret'}})
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    with pytest.raises(ai.GroqAPIError) as error:ai._groq('test prompt')
    assert len(requests)==expected and requests[0].url=='https://api.groq.com/openai/v1/chat/completions'
    assert requests[0].headers['authorization']=='Bearer local-test-groq-key'
    assert json.loads(requests[0].content)['max_completion_tokens']==1536
    assert 'private-response-secret' not in ai.provider_error_detail(error.value)

def test_groq_usage_and_refusal(dual,monkeypatch):
    original=httpx.Client;blocked=[False]
    def handle(req):return httpx.Response(200,json={'choices':[{'message':{'content':'REPLY: hi\nMEANING: hi','refusal':'blocked' if blocked[0] else None},'finish_reason':'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':7,'total_tokens':18,'completion_tokens_details':{'reasoning_tokens':3}}})
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    assert ai._groq('safe').startswith('REPLY:')
    trace=ai.provider_trace.get();assert trace['input_tokens']==11 and trace['total_tokens']==18 and trace['thinking_tokens']==3
    blocked[0]=True
    with pytest.raises(ai.ProviderSafetyError):ai._groq('safe')

def test_api_failover_is_idempotent_and_health_reports_actual_provider(client,dual,monkeypatch):
    calls=[];provider(monkeypatch,'gemini',ai.GroqAPIError(503),calls);provider(monkeypatch,'groq','REPLY: recovered\nMEANING: English meaning',calls)
    body={'message':'safe','request_id':str(uuid.uuid4()),'conversation_id':'fallback-test'}
    first=client.post('/api/roast',headers=AUTH,json=body);second=client.post('/api/roast',headers=AUTH,json=body)
    assert first.status_code==second.status_code==200 and len(calls)==2
    assert first.json()['usage']['provider']=='groq'
    status=client.get('/api/platforms/status',headers=AUTH).json();assert status['provider_health']['provider']=='groq' and status['provider_health']['status']=='healthy'
    assert status['providers']['groq']['configured'] and status['fallback_enabled']
    assert len(client.get('/api/messages?sender_id=fallback-test',headers=AUTH).json())==2
    monkeypatch.setattr(settings,'ai_fallback_enabled',False)
    assert client.get('/api/platforms/status',headers=AUTH).json()['provider_health']['status']=='not_tested'

def test_both_fail_no_partial_conversation_or_secret_leaks(client,dual,monkeypatch):
    calls=[];provider(monkeypatch,'gemini',ai.GroqAPIError(503),calls);provider(monkeypatch,'groq',ai.GroqAPIError(429),calls)
    body={'message':'safe','request_id':str(uuid.uuid4()),'conversation_id':'failed-test'}
    r=client.post('/api/roast',headers=AUTH,json=body)
    assert r.status_code==502 and 'Gemini and Groq' in r.json()['detail']
    assert client.get('/api/messages?sender_id=failed-test',headers=AUTH).json()==[]
    assert 'local-test-groq-key' not in r.text+client.get('/api/activity',headers=AUTH).text
    assert client.post('/api/roast',headers=AUTH,json=body).status_code==502 and len(calls)==2


def test_autonomous_jobs_use_the_same_failover(client,dual,monkeypatch):
    calls=[];provider(monkeypatch,'gemini',ai.GroqAPIError(503),calls);provider(monkeypatch,'groq','REPLY: recovered\nMEANING: recovered',calls)
    main.update({'enabled':True,'dry_run':True,'reply_delay_seconds':0,'cooldown_seconds':0})
    import asyncio
    asyncio.run(main.process_job({'platform':'whatsapp','sender_id':'test-recipient','sender_name':'','message_id':'autonomous-failover','text':'safe'}))
    assert [n for n,_ in calls]==['gemini','groq']
    assert store.provider_status()['provider']=='groq' and store.provider_status()['status']=='healthy'


def test_real_gemini_error_type_fails_over(dual,monkeypatch):
    from google.genai.errors import ServerError
    calls=[];provider(monkeypatch,'gemini',ServerError(503,{'error':{'message':'private-google-detail'}}),calls)
    provider(monkeypatch,'groq','REPLY: recovered\nMEANING: recovered',calls)
    assert ai.generate_with_meaning('safe',BotSettings())[0]=='recovered'
    assert [n for n,_ in calls]==['gemini','groq']


def test_missing_primary_key_uses_configured_backup(dual,monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','');calls=[]
    provider(monkeypatch,'groq','REPLY: recovered\nMEANING: recovered',calls)
    assert ai.generate_with_meaning('safe',BotSettings())[0]=='recovered'
    assert ai.provider_trace.get()['providers'][0]['attempts']==0
    assert [n for n,_ in calls]==['groq']


def test_gemini_explicit_safety_finish_blocks_fallback(dual,monkeypatch):
    class Client:
        def __init__(self,**kwargs):self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):return SimpleNamespace(text='',candidates=[SimpleNamespace(finish_reason='SAFETY')])
    monkeypatch.setattr(ai.genai,'Client',Client);calls=[]
    provider(monkeypatch,'groq','REPLY: no\nMEANING: no',calls)
    with pytest.raises(ai.ProviderSafetyError):ai.generate_with_meaning('safe',BotSettings())
    assert calls==[]
