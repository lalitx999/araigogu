{% autoescape off %}/* ARAI GO GU service worker (rendered by Django so static URLs carry their content hash). */
"use strict";

const VERSION = "{{ version }}";
const SHELL = "agg-shell-" + VERSION;      // precached app shell, replaced on every deploy that changes it
const RUNTIME = "agg-static-" + VERSION;   // other static files, cached on first use
const PRECACHE = {{ precache_json }};
const OFFLINE_URL = "{{ offline_url }}";
const DEV = {{ debug|yesno:"true,false" }};          // dev server: file names are not hashed, prefer the network

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        const keep = new Set([SHELL, RUNTIME]);
        for (const key of await caches.keys()) {
            if (key.startsWith("agg-") && !keep.has(key)) await caches.delete(key);
        }
        if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
        await self.clients.claim();
    })());
});

self.addEventListener("message", (event) => {
    if (event.data === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") return;                       // never touch POSTs (chat, posts, forms)
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith("/admin/") || url.pathname.startsWith("/media/")) return;

    // Pages: always from the network (they hold personal data, so they are never cached).
    // Offline -> a friendly page instead of the browser error.
    if (request.mode === "navigate") {
        event.respondWith((async () => {
            try {
                const preloaded = await event.preloadResponse;
                return preloaded || await fetch(request);
            } catch (err) {
                return (await caches.match(OFFLINE_URL)) || Response.error();
            }
        })());
        return;
    }

    // Static files have hashed names in production: cache-first is safe.
    if (url.pathname.startsWith("/static/")) {
        event.respondWith((async () => {
            const cached = await caches.match(request);
            if (cached && !DEV) return cached;
            try {
                const response = await fetch(request);
                if (response.ok) (await caches.open(RUNTIME)).put(request, response.clone());
                return response;
            } catch (err) {
                if (cached) return cached;
                throw err;
            }
        })());
    }
    // Everything else (JSON, manifest, sitemap...) goes straight to the network.
});
{% endautoescape %}
