import os
import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime
import tempfile
import zipfile

# App setup
st.set_page_config(page_title="Steel Nesting Planner v13.2", layout="wide")
st.title("🧰 Steel Nesting Planner v13.2 – Multi-Mode with Metadata")

KERF = 3  # mm
today = datetime.today().strftime('%Y-%m-%d')

# -----------------------------------------
# 🧾 Project Metadata Section
# -----------------------------------------
st.header("📁 Project Details")

colA1, colA2 = st.columns(2)
with colA1:
    project_name = st.text_input("Project Name", "PG Bison Extraction Ducts")
    project_location = st.text_input("Project Location", "Ugie")
    person_cutting = st.text_input("Person Cutting", "Wynand")
    supplier_name = st.text_input("Supplier", "Macsteel")
with colA2:
    order_number = st.text_input("Order Number", "PO-2024-145")
    drawing_number = st.text_input("Drawing Number", "1450-002-04")
    revision_number = st.text_input("Revision Number", "01")
    material_type = st.text_input("Material Type", "150x150x10 FB")

st.divider()

# -----------------------------------------
# MODE SELECTOR
# -----------------------------------------
mode = st.radio("Select Nesting Mode:", [
    "🔁 Nest by Required Cuts",
    "📦 Nest From Stock",
    "📊 View Summary Report"
])

# -----------------------------------------
# MODE 1: NEST BY REQUIRED CUTS
# -----------------------------------------
if mode == "🔁 Nest by Required Cuts":
    st.header("🔁 Nest by Required Cuts (Estimate Stock Needed)")

    stock_length = st.number_input("Stock Length (mm)", min_value=1000, max_value=20000, value=6000, step=100)
    cost_per_meter = st.number_input("Cost per Meter", min_value=0.0, value=125.0)
    section_tag = material_type

    cut_data = pd.DataFrame(st.data_editor(
        [{"Length": 550, "Qty": 4}, {"Length": 750, "Qty": 2}],
        num_rows="dynamic",
        use_container_width=True
    ))

    lengths = []
    for _, row in cut_data.iterrows():
        try:
            lengths += [int(row["Length"])] * int(row["Qty"])
        except:
            pass

    def nest_lengths(lengths, stock_length, kerf):
        bars = []
        for length in sorted(lengths, reverse=True):
            placed = False
            for bar in bars:
                remaining = stock_length - sum(bar) - kerf * len(bar)
                if length + kerf <= remaining:
                    bar.append(length)
                    placed = True
                    break
            if not placed:
                bars.append([length])
        return bars

    if st.button("Run Nesting"):
        bars = nest_lengths(lengths, stock_length, KERF)
        total_cut = sum(lengths)
        total_cost = (total_cut / 1000) * cost_per_meter
        total_offcut = sum(stock_length - (sum(bar) + KERF * (len(bar)-1 if len(bar) > 0 else 0)) for bar in bars)

        st.success(f"Bars Required: {len(bars)}")
        for i, bar in enumerate(bars, 1):
            used = sum(bar) + KERF * (len(bar) - 1)
            offcut = stock_length - used
            st.text(f"Bar {i}: {bar} => Total: {used} mm | Offcut: {offcut} mm")

        st.markdown(f"💰 Total Estimated Cost: R {total_cost:,.2f}")
        st.markdown(f"📏 Total Offcut: {int(total_offcut)} mm")

        # PDF and TXT export
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

        pdf.cell(0, 10, safe(f"Stock Length: {stock_length} mm"), ln=True)
        pdf.cell(0, 10, safe(f"Total Estimated Cost: R {total_cost:.2f}"), ln=True)
        pdf.cell(0, 10, safe(f"Total Offcut: {int(total_offcut)} mm"), ln=True)
        pdf.ln(5)
        for i, bar in enumerate(bars, 1):
            bar_str = ", ".join(str(c) for c in bar)
            used = sum(bar) + KERF * (len(bar) - 1)
            offcut = stock_length - used
            line = f"Bar {i}: [{bar_str}] => Total: {used} mm | Offcut: {offcut} mm"
            pdf.multi_cell(0, 8, safe(line))

        txt = f"Nesting Report – {today}\n"
        for label, value in [
            ("Project", project_name), ("Location", project_location), ("Person Cutting", person_cutting),
            ("Supplier", supplier_name), ("Order Number", order_number),
            ("Drawing Number", drawing_number), ("Revision", revision_number), ("Material", material_type)
        ]:
            txt += f"{label}: {value}\n"
        txt += f"\nStock Length: {stock_length} mm\nTotal Cost: R {total_cost:.2f}\nTotal Offcut: {int(total_offcut)} mm\n\n"
        for i, bar in enumerate(bars, 1):
            bar_str = ", ".join(str(c) for c in bar)
            used = sum(bar) + KERF * (len(bar) - 1)
            offcut = stock_length - used
            txt += f"Bar {i}: [{bar_str}] => Total: {used} mm | Offcut: {offcut} mm\n"

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

# -----------------------------------------
# MODE 2: NEST FROM STOCK
# -----------------------------------------
elif mode == "📦 Nest From Stock":
    st.header("📦 Nest From Available Stock")

    col1, col2 = st.columns([2, 1])
    with col1:
        stock_length = st.number_input("Stock Length (mm)", min_value=1000, max_value=20000, value=6000, step=100)
    with col2:
        stock_qty = st.number_input("Stock Quantity", min_value=1, value=4)

    cut_length = st.number_input("Cut Length (mm)", min_value=10, max_value=stock_length, value=550)
    cost_per_meter = st.number_input("Cost Per Meter (optional)", min_value=0.0, value=0.0, step=1.0)

    def simulate_nesting(stock_length, stock_qty, cut_length, kerf):
        bars = [{"cuts": [], "remaining": stock_length} for _ in range(stock_qty)]
        for bar in bars:
            while True:
                required = cut_length + (kerf if bar["cuts"] else 0)
                if bar["remaining"] >= required:
                    bar["cuts"].append(cut_length)
                    bar["remaining"] -= required
                else:
                    break
        total_cuts = sum(len(bar["cuts"]) for bar in bars)
        return bars, total_cuts

    if st.button("🧠 Simulate Nesting"):
        bars_used, total_cuts = simulate_nesting(stock_length, stock_qty, cut_length, KERF)
        st.header("📦 Nesting Results")
        for i, bar in enumerate(bars_used, 1):
            if bar["cuts"]:
                total = sum(bar["cuts"]) + KERF * (len(bar["cuts"]) - 1)
                offcut = stock_length - total
                st.text(f"Bar {i}: {bar['cuts']} => Total: {total} mm | Offcut: {offcut} mm")

        total_m = (total_cuts * cut_length) / 1000
        total_cost = total_m * cost_per_meter

        st.markdown(f"✅ **Cuts Completed:** {total_cuts}")
        st.markdown(f"💰 **Total Cost:** R {total_cost:,.2f}")

        # --- Safe PDF Export (Unicode-safe) ---
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

# -----------------------------------------
# MODE 3: VIEW REPORTS
# -----------------------------------------
elif mode == "📊 View Summary Report":
    st.header("📊 View Summary Report (Coming Soon)")
    st.info("This section will let you upload or browse past reports.")
