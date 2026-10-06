# NOP Data Analysis Dashboard

An interactive Streamlit dashboard for analyzing Network Operation Performance (NOP) data from Pekanbaru region. Visualize and explore availability, packet loss, PRB utilization, incidents, complaints, and payload metrics.

## Features

- **9 Interactive Dashboards:**
  - Overview - High-level KPIs and key metrics
  - Availability Analysis - SLA compliance and outage tracking
  - Packet Loss Analysis - Network quality metrics
  - PRB Utilization - Resource usage patterns
  - RCI Analysis - Resource complexity index by region
  - Payload Analysis - Data consumption trends
  - Complaints (CCM) - Customer complaint tracking
  - Incidents - Issue management and SLA compliance
  - Site Information - Network inventory and filtering

- **Interactive Visualizations:** Plotly charts with hover details, zoom, pan, and download
- **Dynamic Filtering:** Filter by vendor, site class, kabupaten, zones, and more
- **Real-time Metrics:** Key performance indicators and statistics
- **Data Tables:** Detailed data views with sorting and searching

## Data Source

Data is stored in **Supabase** with 8 tables:
- SiteList
- Availability
- Packet_Loss
- PRB_Util
- RCI
- Payload
- CCM
- Data_Incident

## Requirements

- Python 3.8+
- pandas
- streamlit
- plotly
- supabase-py
- python-dotenv

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Fried0nion/NOP.git
cd NOP
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Setup

### For Local Development

1. Create a `.streamlit/secrets.toml` file with your Supabase credentials:

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-anon-api-key"
```

**To get your Supabase credentials:**
- Go to [Supabase Dashboard](https://app.supabase.com)
- Select your project
- Click Settings → API
- Copy the **Project URL** and **Anon Key**

**Important:** Never commit `.streamlit/secrets.toml` to GitHub (it's in .gitignore)

2. Run the app:
```bash
streamlit run app.py
```

The dashboard will open at `http://localhost:8501`

### For Streamlit Cloud Deployment

1. Push your code to GitHub:
```bash
git add .
git commit -m "Supabase integration with Streamlit"
git push origin main
```

2. Deploy on Streamlit Cloud:
   - Go to [Streamlit Cloud](https://share.streamlit.io)
   - Click "New App"
   - Select your GitHub repo, branch `main`, and file `app.py`
   - Click "Deploy"

3. Add Supabase secrets in Streamlit Cloud:
   - In your deployed app settings, go to **Secrets**
   - Click "Edit secrets"
   - Add your Supabase credentials:
   ```toml
   [supabase]
   url = "https://your-project.supabase.co"
   key = "your-anon-api-key"
   ```
   - Save and your app will auto-refresh

4. Share the Streamlit Cloud URL with your team!

## Updating Data

### From Excel to Supabase

1. Update your Excel file locally
2. Convert sheets to CSV using the provided script:
```bash
python excel-to-csv.py
```

3. Upload CSVs to Supabase:
   - Go to [Supabase Dashboard](https://app.supabase.com)
   - For each CSV file:
     - Create a new table (or update existing)
     - Import the CSV data
   - Ensure table names match: `SiteList`, `Availability`, `Packet_Loss`, `PRB_Util`, `RCI`, `Payload`, `CCM`, `Data_Incident`

4. The Streamlit Cloud app will automatically fetch the latest data on next page refresh (cache refreshes every hour)

## Project Structure

```
├── app.py                      # Main Streamlit dashboard application
├── excel-to-csv.py             # Script to convert Excel sheets to CSV
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── .gitignore                  # Git ignore file (excludes secrets.toml)
└── data/                       # Local CSV files (for development/reference)
    ├── SiteList.csv
    ├── Availability.csv
    ├── Packet_Loss.csv
    ├── PRB_Util.csv
    ├── RCI.csv
    ├── Payload.csv
    ├── CCM.csv
    └── Data_Incident.csv
```

## Usage

1. Run the dashboard:
```bash
streamlit run app.py
```

2. Navigate using the sidebar menu to select different dashboards

3. Use filters to drill down into specific data

4. Hover over charts to see detailed information

5. Click the download icon on charts to save visualizations

## Data Sheets

- **SiteList:** Network site inventory with vendor, class, location, and contact info
- **Availability:** Site availability metrics by period with outage details
- **Packet Loss:** Weekly packet loss measurements and status
- **PRB Util:** Physical Resource Block utilization by site
- **RCI:** Resource Complexity Index with sector-level analysis
- **Payload:** Data consumption (GB) over time by site
- **CCM:** Customer complaints with root cause and SLA tracking
- **Data Incident:** Network incidents with severity and resolution tracking

## Troubleshooting

### "Missing Supabase configuration"
- Ensure `.streamlit/secrets.toml` exists with correct credentials (local)
- Ensure Secrets are added in Streamlit Cloud app settings (cloud)

### "Table not found" error
- Verify table names in Supabase match exactly: `SiteList`, `Availability`, etc.
- Ensure tables contain data (not empty)

### Data not updating
- App caches data for 1 hour
- Hard refresh the page or wait 1 hour for new data
- Check Supabase dashboard to confirm data was uploaded

