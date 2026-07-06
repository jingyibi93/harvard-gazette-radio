const CACHE = "harvard-radio-v34";
const SHELL = [
  "./",
  "./index.html",
  "./fonts/noto-serif-sc-700.css?v=19",
  "./styles.css",
  "./runtime-config.js",
  "./app.js",
  "./manifest.webmanifest",
  "./icon-192.png",
  "./icon-512.png",
  "./apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.mode === "navigate" ||
    url.pathname.endsWith("/index.html") ||
    url.pathname.endsWith(".css") ||
    url.pathname.endsWith("/app.js") ||
    url.pathname.endsWith("/runtime-config.js")
  ) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request).then((cached) => cached || caches.match("./index.html"))),
    );
    return;
  }
  if (url.pathname.endsWith(".m4a")) {
    event.respondWith(fetch(event.request));
    return;
  }
  if (
    (url.pathname.includes("/episodes/") && url.pathname.endsWith(".json")) ||
    (url.pathname.includes("/audio/") && !url.pathname.endsWith(".m4a")) ||
    url.pathname.includes("/images/")
  ) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request)),
    );
    return;
  }
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
