from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from database import execute_query
from datetime import datetime, date
import os
from dotenv import load_dotenv
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')


def ensure_default_case_categories():
    """Create starter case categories if table is sparse."""
    category_count = execute_query("SELECT COUNT(*) AS count FROM CASE_CATEGORIES")
    if category_count and category_count[0]['count'] >= 6:
        return

    case_types = execute_query("SELECT case_type_id, type_name FROM CASE_TYPES ORDER BY case_type_id") or []
    if not case_types:
        return

    first_case_type_id = case_types[0]['case_type_id']
    default_categories = [
        ("Sexual Harassment", first_case_type_id, 4),
        ("Domestic Violence", first_case_type_id, 4),
        ("Property Dispute", first_case_type_id, 3),
        ("Contract Breach", first_case_type_id, 3),
        ("Cyber Crime", first_case_type_id, 4),
        ("Fraud and Cheating", first_case_type_id, 5),
    ]
    for category_name, case_type_id, severity in default_categories:
        exists = execute_query(
            "SELECT category_id FROM CASE_CATEGORIES WHERE category_name = %s AND case_type_id = %s",
            (category_name, case_type_id)
        ) or []
        if not exists:
            execute_query(
                """
                INSERT INTO CASE_CATEGORIES (category_name, case_type_id, severity_level)
                VALUES (%s, %s, %s)
                """,
                (category_name, case_type_id, severity)
            )


def calculate_relevance_score(case_id, precedent_id):
    """Auto-calculate relevance score based on case type/category similarity."""
    metadata = execute_query(
        """
        SELECT c.case_type_id, cc.category_name, p.case_type_id AS precedent_case_type,
               p.case_name, p.summary, p.headnotes
        FROM CASES c
        LEFT JOIN CASE_CATEGORIES cc ON c.case_category_id = cc.category_id
        LEFT JOIN PRECEDENTS p ON p.precedent_id = %s
        WHERE c.case_id = %s
        """,
        (precedent_id, case_id)
    ) or []
    if not metadata:
        return 5

    row = metadata[0]
    score = 5
    if row.get('precedent_case_type') and row.get('case_type_id') == row.get('precedent_case_type'):
        score += 3

    category_name = (row.get('category_name') or '').lower()
    precedent_text = " ".join([
        row.get('case_name') or '',
        row.get('summary') or '',
        row.get('headnotes') or ''
    ]).lower()
    if category_name and category_name in precedent_text:
        score += 2

    return max(1, min(score, 10))

# ============================================================================
# HOME PAGE
# ============================================================================

@app.route('/')
def index():
    """Dashboard with statistics"""
    # Get statistics
    total_cases = execute_query("SELECT COUNT(*) as count FROM CASES")[0]['count']
    active_cases = execute_query("""
        SELECT COUNT(*) as count FROM CASES c
        JOIN CASE_STATUS cs ON c.status_id = cs.status_id
        WHERE cs.is_active = TRUE
    """)[0]['count']
    total_clients = execute_query("SELECT COUNT(*) as count FROM CLIENTS")[0]['count']
    total_lawyers = execute_query("SELECT COUNT(*) as count FROM LAWYERS WHERE is_active = TRUE")[0]['count']
    
    # Recent cases
    recent_cases = execute_query("""
        SELECT c.case_id, c.case_number, c.title, c.filing_date, cs.status_name, co.court_name
        FROM CASES c
        JOIN CASE_STATUS cs ON c.status_id = cs.status_id
        JOIN COURTS co ON c.court_id = co.court_id
        ORDER BY c.filing_date DESC
        LIMIT 5
    """) or []
    
    return render_template('index.html',
                         total_cases=total_cases,
                         active_cases=active_cases,
                         total_clients=total_clients,
                         total_lawyers=total_lawyers,
                         recent_cases=recent_cases)

# ============================================================================
# CASES
# ============================================================================

@app.route('/cases')
def cases():
    """List all cases"""
    query = """
        SELECT c.case_id, c.case_number, c.title, c.filing_date, 
               cs.status_name, c.priority_level, co.court_name,
               CONCAT(j.first_name, ' ', j.last_name) as judge_name
        FROM CASES c
        JOIN CASE_STATUS cs ON c.status_id = cs.status_id
        JOIN COURTS co ON c.court_id = co.court_id
        LEFT JOIN JUDGES j ON c.judge_id = j.judge_id
        ORDER BY c.filing_date DESC
    """
    cases_list = execute_query(query)
    return render_template('cases.html', cases=cases_list)

