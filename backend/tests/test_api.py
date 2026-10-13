import os, tempfile, json, hashlib, hmac, asyncio
from pathlib import Path
import pytest
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'test.db')
os.environ['ENVIRONMENT']='development'
os.environ['ADMIN_TOKEN']='test-workspace-token-32-characters-long'
from fastapi.testclient import TestClient
from app.main import app, current, process_job, limits, update
from app import main, store
from app.config import settings
AUTH={'Authorization':'Bearer '+settings.admin_token}

@pytest.fixture
def client():
    with TestClient(app) as c:
        for table in ['messages','activity','preferences','webhook_jobs','processed_messages','generation_requests','provider_state','social_connections','social_oauth_states','social_page_candidates']:
            store.execute('DELETE FROM '+table)
        store.save_preferences(main.DEFAULT)
        limits.clear()
        yield c

def test_health_and_auth(client):
    assert client.get('/health').json()=={'status':'ok'}
    assert client.get('/api/settings').status_code==401
    assert client.get('/api/settings',headers=AUTH).status_code==200

def test_preferences_restart_and_stop(client):
    value=client.get('/api/settings',headers=AUTH).json();value.update(roast_mode='funny',intensity=4,custom_instructions='short')
    assert client.put('/api/settings',headers=AUTH,json=value).json()['intensity']==4
    store.init_db()
    assert current()['roast_mode']=='funny'
    client.post('/api/bot/start',headers=AUTH)
    client.post('/api/bot/emergency-stop',headers=AUTH)
    value['enabled']=True
    assert not client.put('/api/settings',headers=AUTH,json=value).json()['enabled']
    assert client.post('/api/roast',headers=AUTH,json={'message':'hi'}).status_code==409
    assert not client.post('/api/bot/start',headers=AUTH).json()['emergency_stop']
    assert not client.post('/api/bot/stop',headers=AUTH).json()['enabled']

def test_generation_history_meaning(client,monkeypatch):
    calls=[]
    def ai(message,cfg,*args):
        calls.append(cfg.roast_mode);return 'Test provider reply','Test meaning'
    monkeypatch.setattr(main,'generate_with_meaning',ai)
    value=current();value.update(roast_mode='deadpan',intensity=9)
    client.put('/api/settings',headers=AUTH,json=value)
    r=client.post('/api/roast',headers=AUTH,json={'message':'hello','reply_language':'hindi','script_mode':'native'})
    assert r.status_code==200 and r.json()['english_meaning']=='Test meaning' and calls==['deadpan']
    assert len(client.get('/api/messages',headers=AUTH).json())==2
    assert client.get('/api/conversations',headers=AUTH).json()[0]['message_count']==2
    assert client.get('/api/activity',headers=AUTH).json()[0]['category']=='ROAST'
    client.delete('/api/conversations',headers=AUTH)
    assert not client.get('/api/messages',headers=AUTH).json()
    assert client.get('/api/activity',headers=AUTH).json()

def test_validation_and_sanitized_errors(client,monkeypatch):
    assert client.post('/api/roast',headers=AUTH,json={'message':''}).status_code==422
    value=current();value['intensity']=11
    assert client.put('/api/settings',headers=AUTH,json=value).status_code==422
    def broken(*args): raise RuntimeError('SECRET_TOKEN_IN_UPSTREAM_EXCEPTION')
    monkeypatch.setattr(main,'generate_with_meaning',broken)
    r=client.post('/api/roast',headers=AUTH,json={'message':'hello'})
    assert r.status_code==502 and 'SECRET_TOKEN' not in r.text
    assert 'SECRET_TOKEN' not in json.dumps(store.activity())

