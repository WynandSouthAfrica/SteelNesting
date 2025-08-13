import math
from typing import List, Dict, Tuple
import pandas as pd
import streamlit as st
from fpdf import FPDF
import io
import zipfile
from datetime import datetime

# ────────────────────────────────────────────────────────────────
# App config
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Steel Nesting Planner v13.5", layout="wide")
st.title("🧰 Steel Nesting Planner v13.5 — Multi‑stock × Multi‑cut Nesting + ZIP Export")

# Global settings
KERF_DEFAULT = 2.0  # mm

# ────────────────────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Settings")
kerf = float(st.sidebar.number_input("Kerf (mm)", min_value=0.0, step=0.5, value=KERF_DEFAULT))
st.sidebar.caption("Heuristic: First‑Fit Decreasing per bar. Kerf only between cuts.")

# Optional project metadata (minimal)
st.sidebar.header("📁 Project (optional)")
project_name = st.sidebar.text_input("Project Name", "")
project_location = st.sidebar.text_input("Location", "")
order_no = st.sidebar.text_input("Order No.", "")
material_type = st.sidebar.text_input("Material Type", "")

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
        self.index_in_pool = index_in_pool  # link to stock row
        self.cuts: List[int] = []

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
        new_total = float(sum(self.cuts) + cut_len) + (self.n) * kerf
        return new_total <= self.stock_len + 1e-9

    def add(self, cut_len: int):
        self.cuts.append(int(cut_len))


def first_fit_decreasing_pack(stock_len: int, demand: Dict[int, int]) -> Tuple['BarLayout', Dict[int, int]]:
    bar = BarLayout(stock_len, index_in_pool=-1)
    lengths_desc = sorted([L for L, q in demand.items() if q > 0], reverse=True)

    placed_any = True
    while placed_any and any(demand.values()):
        placed_any = False
        for L in lengths_desc:
            while demand.get(L, 0) > 0 and bar.can_fit(L):
                bar.add(L)
                demand[L] -= 1
                placed_any = True
    return bar, demand


def run_pool_nesting(cuts: pd.DataFrame, stock: pd.DataFrame):
    # Build demand
    demand: Dict[int, int] = {}
    for _, r in cuts.iterrows():
        L = int(r["Cut Length (mm)"])
        q = int(r["Quantity Required"])
        if L > 0 and q > 0:
            demand[L] = demand.get(L, 0) + q

    if not demand:
        return [], {"total_cost": 0.0, "demand_before": {}, "demand_after": {}}, []

    # Stock list preserving row order
    stock_rows = [(
        int(r["Stock Length (mm)"]),
        int(r["Quantity"]),
        float(r["Cost per Meter (optional)"])
    ) for _, r in stock.iterrows() if int(r["Quantity"]) > 0 and int(r["Stock Length (mm)"]) > 0]

    bar_layouts: List[BarLayout] = []
    cost_total = 0.0
    demand_before = demand.copy()

    for row_idx, (Lstock, qty, cpm) in enumerate(stock_rows):
        if cpm > 0:
            cost_total += (Lstock / 1000.0) * cpm * qty
        for _ in range(qty):
            if not any(demand.values()):
                break
            bar, demand = first_fit_decreasing_pack(Lstock, demand)
            bar.index_in_pool = row_idx
            bar_layouts.append(bar)

    # Summary per cut size
    summary_rows = []
    for L, req in sorted(demand_before.items(), reverse=True):
        made = req - demand.get(L, 0)
        summary_rows.append({
            "Cut Length (mm)": L,
            "Required": req,
            "Made": made,
            "Shortfall": max(0, req - made),
        })

    return bar_layouts, {"total_cost": round(cost_total, 2), "demand_before": demand_before, "demand_after": demand}, summary_rows


# ────────────────────────────────────────────────────────────────
# PDF + ZIP helpers
# ────────────────────────────────────────────────────────────────

def bar_string(b: BarLayout) -> str:
    if not b.cuts:
        return f"[empty] | leftover: {b.leftover} mm"
    seg = "|".join(str(x) for x in b.cuts)
    return f"|{seg}|  scrap: {b.leftover} mm"


