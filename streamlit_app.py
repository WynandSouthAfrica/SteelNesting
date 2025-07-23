import os
import csv
from collections import defaultdict
from datetime import datetime
from fpdf import FPDF
import matplotlib.pyplot as plt
import tempfile
import streamlit as st

# Page setup
st.set_page_config(page_title="Steel Nesting Planner", layout="wide")
st.title("Steel Nesting Planner v10.7")

# Constants
STOCK_LENGTH = 6000  # mm
KERF = 3             # mm

# Step 1: Enter Project Metadata
st.header("🔧 Project Details")
project_name = st.text_input("Project Name")
project_location = st.text_input("Project Location")
person_cutting = st.text_input("Person Cutting")
material_type = st.text_input("Material Type")
save_folder = st.text_input("Folder to save cutting lists (e.g., CuttingLists/ProjectA)", value="CuttingLists")
today = datetime.today().strftime('%Y-%m-%d')

# Step 2: Upload CSV or input manually
import io
import csv

raw_entries = []
tag_costs = {}
tag_lengths = {}

if uploaded_file:
    csv_file = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    csv_reader = csv.DictReader(csv_file)

    for row in csv_reader:
        try:
            length = int(float(row["Length"]))
            quantity = int(row["Qty"])
            tag = row["Tag"].strip()
            cost_per_meter = float(row["CostPerMeter"])

            if tag not in tag_costs:
                tag_costs[tag] = cost_per_meter
                tag_lengths[tag] = []

            tag_lengths[tag].extend([length] * quantity)

        except Exception as e:
            st.warning(f"Skipping row due to error: {e}")
else:
    st.info("Upload a CSV file with columns: `Length`, `Qty`, `Tag`, `CostPerMeter`.")

# Nesting logic
def perform_nesting(entries, kerf):
    tags = defaultdict(list)
    for length, quantity, tag in entries:
        for _ in range(quantity):
            tags[tag].append(length)

    cutting_data = {}
    for tag, lengths in tags.items():
        lengths.sort(reverse=True)
        bars = []
        for l in lengths:
            placed = False
            for bar in bars:
                if sum(bar) + kerf * len(bar) + l <= STOCK_LENGTH:
                    bar.append(l)
                    placed = True
                    break
            if not placed:
                bars.append([l])
        cutting_data[tag] = bars
    return cutting_data

# Process + export
if st.button("Run Nesting"):
    if not raw_entries:
        st.error("No input data found.")
    else:
        nested = perform_nesting(raw_entries, KERF)
        st.success("Nesting completed.")

        # Create output folder
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)

        txt_output = os.path.join(save_folder, f"{project_name}_CuttingList.txt")
        pdf_output = os.path.join(save_folder, f"{project_name}_CuttingList.pdf")

        # TXT Export
        with open(txt_output, "w") as txt:
            txt.write(f"Project: {project_name}\nLocation: {project_location}\nCut by: {person_cutting}\nMaterial: {material_type}\nDate: {today}\n\n")
            for tag, bars in nested.items():
                txt.write(f"--- {tag} ---\n")
                for i, bar in enumerate(bars, 1):
                    total = sum(bar) + KERF * (len(bar) - 1)
                    remaining = STOCK_LENGTH - total
                    txt.write(f"Bar {i}: {bar} | Remaining: {remaining}mm\n")
                txt.write("\n")

        # PDF Export
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, f"Steel Nesting Summary - {project_name}", ln=True)
        for tag, bars in nested.items():
            total_cuts = sum(len(bar) for bar in bars)
            total_meters = sum(sum(bar) + KERF * (len(bar)-1) for bar in bars) / 1000
            cost_per_meter = tag_costs.get(tag, 0.0)
            total_cost = total_meters * cost_per_meter

            pdf.set_font("Arial", "B", size=11)
            pdf.cell(200, 10, f"\nSection: {tag}", ln=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(200, 8, f"Total Cuts: {total_cuts}", ln=True)
            pdf.cell(200, 8, f"Meters Ordered: {total_meters:.2f} m", ln=True)
            pdf.cell(200, 8, f"Cost/m: R {cost_per_meter:.2f}", ln=True)
            pdf.cell(200, 8, f"Total Cost: R {total_cost:.2f}", ln=True)

        pdf.output(pdf_output)
        st.success(f"Files saved to '{save_folder}'")
