import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import warnings
from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set page config
st.set_page_config(
    page_title="NOP Data Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Task 1: Define Column Schemas for Selective Data Fetching
COLUMN_SCHEMAS = {
    'sitelist': [
        'Site ID', 'Site_Name', 'VENDOR', 'Class INAP W31', 
        'KABUPATEN', 'Zone', 'PIC'
    ],
    'availability': [
        'availability', 'vendor', 'site_class', 'Meet/notmeet', 
        'outage', 'duration_power', 'duration_ran', 'duration_transport', 'duration_other'
    ],
    'packet_loss': [
        'SITE ID', 'SITE NAME', 'AVG PACKET LOSS', 'PL STATUS - 0.1%'
    ],
    'prb_util': [
        'prb_util', 'dl_thp', 'cqi', 'rrc_user_max', 'kabupaten'
    ],
    'rci': [
        'kabupaten', 'prb_util_sector', 'site_id', 
        'remark_redsector_final', 'unbalanced_prb'
    ],
    'payload': [
        'tgl', 'payl (GB)', 'kabupaten', 'site_id'
    ],
    'ccm': [
        'CreateTime', 'BusinessStatus', 'SLA Category', 
        'Priority', 'RootCauseRO'
    ],
    'data_incident': [
        'Business Status', 'IN SLA / Ou SLA', 
        'Site ID (e.g. ABC123)(Create TT_siteid)', 
        'Severity(Create TT_severity)', 'Root cause category tier 1'
    ]
}

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding-top: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase() -> Client:
    """Initialize Supabase client with credentials from Streamlit secrets"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        supabase: Client = create_client(url, key)
        return supabase
    except KeyError as e:
        st.error(f"Missing Supabase configuration: {e}")
        st.info("Please ensure .streamlit/secrets.toml contains Supabase credentials")
        st.stop()
    except Exception as e:
        st.error(f"Error initializing Supabase: {e}")
        st.stop()

@st.cache_data(ttl=86400)  # Cache for 24 hours
def load_data_with_timing():
    """
    Load data from Supabase tables with:
    - Task 1: Selective column fetching
    - Task 2: Parallel table loading
    - Task 4: RCI pagination optimization
    - Task 5: Timing telemetry
    """
    
    supabase = init_supabase()
    
    # Table names matching the CSV files
    table_names = {
        'sitelist': 'SiteList',
        'availability': 'Availability',
        'packet_loss': 'Packet_Loss',
        'prb_util': 'PRB_Util',
        'rci': 'RCI',
        'payload': 'Payload',
        'ccm': 'CCM',
        'data_incident': 'Data_Incident'
    }
    
    data = {}
    progress_bar = st.progress(0)
    status_text = st.empty()
    timing_data = {}
    
    # Track overall timing
    overall_start = time.time()
    
    def fetch_all_rows(table_name, columns=None, page_size=1000):
        """
        Fetch all rows from a table using pagination with selective columns.
        Task 1 & 4: Uses column schema and adaptive page sizing for RCI
        """
        all_rows = []
        offset = 0
        
        # Task 4: Adaptive page size - RCI is large, use smaller batches
        if table_name == 'RCI':
            page_size = 500
        
        # Build column selection string (Task 1)
        if columns:
            column_str = ", ".join([f'"{col}"' for col in columns])
        else:
            column_str = "*"
        
        while True:
            try:
                response = supabase.table(table_name).select(column_str).range(offset, offset + page_size - 1).execute()
                
                if response.data:
                    all_rows.extend(response.data)
                    if len(response.data) < page_size:
                        break
                    offset += page_size
                else:
                    break
                    
            except Exception as e:
                st.error(f"Error fetching {table_name} at offset {offset}: {str(e)}")
                break
        
        return all_rows
    
    def fetch_table_task(key, table_name):
        """
        Wrapper for parallel execution with timing (Task 2 & 5)
        """
        start_time = time.time()
        try:
            columns = COLUMN_SCHEMAS.get(key)
            all_rows = fetch_all_rows(table_name, columns=columns)
            
            elapsed = time.time() - start_time
            row_count = len(all_rows) if all_rows else 0
            
            # Calculate data size estimate (roughly 1KB per row with selective columns)
            data_size_mb = (row_count * 1.0) / 1024
            
            timing_data[table_name] = {
                'elapsed_seconds': round(elapsed, 2),
                'row_count': row_count,
                'data_size_mb': round(data_size_mb, 2),
                'rows_per_second': round(row_count / elapsed, 0) if elapsed > 0 else 0
            }
            
            logger.info(f"✓ {table_name}: {row_count} rows in {elapsed:.2f}s ({timing_data[table_name]['rows_per_second']:.0f} rows/sec)")
            
            return key, table_name, all_rows, None
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"✗ {table_name} failed after {elapsed:.2f}s: {str(e)}")
            return key, table_name, None, str(e)
    
    try:
        # Task 2: Load tables in parallel using ThreadPoolExecutor (max 4 concurrent)
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all fetch tasks at once
            futures = {
                executor.submit(fetch_table_task, key, table_name): (key, table_name)
                for key, table_name in table_names.items()
            }
            
            # Process results as they complete
            completed = 0
            for future in as_completed(futures):
                key, table_name, all_rows, error = future.result()
                
                if error:
                    st.error(f"Error loading {table_name}: {error}")
                    return None, None
                
                # Convert to DataFrame
                if all_rows:
                    data[key] = pd.DataFrame(all_rows)
                else:
                    st.warning(f"⚠️ Table {table_name} is empty")
                    data[key] = pd.DataFrame()
                
                # Update status
                if table_name in timing_data:
                    status_text.text(f"✓ {table_name} ({timing_data[table_name]['row_count']} rows)")
                
                completed += 1
                progress_bar.progress(completed / len(table_names))
        
        overall_elapsed = time.time() - overall_start
        
        # Task 5: Log timing summary
        logger.info("=" * 70)
        logger.info("LOAD TIMING SUMMARY (24-hour cache)")
        logger.info("=" * 70)
        
        total_rows = 0
        total_mb = 0
        
        for table_name in sorted(table_names.values()):
            if table_name in timing_data:
                t = timing_data[table_name]
                logger.info(f"{table_name:20s} | {t['row_count']:>8d} rows | {t['elapsed_seconds']:>6.2f}s | {t['rows_per_second']:>7.0f} rows/s")
                total_rows += t['row_count']
                total_mb += t['data_size_mb']
        
        logger.info("=" * 70)
        logger.info(f"TOTAL: {total_rows} rows | {overall_elapsed:.2f}s | {total_mb:.1f}MB (est)")
        logger.info("=" * 70)
        
        status_text.success(f"✓ All data loaded in {overall_elapsed:.1f}s! (24-hour cache active)")
        progress_bar.empty()
        
        return data, timing_data
        
    except Exception as e:
        st.error(f"Error loading data from Supabase: {str(e)}")
        return None, None

# Load data
result = load_data_with_timing()

if result[0] is None:
    st.error("Failed to load data from Supabase.")
    st.stop()

data, timing_data = result

# Task 3: Pre-compute Key Metrics at Data Load Time
@st.cache_data(ttl=86400)
def compute_metrics(data):
    """Pre-compute frequently used metrics to avoid recalculation on every page render"""
    metrics = {
        'availability': {
            'avg': data['availability']['availability'].mean(),
            'min': data['availability']['availability'].min(),
            'max': data['availability']['availability'].max(),
            'total_records': len(data['availability']),
            'unique_vendors': data['availability']['vendor'].nunique(),
            'unique_classes': data['availability']['site_class'].nunique(),
        },
        'packet_loss': {
            'avg': data['packet_loss']['AVG PACKET LOSS'].mean(),
            'max': data['packet_loss']['AVG PACKET LOSS'].max(),
            'total_records': len(data['packet_loss']),
        },
        'prb_util': {
            'avg': data['prb_util']['prb_util'].mean(),
            'max': data['prb_util']['prb_util'].max(),
            'min': data['prb_util']['prb_util'].min(),
            'total_records': len(data['prb_util']),
        },
        'rci': {
            'total_records': len(data['rci']),
            'unique_sites': data['rci']['site_id'].nunique(),
        },
        'sitelist': {
            'total_sites': len(data['sitelist']),
        },
        'ccm': {
            'total_complaints': len(data['ccm']),
            'closed_count': (data['ccm']['BusinessStatus'] == 'Closed').sum(),
        },
        'data_incident': {
            'total_incidents': len(data['data_incident']),
        }
    }
    
    logger.info("Pre-computed metrics cached successfully")
    return metrics

metrics = compute_metrics(data)

# Dashboard Title
st.title("📊 NOP Data Analysis Dashboard")
st.markdown("---")

# Sidebar navigation
with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Select Dashboard:",
        ["Overview", "Availability Analysis", "Packet Loss Analysis", "PRB Utilization",
         "RCI Analysis", "Payload Analysis", "Complaints (CCM)", "Incidents", "Site Information",
         "Load Timing Stats"]
    )

# Helper function to convert week format
def week_to_date(week_str):
    """Convert YYYYWW format to date"""
    try:
        year = int(str(week_str)[:4])
        week = int(str(week_str)[4:])
        return datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
    except:
        return None

# ============== OVERVIEW PAGE ==============
if page == "Overview":
    st.header("Dashboard Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Sites", metrics['sitelist']['total_sites'])
    
    with col2:
        st.metric("Total Availability Records", metrics['availability']['total_records'])
    
    with col3:
        st.metric("Total CCM Complaints", metrics['ccm']['total_complaints'])
    
    with col4:
        st.metric("Total Incidents", metrics['data_incident']['total_incidents'])
    
    st.subheader("Key Statistics (Pre-computed)")
    
    tab1, tab2, tab3 = st.tabs(["Availability", "Packet Loss", "PRB Utilization"])
    
    with tab1:
        st.metric("Average Availability", f"{metrics['availability']['avg']:.2f}%")
        
        fig = px.histogram(data['availability'], x='availability', nbins=50, 
                          title='Availability Distribution')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.metric("Average Packet Loss", f"{metrics['packet_loss']['avg']:.4f}%")
        
        fig = px.box(data['packet_loss'], y='AVG PACKET LOSS', 
                    title='Packet Loss Distribution')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.metric("Average PRB Utilization", f"{metrics['prb_util']['avg']:.2f}%")
        
        fig = px.histogram(data['prb_util'], x='prb_util', nbins=50,
                          title='PRB Utilization Distribution')
        st.plotly_chart(fig, use_container_width=True)

# ============== AVAILABILITY ANALYSIS ==============
elif page == "Availability Analysis":
    st.header("Availability Analysis")
    
    # Filters - convert to string and remove NaN values
    col1, col2, col3 = st.columns(3)
    
    with col1:
        vendors = ['All'] + sorted([str(v) for v in data['availability']['vendor'].unique().tolist() if pd.notna(v)])
        selected_vendor = st.selectbox("Vendor", vendors)
    
    with col2:
        site_classes = ['All'] + sorted([str(c) for c in data['availability']['site_class'].unique().tolist() if pd.notna(c)])
        selected_class = st.selectbox("Site Class", site_classes)
    
    with col3:
        meet_status = ['All'] + sorted([str(m) for m in data['availability']['Meet/notmeet'].unique().tolist() if pd.notna(m)])
        selected_meet = st.selectbox("Meet/Not Meet", meet_status)
    
    # Filter data - convert to string for comparison
    filtered_ava = data['availability'].copy()
    if selected_vendor != 'All':
        filtered_ava = filtered_ava[filtered_ava['vendor'].astype(str) == selected_vendor]
    if selected_class != 'All':
        filtered_ava = filtered_ava[filtered_ava['site_class'].astype(str) == selected_class]
    if selected_meet != 'All':
        filtered_ava = filtered_ava[filtered_ava['Meet/notmeet'].astype(str) == selected_meet]
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Records", len(filtered_ava))
    with col2:
        st.metric("Avg Availability", f"{filtered_ava['availability'].mean():.2f}%")
    with col3:
        st.metric("Min Availability", f"{filtered_ava['availability'].min():.2f}%")
    with col4:
        st.metric("Max Availability", f"{filtered_ava['availability'].max():.2f}%")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.scatter(filtered_ava, x='availability', y='outage', 
                        color='vendor', title='Availability vs Outage Events')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        availability_by_vendor = filtered_ava.groupby('vendor')['availability'].mean().sort_values()
        fig = px.bar(x=availability_by_vendor.values, y=availability_by_vendor.index,
                    orientation='h', title='Average Availability by Vendor',
                    labels={'x': 'Availability (%)', 'y': 'Vendor'})
        st.plotly_chart(fig, use_container_width=True)
    
    # Outage breakdown
    st.subheader("Outage Breakdown")
    col1, col2 = st.columns(2)
    
    with col1:
        outage_types = ['power', 'ran', 'transport', 'other']
        outage_data = filtered_ava[['duration_' + col for col in outage_types]].sum()
        fig = px.pie(values=outage_data.values, names=['Power', 'RAN', 'Transport', 'Other'],
                    title='Total Duration by Outage Type')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        avg_by_class = filtered_ava.groupby('site_class')['availability'].mean().sort_values(ascending=False)
        fig = px.bar(x=avg_by_class.index, y=avg_by_class.values,
                    title='Average Availability by Site Class',
                    labels={'x': 'Site Class', 'y': 'Availability (%)'})
        st.plotly_chart(fig, use_container_width=True)

# ============== PACKET LOSS ANALYSIS ==============
elif page == "Packet Loss Analysis":
    st.header("Packet Loss Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Average Packet Loss", f"{metrics['packet_loss']['avg']:.4f}%")
    
    with col2:
        st.metric("Max Packet Loss", f"{metrics['packet_loss']['max']:.4f}%")
    
    tab1, tab2, tab3 = st.tabs(["Distribution", "Status Analysis", "Top Sites"])
    
    with tab1:
        fig = px.histogram(data['packet_loss'], x='AVG PACKET LOSS', 
                          nbins=50, title='Packet Loss Distribution')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        pl_status_dist = data['packet_loss']['PL STATUS - 0.1%'].value_counts()
        fig = px.pie(values=pl_status_dist.values, names=pl_status_dist.index,
                    title='Packet Loss Status Distribution (0.1%)')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        top_pl = data['packet_loss'].nlargest(10, 'AVG PACKET LOSS')[['SITE ID', 'SITE NAME', 'AVG PACKET LOSS']]
        fig = px.bar(top_pl, x='AVG PACKET LOSS', y='SITE NAME', 
                    orientation='h', title='Top 10 Sites by Packet Loss')
        st.plotly_chart(fig, use_container_width=True)

# ============== PRB UTILIZATION ==============
elif page == "PRB Utilization":
    st.header("PRB Utilization Analysis")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Average PRB Util", f"{metrics['prb_util']['avg']:.2f}%")
    
    with col2:
        st.metric("Max PRB Util", f"{metrics['prb_util']['max']:.2f}%")
    
    with col3:
        st.metric("Min PRB Util", f"{metrics['prb_util']['min']:.2f}%")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.scatter(data['prb_util'], x='dl_thp', y='prb_util',
                        color='cqi', size='rrc_user_max',
                        title='DL THP vs PRB Utilization (colored by CQI)')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        prb_by_dept = data['prb_util'].groupby('kabupaten')['prb_util'].mean().sort_values(ascending=False).head(10)
        fig = px.bar(x=prb_by_dept.index, y=prb_by_dept.values,
                    title='Average PRB Util by Kabupaten (Top 10)',
                    labels={'x': 'Kabupaten', 'y': 'PRB Utilization (%)'})
        st.plotly_chart(fig, use_container_width=True)

# ============== RCI ANALYSIS ==============
elif page == "RCI Analysis":
    st.header("RCI (Resource Complexity Index) Analysis")
    
    # Filter options
    kabupaten_list = ['All'] + sorted(data['rci']['kabupaten'].unique().tolist())
    selected_kab = st.selectbox("Select Kabupaten", kabupaten_list)
    
    filtered_rci = data['rci'].copy()
    if selected_kab != 'All':
        filtered_rci = filtered_rci[filtered_rci['kabupaten'] == selected_kab]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Records", len(filtered_rci))
    
    with col2:
        st.metric("Avg PRB Util (Sector)", f"{filtered_rci['prb_util_sector'].mean():.2f}%")
    
    with col3:
        st.metric("Unique Sites", filtered_rci['site_id'].nunique())
    
    col1, col2 = st.columns(2)
    
    with col1:
        sector_status = filtered_rci['remark_redsector_final'].value_counts().head(8)
        fig = px.bar(x=sector_status.index, y=sector_status.values,
                    title='Sector Status Distribution',
                    labels={'x': 'Status', 'y': 'Count'})
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        unbalanced = filtered_rci['unbalanced_prb'].value_counts()
        fig = px.pie(values=unbalanced.values, names=unbalanced.index,
                    title='PRB Balance Status')
        st.plotly_chart(fig, use_container_width=True)

# ============== PAYLOAD ANALYSIS ==============
elif page == "Payload Analysis":
    st.header("Payload Analysis")
    
    # Convert date to datetime if needed
    if data['payload']['tgl'].dtype == 'object':
        data['payload']['tgl'] = pd.to_datetime(data['payload']['tgl'])
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Payload (GB)", f"{data['payload']['payl (GB)'].sum():,.2f}")
    
    with col2:
        st.metric("Average Daily Payload (GB)", f"{data['payload']['payl (GB)'].mean():,.2f}")
    
    with col3:
        st.metric("Peak Daily Payload (GB)", f"{data['payload']['payl (GB)'].max():,.2f}")
    
    # Time series
    payload_by_date = data['payload'].groupby('tgl')['payl (GB)'].sum().sort_index()
    fig = px.line(x=payload_by_date.index, y=payload_by_date.values,
                 title='Payload Trend Over Time',
                 labels={'x': 'Date', 'y': 'Payload (GB)'})
    st.plotly_chart(fig, use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        payload_by_kab = data['payload'].groupby('kabupaten')['payl (GB)'].sum().sort_values(ascending=False).head(10)
        fig = px.bar(x=payload_by_kab.index, y=payload_by_kab.values,
                    title='Top 10 Kabupaten by Total Payload',
                    labels={'x': 'Kabupaten', 'y': 'Payload (GB)'})
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        payload_by_site = data['payload'].groupby('site_id')['payl (GB)'].sum().sort_values(ascending=False).head(10)
        fig = px.bar(x=payload_by_site.index, y=payload_by_site.values,
                    title='Top 10 Sites by Total Payload',
                    labels={'x': 'Site ID', 'y': 'Payload (GB)'})
        st.plotly_chart(fig, use_container_width=True)

# ============== COMPLAINTS (CCM) ==============
elif page == "Complaints (CCM)":
    st.header("Customer Complaints (CCM) Analysis")
    
    # Convert dates
    if data['ccm']['CreateTime'].dtype == 'object':
        data['ccm']['CreateTime'] = pd.to_datetime(data['ccm']['CreateTime'], errors='coerce')
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Complaints", len(data['ccm']))
    
    with col2:
        closed_count = (data['ccm']['BusinessStatus'] == 'Closed').sum()
        st.metric("Closed Complaints", closed_count)
    
    with col3:
        avg_sla = data['ccm']['SLA Category'].value_counts()
        st.metric("Most Common SLA", avg_sla.index[0] if len(avg_sla) > 0 else "N/A")
    
    with col4:
        by_priority = data['ccm']['Priority'].value_counts()
        st.metric("Most Common Priority", by_priority.index[0] if len(by_priority) > 0 else "N/A")
    
    col1, col2 = st.columns(2)
    
    with col1:
        status_dist = data['ccm']['BusinessStatus'].value_counts()
        fig = px.pie(values=status_dist.values, names=status_dist.index,
                    title='Complaint Status Distribution')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        priority_dist = data['ccm']['Priority'].value_counts()
        fig = px.bar(x=priority_dist.index, y=priority_dist.values,
                    title='Complaints by Priority',
                    labels={'x': 'Priority', 'y': 'Count'})
        st.plotly_chart(fig, use_container_width=True)
    
    # Root cause analysis
    st.subheader("Root Cause Analysis")
    root_cause = data['ccm']['RootCauseRO'].value_counts().head(10)
    fig = px.bar(x=root_cause.index, y=root_cause.values,
                title='Top 10 Root Causes',
                labels={'x': 'Root Cause', 'y': 'Count'})
    st.plotly_chart(fig, use_container_width=True)

# ============== INCIDENTS ==============
elif page == "Incidents":
    st.header("Data Incidents Analysis")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Incidents", len(data['data_incident']))
    
    with col2:
        closed = (data['data_incident']['Business Status'] == 'Closed').sum()
        st.metric("Closed Incidents", closed)
    
    with col3:
        in_sla = (data['data_incident']['IN SLA / Ou SLA'] == 'IN SLA').sum()
        st.metric("In SLA", in_sla)
    
    with col4:
        unique_sites = data['data_incident']['Site ID (e.g. ABC123)(Create TT_siteid)'].nunique()
        st.metric("Affected Sites", unique_sites)
    
    col1, col2 = st.columns(2)
    
    with col1:
        sla_dist = data['data_incident']['IN SLA / Ou SLA'].value_counts()
        fig = px.pie(values=sla_dist.values, names=sla_dist.index,
                    title='SLA Compliance')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        severity_dist = data['data_incident']['Severity(Create TT_severity)'].value_counts()
        fig = px.bar(x=severity_dist.index, y=severity_dist.values,
                    title='Incidents by Severity',
                    labels={'x': 'Severity', 'y': 'Count'})
        st.plotly_chart(fig, use_container_width=True)
    
    # Root cause analysis for incidents
    st.subheader("Root Cause Tier 1 Analysis")
    root_cause_t1 = data['data_incident']['Root cause category tier 1'].value_counts().head(8)
    fig = px.bar(x=root_cause_t1.index, y=root_cause_t1.values,
                title='Top Root Causes (Tier 1)',
                labels={'x': 'Root Cause', 'y': 'Count'})
    st.plotly_chart(fig, use_container_width=True)

# ============== SITE INFORMATION ==============
elif page == "Site Information":
    st.header("Site Information")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        vendors = ['All'] + sorted([str(v) for v in data['sitelist']['VENDOR'].unique().tolist() if pd.notna(v)])
        selected_vendor = st.selectbox("Filter by Vendor", vendors)
    
    with col2:
        site_classes = ['All'] + sorted([str(c) for c in data['sitelist']['Class INAP W31'].unique().tolist() if pd.notna(c)])
        selected_site_class = st.selectbox("Filter by Site Class", site_classes)
    
    with col3:
        zones = ['All'] + sorted([str(z) for z in data['sitelist']['Zone'].unique().tolist() if pd.notna(z)])
        selected_zone = st.selectbox("Filter by Zone", zones)
    
    # Filter data
    filtered_sites = data['sitelist'].copy()
    if selected_vendor != 'All':
        filtered_sites = filtered_sites[filtered_sites['VENDOR'].astype(str) == selected_vendor]
    if selected_site_class != 'All':
        filtered_sites = filtered_sites[filtered_sites['Class INAP W31'].astype(str) == selected_site_class]
    if selected_zone != 'All':
        filtered_sites = filtered_sites[filtered_sites['Zone'].astype(str) == selected_zone]
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Sites", len(filtered_sites))
    
    with col2:
        st.metric("Unique Vendors", filtered_sites['VENDOR'].nunique())
    
    with col3:
        st.metric("Unique Kabupaten", filtered_sites['KABUPATEN'].nunique())
    
    with col4:
        st.metric("Unique Zones", filtered_sites['Zone'].nunique())
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        vendor_count = filtered_sites['VENDOR'].value_counts()
        fig = px.bar(x=vendor_count.index, y=vendor_count.values,
                    title='Sites by Vendor',
                    labels={'x': 'Vendor', 'y': 'Count'})
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        class_count = filtered_sites['Class INAP W31'].value_counts()
        fig = px.pie(values=class_count.values, names=class_count.index,
                    title='Sites by Class')
        st.plotly_chart(fig, use_container_width=True)
    
    # Kabupaten distribution
    st.subheader("Sites by Kabupaten")
    kab_count = filtered_sites['KABUPATEN'].value_counts()
    fig = px.bar(x=kab_count.index, y=kab_count.values,
                title='Sites by Kabupaten',
                labels={'x': 'Kabupaten', 'y': 'Count'})
    st.plotly_chart(fig, use_container_width=True)
    
    # Data table
    st.subheader("Site Details")
    display_cols = ['Site ID', 'Site_Name', 'VENDOR', 'Class INAP W31', 'KABUPATEN', 'Zone', 'PIC']
    available_cols = [col for col in display_cols if col in filtered_sites.columns]
    st.dataframe(filtered_sites[available_cols], use_container_width=True)

# ============== LOAD TIMING STATS ==============
elif page == "Load Timing Stats":
    st.header("⏱️ Load Timing Stats")
    st.markdown("Performance telemetry from the most recent data load (cached for 24 hours).")

    if not timing_data:
        st.warning("No timing data available. Reload the page to trigger a fresh data load.")
    else:
        total_elapsed = sum(t['elapsed_seconds'] for t in timing_data.values())
        total_rows = sum(t['row_count'] for t in timing_data.values())
        total_mb = sum(t['data_size_mb'] for t in timing_data.values())

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Load Time", f"{total_elapsed:.2f}s")
        with col2:
            st.metric("Total Rows Loaded", f"{total_rows:,}")
        with col3:
            st.metric("Est. Data Size", f"{total_mb:.1f} MB")

        st.markdown("---")
        st.subheader("Per-Table Breakdown")

        # Build a summary DataFrame for display
        timing_rows = []
        for table_name in sorted(timing_data.keys()):
            t = timing_data[table_name]
            timing_rows.append({
                "Table": table_name,
                "Load Time (s)": t['elapsed_seconds'],
                "Rows": t['row_count'],
                "Est. Size (MB)": t['data_size_mb'],
                "Rows / sec": int(t['rows_per_second'])
            })
        timing_df = pd.DataFrame(timing_rows)
        st.dataframe(timing_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Visualizations")

        col1, col2 = st.columns(2)

        with col1:
            fig_time = px.bar(
                timing_df, x="Table", y="Load Time (s)",
                title="Load Time per Table (seconds)",
                labels={"Load Time (s)": "Seconds"},
                color="Load Time (s)",
                color_continuous_scale="Blues"
            )
            fig_time.update_layout(showlegend=False)
            st.plotly_chart(fig_time, use_container_width=True)

        with col2:
            fig_rows = px.bar(
                timing_df, x="Table", y="Rows",
                title="Rows Loaded per Table",
                color="Rows",
                color_continuous_scale="Greens"
            )
            fig_rows.update_layout(showlegend=False)
            st.plotly_chart(fig_rows, use_container_width=True)

        col3, col4 = st.columns(2)

        with col3:
            fig_rate = px.bar(
                timing_df, x="Table", y="Rows / sec",
                title="Fetch Rate per Table (rows/sec)",
                color="Rows / sec",
                color_continuous_scale="Oranges"
            )
            fig_rate.update_layout(showlegend=False)
            st.plotly_chart(fig_rate, use_container_width=True)

        with col4:
            fig_size = px.bar(
                timing_df, x="Table", y="Est. Size (MB)",
                title="Estimated Data Size per Table (MB)",
                color="Est. Size (MB)",
                color_continuous_scale="Purples"
            )
            fig_size.update_layout(showlegend=False)
            st.plotly_chart(fig_size, use_container_width=True)
