"""One-time legacy SQLite import into an EMPTY migrated PostgreSQL destination."""
import argparse, sqlite3
from pathlib import Path
from sqlalchemy import text
from app.store import engine, metadata

def main():
    parser=argparse.ArgumentParser();parser.add_argument('source');args=parser.parse_args()
    source=Path(args.source).resolve()
    if not source.is_file(): raise SystemExit('Source SQLite file does not exist')
    if engine.dialect.name!='postgresql': raise SystemExit('Set DATABASE_URL to the PostgreSQL destination')
    with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as old, engine.begin() as new:
        old.row_factory=sqlite3.Row
        existing={r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ['messages','activity','processed_messages','preferences','webhook_jobs']:
            if new.execute(text(f'SELECT COUNT(*) FROM {name}')).scalar():
                raise SystemExit('Destination is not empty. Import refused to prevent overwritten or duplicated data.')
        for name in ['messages','activity','processed_messages','preferences','webhook_jobs']:
            if name not in existing: continue
            rows=[dict(x) for x in old.execute(f'SELECT * FROM {name}')]
            if rows: new.execute(metadata.tables[name].insert(),rows)
        for name in ['messages','activity','preferences']:
            new.execute(text(f"SELECT setval(pg_get_serial_sequence('{name}','id'),COALESCE(MAX(id),1),MAX(id) IS NOT NULL) FROM {name}"))
    print('Import committed. All available v2 records preserved.')
if __name__=='__main__': main()
