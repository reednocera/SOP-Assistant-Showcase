/* ── Wonder SOPs — Chat UI ───────────────────────────────────────────────── */

let sessionId = null;
let isStreaming = false;
let sopImageMap = {};

// Load SOP image map at startup
fetch('/api/sops').then(r => r.json()).then(sops => {
  sops.forEach(s => { if (s.images && s.images.length) sopImageMap[s.id] = s.images; });
});

const chatArea = document.getElementById('chat-area');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');

// ── Voice input ─────────────────────────────────────────────────────────────

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
let recognition = null;
let isListening = false;

if (!SpeechRecognition && !isIOS) {
  micBtn.disabled = true;
  micBtn.title = 'Voice input not supported in this browser';
}

function toggleVoice() {
  if (isStreaming) return;

  if (isIOS || !SpeechRecognition) {
    userInput.focus();
    const prev = userInput.placeholder;
    userInput.placeholder = 'Tap \u{1F3A4} on your keyboard to speak\u2026';
    setTimeout(() => { userInput.placeholder = prev; }, 3000);
    return;
  }

  if (isListening) { recognition.stop(); return; }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add('listening');
  };

  recognition.onresult = (event) => {
    const transcript = Array.from(event.results)
      .map(r => r[0].transcript)
      .join('');
    userInput.value = transcript;
    userInput.dispatchEvent(new Event('input'));
  };

  recognition.onend = () => {
    isListening = false;
    micBtn.classList.remove('listening');
    if (userInput.value.trim()) sendMessage();
  };

  recognition.onerror = (event) => {
    isListening = false;
    micBtn.classList.remove('listening');
    if (event.error === 'not-allowed') {
      alert('Microphone access denied. Please allow microphone permissions.');
    }
  };

  recognition.start();
}

micBtn.addEventListener('click', toggleVoice);

// ── Input handling ──────────────────────────────────────────────────────────

userInput.addEventListener('input', () => {
  userInput.style.height = '44px';
  userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
});

userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function askSuggestion(el) {
  userInput.value = el.textContent;
  sendMessage();
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function addMessage(role, content) {
  const welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();

  const div = document.createElement('div');
  div.className = `message message-${role}`;
  div.innerHTML = `<div class="bubble">${content}</div>`;
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  return div;
}

function renderMarkdown(text) {
  return marked.parse(text, { breaks: true, gfm: true });
}

function rewriteImages(container) {
  container.querySelectorAll('img').forEach(img => {
    const src = img.getAttribute('src') || '';
    const match = src.match(/(?:\.\.\/)*images\/([^/]+)$/);
    if (match) {
      img.src = `/api/images/${match[1]}`;
      img.style.cssText = 'max-width:100%;border-radius:8px;margin:8px 0;cursor:pointer;display:block;';
      img.addEventListener('click', () => window.open(img.src, '_blank'));
      img.onerror = () => { img.style.display = 'none'; };
    }
  });
}

// ── Image panel ─────────────────────────────────────────────────────────────

const imagePanel = document.getElementById('image-panel');
const imagePanelBody = document.getElementById('image-panel-body');
const imagePanelHeader = document.getElementById('image-panel-header');
const imagePanelCount = document.getElementById('image-panel-count');

let lbImages = [];
let lbIndex = 0;

function openImagePanel(filenames) {
  lbImages = filenames;
  imagePanelBody.innerHTML = '<div id="image-panel-hint">Click an image to preview it fully</div>';
  imagePanelCount.textContent = filenames.length;

  filenames.forEach((filename, idx) => {
    const card = document.createElement('div');
    card.className = 'img-card';
    card.title = 'Click to view full size';
    card.onclick = () => openLightbox(idx);
    const img = document.createElement('img');
    img.src = `/api/images/${filename}`;
    img.alt = filename;
    img.loading = 'lazy';
    img.onerror = () => { card.remove(); };
    const label = document.createElement('div');
    label.className = 'img-card-label';
    label.textContent = filename.replace(/^SOP-\d+-/, '').replace(/-/g, ' ');
    card.appendChild(img);
    card.appendChild(label);
    imagePanelBody.appendChild(card);
  });
  imagePanel.classList.add('open');
}

function closeImagePanel() {
  imagePanel.classList.remove('open');
}

// ── Lightbox ────────────────────────────────────────────────────────────────

const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxCounter = document.getElementById('lightbox-counter');

function openLightbox(idx) {
  lbIndex = idx;
  lightboxImg.src = `/api/images/${lbImages[lbIndex]}`;
  lightboxCounter.textContent = `${lbIndex + 1} / ${lbImages.length}`;
  document.getElementById('lb-prev').disabled = lbIndex === 0;
  document.getElementById('lb-next').disabled = lbIndex === lbImages.length - 1;
  lightbox.classList.add('open');
}

function closeLightbox() {
  lightbox.classList.remove('open');
}

function lightboxNav(dir) {
  const next = lbIndex + dir;
  if (next >= 0 && next < lbImages.length) openLightbox(next);
}

lightbox.addEventListener('click', (e) => { if (e.target === lightbox) closeLightbox(); });

document.addEventListener('keydown', (e) => {
  if (!lightbox.classList.contains('open')) return;
  if (e.key === 'ArrowRight') lightboxNav(1);
  if (e.key === 'ArrowLeft') lightboxNav(-1);
  if (e.key === 'Escape') closeLightbox();
});

// ── Drag to move image panel ────────────────────────────────────────────────

let dragOffsetX = 0, dragOffsetY = 0, isDragging = false;

imagePanelHeader.addEventListener('mousedown', (e) => {
  if (e.target === document.getElementById('image-panel-close')) return;
  isDragging = true;
  const rect = imagePanel.getBoundingClientRect();
  dragOffsetX = e.clientX - rect.left;
  dragOffsetY = e.clientY - rect.top;
  imagePanel.style.transition = 'none';
  e.preventDefault();
});

document.addEventListener('mousemove', (e) => {
  if (!isDragging) return;
  const x = Math.max(0, Math.min(window.innerWidth - imagePanel.offsetWidth, e.clientX - dragOffsetX));
  const y = Math.max(0, Math.min(window.innerHeight - imagePanel.offsetHeight, e.clientY - dragOffsetY));
  imagePanel.style.left = x + 'px';
  imagePanel.style.top = y + 'px';
  imagePanel.style.right = 'auto';
});

document.addEventListener('mouseup', () => { isDragging = false; });

// ── Send message ────────────────────────────────────────────────────────────

async function sendMessage() {
  const msg = userInput.value.trim();
  if (!msg || isStreaming) return;

  isStreaming = true;
  sendBtn.disabled = true;
  userInput.value = '';
  userInput.style.height = '44px';

  addMessage('user', escapeHtml(msg));

  const assistantDiv = addMessage('assistant',
    '<div class="typing-indicator"><span></span><span></span><span></span></div>'
  );
  const bubble = assistantDiv.querySelector('.bubble');

  let fullText = '';
  let sources = [];
  let nextEventType = null;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, session_id: sessionId }),
    });

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

        if (nextEventType === 'sources') {
          sources = data.split(',').map(s => {
            const [id, ...titleParts] = s.split('|');
            return { id: id.trim(), title: titleParts.join('|').trim() };
          });
          nextEventType = null;
          continue;
        }

        if (nextEventType === 'session') {
          sessionId = data.trim();
          nextEventType = null;
          continue;
        }

        nextEventType = null;
        if (data === '[DONE]') continue;

        let chunk;
        try { chunk = JSON.parse(data); } catch { continue; }

        if (chunk.startsWith('[ERROR]')) {
          bubble.innerHTML = `<p style="color:var(--red)">${escapeHtml(chunk)}</p>`;
          continue;
        }

        fullText += chunk;
      }
    }

    if (fullText) {
      bubble.innerHTML = renderMarkdown(fullText);
      rewriteImages(bubble);
    }

    if (sources.length > 0) {
      const seen = new Set();
      const responseImages = [];
      sources.forEach(s => {
        (sopImageMap[s.id] || []).forEach(filename => {
          if (!seen.has(filename)) { seen.add(filename); responseImages.push(filename); }
        });
      });

      const sourcesDiv = document.createElement('div');
      sourcesDiv.className = 'sources';
      sourcesDiv.innerHTML = sources.map(s =>
        `<div class="source-tag"><span class="sop-id">${escapeHtml(s.id)}</span> ${escapeHtml(s.title)}</div>`
      ).join('');

      if (responseImages.length > 0) {
        const imgBtn = document.createElement('button');
        imgBtn.className = 'img-toggle-btn';
        imgBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> ${responseImages.length} Image${responseImages.length > 1 ? 's' : ''}`;
        imgBtn.onclick = () => openImagePanel(responseImages);
        sourcesDiv.appendChild(imgBtn);
      }

      assistantDiv.appendChild(sourcesDiv);
    }

  } catch (err) {
    bubble.innerHTML = `<p style="color: var(--red);">Connection error: ${escapeHtml(err.message)}</p>`;
  }

  isStreaming = false;
  sendBtn.disabled = false;
  userInput.focus();
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ── Clear chat ──────────────────────────────────────────────────────────────

const welcomeHTML = `
  <div class="welcome" id="welcome">
    <h2>How can I help?</h2>
    <p>Ask any question about Wonder Group standard operating procedures. I'll find the relevant SOPs and give you a clear answer.</p>
    <div class="suggestions">
      <div class="suggestion" onclick="askSuggestion(this)">What do I do if the last item of an order is out of stock?</div>
      <div class="suggestion" onclick="askSuggestion(this)">How do I clean the APW Wyott Bun Toaster?</div>
      <div class="suggestion" onclick="askSuggestion(this)">What is the process for a curbside pickup order?</div>
      <div class="suggestion" onclick="askSuggestion(this)">How do I handle a customer food safety complaint?</div>
    </div>
  </div>`;

async function clearChat() {
  if (sessionId) {
    fetch('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
  }
  sessionId = null;
  chatArea.innerHTML = welcomeHTML;
}

userInput.focus();
