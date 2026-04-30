// ─────────────────────────────────────────────────────────────────────────
// Claude RAG Chat — vanilla JS frontend
// ─────────────────────────────────────────────────────────────────────────
const API = "/api";

const state = {
  files: [],          // FileRecord[]
  selected: new Set(),// file_ids selected for the next chat call
  sessionCost: 0,
  sessionRequests: 0,
  pollTimer: null,
};

// ── DOM refs ────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const filesTbody    = $("files-tbody");
const filesEmpty    = $("files-empty");
const uploadInput   = $("upload");
const uploadStatus  = $("upload-status");
const messagesEl    = $("messages");
const chatForm      = $("chat-form");
const promptEl      = $("prompt");
const sendBtn       = $("send-btn");
const chromaOnlyCb  = $("chroma-only");
const sessionCostEl = $("session-cost");
const sessionReqEl  = $("session-requests");
const clearChatBtn  = $("clear-chat");
const textModal     = $("text-modal");
const textModalTitle= $("text-modal-title");
const textModalBody = $("text-modal-body");
const textModalClose= $("text-modal-close");

// ── helpers ─────────────────────────────────────────────────────────────
function fmtUsd(n) {
  return "$" + Number(n || 0).toFixed(6);
}
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// ── files: list / render / poll ─────────────────────────────────────────
async function refreshFiles() {
  try {
    const res = await fetch(`${API}/files`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.files = data.files || [];
    renderFiles();
  } catch (err) {
    console.error("refreshFiles failed:", err);
  }
}

function renderFiles() {
  filesTbody.innerHTML = "";
  if (state.files.length === 0) {
    filesEmpty.classList.remove("hidden");
    return;
  }
  filesEmpty.classList.add("hidden");

  for (const f of state.files) {
    const tr = document.createElement("tr");
    tr.className = "border-b border-slate-100 hover:bg-slate-50";

    const checked = state.selected.has(f.id) ? "checked" : "";
    const isReady = f.status === "ready";
    const disabledAttr = isReady ? "" : "disabled";

    tr.innerHTML = `
      <td class="p-2 align-top">
        <input type="checkbox" data-fid="${f.id}" class="file-cb"
               ${checked} ${disabledAttr} />
      </td>
      <td class="p-2 align-top">
        <div class="font-medium text-slate-700 break-all">
          ${escapeHtml(f.filename)}
        </div>
        <div class="text-xs text-slate-400">${(f.size_bytes/1024).toFixed(1)} KB</div>
        ${f.error ? `<div class="text-xs text-red-600 mt-1">${escapeHtml(f.error)}</div>` : ""}
      </td>
      <td class="p-2 align-top">
        <span class="status-pill status-${escapeHtml(f.status)}">
          ${escapeHtml(f.status)}
        </span>
      </td>
      <td class="p-2 align-top text-right text-slate-600">
        ${f.chunk_count || 0}
      </td>
      <td class="p-2 align-top text-right">
        <button data-view="${f.id}"
                class="text-xs text-indigo-600 hover:text-indigo-800 ${isReady ? "" : "opacity-40 cursor-not-allowed"}"
                ${disabledAttr}>view</button>
        <button data-del="${f.id}"
                class="text-xs text-slate-400 hover:text-red-600 ml-2">×</button>
      </td>
    `;
    filesTbody.appendChild(tr);
  }
}

// Delegate clicks inside the file table.
filesTbody.addEventListener("click", async (e) => {
  const t = e.target;
  if (t.matches(".file-cb")) {
    const fid = t.dataset.fid;
    if (t.checked) state.selected.add(fid);
    else state.selected.delete(fid);
    return;
  }
  const viewId = t.getAttribute("data-view");
  const delId  = t.getAttribute("data-del");
  if (viewId) await openTextModal(viewId);
  else if (delId) await deleteFile(delId);
});

async function openTextModal(fid) {
  try {
    const res = await fetch(`${API}/files/${fid}/text`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    textModalTitle.textContent = data.filename;
    textModalBody.textContent  = data.text || "(no extracted text)";
    textModal.classList.remove("hidden");
    textModal.classList.add("flex");
  } catch (err) {
    alert("Failed to load text: " + err.message);
  }
}
textModalClose.addEventListener("click", () => {
  textModal.classList.add("hidden");
  textModal.classList.remove("flex");
});
textModal.addEventListener("click", (e) => {
  if (e.target === textModal) textModalClose.click();
});

async function deleteFile(fid) {
  if (!confirm("Delete this file?")) return;
  try {
    const res = await fetch(`${API}/files/${fid}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error(await res.text());
    state.selected.delete(fid);
    await refreshFiles();
  } catch (err) {
    alert("Delete failed: " + err.message);
  }
}

// ── upload ──────────────────────────────────────────────────────────────
uploadInput.addEventListener("change", async () => {
  const files = Array.from(uploadInput.files || []);
  if (!files.length) return;
  uploadStatus.textContent = `Uploading ${files.length} file(s)…`;
  for (const f of files) {
    try {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const res = await fetch(`${API}/files/upload`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
    } catch (err) {
      console.error("upload failed for", f.name, err);
      uploadStatus.textContent = `Failed: ${f.name} — ${err.message}`;
    }
  }
  uploadInput.value = "";
  uploadStatus.textContent = "Upload queued — processing in background.";
  await refreshFiles();
});

// ── chat ────────────────────────────────────────────────────────────────
function appendUser(text) {
  const div = document.createElement("div");
  div.className = "msg-bubble bg-indigo-600 text-white rounded-lg px-4 py-3";
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function appendAssistant({ answer, chunks, cost, used_chroma_only }) {
  const wrap = document.createElement("div");
  wrap.className = "msg-bubble bg-white border border-slate-200 rounded-lg px-4 py-3 space-y-3";

  const body = document.createElement("div");
  body.className = "whitespace-pre-wrap text-slate-800";
  body.textContent = answer;
  wrap.appendChild(body);

  // Sources
  if (chunks && chunks.length) {
    const sources = document.createElement("details");
    sources.className = "text-xs text-slate-600";
    sources.innerHTML = `<summary class="cursor-pointer">Sources (${chunks.length})</summary>`;
    const ul = document.createElement("ul");
    ul.className = "mt-2 space-y-2";
    for (const c of chunks) {
      const li = document.createElement("li");
      li.className = "border-l-2 border-slate-200 pl-2";
      li.innerHTML = `
        <div class="font-semibold">${escapeHtml(c.filename)}
          ${c.distance != null ? `<span class="text-slate-400 font-normal">(d=${c.distance.toFixed(3)})</span>`: ""}
        </div>
        <div class="text-slate-500">${escapeHtml(c.text.slice(0, 400))}${c.text.length > 400 ? "…" : ""}</div>`;
      ul.appendChild(li);
    }
    sources.appendChild(ul);
    wrap.appendChild(sources);
  }

  // Cost
  const costLine = document.createElement("div");
  costLine.className = "cost-line border-t pt-2";
  if (used_chroma_only) {
    costLine.textContent = "ChromaDB-only mode (no Claude call) — cost: $0.00";
  } else {
    costLine.textContent =
      `model: ${cost.model || "?"} • ` +
      `in: ${cost.input_tokens} tok (${fmtUsd(cost.input_cost_usd)}) • ` +
      `out: ${cost.output_tokens} tok (${fmtUsd(cost.output_cost_usd)}) • ` +
      `total: ${fmtUsd(cost.total_cost_usd)}`;
    state.sessionCost += cost.total_cost_usd || 0;
  }
  state.sessionRequests += 1;
  sessionCostEl.textContent = fmtUsd(state.sessionCost);
  sessionReqEl.textContent  = String(state.sessionRequests);
  wrap.appendChild(costLine);

  messagesEl.appendChild(wrap);
  scrollToBottom();
}

function appendError(text) {
  const div = document.createElement("div");
  div.className = "msg-bubble bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3";
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = promptEl.value.trim();
  if (!message) return;
  appendUser(message);
  promptEl.value = "";
  sendBtn.disabled = true;
  sendBtn.textContent = "…";

  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        file_ids: Array.from(state.selected),
        chroma_only: chromaOnlyCb.checked,
      }),
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(body || `HTTP ${res.status}`);
    }
    const data = await res.json();
    appendAssistant(data);
  } catch (err) {
    appendError("Error: " + err.message);
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = "Send";
  }
});

clearChatBtn.addEventListener("click", () => {
  // Keep the intro div, drop everything else.
  const intro = messagesEl.firstElementChild;
  messagesEl.innerHTML = "";
  if (intro) messagesEl.appendChild(intro);
});

// ── polling ─────────────────────────────────────────────────────────────
function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(refreshFiles, 3000);
}

// ── boot ────────────────────────────────────────────────────────────────
refreshFiles();
startPolling();
