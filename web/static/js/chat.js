/* ============================================================
   CV2CC — AI-Guided Chat Interface
   Drives the conversational CV2 form-filling experience.
   ============================================================ */

"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let conversationHistory = [];  // {role: "user"|"assistant", content: "..."}
let collectedData       = null; // populated once AI returns <cv2_data>
let isSending           = false;

// Progress topic keywords — used to light up sidebar items
const PROGRESS_KEYWORDS = {
  "prog-project":        ["project name", "project number", "permit number"],
  "prog-credentials":    ["architect", "license", "engineer", "prepared by"],
  "prog-location":       ["address", "city", "county", "state", "parcel"],
  "prog-classification": ["occupancy", "construction type", "risk category", "zoning"],
  "prog-dimensions":     ["stories", "height", "floor area", "footprint"],
  "prog-rooms":          ["room", "space", "area"],
  "prog-systems":        ["sprinkler", "fire alarm", "nfpa", "suppression"],
  "prog-ada":            ["ada", "accessible", "parking"],
  "prog-energy":         ["energy", "climate zone", "ashrae", "title 24"],
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

const messagesEl  = document.getElementById("chat-messages");
const inputEl     = document.getElementById("chat-input");
const sendBtn     = document.getElementById("chat-send");
const readyBar    = document.getElementById("chat-ready-bar");
const generateBtn = document.getElementById("btn-chat-generate");
const generateLbl = document.getElementById("generate-label");
const generateErr = document.getElementById("generate-error");

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Render basic markdown: **bold**, *italic*, `code`, line breaks */
function renderMarkdown(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g,     "<em>$1</em>")
    .replace(/`(.+?)`/g,       "<code>$1</code>")
    .replace(/\n/g,            "<br>");
}

function appendMessage(role, text, opts = {}) {
  const wrap = document.createElement("div");
  wrap.className = `chat-bubble chat-bubble--${role}`;
  if (opts.id) wrap.id = opts.id;

  const avatar = document.createElement("div");
  avatar.className = "chat-avatar";
  avatar.textContent = role === "assistant" ? "AI" : "You";

  const body = document.createElement("div");
  body.className = "chat-bubble-body";
  if (opts.loading) {
    body.innerHTML = `
      <div class="chat-typing">
        <span class="chat-dot"></span>
        <span class="chat-dot"></span>
        <span class="chat-dot"></span>
      </div>`;
  } else {
    body.innerHTML = renderMarkdown(text);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(body);
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return { wrap, body };
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ---------------------------------------------------------------------------
// Progress sidebar
// ---------------------------------------------------------------------------

const progressMet = new Set();

function updateProgress(assistantText) {
  const lower = assistantText.toLowerCase();
  Object.entries(PROGRESS_KEYWORDS).forEach(([id, keywords]) => {
    if (progressMet.has(id)) return;
    if (keywords.some(kw => lower.includes(kw))) {
      progressMet.add(id);
      const item = document.getElementById(id);
      if (item) item.classList.add("done");
    }
  });
}

function markAllProgress() {
  Object.keys(PROGRESS_KEYWORDS).forEach(id => {
    progressMet.add(id);
    const item = document.getElementById(id);
    if (item) item.classList.add("done");
  });
}

// ---------------------------------------------------------------------------
// Send a message
// ---------------------------------------------------------------------------

async function sendMessage(text) {
  if (isSending || !text.trim()) return;
  isSending = true;
  setSendState(false);

  // Show user bubble
  appendMessage("user", text.trim());
  conversationHistory.push({ role: "user", content: text.trim() });
  inputEl.value = "";
  autoResize();

  // Show typing indicator
  const { wrap: typingWrap, body: typingBody } = appendMessage("assistant", "", { loading: true, id: "chat-typing-indicator" });

  try {
    const res  = await fetch("/api/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ messages: conversationHistory }),
    });
    const data = await res.json();

    // Replace typing bubble with real reply
    typingWrap.remove();

    if (!data.ok) {
      appendMessage("assistant", "Sorry, I ran into an error: " + escHtml(data.error));
    } else {
      appendMessage("assistant", data.message);
      conversationHistory.push({ role: "assistant", content: data.message });
      updateProgress(data.message);

      // If AI returned structured data, store it and show generate button
      if (data.ready && data.cv2_data) {
        collectedData = data.cv2_data;
        markAllProgress();
        readyBar.style.display = "block";
        scrollToBottom();

        // Log Statsig event
        if (window.statsig && typeof statsig.logEvent === "function") {
          statsig.logEvent("chat_form_ready");
        }
      }
    }
  } catch (err) {
    typingWrap.remove();
    appendMessage("assistant", "Network error — please try again. (" + err.message + ")");
  } finally {
    isSending = false;
    setSendState(true);
    inputEl.focus();
  }
}

function setSendState(enabled) {
  sendBtn.disabled  = !enabled;
  inputEl.disabled  = !enabled;
}

// ---------------------------------------------------------------------------
// Generate PDF from collected data
// ---------------------------------------------------------------------------

generateBtn.addEventListener("click", async () => {
  if (!collectedData) return;

  generateBtn.disabled = true;
  generateLbl.textContent = "Generating PDF…";
  generateErr.style.display = "none";

  // Log Statsig event
  if (window.statsig && typeof statsig.logEvent === "function") {
    statsig.logEvent("pdf_generated", "chat");
  }

  try {
    const res  = await fetch("/api/generate", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(collectedData),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);

    const name = collectedData.project_name || "cv2_form";
    window.location.href = `/download/${data.token}?name=${encodeURIComponent(name)}`;

  } catch (err) {
    generateErr.textContent = "Error: " + err.message;
    generateErr.style.display = "block";
  } finally {
    generateBtn.disabled = false;
    generateLbl.textContent = "↓ Generate CV2 PDF Form";
  }
});

// ---------------------------------------------------------------------------
// Input events
// ---------------------------------------------------------------------------

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
}

