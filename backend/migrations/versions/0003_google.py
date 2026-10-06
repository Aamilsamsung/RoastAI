from alembic import op
import sqlalchemy as sa
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('users',sa.Column('google_subject',sa.Text(),nullable=True))
    op.create_index('ix_users_google_subject','users',['google_subject'],unique=True)
    op.create_table('login_challenges',sa.Column('digest',sa.Text(),primary_key=True),sa.Column('expires',sa.Float(),nullable=False))
def downgrade():
    op.drop_table('login_challenges')
    op.drop_index('ix_users_google_subject',table_name='users')
    op.drop_column('users','google_subject')
