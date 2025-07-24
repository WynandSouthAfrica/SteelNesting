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
            os.makedirs(save_folder, exist_ok=Tru
