# Steel Nesting Planner v13.7 — PG Bison Header + Section-Based PDF (18 Aug 2025)
# Modes: Nest by Required Cuts · Nest from Stock · View Summary Report
# Key in v13.7:
# - PG Bison logo header in PDF (upload a logo or place 'pg_bison_logo.png' next to this file)
# - Metadata table like your Word layout (Project, Location, Drawing No., Revision, Material, Cutting List By, Date Created)
# - Group by "Section Size" so multiple sections live in one consolidated PDF
# - Textual "Bar n: |1200|1200|...| scrap: XXX mm" lines + visual bar chart per section
# - PDF-only export

import io, os, math, tempfile, base64
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
st.set_page_config(page_title="Steel Nesting Planner v13.7", layout="wide")
st.title("🧰 Steel Nesting Planner v13.7 — PG Bison Header + Section-Based PDF")

# Defaults
KERF_DEFAULT_MM = 2.0
STOCK_DEFAULT_MM = 6000

# Optional embedded logo as base64 (leave empty if not embedding)
DEFAULT_LOGO_B64 = ""  # put a base64 string here if you want a baked-in default

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

stock_choice = st.sidebar.selectbox(
    "Default Stock Length (mm) – used when a row has no 'Stock Length (mm)' value",
    [6000, 9000, 13000, "Custom"],
    index=0,
)
if stock_choice == "Custom":
    default_stock_length_mm = int(
        st.sidebar.number_input("Custom Stock Length (mm)", min_value=1, step=10, value=STOCK_DEFAULT_MM)
    )
else:
    default_stock_length_mm = int(stock_choice)

st.sidebar.write("---")
offer_zip = st.sidebar.checkbox("Also export per-Section PDFs as ZIP", value=False)

# ────────────────────────────────────────────────────────────────
# Project metadata (Word-style layout)
# ────────────────────────────────────────────────────────────────
st.header("📁 Project Details (PG Bison layout)")
logo_file = st.file_uploader(
    "Company Logo (PNG/JPG) — leave empty to use local 'pg_bison_logo.png' or an embedded default",
    type=["png","jpg","jpeg"]
)

colA1, colA2 = st.columns(2)
with colA1:
    project_name = st.text_input("Project", "PG Bison Extraction Ducts")
    project_location = st.text_input("Location", "Ugie")
    drawing_number = st.text_input("Drawing Number", "DWG-123")
    revision_number = st.text_input("Revision", "A")
with colA2:
    material_type = st.text_input("Material", "Mild Steel")
    cutting_by = st.text_input("Cutting List By", "Wynand Oppermann")
    date_created = st.text_input("Date Created", datetime.now().strftime("%Y-%m-%d"))
    notes_header = st.text_input("Document Note (optional)", "")

project_meta = {
    "Project": project_name,
    "Location": project_location,
    "Drawing Number": drawing_number,
    "Revision": revision_number,
    "Material": material_type,
    "Cutting List By": cutting_by,
    "Date Created": date_created,
    "Document Note": notes_header.strip(),
}

