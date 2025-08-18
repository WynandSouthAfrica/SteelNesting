# Steel Nesting Planner v13.6 — PDF-only (18 Aug 2025)
# Modes: Nest by Required Cuts · Nest from Stock · View Summary Report
# Notes:
# - PDF only (Excel/TXT removed)
# - Per-tag visual bar charts embedded in the PDF
# - Clear per-tag summaries: total cuts, meters ordered, cost/m, total cost
# - "Nest from Stock" uses your stock table; no redundant "Quantity Required" field on stock
# - Adjustable kerf and stock length (global for "Nest by Required Cuts"; multi-length in "Nest from Stock")
# - Optional ZIP with per-tag PDFs; otherwise one consolidated PDF

import io
import math
import tempfile
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from fpdf import FPDF
import matplotlib.pyplot as plt

# ────────────────────────────────────────────────────────────────
# App config
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Steel Nesting Planner v13.6", layout="wide")
st.title("🧰 Steel Nesting Planner v13.6 — PDF-only (18 Aug 2025)")

# Global defaults
KERF_DEFAULT_MM = 2.0
STOCK_DEFAULT_MM = 6000

# ────────────────────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Settings")

kerf_mm = float(
    st.sidebar.number_input("Kerf (mm)", min_value=0.0, step=0.5, value=KERF_DEFAULT_MM)
)

mode = st.sidebar.radio(
    "Mode",
    ["Nest by Required Cuts", "Nest from Stock", "View Summary Report"],
)

# Stock length control (applies to Nest by Required Cuts; "Nest from Stock" uses its own stock table)
stock_choice = st.sidebar.selectbox(
    "Default Stock Length (mm) – for 'Nest by Required Cuts'",
    [6000, 9000, 13000, "Custom"],
    index=0,
)
if stock_choice == "Custom":
    stock_length_mm = int(
        st.sidebar.number_input("Custom Stock Length (mm)", min_value=1, step=10, value=STOCK_DEFAULT_MM)
    )
else:
    stock_length_mm = int(stock_choice)

st.sidebar.write("---")
offer_zip = st.sidebar.checkbox("Also export per-Tag PDFs as ZIP", value=False)

# ────────────────────────────────────────────────────────────────
# Project metadata
# ────────────────────────────────────────────────────────────────
st.header("📁 Project Details")
colA1, colA2 = st.columns(2)
with colA1:
    project_name = st.text_input("Project Name", "PG Bison Extraction Ducts")
    project_location = st.text_input("Project Location", "Ugie")
    person_cutting = st.text_input("Person Cutting", "Wynand")
    supplier_name = st.text_input("Supplier", "Macsteel")
with colA2:
    order_number = st.text_input("Order Number", "PO-001234")
    drawing_number = st.text_input("Drawing Number", "DWG-123")
    revision_number = st.text_input("Revision", "A")
    material_type = st.text_input("Material Type", "Mild Steel")

project_meta = {
    "Project Name": project_name,
    "Location": project_location,
    "Person Cutting": person_cutting,
    "Supplier": supplier_name,
    "Order Number": order_number,
    "Drawing Number": drawing_number,
    "Revision": revision_number,
    "Material": material_type,
    "Date": datetime.now().strftime("%Y-%m-%d"),
}

