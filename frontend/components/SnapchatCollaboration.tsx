'use client'
import {useState} from 'react'
export default function SnapchatCollaboration({request,onError}:{request:(path:string,options?:RequestInit)=>Promise<any>,onError:(message:string)=>void}){
 const [creator,setCreator]=useState(''),[message,setMessage]=useState(''),[messages,setMessages]=useState<{id:string,text:string}[]>([]),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
 async function run(send:boolean){setBusy(true);setNotice('');try{
  if(send){const data=await request('/api/snapchat/messages',{method:'POST',body:JSON.stringify({creator_profile_id:creator,message})});setNotice(data.dry_run?'Dry-run: nothing was sent.':'Snapchat accepted the message.');if(data.accepted)setMessage('')}
  else{const data=await request('/api/snapchat/messages?creator_profile_id='+encodeURIComponent(creator));setMessages(data.messages);setNotice(data.has_more?'Showing the latest 50 messages. Older messages may exist.':data.messages.length?'Conversation loaded.':'No messages yet.')}
 }catch(error){onError(error instanceof Error?error.message:'Snapchat request failed')}finally{setBusy(false)}}
 return <section style={{marginTop:24}}><h3>Snapchat creator collaboration</h3><p className="muted">Requires approved Public Profile messaging access. Manual collaboration messages only.</p><label>Creator profile UUID<input value={creator} onChange={e=>{setCreator(e.target.value);setMessages([])}} maxLength={36} placeholder="Creator Public Profile ID"/></label><button className="secondary" disabled={busy||!creator} onClick={()=>run(false)}>Load conversation</button><label>Collaboration message<textarea value={message} onChange={e=>setMessage(e.target.value)} maxLength={1000}/></label><button className="primary" disabled={busy||!creator||!message.trim()} onClick={()=>run(true)}>{busy?'Connecting to HUB…':'Send collaboration message'}</button><p role="status">{notice}</p>{messages.map((item,index)=><p className="bubble" key={item.id||index}>{item.text}</p>)}</section>
}
