import { state, on, emit } from './state.js';
import { loadCities, loadCity, loadAttractions, parseListingId, readHash, writeHash } from './data.js';
import * as mapview from './mapview.js';
import { initFilters, buildRoomTypes, visibleRows, renderCount, resetFilters } from './filters.js';
import { renderCard, closeCard } from './card.js';
import { renderCompare, MAX_COMPARE } from './compare.js';
import { aggregate, colorScale, renderLegend, hoodPopup, MIN_N } from './hoods.js';
import { verdict, COLORS, LABEL_TEXT } from './labels.js';
import { fmtUsd, fmtInt, fmtShare, fmtPct, fmtDate, fmtMonth, h } from './format.js';
import { showTip, hideTip, initHints } from './tooltip.js';

const $ = s => document.querySelector(s);

async function boot() {
  if (state.control) {  // control-group view: see state.js
    document.body.classList.add('control');
    document.title = 'STR Fair';
    $('#brand-sub').textContent = 'Airbnb listings and their quoted prices';
    state.layers.hoodMetric = 'n';
  }
  initFilters();
  initHints();
  try {
    state.cities = await loadCities();
  } catch (e) {
    $('#loading').hidden = false; $('#loading').textContent = e.message; return;
  }
  const sel = $('#city-select');
  sel.replaceChildren(...state.cities.map(c => h('option', { value: c.slug }, `${c.name} · ${fmtMonth(c.snapshot)}`)));
  sel.addEventListener('change', () => selectCity(sel.value));

  await mapview.initMap({ onPointClick: id => emit('select', id), onHoodClick, onHover, onMapClick: () => mapview.closePopup() });
  state.attractions = await loadAttractions();
  if (state.attractions) {
    $('#attr-label').hidden = false;
    mapview.setAttractions(state.attractions);
  }

  const hash = readHash();
  const slug = state.cities.some(c => c.slug === hash.get('city')) ? hash.get('city') : state.cities[0].slug;
  sel.value = slug;
  await selectCity(slug, hash);
  wireChrome();
}

async function selectCity(slug, hash) {
  const meta = state.cities.find(c => c.slug === slug);
  $('#loading').hidden = false; $('#loading').textContent = `Loading ${meta.name}…`;
  $('#map').classList.add('dim');
  const d = await loadCity(meta);
  Object.assign(state, { city: meta, rows: d.rows, byId: d.byId, metrics: d.metrics, geojson: d.geojson, stub: d.stub,
                         release: 'current', selectedId: null, compare: [], compareOpen: false, hoodAggs: null });
  $('#release-toggle').hidden = !meta.prev_snapshot;
  if (meta.prev_snapshot) {
    $('#release-toggle [data-release=current]').textContent = fmtMonth(meta.snapshot);
    $('#release-toggle [data-release=prev]').textContent = fmtMonth(meta.prev_snapshot);
    setSeg('#release-toggle', $('#release-toggle [data-release=current]'));
  }
  resetFilters();
  buildRoomTypes(d.rows);
  mapview.setHoods(d.geojson);
  mapview.closePopup();
  closeCard();
  mapview.setSelected(null); mapview.setCompare([]);
  renderCompare();
  mapview.fitCity(meta.bounds);
  refresh();
  renderMetrics(); renderCaveat();
  $('#loading').hidden = true; $('#map').classList.remove('dim');
  updateHash();
  const id = hash?.get('id');
  if (hash?.get('release') === 'prev' && meta.prev_snapshot && !state.control) setRelease('prev');
  if (id && state.byId.has(id)) emit('select', id);
}

function refresh() {
  const rows = visibleRows();
  state.visible = rows;
  mapview.setPoints(rows, state.release);
  mapview.setBand(state.band, state.control);
  renderCount(rows.length, state.rows.length);
  if (state.layers.hoods) updateHoodLayer(); else state.hoodAggs = null;
  if (state.selectedId && state.byId.has(state.selectedId)) renderCard(state.byId.get(state.selectedId));
  renderCompare();
  renderMetrics();
  renderCaveat();
}
on('filters', refresh);

on('select', id => {
  const row = state.byId.get(id); if (!row) return;
  state.selectedId = id;
  mapview.setSelected(id);
  mapview.closePopup();
  renderCard(row);
  mapview.flyToRow(row);
  updateHash();
});
on('close-card', () => { state.selectedId = null; mapview.setSelected(null); closeCard(); updateHash(); });

