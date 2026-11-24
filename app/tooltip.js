const el = () => document.getElementById('tooltip');

export function showTip(x, y, build) {
  const t = el();
  t.replaceChildren();
  build(t);
  t.hidden = false;
  const w = t.offsetWidth, hgt = t.offsetHeight;
  const left = Math.min(x + 14, window.innerWidth - w - 8);
  const top = y + 14 + hgt > window.innerHeight ? y - hgt - 10 : y + 14;
  t.style.left = left + 'px';
  t.style.top = top + 'px';
}
export function hideTip() { el().hidden = true; }
