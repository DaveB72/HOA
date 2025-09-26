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
    try:
        conn = psycopg2.connect(
            host=st.secrets.get("DB_HOST", "localhost"),
            database=st.secrets.get("DB_NAME", "hoa_db"),
            user=st.secrets.get("DB_USER", "postgres"),
            password=st.secrets.get("DB_PASSWORD", "password"),
            port=st.secrets.get("DB_PORT", 5432)
        )
        cur = conn.cursor()
        cur.execute(query, params)
        
        if fetch:
            result = cur.fetchall()
            conn.commit()
            return result
        else:
            conn.commit()
            return cur.rowcount
            
    except Exception as e:
        st.error(f"Database error: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def get_properties():
    # Simple query first
    query = """
    SELECT p.id, p.address, p.unit_number, p.hoa_fees_monthly,
           r.first_name || ' ' || r.last_name as primary_contact,
           r.email
    FROM properties p
    LEFT JOIN residents r ON p.id = r.property_id AND r.is_primary_contact = true
    ORDER BY p.address, p.unit_number
    """
    result = execute_query(query)
    
    # Add None for side column to match expected format
    if result:
        return [list(row) + [None] for row in result]  # Add side as None
    return []

def get_maintenance_requests():
    # Simple query first
    query = """
    SELECT mr.id, p.address, p.unit_number, mr.request_type, mr.title, 
           mr.status, mr.priority, mr.created_date, mr.estimated_cost
    FROM maintenance_requests mr
    JOIN properties p ON mr.property_id = p.id
    ORDER BY mr.created_date DESC
    """
    result = execute_query(query)
    
    # Add None for expected_completion column to match expected format
    if result:
        return [list(row) + [None] for row in result]  # Add expected_completion as None
    return []

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

# Email template parsing function
def parse_email_template(template_text, property_row=None, maintenance_data=None, financial_data=None):
    """Replace template variables with actual data"""
    if not template_text:
        return template_text
    
    parsed = template_text
    
    # Property variables
    if property_row:
        property_address = f"{property_row[1]} {property_row[2] or ''}".strip()
        resident_name = property_row[4] or "Resident"
        monthly_fee = property_row[3] or 0
        
        parsed = parsed.replace("{{property_address}}", property_address)
        parsed = parsed.replace("{{resident_name}}", resident_name)
        parsed = parsed.replace("{{monthly_fee}}", f"{monthly_fee}")
    
    # Financial variables
    if financial_data:
        current_balance = financial_data.get('balance', 0)
        due_date = financial_data.get('due_date', 'TBD')
        parsed = parsed.replace("{{current_balance}}", f"{current_balance}")
        parsed = parsed.replace("{{due_date}}", str(due_date))
    
    # Maintenance variables
    if maintenance_data:
        request_title = maintenance_data.get('title', '')
        status = maintenance_data.get('status', '')
        notes = maintenance_data.get('notes', '')
        parsed = parsed.replace("{{request_title}}", request_title)
        parsed = parsed.replace("{{status}}", status)
        parsed = parsed.replace("{{notes}}", notes)
    
    # Default replacements for missing data
    parsed = parsed.replace("{{current_balance}}", "0.00")
    parsed = parsed.replace("{{due_date}}", "End of Month")
    parsed = parsed.replace("{{request_title}}", "")
    parsed = parsed.replace("{{status}}", "")
    parsed = parsed.replace("{{notes}}", "")
    
    return parsed

# Email functions
def send_email(to_email, subject, body, smtp_server="smtp.gmail.com", smtp_port=587):
    try:
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
    st.set_page_config(page_title="Brookfield West I HOA Management", layout="wide")
    
    st.title("🏘️ Brookfield West I HOA Management System")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", [
        "Dashboard", 
        "Properties", 
        "Maintenance Requests", 
        "Financial Management", 
        "Email Center",
        "Reports"
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
    elif page == "Reports":
        show_reports()

def show_dashboard():
    st.header("📊 Brookfield West I HOA Dashboard")
    
    properties_data = get_properties()
    maintenance_data = get_maintenance_requests()
    financial_data = get_financial_summary()
    
    # Top row metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if properties_data:
            st.metric("Total Properties", len(properties_data))
        else:
            st.metric("Total Properties", 0)
    
    with col2:
        if maintenance_data:
            open_requests = len([r for r in maintenance_data if r[5] == 'Open'])
            st.metric("Open Maintenance", open_requests)
        else:
            st.metric("Open Maintenance", 0)
    
    with col3:
        if financial_data and financial_data[0]:
            net_balance = financial_data[0][3] or 0
            st.metric("Net Balance", f"${net_balance:,.2f}")
        else:
            st.metric("Net Balance", "$0.00")
    
    with col4:
        if maintenance_data:
            overdue_count = 0
            today = date.today()
            for request in maintenance_data:
                if request[5] == 'Open' and request[9] and request[9] < today:
                    overdue_count += 1
            st.metric("Overdue Items", overdue_count)
        else:
            st.metric("Overdue Items", 0)
    
    # Recent maintenance requests
    st.subheader("Recent Maintenance Requests")
    if maintenance_data:
        df = pd.DataFrame(maintenance_data[:5], columns=[
            'ID', 'Address', 'Unit', 'Type', 'Title', 'Status', 'Priority', 'Created', 'Est. Cost', 'Expected'
        ])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No maintenance requests found")

def show_properties():
    st.header("🏠 Property Management")
    
    tab1, tab2, tab3, tab4 = st.tabs(["View Properties", "Add Property", "Edit Property", "Delete Property"])
    
    with tab1:
        properties_data = get_properties()
        if properties_data:
            df = pd.DataFrame(properties_data, columns=[
                'ID', 'Address', 'Unit', 'Side', 'Monthly Fee', 'Primary Contact', 'Email'
            ])
            st.dataframe(df, use_container_width=True)
    
    with tab2:
        st.subheader("Add New Property")
        with st.form("add_property"):
            col1, col2 = st.columns(2)
            with col1:
                address = st.text_input("Address")
                unit_number = st.text_input("Unit Number (if applicable)")
                side = st.selectbox("Side", ["", "West", "East"])
                hoa_fee = st.number_input("Monthly HOA Fee", min_value=0.0, step=10.0)
            
            with col2:
                st.subheader("Primary Contact")
                first_name = st.text_input("First Name")
                last_name = st.text_input("Last Name")
                email = st.text_input("Email")
                phone = st.text_input("Phone")
            
            submitted = st.form_submit_button("Add Property")
            if submitted and address and first_name and last_name:
                # Check if side column exists and use appropriate query
                try:
                    property_query = """
                    INSERT INTO properties (address, unit_number, hoa_fees_monthly) 
                    VALUES (%s, %s, %s) RETURNING id
                    """
                    result = execute_query(property_query, (address, unit_number, hoa_fee), fetch=True)
                except:
                    property_query = """
                    INSERT INTO properties (address, unit_number, hoa_fees_monthly) 
                    VALUES (%s, %s, %s) RETURNING id
                    """
                    result = execute_query(property_query, (address, unit_number, hoa_fee), fetch=True)
                
                if result:
                    property_id = result[0][0]
                    resident_query = """
                    INSERT INTO residents (property_id, first_name, last_name, email, phone, is_primary_contact)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    execute_query(resident_query, (property_id, first_name, last_name, email, phone, True), fetch=False)
                    st.success("Property added successfully!")
                    st.rerun()
    
    with tab3:
        st.subheader("Edit Property")
        properties_data = get_properties()
        if properties_data:
            property_options = {f"{row[1]} {row[2] or ''}".strip(): row[0] for row in properties_data}
            selected_property = st.selectbox("Select Property to Edit", list(property_options.keys()))
            
            if selected_property:
                property_id = property_options[selected_property]
                
                property_query = """
                SELECT p.id, p.address, p.unit_number, p.side, p.property_type, p.square_footage, 
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
                            new_side = st.selectbox("Side", ["", "West", "East"], 
                                index=["", "West", "East"].index(details[3]) if details[3] in ["", "West", "East"] else 0)
                            new_hoa_fee = st.number_input("Monthly HOA Fee", 
                                value=float(details[7]) if details[7] else 0.0, step=10.0)
                        
                        with col2:
                            new_first_name = st.text_input("First Name", value=details[9] if details[9] else "")
                            new_last_name = st.text_input("Last Name", value=details[10] if details[10] else "")
                            new_email = st.text_input("Email", value=details[11] if details[11] else "")
                            new_phone = st.text_input("Phone", value=details[12] if details[12] else "")
                        
                        submitted = st.form_submit_button("Update Property")
                        
                        if submitted and new_address and new_first_name and new_last_name:
                            update_property_query = """
                            UPDATE properties 
                            SET address = %s, unit_number = %s, side = %s, hoa_fees_monthly = %s,
                                updated_date = NOW()
                            WHERE id = %s
                            """
                            result1 = execute_query(update_property_query, 
                                (new_address, new_unit, new_side, new_hoa_fee, property_id), fetch=False)
                            
                            if details[8]:  # Resident exists
                                update_resident_query = """
                                UPDATE residents 
                                SET first_name = %s, last_name = %s, email = %s, phone = %s
                                WHERE id = %s
                                """
                                execute_query(update_resident_query,
                                    (new_first_name, new_last_name, new_email, new_phone, details[8]), fetch=False)
                            
                            if result1:
                                st.success("Property updated successfully!")
                                st.rerun()
        else:
            st.info("No properties found. Add some properties first.")
    
    with tab4:
        st.subheader("🗑️ Delete Property")
        st.warning("⚠️ **Warning**: Deleting a property will also delete all associated data!")
        
        properties_data = get_properties()
        if properties_data:
            property_options = {f"{row[1]} {row[2] or ''}".strip(): row[0] for row in properties_data}
            selected_property = st.selectbox("Select Property to Delete", [""] + list(property_options.keys()))
            
            if selected_property and selected_property != "":
                property_id = property_options[selected_property]
                confirm_text = st.text_input(f"Type 'DELETE PROPERTY {property_id}' to confirm deletion:")
                
                if st.button("🗑️ Delete Property", type="primary", 
                           disabled=(confirm_text != f"DELETE PROPERTY {property_id}")):
                    delete_query = "DELETE FROM properties WHERE id = %s"
                    result = execute_query(delete_query, (property_id,), fetch=False)
                    
                    if result:
                        st.success("✅ Property has been deleted!")
                        st.rerun()

def show_maintenance():
    st.header("🔧 Maintenance Requests")
    
    tab1, tab2, tab3, tab4 = st.tabs(["View Requests", "New Request", "Edit Request", "Delete Request"])
    
    with tab1:
        maintenance_data = get_maintenance_requests()
        if maintenance_data:
            df = pd.DataFrame(maintenance_data, columns=[
                'ID', 'Address', 'Unit', 'Type', 'Title', 'Status', 'Priority', 'Created', 'Est. Cost', 'Expected'
            ])
            st.dataframe(df, use_container_width=True)
    
    with tab2:
        st.subheader("Submit New Maintenance Request")
        with st.form("maintenance_request"):
            properties_data = get_properties()
            property_options = {f"{row[1]} {row[2] or ''}".strip(): row[0] 
                             for row in properties_data} if properties_data else {}
            
            col1, col2 = st.columns(2)
            with col1:
                selected_property = st.selectbox("Property", list(property_options.keys()))
                request_type = st.selectbox("Request Type", ["Irrigation", "Landscaping", "Common Area", "Other"])
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Emergency"])
                title = st.text_input("Title/Summary")
            
            with col2:
                description = st.text_area("Description")
                reported_by = st.text_input("Reported By")
                estimated_cost = st.number_input("Estimated Cost", min_value=0.0, step=10.0)
                expected_completion = st.date_input("Expected Completion Date")
            
            submitted = st.form_submit_button("Submit Request")
            if submitted and selected_property and title:
                property_id = property_options[selected_property]
                query = """
                INSERT INTO maintenance_requests 
                (property_id, request_type, priority, title, description, reported_by, estimated_cost, expected_completion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                result = execute_query(query, 
                    (property_id, request_type, priority, title, description, reported_by, estimated_cost, expected_completion), 
                    fetch=False)
                if result:
                    st.success("Maintenance request submitted!")
                    st.rerun()
    
    with tab3:
        st.subheader("Edit Maintenance Request")
        maintenance_data = get_maintenance_requests()
        if maintenance_data:
            request_options = {f"#{row[0]} - {row[1]} {row[2] or ''} - {row[4]}": row[0] for row in maintenance_data}
            selected_request = st.selectbox("Select Request to Edit", list(request_options.keys()))
            
            if selected_request:
                request_id = request_options[selected_request]
                
                detail_query = """
                SELECT mr.id, p.id as property_id, p.address, p.unit_number, mr.request_type, 
                       mr.priority, mr.title, mr.description, mr.reported_by, mr.assigned_to,
                       mr.estimated_cost, mr.actual_cost, mr.status, mr.notes, mr.expected_completion
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
                            new_status = st.selectbox("Status", ["Open", "In Progress", "Completed", "Cancelled"],
                                index=["Open", "In Progress", "Completed", "Cancelled"].index(details[12]) if details[12] in ["Open", "In Progress", "Completed", "Cancelled"] else 0)
                            new_priority = st.selectbox("Priority", ["Low", "Medium", "High", "Emergency"],
                                index=["Low", "Medium", "High", "Emergency"].index(details[5]) if details[5] in ["Low", "Medium", "High", "Emergency"] else 1)
                            new_estimated_cost = st.number_input("Estimated Cost", 
                                value=float(details[10]) if details[10] else 0.0, step=10.0)
                        
                        with col2:
                            new_actual_cost = st.number_input("Actual Cost", 
                                value=float(details[11]) if details[11] else 0.0, step=10.0)
                            new_assigned_to = st.text_input("Assigned To", value=details[9] if details[9] else "")
                            new_expected_completion = st.date_input("Expected Completion", 
                                value=details[14] if details[14] else None)
                        
                        new_title = st.text_input("Title", value=details[6] if details[6] else "")
                        new_description = st.text_area("Description", value=details[7] if details[7] else "")
                        new_notes = st.text_area("Notes", value=details[13] if details[13] else "")
                        
                        submitted = st.form_submit_button("Update Request")
                        
                        if submitted:
                            update_query = """
                            UPDATE maintenance_requests 
                            SET priority = %s, title = %s, description = %s, assigned_to = %s, 
                                estimated_cost = %s, actual_cost = %s, status = %s, notes = %s, 
                                expected_completion = %s
                            WHERE id = %s
                            """
                            result = execute_query(update_query, 
                                (new_priority, new_title, new_description, new_assigned_to, 
                                 new_estimated_cost, new_actual_cost, new_status, new_notes, 
                                 new_expected_completion, request_id), fetch=False)
                            
                            if result:
                                st.success("Maintenance request updated successfully!")
                                st.rerun()
        else:
            st.info("No maintenance requests found.")
    
    with tab4:
        st.subheader("🗑️ Delete Maintenance Request")
        st.warning("⚠️ **Warning**: Deleting a maintenance request is permanent!")
        
        maintenance_data = get_maintenance_requests()
        if maintenance_data:
            request_options = {f"#{row[0]} - {row[1]} {row[2] or ''} - {row[4]}": row[0] for row in maintenance_data}
            selected_request = st.selectbox("Select Request to Delete", [""] + list(request_options.keys()))
            
            if selected_request and selected_request != "":
                request_id = request_options[selected_request]
                confirm_text = st.text_input(f"Type 'DELETE {request_id}' to confirm deletion:")
                
                if st.button("🗑️ Delete Request", type="primary", 
                           disabled=(confirm_text != f"DELETE {request_id}")):
                    delete_query = "DELETE FROM maintenance_requests WHERE id = %s"
                    result = execute_query(delete_query, (request_id,), fetch=False)
                    
                    if result:
                        st.success("✅ Maintenance request has been deleted!")
                        st.rerun()

def show_financial():
    st.header("💰 Financial Management")
    
    tab1, tab2 = st.tabs(["View Transactions", "Add Transaction"])
    
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
            transaction_type = st.selectbox("Transaction Type", ["Assessment", "Payment", "Fee", "Fine", "Credit"])
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
                    (property_id, transaction_type, category, amount, description, due_date), fetch=False)
                if result:
                    st.success("Transaction added!")
                    st.rerun()

