# Steel Nesting Planner v14.1 — Metadata table full width + PG Bison layout, logo fixed, no charts (18 Aug 2025)
# Modes: Nest by Required Cuts · Nest from Stock · View Summary Report

import os, io, math, tempfile, base64
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from fpdf import FPDF

# Pillow improves logo reliability (JPG/PNG → PNG)
try:
    from PIL import Image
    _PIL_OK = True
except Exception:
    _PIL_OK = False

st.set_page_config(page_title="Steel Nesting Planner v14.1", layout="wide")
st.title("🧰 Steel Nesting Planner v14.1 — PG Bison layout (full-width meta), logo fixed, no charts")

KERF_DEFAULT_MM = 2.0
STOCK_DEFAULT_MM = 6000

# ── Sidebar ─────────────────────────────────────────────────────
st.sidebar.header("⚙️ Settings")
kerf_mm = float(st.sidebar.number_input("Kerf (mm)", min_value=0.0, step=0.5, value=KERF_DEFAULT_MM))
mode = st.sidebar.radio("Mode", ["Nest by Required Cuts", "Nest from Stock", "View Summary Report"])

stock_choice = st.sidebar.selectbox(
    "Default Stock Length (mm) – used when a row has no 'Stock Length (mm)' value",
    [6000, 9000, 13000, "Custom"], index=0
)
default_stock_length_mm = int(st.sidebar.number_input("Custom Stock Length (mm)", min_value=1, step=10, value=STOCK_DEFAULT_MM)) \
    if stock_choice == "Custom" else int(stock_choice)

st.sidebar.write("---")
offer_zip = st.sidebar.checkbox("Also export per-Section PDFs as ZIP", value=False)

# ── Project meta (Word-style) ───────────────────────────────────
st.header("📁 Project Details (PG Bison layout)")
logo_file = st.file_uploader("Company Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

colA1, colA2 = st.columns(2)
with colA1:
    project_name = st.text_input("Project", "PG Bison Extraction Ducts")
    project_location = st.text_input("Location", "Ugie")
    drawing_number = st.text_input("Drawing Number", "MDF070-044-000-000")
    revision_number = st.text_input("Revision", "1.0")
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

# ── Utilities ───────────────────────────────────────────────────
def clean_float(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)): return float(default)
        return float(x)
    except Exception:
        return float(default)

def clean_int(x, default=0) -> int:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)): return int(default)
        return int(round(float(x)))
    except Exception:
        return int(default)

# latin-1-safe text
_REPL = {
    "\u2014": "-", "\u2013": "-", "\u2012": "-", "\u2010": "-", "\u2212": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2022": "-",
    "\u00A0": " ",
}
def safe_text(val) -> str:
    s = "" if val is None else str(val)
    for a,b in _REPL.items(): s = s.replace(a,b)
    try:
        s.encode("latin-1"); return s
    except UnicodeEncodeError:
        return s.encode("latin-1", "replace").decode("latin-1")

def explode_cuts(length_mm: int, qty: int) -> List[int]:
    return [length_mm] * max(qty, 0)

def first_fit_decreasing(cuts_mm: List[int], stock_len_mm: int, kerf_mm: float) -> List[Dict]:
    pieces = sorted([int(c) for c in cuts_mm if c > 0], reverse=True)
    bars: List[Dict] = []
    for piece in pieces:
        placed = False
        for bar in bars:
            need = piece + (kerf_mm if len(bar["cuts"])>0 else 0.0)
            if bar["used"] + need <= stock_len_mm + 1e-6:
                bar["cuts"].append(piece); bar["used"] += need; placed = True; break
        if not placed:
            bars.append({"cuts":[piece], "used":float(piece), "waste":0.0})
    for bar in bars:
        bar["waste"] = max(stock_len_mm - bar["used"], 0.0)
    return bars

def bars_to_text_lines(bars: List[Dict], stock_len_mm: int) -> List[str]:
    lines = [f"Stock {stock_len_mm} mm - Bars used: {len(bars)}"]
    for i, b in enumerate(bars, 1):
        cuts_str = "|".join(str(int(c)) for c in b["cuts"])
        scrap = max(stock_len_mm - b["used"], 0.0)
        lines.append(f"Bar {i}: |{cuts_str}| scrap: {int(round(scrap))} mm")
    return [safe_text(x) for x in lines]

def normalize_logo(uploaded_file) -> str:
    """
    Returns a local image path. If Pillow is available, convert to PNG (better FPDF compatibility).
    Priority: uploaded file -> local 'pg_bison_logo.png' -> ''.
    """
    data = None
    if uploaded_file is not None:
        data = uploaded_file.read()
    elif os.path.exists("pg_bison_logo.png"):
        with open("pg_bison_logo.png","rb") as f: data = f.read()
    if not data: return ""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    if _PIL_OK:
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.mode not in ("RGB", "L"): im = im.convert("RGB")
                im.save(tmp.name, format="PNG"); return tmp.name
        except Exception:
            pass
    with open(tmp.name, "wb") as f: f.write(data)
    return tmp.name