@app.route('/case/<int:case_id>')
def case_details(case_id):
    """Show detailed information about a case"""
    # Get case details
    case_query = """
        SELECT c.*, cs.status_name, co.court_name,
               CONCAT(j.first_name, ' ', j.last_name) as judge_name
        FROM CASES c
        JOIN CASE_STATUS cs ON c.status_id = cs.status_id
        JOIN COURTS co ON c.court_id = co.court_id
        LEFT JOIN JUDGES j ON c.judge_id = j.judge_id
        WHERE c.case_id = %s
    """
    case_result = execute_query(case_query, (case_id,)) or []
    if not case_result:
        flash('Case not found.', 'error')
        return redirect(url_for('cases'))
    case = case_result[0]
    
    # Get clients
    clients_query = """
        SELECT cl.first_name, cl.last_name, cc.party_type
        FROM CASE_CLIENTS cc
        JOIN CLIENTS cl ON cc.client_id = cl.client_id
        WHERE cc.case_id = %s
    """
    clients = execute_query(clients_query, (case_id,)) or []
    
    # Get lawyers
    lawyers_query = """
        SELECT l.first_name, l.last_name, cl.role
        FROM CASE_LAWYERS cl
        JOIN LAWYERS l ON cl.lawyer_id = l.lawyer_id
        WHERE cl.case_id = %s AND cl.is_active = TRUE
    """
    lawyers = execute_query(lawyers_query, (case_id,)) or []
    
    # Get precedents cited
    precedents_query = """
        SELECT p.case_name, p.citation, cp.relevance_score, cp.application_type
        FROM CASE_PRECEDENTS cp
        JOIN PRECEDENTS p ON cp.precedent_id = p.precedent_id
        WHERE cp.case_id = %s
        ORDER BY cp.relevance_score DESC
    """
    precedents = execute_query(precedents_query, (case_id,)) or []
    
    # Get hearings
    hearings_query = """
        SELECT h.hearing_date, h.hearing_time, h.hearing_type, h.outcome,
               cr.courtroom_number
        FROM HEARINGS h
        JOIN COURTROOMS cr ON h.courtroom_id = cr.courtroom_id
        WHERE h.case_id = %s
        ORDER BY h.hearing_date DESC
    """
    hearings = execute_query(hearings_query, (case_id,)) or []

    all_clients = execute_query("""
        SELECT client_id, first_name, last_name
        FROM CLIENTS
        WHERE is_active = TRUE
        ORDER BY first_name, last_name
    """) or []
    all_lawyers = execute_query("""
        SELECT lawyer_id, first_name, last_name
        FROM LAWYERS
        WHERE is_active = TRUE
        ORDER BY first_name, last_name
    """) or []
    all_precedents = execute_query("""
        SELECT precedent_id, case_name, citation
        FROM PRECEDENTS
        ORDER BY judgment_date DESC
        LIMIT 100
    """) or []
    all_case_judges = execute_query("""
        SELECT judge_id, first_name, last_name
        FROM JUDGES
        ORDER BY first_name, last_name
    """) or []
    all_courtrooms = execute_query("""
        SELECT courtroom_id, courtroom_number, court_id
        FROM COURTROOMS
        ORDER BY courtroom_number
    """) or []
    
    return render_template('case_details.html', 
                         case=case, 
                         clients=clients, 
                         lawyers=lawyers,
                         precedents=precedents,
                         hearings=hearings,
                         all_clients=all_clients,
                         all_lawyers=all_lawyers,
                         all_precedents=all_precedents,
                         all_case_judges=all_case_judges,
                         all_courtrooms=all_courtrooms)