def test_cors(client):
    r=client.options('/api/settings',headers={'Origin':settings.frontend_url,'Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'authorization,content-type'})
    assert r.status_code==200 and r.headers['access-control-allow-origin']==settings.frontend_url
    r=client.get('/api/settings',headers={'Origin':'https://evil.example'})
    assert 'access-control-allow-origin' not in r.headers
    r=client.get('/api/settings',headers={'Origin':settings.frontend_url})
    assert r.status_code==401 and r.headers['access-control-allow-origin']==settings.frontend_url

def test_verify_and_signature(client,monkeypatch):
    monkeypatch.setattr(settings,'meta_verify_token','verify-test')
    q='?hub.mode=subscribe&hub.verify_token=verify-test&hub.challenge=00123'
    r=client.get('/webhook/meta'+q);assert r.text=='00123' and 'text/plain' in r.headers['content-type']
    assert client.get('/webhook/meta?hub.mode=subscribe').status_code==403
    assert client.post('/webhook/meta',json={}).status_code==403
    monkeypatch.setattr(settings,'meta_app_secret','app-test-secret')
    body=b'[]';signature='sha256='+hmac.new(settings.meta_app_secret.encode(),body,hashlib.sha256).hexdigest()
    assert client.post('/webhook/meta',content=body,headers={'x-hub-signature-256':signature}).status_code==400

def test_durable_webhook_duplicate(client,monkeypatch):
    monkeypatch.setattr(settings,'meta_app_secret','test-secret')
    monkeypatch.setattr(settings,'whatsapp_phone_number_id','phone-test')
    payload={'object':'whatsapp_business_account','entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'phone-test'},'messages':[{'type':'text','from':'123','id':'mid1','text':{'body':'hi'}}]}}]}]}
    body=json.dumps(payload).encode();signature='sha256='+hmac.new(settings.meta_app_secret.encode(),body,hashlib.sha256).hexdigest()
    headers={'x-hub-signature-256':signature}
    assert client.post('/webhook/meta',content=body,headers=headers).json()['accepted']==1
    assert client.post('/webhook/meta',content=body,headers=headers).json()['accepted']==0
    assert len(store.query('SELECT * FROM webhook_jobs'))==1

@pytest.mark.parametrize('platform',['whatsapp','instagram'])
def test_dry_run_and_real_send(client,monkeypatch,platform):
    monkeypatch.setattr(settings,'social_delivery_approved',True)
    monkeypatch.setattr(main,'generate_with_meaning',lambda *args:('reply','meaning'))
    sent=[]
    async def send(*args): sent.append(args)
    monkeypatch.setattr(main,platform+'_send',send)
    update({'enabled':True,'reply_delay_seconds':0,'cooldown_seconds':0,'dry_run':True})
    event={'platform':platform,'sender_id':'user','sender_name':'User','message_id':'event1','text':'hi'}
    asyncio.run(process_job(event)); assert sent==[]
    update({'dry_run':False})
    asyncio.run(process_job(event)); assert sent==[('user','reply')]

def test_inflight_emergency(client,monkeypatch):
    def ai(*args):
        update({'enabled':False,'emergency_stop':True});return 'reply','meaning'
    monkeypatch.setattr(main,'generate_with_meaning',ai)
    sent=[]
    async def send(*args): sent.append(args)
    monkeypatch.setattr(main,'whatsapp_send',send)
    update({'enabled':True,'dry_run':False,'reply_delay_seconds':0})
    asyncio.run(process_job({'platform':'whatsapp','sender_id':'x','sender_name':'','message_id':'e','text':'hi'}))
    assert not sent and not any(m['direction']=='outgoing' for m in store.recent('whatsapp','x'))

def test_rate_limit(client,monkeypatch):
    monkeypatch.setattr(settings,'rate_limit_per_minute',1)
    monkeypatch.setattr(main,'generate_with_meaning',lambda *args:('reply','meaning'))
    assert client.post('/api/roast',headers=AUTH,json={'message':'one'}).status_code==200
    assert client.post('/api/roast',headers=AUTH,json={'message':'two'}).status_code==429

def test_latest_history(client):
    for i in range(105): store.add_message('local','roast-me','You','','incoming',str(i))
    rows=store.conversation_messages('local','roast-me')
    assert len(rows)==100 and rows[0]['text']=='5' and rows[-1]['text']=='104'

def test_instagram_ignores_echo():
    from app.meta import parse_events
    assert not parse_events({'object':'instagram','entry':[{'messaging':[{'sender':{'id':'x'},'message':{'mid':'m','text':'hi','is_echo':True}}]}]})

def test_pair_requires_meaning():
    from app.ai import _parse_pair
    assert _parse_pair('REPLY: hi\nMEANING: hello')==('hi','hello')
    with pytest.raises(RuntimeError): _parse_pair('REPLY: hi')

def test_emergency_bypasses_general_rate_limit(client,monkeypatch):
    monkeypatch.setattr(settings,'rate_limit_per_minute',1)
    for _ in range(8): client.get('/api/settings',headers=AUTH)
    assert client.get('/api/settings',headers=AUTH).status_code==429
    assert client.post('/api/bot/emergency-stop',headers=AUTH).status_code==200

def test_settings_save_does_not_start_bot(client):
    value=current();value['enabled']=True
    assert not client.put('/api/settings',headers=AUTH,json=value).json()['enabled']

def test_migration_preserves_legacy_rows(client):
    store.add_message('local','legacy','Legacy','','incoming','Keep this data')
    store.log('LEGACY','Keep this log')
    store.mark_processed('legacy-message')
    store.init_db();store.init_db()
    assert store.recent('local','legacy')[0]['text']=='Keep this data'
    assert store.activity()[0]['message']=='Keep this log'
    assert store.processed('legacy-message')

def test_adopts_original_v2_database_without_data_loss(tmp_path):
    import sqlite3, subprocess, sys
    legacy=tmp_path/'legacy.db'
    with sqlite3.connect(legacy) as connection:
        connection.executescript('''
        CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,platform TEXT,sender_id TEXT,sender_name TEXT,message_id TEXT,direction TEXT,text TEXT,timestamp TEXT);
        CREATE TABLE processed_messages(message_id TEXT PRIMARY KEY,timestamp TEXT);
        CREATE TABLE activity(id INTEGER PRIMARY KEY AUTOINCREMENT,category TEXT,message TEXT,timestamp TEXT);
        INSERT INTO messages(platform,sender_id,sender_name,message_id,direction,text,timestamp) VALUES('local','old','Owner','','incoming','Original data','2026-01-01');
        INSERT INTO activity(category,message,timestamp) VALUES('OLD','Original log','2026-01-01');
        INSERT INTO processed_messages VALUES('old-mid','2026-01-01');
        ''')
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(legacy)}
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    with sqlite3.connect(legacy) as connection:
        assert connection.execute('SELECT text FROM messages').fetchone()[0]=='Original data'
        assert connection.execute('SELECT message FROM activity').fetchone()[0]=='Original log'
        assert connection.execute('SELECT message_id FROM processed_messages').fetchone()[0]=='old-mid'
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0005'

def test_message_cursor_pagination_and_validation(client):
    for i in range(125): store.add_message('local','pages','Owner','','incoming',str(i))
    first=client.get('/api/messages?sender_id=pages',headers=AUTH).json()
    assert len(first)==100 and first[0]['text']=='25'
    second=client.get(f"/api/messages?sender_id=pages&before_id={first[0]['id']}",headers=AUTH).json()
    assert len(second)==25 and second[0]['text']=='0' and second[-1]['text']=='24'
    assert len({m['id'] for m in first+second})==125
    assert client.get('/api/messages?limit=101',headers=AUTH).status_code==422
    assert client.get('/api/messages?before_id=0',headers=AUTH).status_code==422
    assert not client.get(f"/api/messages?sender_id=other&before_id={first[0]['id']}",headers=AUTH).json()


def test_accounts_isolate_history_settings_and_logout(client,monkeypatch):
    import secrets
    def signup():
        response=client.post('/api/auth/signup',json={'email':secrets.token_hex(8)+'@example.com','password':'a-strong-test-password'})
        assert response.status_code==200,response.text
        return {'Authorization':'Bearer '+response.json()['token']}
    a,b=signup(),signup()
    monkeypatch.setattr(main,'generate_with_meaning',lambda *args:('private reply','meaning'))
    assert client.post('/api/roast',headers=a,json={'message':'private input'}).status_code==200
    assert len(client.get('/api/messages',headers=a).json())==2
    assert client.get('/api/messages',headers=b).json()==[]
    assert client.get('/api/messages',headers=AUTH).json()==[]
    assert client.get('/api/activity',headers=b).json()==[]
    preferences=client.get('/api/settings',headers=a).json();preferences['intensity']=2
    assert client.put('/api/settings',headers=a,json=preferences).status_code==200
    assert client.get('/api/settings',headers=b).json()['intensity']!=2
    assert client.post('/api/bot/start',headers=a).status_code==200
    assert client.get('/api/settings',headers=b).json()['enabled'] is False
    client.delete('/api/conversations',headers=b)
    assert len(client.get('/api/messages',headers=a).json())==2
    assert client.post('/api/auth/logout',headers=a).status_code==200
    assert client.get('/api/messages',headers=a).status_code==401


def test_gemini_supported_thinking_and_single_call(monkeypatch):
    from app import ai
    from types import SimpleNamespace
    calls=[]
    class Client:
        def __init__(self,**kwargs): self.models=self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def generate_content(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text='REPLY: comeback\nMEANING: English meaning')
    monkeypatch.setattr(ai.genai,'Client',Client)
    monkeypatch.setattr(ai.settings,'gemini_api_key','test-key-not-a-real-credential')
    monkeypatch.setattr(ai.settings,'gemini_model','gemini-3.8-flash')
    assert ai._gemini('prompt').startswith('REPLY:')
    assert len(calls)==1
    assert calls[0]['config'].thinking_config.thinking_level.value=='LOW'
    assert calls[0]['config'].max_output_tokens==1536

def test_provider_error_does_not_expose_upstream_details():
    from app.ai import provider_error_detail
    from google.genai.errors import ClientError
    detail=provider_error_detail(ClientError(429,{'error':{'message':'secret-token-url'}}))
    assert 'quota' in detail.lower() and 'secret-token' not in detail


def test_google_nonce_replay_and_existing_account_link(client,monkeypatch):
    import secrets
    from app import accounts
    monkeypatch.setattr(main.settings,'google_client_id','test-client')
    email=secrets.token_hex(8)+'@example.com'
    token=client.post('/api/auth/signup',json={'email':email,'password':'strong-google-test-password'}).json()['token']
    nonce=client.post('/api/auth/google/challenge').json()['nonce']
    monkeypatch.setattr(accounts,'verify_google',lambda credential:{'sub':secrets.token_hex(10),'email':email,'nonce':nonce})
    payload={'credential':'a-test-credential-not-real','nonce':nonce}
    assert client.post('/api/auth/google',json=payload).status_code==409
    nonce=client.post('/api/auth/google/challenge').json()['nonce'];payload['nonce']=nonce
    subject=secrets.token_hex(10)
    monkeypatch.setattr(accounts,'verify_google',lambda credential:{'sub':subject,'email':email,'nonce':nonce})
    result=client.post('/api/auth/google/link',headers={'Authorization':'Bearer '+token},json=payload)
    assert result.status_code==200,result.text
    assert client.post('/api/auth/google',json=payload).status_code==401
    nonce=client.post('/api/auth/google/challenge').json()['nonce'];payload['nonce']=nonce
    assert client.post('/api/auth/google',json=payload).status_code==200


def test_google_new_account_private_session_and_wrong_nonce(client,monkeypatch):
    import secrets
    from app import accounts
    monkeypatch.setattr(main.settings,'google_client_id','test-client')
    nonce=client.post('/api/auth/google/challenge').json()['nonce']
    claims={'sub':secrets.token_hex(10),'email':secrets.token_hex(8)+'@example.com','nonce':'wrong'}
    monkeypatch.setattr(accounts,'verify_google',lambda credential:claims)
    data={'credential':'a-test-credential-not-real','nonce':nonce}
    assert client.post('/api/auth/google',json=data).status_code==401
    claims['nonce']=nonce
    result=client.post('/api/auth/google',json=data)
    assert result.status_code==200,result.text
    assert client.get('/api/messages',headers={'Authorization':'Bearer '+result.json()['token']}).json()==[]
    assert client.post('/api/auth/login',json={'email':claims['email'],'password':'strong-google-test-password'}).status_code==401


def test_facebook_page_filter_and_echo(monkeypatch):
    from app.meta import parse_events
    monkeypatch.setattr(main.settings,'facebook_page_id','page-123')
    event={'sender':{'id':'friend'},'message':{'text':'hello','mid':'m123'}}
    assert parse_events({'object':'page','entry':[{'id':'wrong','messaging':[event]}]})==[]
    parsed=parse_events({'object':'page','entry':[{'id':'page-123','messaging':[event]}]})
    assert parsed[0]['platform']=='facebook'
    event['message']['is_echo']=True
    assert parse_events({'object':'page','entry':[{'id':'page-123','messaging':[event]}]})==[]


def test_snapchat_send_safety_and_dry_run(client,monkeypatch):
    monkeypatch.setattr(settings,'social_delivery_approved',True)
    from app import snapchat
    calls=[]
    async def conversation(creator): calls.append('conversation');return {'conversation_id':'id','token':'token'}
    async def send(conv,message): calls.append('send');return {'accepted':True}
    monkeypatch.setattr(snapchat,'conversation',conversation);monkeypatch.setattr(snapchat,'send',send)
    payload={'creator_profile_id':'11111111-1111-1111-1111-111111111111','message':'Collaboration invitation'}
    assert client.post('/api/snapchat/messages',headers=AUTH,json=payload).status_code==409
    client.post('/api/bot/start',headers=AUTH)
    result=client.post('/api/snapchat/messages',headers=AUTH,json=payload)
    assert result.json()['dry_run'] and not calls
    preferences=client.get('/api/settings',headers=AUTH).json();preferences['dry_run']=False
    client.put('/api/settings',headers=AUTH,json=preferences)
    assert client.post('/api/snapchat/messages',headers=AUTH,json=payload).json()['accepted']
    assert calls==['conversation','send']
    client.post('/api/bot/emergency-stop',headers=AUTH)
    assert client.post('/api/snapchat/messages',headers=AUTH,json=payload).status_code==409
    assert calls==['conversation','send']


def test_snapchat_rejects_partial_success(monkeypatch):
    import asyncio
    from app import snapchat
    from fastapi import HTTPException
    async def api(*args,**kwargs): return {'request_status':'SUCCESS','group_conversation_messages':[{'sub_request_status':'ERROR'}]}
    monkeypatch.setattr(snapchat,'api',api)
    with pytest.raises(HTTPException): asyncio.run(snapchat.send({'conversation_id':'id','token':'token'},'test'))


def test_idempotent_generation_and_separate_threads(client,monkeypatch):
    import uuid
    calls=[]
    monkeypatch.setattr(main,'generate_with_meaning',lambda *args:(calls.append(args) or ('safe reply','meaning')))
    rid=str(uuid.uuid4());payload={'request_id':rid,'conversation_id':'thread-one','message':'Safe identical prompt'}
    first=client.post('/api/roast',headers=AUTH,json=payload)
    second=client.post('/api/roast',headers=AUTH,json=payload)
    assert first.status_code==second.status_code==200 and len(calls)==1
    assert len(client.get('/api/messages?sender_id=thread-one',headers=AUTH).json())==2
    payload['message']='changed'
    assert client.post('/api/roast',headers=AUTH,json=payload).status_code==409
    assert len(calls)==1
    assert client.get('/api/messages?sender_id=thread-two',headers=AUTH).json()==[]
    payload.update(request_id=str(uuid.uuid4()),conversation_id='thread-two')
    assert client.post('/api/roast',headers=AUTH,json=payload).status_code==200
    assert len(client.get('/api/conversations',headers=AUTH).json())==2
    store.init_db()
    assert len(client.get('/api/messages?sender_id=thread-one',headers=AUTH).json())==2


def test_failure_status_request_id_and_no_partial_messages(client,monkeypatch):
    import uuid
    from google.genai.errors import ServerError
    calls=[]
    def failed(*args): calls.append(1);raise ServerError(503,{'error':{'message':'PRIVATE-UPSTREAM-KEY'}})
    monkeypatch.setattr(main,'generate_with_meaning',failed)
    payload={'request_id':str(uuid.uuid4()),'message':'Safe prompt'}
    result=client.post('/api/roast',headers=AUTH,json=payload)
    assert result.status_code==502 and result.json()['provider_status']==503
    assert result.headers['X-Request-ID']==payload['request_id']
    assert 'PRIVATE-UPSTREAM' not in result.text
    assert not client.get('/api/messages',headers=AUTH).json()
    assert client.get('/api/platforms/status',headers=AUTH).json()['provider_health']['status']=='unavailable'
    assert client.post('/api/roast',headers=AUTH,json=payload).status_code==502 and len(calls)==1


def test_account_expiry_hashes_and_deep_isolation(client,monkeypatch):
    from app import accounts
    import secrets,time,uuid
    password=secrets.token_urlsafe(16)
    creds={'email':secrets.token_hex(8)+'@example.com','password':password}
    token=client.post('/api/auth/signup',json=creds).json()['token'];a={'Authorization':'Bearer '+token}
    btoken=client.post('/api/auth/signup',json={**creds,'email':secrets.token_hex(8)+'@example.com'}).json()['token'];b={'Authorization':'Bearer '+btoken}
    user=store.query('SELECT * FROM users WHERE email=:e',e=creds['email'])[0]
    assert user['password_hash'].startswith('v2$') and password not in user['password_hash']
    assert accounts.password_matches(password,user['password_hash']) and not accounts.password_matches('wrong',user['password_hash'])
    monkeypatch.setattr(main,'generate_with_meaning',lambda *args:('private result','meaning'))
    rid=str(uuid.uuid4());payload={'message':'private','request_id':rid,'conversation_id':'private-thread'}
    assert client.post('/api/roast',headers=a,json=payload).status_code==200
    assert client.get('/api/messages?sender_id=private-thread',headers=b).json()==[]
    assert client.get('/api/conversations',headers=b).json()==[]
    assert client.get('/api/activity',headers=b).json()==[]
    assert client.post('/api/bot/start',headers=b).status_code==200
    assert client.get('/api/settings',headers=a).json()['enabled'] is False
    assert client.get('/api/snapchat/messages?creator_profile_id='+str(uuid.uuid4()),headers=b).status_code==403
    assert client.post('/api/roast',headers=b,json=payload).status_code==200 # same request ID is scoped to its own account
    store.execute('UPDATE sessions SET expires=:t WHERE user_id=:u',t=time.time()-1,u=user['id'])
    assert client.get('/api/settings',headers=a).status_code==401


def test_legacy_password_upgrade(client):
    import secrets
    from app import accounts
    salt=secrets.token_hex(16);password='legacy-password-strong';email=secrets.token_hex(8)+'@example.com'
    old=salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    store.execute('INSERT INTO users(email,password_hash) VALUES(:e,:p)',e=email,p=old)
    assert client.post('/api/auth/login',json={'email':email,'password':password}).status_code==200
    assert store.query('SELECT password_hash FROM users WHERE email=:e',e=email)[0]['password_hash'].startswith('v2$')


@pytest.mark.parametrize('mode',['normal','funny','sarcastic','savage','brutal','deadpan','intelligent','respectful','vulgar'])
def test_mode_reaches_provider_prompt(mode,monkeypatch):
    from app import ai
    from app.models import BotSettings
    prompts=[]
    monkeypatch.setattr(ai,'ask',lambda prompt:(prompts.append(prompt) or 'REPLY: safe\nMEANING: safe'))
    ai.generate_with_meaning('You are late again.',BotSettings(roast_mode=mode,profanity_level='off'))
    assert ai.MODES[mode] in prompts[0] and 'no profanity' in prompts[0] and 'Profanity setting overrides mode' in prompts[0]


@pytest.mark.parametrize('intensity',range(1,11))
def test_intensity_reaches_provider_prompt(intensity,monkeypatch):
    from app import ai
    from app.models import BotSettings
    prompts=[]
    monkeypatch.setattr(ai,'ask',lambda prompt:(prompts.append(prompt) or 'REPLY: safe\nMEANING: safe'))
    ai.generate_with_meaning('You are late again.',BotSettings(intensity=intensity))
    assert f'Intensity: {intensity}/10' in prompts[0]


@pytest.mark.parametrize('language',['same','english','hindi','kannada','malayalam','tamil','telugu','bengali','marathi','punjabi','urdu'])
@pytest.mark.parametrize('script',['native','roman'])
def test_language_script_voice_length(language,script,monkeypatch):
    from app import ai
    from app.models import BotSettings
    prompts=[]
    monkeypatch.setattr(ai,'ask',lambda prompt:(prompts.append(prompt) or 'REPLY: '+('a'*100)+'\nMEANING: safe'))
    result,_=ai.generate_with_meaning('You are late again.',BotSettings(custom_instructions='Use a dry librarian voice',max_reply_length=50),reply_language=language,script_mode=script)
    assert len(result)<=50 and ai.LANGUAGES[language] in prompts[0] and 'dry librarian voice' in prompts[0]
    assert ('normal native script' if script=='native' else 'Romanized script') in prompts[0]


@pytest.mark.parametrize('code,expected_calls',[(503,2),(500,2),(403,1),(404,1),(429,1)])
def test_bounded_provider_retries(code,expected_calls,monkeypatch):
    from app import ai
    from google.genai.errors import ClientError,ServerError
    calls=[]
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['http_options'].retry_options.attempts==1
            self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):
            calls.append(kwargs)
            raise (ServerError if code>=500 else ClientError)(code,{'error':{'message':'upstream-private'}})
    monkeypatch.setattr(ai.genai,'Client',Client);monkeypatch.setattr(settings,'gemini_api_key','test-key')
    monkeypatch.setattr(ai.time,'sleep',lambda *args:None)
    with pytest.raises(Exception):ai._gemini('safe')
    assert len(calls)==expected_calls


def test_sdk_usage_and_recovery(monkeypatch):
    from app import ai
    from types import SimpleNamespace
    from google.genai.errors import ServerError
    calls=[]
    class Client:
        def __init__(self,**kwargs):self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):
            calls.append(1)
            if len(calls)==1:raise ServerError(503,{'error':{}})
            return SimpleNamespace(text='REPLY: hello\nMEANING: hello',usage_metadata=SimpleNamespace(prompt_token_count=100,candidates_token_count=20,thoughts_token_count=30,total_token_count=150))
    monkeypatch.setattr(ai.genai,'Client',Client);monkeypatch.setattr(settings,'gemini_api_key','test-key');monkeypatch.setattr(ai.time,'sleep',lambda *args:None)
    assert ai._gemini('safe').startswith('REPLY:')
    trace=ai.provider_trace.get();assert trace['attempts']==2 and trace['input_tokens']==100 and trace['thinking_tokens']==30


