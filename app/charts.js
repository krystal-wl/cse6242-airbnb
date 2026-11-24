// D3 charts for the card and the neighbourhood popup. Thin marks, hairline axes, text in ink tokens.
import { fmtUsd, fmtSignedUsd, fmtInt, h } from './format.js';
import { showTip, hideTip } from './tooltip.js';

function barPath(x0, x1, y, hgt, r, roundRight) {
  const w = Math.max(0, x1 - x0), rr = Math.min(r, w, hgt / 2);
  if (w < 0.5) return `M${x0},${y}h0.5v${hgt}h-0.5z`;
  return roundRight
    ? `M${x0},${y}h${w - rr}a${rr},${rr} 0 0 1 ${rr},${rr}v${hgt - 2 * rr}a${rr},${rr} 0 0 1 -${rr},${rr}h-${w - rr}z`
    : `M${x0 + rr},${y}h${w - rr}v${hgt}h-${w - rr}a${rr},${rr} 0 0 1 -${rr},-${rr}v-${hgt - 2 * rr}a${rr},${rr} 0 0 1 ${rr},-${rr}z`;
}

// Horizontal waterfall from the city's typical listing to this listing's benchmark.
export function waterfall(el, { base, baseLabel, fair, fairLabel, deltas }) {
  const width = el.clientWidth || 360, rowH = 34, padTop = 4, axisH = 22;
  const rows = [{ label: baseLabel, total: base }];
  let run = base;
  for (const [name, usd] of deltas) { rows.push({ label: name, start: run, end: run + usd, delta: usd }); run += usd; }
  rows.push({ label: fairLabel, total: fair, connectFrom: run });
  const height = padTop + rows.length * rowH + axisH;
  const values = rows.flatMap(r => r.total != null ? [r.total] : [r.start, r.end]);
  let [lo, hi] = d3.extent(values);
  const pad = Math.max(10, (hi - lo) * 0.12);
  lo -= pad; hi += pad;
  const x = d3.scaleLinear().domain([lo, hi]).range([4, width - 48]);

  const svg = d3.create('svg').attr('width', width).attr('height', height).attr('role', 'img')
    .attr('aria-label', 'How the benchmark is built up from the typical listing');
  const g = svg.append('g');
  const ticks = x.ticks(4);
  g.selectAll('line.hair').data(ticks).join('line').attr('class', 'hair')
    .attr('x1', d => x(d)).attr('x2', d => x(d)).attr('y1', padTop).attr('y2', padTop + rows.length * rowH);
  g.selectAll('text.tick').data(ticks).join('text').attr('class', 'tick')
    .attr('x', d => x(d)).attr('y', padTop + rows.length * rowH + 14).attr('text-anchor', 'middle').text(d => fmtUsd(d));

  rows.forEach((r, i) => {
    const y = padTop + i * rowH;
    g.append('text').attr('x', 0).attr('y', y + 11).attr('class', r.total != null ? 'ink' : '')
      .style('font-weight', r.total != null ? 600 : 400).text(truncate(r.label, 46));
    if (r.total != null) {
      g.append('line').attr('class', 'axis').attr('x1', x(lo)).attr('x2', x(r.total)).attr('y1', y + 23).attr('y2', y + 23);
      g.append('circle').attr('class', 'total').attr('cx', x(r.total)).attr('cy', y + 23).attr('r', 4.5)
        .attr('stroke', '#fcfcfb').attr('stroke-width', 2);
      g.append('text').attr('class', 'ink').attr('x', x(r.total) + 9).attr('y', y + 27).style('font-weight', 600).text(fmtUsd(r.total));
      if (r.connectFrom != null) g.append('line').attr('class', 'axis').attr('x1', x(r.connectFrom)).attr('x2', x(r.connectFrom)).attr('y1', y - rowH + 29).attr('y2', y + 23);
    } else {
      const x0 = x(Math.min(r.start, r.end)), x1 = x(Math.max(r.start, r.end)), pos = r.delta >= 0;
      g.append('path').attr('class', 'delta').attr('d', barPath(x0, x1, y + 17, 11, 4, pos));
      if (i > 1) g.append('line').attr('class', 'axis').attr('x1', x(r.start)).attr('x2', x(r.start)).attr('y1', y - rowH + 29).attr('y2', y + 17);
      const label = fmtSignedUsd(r.delta);
      const atRight = pos ? x1 + 6 : x0 - 6;
      g.append('text').attr('class', 'ink').attr('x', atRight).attr('y', y + 26).attr('text-anchor', pos ? 'start' : 'end').text(label);
    }
  });
  el.replaceChildren(svg.node());
}