inputEl.addEventListener("input", autoResize);

inputEl.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});

sendBtn.addEventListener("click", () => sendMessage(inputEl.value));

// ---------------------------------------------------------------------------
// Kick off conversation with a welcome message from the AI
// ---------------------------------------------------------------------------

async function startConversation() {
  setSendState(false);

  // This seed message MUST be stored in conversationHistory so subsequent
  // user replies produce a valid user→assistant→user→... alternating sequence.
  // The Anthropic API rejects any message list that doesn't start with "user".
  const seedMsg = {
    role: "user",
    content: "Hi — please start the CV2 form interview. Welcome me briefly (1–2 sentences) then ask for the project name.",
  };

  try {
    const res  = await fetch("/api/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ messages: [seedMsg] }),
    });
    const data = await res.json();

    if (data.ok) {
      // Store BOTH sides so history stays user→assistant alternating
      conversationHistory.push(seedMsg);
      conversationHistory.push({ role: "assistant", content: data.message });
      appendMessage("assistant", data.message);
    } else {
      // API returned an error — use a static fallback and seed history manually
      const fallback = "Welcome to CV2CC! I'm your AI guide for completing the CV2 building permit form. To get started — what's the name of your project?";
      conversationHistory.push(seedMsg);
      conversationHistory.push({ role: "assistant", content: fallback });
      appendMessage("assistant", fallback);
    }
  } catch (err) {
    // Network error — static fallback, still seed history correctly
    const fallback = "Welcome to CV2CC! I'll guide you through filling out your CV2 building permit form. Let's start — what is the project name?";
    conversationHistory.push(seedMsg);
    conversationHistory.push({ role: "assistant", content: fallback });
    appendMessage("assistant", fallback);
  } finally {
    setSendState(true);
    inputEl.focus();
  }
}

startConversation();
