import { state, emit } from './state.js';
import { verdict } from './labels.js';
import { fmtInt, h } from './format.js';

const ROOM_ORDER = ['Entire home/apt', 'Private room', 'Hotel room', 'Shared room'];
const $ = s => document.querySelector(s);

export function passes(row, f, band, release) {
  if (release === 'prev' && row.r_i_prev == null) return false;
  if (f.stay === 'nightly' && row.monthly) return false;
  if (f.stay === 'monthly' && !row.monthly) return false;
  if (f.rooms && !f.rooms.has(row.room)) return false;
  if (f.guests && (row.guests == null || row.guests < f.guests)) return false;
  if (f.bedrooms && (row.bedrooms == null || row.bedrooms < f.bedrooms)) return false;
  if (f.priceMin != null && row.price < f.priceMin) return false;
  if (f.priceMax != null && row.price > f.priceMax) return false;
  const v = verdict(row, band, release);
  if (!f.labels.has(v.label)) return false;
  if (f.confidentOnly && !v.confident) return false;
  return true;
}

export function visibleRows() {
  const { filters, band, release } = state;
  return state.rows.filter(r => passes(r, filters, band, release));
}

function setSeg(sel, btn) {
  for (const b of document.querySelectorAll(sel + ' button')) b.classList.toggle('on', b === btn);
}

export function initFilters() {
  $('#stay-seg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    state.filters.stay = b.dataset.stay; setSeg('#stay-seg', b); emit('filters');
  });
  $('#guests').addEventListener('change', e => { state.filters.guests = +e.target.value; emit('filters'); });
  $('#bedrooms').addEventListener('change', e => { state.filters.bedrooms = +e.target.value; emit('filters'); });
  const price = () => {
    const a = $('#price-min').value, b = $('#price-max').value;
    state.filters.priceMin = a === '' ? null : +a;
    state.filters.priceMax = b === '' ? null : +b;
    emit('filters');
  };
  $('#price-min').addEventListener('change', price);
  $('#price-max').addEventListener('change', price);
  $('#label-checks').addEventListener('change', e => {
    const cb = e.target;
    if (cb.dataset.label) cb.checked ? state.filters.labels.add(cb.dataset.label) : state.filters.labels.delete(cb.dataset.label);
    else if (cb.id === 'confident-only') state.filters.confidentOnly = cb.checked;
    emit('filters');
  });
  $('#band').addEventListener('input', e => {
    state.band = +e.target.value / 100;
    $('#band-val').textContent = `±${e.target.value}%`;
    emit('filters');
  });
  $('#room-types').addEventListener('change', () => {
    const boxes = [...document.querySelectorAll('#room-types input')];
    const on = boxes.filter(b => b.checked).map(b => b.value);
    state.filters.rooms = on.length === boxes.length ? null : new Set(on);
    emit('filters');
  });
  $('#reset-btn').addEventListener('click', () => { resetFilters(); emit('filters'); });
}

export function buildRoomTypes(rows) {
  const counts = new Map();
  for (const r of rows) counts.set(r.room, (counts.get(r.room) || 0) + 1);
  const types = [...counts.keys()].sort((a, b) => (ROOM_ORDER.indexOf(a) + 99) % 100 - (ROOM_ORDER.indexOf(b) + 99) % 100);
  const box = $('#room-types');
  box.replaceChildren(...types.map(t => h('label', {},
    h('input', { type: 'checkbox', value: t, checked: true }), t,
    h('span', { class: 'muted small', style: { marginLeft: 'auto' } }, fmtInt(counts.get(t))))));
  state.filters.rooms = null;
}

export function resetFilters() {
  const f = state.filters;
  Object.assign(f, { stay: 'nightly', rooms: null, guests: 0, bedrooms: 0, priceMin: null, priceMax: null, confidentOnly: false });
  f.labels = new Set(['under', 'fair', 'over']);
  setSeg('#stay-seg', $('#stay-seg button[data-stay=nightly]'));
  $('#guests').value = '0'; $('#bedrooms').value = '0';
  $('#price-min').value = ''; $('#price-max').value = '';
  for (const cb of document.querySelectorAll('#label-checks input[data-label]')) cb.checked = true;
  $('#confident-only').checked = false;
  for (const cb of document.querySelectorAll('#room-types input')) cb.checked = true;
}

export function renderCount(nShown, nTotal) {
  const el = $('#count');
  el.replaceChildren(h('strong', {}, fmtInt(nShown)), ` of ${fmtInt(nTotal)} priced listings shown`);
}
