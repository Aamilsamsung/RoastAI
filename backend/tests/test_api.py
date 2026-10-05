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
        for table in ['messages','activity','preferences','webhook_jobs','processed_messages']:
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
    payload={'object':'whatsapp_business_account','entry':[{'changes':[{'value':{'messages':[{'type':'text','from':'123','id':'mid1','text':{'body':'hi'}}]}}]}]}
    body=json.dumps(payload).encode();signature='sha256='+hmac.new(settings.meta_app_secret.encode(),body,hashlib.sha256).hexdigest()
    headers={'x-hub-signature-256':signature}
    assert client.post('/webhook/meta',content=body,headers=headers).json()['accepted']==1
    assert client.post('/webhook/meta',content=body,headers=headers).json()['accepted']==0
    assert len(store.query('SELECT * FROM webhook_jobs'))==1

@pytest.mark.parametrize('platform',['whatsapp','instagram'])
def test_dry_run_and_real_send(client,monkeypatch,platform):
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
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0002'

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
    assert client.post('/api/bot/start',headers=a).status_code==403
    client.delete('/api/conversations',headers=b)
    assert len(client.get('/api/messages',headers=a).json())==2
    assert client.post('/api/auth/logout',headers=a).status_code==200
    assert client.get('/api/messages',headers=a).status_code==401
