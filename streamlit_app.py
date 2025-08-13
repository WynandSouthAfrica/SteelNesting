import math
from typing import List, Dict, Tuple
import pandas as pd
import streamlit as st

# ────────────────────────────────────────────────────────────────
# App config
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Steel Nesting Planner v13.4", layout="wide")
st.title("🧰 Steel Nesting Planner v13.4 — Multi‑stock × Multi‑cut Nesting")

# Global settings
KERF_DEFAULT = 2.0  # mm (your preference)

# ────────────────────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Settings")
kerf = float(st.sidebar.number_input("Kerf (mm)", min_value=0.0, step=0.5, value=KERF_DEFAULT))

st.sidebar.caption(
    "Greedy heuristic: First‑Fit Decreasing per bar. Longest remaining cut placed first until no fit."
)

# ────────────────────────────────────────────────────────────────
# Inputs
# ────────────────────────────────────────────────────────────────
st.header("✂️ Cuts Required (multiple sizes)")
init_cuts = pd.DataFrame({
    "Cut Length (mm)": [550, 1200],
    "Quantity Required": [8, 3],
})
cuts_df = st.data_editor(
    init_cuts,
    num_rows="dynamic",
    use_container_width=True,
    key="cuts_table",
)

st.header("📦 Stock Pool (multiple stock lengths)")
init_stock = pd.DataFrame({
    "Stock Length (mm)": [6000, 9000],
    "Quantity": [4, 2],
    "Cost per Meter (optional)": [0.0, 0.0],
})
stock_df = st.data_editor(
    init_stock,
    num_rows="dynamic",
    use_container_width=True,
    key="stock_pool",
)

# Clean inputs
cuts_df = cuts_df.fillna({"Quantity Required": 0})
stock_df = stock_df.fillna({"Quantity": 0, "Cost per Meter (optional)": 0.0})

# Ensure types
if not cuts_df.empty:
    cuts_df["Cut Length (mm)"] = cuts_df["Cut Length (mm)"].astype(int)
    cuts_df["Quantity Required"] = cuts_df["Quantity Required"].astype(int).clip(lower=0)

if not stock_df.empty:
    stock_df["Stock Length (mm)"] = stock_df["Stock Length (mm)"].astype(int)
    stock_df["Quantity"] = stock_df["Quantity"].astype(int).clip(lower=0)
    stock_df["Cost per Meter (optional)"] = stock_df["Cost per Meter (optional)"].astype(float).clip(lower=0)

# ────────────────────────────────────────────────────────────────
# Core helpers
# ────────────────────────────────────────────────────────────────

class BarLayout:
    def __init__(self, stock_len: int, index_in_pool: int):
        self.stock_len = stock_len
        self.index_in_pool = index_in_pool  # for grouping by stock length row
        self.cuts: List[int] = []
        self.used = 0.0

    @property
    def n(self) -> int:
        return len(self.cuts)

    @property
    def kerf_total(self) -> float:
        return max(0, self.n - 1) * kerf

    @property
    def used_with_kerf(self) -> float:
        return float(sum(self.cuts)) + self.kerf_total

    @property
    def leftover(self) -> int:
        return int(round(self.stock_len - self.used_with_kerf))

    def can_fit(self, cut_len: int) -> bool:
        if cut_len <= 0:
            return False
        new_total = float(sum(self.cuts) + cut_len) + (self.n) * kerf  # kerf increases by one if we add a piece
        return new_total <= self.stock_len + 1e-9

    def add(self, cut_len: int):
        self.cuts.append(int(cut_len))


def first_fit_decreasing_pack(stock_len: int, demand: Dict[int, int]) -> Tuple[BarLayout, Dict[int, int]]:
    """Pack one bar of length stock_len using FFD against remaining demand.
    Returns (bar_layout, updated_demand)."""
    bar = BarLayout(stock_len, index_in_pool=-1)

    # sort unique cut lengths by descending
    lengths_desc = sorted([L for L, q in demand.items() if q > 0], reverse=True)

    placed_any = True
    while placed_any and any(demand.values()):
        placed_any = False
        for L in lengths_desc:
            while demand.get(L, 0) > 0 and bar.can_fit(L):
                bar.add(L)
                demand[L] -= 1
                placed_any = True
            # Try next size
    return bar, demand


