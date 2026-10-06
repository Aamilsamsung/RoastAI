'use client'

import { useEffect, useState } from 'react'
import Logo from '../components/Logo'
import SnapchatCollaboration from '../components/SnapchatCollaboration'
import GoogleSignIn from '../components/GoogleSignIn'
import HubLoading from '../components/HubLoading'

const API = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, '')
const modes = ['normal','funny','sarcastic','savage','brutal','deadpan','intelligent','respectful','vulgar']
const langs = [
  ['auto','Auto detect'],['same','Same as message'],['english','English'],['hindi','Hindi'],
  ['kannada','Kannada'],['malayalam','Malayalam'],['tamil','Tamil'],['telugu','Telugu'],
  ['bengali','Bengali'],['marathi','Marathi'],['punjabi','Punjabi'],['urdu','Urdu']
]

function Icon({name}:{name:string}) {
  const paths:any = {
    chat:<><path d="M4 5h16v11H8l-4 4V5z"/><path d="M8 9h8M8 12h5"/></>,
    social:<><rect x="4" y="4" width="16" height="16" rx="4"/><circle cx="12" cy="12" r="3.5"/><circle cx="17.3" cy="6.8" r="1"/></>,
    history:<><path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 5v5h5"/><path d="M12 7v5l3 2"/></>,
    settings:<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.8 1.8 0 0 0 .3 2l-1 1-2-1a1.8 1.8 0 0 0-2 .3l-.5 2h-1.6l-.5-2a1.8 1.8 0 0 0-2-.3l-2 1-1-1 .9-2a1.8 1.8 0 0 0-.3-2l-2-.5v-1.6l2-.5a1.8 1.8 0 0 0 .3-2l-1-2 1-1 2 .9a1.8 1.8 0 0 0 2-.3l.5-2h1.6l.5 2a1.8 1.8 0 0 0 2 .3l2-1 1 1-1 2a1.8 1.8 0 0 0 .3 2l2 .5v1.6l-2 .5z"/></>,
    activity:<><path d="M4 12h4l2-7 4 14 2-7h4"/></>,
    send:<><path d="M4 4l16 8-16 8 3-8-3-8z"/><path d="M7 12h13"/></>,
    bolt:<><path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/></>,
    link:<><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/></>
  }
  return <svg viewBox="0 0 24 24" className="icon">{paths[name]}</svg>
}

