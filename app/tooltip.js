import { h } from './format.js';

const el = () => document.getElementById('tooltip');

export function showTip(x, y, build, cls = '') {
  const t = el();
  t.className = 'tooltip' + (cls ? ' ' + cls : '');
  t.replaceChildren();
  build(t);
  t.hidden = false;
  const w = t.offsetWidth, hgt = t.offsetHeight;
  const left = Math.max(8, Math.min(x + 14, window.innerWidth - w - 8));
  const top = y + 14 + hgt > window.innerHeight ? y - hgt - 10 : y + 14;
  t.style.left = left + 'px';
  t.style.top = top + 'px';
}
export function hideTip() { el().hidden = true; }

// Hint buttons. Help text that a reader needs once ("how to read this chart") sits behind a small "i" button
// instead of taking a paragraph on the page. The text shows on hover, on keyboard focus and on click (a click
// keeps it open, so it works on a touch screen); Escape, a click elsewhere or scrolling closes it.
// What the page says about the data's limits is never put behind one of these.
export function info(text) {
  return h('button', { type: 'button', class: 'info', 'aria-label': text, dataset: { hint: text } }, 'i');
}

export function initHints() {
  for (const b of document.querySelectorAll('.info[data-hint]')) b.setAttribute('aria-label', b.dataset.hint);
  let pinned = null;
  const btn = e => e.target instanceof Element ? e.target.closest('.info') : null;
  const open = b => {
    const r = b.getBoundingClientRect();
    showTip(r.left - 14, r.bottom - 8, t => t.append(b.dataset.hint), 'hint-tip');
  };
  const close = () => { pinned = null; hideTip(); };
  document.addEventListener('mouseover', e => { const b = btn(e); if (b) open(b); });
  document.addEventListener('mouseout', e => { const b = btn(e); if (b && pinned !== b) hideTip(); });
  document.addEventListener('focusin', e => { const b = btn(e); if (b) open(b); });
  document.addEventListener('focusout', e => { if (btn(e)) close(); });
  document.addEventListener('click', e => {
    const b = btn(e);
    if (!b) { if (pinned) close(); return; }
    e.preventDefault();
    if (pinned === b && !el().hidden) close(); else { pinned = b; open(b); }
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pinned) close(); });
  document.addEventListener('scroll', () => { if (pinned) close(); }, true);
}