def build_pdf_report(project: dict, kerf_mm: float, cuts_summary_df: pd.DataFrame, stock_df: pd.DataFrame, layouts: List[BarLayout]) -> bytes:
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    # Header
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 8, 'Steel Nesting Planner – Multi‑stock × Multi‑cut Report', ln=1)
    pdf.set_font('Arial', '', 10)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    meta_line = f"Generated: {ts}   Kerf: {kerf_mm:.2f} mm"
    pdf.cell(0, 5, meta_line, ln=1)

    # Project block
    if any(project.values()):
        pdf.ln(2)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, 'Project', ln=1)
        pdf.set_font('Arial', '', 10)
        for k in ["Project Name", "Location", "Order No.", "Material Type"]:
            v = project.get(k, '')
            if v:
                pdf.cell(0, 5, f"{k}: {v}", ln=1)

    # Cuts summary table
    pdf.ln(2)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 6, 'Fulfilment by Cut Size', ln=1)
    pdf.set_font('Arial', 'B', 9)
    headers = ["Cut (mm)", "Required", "Made", "Shortfall"]
    widths = [30, 30, 30, 30]
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, h, border=1, align='C')
    pdf.ln(6)
    pdf.set_font('Arial', '', 9)
    for _, r in cuts_summary_df.iterrows():
        pdf.cell(widths[0], 6, str(int(r['Cut Length (mm)'])), border=1)
        pdf.cell(widths[1], 6, str(int(r['Required'])), border=1, align='R')
        pdf.cell(widths[2], 6, str(int(r['Made'])), border=1, align='R')
        pdf.cell(widths[3], 6, str(int(r['Shortfall'])), border=1, align='R')
        pdf.ln(6)

    # Stock used header
    pdf.ln(2)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 6, 'Bar‑by‑Bar Layouts', ln=1)

    pdf.set_font('Arial', '', 9)
    # Group by stock row order
    grouped: Dict[int, List[BarLayout]] = {}
    for b in layouts:
        grouped.setdefault(b.index_in_pool, []).append(b)

    for row_idx, group in grouped.items():
        if row_idx is None:
            continue
        # get stock meta
        try:
            stock_len = int(stock_df.iloc[row_idx]["Stock Length (mm)"])
        except Exception:
            stock_len = 0
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(0, 5, f"Stock {stock_len} mm — Bars used: {len(group)}", ln=1)
        pdf.set_font('Arial', '', 9)
        for j, b in enumerate(group, start=1):
            pdf.multi_cell(0, 5, f"Bar {j}: {bar_string(b)}")
        pdf.ln(1)

    # Output bytes
    return bytes(pdf.output(dest='S').encode('latin1'))


def build_cutlist_csv(summary_df: pd.DataFrame) -> bytes:
    out = io.StringIO()
    summary_df.to_csv(out, index=False)
    return out.getvalue().encode('utf-8')


def build_cutlist_txt(layouts: List[BarLayout]) -> bytes:
    out = io.StringIO()
    out.write("CUT LIST (per bar)\n")
")
    for i, b in enumerate(layouts, start=1):
        out.write(f"Bar {i}: {bar_string(b)}
")
    return out.getvalue().encode('utf-8')


def build_zip(project: dict, kerf_mm: float, cuts_summary_df: pd.DataFrame, stock_df: pd.DataFrame, layouts: List[BarLayout]) -> bytes:
    pdf_bytes = build_pdf_report(project, kerf_mm, cuts_summary_df, stock_df, layouts)
    csv_bytes = build_cutlist_csv(cuts_summary_df)
    txt_bytes = build_cutlist_txt(layouts)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, mode='w', compression=zipfile.ZIP_DEFLATED) as z:
        ts = datetime.now().strftime('%Y%m%d_%H%M')
        base = project.get("Project Name", "nesting") or "nesting"
        z.writestr(f"{base}/report_{ts}.pdf", pdf_bytes)
        z.writestr(f"{base}/cutlist_{ts}.csv", csv_bytes)
        z.writestr(f"{base}/cutlist_{ts}.txt", txt_bytes)
    return zbuf.getvalue()


# ────────────────────────────────────────────────────────────────
# Execute
# ────────────────────────────────────────────────────────────────
if cuts_df.empty or stock_df.empty:
    st.warning("Please enter both cuts and stock.")
    st.stop()

layouts, stats, summary_rows = run_pool_nesting(cuts_df, stock_df)

# Summary per cut size
st.subheader("📈 Fulfilment Summary by Cut Size")
summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True)

# Totals & cost
colA = st.columns(3)
colA[0].metric("Unique Cut Sizes", len(summary_df))
colA[1].metric("Total Bars Used", sum(1 for b in layouts if b.n > 0))
colA[2].metric("Estimated Stock Cost", f"R {stats['total_cost']:,.2f}")

# Group layouts by stock row (length)
if layouts:
    st.subheader("🪵 Bar‑by‑Bar Layouts (text view)")
    # Grouped display
    grouped: Dict[int, List[BarLayout]] = {}
    for b in layouts:
        grouped.setdefault(b.index_in_pool, []).append(b)
    for row_idx, group in grouped.items():
        stock_len = int(stock_df.iloc[row_idx]["Stock Length (mm)"]) if row_idx < len(stock_df) else 0
        st.markdown(f"**Stock {stock_len} mm** — Bars used: {len(group)}")
        for j, b in enumerate(group, start=1):
            st.text(f"Bar {j}: {bar_string(b)}")

# Remaining demand
remaining = stats["demand_after"]
if any(remaining.values()):
    st.error("❗Not enough stock to fulfill all cuts.")
    st.json({"Shortfalls": remaining})
else:
    st.success("✅ All required cuts satisfied with given stock pool.")

# ────────────────────────────────────────────────────────────────
# ZIP export
# ────────────────────────────────────────────────────────────────
project = {
    "Project Name": project_name,
    "Location": project_location,
    "Order No.": order_no,
    "Material Type": material_type,
}

if not summary_df.empty:
    zip_bytes = build_zip(project, kerf, summary_df, stock_df.reset_index(drop=True), layouts)
    default_name = (project_name or "nesting") + "_outputs.zip"
    st.download_button(
        label="📦 Download ZIP (Report + Cutlist)",
        data=zip_bytes,
        file_name=default_name,
        mime="application/zip",
    )

st.caption("ZIP contains: PDF report, CSV cutlist, and TXT bar‑by‑bar list. Add more exports on request (per‑bar CSV, JSON, etc.).")

