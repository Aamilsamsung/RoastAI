"""Persistent SQLAlchemy storage. Existing v2 SQLite tables are retained intact."""
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Text, Index, text
from sqlalchemy.exc import IntegrityError
from .config import settings

url = settings.database_url
if url.startswith(('postgres://', 'postgresql://')):
    url = 'postgresql+psycopg://' + url.split('://', 1)[1]
if settings.environment == 'production' and url.startswith('sqlite'):
    raise RuntimeError('Production requires persistent PostgreSQL DATABASE_URL')
engine = create_engine(url, pool_pre_ping=True, **({'connect_args': {'check_same_thread': False, 'timeout': 30}} if url.startswith('sqlite') else {}))
metadata = MetaData()
messages = Table('messages', metadata, Column('id', Integer, primary_key=True), *[Column(k, Text) for k in ['platform','sender_id','sender_name','message_id','direction','text','timestamp']])
logs = Table('activity', metadata, Column('id', Integer, primary_key=True), *[Column(k, Text) for k in ['category','message','timestamp']])
Table('processed_messages', metadata, Column('message_id', Text, primary_key=True), Column('timestamp', Text))
Table('preferences', metadata, Column('id', Integer, primary_key=True), Column('data', Text, nullable=False))
Table('webhook_jobs', metadata, Column('message_id', Text, primary_key=True), Column('data', Text, nullable=False), Column('status', Text, nullable=False), Column('timestamp', Text))
Index('ix_messages_thread', messages.c.platform, messages.c.sender_id, messages.c.id)

def now(): return datetime.now(timezone.utc).isoformat()
def init_db():
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    command.upgrade(Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini')), 'head')
def query(sql, **params):
    with engine.begin() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings()]
def execute(sql, **params):
    with engine.begin() as c: c.execute(text(sql), params)
def add_message(platform, sender_id, sender_name, message_id, direction, text):
    with engine.begin() as c:
        c.execute(messages.insert().values(platform=platform,sender_id=sender_id,sender_name=sender_name,message_id=message_id,direction=direction,text=text,timestamp=now()))
def recent(platform, sender_id, limit=12):
    return list(reversed(query('SELECT * FROM messages WHERE platform=:p AND sender_id=:s ORDER BY id DESC LIMIT :n',p=platform,s=sender_id,n=limit)))
def conversation_messages(platform, sender_id, limit=100, before_id=None):
    clause=' AND id<:before' if before_id is not None else ''
    rows=query('SELECT * FROM messages WHERE platform=:p AND sender_id=:s'+clause+' ORDER BY id DESC LIMIT :n',p=platform,s=sender_id,n=limit,before=before_id)
    return list(reversed(rows))
def conversations(limit=50):
    rows=query('SELECT platform,sender_id,MAX(timestamp) AS last_time,COUNT(*) AS message_count FROM messages GROUP BY platform,sender_id ORDER BY last_time DESC LIMIT :n',n=limit)
    for r in rows:
        last=recent(r['platform'],r['sender_id'],1)[0]
        r.update(sender_name=last['sender_name'],last_message=last['text'])
    return rows
def processed(mid): return bool(query('SELECT 1 FROM processed_messages WHERE message_id=:m',m=mid))
def mark_processed(mid):
    execute('INSERT INTO processed_messages VALUES(:m,:t) ON CONFLICT(message_id) DO NOTHING',m=mid,t=now())
def log(category,message):
    with engine.begin() as c: c.execute(logs.insert().values(category=category,message=message,timestamp=now()))
def activity(limit=80): return query('SELECT * FROM activity ORDER BY id DESC LIMIT :n',n=limit)
def clear_history():
    execute('DELETE FROM messages')
def load_preferences(default):
    rows=query('SELECT data FROM preferences WHERE id=1')
    return {**default,**json.loads(rows[0]['data'])} if rows else default.copy()
def save_preferences(data):
    execute('INSERT INTO preferences(id,data) VALUES(1,:d) ON CONFLICT(id) DO UPDATE SET data=excluded.data',d=json.dumps(data))
def enqueue(event):
    try:
        execute("INSERT INTO webhook_jobs VALUES(:m,:d,'pending',:t)",m=event['message_id'],d=json.dumps(event),t=now())
        return True
    except IntegrityError: return False


def update_preferences(default, changes, protect_stop=False):
    # Serialize read/modify/write across threads and PostgreSQL connections.
    with engine.connect() as c:
        if engine.dialect.name == 'sqlite': c.exec_driver_sql('BEGIN IMMEDIATE')
        else: c.begin()
        try:
            suffix=' FOR UPDATE' if engine.dialect.name=='postgresql' else ''
            row=c.execute(text('SELECT data FROM preferences WHERE id=1'+suffix)).scalar()
            value={**default,**json.loads(row)} if row else default.copy()
            changes=dict(changes)
            if protect_stop:
                changes.pop('enabled',None)
            value.update(changes)
            value['safety_epoch']=value.get('safety_epoch',0)+1
            c.execute(text('INSERT INTO preferences(id,data) VALUES(1,:d) ON CONFLICT(id) DO UPDATE SET data=excluded.data'),{'d':json.dumps(value)})
            c.commit()
            return value
        except BaseException:
            c.rollback(); raise
