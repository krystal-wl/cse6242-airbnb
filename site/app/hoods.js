// Neighbourhood aggregates are computed in the browser from the rows currently shown, so they follow the filters and the band.
import { labelOf, COLORS } from './labels.js';
import { ratiosOf } from './labels.js';
import { fmtInt, fmtShare, fmtRatio, h } from './format.js';
import { histogram } from './charts.js';

export const MIN_N = 5;

export function aggregate(rows, band, release) {
  const m = new Map();
  for (const r of rows) {
    const { ri } = ratiosOf(r, release);
    if (ri == null) continue;
    let a = m.get(r.hood);
    if (!a) m.set(r.hood, a = { hood: r.hood, ratios: [], under: 0, over: 0 });
    a.ratios.push(ri);
    const l = labelOf(ri, band);
    if (l === 'under') a.under++; else if (l === 'over') a.over++;
  }
  for (const a of m.values()) {
    a.n = a.ratios.length;
    a.median_ratio = d3.median(a.ratios);
    a.share_under = a.under / a.n;
    a.share_over = a.over / a.n;
  }
  return m;
}

const BLUE_RAMP = ['#cde2fb', '#0d366b'];
const ORANGE_RAMP = ['#fbe3d6', '#8a3612'];

export function colorScale(metric, aggs) {
  const vals = [...aggs.values()].filter(a => a.n >= MIN_N).map(a => a[metric]);
  if (metric === 'median_ratio') {
    return { scale: d3.scaleLinear().domain([0.75, 1, 1.333]).range([COLORS.under, '#f0efec', COLORS.over]).interpolate(d3.interpolateLab).clamp(true),
             stops: [COLORS.under, '#f0efec', COLORS.over], ends: ['0.75× or less', '1×', '1.33× or more'], title: 'Median price ÷ benchmark' };
  }
  const max = Math.max(0.05, d3.quantile(vals.sort(d3.ascending), 0.95) || 0);
  if (metric === 'share_over') return seq(ORANGE_RAMP, max, v => fmtShare(v), 'Share overpriced');
  if (metric === 'share_under') return seq(BLUE_RAMP, max, v => fmtShare(v), 'Share underpriced');
  return seq(BLUE_RAMP, max, v => fmtInt(v), 'Listings shown');
}
function seq(ramp, max, fmt, title) {
  return { scale: d3.scaleLinear().domain([0, max]).range(ramp).interpolate(d3.interpolateLab).clamp(true),
           stops: ramp, ends: ['0', fmt(max) + '+'], title };
}

export function renderLegend(el, info) {
  el.replaceChildren(
    h('div', {}, info.title, h('span', { class: 'muted' }, ` · fewer than ${MIN_N} listings: not coloured`)),
    h('div', { class: 'bar', style: { background: `linear-gradient(to right, ${info.stops.join(', ')})` } }),
    h('div', { class: 'ends' }, ...info.ends.map(t => h('span', {}, t))),
  );
}

export function hoodPopup(a, band, stayText) {
  const el = h('div', { class: 'popup' },
    h('h3', {}, a.hood),
    h('div', { class: 'facts' },
      h('span', {}, h('b', {}, fmtInt(a.n)), ` ${stayText} listings shown`),
      h('span', {}, 'median ', h('b', {}, fmtRatio(a.median_ratio))),
      h('span', {}, h('b', {}, fmtShare(a.share_under)), ' under'),
      h('span', {}, h('b', {}, fmtShare(a.share_over)), ' over')),
  );
  const chart = h('div', { class: 'chart' });
  el.append(chart, h('div', { class: 'muted small' }, 'Price ÷ benchmark, log scale. Shaded: the fair band.'));
  histogram(chart, a.ratios, { band, width: 260, height: 90 });
  return el;
}
