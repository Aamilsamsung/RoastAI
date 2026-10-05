from alembic import context
from app.store import engine, metadata

def offline():
    context.configure(url=engine.url.render_as_string(hide_password=False),target_metadata=metadata,literal_binds=True)
    with context.begin_transaction(): context.run_migrations()

def online():
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=metadata,render_as_batch=engine.dialect.name=='sqlite')
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): offline()
else: online()