def test_validation_does_not_echo_secret(client):
    secret='private-password'
    response=client.post('/api/auth/login',json={'email':'bad','password':secret})
    assert response.status_code==422 and secret not in response.text


def test_unknown_account_events_and_delivery_approval(client,monkeypatch):
    from app.meta import parse_events
    monkeypatch.setattr(settings,'whatsapp_phone_number_id','owned')
    event={'object':'whatsapp_business_account','entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'wrong'},'messages':[{'type':'text','from':'friend','id':'mid','text':{'body':'hi'}}]}}]}]}
    assert parse_events(event)==[]
    monkeypatch.setattr(settings,'social_delivery_approved',False);monkeypatch.setattr(main,'generate_with_meaning',lambda *args:('reply','meaning'))
    calls=[]
    async def send(*args):calls.append(1)
    monkeypatch.setattr(main,'whatsapp_send',send)
    update({'enabled':True,'dry_run':False,'reply_delay_seconds':0})
    asyncio.run(process_job({'platform':'whatsapp','sender_id':'friend','sender_name':'','message_id':'safe','text':'hi'}))
    assert not calls


@pytest.mark.parametrize('model,level',[('gemini-3.8-flash','LOW'),('gemini-3.5-flash-lite','MINIMAL')])
def test_model_specific_thinking(model,level,monkeypatch):
    from app import ai
    from types import SimpleNamespace
    class Client:
        def __init__(self,**kwargs):self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):
            assert kwargs['config'].thinking_config.thinking_level.value==level
            return SimpleNamespace(text='REPLY: safe\nMEANING: safe')
    monkeypatch.setattr(ai.genai,'Client',Client);monkeypatch.setattr(settings,'gemini_model',model);monkeypatch.setattr(settings,'gemini_api_key','test-key')
    ai._gemini('safe')


