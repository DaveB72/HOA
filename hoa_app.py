import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.express as px
from io import StringIO
import os

# Database connection
@st.cache_resource
def init_connection():
    return psycopg2.connect(
        host=st.secrets.get("DB_HOST", "localhost"),
        database=st.secrets.get("DB_NAME", "hoa_db"),
        user=st.secrets.get("DB_USER", "postgres"),
        password=st.secrets.get("DB_PASSWORD", "password"),
        port=st.secrets.get("DB_PORT", 5432)
    )

# Database helper functions
def execute_query(query, params=None, fetch=True):
    conn = init_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            return cur.fetchall()
        else:
            conn.commit()
            return cur.rowcount
    except Exception as e:
        st.error(f"Database error: {e}")
        return None
    finally:
        cur.close()

def get_properties():
    query = """
    SELECT p.id, p.address, p.unit_number, p.hoa_fees_monthly,
           r.first_name || ' ' || r.last_name as primary_contact,
           r.email
    FROM properties p
    LEFT JOIN residents r ON p.id = r.property_id AND r.is_primary_contact = true
    ORDER BY p.address, p.unit_number
    """
    return execute_query(query)

def get_maintenance_requests():
    query = """
    SELECT mr.id, p.address, p.unit_number, mr.request_type, mr.title, 
           mr.status, mr.priority, mr.created_date, mr.estimated_cost
    FROM maintenance_requests mr
    JOIN properties p ON mr.property_id = p.id
    ORDER BY mr.created_date DESC
    """
    return execute_query(query)

def get_financial_summary():
    query = """
    SELECT 
        COUNT(DISTINCT property_id) as total_properties,
        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_assessments,
        SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_payments,
        SUM(amount) as net_balance
    FROM financial_transactions
    """
    return execute_query(query)

# Email functions
def send_email(to_email, subject, body, smtp_server="smtp.gmail.com", smtp_port=587):
    try:
        # You'll need to set these in your Streamlit secrets
        sender_email = st.secrets.get("EMAIL_USER", "your_hoa@gmail.com")
        sender_password = st.secrets.get("EMAIL_PASSWORD", "your_app_password")
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email error: {e}")
        return False

# Main Streamlit app
def main():
    st.set_page_config(page_title="HOA Management System", layout="wide")
    
    st.title("🏘️ HOA Management System")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", [
        "Dashboard", 
        "Properties", 
        "Maintenance Requests", 
        "Financial Management", 
        "Email Center"
    ])
    
    if page == "Dashboard":
        show_dashboard()
    elif page == "Properties":
        show_properties()
    elif page == "Maintenance Requests":
        show_maintenance()
    elif page == "Financial Management":
        show_financial()
    elif page == "Email Center":
        show_email_center()

def show_dashboard():
    st.header("📊 HOA Dashboard")
    
    col1, col2, col3 = st.columns(3)
    
    # Get summary statistics
    properties_data = get_properties()
    maintenance_data = get_maintenance_requests()
    financial_data = get_financial_summary()
    
    if properties_data:
        with col1:
            st.metric("Total Properties", len(properties_data))
        
    if maintenance_data:
        open_requests = len([r for r in maintenance_data if r[5] == 'Open'])
        with col2:
            st.metric("Open Maintenance Requests", open_requests)
    
    if financial_data and financial_data[0]:
        with col3:
            net_balance = financial_data[0][3] or 0
            st.metric("Net Balance", f"${net_balance:,.2f}")
    
    # Recent maintenance requests
    st.subheader("Recent Maintenance Requests")
    if maintenance_data:
        df = pd.DataFrame(maintenance_data, columns=[
            'ID', 'Address', 'Unit', 'Type', 'Title', 'Status', 'Priority', 'Created', 'Est. Cost'
        ])
        st.dataframe(df.head(10), use_container_width=True)

