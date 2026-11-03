const CACHE = 'chainbrief-shell-v1';
const SHELL = ['./','./index.html','./styles.css','./app.js','./seed-data.js','./manifest.webmanifest','./icons/icon.svg'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (new URL(req.url).pathname.includes('/data/')) {
    event.respondWith(fetch(req).catch(()=>caches.match(req)));
  } else {
    event.respondWith(fetch(req).then(resp=>{if(resp.ok){const copy=resp.clone();caches.open(CACHE).then(c=>c.put(req,copy))}return resp}).catch(()=>caches.match(req)));
  }
});
