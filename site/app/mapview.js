// MapLibre wrapper: one GeoJSON source of points, a neighbourhood fill, optional attractions.
import { COLORS } from './labels.js';
import { ratiosOf } from './labels.js';

const STYLE = 'https://tiles.openfreemap.org/styles/positron';
let map, popup, cb = {};

const EMPTY = { type: 'FeatureCollection', features: [] };

export function initMap(callbacks) {
  cb = callbacks;
  map = new maplibregl.Map({
    container: 'map', style: STYLE, center: [-98, 39], zoom: 3, minZoom: 3, maxZoom: 18,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
  return new Promise(resolve => map.on('load', () => { addLayers(); wire(); resolve(map); }));
}

function labelIdx(prop, band) {
  return ['case', ['<', ['get', prop], 1 - band], 0, ['>', ['get', prop], 1 + band], 2, 1];
}
const radius = (k = 0) => ['interpolate', ['linear'], ['zoom'], 9, 2 + k, 12, 3.5 + k, 14, 5.5 + k, 16, 8 + k, 18, 11 + k];

function addLayers() {
  map.addSource('hoods', { type: 'geojson', data: EMPTY });
  map.addSource('listings', { type: 'geojson', data: EMPTY });
  map.addSource('attractions', { type: 'geojson', data: EMPTY });

  map.addLayer({ id: 'hoods-fill', type: 'fill', source: 'hoods', layout: { visibility: 'none' },
    paint: { 'fill-color': 'rgba(0,0,0,0)', 'fill-opacity': 0.62 } });
  map.addLayer({ id: 'hoods-line', type: 'line', source: 'hoods', layout: { visibility: 'none' },
    paint: { 'line-color': '#52514e', 'line-width': 0.7, 'line-opacity': 0.5 } });
  map.addLayer({ id: 'hoods-selected', type: 'line', source: 'hoods', layout: { visibility: 'none' },
    filter: ['==', ['get', 'neighbourhood'], ''],
    paint: { 'line-color': '#0b0b0b', 'line-width': 2.2, 'line-opacity': 0.9 } });
  map.addLayer({ id: 'points', type: 'circle', source: 'listings',
    paint: { 'circle-radius': radius(), 'circle-color': COLORS.fair, 'circle-opacity': 0.85,
             'circle-stroke-color': '#fcfcfb', 'circle-stroke-width': 0.6, 'circle-stroke-opacity': 0.9 } });
  map.addLayer({ id: 'points-compare', type: 'circle', source: 'listings', filter: ['in', ['get', 'id'], ['literal', []]],
    paint: { 'circle-radius': radius(4), 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#6250d6', 'circle-stroke-width': 2.5 } });
  map.addLayer({ id: 'points-selected', type: 'circle', source: 'listings', filter: ['==', ['get', 'id'], ''],
    paint: { 'circle-radius': radius(5), 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#0b0b0b', 'circle-stroke-width': 2.5 } });
  map.addLayer({ id: 'attractions', type: 'circle', source: 'attractions', layout: { visibility: 'none' },
    paint: { 'circle-radius': 5, 'circle-color': '#6250d6', 'circle-stroke-color': '#fcfcfb', 'circle-stroke-width': 2 } });
  map.addLayer({ id: 'attractions-label', type: 'symbol', source: 'attractions', minzoom: 11, layout: { visibility: 'none',
    'text-field': ['get', 'name'], 'text-size': 11, 'text-offset': [0, 1.1], 'text-anchor': 'top', 'text-font': ['Noto Sans Regular'] },
    paint: { 'text-color': '#52514e', 'text-halo-color': '#fcfcfb', 'text-halo-width': 1.2 } });
}

function wire() {
  const box = p => [[p.x - 5, p.y - 5], [p.x + 5, p.y + 5]];
  map.on('click', e => {
    const pts = map.queryRenderedFeatures(box(e.point), { layers: ['points'] });
    if (pts.length) return cb.onPointClick?.(nearest(pts, e.lngLat).properties.id);
    if (map.getLayoutProperty('hoods-fill', 'visibility') === 'visible') {
      const hd = map.queryRenderedFeatures(e.point, { layers: ['hoods-fill'] });
      if (hd.length) return cb.onHoodClick?.(hd[0].properties.neighbourhood, e.lngLat);
    }
    cb.onMapClick?.();
  });
  let last = null;
  map.on('mousemove', e => {
    const pts = map.queryRenderedFeatures(box(e.point), { layers: ['points'] });
    const id = pts.length ? nearest(pts, e.lngLat).properties.id : null;
    map.getCanvasContainer().classList.toggle('pointer', !!id ||
      (map.getLayoutProperty('hoods-fill', 'visibility') === 'visible' && map.queryRenderedFeatures(e.point, { layers: ['hoods-fill'] }).length > 0));
    if (id !== last || id) cb.onHover?.(id, e.originalEvent);
    last = id;
  });
  map.on('mouseout', () => { last = null; cb.onHover?.(null); });
  map.on('movestart', e => { if (e.originalEvent) framed = null; });  // a drag or zoom by the reader, not a move the page made
}
function nearest(features, lngLat) {
  let best = features[0], bd = Infinity;
  for (const f of features) {
    const [x, y] = f.geometry.coordinates, d = (x - lngLat.lng) ** 2 + (y - lngLat.lat) ** 2;
    if (d < bd) { bd = d; best = f; }
  }
  return best;
}

export function setPoints(rows, release, pinned = null) {
  const features = new Array(rows.length);
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i], { ri, re } = ratiosOf(r, release);
    features[i] = { type: 'Feature', geometry: { type: 'Point', coordinates: [r.lon, r.lat] }, properties: { id: r.id, r: ri, re: re ?? ri, s: pinned?.has(r.id) ? 1 : 0 } };
  }
  map.getSource('listings').setData({ type: 'FeatureCollection', features });
}

const PLAIN = '#4f6478';  // control-group view: every dot the same, no label colours

// fade: survey view, where every listing without a pin steps back
export function setBand(band, control = false, fade = false) {
  const dim = base => fade ? ['case', ['==', ['get', 's'], 1], base, 0.16] : base;
  map.setPaintProperty('points', 'circle-stroke-opacity', dim(0.9));
  if (control) {
    map.setPaintProperty('points', 'circle-color', PLAIN);
    map.setPaintProperty('points', 'circle-opacity', dim(0.8));
    return;
  }
  map.setPaintProperty('points', 'circle-color', ['match', labelIdx('r', band), 0, COLORS.under, 2, COLORS.over, COLORS.fair]);
  map.setPaintProperty('points', 'circle-opacity', dim(['case', ['==', labelIdx('r', band), labelIdx('re', band)], 0.88, 0.38]));
}

// Lettered pins for the survey listings: HTML markers, so they sit above every dot and need no map font.
// items: [{ id, letter, lon, lat, color (null = plain), selected }]
let pins = [];
export function setPins(items) {
  for (const p of pins) p.remove();
  pins = items.map(it => {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'pin' + (it.selected ? ' on' : '');
    el.textContent = it.letter;
    el.setAttribute('aria-label', `Listing ${it.letter}`);
    if (it.color) el.style.setProperty('--c', it.color);
    el.addEventListener('click', e => { e.stopPropagation(); cb.onPointClick?.(it.id); });
    el.addEventListener('mouseenter', e => cb.onHover?.(it.id, e));
    el.addEventListener('mousemove', e => e.stopPropagation());  // the map's own hover would hide the tooltip at the pin's edge
    el.addEventListener('mouseleave', () => cb.onHover?.(null));
    return new maplibregl.Marker({ element: el }).setLngLat([it.lon, it.lat]).addTo(map);
  });
}
// Frame a handful of listings (the survey set) instead of the whole city.
let framed = null;  // the rows last framed, until the reader moves the map themself
export function fitRows(rows, duration = 0) {
  if (!rows.length) return;
  const b = new maplibregl.LngLatBounds();
  for (const r of rows) b.extend([r.lon, r.lat]);
  map.fitBounds(b, { padding: 70, maxZoom: 14, duration });
  framed = rows;
}
// Opening a survey listing keeps the overview of all the pins. The card narrows the map, so the pins are
// framed again; once the reader has moved the map, it only pans, without zooming, to a pin that is off screen.
export function showRow(row) {
  map.resize();
  if (framed) fitRows(framed, 300);
  else if (!map.getBounds().contains([row.lon, row.lat])) map.easeTo({ center: [row.lon, row.lat], duration: 500 });
}

export function setSelected(id) { map.setFilter('points-selected', ['==', ['get', 'id'], id ?? '']); }
export function setCompare(ids) { map.setFilter('points-compare', ['in', ['get', 'id'], ['literal', ids]]); }

export function flyToRow(row, minZoom = 14) {
  map.flyTo({ center: [row.lon, row.lat], zoom: Math.max(map.getZoom(), minZoom), speed: 1.4, essential: true });
}
export function fitCity(bounds) {
  framed = null;
  map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 30, duration: 0 });
}

export function setHoods(geojson) { map.getSource('hoods').setData(geojson || EMPTY); }
export function setHoodStyle(colorByName) {
  const on = !!colorByName;
  map.setLayoutProperty('hoods-fill', 'visibility', on ? 'visible' : 'none');
  map.setLayoutProperty('hoods-line', 'visibility', on ? 'visible' : 'none');
  map.setLayoutProperty('hoods-selected', 'visibility', on ? 'visible' : 'none');
  if (!on) return;
  const pairs = [];
  for (const [name, color] of colorByName) pairs.push(name, color);
  map.setPaintProperty('hoods-fill', 'fill-color', pairs.length ? ['match', ['get', 'neighbourhood'], ...pairs, 'rgba(0,0,0,0)'] : 'rgba(0,0,0,0)');
}

export function setAttractions(fc) { map.getSource('attractions').setData(fc || EMPTY); }
export function showAttractions(on) {
  for (const id of ['attractions', 'attractions-label']) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

export function showPopup(lngLat, el) {
  popup?.remove();
  popup = new maplibregl.Popup({ maxWidth: '320px', offset: 6 }).setLngLat(lngLat).setDOMContent(el).addTo(map);
  popup.on('close', () => setHoodSelected(null));
}
export function closePopup() { popup?.remove(); popup = null; }
// Outline one neighbourhood (the one whose popup is open); null clears it.
export function setHoodSelected(name) { map.setFilter('hoods-selected', ['==', ['get', 'neighbourhood'], name ?? '']); }
export function resize() { map?.resize(); }