def show_properties():
    st.header("🏠 Property Management")
    
    tab1, tab2, tab3, tab4 = st.tabs(["View Properties", "Add Property", "Edit Property", "Delete Property"])
    
    with tab1:
        properties_data = get_properties()
        if properties_data:
            df = pd.DataFrame(properties_data, columns=[
                'ID', 'Address', 'Unit', 'Monthly Fee', 'Primary Contact', 'Email'
            ])
            st.dataframe(df, use_container_width=True)
    
    with tab2:
        st.subheader("Add New Property")
        with st.form("add_property"):
            address = st.text_input("Address")
            unit_number = st.text_input("Unit Number (if applicable)")
            hoa_fee = st.number_input("Monthly HOA Fee", min_value=0.0, step=10.0)
            
            # Resident information
            st.subheader("Primary Contact")
            first_name = st.text_input("First Name")
            last_name = st.text_input("Last Name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            
            submitted = st.form_submit_button("Add Property")
            if submitted and address and first_name and last_name:
                # Insert property
                property_query = """
                INSERT INTO properties (address, unit_number, hoa_fees_monthly) 
                VALUES (%s, %s, %s) RETURNING id
                """
                result = execute_query(property_query, (address, unit_number, hoa_fee), fetch=True)
                
                if result:
                    property_id = result[0][0]
                    # Insert resident
                    resident_query = """
                    INSERT INTO residents (property_id, first_name, last_name, email, phone, is_primary_contact)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    execute_query(resident_query, (property_id, first_name, last_name, email, phone, True), fetch=False)
                    st.success("Property added successfully!")
                    st.rerun()
    
    with tab3:
        st.subheader("Edit Property")
        
        # Get properties for dropdown
        properties_data = get_properties()
        if properties_data:
            property_options = {}
            for row in properties_data:
                display_text = f"{row[1]} {row[2] or ''}".strip()
                property_options[display_text] = row[0]
            
            selected_property = st.selectbox("Select Property to Edit", list(property_options.keys()))
            
            if selected_property:
                property_id = property_options[selected_property]
                
                # Get full property and resident details
                property_query = """
                SELECT p.id, p.address, p.unit_number, p.property_type, p.square_footage, 
                       p.lot_size_sqft, p.hoa_fees_monthly,
                       r.id as resident_id, r.first_name, r.last_name, r.email, r.phone,
                       r.is_owner, r.move_in_date
                FROM properties p
                LEFT JOIN residents r ON p.id = r.property_id AND r.is_primary_contact = true
                WHERE p.id = %s
                """
                property_details = execute_query(property_query, (property_id,))
                
                if property_details:
                    details = property_details[0]
                    
                    with st.form("edit_property"):
                        st.subheader("Property Information")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            new_address = st.text_input("Address", value=details[1] if details[1] else "")
                            new_unit = st.text_input("Unit Number", value=details[2] if details[2] else "")
                            new_property_type = st.selectbox("Property Type", 
                                ["Single Family", "Condo", "Townhome"],
                                index=["Single Family", "Condo", "Townhome"].index(details[3]) if details[3] in ["Single Family", "Condo", "Townhome"] else 0)
                        
                        with col2:
                            new_square_footage = st.number_input("Square Footage", 
                                value=int(details[4]) if details[4] else 0, min_value=0)
                            new_lot_size = st.number_input("Lot Size (sq ft)", 
                                value=int(details[5]) if details[5] else 0, min_value=0)
                            new_hoa_fee = st.number_input("Monthly HOA Fee", 
                                value=float(details[6]) if details[6] else 0.0, step=10.0)
                        
                        st.subheader("Primary Contact Information")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            new_first_name = st.text_input("First Name", value=details[8] if details[8] else "")
                            new_last_name = st.text_input("Last Name", value=details[9] if details[9] else "")
                            new_email = st.text_input("Email", value=details[10] if details[10] else "")
                        
                        with col2:
                            new_phone = st.text_input("Phone", value=details[11] if details[11] else "")
                            new_is_owner = st.checkbox("Is Owner", value=details[12] if details[12] else True)
                            new_move_in_date = st.date_input("Move In Date", 
                                value=details[13] if details[13] else None)
                        
                        submitted = st.form_submit_button("Update Property")
                        
                        if submitted and new_address and new_first_name and new_last_name:
                            # Update property
                            update_property_query = """
                            UPDATE properties 
                            SET address = %s, unit_number = %s, property_type = %s, 
                                square_footage = %s, lot_size_sqft = %s, hoa_fees_monthly = %s,
                                updated_date = NOW()
                            WHERE id = %s
                            """
                            result1 = execute_query(update_property_query, 
                                (new_address, new_unit, new_property_type, new_square_footage, 
                                 new_lot_size, new_hoa_fee, property_id), fetch=False)
                            
                            # Update or insert resident
                            if details[7]:  # Resident exists
                                update_resident_query = """
                                UPDATE residents 
                                SET first_name = %s, last_name = %s, email = %s, phone = %s,
                                    is_owner = %s, move_in_date = %s
                                WHERE id = %s
                                """
                                result2 = execute_query(update_resident_query,
                                    (new_first_name, new_last_name, new_email, new_phone,
                                     new_is_owner, new_move_in_date, details[7]), fetch=False)
                            else:  # Create new resident
                                insert_resident_query = """
                                INSERT INTO residents (property_id, first_name, last_name, email, phone,
                                                     is_owner, is_primary_contact, move_in_date)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                """
                                result2 = execute_query(insert_resident_query,
                                    (property_id, new_first_name, new_last_name, new_email, new_phone,
                                     new_is_owner, True, new_move_in_date), fetch=False)
                            
                            if result1:
                                st.success("Property updated successfully!")
                                st.rerun()
        else:
            st.info("No properties found. Add some properties first.")
    
    with tab4:
        st.subheader("🗑️ Delete Property")
        st.warning("⚠️ **Warning**: Deleting a property will also delete all associated residents, maintenance requests, and financial transactions!")
        
        properties_data = get_properties()
        if properties_data:
            property_options = {}
            for row in properties_data:
                display_text = f"{row[1]} {row[2] or ''}".strip()
                property_options[display_text] = row[0]
            
            selected_property = st.selectbox("Select Property to Delete", 
                [""] + list(property_options.keys()))
            
            if selected_property and selected_property != "":
                property_id = property_options[selected_property]
                
                # Get property details and counts of related records
                detail_query = """
                SELECT p.address, p.unit_number, p.hoa_fees_monthly,
                       r.first_name || ' ' || r.last_name as primary_contact,
                       COUNT(DISTINCT mr.id) as maintenance_count,
                       COUNT(DISTINCT ft.id) as financial_count
                FROM properties p
                LEFT JOIN residents r ON p.id = r.property_id AND r.is_primary_contact = true
                LEFT JOIN maintenance_requests mr ON p.id = mr.property_id
                LEFT JOIN financial_transactions ft ON p.id = ft.property_id
                WHERE p.id = %s
                GROUP BY p.id, p.address, p.unit_number, p.hoa_fees_monthly, r.first_name, r.last_name
                """
                property_details = execute_query(detail_query, (property_id,))
                
                if property_details:
                    details = property_details[0]
                    
                    st.subheader("Property Details:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Address:** {details[0]} {details[1] or ''}")
                        st.write(f"**Primary Contact:** {details[3] if details[3] else 'None'}")
                        st.write(f"**Monthly HOA Fee:** ${details[2]:,.2f}" if details[2] else "Monthly HOA Fee: Not set")
                    
                    with col2:
                        st.write(f"**Maintenance Requests:** {details[4]}")
                        st.write(f"**Financial Transactions:** {details[5]}")
                    
                    if details[4] > 0 or details[5] > 0:
                        st.error(f"⚠️ **This property has {details[4]} maintenance requests and {details[5]} financial transactions that will also be deleted!**")
                    
                    st.write("---")
                    
                    # Confirmation section
                    st.subheader("⚠️ Confirm Deletion")
                    
                    confirm_text = st.text_input(
                        f"Type 'DELETE PROPERTY {property_id}' to confirm deletion:",
                        placeholder=f"DELETE PROPERTY {property_id}"
                    )
                    
                    col1, col2, col3 = st.columns([1, 1, 2])
                    
                    with col1:
                        if st.button("🗑️ Delete Property", type="primary", 
                                   disabled=(confirm_text != f"DELETE PROPERTY {property_id}")):
                            # Delete property (CASCADE will handle related records)
                            delete_query = "DELETE FROM properties WHERE id = %s"
                            result = execute_query(delete_query, (property_id,), fetch=False)
                            
                            if result:
                                st.success(f"✅ Property '{details[0]}' has been deleted!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete the property. Please try again.")
                    
                    with col2:
                        if st.button("Cancel"):
                            st.rerun()
                    
                    with col3:
                        if confirm_text != f"DELETE PROPERTY {property_id}" and confirm_text != "":
                            st.error("⚠️ Confirmation text doesn't match. Please type exactly as shown.")
        else:
            st.info("No properties found to delete.")

def show_maintenance():
    st.header("🔧 Maintenance Requests")
    
    tab1, tab2, tab3, tab4 = st.tabs(["View Requests", "New Request", "Edit Request", "Delete Request"])
    
    with tab1:
        maintenance_data = get_maintenance_requests()
        if maintenance_data:
            df = pd.DataFrame(maintenance_data, columns=[
                'ID', 'Address', 'Unit', 'Type', 'Title', 'Status', 'Priority', 'Created', 'Est. Cost'
            ])
            
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                status_filter = st.selectbox("Filter by Status", 
                    ["All"] + list(df['Status'].unique()))
            with col2:
                type_filter = st.selectbox("Filter by Type", 
                    ["All"] + list(df['Type'].unique()))
            
            # Apply filters
            filtered_df = df.copy()
            if status_filter != "All":
                filtered_df = filtered_df[filtered_df['Status'] == status_filter]
            if type_filter != "All":
                filtered_df = filtered_df[filtered_df['Type'] == type_filter]
            
            st.dataframe(filtered_df, use_container_width=True)
            
            # Quick status updates
            st.subheader("Quick Status Update")
            col1, col2, col3 = st.columns(3)
            with col1:
                request_id = st.selectbox("Select Request ID", 
                    [row[0] for row in maintenance_data])
            with col2:
                new_status = st.selectbox("New Status", 
                    ["Open", "In Progress", "Completed", "Cancelled"])
            with col3:
                if st.button("Update Status"):
                    query = "UPDATE maintenance_requests SET status = %s WHERE id = %s"
                    result = execute_query(query, (new_status, request_id), fetch=False)
                    if result:
                        st.success("Status updated!")
                        st.rerun()
    
    with tab2:
        st.subheader("Submit New Maintenance Request")
        with st.form("maintenance_request"):
            # Get properties for dropdown
            properties_data = get_properties()
            property_options = {f"{row[1]} {row[2] or ''}".strip(): row[0] 
                             for row in properties_data} if properties_data else {}
            
            selected_property = st.selectbox("Property", list(property_options.keys()))
            request_type = st.selectbox("Request Type", 
                ["Irrigation", "Landscaping", "Common Area", "Other"])
            priority = st.selectbox("Priority", ["Low", "Medium", "High", "Emergency"])
            title = st.text_input("Title/Summary")
            description = st.text_area("Description")
            reported_by = st.text_input("Reported By")
            estimated_cost = st.number_input("Estimated Cost", min_value=0.0, step=10.0)
            
            submitted = st.form_submit_button("Submit Request")
            if submitted and selected_property and title:
                property_id = property_options[selected_property]
                query = """
                INSERT INTO maintenance_requests 
                (property_id, request_type, priority, title, description, reported_by, estimated_cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                result = execute_query(query, 
                    (property_id, request_type, priority, title, description, reported_by, estimated_cost), 
                    fetch=False)
                if result:
                    st.success("Maintenance request submitted!")
                    st.rerun()
    
    with tab3:
        st.subheader("Edit Maintenance Request")
        
        # Get maintenance requests for dropdown
        maintenance_data = get_maintenance_requests()
        if maintenance_data:
            # Create options for dropdown
            request_options = {}
            for row in maintenance_data:
                display_text = f"#{row[0]} - {row[1]} {row[2] or ''} - {row[4]}"
                request_options[display_text] = row[0]
            
            selected_request = st.selectbox("Select Request to Edit", list(request_options.keys()))
            
            if selected_request:
                request_id = request_options[selected_request]
                
                # Get full request details
                detail_query = """
                SELECT mr.id, p.id as property_id, p.address, p.unit_number, mr.request_type, 
                       mr.priority, mr.title, mr.description, mr.reported_by, mr.assigned_to,
                       mr.estimated_cost, mr.actual_cost, mr.status, mr.notes
                FROM maintenance_requests mr
                JOIN properties p ON mr.property_id = p.id
                WHERE mr.id = %s
                """
                request_details = execute_query(detail_query, (request_id,))
                
                if request_details:
                    details = request_details[0]
                    
                    with st.form("edit_maintenance_request"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            new_type = st.selectbox("Request Type", 
                                ["Irrigation", "Landscaping", "Common Area", "Other"],
                                index=["Irrigation", "Landscaping", "Common Area", "Other"].index(details[4]) if details[4] in ["Irrigation", "Landscaping", "Common Area", "Other"] else 0)
                            
                            new_priority = st.selectbox("Priority", 
                                ["Low", "Medium", "High", "Emergency"],
                                index=["Low", "Medium", "High", "Emergency"].index(details[5]) if details[5] in ["Low", "Medium", "High", "Emergency"] else 1)
                            
                            new_status = st.selectbox("Status", 
                                ["Open", "In Progress", "Completed", "Cancelled"],
                                index=["Open", "In Progress", "Completed", "Cancelled"].index(details[12]) if details[12] in ["Open", "In Progress", "Completed", "Cancelled"] else 0)
                        
                        with col2:
                            new_estimated_cost = st.number_input("Estimated Cost", 
                                value=float(details[10]) if details[10] else 0.0, step=10.0)
                            
                            new_actual_cost = st.number_input("Actual Cost", 
                                value=float(details[11]) if details[11] else 0.0, step=10.0)
                            
                            new_assigned_to = st.text_input("Assigned To", 
                                value=details[9] if details[9] else "")
                        
                        new_title = st.text_input("Title", value=details[6] if details[6] else "")
                        new_description = st.text_area("Description", value=details[7] if details[7] else "")
                        new_notes = st.text_area("Notes", value=details[13] if details[13] else "")
                        
                        submitted = st.form_submit_button("Update Request")
                        
                        if submitted:
                            update_query = """
                            UPDATE maintenance_requests 
                            SET request_type = %s, priority = %s, title = %s, description = %s,
                                assigned_to = %s, estimated_cost = %s, actual_cost = %s, 
                                status = %s, notes = %s,
                                completed_date = CASE WHEN %s = 'Completed' THEN NOW() ELSE completed_date END
                            WHERE id = %s
                            """
                            result = execute_query(update_query, 
                                (new_type, new_priority, new_title, new_description, 
                                 new_assigned_to, new_estimated_cost, new_actual_cost, 
                                 new_status, new_notes, new_status, request_id), 
                                fetch=False)
                            
                            if result:
                                st.success("Maintenance request updated successfully!")
                                st.rerun()
        else:
            st.info("No maintenance requests found. Add some requests first.")
    
    with tab4:
        st.subheader("🗑️ Delete Maintenance Request")
        st.warning("⚠️ **Warning**: Deleting a maintenance request is permanent and cannot be undone!")
        
        # Get maintenance requests for dropdown
        maintenance_data = get_maintenance_requests()
        if maintenance_data:
            # Create options for dropdown with more detail
            request_options = {}
            for row in maintenance_data:
                display_text = f"#{row[0]} - {row[1]} {row[2] or ''} - {row[4]} ({row[5]})"
                request_options[display_text] = row[0]
            
            selected_request = st.selectbox("Select Request to Delete", 
                [""] + list(request_options.keys()))
            
            if selected_request and selected_request != "":
                request_id = request_options[selected_request]
                
                # Get full request details for confirmation
                detail_query = """
                SELECT mr.id, p.address, p.unit_number, mr.request_type, 
                       mr.priority, mr.title, mr.description, mr.status, 
                       mr.created_date, mr.estimated_cost
                FROM maintenance_requests mr
                JOIN properties p ON mr.property_id = p.id
                WHERE mr.id = %s
                """
                request_details = execute_query(detail_query, (request_id,))
                
                if request_details:
                    details = request_details[0]
                    
                    # Show request details for confirmation
                    st.subheader("Request Details:")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**ID:** #{details[0]}")
                        st.write(f"**Property:** {details[1]} {details[2] or ''}")
                        st.write(f"**Type:** {details[3]}")
                        st.write(f"**Priority:** {details[4]}")
                        st.write(f"**Status:** {details[7]}")
                    
                    with col2:
                        st.write(f"**Title:** {details[5]}")
                        st.write(f"**Created:** {details[8]}")
                        if details[9]:
                            st.write(f"**Estimated Cost:** ${details[9]:,.2f}")
                    
                    if details[6]:  # Description
                        st.write(f"**Description:** {details[6]}")
                    
                    st.write("---")
                    
                    # Confirmation section
                    st.subheader("⚠️ Confirm Deletion")
                    
                    confirm_text = st.text_input(
                        f"Type 'DELETE {details[0]}' to confirm deletion:",
                        placeholder=f"DELETE {details[0]}"
                    )
                    
                    col1, col2, col3 = st.columns([1, 1, 2])
                    
                    with col1:
                        if st.button("🗑️ Delete Request", type="primary", 
                                   disabled=(confirm_text != f"DELETE {details[0]}")):
                            delete_query = "DELETE FROM maintenance_requests WHERE id = %s"
                            result = execute_query(delete_query, (request_id,), fetch=False)
                            
                            if result:
                                st.success(f"✅ Maintenance request #{details[0]} has been deleted!")
                                st.balloons()
                                # Clear the form by rerunning
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete the request. Please try again.")
                    
                    with col2:
                        if st.button("Cancel"):
                            st.rerun()
                    
                    with col3:
                        if confirm_text != f"DELETE {details[0]}" and confirm_text != "":
                            st.error("⚠️ Confirmation text doesn't match. Please type exactly as shown.")
        else:
            st.info("No maintenance requests found to delete.")

def show_financial():
    st.header("💰 Financial Management")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Transactions", "Add Transaction", "Edit Transaction", "Delete Transaction"])
    
    with tab1:
        query = """
        SELECT ft.id, p.address, p.unit_number, ft.transaction_type, 
               ft.category, ft.amount, ft.description, ft.due_date, ft.paid_date
        FROM financial_transactions ft
        JOIN properties p ON ft.property_id = p.id
        ORDER BY ft.created_date DESC
        LIMIT 50
        """
        transactions = execute_query(query)
        if transactions:
            df = pd.DataFrame(transactions, columns=[
                'ID', 'Address', 'Unit', 'Type', 'Category', 'Amount', 'Description', 'Due Date', 'Paid Date'
            ])
            st.dataframe(df, use_container_width=True)
    
    with tab2:
        st.subheader("Add Financial Transaction")
        with st.form("add_transaction"):
            properties_data = get_properties()
            property_options = {f"{row[1]} {row[2] or ''}".strip(): row[0] 
                             for row in properties_data} if properties_data else {}
            
            selected_property = st.selectbox("Property", list(property_options.keys()))
            transaction_type = st.selectbox("Transaction Type", 
                ["Assessment", "Payment", "Fee", "Fine", "Credit"])
            category = st.text_input("Category")
            amount = st.number_input("Amount", step=0.01)
            description = st.text_area("Description")
            due_date = st.date_input("Due Date") if transaction_type == "Assessment" else None
            
            submitted = st.form_submit_button("Add Transaction")
            if submitted and selected_property and amount != 0:
                property_id = property_options[selected_property]
                query = """
                INSERT INTO financial_transactions 
                (property_id, transaction_type, category, amount, description, due_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                result = execute_query(query, 
                    (property_id, transaction_type, category, amount, description, due_date), 
                    fetch=False)
                if result:
                    st.success("Transaction added!")
                    st.rerun()
    
    with tab3:
        st.subheader("Edit Financial Transaction")
        
        # Get transactions for dropdown
        transactions_query = """
        SELECT ft.id, p.address, p.unit_number, ft.transaction_type, 
               ft.category, ft.amount, ft.description, ft.due_date, ft.paid_date,
               ft.payment_method, ft.reference_number
        FROM financial_transactions ft
        JOIN properties p ON ft.property_id = p.id
        ORDER BY ft.created_date DESC
        LIMIT 50
        """
        transactions = execute_query(transactions_query)
        
        if transactions:
            transaction_options = {}
            for row in transactions:
                display_text = f"#{row[0]} - {row[1]} {row[2] or ''} - {row[3]} - ${row[5]:,.2f}"
                transaction_options[display_text] = row[0]
            
            selected_transaction = st.selectbox("Select Transaction to Edit", list(transaction_options.keys()))
            
            if selected_transaction:
                transaction_id = transaction_options[selected_transaction]
                
                # Get full transaction details
                detail_query = """
                SELECT ft.id, ft.property_id, p.address, p.unit_number, ft.transaction_type, 
                       ft.category, ft.amount, ft.description, ft.due_date, ft.paid_date,
                       ft.payment_method, ft.reference_number
                FROM financial_transactions ft
                JOIN properties p ON ft.property_id = p.id
                WHERE ft.id = %s
                """
                transaction_details = execute_query(detail_query, (transaction_id,))
                
                if transaction_details:
                    details = transaction_details[0]
                    
                    with st.form("edit_transaction"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            new_transaction_type = st.selectbox("Transaction Type", 
                                ["Assessment", "Payment", "Fee", "Fine", "Credit"],
                                index=["Assessment", "Payment", "Fee", "Fine", "Credit"].index(details[4]) if details[4] in ["Assessment", "Payment", "Fee", "Fine", "Credit"] else 0)
                            
                            new_category = st.text_input("Category", value=details[5] if details[5] else "")
                            new_amount = st.number_input("Amount", value=float(details[6]) if details[6] else 0.0, step=0.01)
                            new_payment_method = st.selectbox("Payment Method",
                                ["", "Check", "ACH", "Credit Card", "Cash", "Online"],
                                index=["", "Check", "ACH", "Credit Card", "Cash", "Online"].index(details[10]) if details[10] in ["", "Check", "ACH", "Credit Card", "Cash", "Online"] else 0)
                        
                        with col2:
                            new_due_date = st.date_input("Due Date", value=details[8] if details[8] else None)
                            new_paid_date = st.date_input("Paid Date", value=details[9] if details[9] else None)
                            new_reference_number = st.text_input("Reference Number", value=details[11] if details[11] else "")
                        
                        new_description = st.text_area("Description", value=details[7] if details[7] else "")
                        
                        submitted = st.form_submit_button("Update Transaction")
                        
                        if submitted:
                            update_query = """
                            UPDATE financial_transactions 
                            SET transaction_type = %s, category = %s, amount = %s, description = %s,
                                due_date = %s, paid_date = %s, payment_method = %s, reference_number = %s
                            WHERE id = %s
                            """
                            result = execute_query(update_query, 
                                (new_transaction_type, new_category, new_amount, new_description,
                                 new_due_date, new_paid_date, new_payment_method, new_reference_number, 
                                 transaction_id), fetch=False)
                            
                            if result:
                                st.success("Transaction updated successfully!")
                                st.rerun()
        else:
            st.info("No transactions found. Add some transactions first.")
    
    with tab4:
        st.subheader("🗑️ Delete Financial Transaction")
        st.warning("⚠️ **Warning**: Deleting a financial transaction is permanent and cannot be undone!")
        
        # Get transactions for dropdown (same as edit)
        transactions_query = """
        SELECT ft.id, p.address, p.unit_number, ft.transaction_type, 
               ft.category, ft.amount, ft.description, ft.created_date
        FROM financial_transactions ft
        JOIN properties p ON ft.property_id = p.id
        ORDER BY ft.created_date DESC
        LIMIT 50
        """
        transactions = execute_query(transactions_query)
        
        if transactions:
            transaction_options = {}
            for row in transactions:
                display_text = f"#{row[0]} - {row[1]} {row[2] or ''} - {row[3]} - ${row[5]:,.2f}"
                transaction_options[display_text] = row[0]
            
            selected_transaction = st.selectbox("Select Transaction to Delete", 
                [""] + list(transaction_options.keys()))
            
            if selected_transaction and selected_transaction != "":
                transaction_id = transaction_options[selected_transaction]
                
                # Get transaction details for confirmation
                detail_query = """
                SELECT ft.id, p.address, p.unit_number, ft.transaction_type, 
                       ft.category, ft.amount, ft.description, ft.created_date, ft.due_date, ft.paid_date
                FROM financial_transactions ft
                JOIN properties p ON ft.property_id = p.id
                WHERE ft.id = %s
                """
                transaction_details = execute_query(detail_query, (transaction_id,))
                
                if transaction_details:
                    details = transaction_details[0]
                    
                    st.subheader("Transaction Details:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**ID:** #{details[0]}")
                        st.write(f"**Property:** {details[1]} {details[2] or ''}")
                        st.write(f"**Type:** {details[3]}")
                        st.write(f"**Category:** {details[4]}")
                        st.write(f"**Amount:** ${details[5]:,.2f}")
                    
                    with col2:
                        st.write(f"**Created:** {details[7]}")
                        if details[8]:
                            st.write(f"**Due Date:** {details[8]}")
                        if details[9]:
                            st.write(f"**Paid Date:** {details[9]}")
                    
                    if details[6]:
                        st.write(f"**Description:** {details[6]}")
                    
                    st.write("---")
                    
                    # Confirmation section
                    st.subheader("⚠️ Confirm Deletion")
                    
                    confirm_text = st.text_input(
                        f"Type 'DELETE TRANSACTION {details[0]}' to confirm deletion:",
                        placeholder=f"DELETE TRANSACTION {details[0]}"
                    )
                    
                    col1, col2, col3 = st.columns([1, 1, 2])
                    
                    with col1:
                        if st.button("🗑️ Delete Transaction", type="primary", 
                                   disabled=(confirm_text != f"DELETE TRANSACTION {details[0]}")):
                            delete_query = "DELETE FROM financial_transactions WHERE id = %s"
                            result = execute_query(delete_query, (transaction_id,), fetch=False)
                            
                            if result:
                                st.success(f"✅ Transaction #{details[0]} has been deleted!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete the transaction. Please try again.")
                    
                    with col2:
                        if st.button("Cancel"):
                            st.rerun()
                    
                    with col3:
                        if confirm_text != f"DELETE TRANSACTION {details[0]}" and confirm_text != "":
                            st.error("⚠️ Confirmation text doesn't match. Please type exactly as shown.")
        else:
            st.info("No transactions found to delete.")

def show_email_center():
    st.header("📧 Email Center")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Send Emails", "Email Templates", "Add Template", "Edit Template", "Delete Template"])
    
    with tab1:
        st.subheader("Send Monthly Statements")
        
        properties_data = get_properties()
        if properties_data:
            selected_properties = st.multiselect(
                "Select Properties",
                options=[f"{row[1]} {row[2] or ''}".strip() for row in properties_data],
                default=[f"{row[1]} {row[2] or ''}".strip() for row in properties_data[:5]]
            )
            
            email_subject = st.text_input("Subject", "Monthly HOA Statement")
            email_body = st.text_area("Email Body Template", 
                "Dear Resident,\n\nPlease find your monthly HOA statement attached.\n\nBest regards,\nHOA Management")
            
            if st.button("Send Emails"):
                sent_count = 0
                for prop_display in selected_properties:
                    # Find the matching property
                    for row in properties_data:
                        if f"{row[1]} {row[2] or ''}".strip() == prop_display and row[5]:  # row[5] is email
                            if send_email(row[5], email_subject, email_body):
                                sent_count += 1
                            break
                st.success(f"Sent {sent_count} emails successfully!")
        
        st.subheader("📧 Use Email Template")
        templates_query = "SELECT id, template_name, subject_line, body_template FROM email_templates WHERE is_active = true ORDER BY template_name"
        templates = execute_query(templates_query)
        
        if templates:
            template_options = {f"{row[1]}": row[0] for row in templates}
            selected_template_name = st.selectbox("Select Template", ["Custom"] + list(template_options.keys()))
            
            if selected_template_name != "Custom":
                template_id = template_options[selected_template_name]
                # Get template details
                for template in templates:
                    if template[0] == template_id:
                        st.info(f"**Subject:** {template[2]}")
                        st.text_area("Template Body (Preview)", template[3], height=150, disabled=True)
                        
                        if st.button("Use This Template"):
                            # Auto-fill the form above with template content
                            st.session_state.email_subject = template[2]
                            st.session_state.email_body = template[3]
                            st.rerun()
                        break
    
    with tab2:
        st.subheader("📄 Email Templates")
        templates_query = "SELECT id, template_name, subject_line, body_template, template_type, is_active, created_date FROM email_templates ORDER BY template_name"
        templates = execute_query(templates_query)
        
        if templates:
            # Display templates in a nice format
            for template in templates:
                status_icon = "✅" if template[5] else "❌"
                with st.expander(f"{status_icon} {template[1]} ({template[4] if template[4] else 'General'})"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.write(f"**Subject:** {template[2]}")
                        st.write(f"**Type:** {template[4] if template[4] else 'General'}")
                        st.write(f"**Created:** {template[6]}")
                        st.write("**Body:**")
                        st.code(template[3], language="text")
                    with col2:
                        st.write(f"**Status:** {'Active' if template[5] else 'Inactive'}")
                        if st.button(f"{'Deactivate' if template[5] else 'Activate'}", key=f"toggle_{template[0]}"):
                            toggle_query = "UPDATE email_templates SET is_active = %s WHERE id = %s"
                            execute_query(toggle_query, (not template[5], template[0]), fetch=False)
                            st.rerun()
        else:
            st.info("No email templates found. Create some templates to get started!")
    
    with tab3:
        st.subheader("➕ Add Email Template")
        
        with st.form("add_template"):
            col1, col2 = st.columns(2)
            with col1:
                template_name = st.text_input("Template Name", placeholder="e.g., Monthly Statement")
                template_type = st.selectbox("Template Type", 
                    ["Monthly Statement", "Maintenance Notice", "General", "Assessment Notice", "Meeting Notice", "Violation Notice"])
                is_active = st.checkbox("Active", value=True)
            
            with col2:
                st.write("**Available Variables:**")
                st.code("""{{property_address}}
{{resident_name}}
{{current_balance}}
{{monthly_fee}}
{{due_date}}
{{request_title}}
{{status}}
{{notes}}""", language="text")
            
            subject_line = st.text_input("Subject Line", placeholder="e.g., Monthly HOA Statement - {{property_address}}")
            
            body_template = st.text_area("Email Body Template", 
                placeholder="""Dear {{resident_name}},

Please find your monthly HOA statement for {{property_address}}.

Current Balance: ${{current_balance}}
Monthly HOA Fee: ${{monthly_fee}}
Due Date: {{due_date}}

Best regards,
HOA Management Team""", height=300)
            
            submitted = st.form_submit_button("Create Template")
            
            if submitted and template_name and subject_line and body_template:
                insert_query = """
                INSERT INTO email_templates (template_name, subject_line, body_template, template_type, is_active)
                VALUES (%s, %s, %s, %s, %s)
                """
                result = execute_query(insert_query, 
                    (template_name, subject_line, body_template, template_type, is_active), fetch=False)
                
                if result:
                    st.success("✅ Email template created successfully!")
                    st.balloons()
                    st.rerun()
    
    with tab4:
        st.subheader("✏️ Edit Email Template")
        
        templates_query = "SELECT id, template_name, subject_line, body_template, template_type, is_active FROM email_templates ORDER BY template_name"
        templates = execute_query(templates_query)
        
        if templates:
            template_options = {f"{row[1]} ({'Active' if row[5] else 'Inactive'})": row[0] for row in templates}
            selected_template = st.selectbox("Select Template to Edit", list(template_options.keys()))
            
            if selected_template:
                template_id = template_options[selected_template]
                
                # Get template details
                template_details = None
                for template in templates:
                    if template[0] == template_id:
                        template_details = template
                        break
                
                if template_details:
                    with st.form("edit_template"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_template_name = st.text_input("Template Name", value=template_details[1])
                            new_template_type = st.selectbox("Template Type", 
                                ["Monthly Statement", "Maintenance Notice", "General", "Assessment Notice", "Meeting Notice", "Violation Notice"],
                                index=["Monthly Statement", "Maintenance Notice", "General", "Assessment Notice", "Meeting Notice", "Violation Notice"].index(template_details[4]) if template_details[4] in ["Monthly Statement", "Maintenance Notice", "General", "Assessment Notice", "Meeting Notice", "Violation Notice"] else 2)
                            new_is_active = st.checkbox("Active", value=template_details[5])
                        
                        with col2:
                            st.write("**Available Variables:**")
                            st.code("""{{property_address}}
{{resident_name}}
{{current_balance}}
{{monthly_fee}}
{{due_date}}
{{request_title}}
{{status}}
{{notes}}""", language="text")
                        
                        new_subject_line = st.text_input("Subject Line", value=template_details[2])
                        new_body_template = st.text_area("Email Body Template", value=template_details[3], height=300)
                        
                        submitted = st.form_submit_button("Update Template")
                        
                        if submitted and new_template_name and new_subject_line and new_body_template:
                            update_query = """
                            UPDATE email_templates 
                            SET template_name = %s, subject_line = %s, body_template = %s, 
                                template_type = %s, is_active = %s
                            WHERE id = %s
                            """
                            result = execute_query(update_query, 
                                (new_template_name, new_subject_line, new_body_template, 
                                 new_template_type, new_is_active, template_id), fetch=False)
                            
                            if result:
                                st.success("✅ Email template updated successfully!")
                                st.rerun()
        else:
            st.info("No templates found. Create some templates first!")
    
    with tab5:
        st.subheader("🗑️ Delete Email Template")
        st.warning("⚠️ **Warning**: Deleting an email template is permanent and cannot be undone!")
        
        templates_query = "SELECT id, template_name, template_type, is_active, created_date FROM email_templates ORDER BY template_name"
        templates = execute_query(templates_query)
        
        if templates:
            template_options = {}
            for template in templates:
                status = "Active" if template[3] else "Inactive"
                display_text = f"{template[1]} ({template[2] if template[2] else 'General'}) - {status}"
                template_options[display_text] = template[0]
            
            selected_template = st.selectbox("Select Template to Delete", 
                [""] + list(template_options.keys()))
            
            if selected_template and selected_template != "":
                template_id = template_options[selected_template]
                
                # Get template details
                detail_query = "SELECT id, template_name, subject_line, body_template, template_type, is_active, created_date FROM email_templates WHERE id = %s"
                template_details = execute_query(detail_query, (template_id,))
                
                if template_details:
                    details = template_details[0]
                    
                    st.subheader("Template Details:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Name:** {details[1]}")
                        st.write(f"**Type:** {details[4] if details[4] else 'General'}")
                        st.write(f"**Status:** {'Active' if details[5] else 'Inactive'}")
                        st.write(f"**Created:** {details[6]}")
                    
                    with col2:
                        st.write(f"**Subject:** {details[2]}")
                    
                    st.write("**Body Preview:**")
                    st.code(details[3][:200] + "..." if len(details[3]) > 200 else details[3], language="text")
                    
                    # Check if template is being used
                    usage_query = "SELECT COUNT(*) FROM email_log WHERE template_id = %s"
                    usage_count = execute_query(usage_query, (template_id,))
                    usage_num = usage_count[0][0] if usage_count else 0
                    
                    if usage_num > 0:
                        st.warning(f"⚠️ **This template has been used {usage_num} times in email history. Deleting it will not affect sent emails but will remove the template.**")
                    
                    st.write("---")
                    
                    # Confirmation section
                    st.subheader("⚠️ Confirm Deletion")
                    
                    confirm_text = st.text_input(
                        f"Type 'DELETE TEMPLATE {details[0]}' to confirm deletion:",
                        placeholder=f"DELETE TEMPLATE {details[0]}"
                    )
                    
                    col1, col2, col3 = st.columns([1, 1, 2])
                    
                    with col1:
                        if st.button("🗑️ Delete Template", type="primary", 
                                   disabled=(confirm_text != f"DELETE TEMPLATE {details[0]}")):
                            delete_query = "DELETE FROM email_templates WHERE id = %s"
                            result = execute_query(delete_query, (template_id,), fetch=False)
                            
                            if result:
                                st.success(f"✅ Email template '{details[1]}' has been deleted!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete the template. Please try again.")
                    
                    with col2:
                        if st.button("Cancel"):
                            st.rerun()
                    
                    with col3:
                        if confirm_text != f"DELETE TEMPLATE {details[0]}" and confirm_text != "":
                            st.error("⚠️ Confirmation text doesn't match. Please type exactly as shown.")
        else:
            st.info("No templates found to delete.")

if __name__ == "__main__":
    main()