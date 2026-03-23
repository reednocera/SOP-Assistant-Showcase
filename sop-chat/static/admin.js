/* ── Wonder SOPs — Admin UI ──────────────────────────────────────────────── */

// ── State ───────────────────────────────────────────────────────────────────
let allSOPs = [];
let pinnedSopId = null;
let chatSessionId = null;
let isChatStreaming = false;
let pendingProposal = null;

// ── Elements ────────────────────────────────────────────────────────────────
const sopList = document.getElementById('sop-list');
const sopCount = document.getElementById('sop-count');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatMicBtn = document.getElementById('chat-mic-btn');
const pinnedBar = document.getElementById('pinned-bar');
const proposalCard = document.getElementById('proposal-card');

// ── Voice input ─────────────────────────────────────────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
let recognition = null;
let isListening = false;

if (!SpeechRecognition && !isIOS) {
  chatMicBtn.disabled = true;
  chatMicBtn.title = 'Voice input not supported in this browser';
}

function toggleVoice() {
  if (isChatStreaming) return;

  if (isIOS || !SpeechRecognition) {
    chatInput.focus();
    const prev = chatInput.placeholder;
    chatInput.placeholder = 'Tap \u{1F3A4} on your keyboard to speak\u2026';
    setTimeout(() => { chatInput.placeholder = prev; }, 3000);
    return;
  }

  if (isListening) { recognition.stop(); return; }
  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onstart = () => { isListening = true; chatMicBtn.classList.add('listening'); };
  recognition.onresult = (e) => {
    chatInput.value = Array.from(e.results).map(r => r[0].transcript).join('');
    chatInput.dispatchEvent(new Event('input'));
  };
  recognition.onend = () => {
    isListening = false;
    chatMicBtn.classList.remove('listening');
    if (chatInput.value.trim()) sendChatMessage();
  };
  recognition.onerror = (e) => {
    isListening = false;
    chatMicBtn.classList.remove('listening');
    if (e.error === 'not-allowed') alert('Microphone access denied.');
  };
  recognition.start();
}

chatMicBtn.addEventListener('click', toggleVoice);

// ── Init ────────────────────────────────────────────────────────────────────
async function init() {
  const res = await fetch('/api/sops');
  allSOPs = await res.json();
  document.getElementById('overview-count').textContent = allSOPs.length;
  renderSidebar(allSOPs);
  sopCount.textContent = `${allSOPs.length} SOPs`;
}

function renderSidebar(list) {
  sopList.innerHTML = list.map(s =>
    `<div class="sop-item ${s.id === pinnedSopId ? 'active' : ''}" onclick="pinSOP('${escHtml(s.id)}')" data-id="${escHtml(s.id)}">
      <div class="sop-id">${escHtml(s.id)}</div>
      <div class="sop-title">${escHtml(s.title)}</div>
    </div>`
  ).join('');
}

function filterSidebar() {
  const q = document.getElementById('sidebar-search').value.toLowerCase();
  const filtered = q
    ? allSOPs.filter(s => s.id.toLowerCase().includes(q) || s.title.toLowerCase().includes(q))
    : allSOPs;
  renderSidebar(filtered);
  sopCount.textContent = q ? `${filtered.length} of ${allSOPs.length} SOPs` : `${allSOPs.length} SOPs`;
}

// ── Pin / Unpin ─────────────────────────────────────────────────────────────
function pinSOP(id) {
  if (pinnedSopId === id) { unpinSOP(); return; }
  pinnedSopId = id;
  const sop = allSOPs.find(s => s.id === id);
  document.getElementById('pinned-id').textContent = id;
  document.getElementById('pinned-label').textContent = sop ? sop.title : '';
  pinnedBar.style.display = 'block';
  document.querySelectorAll('.sop-item').forEach(el =>
    el.classList.toggle('active', el.dataset.id === id)
  );
  chatInput.focus();
}

function unpinSOP() {
  pinnedSopId = null;
  pinnedBar.style.display = 'none';
  document.querySelectorAll('.sop-item').forEach(el => el.classList.remove('active'));
}

async function archiveSOP() {
  if (!pinnedSopId) return;
  const sop = allSOPs.find(s => s.id === pinnedSopId);
  const label = sop ? `${pinnedSopId} — ${sop.title}` : pinnedSopId;
  if (!confirm(`Archive "${label}"?\n\nThis will remove it from the active SOP list. The file will be moved to the archive folder.`)) return;

  const idToArchive = pinnedSopId;
  try {
    const res = await fetch('/api/admin/archive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sop_id: idToArchive }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Archive failed');

    allSOPs = allSOPs.filter(s => s.id !== idToArchive);
    document.getElementById('overview-count').textContent = allSOPs.length;
    sopCount.textContent = `${allSOPs.length} SOPs`;
    unpinSOP();
    hideProposalCard();
    renderSidebar(allSOPs);
    addSystemMessage(`\u2713 ${idToArchive} archived and removed from active SOPs.`);
  } catch (err) {
    addSystemMessage(`\u2717 Archive error: ${escHtml(err.message)}`);
  }
}

// ── "Add New SOP" ───────────────────────────────────────────────────────────
async function startNewSOP() {
  unpinSOP();
  const res = await fetch('/api/admin/next-id');
  const data = await res.json();
  addChatMessage('user', 'I\'d like to create a new SOP.');
  chatInput.value = "I'd like to create a new SOP.";
  sendChatMessage();
}