# ── Inputs (Section-based) ──────────────────────────────────────
st.header("✏️ Required Cuts (grouped by Section Size)")

if mode in ("Nest by Required Cuts", "Nest from Stock"):
    example_req = pd.DataFrame({
        "Section Size": ["152x152x23 kg/m", "152x152x23 kg/m", "100x50 RSC Channel", "50x6 Flat Bar"],
        "Cut Length (mm)": [1200, 550, 1200, 550],
        "Quantity": [4, 5, 2, 6],
        "Stock Length (mm)": [6000, 6000, 6000, 6000],
        "Tag (optional)": ["Frame", "Frame", "Channel", "Flat"],
        "Note": ["", "", "", ""],
    })
    req_df = st.data_editor(
        example_req, key="req_df", num_rows="dynamic", use_container_width=True,
        column_config={
            "Section Size": st.column_config.TextColumn(),
            "Cut Length (mm)": st.column_config.NumberColumn(min_value=1, step=1),
            "Quantity": st.column_config.NumberColumn(min_value=1, step=1),
            "Stock Length (mm)": st.column_config.NumberColumn(min_value=0, step=10, help="Leave 0 to use sidebar default"),
            "Tag (optional)": st.column_config.TextColumn(required=False),
            "Note": st.column_config.TextColumn(required=False),
        },
    )

if mode == "Nest from Stock":
    st.header("🏷️ Available Stock (by Section)")
    st.caption("Bars Available replaces any old 'Quantity Required' fields.")
    example_stock = pd.DataFrame({
        "Section Size": ["152x152x23 kg/m", "100x50 RSC Channel"],
        "Stock Length (mm)": [6000, 6000],
        "Bars Available": [3, 2],
    })
    stock_df = st.data_editor(
        example_stock, key="stock_df", num_rows="dynamic", use_container_width=True,
        column_config={
            "Section Size": st.column_config.TextColumn(),
            "Stock Length (mm)": st.column_config.NumberColumn(min_value=1, step=10),
            "Bars Available": st.column_config.NumberColumn(min_value=0, step=1),
        },
    )
else:
    stock_df = pd.DataFrame(columns=["Section Size", "Stock Length (mm)", "Bars Available"])

# ── Grouping ────────────────────────────────────────────────────
def group_by_section(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    cols = ["Section Size", "Cut Length (mm)", "Quantity", "Stock Length (mm)", "Tag (optional)", "Note"]
    for c in cols:
        if c not in df.columns: df[c] = np.nan
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

# ── PDF helpers (Word layout, no charts) ────────────────────────
def draw_header(pdf: FPDF, logo_path: str):
    if logo_path and os.path.exists(logo_path):
        try:
            pdf.image(logo_path, x=10, y=10, w=38)
        except Exception:
            pass
    pdf.set_y(10)

def draw_meta_table(pdf: FPDF, meta: Dict):
    """
    Full-width table matching the content width (same as pdf.cell(0, ...)).
    Left column is fixed label width; right column stretches to fill the rest.
    """
    pdf.set_y(28)  # under logo
    page_w = pdf.w - pdf.l_margin - pdf.r_margin  # available content width
    label_w = 55                                   # keep your label width
    value_w = page_w - label_w                     # stretch the value column to full width
    row_h = 8
    rows = ["Project","Location","Drawing Number","Revision","Material","Cutting List By","Date Created"]
    for label in rows:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 11); pdf.cell(label_w, row_h, safe_text(label), border=1)
        pdf.set_font("Helvetica", "B", 11); pdf.cell(value_w, row_h, safe_text(meta.get(label,"")), border=1, ln=1)
    pdf.ln(2)

def write_section_block(pdf: FPDF, section: str, stock_len_mm: int, bars: List[Dict]):
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, safe_text(f"Section Size   {section}"), border=1, ln=1)  # 0 → spans full content width
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 11)
    for line in bars_to_text_lines(bars, stock_len_mm):
        pdf.cell(0, 6, safe_text(line), ln=1)
    pdf.ln(2)

