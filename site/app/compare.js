import { state, emit } from './state.js';
import { verdict, COLORS, LABEL_TEXT } from './labels.js';
import { fmtUsd, fmtPct, fmtInt, h } from './format.js';

export const MAX_COMPARE = 5;

export function renderCompare() {
  const drawer = document.getElementById('compare');
  document.getElementById('compare-count').textContent = String(state.compare.length);
  const rows = state.compare.map(id => state.byId.get(id)).filter(Boolean);
  if (!rows.length || !state.compareOpen) { drawer.hidden = true; drawer.replaceChildren(); return; }
  drawer.hidden = false;
  const band = state.band;
  const vs = rows.map(r => verdict(r, band, 'current'));
  const bestRatio = Math.min(...vs.map(v => v.ratio));
  const head = h('div', { class: 'head' },
    h('h2', {}, `Compare (${rows.length} of ${MAX_COMPARE})`),
    h('span', { class: 'muted' }, 'Lowest price ÷ benchmark is highlighted. Click a name to open it.'),
    h('span', { class: 'spacer' }),
    h('button', { class: 'btn ghost', onclick: () => emit('clear-compare') }, 'Clear'),
    h('button', { class: 'btn ghost', onclick: () => emit('toggle-compare-drawer') }, 'Close'));
  const th = (t, cls) => h('th', { class: cls }, t);
  const table = h('table', { class: 'cmp' },
    h('thead', {}, h('tr', {}, th('Listing'), th('Label'), th('Price', 'num'), th('Benchmark', 'num'), th('vs.', 'num'),
      th('Both models', ''), th('Sleeps', 'num'), th('Bedrooms', 'num'), th('Rating', 'num'), th('Km to centre', 'num'), th('Stay'), th(''))),
    h('tbody', {}, ...rows.map((r, i) => {
      const v = vs[i];
      return h('tr', { class: v.ratio === bestRatio && rows.length > 1 ? 'best' : '' },
        h('td', { class: 'name', title: r.name, onclick: () => emit('select', r.id) }, r.name),
        h('td', {}, h('span', { class: 'tag', style: { '--c': COLORS[v.label] } }, h('span', { class: 'dot' }), LABEL_TEXT[v.label])),
        h('td', { class: 'num' }, fmtUsd(r.price)), h('td', { class: 'num' }, fmtUsd(r.fair_i)), h('td', { class: 'num' }, fmtPct(v.ratio)),
        h('td', {}, v.confident ? 'agree' : 'disagree'),
        h('td', { class: 'num' }, fmtInt(r.guests)), h('td', { class: 'num' }, r.bedrooms == null ? '–' : fmtInt(r.bedrooms)),
        h('td', { class: 'num' }, r.rating == null ? '–' : r.rating.toFixed(2)), h('td', { class: 'num' }, r.km?.toFixed(1)),
        h('td', {}, r.monthly ? 'monthly' : 'nightly'),
        h('td', {}, h('button', { class: 'rm', 'aria-label': 'Remove', onclick: () => emit('toggle-compare', r.id) }, '×')));
    })));
  drawer.replaceChildren(head, table);
}
