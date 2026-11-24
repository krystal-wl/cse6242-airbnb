// The label is computed in the browser from the shipped ratios, so the band slider needs no rebuild.
export const COLORS = { under: '#2a78d6', fair: '#8a8880', over: '#eb6834' };
export const LABEL_TEXT = { under: 'Underpriced', fair: 'Fairly priced', over: 'Overpriced' };
export const LABEL_SHORT = { under: 'under', fair: 'fair', over: 'over' };

export function labelOf(ratio, band) {
  if (ratio == null || isNaN(ratio)) return null;
  return ratio < 1 - band ? 'under' : ratio > 1 + band ? 'over' : 'fair';
}

// ratios of the release being shown; the card always explains the current quote
export function ratiosOf(row, release) {
  return release === 'prev'
    ? { ri: row.r_i_prev, re: row.r_e_prev, price: row.price_prev, fair: row.fair_i_prev }
    : { ri: row.r_i, re: row.r_e, price: row.price, fair: row.fair_i };
}

export function verdict(row, band, release = 'current') {
  const { ri, re, price, fair } = ratiosOf(row, release);
  const label = labelOf(ri, band), labelEns = labelOf(re, band);
  return { label, labelEns, confident: label != null && label === labelEns, ratio: ri, ratioEns: re, price, fair };
}
