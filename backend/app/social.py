"""User-owned official Meta connections. Tokens never leave the server."""
import base64,hashlib,json,secrets,time,uuid
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet,InvalidToken
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from . import store
from .config import settings

def cipher():
    if len(settings.social_token_encryption_key)<32:raise HTTPException(503,'Social connection encryption is not configured')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.social_token_encryption_key.encode()).digest()))
def configured():
    return bool(len(settings.social_token_encryption_key)>=32 and settings.instagram_client_id and settings.instagram_client_secret and settings.backend_url.startswith('https://') and settings.meta_verify_token)
def redirect_uri():return settings.backend_url.rstrip('/')+'/oauth/instagram/callback'
def listing():
    rows=store.query('SELECT id,platform,account_id,label,expires_at,created_at FROM social_connections WHERE owner_id=:o',o=store.owner.get())
    for r in rows:r['status']='authorization_verified' if r['expires_at']>time.time() else 'reauthorization_required'
    return {'connections':rows,'instagram_oauth_configured':configured(),'delivery_approved':settings.social_delivery_approved,'webhook_configured':bool(settings.instagram_client_secret and settings.meta_verify_token),'supported_account_type':'Instagram Business or Creator','whatsapp_embedded_signup_configured':meta_configured() and bool(settings.whatsapp_signup_config_id),'facebook_oauth_configured':meta_configured(),'facebook_candidates':store.query('SELECT id,account_id,label FROM social_page_candidates WHERE owner_id=:o AND expires_at>:t',o=store.owner.get(),t=time.time())}
def begin():
    if not configured():raise HTTPException(503,'Instagram connection needs the app owner to configure Instagram OAuth and token encryption')
    # State binds an authenticated account to exactly one callback; credentials are never placed in browser URLs.
    state=secrets.token_urlsafe(32)
    with store.engine.begin() as c:
        c.execute(store.text('DELETE FROM social_oauth_states WHERE expires_at<:t'),{'t':time.time()})
        c.execute(store.text('INSERT INTO social_oauth_states VALUES(:d,:o,:p,:t)'),{'d':hashlib.sha256(state.encode()).hexdigest(),'o':store.owner.get(),'p':'instagram','t':time.time()+600})
    return {'url':'https://www.instagram.com/oauth/authorize?'+urlencode({'client_id':settings.instagram_client_id,'redirect_uri':redirect_uri(),'response_type':'code','scope':'instagram_business_basic,instagram_business_manage_messages','state':state,'enable_fb_login':'0','force_authentication':'1'})}
def consume(state,platform='instagram',expected_owner=None):
    if platform not in ('instagram','facebook','whatsapp'):raise HTTPException(422,'Unsupported OAuth platform')
    if not state or len(state)>200:raise HTTPException(400,'Instagram connection challenge is invalid')
    owner_clause=' AND owner_id=:o' if expected_owner is not None else ''
    with store.engine.begin() as c:
        row=c.execute(store.text('DELETE FROM social_oauth_states WHERE digest=:d AND platform=:p AND expires_at>:t'+owner_clause+' RETURNING owner_id'),{'d':hashlib.sha256(state.encode()).hexdigest(),'p':platform,'t':time.time(),'o':expected_owner}).first()
    if row is None:raise HTTPException(400,'Instagram connection challenge expired or already used')
    return row[0]
async def graph(client,method,url,**kwargs):
    try:
        r=await client.request(method,url,**kwargs)
        if not r.is_success:raise HTTPException(502,'Meta rejected the connection request. Check app permissions and account eligibility.')
        data=r.json()
        if not isinstance(data,dict):raise ValueError()
        if data.get('error'):raise HTTPException(502,'Meta rejected the connection request. Check app permissions and account eligibility.')
        return data
    except HTTPException:raise
    except (httpx.HTTPError,ValueError):raise HTTPException(502,'Meta connection is temporarily unavailable. Please reconnect.')