on('toggle-compare', id => {
  const i = state.compare.indexOf(id);
  if (i >= 0) state.compare.splice(i, 1);
  else if (state.compare.length >= MAX_COMPARE) { flash(`You can compare up to ${MAX_COMPARE} listings. Remove one first.`); return; }
  else { state.compare.push(id); state.compareOpen = true; }
  mapview.setCompare(state.compare);
  renderCompare();
  if (state.selectedId === id) renderCard(state.byId.get(id));
  setTimeout(() => mapview.resize(), 50);
});
on('clear-compare', () => { state.compare = []; mapview.setCompare([]); renderCompare(); if (state.selectedId) renderCard(state.byId.get(state.selectedId)); setTimeout(() => mapview.resize(), 50); });
on('toggle-compare-drawer', () => { state.compareOpen = !state.compareOpen; renderCompare(); setTimeout(() => mapview.resize(), 50); });

function setRelease(release) {
  state.release = release;
  setSeg('#release-toggle', $(`#release-toggle [data-release=${release}]`));
  refresh();
  updateHash();
}

function wireChrome() {
  $('#release-toggle').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setRelease(b.dataset.release); });
  $('#search').addEventListener('submit', e => {
    e.preventDefault();
    const id = parseListingId($('#search-input').value);
    const msg = $('#search-msg');
    if (!id) { msg.textContent = 'Paste a listing URL (…/rooms/123…) or a numeric id.'; return; }
    if (!state.byId.has(id)) { msg.textContent = `Not among ${state.city.name}'s priced listings in this release.`; return; }
    msg.textContent = '';
    const row = state.byId.get(id);
    if (!state.visible.includes(row)) { resetFilters(); state.filters.stay = row.monthly ? 'monthly' : 'nightly'; setSeg('#stay-seg', $(`#stay-seg [data-stay=${state.filters.stay}]`)); refresh(); }
    emit('select', id);
  });
  $('#compare-btn').addEventListener('click', () => {
    if (!state.compare.length) { flash('Pin listings from their card to compare them here.'); return; }
    emit('toggle-compare-drawer');
  });
  $('#about-btn').addEventListener('click', () => setCaveat(true));
  $('#filters-btn').addEventListener('click', () => $('#filters').classList.toggle('open'));
  $('#hood-layer').addEventListener('change', e => {
    state.layers.hoods = e.target.checked;
    $('#hood-metric').disabled = !e.target.checked;
    $('#hood-legend').hidden = !e.target.checked;
    if (e.target.checked) updateHoodLayer(); else { mapview.setHoodStyle(null); mapview.closePopup(); }
  });
  $('#hood-metric').addEventListener('change', e => { state.layers.hoodMetric = e.target.value; updateHoodLayer(); });
  $('#attr-layer').addEventListener('change', e => { state.layers.attractions = e.target.checked; mapview.showAttractions(e.target.checked); });
  $('#caveat').addEventListener('click', e => { if (e.target.closest('.head')) setCaveat(!caveatOpen); });
  window.addEventListener('keydown', e => { if (e.key === 'Escape') { if (state.selectedId) emit('close-card'); mapview.closePopup(); } });
}

function updateHoodLayer() {
  const aggs = aggregate(state.visible, state.band, state.release);
  state.hoodAggs = aggs;
  const info = colorScale(state.layers.hoodMetric, aggs);
  const colors = new Map();
  for (const a of aggs.values()) if (a.n >= MIN_N) colors.set(a.hood, info.scale(a[state.layers.hoodMetric]));
  mapview.setHoodStyle(colors);
  renderLegend($('#hood-legend'), info);
}

function onHoodClick(name, lngLat) {
  const a = state.hoodAggs?.get(name);
  const stay = state.filters.stay === 'all' ? '' : state.filters.stay;
  if (a) mapview.showPopup(lngLat, hoodPopup(a, state.band, stay, state.control));
  else mapview.showPopup(lngLat, h('div', { class: 'popup' }, h('h3', {}, name), h('p', { class: 'muted small' }, 'No listings shown here with the current filters.')));
  mapview.setHoodSelected(name);  // after showPopup: closing the previous popup clears the outline
}

function onHover(id, ev) {
  if (!id) { hideTip(); return; }
  const r = state.byId.get(id); if (!r) return;
  const v = verdict(r, state.band, state.release);
  if (state.control) {
    showTip(ev.clientX, ev.clientY, t => {
      t.append(h('b', {}, r.name), h('br'), `${fmtUsd(v.price)} quoted`, h('br'),
        h('span', { class: 'sub' }, `${r.room}, sleeps ${r.guests}${r.monthly ? ' · monthly quote' : ''}`));
    });
    return;
  }
  showTip(ev.clientX, ev.clientY, t => {
    t.append(h('b', {}, r.name), h('br'),
      `${fmtUsd(v.price)} quoted · benchmark ${fmtUsd(v.fair)} · `, h('b', {}, fmtPct(v.ratio)), h('br'),
      h('span', { class: 'sub' }, `${LABEL_TEXT[v.label]}${v.confident ? '' : ' (models disagree)'} · ${r.room}, sleeps ${r.guests}${r.monthly ? ' · monthly quote' : ''}`));
  });
}

