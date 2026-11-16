/* Progressive enhancement for the original community pages. Without JS every form still works as a normal submit. */
(function () {
  "use strict";
  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  async function request(url, body) {
    try {
      const res = await fetch(url, {
        method: body ? "POST" : "GET",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() },
        body: body || undefined,
        credentials: "same-origin",
      });
      if (res.redirected) return { ok: false, data: {} };       // e.g. session expired -> let the browser do a normal submit
      let data = {};
      try { data = await res.json(); } catch (_) { return { ok: false, data: {} }; }
      return { ok: res.ok, data: data };
    } catch (_) {
      return { ok: false, data: {} };
    }
  }

  // like / repost / bookmark without reloading the page
  const CLASS_OF = { like: "liked", repost: "reposted", bookmark: "bookmarked" };
  document.addEventListener("submit", async function (e) {
    const form = e.target.closest("form[data-ajax-toggle]");
    if (!form) return;
    e.preventDefault();
    const kind = form.dataset.ajaxToggle;
    const btn = form.querySelector("button");
    btn.disabled = true;
    const r = await request(form.action, new FormData(form));
    btn.disabled = false;
    if (!r.ok) { HTMLFormElement.prototype.submit.call(form); return; }
    btn.classList.toggle(CLASS_OF[kind], r.data.active);
    const icon = btn.querySelector("i");
    if (icon && kind === "like") icon.className = "bi bi-heart" + (r.data.active ? "-fill" : "");
    if (icon && kind === "bookmark") icon.className = "bi bi-bookmark" + (r.data.active ? "-fill" : "");
    const count = btn.querySelector("span");
    if (count) count.textContent = r.data.count;
  });

  // "load more" on the feed
  const more = document.getElementById("loadMoreBtn");
  if (more) {
    more.addEventListener("click", async function () {
      const box = document.getElementById("postsFeed");
      if (!box || !box.dataset.next) return;
      more.disabled = true;
      const r = await request(box.dataset.next);
      more.disabled = false;
      if (!r.ok) return;
      box.insertAdjacentHTML("beforeend", r.data.html);
      box.dataset.next = r.data.next || "";
      document.getElementById("loadMoreWrap").hidden = !r.data.next;
    });
  }

  // whole card opens the post (links, buttons and forms inside keep their own behaviour)
  document.addEventListener("click", function (e) {
    const card = e.target.closest(".post-card[data-href]");
    if (!card || e.target.closest("a, button, form, textarea, input")) return;
    if (window.getSelection && String(window.getSelection())) return;  // selecting text, not clicking
    window.location.href = card.dataset.href;
  });

  // comment button on a feed card opens the quick reply under it
  document.addEventListener("click", function (e) {
    const toggle = e.target.closest("[data-reply-toggle]");
    if (!toggle) return;
    const form = document.getElementById("reply-" + toggle.dataset.replyToggle);
    if (!form) return;
    e.preventDefault();
    form.hidden = !form.hidden;
    if (!form.hidden) form.querySelector("textarea").focus();
  });

  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-focus]");
    if (btn) document.querySelector(btn.dataset.focus)?.focus();
  });

  // textareas grow with their content; Enter sends, Shift+Enter adds a line (not the main post box)
  document.addEventListener("input", function (e) {
    const t = e.target.closest(".auto-expand-textarea");
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 240) + "px";
    if (t.id === "postContent") {
      const c = document.getElementById("postCount");
      if (c) c.textContent = t.value.length + "/1000";
    }
  });
  document.addEventListener("keydown", function (e) {
    const t = e.target.closest(".auto-expand-textarea");
    if (!t || t.id === "postContent" || e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (t.value.trim()) t.form.requestSubmit();
  });
  document.addEventListener("submit", function (e) {
    const btn = e.target.querySelector('button[type="submit"]');
    if (btn && !e.target.matches("[data-ajax-toggle]")) setTimeout(function () { btn.disabled = true; }, 0);
  });

  // P'Ryu's comment is generated after the redirect, so the author never waits for the AI
  const ryuUrl = document.body.dataset.ryuUrl;
  if (ryuUrl) {
    const postId = document.body.dataset.ryuPost;
    history.replaceState(null, "", location.pathname);
    request(ryuUrl, new FormData()).then(function (r) {
      if (!r.ok || !r.data.created) return;
      document.querySelectorAll('.js-comment-count[data-post-id="' + postId + '"]').forEach(function (el) {
        el.textContent = r.data.count;
      });
    });
  }
})();