def test_concurrent_duplicate_starts_only_one_generation(client,monkeypatch):
    import uuid,threading
    from concurrent.futures import ThreadPoolExecutor
    entered=threading.Event();release=threading.Event();calls=[]
    def slow(*args):
        calls.append(1);entered.set();assert release.wait(5);return 'single reply','meaning'
    monkeypatch.setattr(main,'generate_with_meaning',slow)
    payload={'message':'safe simultaneous request','request_id':str(uuid.uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.post,'/api/roast',headers=AUTH,json=payload)
        try:
            assert entered.wait(3)
            second=client.post('/api/roast',headers=AUTH,json=payload)
            assert second.status_code==409 and len(calls)==1
        finally:release.set()
        assert first.result(timeout=5).status_code==200
    assert len(client.get('/api/messages',headers=AUTH).json())==2


@pytest.mark.parametrize('change',[{'aud':'attacker-client'},{'iss':'https://attacker.example'},{'email_verified':False},{'sub':''}])
def test_google_claim_validation(change,monkeypatch):
    from app import accounts
    from google.oauth2 import id_token
    from fastapi import HTTPException
    monkeypatch.setattr(settings,'google_client_id','our-client')
    claims={'aud':'our-client','iss':'https://accounts.google.com','email_verified':True,'sub':'subject','email':'qa@example.com',**change}
    monkeypatch.setattr(id_token,'verify_oauth2_token',lambda *args:claims)
    with pytest.raises(HTTPException) as error:accounts.verify_google('test-credential')
    assert error.value.status_code==401


def test_access_logs_redact_webhook_verification_and_private_queries():
    import logging
    from app.observability import AccessLogPrivacyFilter
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',('127.0.0.1','GET','/webhook/meta?hub.verify_token=private-verify-token&hub.challenge=123','1.1',200),None)
    AccessLogPrivacyFilter().filter(record)
    assert 'private-verify-token' not in record.getMessage() and 'hub.challenge' not in record.getMessage()
    assert '/webhook/meta' in record.getMessage() and '200' in record.getMessage()

# Official Instagram calls below are labelled local test doubles, never real sends.
def social_config(monkeypatch):
    from app import social
    for k,v in {'social_token_encryption_key':'test-encryption-key-at-least-32-characters','instagram_client_id':'12345','instagram_client_secret':'test-app-secret','backend_url':'https://backend.example.com','meta_verify_token':'test-verify'}.items():monkeypatch.setattr(settings,k,v)
    return social

def social_user(client):
    import secrets
    email=secrets.token_hex(8)+'@example.com'
    r=client.post('/api/auth/signup',json={'email':email,'password':'test-password-over-12-characters'});assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['token']},store.query('SELECT id FROM users WHERE email=:e',e=email)[0]['id']