# ────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────
def clean_float(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def clean_int(x, default=0) -> int:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return int(default)
        return int(round(float(x)))
    except Exception:
        return int(default)

def explode_cuts(length_mm: int, qty: int) -> List[int]:
    return [length_mm] * max(qty, 0)

def first_fit_decreasing(cuts_mm: List[int], stock_len_mm: int, kerf_mm: float) -> List[Dict]:
    """
    Place 'cuts_mm' into bars with given stock_len_mm using FFD.
    Returns list of bars: [{"cuts":[len,...], "used":sum, "waste":w}, ...]
    Kerf is applied between pieces on the same bar (count of joints = n_cuts-1).
    """
    pieces = sorted([int(c) for c in cuts_mm if c > 0], reverse=True)
    bars: List[Dict] = []

    for piece in pieces:
        placed = False
        for bar in bars:
            n = len(bar["cuts"])
            # Additional kerf only if there is already at least one cut on this bar
            needed = piece + (kerf_mm if n > 0 else 0)
            if bar["used"] + needed <= stock_len_mm + 1e-6:
                bar["cuts"].append(piece)
                bar["used"] += needed
                placed = True
                break
        if not placed:
            # Start a new bar
            bars.append({"cuts": [piece], "used": float(piece), "waste": 0.0})

    for bar in bars:
        bar["waste"] = max(stock_len_mm - bar["used"], 0.0)

    return bars

def plot_bars_png(bars: List[Dict], stock_len_mm: int) -> bytes:
    """
    Create a stacked-strip figure (one row per bar) and return PNG bytes.
    """
    if len(bars) == 0:
        fig, ax = plt.subplots(figsize=(8, 1.5))
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=200)
        plt.close(fig)
        return buf.getvalue()

    rows = len(bars)
    height = max(2.0, 0.35 * rows + 1.0)  # scale height by number of bars

    fig, ax = plt.subplots(figsize=(9, height))
    ax.set_xlim(0, stock_len_mm)
    ax.set_ylim(0, rows)
    ax.set_xlabel("mm")
    ax.set_ylabel("Stock Bars")

    # Draw each bar as a line + rectangles for cuts
    for i, bar in enumerate(bars):
        y = rows - i - 0.5
        ax.hlines(y, 0, stock_len_mm, linewidth=1)
        x = 0.0
        for j, cut in enumerate(bar["cuts"]):
            # rectangle [x, x+cut]
            rect = plt.Rectangle((x, y - 0.15), cut, 0.3, fill=True, alpha=0.5)
            ax.add_patch(rect)
            ax.text(x + cut / 2, y, f"{int(cut)}", ha="center", va="center", fontsize=7)
            x += cut
            if j < len(bar["cuts"]) - 1:
                # kerf gap
                x += kerf_mm

        # waste label
        waste = max(stock_len_mm - (x), 0.0)
        ax.text(
            stock_len_mm - 5, y + 0.22, f"Waste: {int(round(waste))} mm",
            ha="right", va="center", fontsize=7
        )

    ax.grid(True, axis="x", linestyle=":", linewidth=0.6)
    ax.set_yticks([])
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    return buf.getvalue()

def mm_to_m(millimetres: float) -> float:
    return float(millimetres) / 1000.0

def per_tag_summary(tag_df: pd.DataFrame, total_bars: int, stock_length_mm: int) -> Dict:
    total_cuts = int(tag_df["Quantity"].sum()) if "Quantity" in tag_df.columns else 0
    total_cut_len_mm = float((tag_df["Cut Length (mm)"] * tag_df["Quantity"]).sum())
    meters_ordered = total_bars * mm_to_m(stock_length_mm)
    # Assume one cost per meter per Tag (take first nonzero or first)
    cost_per_m = 0.0
    if "Cost per meter (ZAR)" in tag_df.columns and len(tag_df) > 0:
        # prefer a nonzero; else fallback to first value
        vals = [clean_float(v, 0.0) for v in tag_df["Cost per meter (ZAR)"].tolist()]
        cost_per_m = next((v for v in vals if v > 0), (vals[0] if len(vals) else 0.0))
    total_cost = meters_ordered * cost_per_m
    return {
        "total_cuts": total_cuts,
        "total_cut_len_mm": total_cut_len_mm,
        "meters_ordered": meters_ordered,
        "cost_per_m": cost_per_m,
        "total_cost": total_cost,
    }

def write_tag_section_to_pdf(pdf: FPDF, tag_name: str, section: str, stock_len_mm: int,
                             kerf_mm: float, tag_df: pd.DataFrame, bars: List[Dict],
                             material: str):
    # Header
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"Tag: {tag_name}   |   Section: {section}", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"Material: {material}    Stock Length: {stock_len_mm} mm    Kerf: {kerf_mm} mm", ln=1)
    pdf.ln(1)

    # Table header
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(50, 7, "Cut Length (mm)", border=1)
    pdf.cell(30, 7, "Quantity", border=1)
    pdf.cell(40, 7, "Cost/m (ZAR)", border=1)
    pdf.cell(60, 7, "Note", border=1, ln=1)

    # Table rows
    pdf.set_font("Helvetica", "", 10)
    for _, r in tag_df.iterrows():
        pdf.cell(50, 7, f"{clean_int(r['Cut Length (mm)'])}", border=1)
        pdf.cell(30, 7, f"{clean_int(r['Quantity'])}", border=1)
        pdf.cell(40, 7, f"{clean_float(r.get('Cost per meter (ZAR)', 0.0)):.2f}", border=1)
        note = str(r.get("Note", "")) if "Note" in tag_df.columns else ""
        pdf.cell(60, 7, note[:30], border=1, ln=1)

    pdf.ln(2)

    # Summary
    sums = per_tag_summary(tag_df, len(bars), stock_len_mm)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Per-Tag Summary:", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"• Total cuts: {sums['total_cuts']}", ln=1)
    pdf.cell(0, 6, f"• Total cut length: {int(round(sums['total_cut_len_mm']))} mm", ln=1)
    pdf.cell(0, 6, f"• Bars used: {len(bars)}  (each {stock_len_mm} mm)", ln=1)
    pdf.cell(0, 6, f"• Meters ordered: {sums['meters_ordered']:.3f} m", ln=1)
    pdf.cell(0, 6, f"• Cost per meter: ZAR {sums['cost_per_m']:.2f}", ln=1)
    pdf.cell(0, 6, f"• Total cost: ZAR {sums['total_cost']:.2f}", ln=1)

    # Visual bar chart
    img_bytes = plot_bars_png(bars, stock_len_mm)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Cut Layout Visualization:", ln=1)
    # Fit image width
    pdf.image(tmp_path, w=190)
    pdf.ln(4)

