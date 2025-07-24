import os
import csv
import pandas as pd
from datetime import datetime
import streamlit as st
from fpdf import FPDF
import matplotlib.pyplot as plt
import tempfile

# App config
st.set_page_config(page_title="Steel Nesting Planner", layout="wide")
st.title("Steel Nesting Planner v10.7")

# Constants
KERF = 3  # mm (fixed kerf for now)

# Step 1: Enter Project Metadata
st.header("🔧 Project Details")
project_name = st.text_input("Project Name")
project_location = st.text_input("Project Location")
person_cutting = st.text_input("Person Cutting")
material_type = st.text_input("Material Type")
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

# Nesting logic
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

# PDF export with bar chart
def export_cutting_lists(raw_entries, tag_costs, stock_length, save_folder):
    os.makedirs(save_folder, exist_ok=True)
    tag_lengths = {}
    for length, tag in raw_entries:
        tag_lengths.setdefault(tag, []).append(length)

    for tag, lengths in tag_lengths.items():
        bars = nest_lengths(lengths, stock_length, KERF)
        total_length = sum(lengths)
        cost_per_meter = tag_costs.get(tag, 0.0)
        total_cost = (total_length / 1000) * cost_per_meter
        file_base = os.path.join(save_folder, f"{tag.replace('/', '_')}")

        # Text file
        with open(f"{file_base}.txt", "w", encoding="utf-8") as f:
            f.write(f"Project: {project_name}\n")
            f.write(f"Location: {project_location}\n")
            f.write(f"Cut By: {person_cutting}\n")
            f.write(f"Material: {material_type}\n")
            f.write(f"Date: {today}\n\n")
            f.write(f"Section: {tag}\n")
            f.write(f"Total cuts: {len(lengths)}\n")
            f.write(f"Bars used: {len(bars)}\n")
            f.write(f"Total meters ordered: {round(sum(lengths)/1000, 2)} m\n")
            f.write(f"Cost per meter: R {cost_per_meter:.2f}\n")
            f.write(f"Total cost: R {total_cost:.2f}\n\n")
            for i, bar in enumerate(bars, 1):
                f.write(f"Bar {i}: {bar} => Total: {sum(bar)} mm\n")

        # PDF with visual bar chart
        pdf = FPDF()
        pdf.set_doc_option("core_fonts_encoding", "utf-8")
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, f"Cutting List – {tag}", ln=True)
        pdf.cell(200, 10, f"Project: {project_name} | Location: {project_location}", ln=True)
        pdf.cell(200, 10, f"Material: {material_type} | Cut By: {person_cutting}", ln=True)
        pdf.cell(200, 10, f"Total cuts: {len(lengths)} | Bars: {len(bars)}", ln=True)
        pdf.cell(200, 10, f"Total meters: {round(sum(lengths)/1000, 2)} m | Cost: R {total_cost:.2f}", ln=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            fig, ax = plt.subplots(figsize=(8, 4))
            for i, bar in enumerate(bars):
                left = 0
                for segment in bar:
                    ax.barh(i, segment, left=left, height=0.5)
                    left += segment + KERF
            ax.set_xlim(0, stock_length)
            ax.set_xlabel("mm")
            ax.set_ylabel("Bar Number")
            ax.set_title(f"Cut Layout for {tag}")
            plt.tight_layout()
            plt.savefig(tmpfile.name)
            plt.close()
            pdf.image(tmpfile.name, x=10, y=80, w=190)

        pdf.output(f"{file_base}.pdf")

# Run nesting
if st.button("Run Nesting"):
    if raw_entries:
        export_cutting_lists(raw_entries, tag_costs, stock_length, save_folder)
        st.success("Nesting completed.")
        st.success(f"Files saved to '{save_folder}'")
    else:
        st.warning("No valid data to nest.")
