import asyncio, json, time, hmac
from contextlib import asynccontextmanager
from types import SimpleNamespace
from collections import defaultdict, deque
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from .config import settings
from .models import BotSettings, RoastRequest
from .ai import generate_with_meaning
from .meta import verify_signature, parse_events, whatsapp_send, instagram_send
from . import store
from . import accounts

DEFAULT = {**BotSettings().model_dump(), 'enabled':settings.bot_enabled,'dry_run':settings.dry_run,
    'roast_mode':settings.roast_mode,'intensity':settings.roast_intensity,'profanity_level':settings.profanity_level,
    'custom_instructions':settings.custom_instructions,'reply_delay_seconds':settings.reply_delay_seconds,
    'cooldown_seconds':settings.cooldown_seconds,'max_reply_length':settings.max_reply_length,
    'input_language':settings.input_language,'reply_language':settings.reply_language,'script_mode':settings.script_mode,
    'emergency_stop':False, 'safety_epoch':0}

def current(): return store.load_preferences(DEFAULT)
def update(changes,protect_stop=False):
    return store.update_preferences(DEFAULT,changes,protect_stop)

def allowed(cfg,platform): return cfg['enabled'] and not cfg['emergency_stop'] and cfg[platform+'_enabled']

async def process_job(event):
    platform=event['platform']; sender=event['sender_id']; cfg=current()
    store.add_message(platform,sender,event['sender_name'],event['message_id'],'incoming',event['text'])
    if not allowed(cfg,platform):
        store.log('DELIVERY','Incoming message recorded; bot or platform paused'); return
    # Use persisted outgoing timestamps so restarts do not reset sender cooldowns.
    history=store.recent(platform,sender)
    from datetime import datetime, timezone
    last=next((x for x in reversed(history) if x['direction']=='outgoing'),None)
    if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last['timestamp'])).total_seconds()<cfg['cooldown_seconds']:
        store.log('DELIVERY','Sender cooldown applied'); return
    await asyncio.sleep(cfg['reply_delay_seconds'])
    if not allowed(current(),platform) or current()['safety_epoch']!=cfg['safety_epoch']: return
    reply,meaning=await run_in_threadpool(generate_with_meaning,event['text'],SimpleNamespace(**cfg),event['sender_name'],history,cfg['input_language'],cfg['reply_language'],cfg['script_mode'])
    live=current()
    if not allowed(live,platform) or live['safety_epoch']!=cfg['safety_epoch']:
        store.log('DELIVERY','Reply cancelled by stop or delivery-setting change'); return
    if cfg['dry_run']:
        store.log('DRY_RUN',f'{platform} reply generated without delivery')
    else:
        send=whatsapp_send if platform=='whatsapp' else instagram_send
        await send(sender,reply)
        store.log('DELIVERY',f'{platform} reply accepted by Meta')
    store.add_message(platform,sender,'RoastAI','','outgoing',reply)

async def worker():
    while True:
        rows=store.query("SELECT * FROM webhook_jobs WHERE status='pending' ORDER BY timestamp LIMIT 1")
        if not rows:
            await asyncio.sleep(.5); continue
        job=rows[0]; mid=job['message_id']
        store.execute("UPDATE webhook_jobs SET status='processing' WHERE message_id=:m",m=mid)
        try:
            await process_job(json.loads(job['data']))
            store.execute("UPDATE webhook_jobs SET status='done' WHERE message_id=:m",m=mid)
        except asyncio.CancelledError: raise
        except Exception:
            # Raw upstream exceptions can contain credential-bearing URLs; never persist them.
            store.log('ERROR','Social reply failed; check credentials, permissions and provider availability')
            store.execute("UPDATE webhook_jobs SET status='failed' WHERE message_id=:m",m=mid)

