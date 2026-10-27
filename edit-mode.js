/**
 * STUDIO SHIFT — Staging edit mode
 * Open  https://studioshift.eu/index-staging.html?edit  and click any text to edit it.
 * "Copy changes" puts the edits on the clipboard so they can be pasted into Claude
 * and committed to content.js. Nothing is saved from the browser itself.
 * Only runs on index-staging.html with ?edit, so it is inert on the live page.
 */
(function () {
  if (!/index-staging/.test(location.pathname)) return;
  if (!/[?&]edit(=|&|$)/.test(location.search)) return;
  if (typeof CONTENT === 'undefined') return;

  document.body.classList.add('editing');
  document.querySelectorAll('.reveal').forEach(el => el.classList.add('visible'));

  const ITEM_SEL = '.step-chip, .step-chip-sub, .team-tag, .how-pill';
  const fields = [];      // { key, el, orig, read() }
  const bioOrig = {};     // key -> original bio text (captured on first edit)

  // ── styles ──────────────────────────────────────────
  const style = document.createElement('style');
  style.textContent = `
    [data-edit] { cursor: text; transition: box-shadow .15s, background .15s; }
    [data-edit]:hover { outline: 2px dashed rgba(0,180,216,.7); outline-offset: 3px; }
    [data-edit]:focus { outline: 2px solid #00B4D8; outline-offset: 3px; background: rgba(0,180,216,.08); }
    [data-edit].edited { box-shadow: 0 0 0 3px rgba(39,174,96,.55); border-radius: 4px; }
    .edit-add {
      display: inline-flex; align-items: center; cursor: pointer; user-select: none;
      font: 600 11px 'Space Grotesk', sans-serif; color: #00B4D8; background: rgba(0,180,216,.1);
      border: 1px dashed rgba(0,180,216,.7); border-radius: 100px; padding: 4px 12px;
    }
    .edit-add:hover { background: rgba(0,180,216,.2); }
    .specialist-more { opacity: 1 !important; transform: none !important; }
    #editBar {
      position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%); z-index: 2000;
      display: flex; align-items: center; gap: 10px; padding: 10px 12px 10px 18px;
      background: #0B3D52; color: #fff; border-radius: 100px;
      box-shadow: 0 12px 40px rgba(11,61,82,.4); font: 600 13px 'Space Grotesk', sans-serif;
      max-width: calc(100vw - 24px);
    }
    #editBar button {
      font: inherit; border: none; cursor: pointer; border-radius: 100px; padding: 8px 16px;
      background: rgba(255,255,255,.12); color: #fff;
    }
    #editBar button:hover { background: rgba(255,255,255,.22); }
    #editBar #editCopy { background: #00B4D8; color: #0B3D52; }
    #editBar #editCopy:hover { background: #33c4e2; }
    #editBar .edit-title { opacity: .75; font-weight: 500; }
    #editPanel {
      position: fixed; left: 50%; bottom: 80px; transform: translateX(-50%); z-index: 2000;
      width: min(560px, calc(100vw - 24px)); max-height: 60vh; overflow: auto;
      background: #fff; color: #0B3D52; border-radius: 16px; padding: 18px 20px;
      box-shadow: 0 20px 60px rgba(11,61,82,.35); font: 14px/1.5 'Outfit', sans-serif; display: none;
    }
    #editPanel.open { display: block; }
    #editPanel h4 { font: 700 15px 'Space Grotesk', sans-serif; margin-bottom: 8px; }
    #editPanel ul { padding-left: 18px; margin: 0 0 12px; }
    #editPanel li { margin-bottom: 6px; word-break: break-word; }
    #editPanel code { font: 12px 'IBM Plex Mono', monospace; color: #00809a; }
    #editPanel .help { font-size: 12.5px; opacity: .75; }
    #editToast {
      position: fixed; left: 50%; bottom: 84px; transform: translateX(-50%); z-index: 2100;
      background: #27AE60; color: #fff; padding: 10px 20px; border-radius: 100px;
      font: 600 13px 'Space Grotesk', sans-serif; opacity: 0; pointer-events: none; transition: opacity .25s;
    }
    #editToast.show { opacity: 1; }
  `;
  document.head.appendChild(style);

  // ── helpers ─────────────────────────────────────────
  function makeEditable(el) {
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('data-edit', '');
    el.setAttribute('spellcheck', 'true');
  }
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  function readItems(el) {
    return [...el.children]
      .filter(c => c.matches(ITEM_SEL))
      .map(c => c.classList.contains('step-chip-sub')
        ? { sub: c.textContent.trim() }
        : c.textContent.trim())
      .filter(v => typeof v === 'string' ? v : v.sub);
  }
  function normalise(arr) {
    return (arr || []).map(i => typeof i === 'object' ? (i.sub ? { sub: i.sub } : (i.chip || '')) : i);
  }

  // ── 1. plain text fields: [data-content] ────────────
  document.querySelectorAll('[data-content]').forEach(el => {
    if (el.namespaceURI === 'http://www.w3.org/2000/svg') return;
    if (el.querySelector('[data-content]')) return;
    makeEditable(el);
    const key = el.getAttribute('data-content');
    const orig = el.innerHTML;
    fields.push({ key, el, orig, multiline: true, read: () => el.innerHTML });
  });

  // ── 2. chip / tag arrays ────────────────────────────
  document.querySelectorAll('[data-chips], [data-tags], [data-how-pills]').forEach(box => {
    const key = box.getAttribute('data-chips') || box.getAttribute('data-tags') || box.getAttribute('data-how-pills');
    const orig = normalise(CONTENT[key]);
    const items = () => [...box.children].filter(c => c.matches(ITEM_SEL));
    items().forEach(makeEditable);
    fields.push({ key, el: box, orig, items: true, read: () => readItems(box) });

    const add = document.createElement('span');
    add.className = 'edit-add';
    add.setAttribute('contenteditable', 'false');
    add.textContent = '+ add';
    add.addEventListener('click', e => {
      e.stopPropagation();
      const tpl = items().filter(c => !c.classList.contains('step-chip-sub')).pop() || items()[0];
      if (!tpl) return;
      const n = document.createElement(tpl.tagName);
      n.className = tpl.className;
      n.textContent = 'New';
      makeEditable(n);
      box.insertBefore(n, add);
      n.focus();
      document.getSelection().selectAllChildren(n);
      update();
    });
    box.appendChild(add);
  });

  // ── 3. FAQ (questions and answers rendered from CONTENT.faq_items) ──
  const allBtn = document.querySelector('.faq-cat[data-cat="all"]');
  if (allBtn) allBtn.click();
  document.querySelectorAll('.faq-item').forEach((item, i) => {
    item.open = true;
    const q = item.querySelector('.faq-q'), a = item.querySelector('.faq-answer');
    const src = CONTENT.faq_items && CONTENT.faq_items[i];
    if (!src) return;
    if (q) { makeEditable(q); fields.push({ key: 'faq_items.' + i + '.q', el: q, orig: q.innerHTML, read: () => q.innerHTML }); }
    if (a) { makeEditable(a); fields.push({ key: 'faq_items.' + i + '.a', el: a, orig: a.innerHTML, multiline: true, read: () => a.innerHTML }); }
  });
  // keep every answer open and the question editable (a click on a <summary> normally toggles it)
  document.addEventListener('click', e => {
    if (e.target.closest('.faq-item summary')) e.preventDefault();
  }, true);

  // ── 4. specialist bios (edited inside the modal) ────
  const bioEl = document.getElementById('bioText');
  const overlay = document.getElementById('bioOverlay');
  if (bioEl && overlay) {
    makeEditable(bioEl);
    bioEl.addEventListener('input', () => {
      const key = overlay.dataset.key + '_bio';
      if (!(key in bioOrig)) bioOrig[key] = CONTENT[key] || '';
      CONTENT[key] = bioEl.textContent.trim();   // so re-opening the card shows the edit
      update();
    });
    bioEl.addEventListener('keydown', e => { if (e.key === 'Enter') e.preventDefault(); });
  }

  // ── behaviour shared by all editable fields ─────────
  document.addEventListener('keydown', e => {
    const el = e.target.closest && e.target.closest('[data-edit]');
    if (!el || e.key !== 'Enter' || e.isComposing) return;
    if (el.closest('li')) return;                       // keep list behaviour in FAQ answers
    e.preventDefault();
    const f = fields.find(x => x.el === el);
    if (f && f.multiline) document.execCommand('insertLineBreak');
    else el.blur();
  });
  document.addEventListener('paste', e => {
    if (!e.target.closest || !e.target.closest('[data-edit]')) return;
    e.preventDefault();
    document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain'));
  });
  // no navigating away while editing text that sits inside links / buttons
  document.addEventListener('click', e => {
    if (e.target.closest('#editBar, #editPanel')) return;
    const link = e.target.closest('a');
    if (link) e.preventDefault();
  }, true);

  // ── change tracking ─────────────────────────────────
  function collect() {
    const out = {};
    fields.forEach(f => {
      const v = f.read();
      const changed = !same(v, f.orig);
      f.el.classList.toggle('edited', changed);
      if (changed) out[f.key] = v;
    });
    Object.keys(bioOrig).forEach(k => {
      if (CONTENT[k] !== bioOrig[k]) out[k] = CONTENT[k];
    });
    return out;
  }
  document.addEventListener('input', () => update());
  document.addEventListener('focusout', () => update());

  // ── toolbar + review panel ──────────────────────────
  const bar = document.createElement('div');
  bar.id = 'editBar';
  bar.innerHTML = '<span class="edit-title">Edit mode</span>' +
    '<button type="button" id="editCount">0 changes</button>' +
    '<button type="button" id="editCopy">Copy changes</button>' +
    '<button type="button" id="editExit">Exit</button>';
  const panel = document.createElement('div');
  panel.id = 'editPanel';
  const toast = document.createElement('div');
  toast.id = 'editToast';
  document.body.append(bar, panel, toast);

  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const preview = v => {
    const t = typeof v === 'string' ? v.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
      : v.map(i => typeof i === 'object' ? i.sub : i).join(' · ');
    return t.length > 110 ? t.slice(0, 110) + '…' : t;
  };
  function update() {
    const out = collect();
    const n = Object.keys(out).length;
    document.getElementById('editCount').textContent = n + (n === 1 ? ' change' : ' changes');
    panel.innerHTML = '<h4>' + (n ? 'Your changes' : 'No changes yet') + '</h4>' +
      (n ? '<ul>' + Object.keys(out).map(k => '<li><code>' + esc(k) + '</code><br>' + esc(preview(out[k])) + '</li>').join('') + '</ul>' : '') +
      '<p class="help">Click any text on the page to edit it. Chips and skills: delete the text to remove one, <b>+ add</b> to add one. ' +
      'Specialist bios: click <b>Read bio +</b> on a card and type in the popup. When you are done, press <b>Copy changes</b> and paste it to Claude.</p>';
    return out;
  }
  document.getElementById('editCount').addEventListener('click', () => panel.classList.toggle('open'));
  document.getElementById('editCopy').addEventListener('click', async () => {
    const out = update();
    const n = Object.keys(out).length;
    if (!n) { flash('Nothing changed yet'); return; }
    const text = 'Studio SHIFT staging edits (apply to content.js):\n' + JSON.stringify(out, null, 2);
    try { await navigator.clipboard.writeText(text); flash('Copied ' + n + (n === 1 ? ' change' : ' changes') + ' to the clipboard'); }
    catch (err) {
      panel.classList.add('open');
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.cssText = 'width:100%;height:160px;font:12px monospace';
      panel.appendChild(ta); ta.select();
      flash('Press Cmd+C to copy');
    }
  });
  document.getElementById('editExit').addEventListener('click', () => {
    if (Object.keys(collect()).length && !confirm('You have changes that are not copied yet. Leave edit mode and discard them?')) return;
    window.removeEventListener('beforeunload', warn);
    location.href = location.pathname;
  });
  function flash(msg) {
    toast.textContent = msg; toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2200);
  }
  function warn(e) { if (Object.keys(collect()).length) { e.preventDefault(); e.returnValue = ''; } }
  window.addEventListener('beforeunload', warn);
  update();
})();