# ────────────────────────────────────────────────────────────────
# Run the nesting across the pool
# ────────────────────────────────────────────────────────────────

def run_pool_nesting(cuts: pd.DataFrame, stock: pd.DataFrame):
    # Demand map
    demand: Dict[int, int] = {}
    for _, r in cuts.iterrows():
        L = int(r["Cut Length (mm)"])
        q = int(r["Quantity Required"])
        if L > 0 and q > 0:
            demand[L] = demand.get(L, 0) + q

    if not demand:
        return [], {"total_cost": 0.0, "demand_before": {}, "demand_after": {}}, []

    # Stock list [(length, bars, cpm)] preserving row order for cost and reporting
    stock_rows = [(int(r["Stock Length (mm)"]), int(r["Quantity"]), float(r["Cost per Meter (optional)"])) for _, r in stock.iterrows() if int(r["Quantity"]) > 0 and int(r["Stock Length (mm)"]) > 0]

    bar_layouts: List[BarLayout] = []
    cost_total = 0.0
    demand_before = demand.copy()

    for row_idx, (Lstock, qty, cpm) in enumerate(stock_rows):
        # cost accumulation
        if cpm > 0:
            cost_total += (Lstock / 1000.0) * cpm * qty

        for _ in range(qty):
            if not any(demand.values()):
                break
            bar, demand = first_fit_decreasing_pack(Lstock, demand)
            bar.index_in_pool = row_idx
            bar_layouts.append(bar)

    # Build per‑size fulfillment summary
    summary_rows = []
    for L, req in sorted(demand_before.items(), reverse=True):
        done = req - demand.get(L, 0)
        short = max(0, req - done)
        summary_rows.append({
            "Cut Length (mm)": L,
            "Required": req,
            "Made": done,
            "Shortfall": short,
        })

    return bar_layouts, {"total_cost": round(cost_total, 2), "demand_before": demand_before, "demand_after": demand}, summary_rows


# ────────────────────────────────────────────────────────────────
# Execute
# ────────────────────────────────────────────────────────────────
if cuts_df.empty or stock_df.empty:
    st.warning("Please enter both cuts and stock.")
    st.stop()

layouts, stats, summary_rows = run_pool_nesting(cuts_df, stock_df)

# Summary per cut size
st.subheader("📈 Fulfillment Summary by Cut Size")
summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True)

# Totals & cost
colA = st.columns(3)
colA[0].metric("Unique Cut Sizes", len(summary_df))
colA[1].metric("Total Bars Used", sum(1 for b in layouts if b.n > 0))
colA[2].metric("Estimated Stock Cost", f"R {stats['total_cost']:,.2f}")

# Group layouts by stock row (length)
if layouts:
    st.subheader("🪵 Bar‑by‑Bar Layouts")

    # Build simple text visualization per bar
    def bar_string(b: BarLayout) -> str:
        if not b.cuts:
            return f"[empty] | leftover: {b.leftover} mm"
        segments = "|".join(str(x) for x in b.cuts)
        return f"|{segments}|  scrap: {b.leftover} mm"

    # Map row index to metadata
    pool_meta = []
    for i, r in stock_df.iterrows():
        pool_meta.append({"row": i, "stock_len": int(r["Stock Length (mm)"])} )

    # Render grouped
    for row_idx, (Lstock, qty, _cpm) in enumerate([(int(r["Stock Length (mm)"]), int(r["Quantity"]), float(r["Cost per Meter (optional)"])) for _, r in stock_df.iterrows()]):
        group = [b for b in layouts if b.index_in_pool == row_idx]
        if not group:
            continue
        st.markdown(f"**Stock {Lstock} mm** — Bars used: {len(group)}")
        for j, b in enumerate(group, start=1):
            st.text(f"Bar {j}: {bar_string(b)}")

# Leftover demand
remaining = stats["demand_after"]
if any(remaining.values()):
    st.error("❗Not enough stock to fulfill all cuts.")
    st.json({"Shortfalls": remaining})
else:
    st.success("✅ All required cuts satisfied with given stock pool.")

st.caption(
    "Algorithm: First‑Fit Decreasing per bar using the current kerf. "
    "We only insert kerf between pieces, never at the ends."
)