def build_project_header(pdf: FPDF, meta: Dict):
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"{meta.get('Project Name','')}", ln=1)
    pdf.set_font("Helvetica", "", 11)
    left = [
        ("Location", "Location"),
        ("Person Cutting", "Person Cutting"),
        ("Supplier", "Supplier"),
        ("Order Number", "Order Number"),
    ]
    right = [
        ("Drawing Number", "Drawing Number"),
        ("Revision", "Revision"),
        ("Material", "Material"),
        ("Date", "Date"),
    ]
    y0 = pdf.get_y()
    xL, xR = pdf.get_x(), 110
    pdf.set_xy(xL, y0)
    for key, label in left:
        pdf.set_font("Helvetica", "B", 11); pdf.cell(40, 7, f"{label}:", ln=0)
        pdf.set_font("Helvetica", "", 11); pdf.cell(60, 7, f"{meta.get(key,'')}", ln=1)
    pdf.set_xy(xR, y0)
    for key, label in right:
        pdf.set_font("Helvetica", "B", 11); pdf.cell(40, 7, f"{label}:", ln=0)
        pdf.set_font("Helvetica", "", 11); pdf.cell(60, 7, f"{meta.get(key,'')}", ln=1)
    pdf.ln(2)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

def consolidated_pdf(meta: Dict, tag_payloads: List[Tuple[str, str, int, float, pd.DataFrame, List[Dict]]]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    build_project_header(pdf, meta)

    for idx, (tag, section, stock_len_mm, kerf_mm, tag_df, bars) in enumerate(tag_payloads):
        if idx > 0:
            pdf.add_page()
        write_tag_section_to_pdf(pdf, tag, section, stock_len_mm, kerf_mm, tag_df, bars, meta.get("Material",""))

    return pdf.output(dest="S").encode("latin-1")

def single_tag_pdf(meta: Dict, tag: str, section: str, stock_len_mm: int, kerf_mm: float,
                   tag_df: pd.DataFrame, bars: List[Dict]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    build_project_header(pdf, meta)
    write_tag_section_to_pdf(pdf, tag, section, stock_len_mm, kerf_mm, tag_df, bars, meta.get("Material",""))
    return pdf.output(dest="S").encode("latin-1")

def zip_bytes(files: Dict[str, bytes]) -> bytes:
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()

def group_required_table(df: pd.DataFrame) -> Dict[Tuple[str, str], pd.DataFrame]:
    """
    Group by (Tag, Section). Ensures columns exist.
    """
    cols_needed = ["Tag", "Section", "Cut Length (mm)", "Quantity", "Cost per meter (ZAR)", "Note"]
    for c in cols_needed:
        if c not in df.columns:
            df[c] = np.nan
    # Clean
    df["Tag"] = df["Tag"].fillna("").astype(str)
    df["Section"] = df["Section"].fillna("").astype(str)
    df["Cut Length (mm)"] = df["Cut Length (mm)"].apply(clean_int)
    df["Quantity"] = df["Quantity"].apply(clean_int)
    df["Cost per meter (ZAR)"] = df["Cost per meter (ZAR)"].apply(clean_float)
    df["Note"] = df["Note"].fillna("").astype(str)

    # Filter valid rows
    df = df[(df["Tag"] != "") & (df["Cut Length (mm)"] > 0) & (df["Quantity"] > 0)].copy()
    groups = {}
    for (tag, sect), g in df.groupby(["Tag", "Section"], dropna=False):
        groups[(tag, sect)] = g.reset_index(drop=True)
    return groups

# ────────────────────────────────────────────────────────────────
# Data input tables
# ────────────────────────────────────────────────────────────────
st.header("✏️ Required Cuts")

if mode in ("Nest by Required Cuts", "Nest from Stock"):
    example_req = pd.DataFrame(
        {
            "Tag": ["Duct-A", "Duct-A", "Frame-B"],
            "Section": ["FLAT 50x5", "FLAT 50x5", "ANGLE 50x50x5"],
            "Cut Length (mm)": [1200, 850, 1500],
            "Quantity": [6, 4, 5],
            "Cost per meter (ZAR)": [38.50, 38.50, 62.00],
            "Note": ["Outer frame", "Stiffeners", "Posts"],
        }
    )
    req_df = st.data_editor(
        example_req,
        key="req_df",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Tag": st.column_config.TextColumn(required=False),
            "Section": st.column_config.TextColumn(required=False),
            "Cut Length (mm)": st.column_config.NumberColumn(min_value=1, step=1),
            "Quantity": st.column_config.NumberColumn(min_value=1, step=1),
            "Cost per meter (ZAR)": st.column_config.NumberColumn(min_value=0.0, step=0.1),
            "Note": st.column_config.TextColumn(required=False),
        },
    )

# Stock table only for "Nest from Stock"
if mode == "Nest from Stock":
    st.header("🏷️ Available Stock (by Tag)")
    st.caption("Add one row per stock length for a Tag. **Bars Available** replaces any old 'Quantity Required' fields.")
    example_stock = pd.DataFrame(
        {
            "Tag": ["Duct-A", "Frame-B"],
            "Stock Length (mm)": [6000, 6000],
            "Bars Available": [3, 2],
        }
    )
    stock_df = st.data_editor(
        example_stock,
        key="stock_df",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Tag": st.column_config.TextColumn(),
            "Stock Length (mm)": st.column_config.NumberColumn(min_value=1, step=10),
            "Bars Available": st.column_config.NumberColumn(min_value=0, step=1),
        },
    )
