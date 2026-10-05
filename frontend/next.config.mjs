const api = process.env.NEXT_PUBLIC_API_URL;
if (process.env.RENDER === 'true') {
  if (!api || !/^https:\/\/[^/]+\/?$/.test(api) || /localhost|127\.0\.0\.1/.test(api))
    throw new Error('Set NEXT_PUBLIC_API_URL to your public HTTPS backend origin before building on Render');
}
/** @type {import('next').NextConfig} */
const nextConfig={
  poweredByHeader:false,
  async headers(){return [{source:'/:path*',headers:[
    {key:'X-Content-Type-Options',value:'nosniff'},
    {key:'Referrer-Policy',value:'strict-origin-when-cross-origin'},
    {key:'X-Frame-Options',value:'DENY'},
    {key:'Permissions-Policy',value:'camera=(), microphone=(), geolocation=()'}
  ]}]}
};
export default nextConfig;
