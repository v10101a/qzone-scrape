
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (/\.(qq\.com|gtimg\.cn)$/.test(u.hostname)) {
    // serve the mirrored copy if we have it; otherwise FALL BACK to the live
    // network so un-mirrored fonts/assets (e.g. a player's font) still load.
    const local = `assets/bundle/mirror/${u.hostname}${u.pathname}`;
    e.respondWith(
      fetch(local)
        .then((r) => (r.ok ? r : fetch(e.request)))
        .catch(() => fetch(e.request))
    );
  }
  // everything else falls through to the network normally
});
