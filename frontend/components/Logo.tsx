export default function Logo({large=false}:{large?:boolean}) {
  return <div className={large ? 'logoWrap large' : 'logoWrap'} aria-label="RoastAI logo">
    <svg viewBox="0 0 64 64" className="logoSvg">
      <defs>
        <linearGradient id="flame" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#ff42e8"/><stop offset=".55" stopColor="#8b3dff"/><stop offset="1" stopColor="#5420ff"/>
        </linearGradient>
      </defs>
      <path fill="url(#flame)" d="M31 5c7 10 2 15 9 19 5-5 8-10 7-15 11 10 13 24 8 35-5 11-15 16-27 14C16 56 9 47 10 35c1-10 7-18 17-25-1 7-1 11 2 15 4-5 4-11 2-20z"/>
      <path fill="#11101c" d="M17 34c7-3 23-3 31 0-2 7-7 10-15 10s-14-3-16-10z"/>
      <path fill="#fff" opacity=".18" d="M18 35c6-2 10-2 13-1-1 3-3 5-7 5-3 0-5-1-6-4zm17-1c5-1 9 0 13 1-1 3-4 4-7 4-3 0-5-2-6-5z"/>
      <path stroke="#17121f" strokeWidth="2.5" strokeLinecap="round" fill="none" d="M25 48c4 3 10 3 14 0"/>
      <circle cx="27" cy="36" r="1.4" fill="#fff"/><circle cx="38" cy="36" r="1.4" fill="#fff"/>
    </svg>
  </div>
}