def attach(social,uid,account):
    import time
    context=store.owner.set(uid)
    try:social.persist(account,'qa_creator','test-private-token',time.time()+3600);return social.listing()['connections'][0]
    finally:store.owner.reset(context)

def test_personal_bot_and_emergency_isolation(client):
    a,_=social_user(client);b,_=social_user(client)
    assert client.post('/api/bot/start',headers=a).json()['enabled']
    assert not client.get('/api/settings',headers=b).json()['enabled']
    assert not client.get('/api/settings',headers=AUTH).json()['enabled']
    assert client.post('/api/bot/emergency-stop',headers=a).json()['emergency_stop']
    assert not client.get('/api/settings',headers=b).json()['emergency_stop']
    assert not client.post('/api/bot/start',headers=a).json()['emergency_stop']
    assert not client.post('/api/bot/stop',headers=a).json()['enabled']

def test_encrypted_social_account_isolation_and_claim_conflict(client,monkeypatch):
    social=social_config(monkeypatch);a,aid=social_user(client);b,bid=social_user(client)
    attach(social,aid,'123456')
    row=store.query('SELECT * FROM social_connections')[0]
    assert 'test-private-token' not in row['token_ciphertext'] and social.decrypt(row)=='test-private-token'
    r=client.get('/api/social/connections',headers=a);assert len(r.json()['connections'])==1 and 'token' not in json.dumps(r.json()['connections'])
    assert client.get('/api/social/connections',headers=b).json()['connections']==[]
    with pytest.raises(__import__('fastapi').HTTPException) as e:attach(social,bid,'123456')
    assert e.value.status_code==409 and store.query('SELECT owner_id FROM social_connections')[0]['owner_id']==aid
    assert not client.get('/api/platforms/status',headers=b).json()['instagram']
    assert client.get('/api/platforms/status',headers=a).json()['instagram']
    client.post('/api/bot/start',headers=a);client.post('/api/bot/start',headers=b)
    client.delete('/api/social/connections/instagram',headers=b)
    assert len(client.get('/api/social/connections',headers=a).json()['connections'])==1
    assert client.get('/api/settings',headers=a).json()['enabled']
    client.delete('/api/social/connections/instagram',headers=a)
    assert client.get('/api/social/connections',headers=a).json()['connections']==[]
    assert not client.get('/api/settings',headers=a).json()['enabled']

