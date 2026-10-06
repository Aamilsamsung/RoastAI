"""Official allowlisted brand–creator collaboration; never general Snapchat DMs."""
from uuid import UUID, uuid4
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .config import settings

class Collaboration(BaseModel):
    creator_profile_id: UUID
    message: str = Field(min_length=1,max_length=1000)

async def api(method,path,**kwargs):
    if not settings.snapchat_access_token or not settings.snapchat_profile_id:
        raise HTTPException(503,'Configure approved Snapchat Public Profile credentials first')
    try: profile=str(UUID(settings.snapchat_profile_id))
    except ValueError: raise HTTPException(503,'Snapchat brand profile ID must be a UUID')
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.request(method,f'https://businessapi.snapchat.com/v1/public_profiles/{profile}/{path}',headers={'Authorization':'Bearer '+settings.snapchat_access_token},**kwargs)
            response.raise_for_status();data=response.json()
        if data.get('request_status')!='SUCCESS': raise ValueError('Rejected request')
        return data
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,'Snapchat request failed. Verify access token, profile permissions and messaging allowlist approval. Do not retry uncertain sends automatically.')

async def conversation(creator):
    data=await api('GET','group_conversation',params={'creator_profile_id':str(creator)})
    item=data.get('conversation',{})
    try: cid=str(UUID(item['conversation_id']))
    except (ValueError,KeyError,TypeError): raise HTTPException(502,'Snapchat returned an invalid conversation')
    token='SnapProfileId/'+str(UUID(settings.snapchat_profile_id))
    if item.get('token')!=token: raise HTTPException(502,'Snapchat returned an unexpected conversation token')
    return {'conversation_id':cid,'token':token}

async def read(creator):
    conv=await conversation(creator)
    data=await api('GET','group_conversation_messages',params={**conv,'limit':50})
    messages=[]
    for item in data.get('group_conversation_messages',[]):
        if item.get('sub_request_status')!='SUCCESS': raise HTTPException(502,'Snapchat could not load all requested messages')
        message=item.get('group_conversation_message',{})
        messages.append({'id':message.get('message_id',''),'text':message.get('text_message','')})
    return {'messages':messages,'has_more':bool(data.get('paging',{}).get('next_page_id'))}

async def send(conv,message):
    data=await api('POST','group_conversation_messages',json={**conv,'group_conversation_messages':[{'type':'TEXT','text_message':message,'message_id':str(uuid4())}]})
    items=data.get('group_conversation_messages',[])
    if len(items)!=1 or items[0].get('sub_request_status')!='SUCCESS': raise HTTPException(502,'Snapchat did not confirm message delivery. Check the conversation before retrying.')
    return {'accepted':True}