// Distribution of price ÷ benchmark on a log axis, with the fair band shaded and an optional marker.
export function histogram(el, values, { band, marker, width, height, markerLabel }) {
  width = width || el.clientWidth || 360; height = height || 110;
  const m = { top: 6, right: 8, bottom: 20, left: 8 };
  const x = d3.scaleLog().domain([0.4, 2.5]).range([m.left, width - m.right]).clamp(true);
  const thresholds = d3.range(Math.log2(0.4), Math.log2(2.5) + 1e-9, (Math.log2(2.5) - Math.log2(0.4)) / 26).map(v => 2 ** v);
  const bins = d3.bin().domain([0.4, 2.5]).thresholds(thresholds)(values.map(v => Math.min(2.499, Math.max(0.4, v))));
  const y = d3.scaleLinear().domain([0, d3.max(bins, b => b.length) || 1]).range([height - m.bottom, m.top]);
  const svg = d3.create('svg').attr('width', width).attr('height', height).attr('role', 'img')
    .attr('aria-label', 'Distribution of price divided by benchmark');
  svg.append('rect').attr('class', 'band').attr('x', x(1 - band)).attr('width', x(1 + band) - x(1 - band)).attr('y', m.top).attr('height', height - m.bottom - m.top);
  svg.append('line').attr('class', 'axis').attr('x1', m.left).attr('x2', width - m.right).attr('y1', height - m.bottom).attr('y2', height - m.bottom);
  svg.selectAll('rect.bar').data(bins).join('rect').attr('class', 'bar')
    .attr('x', b => x(b.x0) + 1).attr('width', b => Math.max(1, x(b.x1) - x(b.x0) - 2))
    .attr('y', b => y(b.length)).attr('height', b => Math.max(0, y(0) - y(b.length)))
    .attr('rx', 2)
    .on('pointermove', (ev, b) => {
      d3.select(ev.currentTarget).classed('hover', true);
      showTip(ev.clientX, ev.clientY, t => {
        t.append(h('b', {}, fmtInt(b.length)), ` listing${b.length === 1 ? '' : 's'}`, h('br'),
          h('span', { class: 'sub' }, `${b.x0.toFixed(2)}× to ${b.x1.toFixed(2)}× the benchmark`));
      });
    })
    .on('pointerleave', ev => { d3.select(ev.currentTarget).classed('hover', false); hideTip(); });
  const ticks = [0.5, 0.7, 1, 1.4, 2];
  svg.selectAll('text.tick').data(ticks).join('text').attr('x', d => x(d)).attr('y', height - 6)
    .attr('text-anchor', 'middle').text(d => d + '×');
  if (marker != null) {
    const mx = x(marker);
    svg.append('line').attr('class', 'marker').attr('x1', mx).attr('x2', mx).attr('y1', m.top - 2).attr('y2', height - m.bottom);
    if (markerLabel) svg.append('text').attr('class', 'ink').attr('x', mx + (mx > width / 2 ? -5 : 5)).attr('y', m.top + 9)
      .attr('text-anchor', mx > width / 2 ? 'end' : 'start').style('font-weight', 600).text(markerLabel);
  }
  el.replaceChildren(svg.node());
}

function truncate(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