def test_setup_and_invalid_oauth_are_honest(client,monkeypatch):
    monkeypatch.setattr(settings,'social_token_encryption_key','')
    a,_=social_user(client)
    assert client.post('/api/social/instagram/connect',headers=a).status_code==503
    assert not client.get('/api/social/connections',headers=a).json()['instagram_oauth_configured']
    assert client.get('/oauth/instagram/callback?state=invalid&code=test').status_code==400

def test_oauth_state_owner_bound_single_use_expiry(client,monkeypatch):
    from urllib.parse import urlparse,parse_qs
    social=social_config(monkeypatch);a,aid=social_user(client)
    q=parse_qs(urlparse(client.post('/api/social/instagram/connect',headers=a).json()['url']).query)
    assert q['redirect_uri']==['https://backend.example.com/oauth/instagram/callback']
    assert 'instagram_business_manage_messages' in q['scope'][0]
    state=q['state'][0];assert state not in json.dumps(store.query('SELECT * FROM social_oauth_states'))
    assert social.consume(state)==aid
    with pytest.raises(__import__('fastapi').HTTPException):social.consume(state)
    state=parse_qs(urlparse(client.post('/api/social/instagram/connect',headers=a).json()['url']).query)['state'][0]
    store.execute('UPDATE social_oauth_states SET expires_at=0')
    with pytest.raises(__import__('fastapi').HTTPException):social.consume(state)

@pytest.mark.parametrize('fault',[None,'permissions','identity','subscription'])
def test_oauth_provider_success_failures_and_no_secrets(client,monkeypatch,fault):
    from urllib.parse import urlparse,parse_qs
    social=social_config(monkeypatch);a,aid=social_user(client);calls=[]
    async def graph(client,method,url,**kwargs):
        calls.append(url)
        if url=='https://api.instagram.com/oauth/access_token':return {'access_token':'short-secret','user_id':'777777','permissions':['instagram_business_basic'] if fault=='permissions' else ['instagram_business_basic','instagram_business_manage_messages']}
        if url.endswith('/access_token'):return {'access_token':'long-secret','expires_in':3600}
        if url.endswith('/me'):return {'user_id':'999999' if fault=='identity' else '777777','username':'qa_creator'}
        if url.endswith('/subscribed_apps'):return {'success':fault!='subscription'}
        raise AssertionError(url)
    monkeypatch.setattr(social,'graph',graph)
    state=parse_qs(urlparse(client.post('/api/social/instagram/connect',headers=a).json()['url']).query)['state'][0]
    r=client.get('/oauth/instagram/callback',params={'state':state,'code':'local-test-code'},follow_redirects=False)
    assert r.status_code==303 and 'social='+('failed' if fault else 'connected') in r.headers['location']
    assert 'secret' not in r.text+r.headers['location']
    assert len(client.get('/api/social/connections',headers=a).json()['connections'])==(0 if fault else 1)
    assert 'secret' not in client.get('/api/activity',headers=a).text
    assert all(not url.endswith('/messages') for url in calls)

def test_tenant_webhook_signature_routing_duplicate_and_window(client,monkeypatch):
    import time
    social=social_config(monkeypatch);a,aid=social_user(client);b,_=social_user(client)
    attach(social,aid,'888888')
    payload={'object':'instagram','entry':[{'id':'888888','messaging':[{'timestamp':time.time()*1000,'sender':{'id':'friend'},'message':{'mid':'test-mid','text':'hello'}}]}]}
    body=json.dumps(payload).encode();signature='sha256='+hmac.new(settings.instagram_client_secret.encode(),body,hashlib.sha256).hexdigest()
    assert client.post('/webhook/meta',content=body,headers={'x-hub-signature-256':signature}).json()['accepted']==1
    assert client.post('/webhook/meta',content=body,headers={'x-hub-signature-256':signature}).json()['accepted']==0
    event=json.loads(store.query('SELECT data FROM webhook_jobs')[0]['data']);assert event['owner_id']==aid
    asyncio.run(process_job(event))
    assert client.get('/api/messages?platform=instagram&sender_id=888888:friend',headers=a).json()
    assert client.get('/api/messages?platform=instagram&sender_id=888888:friend',headers=b).json()==[]
    assert client.get('/api/messages?platform=instagram&sender_id=888888:friend',headers=AUTH).json()==[]
    other=json.dumps({'object':'page'}).encode();signature='sha256='+hmac.new(settings.instagram_client_secret.encode(),other,hashlib.sha256).hexdigest()
    assert client.post('/webhook/meta',content=other,headers={'x-hub-signature-256':signature}).status_code==403

