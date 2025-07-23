import os
import csv
from datetime import datetime
import streamlit as st
from fpdf import FPDF
import matplotlib.pyplot as plt
import tempfile
import io

# App config
st.set_page_config(page_title="Steel Nesting Planner", layout="wide")
st.title("Steel Nesting Planner v10.7")

# Constants
STOCK_LENGTH = 6000  # mm
KERF = 3              # mm

# Step 1: Enter Project Metadata
st.header("🔧 Project Details")
project_name = st.text_input("Project Name")
project_location = st.text_input("Project Location")
person_cutting = st.text_input("Person Cutting")
material_type = st.text_input("Material Type")
save_folder = st.text_input("Folder to save cutting lists (e.g., CuttingLists/ProjectA)", value="CuttingLists")
today = datetime.today().strftime('%Y-%m-%d')

# Step 2: Upload CSV or input manually
st.header("📂 Upload or Enter Raw Length Data")
uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

raw_entries = []
tag_costs = {}
tag_lengths = {}

if uploaded_file:
    decoded = uploaded_file.read().decode("utf-8")
    file_stream = io.StringIO(decoded)

    reader = csv.DictReader(file_stream)
    reader.fieldnames = [field.strip() for field in reader.fieldnames]

    for row in reader:
        try:
            length = int(row['Length'].strip())
            quantity = int(row['Qty'].strip())
            tag = row['Tag'].strip()
            cost_str = row['CostPerMeter'].strip().replace(",", ".")  # <-- Fix here
            cost_per_meter = float(cost_str)
            
            raw_entries.append((length, quantity, tag))
            tag_costs[tag] = cost_per_meter
        except Exception as e:
            st.warning(f"Skipping row due to error: {e}")
else:
    st.info("Upload a CSV file with columns: `Length`, `Qty`, `Tag`, `CostPerMeter`.")

# Nesting logic
def nest_lengths(lengths, stock_length, kerf):
    bars = []
    for length in sorted(lengths, reverse=True):
        placed = False
        for bar in bars:
            remaining = stock_length - sum(bar) - kerf * (len(bar))
            if length + kerf <= remaining:
                bar.append(length)
                placed = True
                break
        if not placed:
            bars.append([length])
    return bars

# PDF export
def export_cutting_lists(tag_lengths, tag_costs, save_folder):
    os.makedirs(save_folder, exist_ok=True)

    for tag, lengths in tag_lengths.items():
        bars = nest_lengths(lengths, STOCK_LENGTH, KERF)
        total_length = sum(lengths)
        cost_per_meter = tag_costs.get(tag, 0.0)
        total_cost = (total_length / 1000) * cost_per_meter
        file_base = os.path.join(save_folder, f"{tag.replace('/', '_')}")

        # Text file
        txt_file_path = f"{file_base}.txt"
        with open(txt_file_path, 'w') as f:
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

        # PDF with bar chart
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, f"Cutting List – {tag}", ln=True)
        pdf.cell(200, 10, f"Project: {project_name} | Location: {project_location}", ln=True)
        pdf.cell(200, 10, f"Material: {material_type} | Cut By: {person_cutting}", ln=True)
        pdf.cell(200, 10, f"Total cuts: {len(lengths)} | Bars: {len(bars)}", ln=True)
        pdf.cell(200, 10, f"Total meters: {round(sum(lengths)/1000, 2)} m | Cost: R {total_cost:.2f}", ln=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmpfile:
            fig, ax = plt.subplots(figsize=(8, 4))
            for i, bar in enumerate(bars):
                left = 0
                for segment in bar:
                    ax.barh(i, segment, left=left, height=0.5)
                    left += segment + KERF
            ax.set_xlim(0, STOCK_LENGTH)
            ax.set_xlabel("mm")
            ax.set_ylabel("Bar Number")
            ax.set_title(f"Cut Layout for {tag}")
            plt.tight_layout()
            plt.savefig(tmpfile.name)
            plt.close()
            pdf.image(tmpfile.name, x=10, y=80, w=190)

        pdf_file_path = f"{file_base}.pdf"
        pdf.output(pdf_file_path)

# Run nesting
if st.button("Run Nesting"):
    if tag_lengths:
        export_cutting_lists(tag_lengths, tag_costs, save_folder)
        st.success("Nesting completed.")
        st.success(f"Files saved to '{save_folder}'")
    else:
        st.warning("No valid data to nest.")