@app.route('/add_case', methods=['GET', 'POST'])
def add_case():
    """Add a new case"""
    if request.method == 'POST':
        # Get form data
        case_number = request.form['case_number']
        title = request.form['title']
        filing_date = request.form['filing_date']
        case_type_id = request.form['case_type_id']
        case_category_id = request.form['case_category_id']
        priority_level = request.form['priority_level']
        court_id = request.form['court_id']
        
        # Insert case
        insert_query = """
            INSERT INTO CASES (case_number, title, filing_date, case_type_id, 
                             case_category_id, status_id, priority_level, court_id)
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
        """
        case_id = execute_query(insert_query, (
            case_number, title, filing_date, 
            case_type_id, case_category_id, 
            priority_level, court_id
        ))
        
        if case_id:
            flash('Case added successfully!', 'success')
            return redirect(url_for('case_details', case_id=case_id))
        else:
            flash('Error adding case!', 'error')
    
    ensure_default_case_categories()
    case_categories = execute_query("SELECT * FROM CASE_CATEGORIES ORDER BY category_name") or []
    
    # Existing
    case_types = execute_query("SELECT * FROM CASE_TYPES") or []
    courts = execute_query("SELECT * FROM COURTS") or []
    
    # ✅ UPDATED render
    return render_template(
        'add_case.html',
        case_types=case_types,
        courts=courts,
        case_categories=case_categories
    )

# ============================================================================
# PRECEDENTS
# ============================================================================

