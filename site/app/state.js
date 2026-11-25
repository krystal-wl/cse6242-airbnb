// One shared state object plus a minimal event bus; views subscribe to the events main.js emits.
const listeners = new Map();

export const state = {
  // Control-group view for the user test, opened with ?v=b: the same map, filters and listings, with every
  // model output (benchmark, labels, ratios, waterfall) left out. A link parameter, not a control on the
  // page, so a participant cannot switch it; the name says nothing about which group the link is for.
  control: new URLSearchParams(location.search).get('v') === 'b',
  cities: [], city: null,            // city = the entry from cities.json
  rows: [], byId: new Map(), visible: [], metrics: null, geojson: null, attractions: null,
  band: 0.20, release: 'current',
  filters: {
    stay: 'nightly', rooms: null, guests: 0, bedrooms: 0, priceMin: null, priceMax: null,
    labels: new Set(['under', 'fair', 'over']), confidentOnly: false,
  },
  layers: { hoods: false, hoodMetric: 'median_ratio', attractions: false },
  hoodAggs: null,
  selectedId: null, compare: [],
};

export function on(evt, fn) {
  if (!listeners.has(evt)) listeners.set(evt, []);
  listeners.get(evt).push(fn);
}
export function emit(evt, payload) {
  for (const fn of listeners.get(evt) || []) fn(payload);
}
