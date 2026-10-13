import asyncio, json, time, hmac, hashlib, logging, secrets, math
from contextlib import asynccontextmanager
from types import SimpleNamespace
from collections import defaultdict, deque
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from .config import settings
from .models import BotSettings, RoastRequest, PageSelection, WhatsAppSignup
from .ai import generate_with_meaning, provider_error_detail, provider_trace
from .meta import verify_signature, parse_events, whatsapp_send, instagram_send, facebook_send
from . import store
from . import accounts, snapchat, social
from uuid import UUID
from .observability import AccessLogPrivacyFilter
logging.getLogger('uvicorn.access').addFilter(AccessLogPrivacyFilter())

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
    context=store.owner.set(event.get("owner_id",0))
    try:
        await process_owned_job(event)
    except Exception:
        store.log("ERROR","Social reply failed; check permissions, token expiry and provider status")
        raise
    finally:
        store.owner.reset(context)

def generate_social_reply(event,cfg,history):
    provider_trace.set(None);started=time.perf_counter();model=settings.gemini_model if settings.ai_provider=='gemini' else settings.ollama_model
    try:
        result=generate_with_meaning(event['text'],SimpleNamespace(**cfg),event['sender_name'],history,cfg['input_language'],cfg['reply_language'],cfg['script_mode'])
    except Exception as error:
        code=getattr(error,'code',None)
        status='rate_limited' if code==429 else 'setup_error' if code in (400,401,403,404) else 'unavailable'
        store.record_provider({'status':status,'model':model,'checked_at':time.time(),'request_id':event['message_id'],'http_status':code if isinstance(code,int) else None,'error_type':type(error).__name__})
        store.log('ERROR',provider_error_detail(error)+' · request '+event['message_id'])
        raise
    trace=provider_trace.get() or {}
    store.record_provider({'status':'healthy','model':trace.get('model',model),'checked_at':time.time(),'request_id':event['message_id'],'latency_ms':round((time.perf_counter()-started)*1000)})
    return result

async def process_owned_job(event):
    platform=event['platform']; sender=event['sender_id']; cfg=current()
    connection_id=event.get('connection_id')
    if connection_id and not social.connection(connection_id):return
    if event.get('received_at') and time.time()-event['received_at']>23*3600:
        store.log('DELIVERY','Reply cancelled: incoming messaging window expired');return
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
    bucket=limits['generation:'+str(store.owner.get())];now=time.monotonic()
    while bucket and bucket[0]<now-60:bucket.popleft()
    if len(bucket)>=settings.rate_limit_per_minute:
        store.log('DELIVERY','Workspace generation limit reached; incoming message retained');return
    bucket.append(now)
    reply,meaning=await run_in_threadpool(generate_social_reply,event,cfg,history)
    live=current()
    if connection_id and not social.connection(connection_id):
        store.log('DELIVERY','Reply cancelled: connection was replaced or removed');return
    if not allowed(live,platform) or live['safety_epoch']!=cfg['safety_epoch']:
        store.log('DELIVERY','Reply cancelled by stop or delivery-setting change'); return
    if cfg['dry_run'] or not settings.social_delivery_approved:
        store.log('DRY_RUN',f'{platform} reply generated without delivery')
    else:
        if connection_id:
            row=social.connection(connection_id)
            if not row:return
            await social.send(row,event.get('recipient_id',sender),reply)
        else:
            send={'whatsapp':whatsapp_send,'instagram':instagram_send,'facebook':facebook_send}[platform]
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
    request.state.request_id=secrets.token_hex(16)
    if request.url.path.startswith('/api/'):
        key=request.client.host if request.client else 'unknown'; now=time.monotonic()
        if len(limits)>10000:
            for name in list(limits):
                if not limits[name] or limits[name][-1]<now-60: limits.pop(name,None)
        bucket=limits[key]
        while bucket and bucket[0]<now-60: bucket.popleft()
        if len(bucket)>=settings.rate_limit_per_minute*6 and request.url.path not in ('/api/bot/stop','/api/bot/emergency-stop'):
            return JSONResponse({'detail':'Too many requests. Try again shortly.','request_id':request.state.request_id},status_code=429,headers={'Retry-After':'60','X-Request-ID':request.state.request_id})
        bucket.append(now)
        token=request.headers.get('authorization','').removeprefix('Bearer ')
        public=request.url.path in ('/api/auth/signup','/api/auth/login','/api/auth/config','/api/auth/google','/api/auth/google/challenge')
        admin=not settings.admin_token or hmac.compare_digest(token.encode(),settings.admin_token.encode())
        user=None if admin or public else await run_in_threadpool(accounts.authenticate,token)
        if not public and not admin and user is None:
            return JSONResponse({'detail':'Sign in required','request_id':request.state.request_id},status_code=401)
        store.owner.set(user or 0)
        if user and request.url.path.startswith('/api/snapchat/'):
            return JSONResponse({'detail':'Snapchat collaboration controls are owner-only'},status_code=403)

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
    response.headers['X-Request-ID']=getattr(request.state,'request_id',secrets.token_hex(8))
    response.headers['X-Content-Type-Options']='nosniff'
    if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
    return response

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def invalid_request(request:Request,error:RequestValidationError):
    return JSONResponse({'detail':'Invalid request fields','errors':[{'field':'.'.join(map(str,x['loc'])),'message':x['msg']} for x in error.errors()],'request_id':getattr(request.state,'request_id',None)},status_code=422)

