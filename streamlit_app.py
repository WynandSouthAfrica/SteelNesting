import os
import streamlit as st
import pandas as pd
from fpdf import FPDF  # ✅ REQUIRED for PDF generation
from datetime import datetime
import tempfile
import zipfile
# Export ZIP with safe PDF and TXT
pdf = FPDF()
pdf.add_page()
pdf.set_font("Courier", "", 11)

def safe(text):
    return str(text).encode("latin-1", "replace").decode("latin-1")

pdf.cell(0, 10, safe(f"Nesting Report – {today}"), ln=True)
for label, value in [
    ("Project", project_name), ("Location", project_location), ("Cutting", person_cutting),
    ("Supplier", supplier_name), ("Order Number", order_number),
    ("Drawing", drawing_number), ("Revision", revision_number), ("Material", material_type)
]:
    pdf.cell(0, 10, safe(f"{label}: {value}"), ln=True)

pdf.cell(0, 10, safe(f"Stock: {stock_qty} × {stock_length} mm"), ln=True)
pdf.cell(0, 10, safe(f"Cut Size: {cut_length} mm"), ln=True)
pdf.cell(0, 10, safe(f"Cost per meter: R {cost_per_meter:.2f}"), ln=True)
pdf.cell(0, 10, safe(f"Total cost: R {total_cost:.2f}"), ln=True)
pdf.ln(5)
for i, bar in enumerate(bars_used, 1):
    if bar["cuts"]:
        total = sum(bar["cuts"]) + KERF * (len(bar["cuts"]) - 1)
        offcut = stock_length - total
        bar_str = ", ".join(str(c) for c in bar["cuts"])
        line = f"Bar {i}: [{bar_str}] => Total: {total} mm | Offcut: {offcut} mm"
        pdf.multi_cell(0, 8, safe(line))

# Also fix the TXT content (although it doesn't crash on unicode)
txt = f"Nesting Report – {today}\n"
for label, value in [
    ("Project", project_name), ("Location", project_location), ("Person Cutting", person_cutting),
    ("Supplier", supplier_name), ("Order Number", order_number),
    ("Drawing Number", drawing_number), ("Revision", revision_number), ("Material", material_type)
]:
    txt += f"{label}: {value}\n"

txt += f"\nStock: {stock_qty} × {stock_length} mm\nCut Size: {cut_length} mm\n"
txt += f"Cost per meter: R {cost_per_meter:.2f}\nTotal cost: R {total_cost:.2f}\n\n"
for i, bar in enumerate(bars_used, 1):
    if bar["cuts"]:
        total = sum(bar["cuts"]) + KERF * (len(bar["cuts"]) - 1)
        offcut = stock_length - total
        bar_str = ", ".join(str(c) for c in bar["cuts"])
        txt += f"Bar {i}: [{bar_str}] => Total: {total} mm | Offcut: {offcut} mm\n"

# Create ZIP
with tempfile.TemporaryDirectory() as tmpdir:
    pdf_path = os.path.join(tmpdir, "Report.pdf")
    txt_path = os.path.join(tmpdir, "Report.txt")
    zip_path = os.path.join(tmpdir, "Nest_Export.zip")
    pdf.output(pdf_path)
    with open(txt_path, "w") as f: f.write(txt)
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.write(pdf_path, "Report.pdf")
        zipf.write(txt_path, "Report.txt")
    with open(zip_path, "rb") as zf:
        st.download_button("📦 Download ZIP", data=zf.read(), file_name="Nest_Export.zip", mime="application/zip")
