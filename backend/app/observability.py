"""Keep access logs useful without logging verification tokens or private queries."""
import logging

class AccessLogPrivacyFilter(logging.Filter):
    def filter(self,record):
        # Uvicorn's access tuple is (client, method, full_path, version, status).
        if isinstance(record.args,tuple) and len(record.args)==5 and isinstance(record.args[2],str):
            values=list(record.args);values[2]=values[2].split('?',1)[0];record.args=tuple(values)
        return True
