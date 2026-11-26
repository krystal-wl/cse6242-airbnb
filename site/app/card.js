// The listing card: verdict, quote context, why (waterfall), the listing, comparables, between releases, neighbourhood context.
import { state, emit } from './state.js';
import { verdict, labelOf, COLORS, LABEL_TEXT } from './labels.js';
import { fmtUsd, fmtSignedUsd, fmtPct, fmtInt, fmtDate, fmtMonth, fmtRatio, plural, h } from './format.js';
import { waterfall, histogram } from './charts.js';

const $card = () => document.getElementById('card');

function tag(label, extra) {
  return h('span', { class: 'tag', style: { '--c': COLORS[label] } }, h('span', { class: 'dot' }), LABEL_TEXT[label], extra);
}

export function closeCard() {
  const c = $card(); c.hidden = true; c.replaceChildren();
}

export function renderCard(row) {
  const { band, city, control } = state;
  const v = verdict(row, band, 'current');
  const gapUsd = row.price - row.fair_i;
  const card = $card();
  const keepScroll = card.dataset.id === row.id ? card.scrollTop : 0;  // re-rendering the same listing keeps the reader's place
  card.dataset.id = row.id;
  card.hidden = false;

  const head = h('div', { class: 'card-head' },
    h('h2', {}, row.name || `Listing ${row.id}`),
    h('button', { class: 'close', 'aria-label': 'Close', onclick: () => emit('close-card') }, '×'));

  const agreeText = v.confident
    ? `Both models agree (random forest benchmark ${fmtUsd(row.fair_e)}).`
    : `The two models disagree: the random forest puts the benchmark at ${fmtUsd(row.fair_e)}, which would make it ${LABEL_TEXT[v.labelEns].toLowerCase()}.`;
  const verdictBlock = control
    ? h('div', { class: 'block' }, h('div', { class: 'verdict' },
        h('div', {}, h('div', { class: 'lbl' }, 'Quoted per night'), h('div', { class: 'big' }, fmtUsd(row.price)))))
    : h('div', { class: 'block' },
    h('div', { class: 'verdict' },
      h('div', {}, h('div', { class: 'lbl' }, 'Quoted per night'), h('div', { class: 'big' }, fmtUsd(row.price))),
      h('div', {}, h('div', { class: 'lbl' }, 'Benchmark for a place like this'), h('div', { class: 'big' }, fmtUsd(row.fair_i))),
      h('div', { class: 'gap' }, tag(v.label), h('span', {}, h('b', {}, fmtPct(v.ratio)), ` (${fmtSignedUsd(gapUsd)} vs. the benchmark)`)),
    ),
    h('p', { class: 'agree' }, agreeText));

  const quote = control
    ? (row.monthly
      ? `This is a monthly quote: ${plural(row.nights, 'night')} from ${fmtDate(row.checkin)}, so the rate is per night after a long-stay discount.`
      : `This quote was for ${plural(row.nights, 'night')} from ${fmtDate(row.checkin)}, captured ${plural(row.lead, 'day')} ahead; the price on another date may differ.`)
    : row.monthly
    ? `This is a monthly quote: ${plural(row.nights, 'night')} from ${fmtDate(row.checkin)}, so the rate is per night after a long-stay discount. It is compared with other monthly quotes only.`
    : `This quote was for ${plural(row.nights, 'night')} from ${fmtDate(row.checkin)}, captured ${plural(row.lead, 'day')} ahead. The benchmark controls for that timing; the price on another date may differ.`;
  const quoteBlock = h('div', { class: 'block' }, h('h3', {}, 'The quote'), h('p', { class: 'quote-ctx' }, quote));

  const whyBlock = h('div', { class: 'block' }, h('h3', {}, 'Why the benchmark is ' + fmtUsd(row.fair_i)));
  const chart = h('div', { class: 'chart' });
  const stayWord = row.monthly ? 'monthly' : 'nightly';
  const base = state.metrics?.base_price?.[stayWord] ?? row.fair_i;
  whyBlock.append(chart, h('p', { class: 'hint' },
    `Starting from the typical ${stayWord} listing in ${city.name} (${fmtUsd(base)} per night), each row is what this listing's features add or take away, in dollars.`));

  const facts = h('div', { class: 'facts' },
    h('span', {}, h('b', {}, row.room)),
    h('span', {}, 'sleeps ', h('b', {}, fmtInt(row.guests))),
    row.bedrooms != null && h('span', {}, h('b', {}, fmtInt(row.bedrooms)), row.bedrooms === 1 ? ' bedroom' : ' bedrooms'),
    row.baths != null && h('span', {}, h('b', {}, String(row.baths)), row.baths === 1 ? ' bath' : ' baths'),
    row.rating != null ? h('span', {}, '★ ', h('b', {}, row.rating.toFixed(2)), ` (${plural(row.reviews, 'review')})`) : h('span', { class: 'muted' }, 'no reviews yet'),
    row.superhost ? h('span', {}, h('b', {}, 'Superhost')) : null,
    h('span', {}, h('b', {}, row.km?.toFixed(1)), ' km from the centre'),
    h('span', {}, row.hood),
  );
  // the map's data files carry no listing_url; an Airbnb listing's address is its id
  const airbnbUrl = row.listing_url || `https://www.airbnb.com/rooms/${encodeURIComponent(row.id)}`;
  const listingBlock = h('div', { class: 'block' }, h('h3', {}, 'The listing'), facts,
    h('p', { style: { margin: '10px 0 0' } }, h('a', { href: airbnbUrl, target: '_blank', rel: 'noopener' }, 'View on Airbnb ↗'),
      h('span', { class: 'muted small' }, `  ·  id ${row.id}`)));

  const compsBlock = h('div', { class: 'block' }, h('h3', {}, 'Similar listings nearby'));
  const comps = (row.comps || []).map(id => state.byId.get(id)).filter(Boolean);
  if (comps.length) {
    const table = h('table', { class: 'comps' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Listing'), h('th', { class: 'num' }, 'Price'), !control && h('th', { class: 'num' }, 'Benchmark'), !control && h('th', { class: 'num' }, 'vs.'))),
      h('tbody', {}, ...comps.map(c => {
        const cv = verdict(c, band, 'current');
        return h('tr', { class: 'row', onclick: () => emit('select', c.id) },
          h('td', { class: 'name', title: c.name }, !control && h('span', { class: 'dot', style: { '--c': COLORS[cv.label] } }), c.name),
          h('td', { class: 'num' }, fmtUsd(c.price)), !control && h('td', { class: 'num' }, fmtUsd(c.fair_i)), !control && h('td', { class: 'num' }, fmtPct(cv.ratio)));
      })));
    compsBlock.append(table, h('p', { class: 'hint' }, `Same room type and stay type, bedrooms within one, nearest first. Click a row to open it.`));
  } else {
    compsBlock.append(h('p', { class: 'muted small' }, 'No similar listing within 3 km.'));
  }

  let prevBlock = null;
  if (city.prev_snapshot && !control) {
    const prevMonth = fmtMonth(city.prev_snapshot), curMonth = fmtMonth(city.snapshot);
    if (row.r_i_prev != null) {
      const pv = verdict(row, band, 'prev');
      const same = pv.label === v.label;
      prevBlock = h('div', { class: 'block' }, h('h3', {}, 'Between releases'),
        h('p', { class: 'quote-ctx' },
          `In the ${prevMonth} release this listing quoted ${fmtUsd(row.price_prev)} against a benchmark of ${fmtUsd(row.fair_i_prev)} (${fmtPct(pv.ratio)}): `,
          tag(pv.label), same ? ` — the same label as in ${curMonth}.` : ` — a different label from ${curMonth}, so treat the label with care.`));
    } else {
      prevBlock = h('div', { class: 'block' }, h('h3', {}, 'Between releases'),
        h('p', { class: 'muted small' }, `Not priced in the ${prevMonth} release, so there is no second label to compare.`));
    }
  }

  const hoodRows = state.rows.filter(r => r.hood === row.hood && !!r.monthly === !!row.monthly);
  const ratios = hoodRows.map(r => r.r_i);
  const pct = Math.round(100 * ratios.filter(x => x < row.r_i).length / Math.max(1, ratios.length));
  const hoodBlock = h('div', { class: 'block' }, h('h3', {}, 'In its neighbourhood'));
  const hchart = h('div', { class: 'chart' });
  hoodBlock.append(hchart, h('p', { class: 'hint' },
    `Price ÷ benchmark for the ${fmtInt(hoodRows.length)} ${row.monthly ? 'monthly' : 'nightly'} listings in ${row.hood}; this one sits above ${pct}% of them. Shaded: the fair band.`));

  const pinned = state.compare.includes(row.id);
  const actions = h('div', { class: 'actions' },
    h('button', { class: 'btn ' + (pinned ? '' : 'primary'), onclick: () => emit('toggle-compare', row.id) }, pinned ? 'Unpin from compare' : 'Pin to compare'),
    h('button', { class: 'btn ghost', onclick: () => { navigator.clipboard?.writeText(location.href); } }, 'Copy link'));

  // control-group view: price, quote, the listing and similar listings; nothing derived from the models
  const blocks = control ? [head, verdictBlock, quoteBlock, listingBlock, compsBlock, actions]
    : [head, verdictBlock, quoteBlock, whyBlock, listingBlock, compsBlock, prevBlock, hoodBlock, actions];
  card.replaceChildren(...blocks.filter(Boolean));
  card.scrollTop = keepScroll;
  if (control) return;

  waterfall(chart, {
    base, baseLabel: `Typical ${stayWord} listing in ${city.name}`,
    fair: row.fair_i, fairLabel: 'Benchmark for this listing',
    deltas: (row.contrib || []).map(([name, usd]) => [name, usd]),
  });
  histogram(hchart, ratios, { band, marker: row.r_i, markerLabel: 'this listing', height: 100 });
}
