import os
import csv
import pandas as pd
from datetime import datetime
import streamlit as st
from fpdf import FPDF
import tempfile
import zipfile

# App config
st.set_page_config(page_title="Steel Nesting Planner", layout="wide")
st.title("Steel Nesting Planner v10.9")

# Constants
KERF = 3  # mm (fixed kerf for now)

# Step 1: Enter Project Metadata
st.header("🔧 Project Details")
project_name = st.text_input("Project Name")
project_location = st.text_input("Project Location")
person_cutting = st.text_input("Person Cutting")
material_type = st.text_input("Material Type")
drawing_number = st.text_input("Drawing Number")
revision_number = st.text_input("Revision Number")
save_folder = st.text_input("Folder to save cutting lists (e.g., CuttingLists/ProjectA)", value="CuttingLists")
today = datetime.today().strftime('%Y-%m-%d')

# Step 2: Enter Raw Length Data Manually
st.header("📋 Cutting List Input")

# Input: Stock Length (default is 6000)
stock_length = st.number_input("Enter Stock Length (mm)", min_value=1000, max_value=20000, value=6000, step=500)

# Editable table for manual input
st.markdown("### ✍️ Enter or Edit Cutting Entries")
default_data = [
    {"Length": 550, "Qty": 3, "Tag": "50x50x6 Equal Angle", "CostPerMeter": 125.36},
    {"Length": 650, "Qty": 8, "Tag": "50x50x6 Equal Angle", "CostPerMeter": 125.36},
]
input_df = st.data_editor(
    pd.DataFrame(default_data),
    num_rows="dynamic",
    use_container_width=True,
)

# Validate and parse data
raw_entries = []
tag_costs = {}
if not input_df.empty:
    for _, row in input_df.iterrows():
        try:
            length = int(row["Length"])
            quantity = int(row["Qty"])
            tag = str(row["Tag"]).strip()
            cost_per_meter = float(row["CostPerMeter"])
            for _ in range(quantity):
                raw_entries.append((length, tag))
            tag_costs[tag] = cost_per_meter
        except Exception as e:
            st.warning(f"Skipping row due to error: {e}")
else:
    st.info("Please enter at least one row of data in the table above.")

# Run nesting
if st.button("Run Nesting"):
    if raw_entries:
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

        def safe_pdf_text(text):
            return str(text).encode("latin-1", "replace").decode("latin-1")

        def export_cutting_lists(raw_entries, tag_costs, stock_length, save_folder):
            os.makedirs(save_folder, exist_ok=True)
            tag_lengths = {}
            pdf_paths = []
            txt_paths = []

            for length, tag in raw_entries:
                tag_lengths.setdefault(tag, []).append(length)

            for tag, lengths in tag_lengths.items():
                bars = nest_lengths(lengths, stock_length, KERF)
                total_length = sum(lengths)
                cost_per_meter = tag_costs.get(tag, 0.0)
                total_cost = (total_length / 1000) * cost_per_meter
                filename_base = f"{tag.replace('/', '_').replace(' ', '_')}"
                file_base = os.path.join(save_folder, filename_base)

                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                pdf.set_draw_color(0, 0, 0)
                pdf.rect(5.0, 5.0, 200.0, 287.0)
                logo_path = "pg_bison_logo.png"
                if os.path.exists(logo_path):
                    pdf.image(logo_path, x=10, y=8, w=30)
                    pdf.set_y(25)
                else:
                    pdf.set_y(15)

                pdf.set_font("Courier", size=11)
                pdf.multi_cell(0, 8, safe_pdf_text(f"Project: {project_name}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Location: {project_location}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Cut By: {person_cutting}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Material: {material_type}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Drawing Number: {drawing_number}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Revision: {revision_number}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Date: {today}"))
                pdf.ln(3)
                pdf.multi_cell(0, 8, safe_pdf_text(f"Section Size: {tag}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Bars required: {len(bars)}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Stock length: {stock_length} mm"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Total meters: {round(total_length / 1000, 2)} m"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Cost per meter: R {cost_per_meter:.2f}"))
                pdf.multi_cell(0, 8, safe_pdf_text(f"Total cost: R {total_cost:.2f}"))
                pdf.ln(3)

                pdf.set_font("Courier", size=10)
                for i, bar in enumerate(bars, 1):
                    used = sum(bar) + KERF * (len(bar)-1 if len(bar)>0 else 0)
                    offcut = stock_length - used
                    bar_text = f"Bar {i}: {bar} => Total: {sum(bar)} mm | Offcut: {offcut} mm"
                    pdf.multi_cell(0, 8, safe_pdf_text(bar_text))

                pdf_path = f"{file_base}.pdf"
                pdf.output(pdf_path)
                pdf_paths.append(pdf_path)

                txt_path = f"{file_base}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(f"Project: {project_name}\n")
                    f.write(f"Location: {project_location}\n")
                    f.write(f"Cut By: {person_cutting}\n")
                    f.write(f"Material: {material_type}\n")
                    f.write(f"Drawing Number: {drawing_number}\n")
                    f.write(f"Revision: {revision_number}\n")
                    f.write(f"Date: {today}\n\n")
                    f.write(f"Section Size: {tag}\n")
                    f.write(f"Bars required: {len(bars)}\n")
                    f.write(f"Stock length: {stock_length} mm\n")
                    f.write(f"Total meters: {round(total_length / 1000, 2)} m\n")
                    f.write(f"Cost per meter: R {cost_per_meter:.2f}\n")
                    f.write(f"Total cost: R {total_cost:.2f}\n\n")
                    for i, bar in enumerate(bars, 1):
                        used = sum(bar) + KERF * (len(bar)-1 if len(bar)>0 else 0)
                        offcut = stock_length - used
                        f.write(f"Bar {i}: {bar} => Total: {sum(bar)} mm | Offcut: {offcut} mm\n")
                txt_paths.append(txt_path)

            zip_path = os.path.join(save_folder, f"{project_name.replace(' ', '_')}_cutting_lists.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file in pdf_paths + txt_paths:
                    zipf.write(file, arcname=os.path.basename(file))

            with open(zip_path, "rb") as zip_file:
                st.download_button(
                    label="📦 Download All Cutting Lists (ZIP)",
                    data=zip_file,
                    file_name=os.path.basename(zip_path),
                    mime="application/zip"
                )

        export_cutting_lists(raw_entries, tag_costs, stock_length, save_folder)
        st.success("Nesting completed.")
        st.success(f"Files saved to '{save_folder}'")
    else:
        st.warning("No valid data to nest.")
