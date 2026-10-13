'use client'
import Script from 'next/script'
import {useEffect,useRef,useState} from 'react'
type Props={configured:boolean;request:(path:string,options?:RequestInit)=>Promise<any>;onConnected:()=>Promise<void>;onError:(message:string)=>void;onBusy:(busy:boolean)=>void}
type Signup={state:string;app_id:string;config_id:string;version:string}
export default function WhatsAppSignup(props:Props){
 const callbacks=useRef(props);callbacks.current=props
 const [ready,setReady]=useState(false),[busy,setBusy]=useState(false),[pin,setPin]=useState(''),[signup,setSignup]=useState<Signup|null>(null),[attempt,setAttempt]=useState(0),[setupFailed,setSetupFailed]=useState(false)
 const active=useRef(false),assets=useRef<{waba_id:string;phone_number_id:string}|null>(null),mounted=useRef(true)
 useEffect(()=>{mounted.current=true;const receive=(event:MessageEvent)=>{
  if(!active.current||!['https://www.facebook.com','https://web.facebook.com'].includes(event.origin))return
  try{const data=typeof event.data==='string'?JSON.parse(event.data):event.data;if(data?.type==='WA_EMBEDDED_SIGNUP'&&data.event==='FINISH'&&/^[0-9]{1,64}$/.test(data.data?.waba_id)&&/^[0-9]{1,64}$/.test(data.data?.phone_number_id))assets.current={waba_id:String(data.data.waba_id),phone_number_id:String(data.data.phone_number_id)}}catch{}
 };window.addEventListener('message',receive);return()=>{mounted.current=false;active.current=false;window.removeEventListener('message',receive)}},[])
 useEffect(()=>{
  if(!props.configured||!ready)return
  let live=true;setSignup(null);setSetupFailed(false)
  callbacks.current.request('/api/social/whatsapp/connect',{method:'POST'}).then(data=>{
   if(!live)return
   const fb=(window as any).FB;if(!fb)throw Error('Meta signup could not load. Refresh and retry.')
   fb.init({appId:data.app_id,version:data.version,xfbml:false,cookie:false});setSignup(data)
  }).catch(e=>{if(live){setSetupFailed(true);callbacks.current.onError(e instanceof Error?e.message:'Unable to prepare WhatsApp signup')}})
  const renew=setInterval(()=>{if(!active.current)setAttempt(v=>v+1)},240000)
  return()=>{live=false;clearInterval(renew)}
 },[props.configured,ready,attempt])
 function connect(){
  if(active.current||busy||!signup||pin.length!==6)return
  const fb=(window as any).FB;if(!fb){callbacks.current.onError('Meta signup could not load. Refresh and retry.');return}
  active.current=true;assets.current=null;setBusy(true);callbacks.current.onBusy(true)
  // Begin popup synchronously inside the user's click, after prefetching the nonce.
  try{fb.login(async(response:any)=>{
   if(!mounted.current||!active.current)return
   try{
    const code=response?.authResponse?.code;if(!code)throw Error('WhatsApp signup was cancelled or did not return authorization.')
    for(let i=0;i<50&&!assets.current&&mounted.current;i++)await new Promise(r=>setTimeout(r,100))
    if(!mounted.current)return
    if(!assets.current)throw Error('WhatsApp did not return a Cloud API phone number. Coexistence-only and incomplete signup are not supported in this flow.')
    await callbacks.current.request('/api/social/whatsapp/complete',{method:'POST',body:JSON.stringify({state:signup.state,code,...assets.current,pin})})
    if(mounted.current)await callbacks.current.onConnected()
   }catch(e){if(mounted.current)callbacks.current.onError(e instanceof Error?e.message:'WhatsApp connection failed')}
   finally{active.current=false;assets.current=null;if(mounted.current){setBusy(false);callbacks.current.onBusy(false);setPin('');setAttempt(v=>v+1)}}
  },{config_id:signup.config_id,response_type:'code',override_default_response_type:true,extras:{setup:{},sessionInfoVersion:'3'}})}
  catch(e){active.current=false;setBusy(false);callbacks.current.onBusy(false);callbacks.current.onError(e instanceof Error?e.message:'WhatsApp connection failed')}
 }
 return <div>{props.configured&&<Script src="https://connect.facebook.net/en_US/sdk.js" onReady={()=>setReady(true)} onError={()=>callbacks.current.onError('Meta signup could not load. Refresh the page and retry.')}/>}<p className="muted">Embedded Signup connects a WhatsApp Business Cloud API phone number. Continuing registers the number and subscribes it to incoming-message webhooks. No messages are sent during signup.</p><label className="socialPin">Phone registration PIN<input type="password" inputMode="numeric" autoComplete="off" maxLength={6} value={pin} onChange={e=>setPin(e.target.value.replace(/\D/g,''))} disabled={busy||!props.configured} aria-describedby="wa-pin-help"/></label><small id="wa-pin-help">Enter the six-digit two-step verification PIN for this business number. It is never stored.</small><button className="primary" disabled={busy||!signup||pin.length!==6} onClick={connect}>{busy?'Connecting…':props.configured&&!signup?'Preparing Meta signup…':'Continue to WhatsApp Business'}</button>{setupFailed&&<button className="secondary" onClick={()=>setAttempt(v=>v+1)}>Retry signup setup</button>}</div>
}