async def complete(code):
    if not configured():raise HTTPException(503,'Instagram OAuth is not configured')
    if not code or len(code)>4096:raise HTTPException(400,'Instagram authorization code is missing')
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        short=await graph(client,'POST','https://api.instagram.com/oauth/access_token',data={'client_id':settings.instagram_client_id,'client_secret':settings.instagram_client_secret,'grant_type':'authorization_code','redirect_uri':redirect_uri(),'code':code})
        # Some token responses use a data array; never trust caller-supplied account IDs.
        if isinstance(short.get('data'),list) and short['data']:short=short['data'][0]
        if not isinstance(short,dict):raise HTTPException(502,'Instagram returned an invalid token response')
        token=short.get('access_token');account_id=str(short.get('user_id',''))
        granted=short.get('permissions',[])
        if isinstance(granted,str):granted=granted.split(',')
        if not isinstance(granted,list) or any(not isinstance(x,str) for x in granted):raise HTTPException(403,'Instagram permissions could not be verified')
        if not isinstance(token,str) or not account_id.isdigit() or not {'instagram_business_basic','instagram_business_manage_messages'}.issubset(set(granted)):
            raise HTTPException(403,'Instagram messaging permission was not granted. Reconnect a Business or Creator account.')
        long=await graph(client,'GET','https://graph.instagram.com/access_token',params={'grant_type':'ig_exchange_token','client_secret':settings.instagram_client_secret,'access_token':token})
        token=long.get('access_token');expires=long.get('expires_in')
        if not isinstance(token,str) or not isinstance(expires,(int,float)) or expires<=0:raise HTTPException(502,'Instagram returned an incomplete token response')
        identity=await graph(client,'GET',f'https://graph.instagram.com/{settings.instagram_api_version}/me',headers={'Authorization':'Bearer '+token},params={'fields':'user_id,username'})
        if str(identity.get('user_id',''))!=account_id:raise HTTPException(403,'Instagram account ownership could not be verified')
        existing=store.query('SELECT owner_id FROM social_connections WHERE platform=:p AND account_id=:a',p='instagram',a=account_id)
        if existing and existing[0]['owner_id']!=store.owner.get():raise HTTPException(409,'This Instagram account is already connected to another workspace')
        if settings.instagram_account_id==account_id and store.owner.get()!=0:raise HTTPException(409,'This Instagram account is reserved for the existing owner workspace')
        # Subscription grants access to incoming message events; no messages are sent.
        sub=await graph(client,'POST',f'https://graph.instagram.com/{settings.instagram_api_version}/{account_id}/subscribed_apps',headers={'Authorization':'Bearer '+token},data={'subscribed_fields':'messages'})
        if sub.get('success') is not True:raise HTTPException(502,'Instagram did not confirm webhook subscription')
        persist(account_id,str(identity.get('username') or account_id),token,time.time()+expires)
        store.log('CONNECTION','Instagram authorization and webhook subscription verified; delivery remains dry-run')
def persist(account_id,label,token,expires,platform='instagram'):
    if platform not in ('instagram','facebook','whatsapp') or not account_id.isdigit() or len(account_id)>64:raise HTTPException(422,'Invalid social account')
    legacy={'instagram':settings.instagram_account_id,'facebook':settings.facebook_page_id,'whatsapp':settings.whatsapp_phone_number_id}[platform]
    if legacy==account_id and store.owner.get()!=0:raise HTTPException(409,'This Instagram account is reserved for the existing owner workspace')
    encrypted=cipher().encrypt(token.encode()).decode()
    try:
        with store.engine.begin() as c:
            existing=c.execute(store.text('SELECT owner_id FROM social_connections WHERE platform=:p AND account_id=:a'),{'p':platform,'a':account_id}).scalar()
            if existing is not None and existing!=store.owner.get():raise HTTPException(409,'This Instagram account is already connected to another workspace')
            c.execute(store.text('DELETE FROM social_connections WHERE owner_id=:o AND platform=:p'),{'o':store.owner.get(),'p':platform})
            c.execute(store.text('INSERT INTO social_connections VALUES(:id,:o,:p,:a,:l,:c,:e,:t)'),{'id':str(uuid.uuid4()),'o':store.owner.get(),'p':platform,'a':account_id,'l':label[:200],'c':encrypted,'e':expires,'t':time.time()})
    except IntegrityError:raise HTTPException(409,'This Instagram account is already connected to another workspace')
def connection(identifier):
    rows=store.query('SELECT * FROM social_connections WHERE id=:id AND owner_id=:o',id=identifier,o=store.owner.get())
    if not rows or rows[0]['expires_at']<=time.time():return None
    return rows[0]
def decrypt(row):
    try:return cipher().decrypt(row['token_ciphertext'].encode()).decode()
    except InvalidToken:raise HTTPException(503,'Social token encryption key is unavailable or changed')
def disconnect(platform):
    if platform not in ('instagram','facebook','whatsapp'):raise HTTPException(422,'Unsupported connection platform')
    store.execute('DELETE FROM social_connections WHERE owner_id=:o AND platform=:p',o=store.owner.get(),p=platform)
    store.log('CONNECTION',platform+' disconnected locally; pending replies will be cancelled')
    # Stop is incremented before deleting connection elsewhere to cancel in-flight AI.
    return {'ok':True,'provider_authorization_revoked':False}