def consolidated_pdf(meta: Dict, logo_path: str, payloads: List[Tuple[str,int,float,pd.DataFrame,List[Dict]]]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    for idx, (section, stock_len_mm, _k, df_section, bars) in enumerate(payloads):
        pdf.add_page(); draw_header(pdf, logo_path); draw_meta_table(pdf, meta)
        if idx == 0 and meta.get("Document Note"):
            pdf.set_font("Helvetica", "", 10); pdf.multi_cell(0, 5, safe_text(meta["Document Note"])); pdf.ln(1)
        write_section_block(pdf, section, stock_len_mm, bars)
    return pdf.output(dest="S").encode("latin-1")

def single_section_pdf(meta: Dict, logo_path: str, section: str, stock_len_mm: int, _k: float,
                       df_section: pd.DataFrame, bars: List[Dict]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page(); draw_header(pdf, logo_path); draw_meta_table(pdf, meta)
    write_section_block(pdf, section, stock_len_mm, bars)
    return pdf.output(dest="S").encode("latin-1")

# ── Payload builders ────────────────────────────────────────────
def payloads_by_required(req_df: pd.DataFrame, default_stock_len_mm: int, kerf_mm: float):
    payloads = []
    for section, g in group_by_section(req_df).items():
        s_vals = [clean_int(v, 0) for v in g.get("Stock Length (mm)", [])]
        s_override = next((v for v in s_vals if v and v > 0), 0) if len(s_vals)>0 else 0
        stock_len = s_override if s_override > 0 else default_stock_len_mm
        pieces = []; 
        for _, r in g.iterrows():
            pieces.extend(explode_cuts(clean_int(r["Cut Length (mm)"]), clean_int(r["Quantity"])))
        bars = first_fit_decreasing(pieces, stock_len, kerf_mm)
        payloads.append((safe_text(section), stock_len, kerf_mm, g, bars))
    return payloads

def payloads_from_stock(req_df: pd.DataFrame, stock_df: pd.DataFrame, kerf_mm: float):
    payloads = []; req_groups = group_by_section(req_df)
    stock_df = stock_df.copy()
    for c in ["Section Size", "Stock Length (mm)", "Bars Available"]:
        if c not in stock_df.columns: stock_df[c] = 0
    stock_df["Section Size"] = stock_df["Section Size"].fillna("").astype(str)
    stock_df["Stock Length (mm)"] = stock_df["Stock Length (mm)"].apply(clean_int)
    stock_df["Bars Available"] = stock_df["Bars Available"].apply(clean_int)

    stock_by_sec: Dict[str, List[Tuple[int, int]]] = {}
    for _, r in stock_df.iterrows():
        if r["Section Size"] == "" or r["Stock Length (mm)"] <= 0 or r["Bars Available"] <= 0: continue
        stock_by_sec.setdefault(r["Section Size"], []).append((int(r["Stock Length (mm)"]), int(r["Bars Available"])))

    for section, g in req_groups.items():
        pieces = []; 
        for _, r in g.iterrows():
            pieces.extend(explode_cuts(clean_int(r["Cut Length (mm)"]), clean_int(r["Quantity"])))
        pieces = sorted([p for p in pieces if p > 0], reverse=True)

        inv = stock_by_sec.get(section, [])
        bars: List[Dict] = []
        for length_mm, qty in inv:
            for _ in range(int(qty)): bars.append({"len": length_mm, "cuts": [], "used": 0.0})

        remaining = pieces.copy()
        for piece in remaining[:]:
            placed = False
            for bar in bars:
                need = piece + (kerf_mm if len(bar["cuts"]) > 0 else 0.0)
                if bar["used"] + need <= bar["len"] + 1e-6:
                    bar["cuts"].append(piece); bar["used"] += need; placed = True; break
            if placed: remaining.remove(piece)

        if len(remaining) > 0:
            base_len = inv[0][0] if len(inv) > 0 else 6000
            extra = first_fit_decreasing(remaining, base_len, kerf_mm)
            for b in extra: bars.append({"len": base_len, "cuts": b["cuts"][:], "used": b["used"]})

        dominant_len = (inv[0][0] if len(inv)>0 else 6000)
        if len(bars) > 0:
            lengths = [b["len"] for b in bars]; dominant_len = int(pd.Series(lengths).mode().iloc[0])

        normalized = []
        for b in bars:
            normalized.append({"cuts": b["cuts"], "used": b["used"], "waste": max(dominant_len - b["used"], 0.0)})
        payloads.append((safe_text(section), dominant_len, kerf_mm, g, normalized))
    return payloads

# ── Run ─────────────────────────────────────────────────────────
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
            logo_path = normalize_logo(logo_file)

            all_pdf = consolidated_pdf(project_meta, logo_path, payloads)
            st.download_button(
                "⬇️ Download Consolidated PDF",
                data=all_pdf,
                file_name=f"nesting_{safe_text(project_meta['Project']).replace(' ','_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            if offer_zip:
                files = {}
                for section, slen, k, g, bars in payloads:
                    b = single_section_pdf(project_meta, logo_path, section, slen, k, g, bars)
                    files[f"{section.replace(' ','_').replace('/','-')}.pdf"] = b
                import zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, data in files.items(): zf.writestr(name, data)
                st.download_button(
                    "⬇️ Download Per-Section PDFs (ZIP)",
                    data=buf.getvalue(),
                    file_name=f"nesting_{safe_text(project_meta['Project']).replace(' ','_')}_per_section.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        if mode in ("Nest by Required Cuts", "Nest from Stock") and len(payloads) > 0:
            st.success("PDF built with full-width metadata table and section banner.")

    except Exception as e:
        error_box.error(f"Something went wrong: {e}")

if mode == "View Summary Report":
    st.info("Switch to one of the nesting modes and click **Run Nesting & Build PDF** to generate outputs.")
    st.write("Project summary:"); st.json(project_meta, expanded=False)