def test_user_worker_voice_dry_run_and_disconnected_cancellation(client,monkeypatch):
    import time
    social=social_config(monkeypatch);a,aid=social_user(client);b,_=social_user(client);calls=[]
    row=attach(social,aid,'555555');context=store.owner.set(aid)
    try:update({'enabled':True,'roast_mode':'deadpan','reply_delay_seconds':0,'cooldown_seconds':0,'dry_run':False})
    finally:store.owner.reset(context)
    monkeypatch.setattr(settings,'social_delivery_approved',False)
    monkeypatch.setattr(main,'generate_with_meaning',lambda message,cfg,*args:(calls.append((store.owner.get(),cfg.roast_mode)) or 'reply','meaning'))
    async def forbidden(*args):raise AssertionError('No live sends allowed')
    monkeypatch.setattr(social,'send',forbidden)
    event={'platform':'instagram','sender_id':'friend','sender_name':'','message_id':'test-worker','text':'hi','owner_id':aid,'connection_id':row['id'],'received_at':time.time()}
    asyncio.run(process_job(event));assert calls==[(aid,'deadpan')]
    assert len(client.get('/api/messages?platform=instagram&sender_id=friend',headers=a).json())==2
    assert client.get('/api/messages?platform=instagram&sender_id=friend',headers=b).json()==[]
    assert any(e['category']=='DRY_RUN' for e in client.get('/api/activity',headers=a).json())
    client.delete('/api/social/connections/instagram',headers=a)
    asyncio.run(process_job(event));assert len(calls)==1
    asyncio.run(process_job({**event,'connection_id':None,'received_at':time.time()-24*3600}));assert len(calls)==1

def meta_social_config(monkeypatch):
    social=social_config(monkeypatch)
    for k,v in {'meta_app_id':'12345','meta_app_secret':'test-meta-app-secret','whatsapp_signup_config_id':'test-business-config'}.items():monkeypatch.setattr(settings,k,v)
    return social

@pytest.mark.parametrize('fault',[None,'permission','no_pages','subscription'])
def test_facebook_page_oauth_selection_and_isolation(client,monkeypatch,fault):
    from urllib.parse import urlparse,parse_qs
    social=meta_social_config(monkeypatch);a,aid=social_user(client);b,bid=social_user(client);calls=[]
    async def graph(client,method,url,**kwargs):
        calls.append(url)
        if url.endswith('/oauth/access_token'):return {'access_token':'test-fb-user-secret','expires_in':3600}
        if url.endswith('/me/permissions'):return {'data':[{'permission':p,'status':'granted'} for p in (['pages_show_list'] if fault=='permission' else ['pages_show_list','pages_messaging','pages_manage_metadata'])]}
        if url.endswith('/me/accounts'):return {'data':[] if fault=='no_pages' else [{'id':'987654','name':'QA Page','access_token':'test-page-secret','tasks':['MESSAGE']}]}
        if url.endswith('/subscribed_apps'):return {'success':fault!='subscription'}
        raise AssertionError(url)
    monkeypatch.setattr(social,'graph',graph)
    q=parse_qs(urlparse(client.post('/api/social/facebook/connect',headers=a).json()['url']).query)
    assert q['redirect_uri']==['https://backend.example.com/oauth/facebook/callback']
    callback=client.get('/oauth/facebook/callback',params={'state':q['state'][0],'code':'test-fb-code'},follow_redirects=False)
    assert callback.status_code==303
    if fault in ('permission','no_pages'):
        assert 'social=failed' in callback.headers['location'];return
    assert 'social=select_page' in callback.headers['location']
    data=client.get('/api/social/connections',headers=a).json();candidate=data['facebook_candidates'][0]
    assert 'test-page-secret' not in json.dumps(data)
    assert client.get('/api/social/connections',headers=b).json()['facebook_candidates']==[]
    assert client.post('/api/social/facebook/select',headers=b,json={'candidate_id':candidate['id']}).status_code==404
    selected=client.post('/api/social/facebook/select',headers=a,json={'candidate_id':candidate['id']})
    assert selected.status_code==(502 if fault=='subscription' else 200)
    rows=client.get('/api/social/connections',headers=a).json()['connections']
    assert len(rows)==(0 if fault else 1)
    assert not any(url.endswith('/messages') for url in calls)
    if not fault:assert rows[0]['platform']=='facebook' and rows[0]['account_id']=='987654'

@pytest.mark.parametrize('fault',[None,'app','scope','phone','expired','registration','subscription'])
def test_whatsapp_signup_verifies_app_ownership_scopes_phone_and_ack(client,monkeypatch,fault):
    import time
    social=meta_social_config(monkeypatch);a,aid=social_user(client);calls=[]
    async def graph(client,method,url,**kwargs):
        calls.append(url)
        if url.endswith('/oauth/access_token'):return {'access_token':'test-whatsapp-secret'}
        if url.endswith('/debug_token'):return {'data':{'is_valid':True,'app_id':'other' if fault=='app' else settings.meta_app_id,'scopes':['whatsapp_business_management'] if fault=='scope' else ['whatsapp_business_management','whatsapp_business_messaging'],'expires_at':time.time()-100 if fault=='expired' else time.time()+3600}}
        if url.endswith('/phone_numbers'):return {'data':[{'id':'wrong' if fault=='phone' else '654321','verified_name':'QA Business'}]}
        if url.endswith('/register'):
            assert kwargs['json']['pin']=='123456';return {'success':fault!='registration'}
        if url.endswith('/subscribed_apps'):return {'success':fault!='subscription'}
        raise AssertionError(url)
    monkeypatch.setattr(social,'graph',graph)
    start=client.post('/api/social/whatsapp/connect',headers=a).json()
    result=client.post('/api/social/whatsapp/complete',headers=a,json={'state':start['state'],'code':'test-code','phone_number_id':'654321','waba_id':'666666','pin':'123456'})
    assert result.status_code==(200 if not fault else 502 if fault in ('registration','subscription') else 403),result.text
    assert 'secret' not in result.text and '123456' not in result.text
    data=client.get('/api/social/connections',headers=a).json();assert len(data['connections'])==(0 if fault else 1)
    assert 'test-whatsapp-secret' not in json.dumps(data)
    assert not any(url.endswith('/messages') for url in calls)
    if not fault:assert data['connections'][0]['platform']=='whatsapp'

