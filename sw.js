const CACHE_NAME = 'upsc-prelims-v1';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './tests/test_manifest.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then((response) => response || fetch(e.request))
  );
});
