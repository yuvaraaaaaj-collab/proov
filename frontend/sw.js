const CACHE_NAME = 'trader-pro-v3.14';
const ASSETS = [
  '/',
  '/index.html',
  '/app.js',
  '/manifest.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Never cache API or WebSocket requests
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) {
    return;
  }
  // Network first, fallback to cache
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});

// Background Push Notification handler (Lock screen & sound)
self.addEventListener('push', (e) => {
  let data = { title: '🚨 TraderPro VIP Alert', body: 'New trade entry setup formed!' };
  if (e.data) {
    try {
      data = e.data.json();
    } catch (_) {
      data = { title: '🚨 TraderPro VIP Alert', body: e.data.text() };
    }
  }
  const options = {
    body: data.body || 'New entry order ticket available',
    vibrate: [300, 150, 300, 150, 600],
    tag: 'trade-entry-alert',
    renotify: true,
    requireInteraction: true,
    data: { url: '/' }
  };
  e.waitUntil(self.registration.showNotification(data.title, options));
});

// Click notification to open TraderPro
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});
