from fpdf import FPDF
import matplotlib.pyplot as plt
import tempfile

st.set_page_config(page_title="Steel Nesting Planner", layout="wide")
st.title("Steel Nesting Planner v10.7")

# Step 1: Enter Project Metadata
st.header("Project Details")
project_name = st.text_input("Project Name")
project_location = st.text_input("Project Location")
person_cutting = st.text_input("Person Cutting")
material_type = st.text_input("Material Type")
save_folder = st.text_input("Folder to save cutting lists (e.g., CuttingLists/ProjectA)", value="CuttingLists")
today = datetime.today().strftime('%Y-%m-%d')

STOCK_LENGTH = 6000  # mm
KERF = 3             # mm

# Step 1: Get project metadata
print("Enter project details:")
project_name = input("Project Name      : ").strip()
project_location = input("Project Location  : ").strip()
person_cutting = input("Person Cutting    : ").strip()
material_type = input("Material Type     : ").strip()
save_folder = input("Folder to save cutting lists (e.g. CuttingLists/ProjectA): ").strip()
today = datetime.today().strftime('%Y-%m-%d')

if not os.path.exists(save_folder):
    os.makedirs(save_folder)

# Step 2: Ask for CSV file path
csv_input_path = input("\n(Optional) Enter full path to CSV input file or leave blank to type manually:\n> ").strip()
raw_entries = []
tag_costs = {}