@asynccontextmanager
async def lifespan(app):
    if settings.environment=='production' and (len(settings.admin_token)<32 or not settings.frontend_url.startswith('https://')):
        raise RuntimeError('Production requires ADMIN_TOKEN (32+ characters) and HTTPS FRONTEND_URL')
    if '*' in [x.strip() for x in (settings.cors_origins or settings.frontend_url).split(',')]:
        raise RuntimeError('CORS must list exact origins; wildcard access is disabled')
    store.init_db(); BotSettings.model_validate(current())
    store.execute('INSERT INTO preferences(id,data) VALUES(1,:d) ON CONFLICT(id) DO NOTHING',d=json.dumps(DEFAULT))
    # Never resend an ambiguous in-flight job after restart (Meta lacks send idempotency).
    store.log('SYSTEM','RoastAI started')
    # Session-level lock prevents two queue consumers during Render rolling deploys.
    leader=None
    if store.engine.dialect.name=='postgresql':
        leader=store.engine.connect()
    async def elected_worker():
        while leader is not None and not leader.execute(store.text('SELECT pg_try_advisory_lock(78192031)')).scalar():
            leader.rollback()
            await asyncio.sleep(1)
        store.execute("UPDATE webhook_jobs SET status='uncertain' WHERE status='processing'")
        await worker()
    task=asyncio.create_task(elected_worker())
    app.state.worker_task=task
    try: yield
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        if leader is not None:
            leader.execute(store.text('SELECT pg_advisory_unlock(78192031)'))
            leader.close()

app=FastAPI(title='RoastAI API',version='2.1',lifespan=lifespan,docs_url=None if settings.environment=='production' else '/docs',redoc_url=None,openapi_url=None if settings.environment=='production' else '/openapi.json')
origins=[x.strip().rstrip('/') for x in (settings.cors_origins or settings.frontend_url).split(',') if x.strip()]

limits=defaultdict(deque)

