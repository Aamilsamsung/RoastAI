from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('generation_requests',sa.Column('owner_id',sa.Integer(),primary_key=True),sa.Column('request_id',sa.Text(),primary_key=True),sa.Column('fingerprint',sa.Text(),nullable=False),sa.Column('status',sa.Text(),nullable=False),sa.Column('response',sa.Text()),sa.Column('created_at',sa.Float(),nullable=False))
    op.create_table('provider_state',sa.Column('provider',sa.Text(),primary_key=True),sa.Column('data',sa.Text(),nullable=False))
def downgrade():
    raise RuntimeError('Restore a verified backup to roll back durable request records')