@app.get('/api/auth/config')
def auth_config(): return {'google_client_id':settings.google_client_id}
@app.post('/api/auth/google/challenge')
def google_challenge(): return accounts.google_challenge()
@app.post('/api/auth/google')
def google_login(x:accounts.GoogleCredential): return accounts.google_sign_in(x)
@app.post('/api/auth/google/link')
def google_link(x:accounts.GoogleCredential): return accounts.google_sign_in(x,store.owner.get())
@app.post('/api/auth/signup')
def signup(x:accounts.Credentials): return accounts.sign_in(x,True)
@app.post('/api/auth/login')
def login(x:accounts.Credentials): return accounts.sign_in(x)
@app.post('/api/auth/logout')
def logout(request:Request):
    import hashlib
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    with store.engine.begin() as c:
        c.execute(store.text('DELETE FROM sessions WHERE digest=:d'),{'d':hashlib.sha256(token.encode()).hexdigest()})
        c.execute(store.text('DELETE FROM social_oauth_states WHERE owner_id=:o'),{'o':store.owner.get()})
        c.execute(store.text('DELETE FROM social_page_candidates WHERE owner_id=:o'),{'o':store.owner.get()})
    return {'ok':True}
@app.get('/')
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
def roast(x: RoastRequest,request:Request):
    started=time.perf_counter();cfg=current();rid=x.request_id or str(__import__('uuid').uuid4())
    request.state.request_id=rid
    if cfg['emergency_stop']: raise HTTPException(409,'Emergency stop is active. Start the bot to reset it.')
    fingerprint=hashlib.sha256(json.dumps({'input':x.model_dump(exclude={'request_id'}),'preferences':{k:cfg[k] for k in BotSettings.model_fields if k not in ('enabled','dry_run','whatsapp_enabled','instagram_enabled','facebook_enabled')}},sort_keys=True).encode()).hexdigest()
    existing=store.claim_request(rid,fingerprint)
    if existing:
        if existing['fingerprint']!=fingerprint: raise HTTPException(409,'Request ID was already used with different input or settings')
        if existing['status']=='processing': return JSONResponse({'detail':'This request is already processing. Do not resubmit with a new ID.','request_id':rid},status_code=409)
        response=json.loads(existing['response'])
        return JSONResponse(response,status_code=200 if existing['status']=='done' else response.get('status_code',502))
    provider_trace.set(None)
    try:
        reply,meaning=generate_with_meaning(x.message,SimpleNamespace(**cfg),x.sender_name,store.recent('local',x.conversation_id),x.input_language,x.reply_language,x.script_mode)
    except Exception as error:
        trace=provider_trace.get() or {};code=getattr(error,'code',None);detail=provider_error_detail(error)
        failure_status='rate_limited' if code==429 else 'setup_error' if code in (400,401,403,404) else 'unavailable'
        evidence={'status':failure_status,'model':settings.gemini_model,'checked_at':time.time(),'request_id':rid,'http_status':code if isinstance(code,int) else None,'error_type':type(error).__name__}
        store.record_provider(evidence)
        payload={'detail':detail,'request_id':rid,'provider_status':evidence['http_status'],'attempts':trace.get('attempts',0),'status_code':502}
        store.finish_request(rid,payload);store.log('ERROR',detail+' · request '+rid)
        logging.getLogger('uvicorn.error').warning('AI failure request_id=%s provider=%s model=%s http_status=%s type=%s attempts=%s',rid,settings.ai_provider,settings.gemini_model,evidence['http_status'],type(error).__name__,trace.get('attempts',0))
        return JSONResponse(payload,status_code=502)
    trace=provider_trace.get() or {};ai_ms=round((time.perf_counter()-started)*1000)
    store.record_provider({'status':'healthy','model':trace.get('model',settings.gemini_model),'checked_at':time.time(),'request_id':rid,'latency_ms':ai_ms})
    if current()['safety_epoch']!=cfg['safety_epoch']:
        payload={'detail':'Generation cancelled because bot settings changed.','request_id':rid,'status_code':409}
        store.finish_request(rid,payload);return JSONResponse(payload,status_code=409)
    response={'request_id':rid,'conversation_id':x.conversation_id,'timing':{'ai_ms':ai_ms},'usage':trace,'reply':reply,'english_meaning':meaning,'mode':cfg['roast_mode'],'intensity':cfg['intensity'],'input_language':x.input_language,'reply_language':x.reply_language,'script_mode':x.script_mode}
    store.finish_request(rid,response,x.message,reply,x.conversation_id,started_at=started)
    logging.getLogger('uvicorn.error').info('Roast request_id=%s model=%s ai_ms=%d total_ms=%d input_tokens=%s output_tokens=%s thinking_tokens=%s attempts=%s',rid,trace.get('model'),ai_ms,response['timing']['total_ms'],trace.get('input_tokens'),trace.get('output_tokens'),trace.get('thinking_tokens'),trace.get('attempts'))
    return response