async def send(row,recipient,message):
    platform=row['platform']
    host='graph.instagram.com' if platform=='instagram' else 'graph.facebook.com'
    version={'instagram':settings.instagram_api_version,'facebook':settings.facebook_api_version,'whatsapp':settings.whatsapp_api_version}[platform]
    payload={'recipient':{'id':recipient},'message':{'text':message}}
    if platform=='facebook':payload['messaging_type']='RESPONSE'
    if platform=='whatsapp':payload={'messaging_product':'whatsapp','to':recipient,'type':'text','text':{'body':message}}
    async with httpx.AsyncClient(timeout=20) as client:
        data=await graph(client,'POST',f'https://{host}/{version}/{row["account_id"]}/messages',headers={'Authorization':'Bearer '+decrypt(row)},json=payload)
        confirmed=data.get('message_id') if platform!='whatsapp' else bool(data.get('messages') and data['messages'][0].get('id'))
        if not confirmed:raise HTTPException(502,'Delivery was not confirmed; do not retry automatically')
        return data


def meta_configured():return bool(len(settings.social_token_encryption_key)>=32 and settings.meta_app_id and settings.meta_app_secret and settings.backend_url.startswith('https://') and settings.meta_verify_token)
def meta_state(platform):
    if not meta_configured():raise HTTPException(503,'The app owner must configure Meta OAuth, webhook and token encryption')
    state=secrets.token_urlsafe(32)
    store.execute('DELETE FROM social_oauth_states WHERE expires_at<:t',t=time.time())
    store.execute('INSERT INTO social_oauth_states VALUES(:d,:o,:p,:t)',d=hashlib.sha256(state.encode()).hexdigest(),o=store.owner.get(),p=platform,t=time.time()+600)
    return state

def facebook_begin():
    state=meta_state('facebook')
    params={'client_id':settings.meta_app_id,'redirect_uri':settings.backend_url.rstrip('/')+'/oauth/facebook/callback','state':state,'response_type':'code','scope':'pages_show_list,pages_messaging,pages_manage_metadata'}
    if settings.facebook_login_config_id:params['config_id']=settings.facebook_login_config_id
    return {'url':f'https://www.facebook.com/{settings.facebook_api_version}/dialog/oauth?'+urlencode(params)}

async def facebook_complete(code):
    if not meta_configured():raise HTTPException(503,'Meta OAuth is not configured')
    async with httpx.AsyncClient(timeout=20) as client:
        auth=await graph(client,'GET',f'https://graph.facebook.com/{settings.facebook_api_version}/oauth/access_token',params={'client_id':settings.meta_app_id,'client_secret':settings.meta_app_secret,'redirect_uri':settings.backend_url.rstrip('/')+'/oauth/facebook/callback','code':code})
        token=auth.get('access_token');expires=auth.get('expires_in')
        if not isinstance(token,str) or not isinstance(expires,(int,float)) or expires<=0:raise HTTPException(502,'Meta returned an incomplete access token')
        headers={'Authorization':'Bearer '+token}
        permissions=await graph(client,'GET',f'https://graph.facebook.com/{settings.facebook_api_version}/me/permissions',headers=headers)
        granted={r.get('permission') for r in permissions.get('data',[]) if r.get('status')=='granted'}
        if not {'pages_show_list','pages_messaging','pages_manage_metadata'}.issubset(granted):raise HTTPException(403,'Facebook Page messaging and management permissions are required')
        pages=await graph(client,'GET',f'https://graph.facebook.com/{settings.facebook_api_version}/me/accounts',headers=headers,params={'fields':'id,name,access_token,tasks','limit':100})
        candidates=[]
        for page in pages.get('data',[]):
            account=str(page.get('id',''));page_token=page.get('access_token')
            if not account.isdigit() or not isinstance(page_token,str) or not set(page.get('tasks',[])).intersection({'MESSAGE','MESSAGING','MANAGE'}):continue
            candidates.append({'id':str(uuid.uuid4()),'o':store.owner.get(),'a':account,'l':str(page.get('name') or account)[:200],'c':cipher().encrypt(page_token.encode()).decode(),'e':time.time()+600,'te':time.time()+expires})
        if not candidates:raise HTTPException(403,'No Facebook Pages with messaging access were found')
        with store.engine.begin() as c:
            c.execute(store.text('DELETE FROM social_page_candidates WHERE owner_id=:o OR expires_at<:t'),{'o':store.owner.get(),'t':time.time()})
            for page in candidates:c.execute(store.text('INSERT INTO social_page_candidates VALUES(:id,:o,:a,:l,:c,:e,:te)'),page)
    store.log('CONNECTION','Facebook authorization received; choose a Page to connect')

