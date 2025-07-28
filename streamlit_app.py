import os
import pandas as pd
import streamlit as st
from datetime import datetime
from fpdf import FPDF
import matplotlib.pyplot as plt
import tempfile
import zipfile

# --- CONFIG ---
st.set_page_config(page_title="Steel Nesting Planner v11.3", layout="wide")
st.title("Steel Nesting Planner v11.3")

KERF = 3  # mm kerf between cuts

# --- PROJECT METADATA ---
st.header("📋 Project Details")
project_name = st.text_input("Project Name", "")
project_location = st.text_input("Project Location", "")
person_cutting = st.text_input("Person Cutting", "")
order_number = st.text_input("Order Number", "")
supplier = st.text_input("Supplier", "")

# --- CUT LIST INPUT ---
st.header("✂️ Cut List")
cut_df = st.data_editor(
    pd.DataFrame(columns=["Length", "Quantity", "Section", "Cost_per_Meter"]),
    num_rows="dynamic",
    use_container_width=True,
    key="cutlist"
)

# --- STOCK AVAILABLE INPUT ---
st.header("🏗️ Available Stock")
stock_df = st.data_editor(
    pd.DataFrame(columns=["Stock_Length", "Quantity"]),
    num_rows="dynamic",
    use_container_width=True,
    key="stock"
)

# --- HELPER FUNCTION: Try to fit cuts into stock ---
def simulate_nesting(cut_df, stock_df):
    nesting_result = []
    remaining_cuts = []

    # Expand all cuts
    all_cuts = []
    for _, row in cut_df.iterrows():
        for _ in range(int(row["Quantity"])):
            all_cuts.append({
                "Length": int(row["Length"]),
                "Section": row["Section"],
                "Cost_per_Meter": float(row["Cost_per_Meter"])
            })

    # Sort cuts longest to shortest
    all_cuts.sort(key=lambda x: -x["Length"])

    # Expand stock bars
    stock_bars = []
    for _, row in stock_df.iterrows():
        for _ in range(int(row["Quantity"])):
            stock_bars.append({
                "Length": int(row["Stock_Length"]),
                "Remaining": int(row["Stock_Length"]),
                "Cuts": []
            })

    # Try nest each cut
    for cut in all_cuts:
        placed = False
        for bar in stock_bars:
            if cut["Length"] + KERF <= bar["Remaining"]:
                bar["Cuts"].append(cut)
                bar["Remaining"] -= (cut["Length"] + KERF)
                placed = True
                break
        if not placed:
            remaining_cuts.append(cut)

    return stock_bars, remaining_cuts

# --- NESTING LOGIC ---
if st.button("🔁 Run Nesting"):
    if cut_df.empty or stock_df.empty:
        st.warning("Please enter both a cut list and available stock.")
    else:
        bars_used, cuts_remaining = simulate_nesting(cut_df, stock_df)

        # Display results
        st.success("Nesting completed.")
        st.header("📦 Nesting Summary")

        total_cost = 0.0
        for i, bar in enumerate(bars_used):
            if bar["Cuts"]:
                st.subheader(f"Bar {i+1} – {bar['Length']}mm")
                cuts_data = pd.DataFrame(bar["Cuts"])
                st.dataframe(cuts_data, use_container_width=True)
                used_length = sum(c["Length"] + KERF for c in bar["Cuts"])
                cost = sum(c["Length"] * c["Cost_per_Meter"] / 1000 for c in bar["Cuts"])
                total_cost += cost

                fig, ax = plt.subplots(figsize=(6, 0.4))
                current = 0
                for cut in bar["Cuts"]:
                    ax.barh(0, cut["Length"], left=current, edgecolor='black')
                    current += cut["Length"] + KERF
                ax.set_xlim(0, bar["Length"])
                ax.axis('off')
                st.pyplot(fig)

        if cuts_remaining:
            st.warning(f"⚠️ {len(cuts_remaining)} cuts could not be nested due to lack of stock.")
            st.dataframe(pd.DataFrame(cuts_remaining), use_container_width=True)

        st.markdown(f"💰 **Estimated Total Cost:** R {total_cost:,.2f}")

        # --- EXPORT TO PDF & TXT ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Nesting Report – {project_name}", ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Location: {project_location} | Cut By: {person_cutting}", ln=True)
        pdf.cell(0, 10, f"Order: {order_number} | Supplier: {supplier}", ln=True)
        pdf.ln()

        for i, bar in enumerate(bars_used):
            if bar["Cuts"]:
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, f"Bar {i+1} – {bar['Length']}mm", ln=True)
                pdf.set_font("Arial", "", 10)
                for cut in bar["Cuts"]:
                    pdf.cell(0, 10, f" - {cut['Length']}mm [{cut['Section']}] @ R{cut['Cost_per_Meter']}/m", ln=True)
                pdf.ln()

        if cuts_remaining:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, "⚠️ Unfulfilled Cuts", ln=True)
            pdf.set_font("Arial", "", 10)
            for cut in cuts_remaining:
                pdf.cell(0, 10, f" - {cut['Length']}mm [{cut['Section']}]", ln=True)

        pdf.ln()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Total Estimated Cost: R {total_cost:,.2f}", ln=True)

        # Save to temp files
        with tempfile.TemporaryDirectory() as tmpdirname:
            pdf_path = os.path.join(tmpdirname, f"nesting_report_{timestamp}.pdf")
            txt_path = os.path.join(tmpdirname, f"nesting_summary_{timestamp}.txt")
            zip_path = os.path.join(tmpdirname, f"nesting_output_{timestamp}.zip")

            pdf.output(pdf_path)

            # Write TXT summary
            with open(txt_path, "w") as txt:
                txt.write(f"Nesting Summary – {project_name}\n")
                txt.write(f"Location: {project_location}\n")
                txt.write(f"Person Cutting: {person_cutting}\n")
                txt.write(f"Order Number: {order_number}\n")
                txt.write(f"Supplier: {supplier}\n\n")
                for i, bar in enumerate(bars_used):
                    if bar["Cuts"]:
                        txt.write(f"Bar {i+1} – {bar['Length']}mm:\n")
                        for cut in bar["Cuts"]:
                            txt.write(f" - {cut['Length']}mm [{cut['Section']}] @ R{cut['Cost_per_Meter']}/m\n")
                        txt.write("\n")
                if cuts_remaining:
                    txt.write("Unfulfilled Cuts:\n")
                    for cut in cuts_remaining:
                        txt.write(f" - {cut['Length']}mm [{cut['Section']}]\n")
                txt.write(f"\nTotal Cost: R {total_cost:,.2f}\n")

            # Zip it
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(pdf_path, os.path.basename(pdf_path))
                zipf.write(txt_path, os.path.basename(txt_path))

            # Streamlit download
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download ZIP (PDF + TXT)",
                    data=f,
                    file_name=f"nesting_output_{timestamp}.zip",
                    mime="application/zip"
                )