// ── Proposal card ───────────────────────────────────────────────────────────
function showProposalCard(sopId, isNew, conflicts) {
  const label = isNew ? 'NEW SOP' : (sopId || 'EDIT');
  document.getElementById('proposal-sop-label').textContent = label;

  const conflictsEl = document.getElementById('proposal-conflicts');
  if (conflicts && conflicts.length > 0) {
    const ids = conflicts.map(c => `<strong>${escHtml(c.id)}</strong>`).join(', ');
    conflictsEl.innerHTML = `\u26A0 Review related SOPs that may be affected: ${ids}`;
    conflictsEl.classList.add('visible');
  } else {
    conflictsEl.classList.remove('visible');
  }

  proposalCard.classList.add('visible');
}

function hideProposalCard() {
  proposalCard.classList.remove('visible');
  pendingProposal = null;
  document.getElementById('proposal-conflicts').classList.remove('visible');
}

async function publishChanges() {
  if (!chatSessionId) return;
  const btn = document.getElementById('btn-publish');
  btn.disabled = true;
  btn.textContent = 'Publishing\u2026';

  try {
    const res = await fetch('/api/admin/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: chatSessionId }),
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || 'Publish failed');

    hideProposalCard();
    if (data.sop_id) {
      const match = allSOPs.find(s => s.id === data.sop_id);
      if (match && data.title) match.title = data.title;
      else if (!match && data.status === 'created') {
        const r2 = await fetch('/api/sops');
        allSOPs = await r2.json();
        document.getElementById('overview-count').textContent = allSOPs.length;
      }
      renderSidebar(allSOPs);
    }

    addSystemMessage(`\u2713 Published successfully \u2014 ${data.sop_id}`);
  } catch (err) {
    addSystemMessage(`\u2717 Error: ${escHtml(err.message)}`);
  }

  btn.disabled = false;
  btn.textContent = 'Publish Changes';
}

async function cancelProposal() {
  if (chatSessionId) {
    fetch('/api/admin/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: chatSessionId }),
    });
  }
  hideProposalCard();
  addSystemMessage('Changes discarded.');
}

// ── Chat helpers ────────────────────────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function addChatMessage(role, html) {
  document.getElementById('chat-welcome')?.remove();
  const div = document.createElement('div');
  div.className = `message message-${role}`;
  div.innerHTML = `<div class="bubble">${html}</div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function addSystemMessage(text) {
  const div = document.createElement('div');
  div.style.cssText = 'text-align:center;font-size:12px;color:var(--text-dim);padding:4px 0;';
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

chatInput.addEventListener('input', () => {
  chatInput.style.height = '44px';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
});

// ── Main send ───────────────────────────────────────────────────────────────
async function sendChatMessage() {
  const msg = chatInput.value.trim();
  if (!msg || isChatStreaming) return;

  isChatStreaming = true;
  chatSendBtn.disabled = true;
  chatInput.value = '';
  chatInput.style.height = '44px';

  const sendingPinned = pinnedSopId;
  addChatMessage('user', escHtml(msg));

  const assistantDiv = addChatMessage('assistant',
    '<div class="typing-indicator"><span></span><span></span><span></span></div>'
  );
  const bubble = assistantDiv.querySelector('.bubble');

  let fullText = '';
  let nextEventType = null;
  let proposalInfo = null;
  let conflictsInfo = null;

  try {
    const payload = { message: msg, session_id: chatSessionId };
    if (sendingPinned) payload.pinned_sop = sendingPinned;

    const res = await fetch('/api/admin/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      bubble.innerHTML = `<p style="color:var(--red)">${escHtml(err.error || 'Request failed')}</p>`;
      isChatStreaming = false;
      chatSendBtn.disabled = false;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          nextEventType = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);

        if (nextEventType === 'session') {
          chatSessionId = data.trim();
          nextEventType = null;
          continue;
        }
        if (nextEventType === 'proposal') {
          try { proposalInfo = JSON.parse(data); } catch {}
          nextEventType = null;
          continue;
        }
        if (nextEventType === 'conflicts') {
          try { conflictsInfo = JSON.parse(data); } catch {}
          nextEventType = null;
          continue;
        }

        nextEventType = null;
        if (data === '[DONE]') continue;
        let chunk;
        try { chunk = JSON.parse(data); } catch { continue; }
        if (chunk.startsWith('[ERROR]')) {
          bubble.innerHTML = `<p style="color:var(--red)">${escHtml(chunk)}</p>`;
          continue;
        }
        fullText += chunk;
      }
    }

    if (fullText) {
      const PROPOSAL_RE = /\[\[PROPOSAL\]\][\s\S]*?\[\[\/PROPOSAL\]\]/g;
      const hasProposal = PROPOSAL_RE.test(fullText);
      const cleanText = fullText.replace(PROPOSAL_RE, '').trim();

      bubble.innerHTML = marked.parse(cleanText || '(Generating proposal\u2026)', { breaks: true, gfm: true });

      if (hasProposal) {
        const notice = document.createElement('div');
        notice.className = 'proposal-notice';
        notice.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
          Proposed changes ready \u2014 see below.`;
        bubble.appendChild(notice);
      }
    }

    if (proposalInfo) {
      pendingProposal = proposalInfo;
      showProposalCard(proposalInfo.sop_id, proposalInfo.is_new, conflictsInfo || []);
    }

  } catch (err) {
    bubble.innerHTML = `<p style="color:var(--red)">Connection error: ${escHtml(err.message)}</p>`;
  }

  isChatStreaming = false;
  chatSendBtn.disabled = false;
  chatInput.focus();
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Clear chat ──────────────────────────────────────────────────────────────
async function clearChat() {
  if (chatSessionId) {
    fetch('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: chatSessionId }),
    });
  }
  chatSessionId = null;
  pendingProposal = null;
  hideProposalCard();
  unpinSOP();
  chatMessages.innerHTML = `
    <div class="chat-welcome" id="chat-welcome">
      <h2>Admin Chat</h2>
      <p>Select an SOP from the sidebar to ask questions, request edits, or create new SOPs.</p>
    </div>`;
}

init();