# ────────────────────────────────────────────────────────────────
# Helpers
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
    Return bars: [{"cuts":[...], "used":used_mm, "waste":waste_mm}, ...]
    """
    pieces = sorted([int(c) for c in cuts_mm if c > 0], reverse=True)
    bars: List[Dict] = []
    for piece in pieces:
        placed = False
        for bar in bars:
            n = len(bar["cuts"])
            needed = piece + (kerf_mm if n > 0 else 0.0)
            if bar["used"] + needed <= stock_len_mm + 1e-6:
                bar["cuts"].append(piece)
                bar["used"] += needed
                placed = True
                break
        if not placed:
            bars.append({"cuts": [piece], "used": float(piece), "waste": 0.0})
    for bar in bars:
        bar["waste"] = max(stock_len_mm - bar["used"], 0.0)
    return bars

def bars_to_text_lines(bars: List[Dict], stock_len_mm: int) -> List[str]:
    lines = [f"Stock {stock_len_mm} mm — Bars used: {len(bars)}"]
    for i, b in enumerate(bars, 1):
        cuts_str = "|".join(str(int(c)) for c in b["cuts"])
        scrap = max(stock_len_mm - b["used"], 0.0)
        lines.append(f"Bar {i}: |{cuts_str}| scrap: {int(round(scrap))} mm")
    return lines

def plot_bars_png(bars: List[Dict], stock_len_mm: int, kerf_mm: float) -> bytes:
    if len(bars) == 0:
        fig, ax = plt.subplots(figsize=(8, 1.5))
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=200)
        plt.close(fig)
        return buf.getvalue()

    rows = len(bars)
    height = max(2.0, 0.35 * rows + 1.0)
    fig, ax = plt.subplots(figsize=(9, height))
    ax.set_xlim(0, stock_len_mm)
    ax.set_ylim(0, rows)
    ax.set_xlabel("mm")
    ax.set_ylabel("Stock Bars")

    for i, bar in enumerate(bars):
        y = rows - i - 0.5
        ax.hlines(y, 0, stock_len_mm, linewidth=1)
        x = 0.0
        for j, cut in enumerate(bar["cuts"]):
            rect = plt.Rectangle((x, y - 0.15), cut, 0.3, fill=True, alpha=0.5)
            ax.add_patch(rect)
            ax.text(x + cut / 2, y, f"{int(cut)}", ha="center", va="center", fontsize=7)
            x += cut
            if j < len(bar["cuts"]) - 1:
                x += kerf_mm
        waste = max(stock_len_mm - (x), 0.0)
        ax.text(stock_len_mm - 5, y + 0.22, f"Waste: {int(round(waste))} mm", ha="right", va="center", fontsize=7)

    ax.grid(True, axis="x", linestyle=":", linewidth=0.6)
    ax.set_yticks([])
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    return buf.getvalue()

def decode_logo_to_path(uploaded_file, default_b64: str) -> str:
    """
    Priority: uploaded file → local 'pg_bison_logo.png' in app folder → embedded base64 → none.
    Returns a filesystem path suitable for FPDF.image(...)
    """
    data = None
    if uploaded_file is not None:
        data = uploaded_file.read()
    elif os.path.exists("pg_bison_logo.png"):
        with open("pg_bison_logo.png", "rb") as f:
            data = f.read()
    elif default_b64:
        data = base64.b64decode(default_b64)

    if not data:
        return ""

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return tmp.name

# ────────────────────────────────────────────────────────────────
# Input tables (Section-based)
# ────────────────────────────────────────────────────────────────
st.header("✏️ Required Cuts (grouped by Section Size)")

if mode in ("Nest by Required Cuts", "Nest from Stock"):
    example_req = pd.DataFrame(
        {
            "Section Size": ["152x152x23 kg/m", "152x152x23 kg/m", "100x50 RSC Channel", "50x6 Flat Bar"],
            "Cut Length (mm)": [1200, 550, 1200, 550],
            "Quantity": [4, 5, 2, 6],
            "Stock Length (mm)": [6000, 6000, 6000, 6000],
            "Tag (optional)": ["Frame", "Frame", "Channel", "Flat"],
            "Note": ["", "", "", ""],
        }
    )
    req_df = st.data_editor(
        example_req,
        key="req_df",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Section Size": st.column_config.TextColumn(help="e.g., 152x152x23 kg/m"),
            "Cut Length (mm)": st.column_config.NumberColumn(min_value=1, step=1),
            "Quantity": st.column_config.NumberColumn(min_value=1, step=1),
            "Stock Length (mm)": st.column_config.NumberColumn(
                min_value=0, step=10, help="Leave 0/blank to use the default from the sidebar"
            ),
            "Tag (optional)": st.column_config.TextColumn(required=False),
            "Note": st.column_config.TextColumn(required=False),
        },
    )

if mode == "Nest from Stock":
    st.header("🏷️ Available Stock (by Section)")
    st.caption("Add one row per stock length for a Section. **Bars Available** replaces any old 'Quantity Required' fields.")
    example_stock = pd.DataFrame(
        {"Section Size": ["152x152x23 kg/m", "100x50 RSC Channel"], "Stock Length (mm)": [6000, 6000], "Bars Available": [3, 2]}
    )
    stock_df = st.data_editor(
        example_stock,
        key="stock_df",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Section Size": st.column_config.TextColumn(),
            "Stock Length (mm)": st.column_config.NumberColumn(min_value=1, step=10),
            "Bars Available": st.column_config.NumberColumn(min_value=0, step=1),
        },
    )
else:
    stock_df = pd.DataFrame(columns=["Section Size", "Stock Length (mm)", "Bars Available"])

# ────────────────────────────────────────────────────────────────
# Grouping
# ────────────────────────────────────────────────────────────────
def group_by_section(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    cols = ["Section Size", "Cut Length (mm)", "Quantity", "Stock Length (mm)", "Tag (optional)", "Note"]
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    df["Section Size"] = df["Section Size"].fillna("").astype(str)
    df["Cut Length (mm)"] = df["Cut Length (mm)"].apply(clean_int)
    df["Quantity"] = df["Quantity"].apply(clean_int)
    df["Stock Length (mm)"] = df["Stock Length (mm)"].apply(lambda v: clean_int(v, 0))
    df["Tag (optional)"] = df["Tag (optional)"].fillna("").astype(str)
    df["Note"] = df["Note"].fillna("").astype(str)

    df = df[(df["Section Size"] != "") & (df["Cut Length (mm)"] > 0) & (df["Quantity"] > 0)].copy()
    groups = {}
    for sec, g in df.groupby("Section Size", dropna=False):
        groups[sec] = g.reset_index(drop=True)
    return groups

# ────────────────────────────────────────────────────────────────
# PDF helpers (header + metadata + section blocks)
# ────────────────────────────────────────────────────────────────
def draw_header_with_logo(pdf: FPDF, logo_path: str):
    # Logo
    if logo_path and os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=10, w=38)
    # Start content below the logo
    pdf.set_y(30)

def draw_meta_table(pdf: FPDF, meta: Dict):
    pdf.set_y(30)
    pdf.set_font("Helvetica", "", 11)
    left_margin = 10
    col_label_w = 55
    col_value_w = 115
    row_h = 7

    rows = [
        ("Project", meta.get("Project","")),
        ("Location", meta.get("Location","")),
        ("Drawing Number", meta.get("Drawing Number","")),
        ("Revision", meta.get("Revision","")),
        ("Material", meta.get("Material","")),
        ("Cutting List By", meta.get("Cutting List By","")),
        ("Date Created", meta.get("Date Created","")),
    ]

    for label, value in rows:
        pdf.set_x(left_margin)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(col_label_w, row_h, label, border=1)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(col_value_w, row_h, str(value), border=1, ln=1)
    pdf.ln(2)

def write_section_block(pdf: FPDF, section: str, stock_len_mm: int, kerf_mm: float, df_section: pd.DataFrame, bars: List[Dict]):
    # Section header
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, f"Section Size   {section}", ln=1, border=1)
    pdf.ln(1)

    # Bar text lines
    lines = bars_to_text_lines(bars, stock_len_mm)
    pdf.set_font("Helvetica", "", 11)
    for line in lines:
        pdf.cell(0, 6, line, ln=1)
    pdf.ln(1)

    # Cuts table
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 7, "Cut Length (mm)", border=1)
    pdf.cell(25, 7, "Qty", border=1)
    pdf.cell(40, 7, "Stock Len (mm)", border=1)
    pdf.cell(80, 7, "Note", border=1, ln=1)

    pdf.set_font("Helvetica", "", 10)
    for _, r in df_section.iterrows():
        pdf.cell(45, 7, f"{clean_int(r['Cut Length (mm)'])}", border=1)
        pdf.cell(25, 7, f"{clean_int(r['Quantity'])}", border=1)
        s_override = clean_int(r.get("Stock Length (mm)", 0), 0)
        pdf.cell(40, 7, f"{s_override if s_override>0 else stock_len_mm}", border=1)
        pdf.cell(80, 7, str(r.get('Note',''))[:45], border=1, ln=1)
    pdf.ln(1)

    # Visual bar chart
    img_bytes = plot_bars_png(bars, stock_len_mm, kerf_mm)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Cut Layout Visualization:", ln=1)
    pdf.image(tmp_path, w=190)
    pdf.ln(4)

def consolidated_pdf(meta: Dict, logo_path: str, payloads: List[Tuple[str, int, float, pd.DataFrame, List[Dict]]]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)

    for idx, (section, stock_len_mm, kerf_mm, df_section, bars) in enumerate(payloads):
        pdf.add_page()
        draw_header_with_logo(pdf, logo_path)
        draw_meta_table(pdf, meta)
        if idx == 0 and meta.get("Document Note"):
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, meta["Document Note"])
            pdf.ln(1)
        write_section_block(pdf, section, stock_len_mm, kerf_mm, df_section, bars)

    return pdf.output(dest="S").encode("latin-1")

def single_section_pdf(meta: Dict, logo_path: str, section: str, stock_len_mm: int, kerf_mm: float,
                       df_section: pd.DataFrame, bars: List[Dict]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    draw_header_with_logo(pdf, logo_path)
    draw_meta_table(pdf, meta)
    write_section_block(pdf, section, stock_len_mm, kerf_mm, df_section, bars)
    return pdf.output(dest="S").encode("latin-1")

# ────────────────────────────────────────────────────────────────
# Build payloads
# ────────────────────────────────────────────────────────────────
def payloads_by_required(req_df: pd.DataFrame, default_stock_len_mm: int, kerf_mm: float):
    payloads = []
    groups = group_by_section(req_df)
    for section, g in groups.items():
        # find first nonzero per-row override if present
        s_vals = [clean_int(v, 0) for v in g.get("Stock Length (mm)", [])]
        s_override = next((v for v in s_vals if v and v > 0), 0) if len(s_vals)>0 else 0
        stock_len = s_override if s_override > 0 else default_stock_len_mm

        pieces = []
        for _, r in g.iterrows():
            pieces.extend(explode_cuts(clean_int(r["Cut Length (mm)"]), clean_int(r["Quantity"])))
        bars = first_fit_decreasing(pieces, stock_len, kerf_mm)
        payloads.append((section, stock_len, kerf_mm, g, bars))
    return payloads

def payloads_from_stock(req_df: pd.DataFrame, stock_df: pd.DataFrame, kerf_mm: float):
    payloads = []
    req_groups = group_by_section(req_df)

    stock_df = stock_df.copy()
    for c in ["Section Size", "Stock Length (mm)", "Bars Available"]:
        if c not in stock_df.columns:
            stock_df[c] = 0
    stock_df["Section Size"] = stock_df["Section Size"].fillna("").astype(str)
    stock_df["Stock Length (mm)"] = stock_df["Stock Length (mm)"].apply(clean_int)
    stock_df["Bars Available"] = stock_df["Bars Available"].apply(clean_int)

    stock_by_sec: Dict[str, List[Tuple[int, int]]] = {}
    for _, r in stock_df.iterrows():
        if r["Section Size"] == "" or r["Stock Length (mm)"] <= 0 or r["Bars Available"] <= 0:
            continue
        stock_by_sec.setdefault(r["Section Size"], []).append((int(r["Stock Length (mm)"]), int(r["Bars Available"])))

    for section, g in req_groups.items():
        pieces = []
        for _, r in g.iterrows():
            pieces.extend(explode_cuts(clean_int(r["Cut Length (mm)"]), clean_int(r["Quantity"])))
        pieces = sorted([p for p in pieces if p > 0], reverse=True)

        inv = stock_by_sec.get(section, [])
        bars: List[Dict] = []
        for length_mm, qty in inv:
            for _ in range(int(qty)):
                bars.append({"len": length_mm, "cuts": [], "used": 0.0})

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
                remaining.remove(piece)

        if len(remaining) > 0:
            base_len = inv[0][0] if len(inv) > 0 else 6000
            extra = first_fit_decreasing(remaining, base_len, kerf_mm)
            for b in extra:
                bars.append({"len": base_len, "cuts": b["cuts"][:], "used": b["used"]})

        # Choose dominant length to plot
        if len(bars) == 0:
            dominant_len = (inv[0][0] if len(inv) else 6000)
        else:
            lengths = [b["len"] for b in bars]
            dominant_len = int(pd.Series(lengths).mode().iloc[0])

        # Normalize bars to dominant axis for plotting
        normalized = []
        for b in bars:
            used = b["used"] if b["len"] == dominant_len else b["used"] * (dominant_len / max(b["len"], 1))
            normalized.append({"cuts": b["cuts"], "used": used, "waste": max(dominant_len - used, 0.0)})

        payloads.append((section, dominant_len, kerf_mm, g, normalized))

    return payloads

# ────────────────────────────────────────────────────────────────
# Compute & Export
# ────────────────────────────────────────────────────────────────
st.write("---")
col_run, col_sp = st.columns([1, 3])
with col_run:
    run = st.button("⚙️ Run Nesting & Build PDF", type="primary")

if run:
    error_box = st.empty()
    try:
        if mode == "Nest by Required Cuts":
            payloads = payloads_by_required(req_df, default_stock_length_mm, kerf_mm)
        elif mode == "Nest from Stock":
            payloads = payloads_from_stock(req_df, stock_df, kerf_mm)
        else:
            payloads = []

        if mode in ("Nest by Required Cuts", "Nest from Stock") and len(payloads) == 0:
            st.warning("No valid rows found. Please add Section Size, Cut Length, and Quantity.")
        else:
            logo_path = decode_logo_to_path(logo_file, DEFAULT_LOGO_B64)

            # consolidated PDF
            all_pdf = consolidated_pdf(project_meta, logo_path, payloads)
            st.download_button(
                "⬇️ Download Consolidated PDF",
                data=all_pdf,
                file_name=f"nesting_{project_meta['Project'].replace(' ','_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            # optional per-section ZIP
            if offer_zip:
                files = {}
                for section, slen, k, g, bars in payloads:
                    b = single_section_pdf(project_meta, logo_path, section, slen, k, g, bars)
                    safe = f"{section}".replace(" ", "_").replace("/", "-")
                    files[f"{safe}.pdf"] = b
                import zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, data in files.items():
                        zf.writestr(name, data)
                st.download_button(
                    "⬇️ Download Per-Section PDFs (ZIP)",
                    data=buf.getvalue(),
                    file_name=f"nesting_{project_meta['Project'].replace(' ','_')}_per_section.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        # quick on-screen summary
        if mode in ("Nest by Required Cuts", "Nest from Stock") and len(payloads) > 0:
            st.write("---")
            st.subheader("📊 Quick On-Screen Summary (per Section)")
            rows = []
            for section, slen, k, g, bars in payloads:
                total_cuts = int(g["Quantity"].sum())
                total_cut_len_mm = float((g["Cut Length (mm)"] * g["Quantity"]).sum())
                meters_ordered = len(bars) * (slen / 1000.0)
                rows.append(
                    {
                        "Section": section,
                        "Bars Used": len(bars),
                        "Stock Len (mm)": slen,
                        "Total Cuts": total_cuts,
                        "Total Cut Len (mm)": int(round(total_cut_len_mm)),
                        "Meters Ordered": round(meters_ordered, 3),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    except Exception as e:
        error_box.error(f"Something went wrong: {e}")

# ────────────────────────────────────────────────────────────────
# View-only summary
# ────────────────────────────────────────────────────────────────
if mode == "View Summary Report":
    st.info("Switch to one of the nesting modes and click **Run Nesting & Build PDF** to generate outputs.")
    st.write("Project summary:")
    st.json(project_meta, expanded=False)
