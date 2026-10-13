"""Add tenant-owned social connections without modifying existing records."""
from alembic import op
import sqlalchemy as sa
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('social_connections',sa.Column('id',sa.Text(),primary_key=True),sa.Column('owner_id',sa.Integer(),nullable=False),sa.Column('platform',sa.Text(),nullable=False),sa.Column('account_id',sa.Text(),nullable=False),sa.Column('label',sa.Text(),nullable=False),sa.Column('token_ciphertext',sa.Text(),nullable=False),sa.Column('expires_at',sa.Float(),nullable=False),sa.Column('created_at',sa.Float(),nullable=False),sa.UniqueConstraint('platform','account_id',name='uq_social_account'),sa.UniqueConstraint('owner_id','platform',name='uq_social_owner_platform'))
    op.create_table('social_oauth_states',sa.Column('digest',sa.Text(),primary_key=True),sa.Column('owner_id',sa.Integer(),nullable=False),sa.Column('platform',sa.Text(),nullable=False),sa.Column('expires_at',sa.Float(),nullable=False))
    op.create_table('social_page_candidates',sa.Column('id',sa.Text(),primary_key=True),sa.Column('owner_id',sa.Integer(),nullable=False),sa.Column('account_id',sa.Text(),nullable=False),sa.Column('label',sa.Text(),nullable=False),sa.Column('token_ciphertext',sa.Text(),nullable=False),sa.Column('expires_at',sa.Float(),nullable=False),sa.Column('token_expires_at',sa.Float(),nullable=False))
def downgrade():
    raise RuntimeError('Restore a verified backup to roll back encrypted social connections')