@app.middleware('http')
async def protect(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        token=request.headers.get('authorization','').removeprefix('Bearer ')
        public=request.url.path in ('/api/auth/signup','/api/auth/login')
        admin=not settings.admin_token or hmac.compare_digest(token.encode(),settings.admin_token.encode())
        user=None if admin or public else await run_in_threadpool(accounts.authenticate,token)
        if not public and not admin and user is None:
            return JSONResponse({'detail':'Sign in required'},status_code=401)
        store.owner.set(user or 0)
        if user and (request.url.path.startswith('/api/bot/') or request.url.path=='/api/platforms/status'):
            if request.url.path.startswith('/api/bot/'):
                return JSONResponse({'detail':'Social bot controls are owner-only'},status_code=403)

        key=request.client.host if request.client else 'unknown'; now=time.monotonic()
        bucket=limits[key]
        while bucket and bucket[0]<now-60: bucket.popleft()
        if len(bucket)>=settings.rate_limit_per_minute*6 and request.url.path not in ('/api/bot/stop','/api/bot/emergency-stop'):
            return JSONResponse({'detail':'Too many requests. Try again shortly.'},status_code=429,headers={'Retry-After':'60'})
        bucket.append(now)
        if public:
            auth_bucket=limits['auth:'+key]
            while auth_bucket and auth_bucket[0]<now-60: auth_bucket.popleft()
            if len(auth_bucket)>=10: return JSONResponse({'detail':'Too many sign-in attempts. Try again in a minute.'},status_code=429)
            auth_bucket.append(now)
        if request.url.path in ('/api/roast','/api/preview'):
            bucket=limits['generation:'+str(store.owner.get())]
            while bucket and bucket[0]<now-60: bucket.popleft()
            if len(bucket)>=settings.rate_limit_per_minute:
                return JSONResponse({'detail':'Generation limit reached. Try again shortly.'},status_code=429,headers={'Retry-After':'60'})
            bucket.append(now)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
    return response

@app.post('/api/auth/signup')
def signup(x:accounts.Credentials): return accounts.sign_in(x,True)
@app.post('/api/auth/login')
def login(x:accounts.Credentials): return accounts.sign_in(x)
@app.post('/api/auth/logout')
def logout(request:Request):
    import hashlib
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    store.execute('DELETE FROM sessions WHERE digest=:d',d=hashlib.sha256(token.encode()).hexdigest())
    return {'ok':True}
@app.get('/health')
def health():
    store.query('SELECT 1')
    task=getattr(app.state,'worker_task',None)
    if task is not None and task.done(): raise HTTPException(503,'Webhook worker unavailable')
    return {'status':'ok'}
@app.get('/api/settings')
def get_settings(): return current()
@app.put('/api/settings')
def save_settings(x: BotSettings):
    changes=x.model_dump()
    value=update(changes,protect_stop=True); store.log('SETTINGS','Preferences saved'); return value
@app.post('/api/bot/start')
def start():
    value=update({'enabled':True,'emergency_stop':False}); store.log('BOT','Bot started'); return value
@app.post('/api/bot/stop')
def stop():
    value=update({'enabled':False}); store.log('BOT','Bot paused'); return value
@app.post('/api/bot/emergency-stop')
def emergency():
    value=update({'enabled':False,'emergency_stop':True}); store.log('BOT','Emergency stop activated'); return value
@app.post('/api/roast')
@app.post('/api/preview')
def roast(x: RoastRequest):
    cfg=current()
    if cfg['emergency_stop']: raise HTTPException(409,'Emergency stop is active. Start the bot to reset it.')
    try:
        reply,meaning=generate_with_meaning(x.message,SimpleNamespace(**cfg),x.sender_name,store.recent('local','roast-me'),x.input_language,x.reply_language,x.script_mode)
    except Exception:
        store.log('ERROR','AI generation failed; check provider configuration or retry')
        raise HTTPException(502,'AI provider unavailable. Check the server API key, model, quota, or retry shortly.')
    if current()['safety_epoch']!=cfg['safety_epoch']: raise HTTPException(409,'Generation cancelled because bot settings changed.')
    store.add_message('local','roast-me','You','','incoming',x.message)
    store.add_message('local','roast-me','RoastAI','','outgoing',reply)
    store.log('ROAST',f"Generated {cfg['roast_mode']} comeback")
    return {'reply':reply,'english_meaning':meaning,'mode':cfg['roast_mode'],'intensity':cfg['intensity'],'input_language':x.input_language,'reply_language':x.reply_language,'script_mode':x.script_mode}
@app.get('/api/activity')
def activity(): return store.activity()
@app.get('/api/messages')
def messages(platform:str='local',sender_id:str='roast-me',before_id:int|None=Query(None,ge=1),limit:int=Query(100,ge=1,le=100)):
    if platform not in ('local','whatsapp','instagram') or len(sender_id)>200: raise HTTPException(422,'Invalid conversation')
    return store.conversation_messages(platform,sender_id,limit,before_id)
@app.get('/api/conversations')
def conversations(): return store.conversations()
@app.delete('/api/conversations')
def clear():
    store.clear_history(); store.log('HISTORY','Conversation history cleared'); return {'ok':True}
@app.get('/api/platforms/status')
def platforms():
    return {'gemini':bool(settings.gemini_api_key and settings.gemini_model),'ollama':settings.ai_provider=='ollama' and bool(settings.ollama_base_url),
        'whatsapp':bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),'instagram':bool(settings.instagram_access_token and settings.instagram_account_id),
        'provider':settings.ai_provider,'status_kind':'configuration'}
@app.get('/webhook/meta',response_class=PlainTextResponse)
async def verify(request:Request):
    q=request.query_params
    if settings.meta_verify_token and q.get('hub.mode')=='subscribe' and hmac.compare_digest(q.get('hub.verify_token','').encode(),settings.meta_verify_token.encode()):
        challenge=q.get('hub.challenge','')
        if challenge.isdigit(): return challenge
    raise HTTPException(403,'Webhook verification failed')
@app.post('/webhook/meta')
async def webhook(request:Request):
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>1_000_000: raise HTTPException(413,'Webhook too large')
    if not verify_signature(bytes(body),request.headers.get('x-hub-signature-256')): raise HTTPException(403,'Invalid webhook signature')
    try:
        payload=json.loads(body)
        if not isinstance(payload,dict): raise ValueError()
        events=parse_events(payload)
    except (ValueError,TypeError,AttributeError): raise HTTPException(400,'Malformed webhook')
    accepted=0
    for event in events:
        if any(not isinstance(event[k],str) for k in ('message_id','sender_id','text','sender_name')): continue
        if not event['message_id'] or len(event['message_id'])>512 or not event['sender_id'] or len(event['sender_id'])>200 or not event['text'].strip() or len(event['text'])>5000: continue
        if not store.processed(event['message_id']) and store.enqueue(event): accepted+=1
    return {'accepted':accepted}

app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type','Authorization'])
