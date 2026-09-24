self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

// player SWFs pull shared font SWFs from Tencent; serve the mirrored copy, else live network
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (!/\.(qq\.com|gtimg\.cn)$/.test(u.hostname)) return;
  const local = `../site/assets/bundle/mirror/${u.hostname}${u.pathname}`;
  e.respondWith(
    fetch(local)
      .then((r) => (r.ok ? r : fetch(e.request)))
      .catch(() => fetch(e.request))
  );
});
