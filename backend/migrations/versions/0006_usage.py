"""Add manual generation usage ledger; no existing records are rewritten."""
from alembic import op
import sqlalchemy as sa
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('subscriptions',
        sa.Column('owner_id', sa.Integer(), primary_key=True),
        sa.Column('plan', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('paid_until', sa.Float(), nullable=False))
    op.create_table('monthly_usage',
        sa.Column('owner_id', sa.Integer(), primary_key=True),
        sa.Column('month', sa.Text(), primary_key=True),
        sa.Column('generations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('usage_reservations',
        sa.Column('owner_id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.Text(), primary_key=True),
        sa.Column('month', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False))


def downgrade():
    raise RuntimeError('Usage ledger rollback requires a verified backup')