async def facebook_select(identifier):
    rows=store.query('SELECT * FROM social_page_candidates WHERE id=:id AND owner_id=:o AND expires_at>:t',id=identifier,o=store.owner.get(),t=time.time())
    if not rows:raise HTTPException(404,'Page selection expired or unavailable. Reconnect Facebook.')
    page=rows[0];account=page['account_id'];token=decrypt(page)
    assert_claimable('facebook',account)
    async with httpx.AsyncClient(timeout=20) as client:
        sub=await graph(client,'POST',f'https://graph.facebook.com/{settings.facebook_api_version}/{account}/subscribed_apps',headers={'Authorization':'Bearer '+token},data={'subscribed_fields':'messages'})
        if sub.get('success') is not True:raise HTTPException(502,'Facebook did not confirm webhook subscription')
    persist(account,page['label'],token,page['token_expires_at'],'facebook')
    store.execute('DELETE FROM social_page_candidates WHERE owner_id=:o',o=store.owner.get())
    store.log('CONNECTION','Facebook Page authorization and webhook subscription verified; delivery remains dry-run')
    return {'ok':True}

def assert_claimable(platform,account):
    legacy={'instagram':settings.instagram_account_id,'facebook':settings.facebook_page_id,'whatsapp':settings.whatsapp_phone_number_id}[platform]
    if legacy==account and store.owner.get()!=0:raise HTTPException(409,'This account is reserved for the existing owner workspace')
    rows=store.query('SELECT owner_id FROM social_connections WHERE platform=:p AND account_id=:a',p=platform,a=account)
    if rows and rows[0]['owner_id']!=store.owner.get():raise HTTPException(409,'This account is already connected to another workspace')

def whatsapp_begin():
    if not settings.whatsapp_signup_config_id:raise HTTPException(503,'WhatsApp Embedded Signup requires app-owner configuration and Meta approval')
    state=meta_state('whatsapp')
    return {'state':state,'app_id':settings.meta_app_id,'config_id':settings.whatsapp_signup_config_id,'version':settings.whatsapp_api_version}

async def whatsapp_complete(x):
    account=consume(x.state,'whatsapp',store.owner.get())
    if account!=store.owner.get():raise HTTPException(403,'This signup belongs to another account')
    if not meta_configured() or not settings.whatsapp_signup_config_id:raise HTTPException(503,'WhatsApp onboarding is not configured')
    async with httpx.AsyncClient(timeout=20) as client:
        auth=await graph(client,'GET',f'https://graph.facebook.com/{settings.whatsapp_api_version}/oauth/access_token',params={'client_id':settings.meta_app_id,'client_secret':settings.meta_app_secret,'code':x.code})
        token=auth.get('access_token')
        if not isinstance(token,str):raise HTTPException(502,'Meta returned an incomplete token')
        headers={'Authorization':'Bearer '+token}
        debug=await graph(client,'GET',f'https://graph.facebook.com/{settings.whatsapp_api_version}/debug_token',headers={'Authorization':'Bearer '+settings.meta_app_id+'|'+settings.meta_app_secret},params={'input_token':token})
        details=debug.get('data',{})
        if details.get('is_valid') is not True or str(details.get('app_id'))!=settings.meta_app_id or not {'whatsapp_business_management','whatsapp_business_messaging'}.issubset(set(details.get('scopes',[]))):raise HTTPException(403,'WhatsApp token or required app permissions could not be verified')
        expiry=[v for v in (details.get('expires_at'),details.get('data_access_expires_at')) if isinstance(v,(int,float)) and v>0]
        expires=min(expiry) if expiry else 253402300799.0
        if expires<=time.time():raise HTTPException(403,'WhatsApp authorization has expired')
        phones=await graph(client,'GET',f'https://graph.facebook.com/{settings.whatsapp_api_version}/{x.waba_id}/phone_numbers',headers=headers,params={'fields':'id,display_phone_number,verified_name','limit':100})
        phone=next((p for p in phones.get('data',[]) if str(p.get('id'))==x.phone_number_id),None)
        if not phone:raise HTTPException(403,'This phone number does not belong to the authorized WhatsApp Business Account')
        assert_claimable('whatsapp',x.phone_number_id)
        registered=await graph(client,'POST',f'https://graph.facebook.com/{settings.whatsapp_api_version}/{x.phone_number_id}/register',headers=headers,json={'messaging_product':'whatsapp','pin':x.pin})
        if registered.get('success') is not True:raise HTTPException(502,'WhatsApp phone registration was not confirmed')
        subscribed=await graph(client,'POST',f'https://graph.facebook.com/{settings.whatsapp_api_version}/{x.waba_id}/subscribed_apps',headers=headers)
        if subscribed.get('success') is not True:raise HTTPException(502,'WhatsApp webhook subscription was not confirmed')
        persist(x.phone_number_id,str(phone.get('verified_name') or phone.get('display_phone_number') or x.phone_number_id),token,expires,'whatsapp')
    store.log('CONNECTION','WhatsApp Business authorization, phone registration and webhook subscription verified; delivery remains dry-run')
    return {'ok':True}