@app.route('/precedents')
def precedents():
    """List all precedents"""
    search = request.args.get('search', '').strip()
    precedent_type = request.args.get('type', '').strip()
    sort = request.args.get('sort', 'most_cited').strip()

    query = """
        SELECT p.precedent_id, p.case_name, p.citation, p.judgment_date,
               p.is_landmark, co.court_name,
               COUNT(DISTINCT cp.case_id) as times_cited
        FROM PRECEDENTS p
        JOIN COURTS co ON p.court_id = co.court_id
        LEFT JOIN CASE_PRECEDENTS cp ON p.precedent_id = cp.precedent_id
    """
    conditions = []
    params = []

    if search:
        conditions.append("(p.citation LIKE %s OR p.case_name LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if precedent_type == 'landmark':
        conditions.append("p.is_landmark = TRUE")
    elif precedent_type == 'regular':
        conditions.append("p.is_landmark = FALSE")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY p.precedent_id "
    if sort == 'recent':
        query += " ORDER BY p.judgment_date DESC "
    elif sort == 'oldest':
        query += " ORDER BY p.judgment_date ASC "
    else:
        query += " ORDER BY times_cited DESC, p.is_landmark DESC "

    precedents_list = execute_query(query, tuple(params) if params else None) or []
    court_options = execute_query("SELECT court_id, court_name FROM COURTS ORDER BY court_name") or []
    case_type_options = execute_query("SELECT case_type_id, type_name FROM CASE_TYPES ORDER BY type_name") or []
    return render_template(
        'precedents.html',
        precedents=precedents_list,
        selected_search=search,
        selected_type=precedent_type,
        selected_sort=sort,
        court_options=court_options,
        case_type_options=case_type_options
    )


@app.route('/add_precedent', methods=['POST'])
def add_precedent():
    """Add precedent from precedents page."""
    insert_query = """
        INSERT INTO PRECEDENTS (
            case_name, citation, court_id, judgment_date, case_type_id, summary, authority_level, is_landmark
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    result = execute_query(insert_query, (
        request.form.get('case_name'),
        request.form.get('citation'),
        request.form.get('court_id'),
        request.form.get('judgment_date'),
        request.form.get('case_type_id') or None,
        request.form.get('summary'),
        request.form.get('authority_level') or 3,
        True if request.form.get('is_landmark') == 'on' else False
    ))
    flash('Precedent added successfully.' if result else 'Failed to add precedent.', 'success' if result else 'error')
    return redirect(url_for('precedents'))


@app.route('/precedent/<int:precedent_id>')
def precedent_details(precedent_id):
    """Precedent details page"""
    details = execute_query("""
        SELECT p.*, co.court_name
        FROM PRECEDENTS p
        JOIN COURTS co ON p.court_id = co.court_id
        WHERE p.precedent_id = %s
    """, (precedent_id,)) or []
    if not details:
        flash('Precedent not found.', 'error')
        return redirect(url_for('precedents'))

    linked_cases = execute_query("""
        SELECT c.case_id, c.case_number, c.title, cp.relevance_score, cp.application_type
        FROM CASE_PRECEDENTS cp
        JOIN CASES c ON cp.case_id = c.case_id
        WHERE cp.precedent_id = %s
        ORDER BY cp.relevance_score DESC
    """, (precedent_id,)) or []

    return render_template('precedent_details.html', precedent=details[0], linked_cases=linked_cases)

# ============================================================================
# CLIENTS
# ============================================================================

@app.route('/clients')
def clients():
    """List all clients"""
    query = """
        SELECT cl.client_id, cl.first_name, cl.last_name, cl.client_type,
               cl.contact_number, cl.email,
               COUNT(DISTINCT cc.case_id) as total_cases
        FROM CLIENTS cl
        LEFT JOIN CASE_CLIENTS cc ON cl.client_id = cc.client_id
        GROUP BY cl.client_id
        ORDER BY cl.registration_date DESC
    """
    clients_list = execute_query(query) or []
    return render_template('clients.html', clients=clients_list)


@app.route('/client/<int:client_id>')
def client_details(client_id):
    flash(f'Client profile view for ID {client_id} is coming soon.', 'success')
    return redirect(url_for('clients'))


@app.route('/add_client', methods=['POST'])
def add_client():
    """Add a new client"""
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    client_type = request.form.get('client_type', 'Individual')
    contact_number = request.form.get('contact_number')
    email = request.form.get('email')
    address_text = request.form.get('address', '').strip()

    # Align UI value to schema enum.
    if client_type == 'Corporate':
        client_type = 'Organization'

    address_id = None
    if address_text:
        location_insert = """
            INSERT INTO LOCATIONS (address_line1, city, state, pincode, country)
            VALUES (%s, %s, %s, %s, 'India')
        """
        address_id = execute_query(location_insert, (address_text, 'Unknown', 'Unknown', '000000'))
    else:
        fallback_location = execute_query("SELECT location_id FROM LOCATIONS ORDER BY location_id LIMIT 1") or []
        if fallback_location:
            address_id = fallback_location[0]['location_id']
        else:
            address_id = execute_query("""
                INSERT INTO LOCATIONS (address_line1, city, state, pincode, country)
                VALUES ('N/A', 'Unknown', 'Unknown', '000000', 'India')
            """)

    insert_client = """
        INSERT INTO CLIENTS (first_name, last_name, client_type, contact_number, email, address_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    client_id = execute_query(
        insert_client,
        (first_name, last_name, client_type, contact_number, email, address_id)
    )
    if client_id:
        flash('Client added successfully.', 'success')
    else:
        flash('Failed to add client.', 'error')
    return redirect(url_for('clients'))

# ============================================================================
# LAWYERS
# ============================================================================

@app.route('/lawyers')
def lawyers():
    """List all lawyers"""
    query = """
        SELECT l.lawyer_id, l.first_name, l.last_name, l.bar_council_number,
               ls.specialization_name, l.experience_years, l.success_rate,
               COUNT(DISTINCT cl.case_id) as active_cases
        FROM LAWYERS l
        LEFT JOIN LAWYER_SPECIALIZATIONS ls ON l.specialization_id = ls.specialization_id
        LEFT JOIN CASE_LAWYERS cl ON l.lawyer_id = cl.lawyer_id AND cl.is_active = TRUE
        WHERE l.is_active = TRUE
        GROUP BY l.lawyer_id
        ORDER BY active_cases DESC
    """
    lawyers_list = execute_query(query) or []
    specializations = execute_query("""
        SELECT specialization_id, specialization_name
        FROM LAWYER_SPECIALIZATIONS
        ORDER BY specialization_name
    """) or []
    return render_template('lawyers.html', lawyers=lawyers_list, specializations=specializations)


@app.route('/lawyer/<int:lawyer_id>')
def lawyer_profile(lawyer_id):
    flash(f'Lawyer profile view for ID {lawyer_id} is coming soon.', 'success')
    return redirect(url_for('lawyers'))


@app.route('/add_lawyer', methods=['POST'])
def add_lawyer():
    """Add a new lawyer"""
    enrollment_date = request.form.get('enrollment_date') or date.today().isoformat()
    specialization_id = request.form.get('specialization_id') or None
    experience_years = request.form.get('experience_years') or 0

    insert_query = """
        INSERT INTO LAWYERS (
            first_name, last_name, bar_council_number, enrollment_date,
            specialization_id, experience_years, contact_number, email
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    lawyer_id = execute_query(insert_query, (
        request.form.get('first_name'),
        request.form.get('last_name'),
        request.form.get('bar_council_number'),
        enrollment_date,
        specialization_id,
        experience_years,
        request.form.get('contact_number'),
        request.form.get('email')
    ))
    if lawyer_id:
        flash('Lawyer added successfully.', 'success')
    else:
        flash('Failed to add lawyer.', 'error')
    return redirect(url_for('lawyers'))

# ============================================================================
# HEARINGS
# ============================================================================

@app.route('/hearings')
def hearings():
    """List upcoming hearings"""
    date_range = request.args.get('range', 'week')
    hearing_type = request.args.get('type', '').strip()
    search = request.args.get('search', '').strip()

    query = """
        SELECT h.hearing_id, h.case_id, h.hearing_date, h.hearing_time, h.hearing_type,
               c.case_number, c.title, cr.courtroom_number,
               CONCAT(j.first_name, ' ', j.last_name) as judge_name
        FROM HEARINGS h
        JOIN CASES c ON h.case_id = c.case_id
        JOIN COURTROOMS cr ON h.courtroom_id = cr.courtroom_id
        JOIN JUDGES j ON h.judge_id = j.judge_id
        WHERE 1=1
    """
    params = []

    if date_range == 'today':
        query += " AND h.hearing_date = CURDATE()"
    elif date_range == 'week':
        query += " AND h.hearing_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)"
    elif date_range == 'month':
        query += " AND h.hearing_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 1 MONTH)"
    else:
        query += " AND h.hearing_date >= CURDATE()"

    if hearing_type:
        query += " AND h.hearing_type = %s"
        params.append(hearing_type)
    if search:
        query += " AND (c.case_number LIKE %s OR c.title LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY h.hearing_date, h.hearing_time"

    hearings_list = execute_query(query, tuple(params) if params else None) or []
    case_options = execute_query("""
        SELECT case_id, case_number, title
        FROM CASES
        ORDER BY filing_date DESC
    """) or []
    judge_options = execute_query("""
        SELECT judge_id, first_name, last_name
        FROM JUDGES
        ORDER BY first_name, last_name
    """) or []
    courtroom_options = execute_query("""
        SELECT courtroom_id, courtroom_number
        FROM COURTROOMS
        ORDER BY courtroom_number
    """) or []
    return render_template(
        'hearings.html',
        hearings=hearings_list,
        case_options=case_options,
        judge_options=judge_options,
        courtroom_options=courtroom_options,
        today=date.today(),
        selected_range=date_range,
        selected_type=hearing_type,
        selected_search=search
    )


@app.route('/schedule_hearing', methods=['POST'])
def schedule_hearing():
    """Schedule a hearing"""
    insert_query = """
        INSERT INTO HEARINGS (
            case_id, hearing_date, hearing_time, courtroom_id, judge_id,
            hearing_type, duration_minutes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    hearing_id = execute_query(insert_query, (
        request.form.get('case_id'),
        request.form.get('hearing_date'),
        request.form.get('hearing_time'),
        request.form.get('courtroom_id'),
        request.form.get('judge_id'),
        request.form.get('hearing_type'),
        request.form.get('duration_minutes') or None
    ))
    if hearing_id:
        execute_query("UPDATE CASES SET judge_id = %s WHERE case_id = %s", (
            request.form.get('judge_id'),
            request.form.get('case_id')
        ))
        flash('Hearing scheduled successfully.', 'success')
    else:
        flash('Failed to schedule hearing.', 'error')
    return redirect(url_for('hearings'))


@app.route('/judges', methods=['GET', 'POST'])
def judges():
    """Judges dashboard with add + assigned cases"""
    if request.method == 'POST':
        insert_judge = """
            INSERT INTO JUDGES (
                first_name, last_name, designation, court_id, appointment_date, specialization
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        judge_id = execute_query(insert_judge, (
            request.form.get('first_name'),
            request.form.get('last_name'),
            request.form.get('designation'),
            request.form.get('court_id'),
            request.form.get('appointment_date'),
            request.form.get('specialization')
        ))
        if judge_id:
            flash('Judge added successfully.', 'success')
        else:
            flash('Failed to add judge.', 'error')
        return redirect(url_for('judges'))

    judge_list = execute_query("""
        SELECT j.judge_id, j.first_name, j.last_name, j.designation, j.specialization,
               j.appointment_date, c.court_name,
               TIMESTAMPDIFF(YEAR, j.appointment_date, CURDATE()) AS experience_years,
               (
                   SELECT COUNT(DISTINCT c2.case_id)
                   FROM CASES c2
                   LEFT JOIN HEARINGS h2 ON h2.case_id = c2.case_id
                   WHERE c2.judge_id = j.judge_id OR h2.judge_id = j.judge_id
               ) AS assigned_cases
        FROM JUDGES j
        JOIN COURTS c ON j.court_id = c.court_id
        GROUP BY j.judge_id
        ORDER BY assigned_cases DESC, j.appointment_date ASC
    """) or []

    assigned_cases = execute_query("""
        SELECT DISTINCT c.case_id, c.case_number, c.title, c.priority_level,
               CONCAT(j.first_name, ' ', j.last_name) AS judge_name
        FROM CASES c
        JOIN JUDGES j ON c.judge_id = j.judge_id
        UNION
        SELECT DISTINCT c.case_id, c.case_number, c.title, c.priority_level,
               CONCAT(j.first_name, ' ', j.last_name) AS judge_name
        FROM HEARINGS h
        JOIN CASES c ON c.case_id = h.case_id
        JOIN JUDGES j ON j.judge_id = h.judge_id
    """) or []

    court_options = execute_query("""
        SELECT court_id, court_name
        FROM COURTS
        ORDER BY court_name
    """) or []

    return render_template(
        'judges.html',
        judges=judge_list,
        assigned_cases=assigned_cases,
        court_options=court_options
    )


@app.route('/judge/<int:judge_id>')
def judge_details(judge_id):
    judge_result = execute_query("""
        SELECT j.*, c.court_name,
               TIMESTAMPDIFF(YEAR, j.appointment_date, CURDATE()) AS experience_years
        FROM JUDGES j
        JOIN COURTS c ON j.court_id = c.court_id
        WHERE j.judge_id = %s
    """, (judge_id,)) or []
    if not judge_result:
        flash('Judge not found.', 'error')
        return redirect(url_for('judges'))

    assigned_cases = execute_query("""
        SELECT ac.case_id, ac.case_number, ac.title, ac.priority_level, cs.status_name
        FROM (
            SELECT DISTINCT c.case_id, c.case_number, c.title, c.priority_level, c.status_id, c.filing_date
            FROM CASES c
            WHERE c.judge_id = %s
            UNION
            SELECT DISTINCT c.case_id, c.case_number, c.title, c.priority_level, c.status_id, c.filing_date
            FROM HEARINGS h
            JOIN CASES c ON c.case_id = h.case_id
            WHERE h.judge_id = %s
        ) ac
        LEFT JOIN CASE_STATUS cs ON ac.status_id = cs.status_id
        ORDER BY ac.filing_date DESC
    """, (judge_id, judge_id)) or []

    return render_template('judge_details.html', judge=judge_result[0], assigned_cases=assigned_cases)


@app.route('/case/<int:case_id>/add-client', methods=['POST'])
def add_case_client(case_id):
    insert_query = """
        INSERT INTO CASE_CLIENTS (case_id, client_id, party_type, involvement_start_date)
        VALUES (%s, %s, %s, CURDATE())
    """
    result = execute_query(insert_query, (
        case_id,
        request.form.get('client_id'),
        request.form.get('party_type')
    ))
    flash('Client linked to case.' if result else 'Failed to link client.', 'success' if result else 'error')
    return redirect(url_for('case_details', case_id=case_id))


@app.route('/case/<int:case_id>/add-lawyer', methods=['POST'])
def add_case_lawyer(case_id):
    insert_query = """
        INSERT INTO CASE_LAWYERS (case_id, lawyer_id, role, assignment_date, is_active)
        VALUES (%s, %s, %s, CURDATE(), TRUE)
    """
    result = execute_query(insert_query, (
        case_id,
        request.form.get('lawyer_id'),
        request.form.get('role')
    ))
    flash('Lawyer added to legal team.' if result else 'Failed to add legal team member.', 'success' if result else 'error')
    return redirect(url_for('case_details', case_id=case_id))


@app.route('/case/<int:case_id>/add-precedent', methods=['POST'])
def add_case_precedent(case_id):
    precedent_id = request.form.get('precedent_id')
    manual_score = request.form.get('relevance_score')
    if manual_score and str(manual_score).strip():
        relevance_score = int(manual_score)
    else:
        relevance_score = calculate_relevance_score(case_id, precedent_id)

    insert_query = """
        INSERT INTO CASE_PRECEDENTS (
            case_id, precedent_id, relevance_score, application_type, cited_by_party
        ) VALUES (%s, %s, %s, %s, %s)
    """
    result = execute_query(insert_query, (
        case_id,
        precedent_id,
        relevance_score,
        request.form.get('application_type'),
        request.form.get('cited_by_party')
    ))
    flash('Precedent linked successfully.' if result else 'Failed to link precedent.', 'success' if result else 'error')
    return redirect(url_for('case_details', case_id=case_id))


@app.route('/case/<int:case_id>/add-hearing', methods=['POST'])
def add_case_hearing(case_id):
    insert_query = """
        INSERT INTO HEARINGS (case_id, hearing_date, hearing_time, courtroom_id, judge_id, hearing_type, duration_minutes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    result = execute_query(insert_query, (
        case_id,
        request.form.get('hearing_date'),
        request.form.get('hearing_time'),
        request.form.get('courtroom_id'),
        request.form.get('judge_id'),
        request.form.get('hearing_type'),
        request.form.get('duration_minutes') or None
    ))
    if result:
        execute_query("UPDATE CASES SET judge_id = %s WHERE case_id = %s", (
            request.form.get('judge_id'),
            case_id
        ))
    flash('Hearing added to case.' if result else 'Failed to add hearing.', 'success' if result else 'error')
    return redirect(url_for('case_details', case_id=case_id))


@app.route('/hearing/<int:hearing_id>')
def hearing_details(hearing_id):
    hearing_result = execute_query("""
        SELECT h.*, c.case_id, c.case_number, c.title, cr.courtroom_number,
               CONCAT(j.first_name, ' ', j.last_name) AS judge_name
        FROM HEARINGS h
        JOIN CASES c ON h.case_id = c.case_id
        JOIN COURTROOMS cr ON h.courtroom_id = cr.courtroom_id
        JOIN JUDGES j ON h.judge_id = j.judge_id
        WHERE h.hearing_id = %s
    """, (hearing_id,)) or []
    if not hearing_result:
        flash('Hearing not found.', 'error')
        return redirect(url_for('hearings'))
    return render_template('hearing_details.html', hearing=hearing_result[0])


@app.route('/hearing/<int:hearing_id>/reschedule', methods=['POST'])
def reschedule_hearing(hearing_id):
    result = execute_query("""
        UPDATE HEARINGS
        SET hearing_date = %s, hearing_time = %s, hearing_type = %s
        WHERE hearing_id = %s
    """, (
        request.form.get('hearing_date'),
        request.form.get('hearing_time'),
        request.form.get('hearing_type'),
        hearing_id
    ))
    flash('Hearing rescheduled successfully.' if result is not None else 'Failed to reschedule hearing.', 'success' if result is not None else 'error')
    return redirect(url_for('hearings'))

# ============================================================================
# SEARCH API
# ============================================================================

@app.route('/api/search_cases')
def search_cases():
    """API endpoint for searching cases"""
    search_term = request.args.get('q', '')
    query = """
        SELECT case_number, title 
        FROM CASES 
        WHERE case_number LIKE %s OR title LIKE %s 
        LIMIT 10
    """
    results = execute_query(query, (f'%{search_term}%', f'%{search_term}%'))
    return jsonify(results)

# ============================================================================
# RUN APP
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, port=5000)