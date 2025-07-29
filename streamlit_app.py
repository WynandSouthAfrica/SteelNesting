import os
import streamlit as st
from fpdf import FPDF
from datetime import datetime
import tempfile
import zipfile

# App config
st.set_page_config(page_title="Steel Nesting Planner v12.0.1", layout="wide")
st.title("🔩 Steel Nesting Planner v12.0.1 – Work From Stock")

KERF = 3  # mm

# --- Inputs ---
st.header("📋 Cutting List Input")

col1, col2 = st.columns([2, 1])
with col1:
    stock_length = st.number_input("Stock Length (mm)", min_value=1000, max_value=20000, value=6000, step=100)
with col2:
    stock_qty = st.number_input("Stock Quantity", min_value=1, value=4)

section_tag = st.text_input("Section / Tag", "150x150x10 FB")
cut_length = st.number_input("Cut Length (mm)", min_value=10, max_value=stock_length, value=550)
cut_qty = st.number_input("Quantity Required", min_value=1, value=10)
cost_per_meter = st.number_input("Cost Per Meter (optional)", min_value=0.0, value=0.0, step=1.0)

project_name = st.text_input("Project Name", "")
person_cutting = st.text_input("Person Cutting", "")
today = datetime.today().strftime('%Y-%m-%d')

# --- Nesting Logic ---
def simulate_forward_nesting(stock_length, stock_qty, cut_length, cut_qty, kerf):
    bars = [{"cuts": [], "remaining": stock_length} for _ in range(stock_qty)]
    cuts_placed = 0

    for _ in range(cut_qty):
        placed = False
        for bar in bars:
            required = cut_length + (kerf if bar["cuts"] else 0)
            if bar["remaining"] >= required:
                bar["cuts"].append(cut_length)
                bar["remaining"] -= required
                cuts_placed += 1
                placed = True
                break
        if not placed:
            break

    cuts_remaining = cut_qty - cuts_placed
    return bars, cuts_placed, cuts_remaining

# --- Run Nesting ---
if st.button("🧠 Simulate Nesting"):
    bars_used, cuts_done, cuts_short = simulate_forward_nesting(stock_length, stock_qty, cut_length, cut_qty, KERF)

    st.header("📦 Nesting Results")
    for i, bar in enumerate(bars_used, 1):
        if bar["cuts"]:
            total_cut = sum(bar["cuts"]) + KERF * (len(bar["cuts"]) - 1)
            offcut = stock_length - total_cut
            st.text(f"Bar {i}: {bar['cuts']} => Total: {total_cut} mm | Offcut: {offcut} mm")

    st.markdown(f"✅ **Total Pieces Cut:** {cuts_done}")
    st.markdown(f"❌ **Remaining to Cut:** {cuts_short}")
    total_meters = (cuts_done * cut_length) / 1000
    total_cost = total_meters * cost_per_meter
    st.markdown(f"💰 **Total Cost (est.):** R {total_cost:,.2f}")

    # --- PDF + TXT Export ---
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", "B", 14)
    pdf.cell(0, 10, "Steel Nesting Report", ln=True)
    pdf.set_font("Courier", "", 11)
    pdf.cell(0, 10, f"Project: {project_name}", ln=True)
    pdf.cell(0, 10, f"Section: {section_tag}", ln=True)
    pdf.cell(0, 10, f"Person Cutting: {person_cutting}", ln=True)
    pdf.cell(0, 10, f"Date: {today}", ln=True)
    pdf.cell(0, 10, f"Stock: {stock_qty} × {stock_length} mm bars", ln=True)
    pdf.cell(0, 10, f"Required: {cut_qty} × {cut_length} mm cuts", ln=True)
    pdf.cell(0, 10, f"Cost per meter: R {cost_per_meter:.2f}", ln=True)
    pdf.cell(0, 10, f"Total cost: R {total_cost:,.2f}", ln=True)
    pdf.ln(5)

    for i, bar in enumerate(bars_used, 1):
        if bar["cuts"]:
            total_cut = sum(bar["cuts"]) + KERF * (len(bar["cuts"]) - 1)
            offcut = stock_length - total_cut
            bar_str = ", ".join(str(c) for c in bar["cuts"])
            pdf.multi_cell(0, 8, f"Bar {i}: [{bar_str}] => Total: {total_cut} mm | Offcut: {offcut} mm")

    txt_output = f"Steel Nesting Report – {today}\n"
    txt_output += f"Project: {project_name}\nSection: {section_tag}\nPerson Cutting: {person_cutting}\n"
    txt_output += f"Stock: {stock_qty} × {stock_length} mm\nRequired Cuts: {cut_qty} × {cut_length} mm\n"
    txt_output += f"Cost per meter: R {cost_per_meter:.2f}\nTotal cost: R {total_cost:.2f}\n\n"
    for i, bar in enumerate(bars_used, 1):
        if bar["cuts"]:
            total_cut = sum(bar["cuts"]) + KERF * (len(bar["cuts"]) - 1)
            offcut = stock_length - total_cut
            bar_str = ", ".join(str(c) for c in bar["cuts"])
            txt_output += f"Bar {i}: [{bar_str}] => Total: {total_cut} mm | Offcut: {offcut} mm\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "Nesting_Report.pdf")
        txt_path = os.path.join(tmpdir, "Nesting_Report.txt")
        zip_path = os.path.join(tmpdir, "Nesting_Output.zip")

        pdf.output(pdf_path)
        with open(txt_path, "w") as f:
            f.write(txt_output)

        with zipfile.ZipFile(zip_path, "w") as zipf:
            zipf.write(pdf_path, os.path.basename(pdf_path))
            zipf.write(txt_path, os.path.basename(txt_path))

        with open(zip_path, "rb") as zf:
            st.download_button("📦 Download ZIP (PDF + TXT)", data=zf.read(), file_name="Nesting_Output.zip", mime="application/zip")
