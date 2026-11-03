// Number and text formatting shared by every view. Text from the data goes through textContent, never innerHTML.
const US = 'en-US';
export const fmtInt = v => (v == null || isNaN(v)) ? '–' : Math.round(v).toLocaleString(US);
export const fmtUsd = v => (v == null || isNaN(v)) ? '–' : (v < 0 ? '−' : '') + '$' + Math.round(Math.abs(v)).toLocaleString(US);
export const fmtSignedUsd = v => (v == null || isNaN(v)) ? '–' : (v >= 0 ? '+' : '−') + '$' + Math.round(Math.abs(v)).toLocaleString(US);
export const fmtPct = (ratio) => {
  if (ratio == null || isNaN(ratio)) return '–';
  const p = Math.round((ratio - 1) * 100);
  return (p > 0 ? '+' : p < 0 ? '−' : '') + Math.abs(p) + '%';
};
export const fmtShare = v => (v == null || isNaN(v)) ? '–' : Math.round(v * 100) + '%';
export const fmtRatio = r => (r == null || isNaN(r)) ? '–' : r.toFixed(2) + '×';
export const fmtDate = s => {
  if (!s) return '–';
  const d = new Date(s + 'T00:00:00');
  return isNaN(d) ? s : d.toLocaleDateString(US, { month: 'short', day: 'numeric', year: 'numeric' });
};
export const fmtMonth = s => {
  if (!s) return '';
  const d = new Date(s + 'T00:00:00');
  return isNaN(d) ? s : d.toLocaleDateString(US, { month: 'short', year: 'numeric' });
};
export const plural = (n, word, words = word + 's') => `${fmtInt(n)} ${n === 1 ? word : words}`;

// tiny DOM helper: h('div', {class: 'x', onclick: fn}, 'text', childEl, ...)
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) sk.startsWith('--') ? el.style.setProperty(sk, sv) : (el.style[sk] = sv);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
