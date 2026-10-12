"""LOCAL browser test fixture only; never deployed as the application entry point."""
import os,pathlib,json
os.environ.update(DATABASE_URL='sqlite:////workspace/scratch/961ec7ba67e2/RoastAI/backend/tests/browser-fixture.db',ENVIRONMENT='test',ADMIN_TOKEN='qa-owner-only-local-test-token-32chars',FRONTEND_URL='http://127.0.0.1:8124')
from app import main,store,ai
store.init_db()
def local_fixture(message,cfg,*args):
 if message=='__FAIL_QA__':raise ai.ProviderConfigurationError('qa missing-key fixture')
 return f'{cfg.roast_mode} response for UI workflow testing.','English meaning for UI workflow testing.'
main.generate_with_meaning=local_fixture
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=8123,log_level='error')
