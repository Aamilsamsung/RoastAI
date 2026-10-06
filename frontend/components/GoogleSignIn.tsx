'use client'
import {useEffect,useRef,useState} from 'react'
import Script from 'next/script'
type Props={request:(path:string,options?:RequestInit)=>Promise<any>,onSuccess:(data:any)=>void,onError:(message:string)=>void,link?:boolean}
export default function GoogleSignIn({request,onSuccess,onError,link=false}:Props){
 const container=useRef<HTMLDivElement>(null),callbacks=useRef({request,onSuccess,onError});callbacks.current={request,onSuccess,onError}
 const [client,setClient]=useState(''),[ready,setReady]=useState(false),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0),[failed,setFailed]=useState(false)
 useEffect(()=>{let active=true;callbacks.current.request('/api/auth/config').then(data=>{if(active)setClient(data.google_client_id||'')}).catch(()=>{if(active)setFailed(true)});return()=>{active=false}},[retry])
 useEffect(()=>{
  if(!client||!ready||!container.current)return
  let active=true
  callbacks.current.request('/api/auth/google/challenge',{method:'POST'}).then(({nonce})=>{
   if(!active||!container.current)return
   const identity=(window as any).google?.accounts?.id
   if(!identity)throw new Error('Google sign-in could not load')
   identity.initialize({client_id:client,nonce,auto_select:false,callback:async(response:{credential:string})=>{
    if(!active)return;setBusy(true)
    try{const data=await callbacks.current.request('/api/auth/google'+(link?'/link':''),{method:'POST',body:JSON.stringify({credential:response.credential,nonce})});if(active)callbacks.current.onSuccess(data)}
    catch(error){if(active){callbacks.current.onError(error instanceof Error?error.message:'Google sign-in failed');setRetry(v=>v+1)}}
    finally{if(active)setBusy(false)}
   }})
   container.current.replaceChildren();identity.renderButton(container.current,{theme:'outline',size:'large',text:link?'continue_with':'signin_with',width:Math.min(320,container.current.clientWidth||280)})
  }).catch(error=>{if(active){setFailed(true);callbacks.current.onError(error.message)}})
  return()=>{active=false}
 },[client,ready,link,retry])
 return <div style={{marginTop:16,minHeight:44}}>{client&&<Script src="https://accounts.google.com/gsi/client" onReady={()=>setReady(true)} onError={()=>{setFailed(true);onError('Unable to load Google sign-in')}}/>}{!client&&!failed&&<button className="secondary full" disabled title="The owner must configure GOOGLE_CLIENT_ID on the backend">Google sign-in · setup needed</button>}<div ref={container} style={{pointerEvents:busy?'none':'auto',opacity:busy?.6:1}}/>{busy&&<p role="status">Connecting to HUB…</p>}{failed&&<button className="secondary" onClick={()=>{setFailed(false);setRetry(v=>v+1)}}>Retry Google sign-in</button>}</div>
}
