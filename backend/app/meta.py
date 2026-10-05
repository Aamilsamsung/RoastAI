import hashlib,hmac,httpx
from .config import settings

def verify_signature(body,signature):
    if not settings.meta_app_secret or not signature: return False
    expected="sha256="+hmac.new(settings.meta_app_secret.encode(),body,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(),signature.encode())

def parse_events(payload):
    out=[]
    if payload.get("object")=="whatsapp_business_account":
        for e in payload.get("entry",[]):
            for c in e.get("changes",[]):
                phone=c.get("value",{}).get("metadata",{}).get("phone_number_id")
                if phone and settings.whatsapp_phone_number_id and phone != settings.whatsapp_phone_number_id: continue
                for m in c.get("value",{}).get("messages",[]):
                    if m.get("type")=="text":
                        out.append({"platform":"whatsapp","sender_id":m.get("from",""),"sender_name":"",
                        "message_id":m.get("id",""),"text":m.get("text",{}).get("body","")})
    elif payload.get("object") == "instagram":
        for e in payload.get("entry",[]):
            if e.get("id") and settings.instagram_account_id and e["id"] != settings.instagram_account_id: continue
            for m in e.get("messaging",[]):
                t=m.get("message",{}).get("text")
                if t and not m.get("message",{}).get("is_echo") and m.get("sender",{}).get("id") != settings.instagram_account_id: out.append({"platform":"instagram","sender_id":m.get("sender",{}).get("id",""),
                "sender_name":"","message_id":m.get("message",{}).get("mid",""),"text":t})
    return out

async def whatsapp_send(recipient,text):
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        raise RuntimeError("WhatsApp credentials are not configured.")
    url=f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    headers={"Authorization":f"Bearer {settings.whatsapp_access_token}"}
    payload={"messaging_product":"whatsapp","to":recipient,"type":"text","text":{"body":text}}
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post(url,headers=headers,json=payload); r.raise_for_status(); return r.json()

async def instagram_send(recipient, text):
    if not settings.instagram_access_token or not settings.instagram_account_id:
        raise RuntimeError('Instagram credentials are not configured')
    host = 'graph.instagram.com' if settings.instagram_login_type == 'instagram' else 'graph.facebook.com'
    url = f'https://{host}/{settings.instagram_api_version}/{settings.instagram_account_id}/messages'
    payload = {'recipient': {'id': recipient}, 'message': {'text': text}}
    if settings.instagram_login_type == 'facebook': payload['messaging_type'] = 'RESPONSE'
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers={'Authorization': f'Bearer {settings.instagram_access_token}'}, json=payload)
        response.raise_for_status()
        return response.json()
