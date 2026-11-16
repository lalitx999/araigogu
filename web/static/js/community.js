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
