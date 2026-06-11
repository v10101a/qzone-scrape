// Service worker — the Flashpoint "replay archived deps at their original URLs"
// trick, browser-native. Any request a SWF makes to a Tencent CDN host is served
// from the local ./mirror/<host>/<path> copy instead of the live/dead origin, so
// the bundle runs fully self-contained (works offline, no Tencent dependency).
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (/\.(qq\.com|gtimg\.cn)$/.test(u.hostname)) {
    // strip query (mirror stores by path only) and serve the local copy
    const local = `mirror/${u.hostname}${u.pathname}`;
    e.respondWith(
      fetch(local)
        .then((r) => (r.ok ? r : new Response("", { status: 404 })))
        .catch(() => new Response("", { status: 404 }))
    );
  }
  // everything else falls through to the network normally
});