def show_email_center():
    st.header("📧 Email Center")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Send Emails", "Email Templates", "Add Template", "Edit Template", "Delete Template"])
    
    with tab1:
        st.subheader("Send Monthly Statements")
        
        properties_data = get_properties()
        if properties_data:
            property_options = [f"{row[1]} {row[2] or ''}".strip() for row in properties_data]
            
            selected_properties = st.multiselect("Select Properties", options=property_options)
            email_subject = st.text_input("Subject", 
                value=st.session_state.get('email_subject', 'Monthly HOA Statement'))
            email_body = st.text_area("Email Body", 
                value=st.session_state.get('email_body', 
                    'Dear Resident,\n\nPlease find your monthly HOA statement.\n\nBest regards,\nHOA Management'))
            
            if st.button("Send Emails"):
                if not selected_properties:
                    st.warning("Please select at least one property to send emails to.")
                else:
                    sent_count = 0
                    failed_count = 0
                    
                    # Show progress
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, prop_display in enumerate(selected_properties):
                        status_text.text(f"Sending to {prop_display}...")
                        
                        # Find the matching property
                        for row in properties_data:
                            property_display = f"{row[1]} {row[2] or ''}".strip()
                            
                            if property_display == prop_display:
                                # Email address is in position 5 (not 6)
                                email_address = row[5] if len(row) > 5 and row[5] else None
                                
                                if email_address and email_address.strip():
                                    # Parse email templates with property data
                                    parsed_subject = parse_email_template(email_subject, property_row=row)
                                    parsed_body = parse_email_template(email_body, property_row=row)
                                    
                                    if send_email(email_address, parsed_subject, parsed_body):
                                        sent_count += 1
                                    else:
                                        failed_count += 1
                                else:
                                    st.warning(f"⚠️ No email address for {prop_display}")
                                    failed_count += 1
                                break
                        
                        # Update progress
                        progress_bar.progress((i + 1) / len(selected_properties))
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    # Summary
                    if sent_count > 0:
                        st.success(f"✅ Successfully sent {sent_count} emails!")
                    if failed_count > 0:
                        st.error(f"❌ Failed to send {failed_count} emails.")
                    
                    if sent_count == 0 and failed_count == 0:
                        st.info("No emails were processed.")
        
        st.subheader("📧 Use Email Template")
        templates_query = "SELECT id, template_name, subject_line, body_template FROM email_templates WHERE is_active = true ORDER BY template_name"
        templates = execute_query(templates_query)
        
        if templates:
            template_options = {f"{row[1]}": row[0] for row in templates}
            selected_template_name = st.selectbox("Select Template", ["Custom"] + list(template_options.keys()))
            
            if selected_template_name != "Custom":
                template_id = template_options[selected_template_name]
                for template in templates:
                    if template[0] == template_id:
                        st.info(f"**Subject:** {template[2]}")
                        st.text_area("Template Body (Preview)", template[3], height=150, disabled=True)
                        
                        if st.button("Use This Template"):
                            st.session_state.email_subject = template[2]
                            st.session_state.email_body = template[3]
                            st.rerun()
                        break
    
    with tab2:
        st.subheader("📄 Email Templates")
        templates_query = "SELECT id, template_name, subject_line, body_template, template_type, is_active, created_date FROM email_templates ORDER BY template_name"
        templates = execute_query(templates_query)
        
        if templates:
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
                    
                    st.write("---")
                    
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

