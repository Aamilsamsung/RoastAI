'use client'
import {useEffect,useRef,useState} from 'react'

type Request=(path:string,options?:RequestInit,timeoutMs?:number)=>Promise<any>
type Props={request:Request;onSuccess:(data:any)=>void;onError:(message:string)=>void;link?:boolean;disabled?:boolean;onBusyChange?:(busy:boolean)=>void}
type Stage='config'|'setup'|'script'|'challenge'|'ready'|'popup'|'verifying'|'verified'|'error'
let sdkPromise:Promise<any>|null=null
function identity(){return (window as any).google?.accounts?.id}
function loadIdentity(){
 if(identity())return Promise.resolve(identity())
 if(sdkPromise)return sdkPromise
 sdkPromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.async=true
  const fail=()=>{clearTimeout(timer);script.remove();reject(Error('Google’s sign-in service could not load. Check your connection or browser blocking settings, then retry.'))}
  const timer=setTimeout(fail,12000)
  script.onload=()=>{clearTimeout(timer);if(identity())resolve(identity());else fail()}
  script.onerror=fail;document.head.appendChild(script)
 }).catch(error=>{sdkPromise=null;throw error})
 return sdkPromise
}
export default function GoogleSignIn(props:Props){
 const host=useRef<HTMLDivElement>(null),callbacks=useRef(props);callbacks.current=props
 const stage=useRef<Stage>('config'),inFlight=useRef(false)
 const [phase,setPhase]=useState<Stage>('config'),[retry,setRetry]=useState(0),[message,setMessage]=useState('')
 const move=(next:Stage)=>{stage.current=next;setPhase(next)}
 useEffect(()=>{
  let active=true
  inFlight.current=false;callbacks.current.onBusyChange?.(false);move('config');setMessage('')
  async function prepare(){
   let config
   try{config=await callbacks.current.request('/api/auth/config',{},12000)}
   catch{if(active){const text='The sign-in server is unavailable. Google and email sign-in need the backend to be online. Please retry shortly.';setMessage(text);move('error');callbacks.current.onError(text)}return}
   if(!active)return
   const client=typeof config.google_client_id==='string'?config.google_client_id.trim():''
   if(!client){move('setup');setMessage(config.google_setup_error==='invalid_client_id'?'Google setup needs a Web Client ID ending in .apps.googleusercontent.com. An API key or Client Secret cannot be used here.':'Google sign-in needs the app owner to configure a Google Web Client ID.');return}
   try{
    move('script');const id=await loadIdentity();if(!active||!host.current)return
    move('challenge')
    let nonce:string
    try{const challenge=await callbacks.current.request('/api/auth/google/challenge',{method:'POST'},12000);nonce=challenge.nonce;if(typeof nonce!=='string'||nonce.length<32)throw Error('Invalid challenge')}
    catch{throw Error('The sign-in server could not prepare a secure Google login. Please retry when the backend is online.')}
    if(!active||!host.current)return
    id.initialize({client_id:client,nonce,auto_select:false,callback:async(response:{credential?:string})=>{
     if(!active||inFlight.current)return
     inFlight.current=true;move('verifying');callbacks.current.onBusyChange?.(true)
     try{
      if(!response.credential)throw Error('Google did not return a sign-in credential. Please try again.')
      const data=await callbacks.current.request('/api/auth/google'+(props.link?'/link':''),{method:'POST',body:JSON.stringify({credential:response.credential,nonce})},25000)
      if(!data?.token)throw Error('The sign-in server returned an incomplete session. Please try again.')
      if(active){move('verified');callbacks.current.onSuccess(data)}
     }catch(error){if(active){callbacks.current.onError(error instanceof Error?error.message:'Google sign-in failed');setRetry(v=>v+1)}}
     finally{inFlight.current=false;if(active)callbacks.current.onBusyChange?.(false)}
    }})
    host.current.replaceChildren()
    id.renderButton(host.current,{theme:'outline',size:'large',text:props.link?'continue_with':'signin_with',width:Math.min(320,host.current.clientWidth||240),click_listener:()=>{
     if(active&&!callbacks.current.disabled){move('popup');callbacks.current.onError('');callbacks.current.onBusyChange?.(true)}
    }})
    move('ready')
   }catch(error){if(active){const text=error instanceof Error?error.message:'Google sign-in could not load';setMessage(text);move('error');callbacks.current.onError(text)}}
  }
  void prepare()
  // Do not replace Google's global nonce/callback while its account picker is open.
  const renew=setInterval(()=>{if(stage.current==='ready'&&!inFlight.current)setRetry(v=>v+1)},240000)
  return()=>{active=false;clearInterval(renew);host.current?.replaceChildren();callbacks.current.onBusyChange?.(false)}
 },[retry,props.link])
 const waiting=phase==='config'||phase==='script'||phase==='challenge'
 return <div className="googleEntry" aria-busy={waiting||phase==='verifying'}>
  {waiting&&<p role="status">{phase==='config'?'Checking Google sign-in…':phase==='script'?'Loading Google sign-in…':'Preparing secure sign-in…'}</p>}
  {phase==='setup'&&<><button className="secondary full" disabled>Continue with Google · setup needed</button><p role="status">{message}</p></>}
  <div ref={host} className={'googleButtonHost '+(phase==='verifying'?'googleBusy':'')} inert={Boolean(props.disabled)||phase==='verifying'||phase==='verified'||phase==='popup'}/>
  {(phase==='verifying'||phase==='verified')&&<p role="status">Connecting to HUB…</p>}{phase==='verified'&&<button type="button" className="secondary full" onClick={()=>setRetry(v=>v+1)}>Retry Google sign-in</button>}
  {phase==='popup'&&<><p role="status">Finish in the Google window. If it closed, try again.</p><button type="button" className="secondary full" onClick={()=>{callbacks.current.onBusyChange?.(false);setRetry(v=>v+1)}}>Try Google again</button></>}
  {phase==='error'&&<><p>{message}</p><button type="button" className="secondary full" disabled={props.disabled} onClick={()=>setRetry(v=>v+1)}>Retry Google sign-in</button></>}
 </div>
}
