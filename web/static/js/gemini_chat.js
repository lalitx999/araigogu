/**
 * Arai Go Gu — Gemini Chat Workspace Controller
 * รองรับการอัปโหลดรูปภาพ, วางรูปภาพจาก Clipboard, แปลงเสียงเป็นข้อความ (STT),
 * สลับโมเดล AI (Gemini 2.5 Flash / Groq / DeepSeek), เรนเดอร์ Markdown, และอ่านออกเสียง (TTS)
 */

(function () {
    "use strict";

    // DOM Elements
    const shell = document.getElementById("gemShell");
    const sideToggleBtn = document.getElementById("sideToggleBtn");
    const mobileSideBtn = document.getElementById("mobileSideBtn");
    const backdrop = document.getElementById("gemBackdrop");
    const chatScroll = document.getElementById("chatScroll");
    const chatContainer = document.getElementById("chatContainer");
    const welcomeStage = document.getElementById("welcomeStage");
    const composerForm = document.getElementById("composerForm");
    const messageInput = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    const fileInput = document.getElementById("fileInput");
    const attachBtn = document.getElementById("attachBtn");
    const attachPreview = document.getElementById("attachPreview");
    const attachThumb = document.getElementById("attachThumb");
    const attachName = document.getElementById("attachName");
    const attachSize = document.getElementById("attachSize");
    const attachDismiss = document.getElementById("attachDismiss");
    const micBtn = document.getElementById("micBtn");
    const modelSelect = document.getElementById("modelSelect");
    const searchInput = document.getElementById("searchChatInput");
    const threadList = document.getElementById("threadList");

    let currentImageFile = null;
    let isSending = false;
    let recognition = null;
    let isRecording = false;

    // --- 1. Markdown Formatter ---
    function escapeHtml(str) {
        return (str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function renderMarkdown(raw) {
        if (!raw) return "";

        // Normalize line breaks
        let text = raw.replace(/\r\n/g, "\n");

        // Code blocks: ```lang ... ```
        const codeBlocks = [];
        text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, function (_, lang, code) {
            const idx = codeBlocks.length;
            codeBlocks.push('<pre><code class="language-' + escapeHtml(lang) + '">' + escapeHtml(code) + '</code></pre>');
            return `__CODE_BLOCK_${idx}__`;
        });

        // Inline code: `...`
        const inlineCodes = [];
        text = text.replace(/`([^`\n]+)`/g, function (_, code) {
            const idx = inlineCodes.length;
            inlineCodes.push('<code>' + escapeHtml(code) + '</code>');
            return `__INLINE_CODE_${idx}__`;
        });

        // Escape remaining text
        text = escapeHtml(text);

        // Headers: ###, ##, #
        text = text.replace(/^### (.*$)/gim, "<h4>$1</h4>");
        text = text.replace(/^## (.*$)/gim, "<h3>$1</h3>");
        text = text.replace(/^# (.*$)/gim, "<h2>$1</h2>");

        // Blockquotes
        text = text.replace(/^\> (.*$)/gim, "<blockquote>$1</blockquote>");

        // Bold & Italic
        text = text.replace(/\*\*\*(.*?)\*\*\*/g, "<strong><em>$1</em></strong>");
        text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");

        // Tables: | col1 | col2 |
        text = text.replace(/((?:\|[^\n]+\|\r?\n)+)/g, function (tableBlock) {
            const rows = tableBlock.trim().split("\n").map(r => r.trim()).filter(Boolean);
            if (rows.length < 2) return tableBlock;
            let html = '<table>';
            rows.forEach((row, rIdx) => {
                if (row.includes("---")) return; // skip delimiter
                const cols = row.split("|").slice(1, -1).map(c => c.trim());
                if (rIdx === 0) {
                    html += '<thead><tr>' + cols.map(c => '<th>' + c + '</th>').join('') + '</tr></thead><tbody>';
                } else {
                    html += '<tr>' + cols.map(c => '<td>' + c + '</td>').join('') + '</tr>';
                }
            });
            html += '</tbody></table>';
            return html;
        });

        // Lists: - item or * item
        text = text.replace(/^\s*[-*]\s+(.*$)/gim, "<li>$1</li>");
        text = text.replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>");

        // Paragraphs & Linebreaks
        const paragraphs = text.split(/\n{2,}/);
        text = paragraphs.map(p => {
            p = p.trim();
            if (!p) return "";
            if (p.startsWith("<h") || p.startsWith("<pre") || p.startsWith("<ul") || p.startsWith("<table") || p.startsWith("<blockquote") || p.startsWith("__CODE_BLOCK_")) {
                return p;
            }
            return '<p>' + p.replace(/\n/g, "<br>") + '</p>';
        }).join("\n");

        // Restore Inline Codes
        inlineCodes.forEach((block, idx) => {
            text = text.replace(`__INLINE_CODE_${idx}__`, block);
        });

        // Restore Code Blocks
        codeBlocks.forEach((block, idx) => {
            text = text.replace(`__CODE_BLOCK_${idx}__`, block);
        });

        return text;
    }

    // --- 2. Sidebar Controls ---
    if (sideToggleBtn) {
        sideToggleBtn.addEventListener("click", () => {
            shell.classList.toggle("side-collapsed");
        });
    }

    if (mobileSideBtn) {
        mobileSideBtn.addEventListener("click", () => {
            shell.classList.add("side-mobile-open");
        });
    }

    if (backdrop) {
        backdrop.addEventListener("click", () => {
            shell.classList.remove("side-mobile-open");
        });
    }

    // Local Search in Sidebar
    if (searchInput && threadList) {
        searchInput.addEventListener("input", (e) => {
            const query = e.target.value.toLowerCase().trim();
            const items = threadList.querySelectorAll(".gem-thread-item");
            items.forEach(item => {
                const title = item.querySelector(".gem-thread-title")?.textContent.toLowerCase() || "";
                item.style.display = title.includes(query) ? "flex" : "none";
            });
        });
    }

    // --- 3. Auto-Grow Textarea ---
    function autoGrow(el) {
        if (!el) return;
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }

    if (messageInput) {
        messageInput.addEventListener("input", function () {
            autoGrow(this);
            if (sendBtn) {
                sendBtn.disabled = !this.value.trim() && !currentImageFile;
            }
        });

        messageInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!sendBtn.disabled && !isSending) {
                    composerForm.dispatchEvent(new Event("submit", { cancelable: true }));
                }
            }
        });

        // Paste Image from Clipboard!
        messageInput.addEventListener("paste", function (e) {
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            for (let item of items) {
                if (item.kind === "file" && item.type.startsWith("image/")) {
                    const file = item.getAsFile();
                    setImageFile(file);
                    break;
                }
            }
        });
    }

    // --- 4. Image Attachment Handler ---
    function setImageFile(file) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) {
            alert("ไฟล์รูปภาพมีขนาดใหญ่เกินไป (กรุณาใช้ขนาดไม่เกิน 10MB)");
            return;
        }
        currentImageFile = file;
        const reader = new FileReader();
        reader.onload = function (e) {
            if (attachThumb) attachThumb.src = e.target.result;
            if (attachName) attachName.textContent = (file.name || "ภาพจาก Clipboard") + " (✨ ส่งให้ Gemini วิเคราะห์ภาพอัตโนมัติ)";
            if (attachSize) attachSize.textContent = (file.size / 1024).toFixed(1) + " KB";
            if (attachPreview) attachPreview.style.display = "flex";
            if (sendBtn) sendBtn.disabled = false;
        };
        reader.readAsDataURL(file);
    }

    function clearImageFile() {
        currentImageFile = null;
        if (fileInput) fileInput.value = "";
        if (attachPreview) attachPreview.style.display = "none";
        if (sendBtn && messageInput) {
            sendBtn.disabled = !messageInput.value.trim();
        }
    }

    if (attachBtn && fileInput) {
        attachBtn.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", function () {
            if (this.files && this.files[0]) {
                setImageFile(this.files[0]);
            }
        });
    }

    if (attachDismiss) {
        attachDismiss.addEventListener("click", clearImageFile);
    }

    // --- 5. Speech to Text (Web Speech API) ---
    if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRec();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = "th-TH"; // Default Thai

        recognition.onstart = function () {
            isRecording = true;
            if (micBtn) {
                micBtn.classList.add("recording");
                micBtn.title = "กำลังฟังเสียงของคุณ...";
            }
        };

        recognition.onresult = function (event) {
            const transcript = event.results[0][0].transcript;
            if (messageInput) {
                messageInput.value = (messageInput.value ? messageInput.value + " " : "") + transcript;
                autoGrow(messageInput);
                if (sendBtn) sendBtn.disabled = false;
            }
        };

        recognition.onerror = function () {
            stopRecording();
        };

        recognition.onend = function () {
            stopRecording();
        };
    } else {
        if (micBtn) micBtn.style.display = "none";
    }

    function stopRecording() {
        isRecording = false;
        if (micBtn) {
            micBtn.classList.remove("recording");
            micBtn.title = "กดเพื่อพูดด้วยเสียง";
        }
    }

    if (micBtn) {
        micBtn.addEventListener("click", () => {
            if (!recognition) return;
            if (isRecording) {
                recognition.stop();
            } else {
                recognition.start();
            }
        });
    }

    // --- 6. Scroll to Bottom ---
    function scrollToBottom() {
        if (chatScroll) {
            chatScroll.scrollTop = chatScroll.scrollHeight;
        }
    }

    // --- 7. Append Message to UI ---
    function appendUserMessage(text, imageSrc) {
        if (welcomeStage) welcomeStage.style.display = "none";
        if (chatContainer) chatContainer.style.display = "flex";

        const row = document.createElement("div");
        row.className = "gem-row user";

        let html = '<div class="gem-user-bubble">';
        if (imageSrc) {
            html += `<img src="${imageSrc}" class="gem-user-image" alt="ภาพแนบ" />`;
        }
        if (text) {
            html += `<div>${escapeHtml(text).replace(/\n/g, "<br>")}</div>`;
        }
        html += '</div>';

        row.innerHTML = html;
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function appendTypingIndicator() {
        const row = document.createElement("div");
        row.className = "gem-row bot-typing";
        row.id = "typingIndicator";
        row.innerHTML = `
            <span class="gem-spark"><i class="bi bi-stars"></i></span>
            <div class="gem-typing-dots">
                <span></span><span></span><span></span>
            </div>
        `;
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const el = document.getElementById("typingIndicator");
        if (el) el.remove();
    }

    function appendBotMessage(markdownText, modelName) {
        removeTypingIndicator();

        const row = document.createElement("div");
        row.className = "gem-row";

        const bodyHtml = renderMarkdown(markdownText);
        const escapedRaw = encodeURIComponent(markdownText);

        let badgeHtml = "";
        if (modelName) {
            let label = modelName;
            let icon = "bi-cpu";
            if (modelName.includes("gemini")) {
                label = "Google Gemini 2.5 Flash (วิเคราะห์ภาพ)";
                icon = "bi-image";
            } else if (modelName.includes("gpt-oss") || modelName.includes("groq") || modelName.includes("llama")) {
                label = "Groq (แชทเร็วทันใจ)";
                icon = "bi-lightning-charge";
            } else if (modelName.includes("deepseek")) {
                label = "DeepSeek (วิเคราะห์ไวยากรณ์)";
                icon = "bi-mortarboard";
            }
            badgeHtml = `<div class="mb-1"><span class="badge bg-light text-muted border rounded-pill" style="font-size: 0.72rem; font-weight: 500;"><i class="bi ${icon} me-1 text-primary"></i>${label}</span></div>`;
        }

        row.innerHTML = `
            <span class="gem-spark"><i class="bi bi-stars"></i></span>
            <div class="gem-bot-body">
                ${badgeHtml}
                <div class="gem-rendered-content">${bodyHtml}</div>
                <div class="gem-actions-row">
                    <button type="button" class="gem-act-btn copy-btn" data-text="${escapedRaw}" title="คัดลอกข้อความ">
                        <i class="bi bi-clipboard"></i> <span>คัดลอก</span>
                    </button>
                    <button type="button" class="gem-act-btn tts-btn" data-text="${escapedRaw}" title="อ่านออกเสียง">
                        <i class="bi bi-volume-up"></i> <span>ฟังเสียง</span>
                    </button>
                    <button type="button" class="gem-act-btn simplify-btn" title="อธิบายให้เข้าใจง่ายขึ้น">
                        <i class="bi bi-magic"></i> <span>อธิบายง่ายขึ้น</span>
                    </button>
                </div>
            </div>
        `;

        chatContainer.appendChild(row);
        scrollToBottom();
    }

    // --- 8. Message Action Delegation (Copy, TTS, Simplify) ---
    if (chatContainer) {
        chatContainer.addEventListener("click", function (e) {
            const copyBtn = e.target.closest(".copy-btn");
            if (copyBtn) {
                const text = decodeURIComponent(copyBtn.getAttribute("data-text") || "");
                navigator.clipboard.writeText(text).then(() => {
                    const span = copyBtn.querySelector("span");
                    const icon = copyBtn.querySelector("i");
                    if (span) span.textContent = "คัดลอกแล้ว";
                    if (icon) icon.className = "bi bi-check2 text-success";
                    setTimeout(() => {
                        if (span) span.textContent = "คัดลอก";
                        if (icon) icon.className = "bi bi-clipboard";
                    }, 2000);
                });
                return;
            }

            const ttsBtn = e.target.closest(".tts-btn");
            if (ttsBtn) {
                const text = decodeURIComponent(ttsBtn.getAttribute("data-text") || "");
                if ("speechSynthesis" in window) {
                    window.speechSynthesis.cancel();
                    const cleanText = text.replace(/[*#`_~\[\]]/g, "").slice(0, 400);
                    const utterance = new SpeechSynthesisUtterance(cleanText);
                    const currentLang = window.CURRENT_LANGUAGE || "ja";
                    const langMap = { "ja": "ja-JP", "en": "en-US", "zh": "zh-CN", "ko": "ko-KR" };
                    utterance.lang = langMap[currentLang] || "th-TH";
                    window.speechSynthesis.speak(utterance);
                }
                return;
            }

            const simplifyBtn = e.target.closest(".simplify-btn");
            if (simplifyBtn) {
                if (messageInput) {
                    messageInput.value = "ช่วยอธิบายเนื้อหาเมื่อสักครู่นี้ให้เข้าใจง่ายขึ้นอีกนิดหน่อยสำหรับนักเรียนครับ";
                    autoGrow(messageInput);
                    if (sendBtn) sendBtn.disabled = false;
                    composerForm.dispatchEvent(new Event("submit", { cancelable: true }));
                }
                return;
            }
        });
    }

    // --- 9. Suggestion Chips Handler ---
    window.askSuggestion = function (prompt) {
        if (messageInput) {
            messageInput.value = prompt;
            autoGrow(messageInput);
            if (sendBtn) sendBtn.disabled = false;
            composerForm.dispatchEvent(new Event("submit", { cancelable: true }));
        }
    };

    // --- 10. Form Submit Handler (Send Message) ---
    if (composerForm) {
        composerForm.addEventListener("submit", function (e) {
            e.preventDefault();
            if (isSending) return;

            const text = (messageInput ? messageInput.value : "").trim();
            const file = currentImageFile;

            if (!text && !file) return;

            isSending = true;
            if (sendBtn) sendBtn.disabled = true;

            const sessionId = window.CURRENT_SESSION_ID;
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

            // User image preview url
            let tempImageSrc = null;
            if (file && attachThumb) {
                tempImageSrc = attachThumb.src;
            }

            // Append user bubble immediately
            appendUserMessage(text, tempImageSrc);

            // Clear inputs
            if (messageInput) {
                messageInput.value = "";
                autoGrow(messageInput);
            }
            clearImageFile();

            // Append typing indicator
            appendTypingIndicator();

        // Prepare model choice: If image is attached, auto-route to Gemini!
        let provider, modelName;
        if (file) {
            provider = "gemini";
            modelName = "gemini-2.5-flash";
        } else {
            const selectedModelVal = modelSelect ? modelSelect.value : "groq:openai/gpt-oss-120b";
            [provider, modelName] = selectedModelVal.split(":");
        }

        // Send via FormData
        const formData = new FormData();
        formData.append("message", text);
        formData.append("model_provider", provider || "groq");
        formData.append("model_name", modelName || "openai/gpt-oss-120b");
        if (file) {
            formData.append("image", file);
        }

            const sendUrl = sessionId ? `/chat/${sessionId}/send/` : "/chat/new/";

            fetch(sendUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: formData,
            })
            .then(res => {
                if (!res.ok) {
                    return res.json().then(err => { throw err; });
                }
                return res.json();
            })
            .then(data => {
                if (data.redirect_url || (data.id && !sessionId)) {
                    // Redirect to newly created session
                    window.location.href = data.url || `/chat/${data.id}/`;
                    return;
                }
                const reply = data.reply || data.ai_response || "ขออภัยครับ ไม่ได้รับคำตอบจากระบบ";
                appendBotMessage(reply, data.model_used || modelName);
            })
            .catch(err => {
                removeTypingIndicator();
                const errMsg = err?.error || "เกิดข้อผิดพลาดในการเชื่อมต่อ กรุณาลองใหม่อีกครั้งครับ";
                appendBotMessage(`⚠️ **ขออภัยครับ:** ${errMsg}`);
            })
            .finally(() => {
                isSending = false;
                if (sendBtn && messageInput) {
                    sendBtn.disabled = !messageInput.value.trim() && !currentImageFile;
                }
            });
        });
    }

    // --- 11. Delete Session Handler ---
    window.deleteChatSession = function (sessionId, event) {
        if (event) event.stopPropagation();
        if (!confirm("คุณต้องการลบประวัติการแชทนี้หรือไม่?")) return;

        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
        fetch(`/chat/${sessionId}/delete/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest",
            },
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (window.CURRENT_SESSION_ID == sessionId) {
                    window.location.href = "/chat/";
                } else {
                    const item = document.querySelector(`[data-session-id="${sessionId}"]`);
                    if (item) item.remove();
                }
            }
        });
    };

    // Format all existing messages rendered on page load
    document.querySelectorAll(".gem-rendered-content").forEach(el => {
        const raw = el.getAttribute("data-raw");
        if (raw) {
            el.innerHTML = renderMarkdown(decodeURIComponent(raw));
        }
    });

    scrollToBottom();
})();