def show_reports():
    st.header("📊 Brookfield West I HOA Reports")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Maintenance Reports", "Financial Reports", "Property Reports", "Executive Summary"])
    
    with tab1:
        st.subheader("🔧 Maintenance Analysis")
        
        # Get maintenance data with side information
        maintenance_query = """
        SELECT mr.id, p.address, p.unit_number, mr.request_type, mr.title, 
               mr.status, mr.priority, mr.created_date, mr.completed_date,
               mr.estimated_cost, mr.actual_cost
        FROM maintenance_requests mr
        JOIN properties p ON mr.property_id = p.id
        ORDER BY mr.created_date DESC
        """
        maintenance_data = execute_query(maintenance_query)
        
        if maintenance_data:
            df = pd.DataFrame(maintenance_data, columns=[
                'ID', 'Address', 'Unit', 'Type', 'Title', 'Status', 'Priority', 
                'Created', 'Completed', 'Est_Cost', 'Actual_Cost'
            ])
            
            # Convert dates and costs
            df['Created'] = pd.to_datetime(df['Created'])
            df['Est_Cost'] = pd.to_numeric(df['Est_Cost'], errors='coerce').fillna(0)
            df['Actual_Cost'] = pd.to_numeric(df['Actual_Cost'], errors='coerce').fillna(0)
            
            # Date range filter
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", value=df['Created'].min().date())
            with col2:
                end_date = st.date_input("End Date", value=df['Created'].max().date())
            
            # Filter data
            mask = (df['Created'].dt.date >= start_date) & (df['Created'].dt.date <= end_date)
            filtered_df = df.loc[mask]
            
            # Charts Row 1
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Maintenance Costs Over Time")
                if len(filtered_df) > 0:
                    monthly_costs = filtered_df.groupby(filtered_df['Created'].dt.to_period('M')).agg({
                        'Est_Cost': 'sum',
                        'Actual_Cost': 'sum'
                    }).reset_index()
                    monthly_costs['Month'] = monthly_costs['Created'].astype(str)
                    
                    fig = px.line(monthly_costs, x='Month', y=['Est_Cost', 'Actual_Cost'], 
                                title="Estimated vs Actual Costs by Month")
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Requests by Type & Status")
                type_status = filtered_df.groupby(['Type', 'Status']).size().unstack(fill_value=0)
                fig = px.bar(type_status, title="Maintenance Requests by Type and Status")
                st.plotly_chart(fig, use_container_width=True)
            
            # Charts Row 2
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Priority Distribution")
                priority_counts = filtered_df['Priority'].value_counts()
                fig = px.pie(values=priority_counts.values, names=priority_counts.index, 
                           title="Requests by Priority Level")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Request Types")
                type_counts = filtered_df['Type'].value_counts()
                fig = px.bar(x=type_counts.index, y=type_counts.values, 
                           title="Maintenance Request Types")
                st.plotly_chart(fig, use_container_width=True)
            
            # Summary metrics
            st.subheader("📈 Summary Metrics")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_requests = len(filtered_df)
                st.metric("Total Requests", total_requests)
            
            with col2:
                avg_cost = filtered_df['Actual_Cost'].mean() if filtered_df['Actual_Cost'].sum() > 0 else filtered_df['Est_Cost'].mean()
                st.metric("Avg Cost per Request", f"${avg_cost:.2f}")
            
            with col3:
                completed_requests = len(filtered_df[filtered_df['Status'] == 'Completed'])
                completion_rate = (completed_requests / total_requests * 100) if total_requests > 0 else 0
                st.metric("Completion Rate", f"{completion_rate:.1f}%")
            
            with col4:
                high_priority = len(filtered_df[filtered_df['Priority'] == 'High'])
                st.metric("High Priority Items", high_priority)
        
        else:
            st.info("No maintenance data available for reporting.")
    
    with tab2:
        st.subheader("💰 Financial Analysis")
        
        # Get financial data
        financial_query = """
        SELECT ft.id, p.address, p.unit_number, ft.transaction_type, 
               ft.category, ft.amount, ft.created_date, ft.due_date, ft.paid_date,
               ft.description
        FROM financial_transactions ft
        JOIN properties p ON ft.property_id = p.id
        ORDER BY ft.created_date DESC
        """
        financial_data = execute_query(financial_query)
        
        if financial_data:
            df = pd.DataFrame(financial_data, columns=[
                'ID', 'Address', 'Unit', 'Type', 'Category', 'Amount', 
                'Created', 'Due_Date', 'Paid_Date', 'Description'
            ])
            
            # Convert dates and amounts
            df['Created'] = pd.to_datetime(df['Created'])
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
            
            # Date range filter
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", value=df['Created'].min().date(), key="fin_start")
            with col2:
                end_date = st.date_input("End Date", value=df['Created'].max().date(), key="fin_end")
            
            # Filter data
            mask = (df['Created'].dt.date >= start_date) & (df['Created'].dt.date <= end_date)
            filtered_df = df.loc[mask]
            
            # Charts Row 1
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Cash Flow Over Time")
                monthly_flow = filtered_df.groupby([filtered_df['Created'].dt.to_period('M'), 'Type']).agg({
                    'Amount': 'sum'
                }).unstack(fill_value=0)
                monthly_flow.index = monthly_flow.index.astype(str)
                
                fig = px.bar(monthly_flow, title="Monthly Cash Flow by Transaction Type")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Revenue by Category")
                revenue_data = filtered_df[filtered_df['Amount'] > 0]
                if len(revenue_data) > 0:
                    category_revenue = revenue_data.groupby('Category')['Amount'].sum().sort_values(ascending=False)
                    fig = px.pie(values=category_revenue.values, names=category_revenue.index, 
                               title="Revenue Breakdown by Category")
                    st.plotly_chart(fig, use_container_width=True)
            
            # Charts Row 2
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Outstanding Balances")
                outstanding = filtered_df[(filtered_df['Amount'] > 0) & (filtered_df['Paid_Date'].isna())]
                if len(outstanding) > 0:
                    outstanding_by_category = outstanding.groupby('Category')['Amount'].sum()
                    fig = px.bar(x=outstanding_by_category.index, y=outstanding_by_category.values, 
                               title="Outstanding Amounts by Category")
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Payment Trends")
                payments = filtered_df[filtered_df['Amount'] < 0]  # Negative amounts are payments
                if len(payments) > 0:
                    payment_trends = payments.groupby(payments['Created'].dt.to_period('M'))['Amount'].sum().abs()
                    payment_trends.index = payment_trends.index.astype(str)
                    fig = px.line(x=payment_trends.index, y=payment_trends.values, 
                                title="Monthly Payment Collections")
                    st.plotly_chart(fig, use_container_width=True)
            
            # Summary metrics
            st.subheader("📈 Financial Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_revenue = filtered_df[filtered_df['Amount'] > 0]['Amount'].sum()
                st.metric("Total Assessments", f"${total_revenue:,.2f}")
            
            with col2:
                total_payments = abs(filtered_df[filtered_df['Amount'] < 0]['Amount'].sum())
                st.metric("Total Payments", f"${total_payments:,.2f}")
            
            with col3:
                net_balance = total_revenue - total_payments
                st.metric("Net Balance", f"${net_balance:,.2f}")
            
            with col4:
                outstanding_count = len(filtered_df[(filtered_df['Amount'] > 0) & (filtered_df['Paid_Date'].isna())])
                st.metric("Outstanding Items", outstanding_count)
        
        else:
            st.info("No financial data available for reporting.")
    
    with tab3:
        st.subheader("🏠 Property Analysis")
        
        # Get property data with counts
        property_analysis_query = """
        SELECT p.id, p.address, p.unit_number, p.hoa_fees_monthly,
               COUNT(DISTINCT mr.id) as maintenance_count,
               COUNT(DISTINCT ft.id) as transaction_count,
               COALESCE(SUM(CASE WHEN ft.amount > 0 AND ft.paid_date IS NULL THEN ft.amount END), 0) as outstanding_balance
        FROM properties p
        LEFT JOIN maintenance_requests mr ON p.id = mr.property_id
        LEFT JOIN financial_transactions ft ON p.id = ft.property_id
        GROUP BY p.id, p.address, p.unit_number, p.hoa_fees_monthly
        ORDER BY p.address
        """
        property_data = execute_query(property_analysis_query)
        
        if property_data:
            df = pd.DataFrame(property_data, columns=[
                'ID', 'Address', 'Unit', 'HOA_Fee', 'Maintenance_Count', 
                'Transaction_Count', 'Outstanding_Balance'
            ])
            
            # Convert numeric columns
            df['HOA_Fee'] = pd.to_numeric(df['HOA_Fee'], errors='coerce').fillna(0)
            df['Outstanding_Balance'] = pd.to_numeric(df['Outstanding_Balance'], errors='coerce').fillna(0)
            
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("HOA Fee Distribution")
                fee_counts = df['HOA_Fee'].value_counts()
                fig = px.pie(values=fee_counts.values, names=[f"${x}" for x in fee_counts.index], 
                           title="Properties by Monthly Fee")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Maintenance Activity by Property")
                top_maintenance = df.nlargest(10, 'Maintenance_Count')[['Address', 'Maintenance_Count']]
                if len(top_maintenance) > 0:
                    fig = px.bar(top_maintenance, x='Address', y='Maintenance_Count', 
                               title="Top 10 Properties by Maintenance Requests")
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
            
            # Property details table
            st.subheader("📋 Property Details")
            st.dataframe(df, use_container_width=True)
            
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Properties", len(df))
            
            with col2:
                monthly_revenue = df['HOA_Fee'].sum()
                st.metric("Monthly Revenue", f"${monthly_revenue:,.2f}")
            
            with col3:
                avg_maintenance = df['Maintenance_Count'].mean()
                st.metric("Avg Maintenance/Property", f"{avg_maintenance:.1f}")
            
            with col4:
                total_outstanding = df['Outstanding_Balance'].sum()
                st.metric("Total Outstanding", f"${total_outstanding:,.2f}")
        
        else:
            st.info("No property data available for reporting.")
    
    with tab4:
        st.subheader("📈 Executive Summary")
        st.write("**Brookfield West I HOA - Management Dashboard**")
        
        # Get all summary data
        properties_data = get_properties()
        maintenance_data = get_maintenance_requests()
        financial_data = get_financial_summary()
        
        # Executive metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🏠 Property Overview")
            if properties_data:
                total_properties = len(properties_data)
                monthly_revenue = sum([float(p[3]) if p[3] else 0 for p in properties_data])
                
                st.write(f"**Total Properties:** {total_properties}")
                st.write(f"**Monthly Revenue:** ${monthly_revenue:,.2f}")
                st.write(f"**Annual Revenue:** ${monthly_revenue * 12:,.2f}")
        
        with col2:
            st.subheader("🔧 Maintenance Status")
            if maintenance_data:
                total_requests = len(maintenance_data)
                open_requests = len([r for r in maintenance_data if r[5] == 'Open'])
                completed_requests = len([r for r in maintenance_data if r[5] == 'Completed'])
                
                st.write(f"**Total Requests:** {total_requests}")
                st.write(f"**Open:** {open_requests}")
                st.write(f"**Completed:** {completed_requests}")
                completion_rate = (completed_requests / total_requests * 100) if total_requests > 0 else 0
                st.write(f"**Completion Rate:** {completion_rate:.1f}%")
        
        with col3:
            st.subheader("💰 Financial Health")
            if financial_data and financial_data[0]:
                net_balance = financial_data[0][3] or 0
                st.write(f"**Net Balance:** ${net_balance:,.2f}")
                
                # Get outstanding by category
                outstanding_query = """
                SELECT category, SUM(amount) as total
                FROM financial_transactions 
                WHERE amount > 0 AND paid_date IS NULL
                GROUP BY category
                ORDER BY total DESC
                LIMIT 3
                """
                outstanding_data = execute_query(outstanding_query)
                
                if outstanding_data:
                    st.write("**Top Outstanding:**")
                    for row in outstanding_data:
                        st.write(f"• {row[0]}: ${row[1]:,.2f}")
        
        # Recent activity summary
        st.subheader("📅 Recent Activity (Last 30 Days)")
        
        # Get recent maintenance
        recent_maintenance_query = """
        SELECT COUNT(*) as count
        FROM maintenance_requests 
        WHERE created_date >= NOW() - INTERVAL '30 days'
        """
        recent_maintenance = execute_query(recent_maintenance_query)
        
        # Get recent transactions  
        recent_financial_query = """
        SELECT COUNT(*) as count, SUM(amount) as total
        FROM financial_transactions 
        WHERE created_date >= NOW() - INTERVAL '30 days'
        """
        recent_financial = execute_query(recent_financial_query)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if recent_maintenance and recent_maintenance[0]:
                st.metric("New Maintenance Requests", recent_maintenance[0][0])
        
        with col2:
            if recent_financial and recent_financial[0]:
                st.metric("New Transactions", recent_financial[0][0] or 0)
        
        with col3:
            if recent_financial and recent_financial[0] and recent_financial[0][1]:
                st.metric("Transaction Volume", f"${recent_financial[0][1]:,.2f}")
        
        # Action items
        st.subheader("⚠️ Action Items")
        
        action_items = []
        
        # Check for outstanding balances
        if financial_data and financial_data[0] and financial_data[0][3] and financial_data[0][3] > 1000:
            action_items.append(f"🟡 High outstanding balance: ${financial_data[0][3]:,.2f}")
        
        if action_items:
            for item in action_items:
                st.write(item)
        else:
            st.success("✅ No critical action items at this time")

if __name__ == "__main__":
    main()
