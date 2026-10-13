"""Real PostgreSQL integration, enabled only with an explicit disposable test URL."""
import os, subprocess, sys, uuid
from pathlib import Path
import pytest

@pytest.mark.skipif(not os.environ.get('TEST_POSTGRES_URL'),reason='TEST_POSTGRES_URL is not set; real PostgreSQL integration runs in CI')
def test_postgres_migration_import_persistence_locks_and_queue(tmp_path):
    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url
    base=os.environ['TEST_POSTGRES_URL']
    schema='roastai_test_'+uuid.uuid4().hex
    url=make_url(base).update_query_dict({'options':'-csearch_path='+schema})
    test_url=url.render_as_string(hide_password=False)
    backend=Path(__file__).resolve().parents[1]
    # All application tables live in a new isolated schema, never existing tables.
    with psycopg.connect(base,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            code=r'''
import os,sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app import store
from app.main import app,DEFAULT,current,update
from fastapi.testclient import TestClient
from scripts import import_sqlite
import sys
source=Path(os.environ['LEGACY_TEST_PATH'])
with sqlite3.connect(source) as old:
    old.executescript("""
    CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,platform TEXT,sender_id TEXT,sender_name TEXT,message_id TEXT,direction TEXT,text TEXT,timestamp TEXT);
    CREATE TABLE activity(id INTEGER PRIMARY KEY AUTOINCREMENT,category TEXT,message TEXT,timestamp TEXT);
    CREATE TABLE processed_messages(message_id TEXT PRIMARY KEY,timestamp TEXT);
    INSERT INTO messages VALUES(41,'local','old','Owner','','incoming','Imported message','2026-01-01T00:00:00+00:00');
    INSERT INTO activity VALUES(31,'OLD','Imported activity','2026-01-01T00:00:00+00:00');
    INSERT INTO processed_messages VALUES('old-id','2026-01-01T00:00:00+00:00');
    """)
store.init_db()
sys.argv=['import_sqlite',str(source)]
import_sqlite.main()
assert store.recent('local','old')[0]['id']==41
assert store.activity()[0]['id']==31
assert store.processed('old-id')
store.add_message('local','old','Owner','','outgoing','New reply')
assert store.recent('local','old')[-1]['id']>41
store.log('TEST','Sequence repaired')
assert store.activity()[0]['id']>31
store.save_preferences(DEFAULT)
update({'intensity':3,'custom_instructions':'Persistent voice'})
store.init_db()
assert current()['intensity']==3
before=current()['safety_epoch']
with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(lambda _:update({'intensity':3}),range(16)))
assert current()['safety_epoch']==before+16
job={'platform':'whatsapp','sender_id':'sample','sender_name':'','message_id':'pg-job','text':'hello'}
assert store.enqueue(job)
assert not store.enqueue(job)
store.init_db()
assert len(store.query('SELECT * FROM webhook_jobs'))==1
# Interrupted deliveries are deliberately retained as uncertain at worker startup.
store.execute("UPDATE webhook_jobs SET status='processing'")
with TestClient(app) as client:
    import time
    for _ in range(40):
        if store.query('SELECT status FROM webhook_jobs')[0]['status']=='uncertain': break
        time.sleep(.01)
    assert store.query('SELECT status FROM webhook_jobs')[0]['status']=='uncertain'
    assert client.get('/health').status_code==200
    assert client.get('/api/settings',headers={'Authorization':'Bearer '+os.environ['ADMIN_TOKEN']}).json()['custom_instructions']=='Persistent voice'
# Additive reliability migration and atomic scoped replay survive PostgreSQL restart.
assert store.query('SELECT version_num FROM alembic_version')[0]['version_num']=='0005'
assert store.claim_request('pg-request','fingerprint') is None
assert store.claim_request('pg-request','fingerprint')['status']=='processing'
store.finish_request('pg-request',{'reply':'safe'},'incoming safe','safe','pg-thread')
assert store.claim_request('pg-request','fingerprint')['status']=='done'
assert len(store.conversation_messages('local','pg-thread'))==2
store.owner.set(7)
assert store.conversation_messages('local','pg-thread')==[]
assert store.claim_request('pg-request','fingerprint') is None
store.owner.set(0)
store.init_db()
assert store.claim_request('pg-request','fingerprint')['status']=='done'
import hashlib,json
from app import social
from app.config import settings
import time
settings.social_token_encryption_key='postgres-test-encryption-key-32-characters'
store.owner.set(7)
social.persist('7654321','PG test creator','test-provider-token',time.time()+3600)
assert len(social.listing()['connections'])==1
assert 'token' not in json.dumps(social.listing()['connections'])
store.owner.set(8)
assert social.listing()['connections']==[]
try:
    social.persist('7654321','Other workspace','test-provider-token',time.time()+3600)
    raise AssertionError('Another owner claimed the same account')
except __import__('fastapi').HTTPException as error:
    assert error.status_code==409
store.owner.set(7)
store.init_db()
assert len(social.listing()['connections'])==1
store.execute('INSERT INTO social_oauth_states VALUES(:d,:o,:p,:t)',d=hashlib.sha256(b'pg-state').hexdigest(),o=7,p='instagram',t=time.time()+300)
assert social.consume('pg-state')==7
store.owner.set(0)
print('PostgreSQL migration, import sequences, persistence, concurrent locks, deduplication and restart checks passed')
'''
            env={**os.environ,'DATABASE_URL':test_url,'ENVIRONMENT':'test','ADMIN_TOKEN':'test-postgres-workspace-token-32-characters',
                'GEMINI_API_KEY':'','BOT_ENABLED':'false','LEGACY_TEST_PATH':str(tmp_path/'legacy.db')}
            result=subprocess.run([sys.executable,'-c',code],cwd=backend,env=env,text=True,capture_output=True,timeout=60)
            assert result.returncode==0,'PostgreSQL integration failed:\n'+result.stdout+'\n'+result.stderr
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
