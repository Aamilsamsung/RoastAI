"""LOCAL isolated browser fixture; never a deployment entry point."""
import os,pathlib,tempfile
fixture=pathlib.Path(tempfile.mkdtemp(prefix='roastai-browser-'))/'fixture.db'
os.environ.update(DATABASE_URL='sqlite:///'+str(fixture),ENVIRONMENT='test',ADMIN_TOKEN='qa-owner-only-local-test-token-32chars',FRONTEND_URL='http://127.0.0.1:8124')
from app import main,store,ai
store.init_db()
def local_fixture(message,cfg,*args):
 if message=='__FAIL_QA__':raise ai.ProviderConfigurationError('qa missing-key fixture')
 return f'{cfg.roast_mode} response for UI workflow testing.','English meaning for UI workflow testing.'
main.generate_with_meaning=local_fixture
@main.app.middleware('http')
async def test_run_header(request,call_next):
 response=await call_next(request);response.headers['X-Browser-Test-Run']=os.environ.get('BROWSER_TEST_RUN_ID','standalone-local-test');return response
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=8123,log_level='error')