def test_whatsapp_nonce_cannot_be_used_by_another_user(client,monkeypatch):
    meta_social_config(monkeypatch);a,_=social_user(client);b,_=social_user(client)
    start=client.post('/api/social/whatsapp/connect',headers=a).json()
    assert client.post('/api/social/whatsapp/complete',headers=b,json={'state':start['state'],'code':'test','phone_number_id':'1','waba_id':'2','pin':'123456'}).status_code in (400,403)

@pytest.mark.parametrize('platform',['instagram','facebook','whatsapp'])
def test_connected_platforms_route_to_only_the_registered_user(client,monkeypatch,platform):
    import time
    social=meta_social_config(monkeypatch);a,aid=social_user(client);b,bid=social_user(client)
    context=store.owner.set(aid)
    try:social.persist('444444','qa','test-token',time.time()+3600,platform)
    finally:store.owner.reset(context)
    if platform=='whatsapp':payload={'object':'whatsapp_business_account','entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'444444'},'messages':[{'id':'m','from':'friend','type':'text','timestamp':str(int(time.time())),'text':{'body':'hello'}}]}}]}]}
    else:payload={'object':'instagram' if platform=='instagram' else 'page','entry':[{'id':'444444','messaging':[{'timestamp':time.time()*1000,'sender':{'id':'friend'},'message':{'mid':'m','text':'hello'}}]}]}
    body=json.dumps(payload).encode();key=settings.instagram_client_secret if platform=='instagram' else settings.meta_app_secret
    signature='sha256='+hmac.new(key.encode(),body,hashlib.sha256).hexdigest()
    response=client.post('/webhook/meta',content=body,headers={'x-hub-signature-256':signature});assert response.json()['accepted']==1,response.text
    event=json.loads(store.query('SELECT data FROM webhook_jobs')[0]['data']);assert event['owner_id']==aid and event['platform']==platform
    asyncio.run(process_job(event))
    assert client.get('/api/messages?platform='+platform+'&sender_id=444444:friend',headers=a).json()
    assert client.get('/api/messages?platform='+platform+'&sender_id=444444:friend',headers=b).json()==[]


def test_logout_invalidates_pending_social_authorization(client,monkeypatch):
    from urllib.parse import urlparse,parse_qs
    social=social_config(monkeypatch);a,aid=social_user(client)
    state=parse_qs(urlparse(client.post('/api/social/instagram/connect',headers=a).json()['url']).query)['state'][0]
    assert client.post('/api/auth/logout',headers=a).status_code==200
    assert client.get('/oauth/instagram/callback',params={'state':state,'code':'test-code'}).status_code==400
    assert client.get('/api/social/connections',headers=a).status_code==401


def test_replaced_connection_cancels_dry_run_after_ai(client,monkeypatch):
    import time
    social=social_config(monkeypatch);a,aid=social_user(client);row=attach(social,aid,'333333')
    context=store.owner.set(aid)
    try:update({'enabled':True,'reply_delay_seconds':0,'cooldown_seconds':0,'dry_run':True})
    finally:store.owner.reset(context)
    def ai(*args):
        social.persist('333333','reauthorized','new-test-token',time.time()+3600)
        return 'reply','meaning'
    monkeypatch.setattr(main,'generate_with_meaning',ai)
    asyncio.run(process_job({'platform':'instagram','sender_id':'friend','sender_name':'','message_id':'replaced','text':'hi','owner_id':aid,'connection_id':row['id'],'received_at':time.time()}))
    assert len(client.get('/api/messages?platform=instagram&sender_id=friend',headers=a).json())==1
    assert not any(e['category']=='DRY_RUN' for e in client.get('/api/activity',headers=a).json())


@pytest.mark.parametrize('status,body',[(403,{'error':{'message':'test-private-token'}}),(200,{'error':{'message':'test-private-token'}}),(200,['test-private-token'])])
def test_meta_transport_errors_never_expose_secrets(status,body):
    import httpx
    from app import social
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(status,json=body))) as client:
            with pytest.raises(__import__('fastapi').HTTPException) as error:await social.graph(client,'GET','https://graph.facebook.com/test',params={'access_token':'test-private-token'})
            assert error.value.status_code==502 and 'test-private-token' not in error.value.detail
    asyncio.run(run())


@pytest.mark.parametrize('sender,timestamp',[('',None),('friend','nan'),('friend','1e30')])
def test_malformed_tenant_webhooks_do_not_enqueue(client,monkeypatch,sender,timestamp):
    import time
    social=social_config(monkeypatch);a,aid=social_user(client);attach(social,aid,'222333')
    payload={'object':'instagram','entry':[{'id':'222333','messaging':[{'timestamp':time.time()*1000 if timestamp is None else timestamp,'sender':{'id':sender},'message':{'mid':'malformed','text':'hello'}}]}]}
    body=json.dumps(payload).encode();sig='sha256='+hmac.new(settings.instagram_client_secret.encode(),body,hashlib.sha256).hexdigest()
    assert client.post('/webhook/meta',content=body,headers={'x-hub-signature-256':sig}).json()['accepted']==0
    assert store.query('SELECT * FROM webhook_jobs')==[]


@pytest.mark.parametrize('code,status',[(429,'rate_limited'),(503,'unavailable')])
def test_autonomous_provider_failures_update_health_safely(client,monkeypatch,code,status):
    social=social_config(monkeypatch);a,aid=social_user(client);row=attach(social,aid,'999888')
    context=store.owner.set(aid)
    try:update({'enabled':True,'reply_delay_seconds':0,'cooldown_seconds':0})
    finally:store.owner.reset(context)
    class ProviderFailure(Exception):pass
    error=ProviderFailure('test-private-provider-secret');error.code=code
    def fail(*args):raise error
    monkeypatch.setattr(main,'generate_with_meaning',fail)
    with pytest.raises(ProviderFailure):asyncio.run(process_job({'platform':'instagram','sender_id':'friend','sender_name':'','message_id':'provider-failure','text':'hello','owner_id':aid,'connection_id':row['id']}))
    health=client.get('/api/platforms/status',headers=a).json()['provider_health']
    assert health['status']==status and health['request_id']=='provider-failure'
    assert 'test-private-provider-secret' not in json.dumps(health)+client.get('/api/activity',headers=a).text
