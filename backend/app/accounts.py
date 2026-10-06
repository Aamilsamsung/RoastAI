import hashlib, hmac, secrets, time
from pydantic import BaseModel, Field, field_validator
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from . import store
from .config import settings
class Credentials(BaseModel):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=12,max_length=128)
    @field_validator('email')
    @classmethod
    def validate_email(cls,value):
        value=value.strip().lower()
        if value.count('@')!=1 or '.' not in value.split('@')[-1] or any(c.isspace() for c in value): raise ValueError('Enter a valid email')
        return value

def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def authenticate(token):
    if not token: return None
    rows=store.query('SELECT user_id FROM sessions WHERE digest=:d AND expires>:now',d=hashlib.sha256(token.encode()).hexdigest(),now=time.time())
    return rows[0]['user_id'] if rows else None

def sign_in(credentials,register=False):
    digest=password_hash(credentials.password)
    if register:
        try: store.execute('INSERT INTO users(email,password_hash) VALUES(:e,:p)',e=credentials.email,p=digest)
        except IntegrityError: raise HTTPException(409,'Unable to create account with this email')
    rows=store.query('SELECT * FROM users WHERE email=:e',e=credentials.email)
    if not rows or not rows[0]['password_hash'] or not hmac.compare_digest(password_hash(credentials.password,rows[0]['password_hash'].split(':')[0]),rows[0]['password_hash']): raise HTTPException(401,'Invalid email or password')
    return create_session(rows[0]['id'])

def create_session(user_id):
    store.execute('DELETE FROM sessions WHERE expires<:now',now=time.time())
    token=secrets.token_urlsafe(48)
    store.execute('INSERT INTO sessions(digest,user_id,expires) VALUES(:d,:u,:e)',d=hashlib.sha256(token.encode()).hexdigest(),u=user_id,e=time.time()+86400)
    return {'token':token,'expires_in':86400}


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=20,max_length=16384)
    nonce: str = Field(min_length=32,max_length=128)

def google_challenge():
    if not settings.google_client_id: raise HTTPException(503,'Google sign-in is not configured yet')
    nonce=secrets.token_urlsafe(32)
    store.execute('DELETE FROM login_challenges WHERE expires<:t',t=time.time())
    store.execute('INSERT INTO login_challenges(digest,expires) VALUES(:d,:t)',d=hashlib.sha256(nonce.encode()).hexdigest(),t=time.time()+300)
    return {'nonce':nonce}

def verify_google(credential):
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request
    from google.auth.exceptions import TransportError
    if not settings.google_client_id: raise HTTPException(503,'Google sign-in is not configured yet')
    transport=Request()
    def bounded_request(*args,**kwargs):
        kwargs['timeout']=10
        return transport(*args,**kwargs)
    try: claims=id_token.verify_oauth2_token(credential,bounded_request,settings.google_client_id)
    except ValueError: raise HTTPException(401,'Google sign-in could not be verified')
    except TransportError: raise HTTPException(503,'Google verification is temporarily unavailable')
    if claims.get('iss') not in ('accounts.google.com','https://accounts.google.com') or claims.get('aud')!=settings.google_client_id or not claims.get('email_verified') or not claims.get('sub') or not claims.get('email'):
        raise HTTPException(401,'Google account verification failed')
    return claims

def google_sign_in(x,link_user=None):
    claims=verify_google(x.credential)
    if not hmac.compare_digest(str(claims.get('nonce','')).encode(),x.nonce.encode()): raise HTTPException(401,'Google login challenge mismatch')
    with store.engine.begin() as c:
        used=c.execute(store.text('DELETE FROM login_challenges WHERE digest=:d AND expires>:t'),{'d':hashlib.sha256(x.nonce.encode()).hexdigest(),'t':time.time()})
        if used.rowcount!=1: raise HTTPException(401,'Google sign-in expired. Please try again')
    subject=str(claims['sub']);email=str(claims['email']).strip().lower()
    rows=store.query('SELECT * FROM users WHERE google_subject=:s',s=subject)
    if link_user is not None:
        if link_user==0: raise HTTPException(403,'Sign into your personal account before linking Google')
        user=store.query('SELECT * FROM users WHERE id=:u',u=link_user)
        if not user or user[0]['email']!=email or (rows and rows[0]['id']!=link_user): raise HTTPException(409,'Use the Google account matching your signed-in email')
        if user[0]['google_subject'] and user[0]['google_subject']!=subject: raise HTTPException(409,'This account is already linked to another Google account')
        try: store.execute('UPDATE users SET google_subject=:s WHERE id=:u',s=subject,u=link_user)
        except IntegrityError: raise HTTPException(409,'Google account already linked')
        return create_session(link_user)
    if rows: return create_session(rows[0]['id'])
    if store.query('SELECT id FROM users WHERE email=:e',e=email):
        raise HTTPException(409,'This email already has an account. Sign in with your password, then link Google in Settings.')
    try: store.execute("INSERT INTO users(email,password_hash,google_subject) VALUES(:e,'',:s)",e=email,s=subject)
    except IntegrityError:
        rows=store.query('SELECT id FROM users WHERE google_subject=:s',s=subject)
        if rows: return create_session(rows[0]['id'])
        raise HTTPException(409,'Account already exists. Sign in and link Google in Settings.')
    return create_session(store.query('SELECT id FROM users WHERE google_subject=:s',s=subject)[0]['id'])