function renderMetrics() {
  const m = state.metrics, c = state.city; if (!m || !c) return;
  const el = $('#metrics');
  const parts = [
    h('b', {}, c.name), ` · ${fmtDate(c.snapshot)} snapshot · `,
    h('b', {}, fmtInt(m.n)), ' priced listings, ', h('b', {}, fmtInt(state.visible.length)), ' shown',
  ];
  // one line; the model figures (error, fair share, agreement, label stability) are in the "How to read this map" panel
  if (state.stub && !state.control) parts.push(h('span', { class: 'stub' }, 'Placeholder scores from scripts/stub_scores.py: the team\'s models replace them.'));
  el.replaceChildren(...parts);
}
// the metrics file is fixed at one band; these three follow the slider using the rows in memory (shown in the caveat panel)
function shareAt(band) { let f = 0; for (const r of state.rows) if (verdict(r, band).label === 'fair') f++; return f / state.rows.length; }
function agreeAt(band) { let a = 0; for (const r of state.rows) if (verdict(r, band).confident) a++; return a / state.rows.length; }
function keptAt(band) { let n = 0, k = 0; for (const r of state.rows) { if (r.r_i_prev == null) continue; n++; if (verdict(r, band).label === verdict(r, band, 'prev').label) k++; } return n ? k / n : null; }

// The panel starts as a one-line bar so it does not cover the map; the reader opens it from the bar or from
// "How to read this" in the top bar, and the choice is remembered.
let caveatOpen = false;
try { caveatOpen = localStorage.getItem('strfair-caveat') === ''; } catch {}
function setCaveat(open) {
  caveatOpen = open;
  try { localStorage.setItem('strfair-caveat', open ? '' : '1'); } catch {}
  renderCaveat();
}

function renderCaveat() {
  const c = state.city, m = state.metrics, el = $('#caveat');
  if (!c || !m) return;
  el.hidden = false;
  const collapsed = !caveatOpen;
  el.classList.toggle('collapsed', collapsed);
  if (collapsed) {  // only the bar: skip the per-listing counts below
    el.replaceChildren(h('div', { class: 'head' }, 'How to read this map', h('span', { class: 'muted' }, '▸')));
    return;
  }
  if (state.control) {
    el.replaceChildren(
      h('div', { class: 'head' }, 'How to read this map', h('span', { class: 'muted' }, collapsed ? '▸' : '▾')),
      h('div', { class: 'body' },
        h('p', {}, `Each dot is a listing with a price in the ${fmtMonth(c.snapshot)} Inside Airbnb snapshot of ${c.name}.`),
        h('p', {}, 'Each listing has one dated quote, not a rate card: the price on another date may differ.')));
    return;
  }
  el.replaceChildren(
    h('div', { class: 'head' }, 'How to read this map', h('span', { class: 'muted' }, collapsed ? '▸' : '▾')),
    h('div', { class: 'body' },
      h('p', {}, `Each dot is a listing with a price in the ${fmtMonth(c.snapshot)} Inside Airbnb snapshot of ${c.name}. Its label compares that quoted price with a benchmark: what similar listings in the same city quoted at the same time, allowing for size, location, amenities, reviews and when the quote was taken.`),
      h('p', {}, 'Each listing has one dated quote, not a rate card: the price on another date may differ. The data record no bookings, so a label is relative market value, not a true price.'),
      h('p', {}, `A linear model explains the benchmark in dollars; a random forest checks it. Lighter dots are where the two disagree. Typical benchmark error here: ±${fmtUsd(m.nightly?.median_abs_err_usd)} per night on nightly quotes.`),
      h('p', {}, `With the fair band at ±${Math.round(state.band * 100)}%: `, h('b', {}, fmtShare(shareAt(state.band))), ' of listings are fairly priced, the two models agree on ', h('b', {}, fmtShare(agreeAt(state.band))),
        m.previous?.kept_label_share != null ? [', and ', h('b', {}, fmtShare(keptAt(state.band))), ` kept their label since ${fmtMonth(m.previous.snapshot)}`] : null, '.'),
      state.stub ? h('p', { style: { color: COLORS.over } }, 'Scores on this page come from a placeholder model so the map could be built; the team\'s models replace them.') : null,
    ));
}

function setSeg(sel, btn) { for (const b of document.querySelectorAll(sel + ' button')) b.classList.toggle('on', b === btn); }
function updateHash() { writeHash({ city: state.city?.slug, id: state.selectedId, release: state.release === 'prev' ? 'prev' : null }); }
let flashTimer;
function flash(text) { const m = $('#search-msg'); m.textContent = text; clearTimeout(flashTimer); flashTimer = setTimeout(() => { m.textContent = ''; }, 4000); }

boot().catch(e => { console.error(e); const l = $('#loading'); l.hidden = false; l.textContent = 'Something went wrong: ' + e.message; });