export default function Home() {
  const [tab,setTab] = useState('roast')
  const [msg,setMsg] = useState('')
  const [reply,setReply] = useState('')
  const [meaning,setMeaning] = useState('')
  const [loading,setLoading] = useState(false)
  const [settings,setSettings] = useState<any>({
    enabled:false, whatsapp_enabled:true, instagram_enabled:true, facebook_enabled:false, roast_mode:'savage',
    intensity:7, profanity_level:'light', custom_instructions:'', reply_delay_seconds:1,
    cooldown_seconds:10, max_reply_length:300, dry_run:true, input_language:'auto',
    reply_language:'same', script_mode:'roman', emergency_stop:false
  })
  const [health,setHealth] = useState<any>({})
  const [activities,setActivities] = useState<any[]>([])
  const [convos,setConvos] = useState<any[]>([])
  const [messages,setMessages] = useState<any[]>([])
  const [notice,setNotice] = useState('')
  const [busy,setBusy] = useState(false)
  const [connected,setConnected] = useState(false)
  const [token,setToken] = useState('')
  const [authMode,setAuthMode] = useState('login')
  const [email,setEmail] = useState('')
  const [password,setPassword] = useState('')
  const [sessionReady,setSessionReady] = useState(false)
  const [authorized,setAuthorized] = useState(false)
  const [initializing,setInitializing] = useState(true)
  const [thread,setThread] = useState('Latest messages')
  const [selectedThread,setSelectedThread] = useState({platform:'local',sender_id:'roast-me'})
  const [hasOlder,setHasOlder] = useState(false)
  const [resultMeta,setResultMeta] = useState<any>(null)
  const request = async(path:string, options:RequestInit={}, timeoutMs=45000) => {
    if(!API) throw Error('NEXT_PUBLIC_API_URL is not configured. Set it and rebuild the frontend.')
    const response = await fetch(API+path, {...options, cache:'no-store', headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,...options.headers}, signal:AbortSignal.timeout(timeoutMs)})
    const data = await response.json().catch(()=>({detail:'The server returned an invalid response'}))
    if(!response.ok) {
      if(response.status===401 && !path.startsWith('/api/auth/')) {setAuthorized(false);setToken('');try{sessionStorage.removeItem('roastai-session')}catch{}}
      throw Error(typeof data.detail==='string'?data.detail:'Check your inputs and try again.')
    }
    return data
  }
  const action = async(work:()=>Promise<void>) => {
    if(busy) return
    setBusy(true)
    try { await work() } catch(e:any) { setNotice(e.message) } finally { setBusy(false) }
  }


  const refresh = async(initial=false) => {
    try {
      const [s,h,a,c,m] = await Promise.all([
        request('/api/settings',{},initial?90000:45000),request('/api/platforms/status',{},initial?90000:45000),request('/api/activity',{},initial?90000:45000),
        request('/api/conversations',{},initial?90000:45000),request('/api/messages?platform=local&sender_id=roast-me',{},initial?90000:45000)
      ])
      if(initial) {setSettings(s);setNotice('')}
      else setSettings((old:any)=>({...old,enabled:s.enabled,emergency_stop:s.emergency_stop}))
      setHealth(h); setActivities(a); setConvos(c)
      if(initial) {setMessages(m);setHasOlder(m.length===100)}
      setAuthorized(true); setConnected(true)
    } catch(e:any) { setConnected(false); setNotice(e.message) }
    finally { setInitializing(false) }
  }
  useEffect(()=>{
    try {const saved=JSON.parse(sessionStorage.getItem('roastai-session')||'null');if(saved?.token){setAuthMode(saved.mode==='owner'?'owner':'login');setToken(saved.token)}}catch{}
    setSessionReady(true)
  },[])
  useEffect(()=>{if(!sessionReady)return;if(token && authMode!=='owner') refresh(true);else if(token && initializing) refresh(true);else setInitializing(false)},[sessionReady,token])
  useEffect(()=>{if(authorized && token){try{sessionStorage.setItem('roastai-session',JSON.stringify({token,mode:authMode}))}catch{}}},[authorized,token,authMode])
  useEffect(()=>{
    if(!notice || !authorized) return
    const timer=setTimeout(()=>setNotice(''),7000)
    return ()=>clearTimeout(timer)
  },[notice,authorized])
  useEffect(()=>{
    if(!authorized) return
    const interval=setInterval(()=>{if(!busy && !loading) refresh()},15000)
    return ()=>clearInterval(interval)
  },[authorized,token,busy,loading])
  useEffect(()=>{
    const handler=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setTab('roast');setMsg('')}}
    window.addEventListener('keydown',handler)
    return ()=>window.removeEventListener('keydown',handler)
  },[])
  const save = () => action(async()=>{
    const value=await request('/api/settings',{method:'PUT',body:JSON.stringify(settings)})
    setSettings(value); setNotice('Preferences saved'); await refresh()
  })
  const toggle = () => action(async()=>{
    const value=await request(settings.enabled?'/api/bot/stop':'/api/bot/start',{method:'POST'})
    setSettings(value); setNotice(value.enabled?'Bot started':'Bot paused'); await refresh()
  })
  const emergency = async() => {
    try {
      setSettings(await request('/api/bot/emergency-stop',{method:'POST'}))
      setNotice('Emergency stop activated'); await refresh()
    } catch(e:any) { setNotice(e.message) }
  }
  const roast = async() => {
    if(!msg.trim() || loading || busy) return
    setLoading(true); setReply(''); setMeaning(''); setNotice('')
    try {
      // Studio controls apply to this request even before an explicit Save.
      const saved=await request('/api/settings',{method:'PUT',body:JSON.stringify(settings)})
      setSettings(saved)
      const d=await request('/api/roast',{method:'POST',body:JSON.stringify({message:msg,input_language:settings.input_language,reply_language:settings.reply_language,script_mode:settings.script_mode})})
      setReply(d.reply); setMeaning(d.english_meaning); setResultMeta(d); setNotice('Reply and English meaning generated')
      const latest=await request('/api/messages?platform=local&sender_id=roast-me')
      setMessages(latest);setHasOlder(latest.length===100);setSelectedThread({platform:'local',sender_id:'roast-me'})
      setThread('Local Roast Studio'); await refresh()
    } catch(e:any) { setNotice(e.message) }
    finally { setLoading(false) }
  }
  const clearHistory = () => action(async()=>{
    if(!window.confirm('Delete all conversation messages? Activity and delivery records are retained.')) return
    await request('/api/conversations',{method:'DELETE'})
    setConvos([]); setMessages([]);setHasOlder(false); setReply(''); setMeaning(''); await refresh(); setNotice('History cleared')
  })
  const openConversation = (c:any) => action(async()=>{
    const latest=await request('/api/messages?platform='+encodeURIComponent(c.platform)+'&sender_id='+encodeURIComponent(c.sender_id))
    setMessages(latest);setHasOlder(latest.length===100);setSelectedThread({platform:c.platform,sender_id:c.sender_id})
    setThread((c.sender_name||c.sender_id)+' · '+c.platform)
  })
  const loadOlder = () => action(async()=>{
    if(!messages.length) return
    const older=await request('/api/messages?platform='+encodeURIComponent(selectedThread.platform)+'&sender_id='+encodeURIComponent(selectedThread.sender_id)+'&before_id='+messages[0].id)
    setMessages(previous=>[...older,...previous]);setHasOlder(older.length===100)
  })
  const copyReply = async()=>{
    try { await navigator.clipboard.writeText(reply); setNotice('Response copied') }
    catch { setNotice('Copy failed. Select the response and copy it manually.') }
  }
  const nav = [
    ['roast','Chat','chat'],['conversations','Conversations','history'],['activity','Activity','activity'],
    ['platforms','Platforms','social'],['settings','Settings','settings']
  ]
  const title = ({roast:'Roast Studio',conversations:'Conversations',activity:'Activity',platforms:'Connected socials',settings:'Settings'} as any)[tab]

  if(initializing) return <HubLoading/>
  if(!authorized) return <main className="accessScreen"><div className="card accessCard"><div className="brand"><Logo large/><h1>RoastAI</h1></div><h2>{authMode==='signup'?'Create your account':'Welcome to RoastAI'}</h2><p className="muted">Your conversations and preferences stay private to your account.</p><div className="modeScroll">{[['login','Sign in'],['signup','Sign up'],['owner','Owner access']].map(([mode,label])=><button key={mode} className={'mode '+(authMode===mode?'selected':'')} onClick={()=>{setAuthMode(mode);setNotice('')}}>{label}</button>)}</div><form onSubmit={e=>{e.preventDefault();action(async()=>{if(authMode==='owner'){await refresh(true);return}const data=await request('/api/auth/'+(authMode==='signup'?'signup':'login'),{method:'POST',body:JSON.stringify({email,password})});setPassword('');setToken(data.token)})}}>{authMode==='owner'?<label>Workspace access token<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} required/></label>:<><label>Email<input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label><label>Password<input type="password" minLength={12} maxLength={128} autoComplete={authMode==='signup'?'new-password':'current-password'} value={password} onChange={e=>setPassword(e.target.value)} required/></label><small className="muted">Use at least 12 characters.</small></>}<button className="primary full" disabled={busy}>{busy?'Connecting to HUB…':authMode==='signup'?'Create account':authMode==='owner'?'Connect':'Sign in'}</button></form>{authMode!=='owner'&&<GoogleSignIn request={request} onSuccess={data=>{setAuthMode('login');setToken(data.token);setPassword('')}} onError={setNotice}/>}{notice&&<p role="alert">{notice}</p>}</div></main>
  return <main>
    <aside className="sidebar">
      <div className="brand"><Logo/><div><b>Roast<span>AI</span></b><small>Gemini roast workspace</small></div></div>
      <button className="newRoast" onClick={()=>{setTab('roast');setMsg('')}}><Icon name="bolt"/> New roast <kbd>⌘ K</kbd></button>
      <nav aria-label="Workspace navigation">{nav.map(([id,label,icon])=><button key={id} className={tab===id?'nav active':'nav'} aria-label={label} aria-current={tab===id?'page':undefined} onClick={()=>{setTab(id);refresh()}}><Icon name={icon}/><span>{label}</span>{id==='activity'&&activities.length>0?<em>{Math.min(activities.length,99)}</em>:null}</button>)}</nav>
      <div className="sideCard">
        <div className="miniLogo"><Logo/></div><div><strong>{settings.enabled?'Bot is live':'Bot is paused'}</strong><small>{settings.dry_run?'Dry-run mode':'Live delivery'}</small></div>
        <button aria-label="Toggle bot" aria-pressed={settings.enabled} onClick={toggle} disabled={busy||loading||authMode!=='owner'} title={authMode==='owner'?'Toggle social bot':'Social bot controls are owner-only'} className={settings.enabled?'tinySwitch on':'tinySwitch'}><i/></button>
      </div>
      <button className="emergency" disabled={authMode!=='owner'} title={authMode==='owner'?'Stop social delivery':'Social bot controls are owner-only'} onClick={emergency}>Emergency stop</button>
      <button className="ghost" onClick={()=>{request('/api/auth/logout',{method:'POST'}).catch(()=>{});try{sessionStorage.removeItem('roastai-session')}catch{};setToken('');setAuthorized(false);setReply('');setMeaning('');setMessages([]);setConvos([]);setActivities([]);setNotice('Signed out')}}>Sign out</button><div className="privacy">Secure workspace • Keys stay server-side</div>
    </aside>

    <section className="content">
      <header className="topbar">
        <div><div className="eyebrow">ROASTAI / {tab.toUpperCase()}</div><h1>{title}</h1><p>Fast comebacks, multilingual control, and a clean command center.</p></div>
        <div className="topRight"><div className={connected&&health.gemini?'gemini':'gemini pendingGemini'}><i/> Gemini <span>{!connected?'Offline':health.gemini?'Configured':'Setup needed'}</span></div><button className={settings.enabled?'power on':'power'} onClick={toggle} disabled={busy||loading||authMode!=='owner'}><i/>{settings.enabled?'Bot ON':'Bot OFF'}</button></div>
      </header>

      {notice && <div className="toast" role="status" aria-live="polite">{notice}</div>}

      {tab==='roast' && <div className="studio">
        <div className="heroCard">
          <div className="heroGlow"/>
          <div className="heroCopy"><div className="heroBrand"><Logo large/><span>RoastAI</span></div><div className="kicker">AI COMEBACK STUDIO</div>
            <h2>Say less.<br/><b>Roast better.</b></h2>
            <p>Drop a message and build a comeback in your language, your script, your style.</p>
          </div>
          <div className="heroStats"><div><b>1</b><span>Gemini pass</span></div><div><b>12+</b><span>Languages</span></div><div><b>10</b><span>Intensity levels</span></div></div>
        </div>

        <div className="studioGrid">
          <div className="card composer">
            <div className="cardHead"><div><span className="kicker">MESSAGE</span><h2>What are you replying to?</h2></div><span className="modePill">{settings.roast_mode}</span></div>
            <textarea aria-label="Incoming message" maxLength={5000} value={msg} onChange={e=>setMsg(e.target.value)} onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter') roast()}} placeholder="Paste a message, DM, or sentence…"/>
            <div className="controls3">
              <label>Input language<select value={settings.input_language} onChange={e=>setSettings({...settings,input_language:e.target.value})}>{langs.map(x=><option value={x[0]} key={x[0]}>{x[1]}</option>)}</select></label>
              <label>Reply language<select value={settings.reply_language} onChange={e=>setSettings({...settings,reply_language:e.target.value})}>{langs.slice(1).map(x=><option value={x[0]} key={x[0]}>{x[1]}</option>)}</select></label>
              <label>Script<select value={settings.script_mode} onChange={e=>setSettings({...settings,script_mode:e.target.value})}><option value="roman">Roman / English letters</option><option value="native">Native script</option></select></label>
            </div>
            <div className="modeScroll">{modes.map(m=><button className={settings.roast_mode===m?'mode selected':'mode'} onClick={()=>setSettings({...settings,roast_mode:m})} key={m}>{m}</button>)}</div>
            <div className="composerFoot"><span className="hint">Ctrl/⌘ + Enter to generate</span><div><button className="ghost" onClick={()=>{setMsg('');setReply('');setMeaning('')}}>Clear</button><button className="primary" onClick={roast} disabled={loading||busy||!msg.trim()||settings.emergency_stop}><Icon name="bolt"/>{loading?'Thinking…':'Generate roast'}</button></div></div>
          </div>

          <div className="sideStack">
            <div className="card controlCard">
              <div className="cardHead"><div><span className="kicker">ROAST ENGINE</span><h3>Personality</h3></div><span className="score">{settings.intensity}/10</span></div>
              <input className="range" aria-label="Roast intensity" type="range" min="1" max="10" value={settings.intensity} onChange={e=>setSettings({...settings,intensity:+e.target.value})}/>
              <div className="rangeLabels"><span>Playful</span><span>Ruthless</span></div>
              <label>Profanity<select value={settings.profanity_level} onChange={e=>setSettings({...settings,profanity_level:e.target.value})}><option value="off">Off</option><option value="light">Light</option><option value="heavy">Heavy</option></select></label>
              <label>Custom voice<textarea className="smallArea" value={settings.custom_instructions} onChange={e=>setSettings({...settings,custom_instructions:e.target.value})} placeholder="witty, short, Gen-Z, dry…"/></label>
              <button className="secondary full" onClick={save} disabled={busy||loading}>Save preferences</button>
            </div>
            <div className="card quickCard"><span className="kicker">QUICK MODES</span><div className="quickGrid">{[['funny','😂'],['savage','🔥'],['sarcastic','😏'],['intelligent','🧠']].map(([m,emoji])=><button onClick={()=>setSettings({...settings,roast_mode:m})} key={m}><span>{emoji}</span>{m}</button>)}</div></div>
          </div>
        </div>

        {(reply||loading) && <div className="resultGrid">
          <div className="card resultCard"><div className="resultHead"><span className="kicker">ROAST GENERATED</span><button className="copy" disabled={!reply} onClick={copyReply}>Copy</button></div><div className={loading?'reply loading':'reply'}>{loading?'Generating a sharp comeback…':reply}</div><div className="resultMeta"><span>{resultMeta?.reply_language}</span><span>{resultMeta?.script_mode}</span><span>{resultMeta?.mode} • {resultMeta?.intensity}/10</span></div></div>
          <div className="card meaningCard"><span className="kicker">ENGLISH MEANING</span><p>{loading?'Waiting for the same Gemini response…':meaning}</p><div className="fastNote"><Icon name="bolt"/> One AI pass for reply + meaning</div></div>
        </div>}
      </div>}

      {tab==='conversations' && <div className="pageGrid"><div className="card listCard"><div className="cardHead"><div><span className="kicker">RECENT CHATS</span><h2>Your conversations</h2></div><button className="dangerText" onClick={clearHistory} disabled={busy}>Clear all</button></div>{convos.length===0?<Empty text="No conversations yet. Generate a roast to start one."/>:convos.map((c,i)=><button className="conversation" key={i} onClick={()=>openConversation(c)}><div className="platformIcon">{c.platform==='local'?'✦':'◉'}</div><div><b>{c.sender_name||'Conversation'}</b><p>{c.last_message}</p></div><time>{new Date(c.last_time).toLocaleString()}</time></button>)}</div><div className="card previewCard"><span className="kicker">CONVERSATION THREAD</span><h2>{thread}</h2>{hasOlder&&<button className="secondary full" onClick={loadOlder} disabled={busy}>{busy?'Loading…':'Load older messages'}</button>}{messages.length===0?<Empty text="Your Roast Me messages will appear here."/>:<div className="thread">{messages.map((m,i)=><div className={m.direction==='outgoing'?'bubble out':'bubble'} key={m.id}>{m.text}</div>)}</div>}</div></div>}

      {tab==='activity' && <div className="pageGrid"><div className="card listCard"><div className="cardHead"><div><span className="kicker">SYSTEM LOG</span><h2>Activity</h2></div><span className="liveBadge"><i/> Live</span></div>{activities.length===0?<Empty text="Nothing has happened yet."/>:<div>{activities.map((a,i)=><div className="activity" key={i}><span className="activityDot"/><div><b>{a.category}</b><p>{a.message}</p></div><time>{new Date(a.timestamp).toLocaleTimeString()}</time></div>)}</div>}</div><div className="card statCard"><span className="kicker">HEALTH</span><div className="bigStat">{connected&&health.gemini?'CONFIGURED':'—'}</div><p>Gemini configuration</p><div className="healthRow"><span>WhatsApp</span><b className={health.whatsapp?'ok':''}>{health.whatsapp?'Configured':'Setup needed'}</b></div><div className="healthRow"><span>Instagram</span><b className={health.instagram?'ok':''}>{health.instagram?'Configured':'Setup needed'}</b></div></div></div>}

      {tab==='platforms' && <div className="pageGrid"><div className="card listCard"><div className="kicker">CONNECT YOUR SOCIALS</div><h2>Delivery channels</h2><p className="muted">Only official platform APIs are used. Keep dry-run on until your Meta app is configured.</p>{[['Instagram','instagram','View messages and account events'],['WhatsApp','whatsapp','Receive and send supported messages'],['Facebook Messenger','facebook','Reply to messages sent to your Facebook Page']].map(([name,key,desc])=><div className="platformRow" key={key}><div className="platformBrand">{key==='instagram'?'◎':'◉'}</div><div><b>{name}</b><small>{desc}</small></div><span className={health[key]?'connected':'pending'}>{health[key]?'Credentials set':'Setup needed'}</span><button onClick={()=>{setTab('settings');setNotice('Configure platform credentials in the backend Render environment')}}>Configure</button></div>)}<div className="platformRow"><div className="platformBrand">◉</div><div><b>Snapchat</b><small>Official brand–creator collaboration API. Requires Snapchat approval; ordinary friend DMs are not supported.</small></div><span className="pending">Approval required</span></div>{authMode==='owner'&&<SnapchatCollaboration request={request} onError={setNotice}/>}</div><div className="card statCard"><span className="kicker">DELIVERY SAFETY</span><h3>Dry-run</h3><p className="muted">Replies are generated and logged without being sent while this is enabled.</p><div className="settingRow"><span>Dry-run mode</span><button className={settings.dry_run?'switch on':'switch'} aria-label="Dry-run mode" aria-pressed={settings.dry_run} onClick={()=>setSettings({...settings,dry_run:!settings.dry_run})}><i/></button></div><button className="secondary full" onClick={save} disabled={busy||loading}>Save delivery settings</button></div></div>}

      {tab==='settings' && <div className="settingsGrid">
        <div className="card settingsCard"><div className="kicker">ROAST ENGINE</div>{authMode!=='owner'&&<><h3>Link your Google account</h3><p className="muted">Use the Google account matching your signed-in email.</p><GoogleSignIn link request={request} onSuccess={data=>{setToken(data.token);setNotice('Google account linked')}} onError={setNotice}/></>}<h2>Default behavior</h2><div className="formGrid"><label>AI provider<select value={health.provider||'gemini'} disabled><option>gemini</option><option>ollama</option></select></label><label>Default mode<select value={settings.roast_mode} onChange={e=>setSettings({...settings,roast_mode:e.target.value})}>{modes.map(m=><option key={m}>{m}</option>)}</select></label><label>Reply delay (seconds)<input type="number" min="0" max="60" value={settings.reply_delay_seconds} onChange={e=>setSettings({...settings,reply_delay_seconds:+e.target.value})}/></label><label>Cooldown (seconds)<input type="number" min="0" max="3600" value={settings.cooldown_seconds} onChange={e=>setSettings({...settings,cooldown_seconds:+e.target.value})}/></label></div><button className="primary" onClick={save} disabled={busy||loading}>Save settings</button></div>
        <div className="card settingsCard"><div className="kicker">DELIVERY</div><h2>Safety & platforms</h2><div className="settingRow"><span>Dry-run mode</span><button className={settings.dry_run?'switch on':'switch'} aria-label="Dry-run mode" aria-pressed={settings.dry_run} onClick={()=>setSettings({...settings,dry_run:!settings.dry_run})}><i/></button></div><div className="settingRow"><span>WhatsApp bot</span><button className={settings.whatsapp_enabled?'switch on':'switch'} aria-label="WhatsApp bot" aria-pressed={settings.whatsapp_enabled} onClick={()=>setSettings({...settings,whatsapp_enabled:!settings.whatsapp_enabled})}><i/></button></div><div className="settingRow"><span>Instagram bot</span><button className={settings.instagram_enabled?'switch on':'switch'} aria-label="Instagram bot" aria-pressed={settings.instagram_enabled} onClick={()=>setSettings({...settings,instagram_enabled:!settings.instagram_enabled})}><i/></button></div><div className="settingRow"><span>Facebook Messenger bot</span><button className={settings.facebook_enabled?'switch on':'switch'} aria-label="Facebook Messenger bot" aria-pressed={settings.facebook_enabled} onClick={()=>setSettings({...settings,facebook_enabled:!settings.facebook_enabled})}><i/></button></div><div className="settingRow"><span>Max reply length</span><input className="inlineInput" type="number" min="50" max="1000" value={settings.max_reply_length} onChange={e=>setSettings({...settings,max_reply_length:+e.target.value})}/></div><button className="secondary full" onClick={save} disabled={busy||loading}>Save delivery settings</button></div>
        <div className="card settingsCard wide"><div className="kicker">ACCOUNT CONNECTION</div><h2>Platform configuration</h2><p className="muted">Configure credentials in the backend environment. Status reflects configuration; live verification requires a successful provider request. The browser never receives API secrets.</p><div className="envGrid"><div><b>Gemini</b><span className={health.gemini?'okPill':'pendingPill'}>{health.gemini?'Configured':'Missing key'}</span></div><div><b>WhatsApp</b><span className={health.whatsapp?'okPill':'pendingPill'}>{health.whatsapp?'Configured':'Not configured'}</span></div><div><b>Instagram</b><span className={health.instagram?'okPill':'pendingPill'}>{health.instagram?'Configured':'Not configured'}</span></div></div></div>
      </div>}
    </section>
  </main>
}

function Empty({text}:{text:string}) { return <div className="empty"><div className="emptyMark"><Logo/></div><p>{text}</p></div> }
