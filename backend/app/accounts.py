import hashlib, hmac, secrets, time
from pydantic import BaseModel, Field, field_validator
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from . import store
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
    if not rows or not hmac.compare_digest(password_hash(credentials.password,rows[0]['password_hash'].split(':')[0]),rows[0]['password_hash']): raise HTTPException(401,'Invalid email or password')
    store.execute('DELETE FROM sessions WHERE expires<:now',now=time.time())
    token=secrets.token_urlsafe(48)
    store.execute('INSERT INTO sessions(digest,user_id,expires) VALUES(:d,:u,:e)',d=hashlib.sha256(token.encode()).hexdigest(),u=rows[0]['id'],e=time.time()+86400)
    return {'token':token,'expires_in':86400}