if csv_input_path and os.path.exists(csv_input_path):
    print(f"Reading cutting list from {csv_input_path}...")
    with open(csv_input_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                length = int(row['Length'])
                qty = int(row['Qty'])
                tag = row['Tag'].strip()
                cost_per_meter = float(row['CostPerMeter'])
                raw_entries.append((length, qty, tag))
                tag_costs[tag] = cost_per_meter
            except Exception as e:
                print(f"Error in row: {row} — {e}")
else:
    print("\nNo valid CSV found. Please enter your lengths, quantities, tags, and cost per meter manually (e.g. 560 4 50x50x6-EA 38.75).\nType 'done' when finished.\n")
    while True:
        line = input("Length Qty Tag Cost/m: ").strip()
        if line.lower() == 'done':
            break
        try:
            parts = line.split()
            if len(parts) < 4:
                print("Please enter: length quantity tag cost_per_meter")
                continue
            length = int(parts[0])
            qty = int(parts[1])
            tag = ' '.join(parts[2:-1])
            cost_per_meter = float(parts[-1])
            raw_entries.append((length, qty, tag))
            tag_costs[tag] = cost_per_meter
        except ValueError:
            print("Invalid input. Please enter like '560 4 50x50x6-EA 38.75'")

# Step 3: Group entries by tag
tagged_entries = defaultdict(list)
for length, qty, tag in raw_entries:
    tagged_entries[tag].extend([length] * qty)

summary_data = []

# Step 4: Process each tag group
for tag, required_lengths in tagged_entries.items():
    required_lengths.sort(reverse=True)
    stock_usage = []
    cost_per_meter = tag_costs.get(tag, 0.0)
    total_cut_length = sum(required_lengths)

    for length in required_lengths:
        placed = False
        for stock in stock_usage:
            used = sum(stock['cuts']) + KERF * (len(stock['cuts']))
            if used + length <= STOCK_LENGTH:
                stock['cuts'].append(length)
                placed = True
                break
        if not placed:
            stock_usage.append({'cuts': [length]})

    total_bars = len(stock_usage)
    total_length_mm = total_bars * STOCK_LENGTH
    total_length_m = total_length_mm / 1000
    total_cost = total_length_m * cost_per_meter

    summary_data.append({
        'tag': tag,
        'bars': total_bars,
        'cut_length': total_cut_length,
        'meters': total_length_m,
        'cost_per_m': cost_per_meter,
        'total_cost': total_cost
    })

    safe_tag = tag.replace("/", "-").replace(" ", "_")

    # Save PDF
    pdf_path = os.path.join(save_folder, f"{safe_tag}_CuttingList.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt=f"Cutting List for: {tag}", ln=True)
    pdf.cell(200, 10, txt=f"Project Name      : {project_name}", ln=True)
    pdf.cell(200, 10, txt=f"Project Location  : {project_location}", ln=True)
    pdf.cell(200, 10, txt=f"Person Cutting    : {person_cutting}", ln=True)
    pdf.cell(200, 10, txt=f"Date              : {today}", ln=True)
    pdf.cell(200, 10, txt=f"Material Type     : {material_type}", ln=True)
    pdf.cell(200, 10, txt=f"Material Tag      : {tag}", ln=True)
    pdf.cell(200, 10, txt=f"Cost per meter    : R{cost_per_meter:.2f}", ln=True)
    pdf.ln(5)

    pdf.cell(200, 10, txt=f"Total stock bars needed: {total_bars}", ln=True)
    pdf.cell(200, 10, txt=f"Total length to order: {total_length_mm} mm ({total_length_m:.2f} meters)", ln=True)
    pdf.cell(200, 10, txt=f"Estimated material cost: R{total_cost:.2f}", ln=True)
    pdf.ln(5)

    for i, stock in enumerate(stock_usage, 1):
        cuts = stock['cuts']
        total_used = sum(cuts) + KERF * (len(cuts) - 1)
        remaining = STOCK_LENGTH - total_used
        pdf.cell(200, 10, txt=f"Stock {i}:", ln=True)
        pdf.cell(200, 10, txt=f"  Cuts = {cuts}", ln=True)
        pdf.cell(200, 10, txt=f"  Used = {total_used} mm | Remaining = {remaining} mm", ln=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
            fig, ax = plt.subplots(figsize=(8, 1))
            x = 0
            for cut in cuts:
                ax.barh(0, cut, left=x, height=0.8, color='steelblue')
                ax.text(x + cut / 2, 0, str(cut), va='center', ha='center', color='white', fontsize=8)
                x += cut + KERF
            if x < STOCK_LENGTH:
                ax.barh(0, STOCK_LENGTH - x, left=x, height=0.8, color='lightgrey')
            ax.set_xlim(0, STOCK_LENGTH)
            ax.set_yticks([])
            ax.set_title(f"Stock {i} Layout", fontsize=9)
            plt.tight_layout()
            plt.savefig(tmp_img.name)
            plt.close()
            pdf.image(tmp_img.name, x=10, w=190)

    pdf.output(pdf_path)
    print(f"PDF saved to: {pdf_path}")

# Final Summary PDF
summary_pdf = os.path.join(save_folder, "CuttingList_Summary.pdf")
pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", size=12)
pdf.cell(200, 10, f"PROJECT SUMMARY - {project_name}", ln=True)
pdf.cell(200, 10, f"Date: {today}", ln=True)
pdf.ln(5)

pdf.set_font("Arial", 'B', size=10)
pdf.cell(50, 10, "Tag", border=1)
pdf.cell(15, 10, "Bars", border=1)
pdf.cell(25, 10, "Cuts (mm)", border=1)
pdf.cell(25, 10, "Meters", border=1)
pdf.cell(25, 10, "R/m", border=1)
pdf.cell(40, 10, "Total Cost", border=1)
pdf.ln()

pdf.set_font("Arial", size=10)
total_bars = total_cut = total_m = total_r = 0
for entry in summary_data:
    pdf.cell(50, 10, entry['tag'], border=1)
    pdf.cell(15, 10, str(entry['bars']), border=1)
    pdf.cell(25, 10, str(entry['cut_length']), border=1)
    pdf.cell(25, 10, f"{entry['meters']:.2f}", border=1)
    pdf.cell(25, 10, f"R{entry['cost_per_m']:.2f}", border=1)
    pdf.cell(40, 10, f"R{entry['total_cost']:.2f}", border=1)
    pdf.ln()
    total_bars += entry['bars']
    total_cut += entry['cut_length']
    total_m += entry['meters']
    total_r += entry['total_cost']

pdf.set_font("Arial", 'B', size=10)
pdf.cell(50, 10, "TOTAL", border=1)
pdf.cell(15, 10, str(total_bars), border=1)
pdf.cell(25, 10, str(total_cut), border=1)
pdf.cell(25, 10, f"{total_m:.2f}", border=1)
pdf.cell(25, 10, "", border=1)
pdf.cell(40, 10, f"R{total_r:.2f}", border=1)

pdf.output(summary_pdf)
print(f"Summary PDF saved to: {summary_pdf}")
