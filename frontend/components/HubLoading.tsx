import Logo from './Logo'

export default function HubLoading() {
  return <main className="accessScreen hubScreen"><div className="card accessCard hubCard" role="status" aria-live="polite">
    <div className="hubEmblem"><div className="hubOrbit" aria-hidden="true"/><Logo large/></div>
    <span className="kicker">ROASTAI WORKSPACE</span><h1>Loading bot · Connecting to HUB<span className="hubDots" aria-hidden="true">…</span></h1>
    <p className="muted">Establishing a secure connection to your workspace.</p>
    <div className="hubTrack" aria-hidden="true"><span/></div><small className="hubHint">Your HUB may take a moment to wake up.</small>
  </div></main>
}

