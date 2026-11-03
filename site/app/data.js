// Loading the files scripts/build_map_data.py writes under site/data/.
const DATA = 'data/';

export async function loadCities() {
  const r = await fetch(DATA + 'cities.json');
  if (!r.ok) throw new Error('site/data/cities.json is missing: run `python scripts/build_map_data.py --all`');
  return r.json();
}

export async function loadCity(meta) {
  const [listings, metrics, geojson] = await Promise.all([
    fetch(DATA + meta.files.listings).then(r => r.json()),
    fetch(DATA + meta.files.metrics).then(r => r.json()),
    fetch(DATA + meta.files.geojson).then(r => r.json()),
  ]);
  const c = listings.columns, n = listings.n, keys = Object.keys(c);
  const rows = new Array(n), byId = new Map();
  for (let i = 0; i < n; i++) {
    const o = {};
    for (const k of keys) o[k] = c[k][i];
    rows[i] = o;
    byId.set(o.id, o);
  }
  return { rows, byId, metrics, geojson, snapshot: listings.snapshot, prev: listings.prev_snapshot, stub: !!listings.stub };
}

export async function loadAttractions() {
  try {
    const r = await fetch(DATA + 'attractions.json');
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

// "https://www.airbnb.com/rooms/12345?x=y", "airbnb.ca/rooms/plus/12345" or a bare id
export function parseListingId(text) {
  const s = String(text || '').trim();
  const m = s.match(/rooms\/(?:plus\/)?(\d+)/) || s.match(/^(\d{4,})$/);
  return m ? m[1] : null;
}

export function readHash() {
  return new URLSearchParams(location.hash.replace(/^#/, ''));
}
export function writeHash(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '' && v !== false) p.set(k, v);
  const next = '#' + p.toString();
  if (next !== location.hash) history.replaceState(null, '', next);
}
