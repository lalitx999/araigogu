/**
 * Arai Go Gu - shared app shell: theme, sidebar, chat history, toast, copy-link, support QR.
 * Page scripts (chat_app.js, community.js) build on window.AGG.
 */
(function () {
    "use strict";

    const root = document.documentElement;
    const body = document.body;
    const $ = (id) => document.getElementById(id);
    const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

    const store = {
        get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
    };

    function post(url, formData) {
        return fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
            body: formData,
            credentials: "same-origin",
        }).then((res) => res.json().catch(() => ({})).then((data) => ({ ok: res.ok, status: res.status, data })));
    }

    let toastTimer = null;
    function toast(text) {
        const el = $("toast");
        if (!el) return;
        el.textContent = text;
        el.classList.add("show");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
    }

    // ---------- theme ----------
    function applyTheme(t) {
        if (t === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", t);
        store.set("agg-theme", t);
        document.querySelectorAll("[data-theme-set]").forEach((b) => b.classList.toggle("on", b.dataset.themeSet === t));
    }
    applyTheme(store.get("agg-theme") || "system");
    document.addEventListener("click", (e) => {
        const set = e.target.closest("[data-theme-set]");
        if (set) { applyTheme(set.dataset.themeSet); return; }
        if (e.target.closest("[data-theme-toggle]")) {
            const dark = root.getAttribute("data-theme") === "dark" ||
                (!root.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
            applyTheme(dark ? "light" : "dark");
        }
    });

    // ---------- sidebar ----------
    const app = $("app");
    $("sideToggle")?.addEventListener("click", () => {
        root.classList.toggle("side-collapsed");
        store.set("agg-side", root.classList.contains("side-collapsed") ? "collapsed" : "open");
    });
    $("mobileMenu")?.addEventListener("click", () => app?.classList.add("side-open"));
    $("backdrop")?.addEventListener("click", () => app?.classList.remove("side-open"));

    $("historySearch")?.addEventListener("input", (e) => {
        const q = e.target.value.trim().toLowerCase();
        document.querySelectorAll(".history-item").forEach((a) => { a.hidden = q && !a.title.toLowerCase().includes(q); });
    });

    $("historyList")?.addEventListener("click", (e) => {
        const del = e.target.closest("[data-delete-id]");
        if (!del) return;
        e.preventDefault();
        e.stopPropagation();
        if (!window.confirm("ลบแชทนี้ใช่ไหม ลบแล้วกู้คืนไม่ได้")) return;
        const id = del.dataset.deleteId;
        post("/chat/" + encodeURIComponent(id) + "/delete/").then(({ ok }) => {
            if (!ok) { toast("ลบไม่สำเร็จ ลองใหม่อีกครั้ง"); return; }
            if (String(body.dataset.sessionId) === String(id)) window.location.href = body.dataset.homeUrl || "/";
            else { del.closest(".history-item")?.remove(); toast("ลบแชทแล้ว"); }
        });
    });

    // dismissible notices
    document.addEventListener("click", (e) => {
        const close = e.target.closest(".notice-close");
        if (close) close.closest(".notice")?.remove();
    });

    // ---------- copy link ----------
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-copy-link]");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const url = new URL(btn.dataset.copyLink || window.location.href, window.location.origin).href;
        (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
            .then(() => toast("คัดลอกลิงก์แล้ว"), () => window.prompt("คัดลอกลิงก์นี้", url));
    });

    // ---------- support QR (library loaded only when the dialog opens) ----------
    function renderQr() {
        const box = $("supportQr");
        if (!box || box.dataset.ready || !window.qrcode) return;
        const qr = window.qrcode(0, "L");
        qr.addData(box.dataset.url);
        qr.make();
        box.innerHTML = qr.createImgTag(5, 0);
        box.dataset.ready = "1";
    }
    $("supportModal")?.addEventListener("show.bs.modal", () => {
        if (window.qrcode) { renderQr(); return; }
        const s = document.createElement("script");
        s.src = body.dataset.qrSrc;
        s.onload = renderQr;
        document.head.appendChild(s);
    });

    window.AGG = { $, csrf, post, toast, store };
})();