else:
    stock_df = pd.DataFrame(columns=["Tag", "Stock Length (mm)", "Bars Available"])

# ────────────────────────────────────────────────────────────────
# Compute and Export
# ────────────────────────────────────────────────────────────────
st.write("---")
col_run, col_sp = st.columns([1, 3])
with col_run:
    run = st.button("⚙️ Run Nesting & Build PDF", type="primary")

def build_payload_by_required_cuts(req_df: pd.DataFrame, stock_len_mm: int, kerf_mm: float):
    payloads = []
    groups = group_required_table(req_df)
    for (tag, sect), g in groups.items():
        # expand cuts
        pieces = []
        for _, r in g.iterrows():
            pieces.extend(explode_cuts(clean_int(r["Cut Length (mm)"]), clean_int(r["Quantity"])))
        bars = first_fit_decreasing(pieces, stock_len_mm, kerf_mm)
        payloads.append((tag or "UNTAGGED", sect or "-", stock_len_mm, kerf_mm, g, bars))
    return payloads

def build_payload_from_stock(req_df: pd.DataFrame, stock_df: pd.DataFrame, kerf_mm: float):
    """
    For each Tag, create bars from stock_df (multiple lengths allowed).
    Allocate required cuts into those bars. If shortfall, calculate additional bars (using the
    first stock length seen for that Tag; otherwise fallback to 6000).
    """
    payloads = []
    req_groups = group_required_table(req_df)

    # prepare stock info by Tag
    stock_df = stock_df.copy()
    if "Tag" not in stock_df.columns:
        stock_df["Tag"] = ""
    if "Stock Length (mm)" not in stock_df.columns:
        stock_df["Stock Length (mm)"] = 0
    if "Bars Available" not in stock_df.columns:
        stock_df["Bars Available"] = 0

    stock_df["Tag"] = stock_df["Tag"].fillna("").astype(str)
    stock_df["Stock Length (mm)"] = stock_df["Stock Length (mm)"].apply(clean_int)
    stock_df["Bars Available"] = stock_df["Bars Available"].apply(clean_int)

    stock_by_tag: Dict[str, List[Tuple[int, int]]] = {}
    for _, r in stock_df.iterrows():
        if r["Tag"] == "" or r["Stock Length (mm)"] <= 0 or r["Bars Available"] <= 0:
            continue
        stock_by_tag.setdefault(r["Tag"], []).append((int(r["Stock Length (mm)"]), int(r["Bars Available"])))

    for (tag, sect), g in req_groups.items():
        # Create list of required pieces
        pieces = []
        for _, r in g.iterrows():
            pieces.extend(explode_cuts(clean_int(r["Cut Length (mm)"]), clean_int(r["Quantity"])))

        pieces = sorted([p for p in pieces if p > 0], reverse=True)

        # Build stock bars list for this Tag
        inventory = stock_by_tag.get(tag, [])
        # Create actual bar bins: list of dicts each with its own length
        bars: List[Dict] = []
        for length_mm, qty in inventory:
            for _ in range(int(qty)):
                bars.append({"len": length_mm, "cuts": [], "used": 0.0})

        # Place with first-fit decreasing across variable-length bars
        remaining = pieces.copy()
        for piece in remaining[:]:
            placed = False
            for bar in bars:
                needed = piece + (kerf_mm if len(bar["cuts"]) > 0 else 0.0)
                if bar["used"] + needed <= bar["len"] + 1e-6:
                    bar["cuts"].append(piece)
                    bar["used"] += needed
                    placed = True
                    break
            if placed:
                # remove one occurrence from remaining
                remaining.remove(piece)

        # If remaining pieces, estimate additional bars needed using a base length:
        if len(remaining) > 0:
            base_len = inventory[0][0] if len(inventory) > 0 else 6000
            extra_bars = first_fit_decreasing(remaining, base_len, kerf_mm)
            # convert to consistent structure with "len" for plotting
            for b in extra_bars:
                bars.append({"len": base_len, "cuts": b["cuts"][:], "used": b["used"]})

        # Determine dominant length for plotting
        if len(bars) == 0:
            dominant_len = (inventory[0][0] if len(inventory) else 6000)
        else:
            lengths = [b["len"] for b in bars]
            dominant_len = int(pd.Series(lengths).mode().iloc[0])

        # Normalize bars list for figure axis
        normalized_bars = []
        for b in bars:
            used = b["used"] if b["len"] == dominant_len else b["used"] * (dominant_len / max(b["len"], 1))
            normalized_bars.append({"cuts": b["cuts"], "used": used, "waste": max(dominant_len - used, 0.0)})

        payloads.append((tag or "UNTAGGED", sect or "-", dominant_len, kerf_mm, g, normalized_bars))

    return payloads