@app.get('/api/activity')
def activity(): return store.activity()
@app.get('/api/messages')
def messages(platform:str='local',sender_id:str='roast-me',before_id:int|None=Query(None,ge=1),limit:int=Query(100,ge=1,le=100)):
    if platform not in ('local','whatsapp','instagram','facebook','snapchat') or len(sender_id)>200: raise HTTPException(422,'Invalid conversation')
    return store.conversation_messages(platform,sender_id,limit,before_id)
@app.get('/api/conversations')
def conversations(): return store.conversations()
@app.delete('/api/conversations')
def clear():
    store.clear_history(); store.log('HISTORY','Conversation history cleared'); return {'ok':True}
@app.get('/api/platforms/status')
def platforms():
    value= {'gemini':bool(settings.gemini_api_key and settings.gemini_model),'ollama':settings.ai_provider=='ollama' and bool(settings.ollama_base_url),
        'whatsapp':bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),'instagram':bool(settings.instagram_access_token and settings.instagram_account_id),
        'facebook':bool(settings.facebook_page_access_token and settings.facebook_page_id),'snapchat':bool(settings.snapchat_access_token and settings.snapchat_profile_id),'snapchat_capability':'creator_collaboration_approval_required',
        'environment':settings.environment,'database_backend':store.engine.dialect.name,'provider':settings.ai_provider,'provider_health':store.provider_status(),'delivery_approved':settings.social_delivery_approved,'status_kind':'configuration_only_not_connection_verified'}
    if store.owner.get()==0:
        value['legacy_owner_connections']={key:value[key] for key in ('whatsapp','instagram','facebook')}
    if store.owner.get()!=0:
        for key in ('whatsapp','instagram','facebook','snapchat'):value[key]=False
    connections=social.listing()
    for row in connections['connections']:
        if row['status']=='authorization_verified':value[row['platform']]=True
    value['social_connections']=connections
    return value
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
    signature=request.headers.get('x-hub-signature-256')
    meta_valid=verify_signature(bytes(body),signature)
    instagram_valid=bool(settings.instagram_client_secret) and verify_signature(bytes(body),signature,settings.instagram_client_secret)
    if not meta_valid and not instagram_valid:raise HTTPException(403,'Invalid webhook signature')
    try:
        payload=json.loads(body)
        if not isinstance(payload,dict): raise ValueError()
        if payload.get('object')!='instagram' and not meta_valid:raise HTTPException(403,'Invalid platform webhook signature')
        events=parse_events(payload)
        # One account belongs to one workspace. Legacy owner integration remains intact.
        rows=store.query('SELECT * FROM social_connections WHERE expires_at>:t',t=time.time())
        legacy={'instagram':settings.instagram_account_id,'whatsapp':settings.whatsapp_phone_number_id,'facebook':settings.facebook_page_id}
        claimed={(r['platform'],r['account_id']) for r in rows}
        events=[e for e in events if (e['platform'],legacy[e['platform']]) not in claimed]
        for row in rows:
            cfg=SimpleNamespace(whatsapp_phone_number_id=row['account_id'] if row['platform']=='whatsapp' else '',instagram_account_id=row['account_id'] if row['platform']=='instagram' else '',facebook_page_id=row['account_id'] if row['platform']=='facebook' else '')
            for event in parse_events(payload,cfg):
                timestamp=event.pop('event_timestamp',None)
                try:timestamp=float(timestamp)
                except (TypeError,ValueError):continue
                received=timestamp if event['platform']=='whatsapp' else timestamp/1000
                if not math.isfinite(received) or received<=0 or received>time.time()+300:continue
                if not isinstance(event['sender_id'],str) or not event['sender_id'] or len(event['sender_id'])>128:continue
                event.update(owner_id=row['owner_id'],connection_id=row['id'],received_at=min(received,time.time()))
                if event['message_id']:event['message_id']=hashlib.sha256((row['platform']+':'+row['account_id']+':'+event['message_id']).encode()).hexdigest()
                if isinstance(event['sender_id'],str):
                    event['recipient_id']=event['sender_id']
                    event['sender_id']=row['account_id']+':'+event['sender_id']
                events.append(event)
    except (ValueError,TypeError,AttributeError): raise HTTPException(400,'Malformed webhook')
    accepted=0
    for event in events:
        event.setdefault('received_at',time.time())
        if any(not isinstance(event[k],str) for k in ('message_id','sender_id','text','sender_name')): continue
        if not event['message_id'] or len(event['message_id'])>512 or not event['sender_id'] or len(event['sender_id'])>200 or not event['text'].strip() or len(event['text'])>5000: continue
        if not store.processed(event['message_id']) and store.enqueue(event): accepted+=1
    return {'accepted':accepted}

