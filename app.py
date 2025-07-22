import streamlit as st
import sqlite3
import datetime
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import os

# Set page config
st.set_page_config(
    page_title="Bid Monitoring Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database setup - Use environment variable for database path in production
DB_PATH = os.getenv('DATABASE_PATH', 'bids.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

def update_database_schema():
    """Check and update database schema if needed"""
    # Check if bid_value column exists
    c.execute("PRAGMA table_info(bids)")
    columns = [col[1] for col in c.fetchall()]
    
    # Add missing columns
    if 'client_name' not in columns:
        c.execute("ALTER TABLE bids ADD COLUMN client_name TEXT")
    if 'bid_value' not in columns:
        c.execute("ALTER TABLE bids ADD COLUMN bid_value REAL")
    if 'reason' not in columns:
        c.execute("ALTER TABLE bids ADD COLUMN reason TEXT")
    if 'stage' not in columns:
        c.execute("ALTER TABLE bids ADD COLUMN stage TEXT DEFAULT 'Proposal Drafting'")
    
    conn.commit()

# Create tables with enhanced schema
c.execute('''CREATE TABLE IF NOT EXISTS bids
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             title TEXT,
             description TEXT,
             status TEXT,
             stage TEXT,
             due_date DATE,
             assigned_to TEXT,
             created_by TEXT,
             created_at DATETIME,
             client_name TEXT,
             bid_value REAL,
             reason TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS documents
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             bid_id INTEGER,
             document_name TEXT,
             sharepoint_url TEXT,
             uploaded_at DATETIME)''')

c.execute('''CREATE TABLE IF NOT EXISTS users
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             username TEXT UNIQUE,
             role TEXT)''')

# New tables for audit trail and stage transitions
c.execute('''CREATE TABLE IF NOT EXISTS bid_history
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             bid_id INTEGER,
             changed_at DATETIME,
             changed_by TEXT,
             field_changed TEXT,
             old_value TEXT,
             new_value TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS bid_stages
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             bid_id INTEGER,
             stage TEXT,
             stage_owner TEXT,
             started_at DATETIME,
             completed_at DATETIME,
             notes TEXT)''')

# Insert default admin user if empty
c.execute("SELECT COUNT(*) FROM users")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO users (username, role) VALUES (?, ?)", ("admin", "admin"))
    conn.commit()

# Define bid stages and default owners
BID_STAGES = {
    "Proposal Drafting": "Proposal Manager",
    "Legal Review": "Legal Team",
    "Pricing Review": "Finance Team",
    "Submission": "Sales Lead",
    "Evaluation": "Client",
    "Awarded": "Account Manager",
    "Lost": "Sales Lead"
}

def log_bid_history(bid_id, field_changed, old_value, new_value):
    """Record changes to bids for audit trail"""
    c.execute('''INSERT INTO bid_history
                (bid_id, changed_at, changed_by, field_changed, old_value, new_value)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (bid_id, datetime.now(), st.session_state.user[1], 
                 field_changed, str(old_value), str(new_value)))
    conn.commit()

def update_bid_stage(bid_id, new_stage, notes=""):
    """Transition bid to new stage and record the change"""
    # Complete current stage if exists
    c.execute('''UPDATE bid_stages 
                SET completed_at = ?
                WHERE bid_id = ? AND completed_at IS NULL''',
                (datetime.now(), bid_id))
    
    # Start new stage
    c.execute('''INSERT INTO bid_stages
                (bid_id, stage, stage_owner, started_at, notes)
                VALUES (?, ?, ?, ?, ?)''',
                (bid_id, new_stage, BID_STAGES.get(new_stage, "Unassigned"), 
                 datetime.now(), notes))
    conn.commit()
    
    # Notify relevant team (simulated)
    st.sidebar.success(f"Notification: Bid moved to {new_stage} stage. Owner: {BID_STAGES.get(new_stage, 'Unassigned')}")

def show_deadline_reminders():
    """Show upcoming deadlines in sidebar"""
    today = datetime.now().date()
    upcoming = pd.read_sql(
        "SELECT id, title, due_date FROM bids WHERE due_date <= ? AND status = 'Open'",
        conn, params=(today + timedelta(days=3),)
    )
    if not upcoming.empty:
        st.sidebar.warning("⚠️ Bids Due Soon")
        for _, row in upcoming.iterrows():
            st.sidebar.write(f"📌 {row['title']} (ID: {row['id']}) - due {row['due_date']}")

def show_stage_notifications():
    """Show stage transition notifications"""
    active_stages = pd.read_sql(
        '''SELECT bs.bid_id, b.title, bs.stage, bs.stage_owner 
           FROM bid_stages bs JOIN bids b ON bs.bid_id = b.id 
           WHERE bs.completed_at IS NULL''',
        conn)
    
    if not active_stages.empty:
        st.sidebar.info("🔄 Active Stages")
        for _, row in active_stages.iterrows():
            st.sidebar.write(f"🔹 {row['title']} (ID: {row['bid_id']})")
            st.sidebar.write(f"   Stage: {row['stage']} (Owner: {row['stage_owner']})")

def main():
    st.title("Bid Monitoring Platform")
    update_database_schema()
    
    # Initialize user session if not exists
    if 'user' not in st.session_state:
        st.session_state.user = ("test_id", "admin", "admin")
    
    show_deadline_reminders()
    show_stage_notifications()
    show_main_interface()

def show_dashboard():
    st.header("Bid Dashboard")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect("Filter by status", ["Open", "Submitted", "Won", "Lost"])
    with col2:
        assigned_filter = st.text_input("Filter by assigned user")

    # Query construction
    query = "SELECT * FROM bids"
    params = []
    conditions = []
    
    if status_filter:
        conditions.append(f"status IN ({','.join(['?']*len(status_filter))})")
        params.extend(status_filter)
    if assigned_filter:
        conditions.append("assigned_to LIKE ?")
        params.append(f"%{assigned_filter}%")
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # Data fetch
    bids = pd.read_sql(query, conn, params=params)

    # Display
    st.subheader("Bid Table")
    if not bids.empty:
        st.dataframe(bids, use_container_width=True)
    else:
        st.info("No bids found matching the current filters.")

    # Metrics
    st.subheader("Performance Metrics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        active_count = len(bids[bids['status'] == 'Open']) if not bids.empty else 0
        st.metric("Active Bids", active_count)
    with col2:
        if not bids.empty:
            won_bids = len(bids[bids['status'] == 'Won'])
            total_outcomes = len(bids[bids['status'].isin(['Won', 'Lost'])])
            win_rate = (won_bids / total_outcomes * 100) if total_outcomes else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")
        else:
            st.metric("Win Rate", "0%")
    with col3:
        if not bids.empty and 'bid_value' in bids.columns:
            total_value = bids['bid_value'].sum(skipna=True) / 1e6
            st.metric("Total Pipeline Value", f"${total_value:.2f}M")
        else:
            st.metric("Total Pipeline Value", "N/A")
    with col4:
        if not bids.empty:
            upcoming = len(bids[pd.to_datetime(bids['due_date']) >= datetime.now()])
            st.metric("Upcoming Deadlines", upcoming)
        else:
            st.metric("Upcoming Deadlines", 0)

    # Visualizations
    st.subheader("Performance Analysis")
    tab1, tab2, tab3 = st.tabs(["Win/Loss", "By Client", "Value Analysis"])
    
    with tab1:
        if not bids.empty:
            fig = px.pie(bids, names='status', title='Bid Status Distribution')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available for visualization")
    
    with tab2:
        if not bids.empty and 'client_name' in bids.columns:
            client_stats = bids.groupby('client_name')['status'].value_counts().unstack().fillna(0)
            st.bar_chart(client_stats)
        else:
            st.info("No client data available for visualization")
    
    with tab3:
        if not bids.empty and 'bid_value' in bids.columns:
            fig = px.box(bids, y='bid_value', x='status', 
                        title='Bid Value Distribution by Status',
                        log_y=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No bid value data available for visualization")

def show_status_summary():
    st.header("Bid Status Overview")
    bids = pd.read_sql("SELECT * FROM bids", conn)
    
    if bids.empty:
        st.warning("No bids found in the database")
        return

    # Main metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Bids", len(bids))
    with col2:
        st.metric("Active Bids", len(bids[bids['status'] == 'Open']))
    with col3:
        if not pd.to_datetime(bids['created_at']).isnull().all():
            avg_duration = (datetime.now() - pd.to_datetime(bids['created_at'])).dt.days.mean()
            st.metric("Avg Bid Duration", f"{avg_duration:.1f} days" if not pd.isnull(avg_duration) else "N/A")
        else:
            st.metric("Avg Bid Duration", "N/A")

    # Status distribution
    st.subheader("Status Distribution")
    status_counts = bids['status'].value_counts().reset_index()
    status_counts.columns = ['Status', 'Count']
    st.bar_chart(status_counts.set_index('Status'))

    # Loss reasons analysis
    if not bids[bids['status'] == 'Lost'].empty:
        st.subheader("Loss Reasons Analysis")
        loss_reasons = bids[bids['status'] == 'Lost']['reason'].value_counts()
        if not loss_reasons.empty:
            fig = px.pie(loss_reasons, values=loss_reasons.values, 
                        names=loss_reasons.index, title='Reasons for Lost Bids')
            st.plotly_chart(fig, use_container_width=True)

def create_bid():
    st.header("New Bid Creation")
    with st.form("bid_form"):
        title = st.text_input("Bid Title*")
        description = st.text_area("Description")
        client_name = st.text_input("Client Name*")
        bid_value = st.number_input("Bid Value ($)", min_value=0.0, format="%.2f")
        due_date = st.date_input("Due Date*")
        assigned_to = st.text_input("Assigned To*")
        
        if st.form_submit_button("Create Bid"):
            if not title or not client_name or not assigned_to:
                st.error("Please fill required fields (*)")
            else:
                c.execute('''INSERT INTO bids 
                            (title, description, status, stage, due_date, 
                             assigned_to, created_by, created_at, client_name, bid_value)
                            VALUES (?, ?, 'Open', 'Proposal Drafting', ?, ?, ?, ?, ?, ?)''',
                            (title, description, due_date, assigned_to, 
                             st.session_state.user[1], datetime.now(), client_name, bid_value))
                bid_id = c.lastrowid
                
                # Initialize first stage
                update_bid_stage(bid_id, "Proposal Drafting", "Bid created")
                
                conn.commit()
                st.success("Bid created successfully!")
                st.balloons()

def upload_to_sharepoint(uploaded_file, bid_id):
    """
    Placeholder for SharePoint upload logic.
    For now, just record the document in the database and return True.
    """
    document_name = uploaded_file.name
    sharepoint_url = f"https://sharepoint.example.com/{document_name}"  # Simulated URL
    uploaded_at = datetime.now()
    c.execute('''INSERT INTO documents (bid_id, document_name, sharepoint_url, uploaded_at)
                 VALUES (?, ?, ?, ?)''', (bid_id, document_name, sharepoint_url, uploaded_at))
    conn.commit()
    return True

def document_manager():
    st.header("Document Management")
    bid_id = st.number_input("Enter Bid ID", min_value=1, step=1, key="doc_bid_id")
    
    if bid_id:
        # Verify bid exists
        bid_exists = pd.read_sql("SELECT 1 FROM bids WHERE id=?", conn, params=(bid_id,))
        if bid_exists.empty:
            st.error("Bid not found")
            return
    
    uploaded_file = st.file_uploader("Upload Document", type=['pdf', 'docx', 'xlsx'])
    if uploaded_file and bid_id:
        if upload_to_sharepoint(uploaded_file, bid_id):
            st.success("Document recorded successfully")
    
    st.subheader("Attached Documents")
    if bid_id:
        documents = pd.read_sql("SELECT * FROM documents WHERE bid_id=?", conn, params=(bid_id,))
        if not documents.empty:
            st.dataframe(documents)
        else:
            st.info("No documents attached to this bid")

def manage_bid_process():
    st.header("Bid Process Management")
    
    bid_id = st.number_input("Enter Bid ID", min_value=1, step=1, key="process_bid_id")
    
    if bid_id:
        # Get bid details
        bid = pd.read_sql("SELECT * FROM bids WHERE id=?", conn, params=(bid_id,))
        
        if bid.empty:
            st.error("Bid not found")
            return
        
        st.subheader(f"Managing Bid: {bid.iloc[0]['title']}")
        
        # Current status
        current_status = bid.iloc[0]['status']
        current_stage = bid.iloc[0]['stage']
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Current Status:** {current_status}")
        with col2:
            st.write(f"**Current Stage:** {current_stage}")
        
        # Status update
        with st.expander("Update Bid Status"):
            new_status = st.selectbox("New Status", ["Open", "Submitted", "Won", "Lost"])
            
            if new_status == "Lost":
                reason = st.selectbox("Reason for Loss", 
                                    ["Pricing too high", "Missed deadline", 
                                     "Technical requirements", "Other"])
            else:
                reason = ""
                
            if st.button("Update Status"):
                old_status = bid.iloc[0]['status']
                c.execute("UPDATE bids SET status=?, reason=? WHERE id=?", 
                          (new_status, reason, bid_id))
                log_bid_history(bid_id, "status", old_status, new_status)
                conn.commit()
                st.success(f"Status updated to {new_status}")
                
                if new_status == "Won":
                    update_bid_stage(bid_id, "Awarded", "Bid won!")
                elif new_status == "Lost":
                    update_bid_stage(bid_id, "Lost", f"Bid lost: {reason}")
                st.rerun()
        
        # Stage management
        with st.expander("Manage Bid Stages"):
            st.write("**Current Stage Progress**")
            stages = pd.read_sql(
                "SELECT * FROM bid_stages WHERE bid_id=? ORDER BY started_at",
                conn, params=(bid_id,))
            
            if not stages.empty:
                st.dataframe(stages)
            
            completed_stages = stages['stage'].values if not stages.empty else []
            available_stages = [s for s in BID_STAGES.keys() if s not in completed_stages]
            
            if available_stages:
                new_stage = st.selectbox("Move to Stage", available_stages)
                notes = st.text_area("Stage Transition Notes")
                
                if st.button("Transition Stage"):
                    update_bid_stage(bid_id, new_stage, notes)
                    c.execute("UPDATE bids SET stage=? WHERE id=?", (new_stage, bid_id))
                    conn.commit()
                    st.success(f"Bid moved to {new_stage} stage")
                    st.rerun()
            else:
                st.info("All stages completed for this bid")

def show_audit_trail():
    st.header("Bid Audit Trail")
    
    bid_id = st.number_input("Enter Bid ID to view history", min_value=1, step=1)
    
    if bid_id:
        history = pd.read_sql(
            "SELECT * FROM bid_history WHERE bid_id=? ORDER BY changed_at DESC",
            conn, params=(bid_id,))
        
        if not history.empty:
            st.dataframe(history)
        else:
            st.info("No history found for this bid")
    
    st.subheader("Recent Activity Across All Bids")
    recent_activity = pd.read_sql(
        "SELECT h.*, b.title as bid_title FROM bid_history h JOIN bids b ON h.bid_id = b.id ORDER BY h.changed_at DESC LIMIT 50",
        conn)
    
    if not recent_activity.empty:
        st.dataframe(recent_activity)
    else:
        st.info("No recent activity found")

def user_admin():
    if st.session_state.user[2] != "admin":
        st.error("Unauthorized Access")
        return
    
    st.header("User Administration")
    
    with st.form("user_form"):
        username = st.text_input("Username")
        role = st.selectbox("Role", ["salesperson", "manager", "admin"])
        if st.form_submit_button("Add User"):
            try:
                c.execute("INSERT INTO users (username, role) VALUES (?, ?)", (username, role))
                conn.commit()
                st.success("User added successfully")
            except sqlite3.IntegrityError:
                st.error("Username already exists")
    
    st.subheader("Existing Users")
    users = pd.read_sql("SELECT username, role FROM users", conn)
    st.dataframe(users)

def show_main_interface():
    user_role = st.session_state.user[2]
    menu_items = ["Dashboard", "Bid Status Summary", "Create Bid", "Document Manager", "Bid Process"]
    if user_role == "admin":
        menu_items.extend(["User Admin", "Audit Trail"])

    choice = st.sidebar.radio("Menu", menu_items, key="main_menu_radio")

    if choice == "Dashboard":
        show_dashboard()
    elif choice == "Bid Status Summary":
        show_status_summary()
    elif choice == "Create Bid":
        create_bid()
    elif choice == "Document Manager":
        document_manager()
    elif choice == "Bid Process":
        manage_bid_process()
    elif choice == "User Admin":
        user_admin()
    elif choice == "Audit Trail":
        show_audit_trail()

if __name__ == "__main__":
    main()