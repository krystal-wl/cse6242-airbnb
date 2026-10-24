"""The amenity feature family: nine group flags (``amg_*``) and four single-amenity flags (``am_*``).

The groups are kentxie's ``scripts/amenities_breakout.py`` rules, applied in the same order with the same
override semantics (checked listing by listing on Jersey City). The single flags come from
``docs/features_selection.md`` (Wang & Nicolau 2017). Edit ``AMENITY_FLAGS`` to add a flag; edit
``_AMENITY_GROUP_RULES`` to change a group.
"""
from __future__ import annotations

import json

import pandas as pd

# ---------------------------------------------------------------------------------------------------------
# Amenities (kentxie's scripts/amenities_breakout.py groups + the four flags of docs/features_selection.md)
# ---------------------------------------------------------------------------------------------------------
#: kentxie's grouping, applied in this order to each raw amenity string (a later rule overrides an earlier
#: one, exactly as in the original script). The three groups the script computed but then dropped
#: ("Paid Parking", "Paid Housekeeping", "Coffee") are kept out here too.
_AMENITY_GROUP_RULES: list[tuple[str, str, bool]] = [  # (pattern, group, case_sensitive)
    (r"TV", "amg_entertainment", True),
    (r"sound system", "amg_entertainment", False),
    (r"game", "amg_entertainment", False),
    (r"pool table", "amg_entertainment", False),
    (r"view", "amg_outdoor_views", False),
    (r"grill", "amg_outdoor_views", False),
    (r"backyard", "amg_outdoor_views", False),
    (r"outdoor", "amg_outdoor_views", False),
    (r"balcony", "amg_outdoor_views", False),
    (r"patio", "amg_outdoor_views", False),
    (r"beach", "amg_outdoor_views", False),
    (r"gym", "amg_exercise", False),
    (r"sauna", "amg_luxury_recreation", False),
    (r"fridge", "amg_kitchen_dining", False),
    (r"refrig", "amg_kitchen_dining", False),
    (r"stove", "amg_kitchen_dining", False),
    (r"oven", "amg_kitchen_dining", False),
    (r"kitchen", "amg_kitchen_dining", False),
    (r"body soap", "amg_bathroom_laundry", False),
    (r"shampoo", "amg_bathroom_laundry", False),
    (r"conditioner", "amg_bathroom_laundry", False),
    (r"baby ", "amg_family_pet", False),
    (r"children", "amg_family_pet", False),
    (r"exercise equipment", "amg_exercise", False),
    (r"coffee", "_dropped_coffee", False),
    (r"ethernet", "amg_connectivity", False),
    (r"^(?!.*(?:dishwasher|hair\s*dryer)).*?(?:washer|dryer)", "amg_bathroom_laundry", False),
    (r"^(?=.*free)(?=.*parking)", "amg_parking", False),
    (r"^(?=.*free)(?=.*garage)", "amg_parking", False),
    (r"^(?=.*paid)(?=.*parking)", "_dropped_paid_parking", False),
    (r"^(?=.*paid)(?=.*housekeeping)", "_dropped_paid_housekeeping", False),
    (r"^(?=.*housekeeping)(?=.*extra cost)", "_dropped_paid_housekeeping", False),
    (r"(?:(?:outdoor|indoor)\s+pool|hot\s+tub)", "amg_luxury_recreation", False),
    (r"(?:(?:shared|private)\s+pool)", "amg_luxury_recreation", False),
    (r"^pool$", "amg_luxury_recreation", False),
    (r"wi[- ]?fi", "amg_connectivity", False),
]
AMENITY_GROUPS: list[str] = ["amg_entertainment", "amg_outdoor_views", "amg_luxury_recreation", "amg_kitchen_dining",
                             "amg_family_pet", "amg_exercise", "amg_parking", "amg_bathroom_laundry", "amg_connectivity"]

#: Single-amenity flags from Wang & Nicolau (2017) via docs/features_selection.md, matched on the raw string.
AMENITY_FLAGS: dict[str, str] = {
    "am_wifi": r"\bwi[- ]?fi\b",
    "am_free_parking": r"\bfree\b.*\b(?:parking|garage|carport|driveway)\b",
    "am_smoking_allowed": r"smoking allowed",
    "am_breakfast": r"breakfast",
}


def parse_amenities(s: pd.Series) -> pd.Series:
    """The raw ``amenities`` column (a JSON list in a string) -> Series of Python lists (empty when unreadable)."""
    def _one(x):
        if not isinstance(x, str):
            return []
        try:
            v = json.loads(x)
        except ValueError:
            try:
                import ast
                v = ast.literal_eval(x)
            except (ValueError, SyntaxError):
                return []
        return [str(a) for a in v] if isinstance(v, list) else []
    return s.map(_one)


def _classify_amenity_strings(unique: pd.Index) -> pd.Series:
    """Group label per distinct raw amenity string (kentxie's rules, same order, same override semantics)."""
    label = pd.Series(unique, index=unique, dtype="object")  # starts as the string itself
    for pat, group, cs in _AMENITY_GROUP_RULES:
        hit = label.str.contains(pat, case=cs, regex=True, na=False)
        label[hit] = group
    return label.where(label.isin(AMENITY_GROUPS), other=None)


def amenity_features(df: pd.DataFrame) -> pd.DataFrame:
    """``n_amenities``, nine 0/1 group columns (``amg_*``) and four single-amenity flags (``am_*``)."""
    out = pd.DataFrame(index=df.index)
    if "amenities" not in df:
        return out
    lists = parse_amenities(df["amenities"])
    out["n_amenities"] = lists.map(len).astype(int)
    long = lists.explode().dropna()
    long = long[long.astype(str).str.len() > 0]
    unique = pd.Index(long.unique())
    group_of = _classify_amenity_strings(unique)
    groups = long.map(group_of).dropna()
    hit = pd.crosstab(groups.index, groups).gt(0)
    for g in AMENITY_GROUPS:
        out[g] = hit[g].reindex(df.index, fill_value=False).astype(int) if g in hit else 0
    lower = pd.Series(unique, index=unique).str.lower()
    for col, pat in AMENITY_FLAGS.items():
        matching = set(lower.index[lower.str.contains(pat, regex=True, na=False)])
        flagged = long[long.isin(matching)].index.unique()
        out[col] = df.index.isin(flagged).astype(int)
    return out
