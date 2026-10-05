from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None
def upgrade():
    for table in ('messages','activity'):
        op.add_column(table,sa.Column('owner_id',sa.Integer(),nullable=False,server_default='0'))
        op.create_index('ix_'+table+'_owner',table,['owner_id'])
    op.create_table('users',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('email',sa.Text(),nullable=False,unique=True),sa.Column('password_hash',sa.Text(),nullable=False))
    op.create_table('sessions',sa.Column('digest',sa.Text(),primary_key=True),sa.Column('user_id',sa.Integer(),nullable=False),sa.Column('expires',sa.Float(),nullable=False))
def downgrade():
    raise RuntimeError('Account migration cannot be downgraded without losing user data')