# Run
if run:
    error_box = st.empty()
    try:
        if mode == "Nest by Required Cuts":
            tag_payloads = build_payload_by_required_cuts(req_df, stock_length_mm, kerf_mm)
        elif mode == "Nest from Stock":
            tag_payloads = build_payload_from_stock(req_df, stock_df, kerf_mm)
        else:
            tag_payloads = []  # View Summary Report will just show summaries below

        if mode in ("Nest by Required Cuts", "Nest from Stock") and len(tag_payloads) == 0:
            st.warning("No valid rows found in Required Cuts. Please add Tag, Cut Length, and Quantity.")
        else:
            # Build consolidated PDF
            if mode in ("Nest by Required Cuts", "Nest from Stock"):
                all_pdf = consolidated_pdf(project_meta, tag_payloads)
                st.download_button(
                    "⬇️ Download Consolidated PDF",
                    data=all_pdf,
                    file_name=f"nesting_{project_meta['Project Name'].replace(' ','_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

                # Optional ZIP with per-tag PDFs
                if offer_zip:
                    files = {}
                    for tag, sect, slen, k, g, bars in tag_payloads:
                        b = single_tag_pdf(project_meta, tag, sect, slen, k, g, bars)
                        safe = f"{tag}_{sect}".replace(" ", "_").replace("/", "-")
                        files[f"{safe}.pdf"] = b
                    z = zip_bytes(files)
                    st.download_button(
                        "⬇️ Download Per-Tag PDFs (ZIP)",
                        data=z,
                        file_name=f"nesting_{project_meta['Project Name'].replace(' ','_')}_per_tag.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )

            # On-screen compact summary
            if mode in ("Nest by Required Cuts", "Nest from Stock"):
                st.write("---")
                st.subheader("📊 Quick On-Screen Summary")
                rows = []
                for tag, sect, slen, k, g, bars in tag_payloads:
                    sums = per_tag_summary(g, len(bars), slen)
                    rows.append(
                        {
                            "Tag": tag,
                            "Section": sect,
                            "Bars Used": len(bars),
                            "Stock Len (mm)": slen,
                            "Total Cuts": sums["total_cuts"],
                            "Total Cut Len (mm)": int(round(sums["total_cut_len_mm"])),
                            "Meters Ordered": round(sums["meters_ordered"], 3),
                            "Cost/m (ZAR)": round(sums["cost_per_m"], 2),
                            "Total Cost (ZAR)": round(sums["total_cost"], 2),
                        }
                    )
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    except Exception as e:
        error_box.error(f"Something went wrong: {e}")

# ────────────────────────────────────────────────────────────────
# View Summary Report (no nesting run required)
# ────────────────────────────────────────────────────────────────
if mode == "View Summary Report":
    st.info("Switch to one of the nesting modes and click **Run Nesting & Build PDF** to generate outputs.")
    st.write("Project summary:")
    st.json(project_meta, expanded=False)
