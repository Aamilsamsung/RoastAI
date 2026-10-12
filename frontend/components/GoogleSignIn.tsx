'use client'
import {useEffect,useRef,useState} from 'react'
import Script from 'next/script'
type Props={request:(path:string,options?:RequestInit)=>Promise<any>,onSuccess:(data:any)=>void,onError:(message:string)=>void,link?:boolean}
export default function GoogleSignIn({request,onSuccess,onError,link=false}:Props){
 const container=useRef<HTMLDivElement>(null),callbacks=useRef({request,onSuccess,onError});callbacks.current={request,onSuccess,onError}
 const inFlight=useRef(false)
 const [client,setClient]=useState(''),[ready,setReady]=useState(false),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0),[failed,setFailed]=useState(false),[configLoaded,setConfigLoaded]=useState(false)
 useEffect(()=>{let active=true;callbacks.current.request('/api/auth/config').then(data=>{if(active){setClient(data.google_client_id||'');setConfigLoaded(true)}}).catch(()=>{if(active)setFailed(true)});return()=>{active=false}},[retry])
 useEffect(()=>{
  if(!client||!ready||!container.current)return
  let active=true
  const renew=setInterval(()=>{if(!inFlight.current)setRetry(v=>v+1)},240000)
  callbacks.current.request('/api/auth/google/challenge',{method:'POST'}).then(({nonce})=>{
   if(!active||!container.current)return
   const identity=(window as any).google?.accounts?.id
   if(!identity)throw new Error('Google sign-in could not load')
   identity.initialize({client_id:client,nonce,auto_select:false,callback:async(response:{credential:string})=>{
    if(!active||inFlight.current)return;inFlight.current=true;setBusy(true)
    try{const data=await callbacks.current.request('/api/auth/google'+(link?'/link':''),{method:'POST',body:JSON.stringify({credential:response.credential,nonce})});if(active)callbacks.current.onSuccess(data)}
    catch(error){if(active){callbacks.current.onError(error instanceof Error?error.message:'Google sign-in failed');setRetry(v=>v+1)}}
    finally{inFlight.current=false;if(active)setBusy(false)}
   }})
   container.current.replaceChildren();identity.renderButton(container.current,{theme:'outline',size:'large',text:link?'continue_with':'signin_with',width:Math.min(320,container.current.clientWidth||280)})
  }).catch(error=>{if(active){container.current?.replaceChildren();setFailed(true);callbacks.current.onError(error.message)}})
  return()=>{active=false;clearInterval(renew);container.current?.replaceChildren()}
 },[client,ready,link,retry])
 return <div className="googleEntry" aria-busy={busy}>{client&&<Script src="https://accounts.google.com/gsi/client" onReady={()=>setReady(true)} onError={()=>{setFailed(true);onError('Unable to load Google sign-in. You can still use email.')}}/>}{!client&&!failed&&<><button className="secondary full" disabled>{configLoaded?'Continue with Google · setup needed':'Checking Google sign-in…'}</button>{configLoaded&&<p>Google sign-in will be available once the workspace owner completes setup. Email sign-in is available now.</p>}</>}{client&&!ready&&!failed&&<p role="status">Loading Google sign-in…</p>}<div ref={container} className={'googleButtonHost '+(busy?'googleBusy':'')} inert={busy}/>{busy&&<p role="status">Connecting to HUB…</p>}{failed&&<button type="button" className="secondary full" onClick={()=>{if(client&&!(window as any).google?.accounts?.id){window.location.reload();return}setFailed(false);setRetry(v=>v+1)}}>Retry Google sign-in</button>}</div>
}
