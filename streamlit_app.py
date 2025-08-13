import math
import pandas as pd
import streamlit as st

# ────────────────────────────────────────────────────────────────
# App config
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Steel Nesting Planner v13.3", layout="wide")
st.title("🧰 Steel Nesting Planner v13.3 — Nest from Stock (Multi‑stock pool)")

# Global settings
KERF_DEFAULT = 2  # mm (you asked for 2 mm previously)

# ────────────────────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Settings")
kerf = st.sidebar.number_input("Kerf (mm)", min_value=0.0, step=0.5, value=float(KERF_DEFAULT))

# ────────────────────────────────────────────────────────────────
# Inputs
# ────────────────────────────────────────────────────────────────
st.header("📏 Cut Definition")
col_cut = st.columns(2)
with col_cut[0]:
    cut_len = st.number_input("Cut Length (mm)", min_value=1, step=1, value=550)
with col_cut[1]:
    target_qty = st.number_input("Target Pieces (optional)", min_value=0, step=1, value=0, help="If > 0, we'll show how many bars are needed to hit this target")

st.header("📦 Stock Pool (multiple stock lengths)")
help_txt = (
    "Add each distinct stock length you have and how many bars of that length are on hand.\n"
    "The nesting will pull from this entire pool."
)
st.caption(help_txt)

# Editable stock table
init_rows = pd.DataFrame({
    "Stock Length (mm)": [6000],
    "Quantity": [4],
    "Cost per Meter (optional)": [0.0],
})
stock_df = st.data_editor(
    init_rows,
    num_rows="dynamic",
    use_container_width=True,
    key="stock_pool_editor",
)

# Clean input
stock_df = stock_df.fillna({"Quantity": 0, "Cost per Meter (optional)": 0.0})
stock_df["Stock Length (mm)"] = stock_df["Stock Length (mm)"].astype(int)
stock_df["Quantity"] = stock_df["Quantity"].astype(int).clip(lower=0)
stock_df["Cost per Meter (optional)"] = stock_df["Cost per Meter (optional)"].astype(float).clip(lower=0)

# ────────────────────────────────────────────────────────────────
# Core helpers
# ────────────────────────────────────────────────────────────────

def pieces_per_bar(stock_len: int, cut: int, kerf_mm: float) -> tuple[int, int]:
    """Return (pieces, leftover_mm) for a single bar.
    Formula: n = floor((L + kerf) / (cut + kerf)).
    leftover = L - n*cut - (n-1)*kerf  (for n>0). If n==0, leftover=L.
    """
    if cut <= 0 or stock_len <= 0:
        return 0, stock_len
    denom = cut + kerf_mm
    if denom <= 0:
        return 0, stock_len
    n = int(math.floor((stock_len + kerf_mm) / denom))
    if n <= 0:
        return 0, stock_len
    leftover = stock_len - n * cut - max(0, n - 1) * kerf_mm
    return n, int(round(leftover))


def compute_pool_breakdown(df: pd.DataFrame, cut: int, kerf_mm: float):
    rows = []
    total_pieces = 0
    total_bars = 0
    total_cost = 0.0

    for _, r in df.iterrows():
        L = int(r["Stock Length (mm)"])
        qty = int(r["Quantity"])
        cpm = float(r["Cost per Meter (optional)"])
        if qty <= 0 or L <= 0:
            continue
        n_per_bar, leftover = pieces_per_bar(L, cut, kerf_mm)
        pieces = n_per_bar * qty
        cost = (L / 1000.0) * cpm * qty if cpm > 0 else 0.0
        rows.append({
            "Stock Length (mm)": L,
            "Bars": qty,
            "Pieces/Bar": n_per_bar,
            "Total Pieces": pieces,
            "Leftover per Bar (mm)": leftover,
            "Cost per Meter": cpm if cpm > 0 else None,
            "Estimated Cost": round(cost, 2) if cost > 0 else None,
        })
        total_pieces += pieces
        total_bars += qty
        total_cost += cost

    return pd.DataFrame(rows), total_pieces, total_bars, round(total_cost, 2)


# ────────────────────────────────────────────────────────────────
# Compute & display
# ────────────────────────────────────────────────────────────────
if cut_len <= 0:
    st.warning("Enter a valid cut length.")
    st.stop()

breakdown_df, total_pcs, total_bars, total_cost = compute_pool_breakdown(stock_df, cut_len, kerf)

st.subheader("📊 Stock Utilization")
st.dataframe(breakdown_df, use_container_width=True)

# Totals
col_tot = st.columns(4)
col_tot[0].metric("Total Bars", total_bars)
col_tot[1].metric("Total Pieces Possible", total_pcs)
col_tot[2].metric("Kerf (mm)", kerf)
col_tot[3].metric("Estimated Total Cost", f"R {total_cost:,.2f}")

# If a target was provided, estimate bars needed
if target_qty and target_qty > 0:
    st.subheader("🎯 Bars Required for Target Pieces")
    # Greedy: consume bars in the order given until we hit target
    remaining = target_qty
    used_rows = []
    for _, r in stock_df.iterrows():
        L = int(r["Stock Length (mm)"])
        qty = int(r["Quantity"])
        if qty <= 0:
            continue
        n_per_bar, _ = pieces_per_bar(L, cut_len, kerf)
        if n_per_bar <= 0:
            continue
        bars_needed = math.ceil(remaining / n_per_bar)
        take = min(qty, bars_needed)
        got = take * n_per_bar
        used_rows.append({"Stock Length (mm)": L, "Bars Used": take, "Pieces From These Bars": got})
        remaining -= got
        if remaining <= 0:
            break

    used_df = pd.DataFrame(used_rows)
    total_used_bars = int(used_df["Bars Used"].sum()) if not used_df.empty else 0
    made = int(used_df["Pieces From These Bars"].sum()) if not used_df.empty else 0
    st.dataframe(used_df, use_container_width=True)
    if remaining > 0:
        st.error(f"Not enough stock to reach {target_qty} pieces. You will be short by {remaining}.")
    st.metric("Bars Needed (given pool order)", total_used_bars)
    st.metric("Pieces Achieved", made)

st.info(
    "This screen purposefully **removes** 'Quantity Required' for the mode and instead tells you what your pool can yield. "
    "Optionally set a Target Pieces number to estimate how many bars will be consumed.")