app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type','Authorization'],expose_headers=['X-Request-ID','Retry-After'])

@app.get('/api/snapchat/messages')
async def snapchat_messages(creator_profile_id:UUID):
    return await snapchat.read(creator_profile_id)

@app.post('/api/snapchat/messages')
async def snapchat_message(x:snapchat.Collaboration):
    cfg=current();sender=str(x.creator_profile_id)
    if cfg['emergency_stop'] or not cfg['enabled']: raise HTTPException(409,'Start the bot and clear emergency stop before social delivery')
    from datetime import datetime, timezone
    history=store.recent('snapchat',sender)
    if history and (datetime.now(timezone.utc)-datetime.fromisoformat(history[-1]['timestamp'])).total_seconds()<cfg['cooldown_seconds']: raise HTTPException(429,'Conversation cooldown active')
    if cfg['dry_run'] or not settings.social_delivery_approved:
        store.log('DRY_RUN','Snapchat collaboration message previewed without sending')
        return {'accepted':False,'dry_run':True}
    conv=await snapchat.conversation(x.creator_profile_id)
    live=current()
    if not live['enabled'] or live['emergency_stop'] or live['dry_run'] or live['safety_epoch']!=cfg['safety_epoch']: raise HTTPException(409,'Delivery cancelled by changed safety settings')
    try: result=await snapchat.send(conv,x.message)
    except HTTPException:
        store.log('ERROR','Snapchat collaboration send failed or unconfirmed; review conversation before retrying')
        raise
    store.add_message('snapchat',sender,'Creator','','outgoing',x.message)
    store.log('DELIVERY','Snapchat accepted collaboration message')
    return result


@app.get('/api/social/connections')
def social_connections():return social.listing()
@app.post('/api/social/instagram/connect')
def instagram_connect():return social.begin()
@app.delete('/api/social/connections/{platform}')
def social_disconnect(platform:str):
    if platform not in ('instagram','facebook','whatsapp'):raise HTTPException(422,'Unsupported connection platform')
    update({'enabled':False})
    return social.disconnect(platform)
@app.get('/oauth/instagram/callback')
async def instagram_callback(state:str='',code:str='',error:str=''):
    account=social.consume(state)
    context=store.owner.set(account)
    try:
        if error:raise HTTPException(400,'Instagram permission was declined')
        await social.complete(code)
        result='connected'
    except HTTPException:
        store.log('CONNECTION','Instagram connection failed; check app permissions, consent and eligibility')
        result='failed'
    finally:store.owner.reset(context)
    return RedirectResponse(settings.frontend_url.rstrip('/')+'/?social='+result,status_code=303,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

@app.post('/api/social/facebook/connect')
def facebook_connect():return social.facebook_begin()
@app.get('/oauth/facebook/callback')
async def facebook_callback(state:str='',code:str='',error:str=''):
    account=social.consume(state,'facebook');context=store.owner.set(account)
    try:
        if error or not code or len(code)>4096:raise HTTPException(400,'Facebook authorization was declined or invalid')
        await social.facebook_complete(code)
        result='select_page'
    except HTTPException:
        store.log('CONNECTION','Facebook connection failed; check Page ownership, permissions and app configuration');result='failed'
    finally:store.owner.reset(context)
    return RedirectResponse(settings.frontend_url.rstrip('/')+'/?social='+result,status_code=303,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
@app.post('/api/social/facebook/select')
async def facebook_select(x:PageSelection):return await social.facebook_select(x.candidate_id)
@app.post('/api/social/whatsapp/connect')
def whatsapp_connect():return social.whatsapp_begin()
@app.post('/api/social/whatsapp/complete')
async def whatsapp_complete(x:WhatsAppSignup):return await social.whatsapp_complete(x)
