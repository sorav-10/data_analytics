import streamlit as st
import duckdb
import pandas as pd
import datetime

# Set page layout and config
st.set_page_config(
    page_title="Logistics Analytics Dashboard",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Premium Look
st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        h1 { font-weight: 800; background: linear-gradient(90deg, #4F46E5, #06B6D4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    </style>
""", unsafe_allow_html=True)

DB_FILE = "logistics_analysis.db"

def query_db(query):
    con = duckdb.connect(DB_FILE, read_only=True)
    try:
        return con.execute(query).df()
    finally:
        con.close()


# Title
st.title("Logistics Performance Dashboard")

# Sidebar Filters
st.sidebar.header("Filter Options")

# Fetch unique regions and statuses for dropdowns
regions_list = ["All"] + list(query_db("SELECT DISTINCT region FROM golden.obt_shipments ORDER BY region;")["region"])
statuses_list = ["All"] + list(query_db("SELECT DISTINCT status FROM golden.obt_shipments ORDER BY status;")["status"])
date_bounds = query_db("SELECT MIN(ship_date) as min_s, MAX(ship_date) as max_s FROM golden.obt_shipments")
if not date_bounds.empty and pd.notna(date_bounds.iloc[0]['min_s']):
    min_date = pd.to_datetime(date_bounds.iloc[0]['min_s']).date()
    max_date = pd.to_datetime(date_bounds.iloc[0]['max_s']).date()
else:
    min_date = datetime.date.today() - datetime.timedelta(days=7)
    max_date = datetime.date.today()


selected_region = st.sidebar.selectbox("Warehouse Region", regions_list)
selected_status = st.sidebar.selectbox("Shipment Status", statuses_list)
selected_date_range = st.sidebar.date_input(
    "Shipment Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)


# Build dynamic query based on filters
where_clauses = []
if selected_region != "All":
    where_clauses.append(f"region = '{selected_region}'")
if selected_status != "All":
    where_clauses.append(f"status = '{selected_status}'")
if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
    start_date, end_date = selected_date_range
    where_clauses.append(f"ship_date BETWEEN '{start_date}' AND '{end_date}'")

where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""


# Load Filtered Data
metrics_df = query_db(f"""
    SELECT 
        COUNT(*)::INT AS total_shipments,
        ROUND(AVG(delivery_date - ship_date), 1) AS avg_days_in_transit,
        ROUND(SUM(weight), 1) AS total_weight_kg,
        COUNT(CASE WHEN status = 'Pending' THEN 1 END) AS pending_shipments,
        COUNT(CASE WHEN status = 'Delivered' THEN 1 END) AS delivered_shipments,
        COUNT(CASE WHEN status IN ('Failed', 'NA') THEN 1 END) AS failed_shipments,
        ROUND(COUNT(CASE WHEN status = 'Delivered' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN status IN ('Delivered', 'Failed', 'NA') THEN 1 END), 0), 1) AS success_rate
    FROM golden.obt_shipments
    {where_str};
""")

# Render KPIs
if not metrics_df.empty:
    kpis = metrics_df.iloc[0]
    
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    with col1:
        st.metric(label="Total Shipments", value=f"{kpis['total_shipments']:,}")
    with col2:
        st.metric(label="Pending Shipments", value=f"{kpis['pending_shipments']:,}")
    with col3:
        st.metric(label="Delivered Shipments", value=f"{kpis['delivered_shipments']}")
    with col4:
        st.metric(label="Failed/NA Shipments", value=f"{kpis['failed_shipments']}")
    with col5:
        st.metric(label="Delivery Success Rate", value=f"{kpis['success_rate']}%")
    with col6:
        st.metric(label="Avg Days in Transit", value=f"{kpis['avg_days_in_transit']} Days")
    with col7:
        st.metric(label="Total Weight Shipped", value=f"{kpis['total_weight_kg']:,} Kgs")

st.markdown("---")

# Main Dashboard Sections
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Carrier Delivery Performance")
    carrier_df = query_db(f"""
        SELECT 
            carrier_name,
            ROUND(AVG(delivery_date - ship_date), 1) AS avg_days
        FROM golden.obt_shipments
        {where_str}
        {(' AND ' if where_str else 'WHERE ')} delivery_date IS NOT NULL AND ship_date IS NOT NULL
        GROUP BY carrier_name
        ORDER BY avg_days ASC;
    """)
    if not carrier_df.empty:
        st.bar_chart(data=carrier_df.set_index("carrier_name")["avg_days"])
    else:
        st.info("No carrier data available for the current filter selection.")

with col_right:
    st.subheader("Regional Delivery Summary")
    region_df = query_db(f"""
        SELECT 
            region AS warehouse_region,
            COUNT(*)::INT AS total_shipments,
            ROUND(AVG(delivery_date - ship_date), 1) AS avg_days
        FROM golden.obt_shipments
        {where_str}
        {(' AND ' if where_str else 'WHERE ')} delivery_date IS NOT NULL AND ship_date IS NOT NULL
        GROUP BY region
        ORDER BY total_shipments DESC;
    """)
    if not region_df.empty:
        st.dataframe(region_df, width='stretch', hide_index=True)
    else:
        st.info("No regional data available.")

st.markdown("---")

# Tabular Data List with Search
st.subheader("Recent Shipment Operations")
search_id = st.text_input("Search Shipment ID", "")

search_clause = f"AND shipment_id ILIKE '%{search_id}%'" if search_id else ""
where_shipments = f"{where_str} {search_clause}" if where_str else (f"WHERE {search_clause[4:]}" if search_id else "")

shipments_df = query_db(f"""
    SELECT 
        shipment_id,
        order_id,
        carrier_name,
        region,
        ship_date,
        delivery_date,
        status,
        weight
    FROM golden.obt_shipments
    {where_shipments}
    ORDER BY copied_at DESC
    LIMIT 100;
""")

if not shipments_df.empty:
    st.dataframe(shipments_df, width='stretch', hide_index=True)
else:
    st.info("No shipments match the current search or filter options.")
