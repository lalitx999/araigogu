/**
 * Arai Go Gu - chat app controller.
 * Guests: free trial (quota shown, images and history need an account).
 * Members: saved chats; the first message of a new chat creates it.
 * Everything the AI or a user wrote is escaped before it touches innerHTML.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const body = document.body;
    const cfg = {
        guest: body.dataset.guest === "1",
        sessionId: body.dataset.sessionId || "",
        language: body.dataset.language || "ja",
        difficulty: body.dataset.difficulty || "n5",
        locked: body.dataset.locked === "1",
        sendNewUrl: body.dataset.sendNewUrl,
        guestResetUrl: body.dataset.guestResetUrl,
        homeUrl: body.dataset.homeUrl,
    };
    const { post } = window.AGG;  // shared helpers from app.js
    const BOT_AVATAR = body.dataset.botAvatar;

    const app = $("app"), stage = $("stage"), thread = $("thread"), welcome = $("welcome");
    const composer = $("composer"), input = $("input"), sendBtn = $("sendBtn");
    const fileInput = $("fileInput"), attach = $("attach");
    let imageFile = null, sending = false;
    let mode = { provider: "groq", model: "openai/gpt-oss-120b" };

    // ---------- safe markdown ----------
    function escapeHtml(s) {
        return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function inline(s) {
        return s
            .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    }

    function renderMarkdown(raw) {
        const keep = [];
        const stash = (html) => "\u0000" + (keep.push(html) - 1) + "\u0000";
        let text = String(raw || "").replace(/\r\n/g, "\n");
        text = text.replace(/```[\w-]*\n([\s\S]*?)```/g, (_, code) => stash("<pre><code>" + escapeHtml(code) + "</code></pre>"));
        text = text.replace(/`([^`\n]+)`/g, (_, code) => stash("<code>" + escapeHtml(code) + "</code>"));
        text = escapeHtml(text);

        const out = [];
        const lines = text.split("\n");
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            let m;
            if (/^\s*\|.*\|\s*$/.test(line)) {             // table
                const rows = [];
                while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++].trim());
                i--;
                const cells = (r) => r.slice(1, -1).split("|").map((c) => inline(c.trim()));
                const bodyRows = rows.filter((r, idx) => idx > 0 && !/^\|[\s:|-]+\|$/.test(r));
                out.push("<table><thead><tr>" + cells(rows[0]).map((c) => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>" +
                    bodyRows.map((r) => "<tr>" + cells(r).map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
            } else if ((m = line.match(/^\s*[-*]\s+(.*)$/))) { // bullet list
                const items = [];
                while (i < lines.length && (m = lines[i].match(/^\s*[-*]\s+(.*)$/))) { items.push("<li>" + inline(m[1]) + "</li>"); i++; }
                i--;
                out.push("<ul>" + items.join("") + "</ul>");
            } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) { // numbered list
                const items = [];
                while (i < lines.length && (m = lines[i].match(/^\s*\d+[.)]\s+(.*)$/))) { items.push("<li>" + inline(m[1]) + "</li>"); i++; }
                i--;
                out.push("<ol>" + items.join("") + "</ol>");
            } else if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {      // --- divider
                out.push("<hr>");
            } else if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
                const level = Math.min(m[1].length + 1, 4);
                out.push("<h" + level + ">" + inline(m[2]) + "</h" + level + ">");
            } else if ((m = line.match(/^&gt;\s?(.*)$/))) {
                out.push("<blockquote>" + inline(m[1]) + "</blockquote>");
            } else if (line.trim() === "") {
                out.push("");
            } else {
                const para = [line];
                while (i + 1 < lines.length && lines[i + 1].trim() !== "" && !/^(\s*[-*]\s|\s*\d+[.)]\s|#{1,4}\s|&gt;|\s*\|)/.test(lines[i + 1])) para.push(lines[++i]);
                out.push("<p>" + inline(para.join("<br>")) + "</p>");
            }
        }
        return out.join("").replace(/\u0000(\d+)\u0000/g, (_, n) => keep[+n]);
    }

    // ---------- new chat: guests forget the trial conversation (members just follow the link) ----------
    $("newChatBtn")?.addEventListener("click", (e) => {
        if (!cfg.guest) return;
        e.preventDefault();
        post(cfg.guestResetUrl).then(() => { window.location.href = cfg.homeUrl; });
    });

    // ---------- language / level picker ----------
    const LEVELS_JA = [["n5", "N5"], ["n4", "N4"], ["n3", "N3"], ["n2", "N2"], ["n1", "N1"]];
    const LEVELS = [["beginner", "เริ่มต้น"], ["intermediate", "กลาง"], ["advanced", "สูง"]];

    function renderLevels() {
        const seg = $("levelSeg");
        if (!seg) return;
        const list = cfg.language === "ja" ? LEVELS_JA : LEVELS;
        if (!list.some(([v]) => v === cfg.difficulty)) cfg.difficulty = list[0][0];
        seg.innerHTML = "";
        list.forEach(([value, label]) => {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = label;
            b.className = value === cfg.difficulty ? "on" : "";
            b.addEventListener("click", () => { cfg.difficulty = value; renderLevels(); });
            seg.appendChild(b);
        });
        $("levelLabel").textContent = (list.find(([v]) => v === cfg.difficulty) || list[0])[1];
    }
    renderLevels();

    $("langList")?.addEventListener("click", (e) => {
        const opt = e.target.closest(".lang-opt");
        if (!opt) return;
        cfg.language = opt.dataset.code;
        document.querySelectorAll(".lang-opt").forEach((o) => o.classList.toggle("active", o === opt));
        $("langLabel").textContent = opt.textContent.trim();
        renderLevels();
    });
    $("langSearch")?.addEventListener("input", (e) => {
        const q = e.target.value.trim().toLowerCase();
        document.querySelectorAll(".lang-opt").forEach((o) => {
            o.hidden = q && !o.textContent.toLowerCase().includes(q) && !o.dataset.code.includes(q);
        });
        document.querySelectorAll(".lang-divider").forEach((d) => { d.hidden = !!q; });
    });

    function lockPicker() {
        if (cfg.locked) return;
        cfg.locked = true;
        const btn = $("langPickerBtn");
        if (!btn) return;
        bootstrap.Dropdown.getInstance(btn)?.hide();
        btn.disabled = true;
        btn.title = "เริ่มแชทใหม่เพื่อเปลี่ยนภาษา";
        const icon = btn.querySelector(".bi-chevron-down");
        if (icon) icon.className = "bi bi-lock";
    }

    // ---------- answer mode (members) ----------
    document.querySelectorAll(".mode-opt").forEach((opt) => opt.addEventListener("click", () => {
        mode = { provider: opt.dataset.provider, model: opt.dataset.model };
        document.querySelectorAll(".mode-opt").forEach((o) => o.classList.toggle("active", o === opt));
        $("modeIcon").className = "bi " + opt.dataset.icon;
        $("modeLabel").textContent = opt.dataset.label;
    }));

    // ---------- composer ----------
    function refreshSend() { sendBtn.disabled = sending || (!input.value.trim() && !imageFile); }
    function grow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 200) + "px"; }

    input.addEventListener("input", () => { grow(); refreshSend(); });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            if (!sendBtn.disabled) composer.requestSubmit();
        }
    });

    function showJoin() {
        const el = $("joinModal");
        if (el) bootstrap.Modal.getOrCreateInstance(el).show();
    }

    function setImage(file) {
        if (!file) return;
        if (cfg.guest) { showJoin(); return; }
        if (!file.type.startsWith("image/")) return;
        if (file.size > 10 * 1024 * 1024) { window.alert("ไฟล์รูปภาพใหญ่เกินไป (ไม่เกิน 10MB)"); return; }
        imageFile = file;
        const reader = new FileReader();
        reader.onload = (ev) => {
            $("attachThumb").src = ev.target.result;
            $("attachName").textContent = file.name || "รูปจากคลิปบอร์ด";
            attach.hidden = false;
            refreshSend();
        };
        reader.readAsDataURL(file);
    }
    function clearImage() { imageFile = null; fileInput.value = ""; attach.hidden = true; refreshSend(); }

    $("attachBtn").addEventListener("click", () => (cfg.guest ? showJoin() : fileInput.click()));
    fileInput.addEventListener("change", () => setImage(fileInput.files[0]));
    $("attachClear").addEventListener("click", clearImage);
    input.addEventListener("paste", (e) => {
        const item = [...(e.clipboardData?.items || [])].find((it) => it.kind === "file" && it.type.startsWith("image/"));
        if (item) { e.preventDefault(); setImage(item.getAsFile()); }
    });

    // speech to text (Thai)
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    const mic = $("micBtn");
    if (!Speech) mic.hidden = true;
    else {
        const rec = new Speech();
        let on = false;
        rec.lang = "th-TH";
        rec.interimResults = false;
        rec.onresult = (e) => { input.value = (input.value ? input.value + " " : "") + e.results[0][0].transcript; grow(); refreshSend(); };
        rec.onend = rec.onerror = () => { on = false; mic.classList.remove("recording"); };
        mic.addEventListener("click", () => {
            if (on) { rec.stop(); return; }
            on = true; mic.classList.add("recording"); rec.start();
        });
    }

    // topics: sidebar links and welcome cards fill the composer instead of navigating
    function useTopic(prompt, needsImage) {
        app.classList.remove("side-open");
        if (needsImage) {
            if (cfg.guest) { showJoin(); return; }
            fileInput.click();
        }
        input.value = prompt || "";
        grow(); refreshSend();
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    }
    document.querySelectorAll(".topic-btn").forEach((btn) => btn.addEventListener("click", (e) => {
        e.preventDefault();
        useTopic(btn.dataset.prompt, btn.dataset.needsImage === "1");
    }));
    // arriving from another page via /?topic=key, or shared into the installed app (?text= / ?title= / ?url=)
    const params = new URLSearchParams(window.location.search);
    const shared = [params.get("title"), params.get("text"), params.get("url")].filter(Boolean).join("\n").trim();
    if (shared && !cfg.locked) {
        window.history.replaceState(null, "", window.location.pathname);
        useTopic(shared.slice(0, 2000), false);
    } else if (params.get("source")) {
        window.history.replaceState(null, "", window.location.pathname);
    }
    const topicKey = params.get("topic");
    if (topicKey) {
        const link = document.querySelector('.side-item.topic-btn[href$="topic=' + CSS.escape(topicKey) + '"]');
        window.history.replaceState(null, "", window.location.pathname);
        if (link && !cfg.locked) useTopic(link.dataset.prompt, false);
    }

    // ---------- rendering ----------
    function scrollDown() { stage.scrollTop = stage.scrollHeight; }

    function addUser(text, imgSrc) {
        welcome.hidden = true;
        const row = document.createElement("div");
        row.className = "msg msg-user";
        const bubble = document.createElement("div");
        bubble.className = "bubble";
        if (imgSrc) {
            const img = document.createElement("img");
            img.src = imgSrc; img.className = "msg-img"; img.alt = "ภาพที่แนบ";
            bubble.appendChild(img);
        }
        if (text) {
            const div = document.createElement("div");
            div.textContent = text;           // textContent: never interpreted as HTML
            div.style.whiteSpace = "pre-wrap";
            bubble.appendChild(div);
        }
        row.appendChild(bubble);
        thread.appendChild(row);
        scrollDown();
    }

    function botShell(extraClass) {
        const row = document.createElement("div");
        row.className = "msg msg-bot" + (extraClass ? " " + extraClass : "");
        const img = document.createElement("img");
        img.src = BOT_AVATAR; img.className = "bot-avatar"; img.alt = "พี่ริว";
        const bodyEl = document.createElement("div");
        bodyEl.className = "bot-body";
        row.append(img, bodyEl);
        thread.appendChild(row);
        return { row, bodyEl };
    }

    function addTyping() {
        const { row, bodyEl } = botShell("is-typing");
        bodyEl.innerHTML = '<div class="typing" aria-label="พี่ริวกำลังพิมพ์"><span></span><span></span><span></span></div>';
        scrollDown();
        return row;
    }

    const ACTIONS = '<div class="msg-actions">' +
        '<button type="button" class="act" data-act="copy" title="คัดลอก" aria-label="คัดลอก"><i class="bi bi-copy"></i></button>' +
        '<button type="button" class="act" data-act="speak" title="ฟังเสียง" aria-label="ฟังเสียง"><i class="bi bi-volume-up"></i></button>' +
        '<button type="button" class="act" data-act="simplify" title="อธิบายให้ง่ายขึ้น" aria-label="อธิบายให้ง่ายขึ้น"><i class="bi bi-lightbulb"></i></button>' +
        "</div>";

    function addBot(text, isError) {
        const { bodyEl } = botShell(isError ? "msg-error" : "");
        const md = document.createElement("div");
        md.className = "md";
        md.dataset.raw = encodeURIComponent(text);
        md.innerHTML = renderMarkdown(text);
        bodyEl.appendChild(md);
        if (!isError) bodyEl.insertAdjacentHTML("beforeend", ACTIONS);
        scrollDown();
    }

    document.querySelectorAll(".md[data-raw]").forEach((el) => { el.innerHTML = renderMarkdown(decodeURIComponent(el.dataset.raw)); });
    if (thread.children.length) welcome.hidden = true;
    scrollDown();

    thread.addEventListener("click", (e) => {
        const btn = e.target.closest(".act");
        if (!btn) return;
        const raw = decodeURIComponent(btn.closest(".bot-body").querySelector(".md").dataset.raw || "");
        if (btn.dataset.act === "copy") {
            navigator.clipboard?.writeText(raw).then(() => {
                const i = btn.querySelector("i");
                i.className = "bi bi-check2";
                setTimeout(() => { i.className = "bi bi-copy"; }, 1600);
            });
        } else if (btn.dataset.act === "speak" && "speechSynthesis" in window) {
            speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(raw.replace(/[*#`_~|>\[\]]/g, "").slice(0, 600));
            const map = { ja: "ja-JP", en: "en-US", zh: "zh-CN", ko: "ko-KR", fr: "fr-FR", de: "de-DE", es: "es-ES" };
            u.lang = map[cfg.language] || "th-TH";
            speechSynthesis.speak(u);
        } else if (btn.dataset.act === "simplify") {
            input.value = "ช่วยอธิบายคำตอบล่าสุดให้เข้าใจง่ายขึ้นอีกหน่อย พร้อมยกตัวอย่างครับ";
            refreshSend();
            composer.requestSubmit();
        }
    });

    // ---------- quota ----------
    function updateQuota(q) {
        if (!q) return;
        if (cfg.guest) {
            ["quotaRemaining", "quotaRemainingInline"].forEach((id) => { const el = $(id); if (el) el.textContent = q.remaining; });
            const bar = $("quotaBar");
            if (bar && q.limit) bar.style.width = Math.min(100, (q.used / q.limit) * 100) + "%";
        } else if ($("quotaUsed")) {
            $("quotaUsed").textContent = q.used;
        }
        if (q.limit && q.remaining === 0) { composer.hidden = true; $("limitPanel").hidden = false; }
    }

    function addHistoryItem(session) {
        const list = $("historyList");
        if (!list) return;
        $("historyEmpty")?.remove();
        const a = document.createElement("a");
        a.href = session.url;
        a.className = "side-item history-item active";
        a.dataset.sessionId = session.id;
        a.title = session.title;
        a.innerHTML = '<i class="bi bi-chat-left"></i><span class="label"></span>' +
            '<button type="button" class="history-del" title="ลบแชทนี้" aria-label="ลบแชทนี้"><i class="bi bi-trash3"></i></button>';
        a.querySelector(".label").textContent = session.title;
        a.querySelector(".history-del").dataset.deleteId = session.id;
        list.prepend(a);
    }

    // ---------- send ----------
    composer.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (sending || (!text && !imageFile)) return;

        const fd = new FormData();
        fd.append("message", text);
        if (imageFile) fd.append("image", imageFile);
        if (!cfg.guest) { fd.append("model_provider", mode.provider); fd.append("model_name", mode.model); }
        if (!cfg.sessionId) { fd.append("language", cfg.language); fd.append("difficulty", cfg.difficulty); }

        addUser(text, imageFile ? $("attachThumb").src : null);
        input.value = ""; grow(); clearImage();
        sending = true; refreshSend();
        lockPicker();
        const typing = addTyping();

        const url = cfg.sessionId ? "/chat/" + encodeURIComponent(cfg.sessionId) + "/send/" : cfg.sendNewUrl;
        post(url, fd).then(({ ok, status, data }) => {
            typing.remove();
            if (!ok) {
                if (data.error === "login_required") showJoin();
                addBot(data.message || data.error || "เชื่อมต่อไม่สำเร็จ ลองใหม่อีกครั้งนะครับ", true);
                if (status === 429) updateQuota(Object.assign({ remaining: 0 }, data.quota || { used: 1, limit: 1 }));
                return;
            }
            addBot(data.reply || "");
            updateQuota(data.quota);
            if (data.session && data.session.created) {
                cfg.sessionId = String(data.session.id);
                body.dataset.sessionId = cfg.sessionId;
                window.history.replaceState(null, "", data.session.url);
                document.title = data.session.title + " - พี่ริว AI ติวเตอร์ภาษา | ARAI GO GU";
                addHistoryItem(data.session);
            }
        }).catch(() => {
            typing.remove();
            addBot("เชื่อมต่อไม่สำเร็จ ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่นะครับ", true);
        }).finally(() => {
            sending = false; refreshSend(); input.focus();
        });
    });

    input.focus();
})();
