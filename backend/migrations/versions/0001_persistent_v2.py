"""Adopt v2 tables without dropping data; add preferences and durable webhook jobs."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    metadata=sa.MetaData()
    messages=sa.Table('messages',metadata,sa.Column('id',sa.Integer,primary_key=True),*[sa.Column(k,sa.Text) for k in ['platform','sender_id','sender_name','message_id','direction','text','timestamp']])
    sa.Table('activity',metadata,sa.Column('id',sa.Integer,primary_key=True),*[sa.Column(k,sa.Text) for k in ['category','message','timestamp']])
    sa.Table('processed_messages',metadata,sa.Column('message_id',sa.Text,primary_key=True),sa.Column('timestamp',sa.Text))
    sa.Table('preferences',metadata,sa.Column('id',sa.Integer,primary_key=True),sa.Column('data',sa.Text,nullable=False))
    sa.Table('webhook_jobs',metadata,sa.Column('message_id',sa.Text,primary_key=True),sa.Column('data',sa.Text,nullable=False),sa.Column('status',sa.Text,nullable=False),sa.Column('timestamp',sa.Text))
    metadata.create_all(op.get_bind())
    if 'ix_messages_thread' not in {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('messages')}:
        op.create_index('ix_messages_thread','messages',['platform','sender_id','id'])

def downgrade():
    raise RuntimeError('Destructive rollback disabled. Restore a database backup instead.')
