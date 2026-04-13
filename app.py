from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from uuid import uuid4
from functools import wraps
import json
import os
import sys
import psycopg
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pawn_shop_secret_key_2026'

# PostgreSQL Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Add this to your environment: DATABASE_URL=postgresql://user:password@host:5432/dbname")
    sys.exit(1)

# Initialize database on startup
_db_initialized = False

def ensure_db_initialized():
    """Ensure database is initialized on first request"""
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            load_data()
            _db_initialized = True
            print("✓ Database ready!")
        except Exception as e:
            print(f"Error during initialization: {e}")

app.before_request(ensure_db_initialized)

def get_db():
    """Get PostgreSQL database connection"""
    try:
        conn = psycopg.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        raise

def create_default_admin():
    """Auto-create default admin account if no admin exists"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check if any admin exists
        c.execute("SELECT COUNT(*) FROM users WHERE is_admin = TRUE")
        admin_count = c.fetchone()[0]
        
        if admin_count == 0:
            print("=" * 50)
            print("No admin found - Auto-creating admin account...")
            
            # Admin credentials - can be overridden by environment variables
            admin_username = os.getenv('ADMIN_USERNAME', 'admin')
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@pawnshop.com')
            admin_password = os.getenv('ADMIN_PASSWORD', 'Admin123!')
            
            # Warn if using default password in production
            if admin_password == 'Admin123!' and os.getenv('RENDER'):
                print("⚠ WARNING: Using default admin password in production!")
                print("  Set ADMIN_PASSWORD environment variable for better security")
            
            # Hash the password
            admin_hash = generate_password_hash(admin_password)
            created_time = datetime.now().isoformat()
            admin_id = str(uuid4())[:10]
            
            # Insert admin user
            c.execute('''INSERT INTO users (id, username, email, password_hash, phone, dob, employment,
                        residence_proof, id_front, id_back, banking_letter, bank_statement,
                        is_admin, created, pawn_submissions, redeem_requests, purchases, messages)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                        (admin_id, admin_username, admin_email, admin_hash,
                         None, None, None, None, None, None, None, None,
                         True, created_time, '{}', '{}', '{}', '[]'))
            
            conn.commit()
            
            print("✓ ADMIN ACCOUNT CREATED!")
            print(f"  Username: {admin_username}")
            print(f"  Email: {admin_email}")
            print(f"  Password: {admin_password}")
            print("=" * 50)
        else:
            print(f"✓ Admin account already exists ({admin_count} found)")
        
        conn.close()
    except Exception as e:
        print(f"Error creating admin: {e}")

def init_db():
    """Initialize PostgreSQL database - create tables if they don't exist"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            phone TEXT,
            dob TEXT,
            employment TEXT,
            residence_proof TEXT,
            id_front TEXT,
            id_back TEXT,
            banking_letter TEXT,
            bank_statement TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            created TEXT,
            pawn_submissions TEXT,
            redeem_requests TEXT,
            purchases TEXT,
            messages TEXT
        )''')
        
        # Items table
        c.execute('''CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            value REAL,
            rate REAL,
            days INTEGER,
            image_url TEXT,
            for_sale BOOLEAN DEFAULT FALSE,
            status TEXT DEFAULT 'available',
            created TEXT
        )''')
        
        # Loans table
        c.execute('''CREATE TABLE IF NOT EXISTS loans (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            amount REAL,
            rate REAL,
            due_date TEXT,
            status TEXT DEFAULT 'active',
            total_due REAL,
            created TEXT
        )''')
        
        conn.commit()
        conn.close()
        
        # Create default admin account
        create_default_admin()
        
        print("✓ PostgreSQL tables created successfully!")
    except Exception as e:
        print(f"Error initializing PostgreSQL DB: {e}")
        raise

def load_data():
    """Load data from PostgreSQL into memory"""
    global users_db, items_db, loans_db
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check if tables exist first
        c.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'users'
            )
        """)
        
        if not c.fetchone()[0]:
            print("⚠ Tables don't exist yet, skipping load")
            conn.close()
            return
        
        # Clear existing data
        users_db.clear()
        items_db.clear()
        loans_db.clear()
        
        # Load users
        try:
            c.execute('''SELECT id, username, email, password_hash, phone, dob, employment, 
                        residence_proof, id_front, id_back, banking_letter, bank_statement, 
                        is_admin, created, pawn_submissions, redeem_requests, purchases, messages 
                        FROM users''')
            
            for row in c.fetchall():
                try:
                    user_dict = {
                        'id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'password_hash': row[3],
                        'phone': row[4],
                        'dob': row[5],
                        'employment': row[6],
                        'residence_proof': row[7],
                        'id_front': row[8],
                        'id_back': row[9],
                        'banking_letter': row[10],
                        'bank_statement': row[11],
                        'is_admin': row[12],
                        'created': row[13],
                        'pawn_submissions': json.loads(row[14] or '{}'),
                        'redeem_requests': json.loads(row[15] or '{}'),
                        'purchases': json.loads(row[16] or '{}'),
                        'messages': json.loads(row[17] or '[]')
                    }
                    users_db[user_dict['id']] = user_dict
                except Exception as e:
                    print(f"  Error loading user: {e}")
        except Exception as e:
            print(f"Error loading users: {e}")
        
        # Load items
        try:
            c.execute('''SELECT id, name, category, description, value, rate, days, 
                        image_url, for_sale, status, created FROM items''')
            
            for row in c.fetchall():
                try:
                    item_dict = {
                        'id': row[0],
                        'name': row[1],
                        'category': row[2],
                        'desc': row[3],
                        'value': row[4],
                        'rate': row[5],
                        'days': row[6],
                        'image_url': row[7],
                        'for_sale': row[8],
                        'status': row[9],
                        'created': row[10]
                    }
                    items_db[item_dict['id']] = item_dict
                except Exception as e:
                    print(f"  Error loading item: {e}")
        except Exception as e:
            print(f"Error loading items: {e}")
        
        # Load loans
        try:
            c.execute('''SELECT id, user_id, item_id, amount, rate, due_date, status, total_due, created FROM loans''')
            
            for row in c.fetchall():
                try:
                    loan_dict = {
                        'id': row[0],
                        'user': row[1],
                        'item': row[2],
                        'amount': row[3],
                        'rate': row[4],
                        'due': row[5],
                        'status': row[6],
                        'total_due': row[7],
                        'created': row[8]
                    }
                    loans_db[loan_dict['id']] = loan_dict
                except Exception as e:
                    print(f"  Error loading loan: {e}")
        except Exception as e:
            print(f"Error loading loans: {e}")
        
        conn.close()
        print(f"✓ Loaded {len(users_db)} users, {len(items_db)} items, {len(loans_db)} loans from PostgreSQL")
    except Exception as e:
        print(f"Error loading from PostgreSQL: {e}")

def save_data():
    """Save data from memory to PostgreSQL"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Save users
        for uid, user in users_db.items():
            user_copy = user.copy()
            user_copy['pawn_submissions'] = json.dumps(user.get('pawn_submissions', {}))
            user_copy['redeem_requests'] = json.dumps(user.get('redeem_requests', {}))
            user_copy['purchases'] = json.dumps(user.get('purchases', {}))
            user_copy['messages'] = json.dumps(user.get('messages', []))
            
            try:
                c.execute('''INSERT INTO users (id, username, email, password_hash, phone, dob, employment, 
                            residence_proof, id_front, id_back, banking_letter, bank_statement, is_admin, 
                            created, pawn_submissions, redeem_requests, purchases, messages) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET 
                    username = EXCLUDED.username,
                    email = EXCLUDED.email,
                    password_hash = EXCLUDED.password_hash,
                    phone = EXCLUDED.phone,
                    dob = EXCLUDED.dob,
                    employment = EXCLUDED.employment,
                    residence_proof = EXCLUDED.residence_proof,
                    id_front = EXCLUDED.id_front,
                    id_back = EXCLUDED.id_back,
                    banking_letter = EXCLUDED.banking_letter,
                    bank_statement = EXCLUDED.bank_statement,
                    is_admin = EXCLUDED.is_admin,
                    created = EXCLUDED.created,
                    pawn_submissions = EXCLUDED.pawn_submissions,
                    redeem_requests = EXCLUDED.redeem_requests,
                    purchases = EXCLUDED.purchases,
                    messages = EXCLUDED.messages''',
                    (user_copy['id'], user_copy['username'], user_copy['email'], 
                     user_copy['password_hash'], user_copy.get('phone'), user_copy.get('dob'),
                     user_copy.get('employment'), user_copy.get('residence_proof'),
                     user_copy.get('id_front'), user_copy.get('id_back'),
                     user_copy.get('banking_letter'), user_copy.get('bank_statement'),
                     user_copy.get('is_admin', False), user_copy.get('created'),
                     user_copy['pawn_submissions'], user_copy['redeem_requests'],
                     user_copy['purchases'], user_copy['messages']))
            except Exception as e:
                print(f"Error saving user {uid}: {e}")
        
        # Save items
        for iid, item in items_db.items():
            try:
                c.execute('''INSERT INTO items (id, name, category, description, value, rate, days, 
                            image_url, for_sale, status, created) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET 
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    value = EXCLUDED.value,
                    rate = EXCLUDED.rate,
                    days = EXCLUDED.days,
                    image_url = EXCLUDED.image_url,
                    for_sale = EXCLUDED.for_sale,
                    status = EXCLUDED.status,
                    created = EXCLUDED.created''',
                    (item['id'], item['name'], item.get('category'), item.get('desc'),
                     item.get('value'), item.get('rate'), item.get('days'),
                     item.get('image_url'), item.get('for_sale', False),
                     item.get('status', 'available'), item.get('created')))
            except Exception as e:
                print(f"Error saving item {iid}: {e}")
        
        # Save loans
        for lid, loan in loans_db.items():
            try:
                c.execute('''INSERT INTO loans (id, user_id, item_id, amount, rate, due_date, status, total_due, created) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET 
                    user_id = EXCLUDED.user_id,
                    item_id = EXCLUDED.item_id,
                    amount = EXCLUDED.amount,
                    rate = EXCLUDED.rate,
                    due_date = EXCLUDED.due_date,
                    status = EXCLUDED.status,
                    total_due = EXCLUDED.total_due,
                    created = EXCLUDED.created''',
                    (loan['id'], loan['user'], loan['item'], loan['amount'],
                     loan['rate'], loan['due'], loan['status'], loan['total_due'],
                     loan['created']))
            except Exception as e:
                print(f"Error saving loan {lid}: {e}")
        
        conn.commit()
        conn.close()
        print(f"✓ Saved {len(users_db)} users, {len(items_db)} items, {len(loans_db)} loans to PostgreSQL")
    except Exception as e:
        print(f"Error saving to PostgreSQL: {e}")
        import traceback
        traceback.print_exc()

# In-memory storage
users_db = {}
items_db = {}
loans_db = {}

def gen_id():
    return str(uuid4())[:10]

# ============ DECORATORS ============

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('home'))
        if not users_db.get(session['user_id'], {}).get('is_admin'):
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

# ============ ROUTES ============

@app.route('/robots.txt')
def robots():
    txt = '''User-agent: *
Allow: /
Allow: /browse
Allow: /privacy
Allow: /terms
Disallow: /admin
Disallow: /api
Sitemap: https://pawn-shop-xdx.onrender.com/sitemap.xml
'''
    response = make_response(txt)
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/privacy')
def privacy():
    return render_template_string(PRIVACY_TEMPLATE)

@app.route('/terms')
def terms():
    return render_template_string(TERMS_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Find user by username
        user = None
        for uid, u in users_db.items():
            if u['username'] == username:
                user = u
                break
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user.get('is_admin', False)
            
            if user.get('is_admin'):
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Invalid username or password")
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user exists
        existing_user = None
        for u in users_db.values():
            if u['username'] == username or u['email'] == email:
                existing_user = u
                break
        
        if existing_user:
            return render_template_string(REGISTER_TEMPLATE, error="Username or email already exists")
        
        # Create new user
        user_id = gen_id()
        password_hash = generate_password_hash(password)
        created_time = datetime.now().isoformat()
        
        new_user = {
            'id': user_id,
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'phone': None,
            'dob': None,
            'employment': None,
            'residence_proof': None,
            'id_front': None,
            'id_back': None,
            'banking_letter': None,
            'bank_statement': None,
            'is_admin': False,
            'created': created_time,
            'pawn_submissions': {},
            'redeem_requests': {},
            'purchases': {},
            'messages': []
        }
        
        users_db[user_id] = new_user
        save_data()
        
        session['user_id'] = user_id
        session['username'] = username
        session['is_admin'] = False
        
        return redirect(url_for('home'))
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/browse')
def browse():
    """Browse all items available for pawn or sale"""
    return render_template_string(BROWSE_TEMPLATE, items=items_db)

@app.route('/pawn', methods=['GET', 'POST'])
@login_required
def pawn_item():
    """Submit an item for pawn"""
    if request.method == 'POST':
        # Get form data
        item_name = request.form.get('item_name')
        category = request.form.get('category')
        description = request.form.get('description')
        estimated_value = float(request.form.get('estimated_value', 0))
        
        # Create new item
        item_id = gen_id()
        created_time = datetime.now().isoformat()
        
        new_item = {
            'id': item_id,
            'name': item_name,
            'category': category,
            'desc': description,
            'value': estimated_value,
            'rate': 5.0,  # Default interest rate
            'days': 30,   # Default loan period
            'image_url': None,
            'for_sale': False,
            'status': 'pending',
            'created': created_time
        }
        
        items_db[item_id] = new_item
        
        # Add to user's pawn submissions
        user = users_db[session['user_id']]
        user['pawn_submissions'][item_id] = {
            'item_id': item_id,
            'submitted_at': created_time,
            'status': 'pending'
        }
        
        save_data()
        
        return render_template_string(PAWN_SUCCESS_TEMPLATE, item=new_item)
    
    return render_template_string(PAWN_FORM_TEMPLATE)

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard showing pawns, loans, and purchases"""
    user = users_db[session['user_id']]
    
    # Get user's pawn submissions
    user_pawns = []
    for pawn_id, pawn_data in user.get('pawn_submissions', {}).items():
        if pawn_id in items_db:
            item = items_db[pawn_id]
            user_pawns.append({
                'item': item,
                'submitted_at': pawn_data.get('submitted_at'),
                'status': pawn_data.get('status', 'pending')
            })
    
    # Get user's active loans
    user_loans = []
    for loan_id, loan in loans_db.items():
        if loan['user'] == session['user_id']:
            if loan_id in items_db:
                item = items_db[loan['item']]
                user_loans.append({
                    'loan': loan,
                    'item': item
                })
    
    return render_template_string(DASHBOARD_TEMPLATE, 
                                user=user, 
                                pawns=user_pawns, 
                                loans=user_loans)

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    return render_template_string(ADMIN_TEMPLATE, 
                                users=users_db, 
                                items=items_db, 
                                loans=loans_db)

@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin user management"""
    return render_template_string(ADMIN_USERS_TEMPLATE, users=users_db)

@app.route('/admin/items')
@admin_required
def admin_items():
    """Admin item management"""
    return render_template_string(ADMIN_ITEMS_TEMPLATE, items=items_db)

@app.route('/admin/loans')
@admin_required
def admin_loans():
    """Admin loan management"""
    return render_template_string(ADMIN_LOANS_TEMPLATE, loans=loans_db)

@app.route('/api/users')
@admin_required
def api_users():
    user_list = []
    for uid, user in users_db.items():
        user_list.append({
            'id': uid,
            'username': user['username'],
            'email': user['email'],
            'is_admin': user.get('is_admin', False),
            'created': user.get('created')
        })
    return jsonify(user_list)

# ============ TEMPLATES ============

HOME_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>O.P.S Online Pawn Shop - Instant Cash for Your Valuables</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
        }

        /* Header Styles */
        .header {
            background: rgba(0, 0, 0, 0.95);
            backdrop-filter: blur(10px);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: 0 2px 20px rgba(0,0,0,0.3);
        }

        .logo {
            font-size: 1.8rem;
            font-weight: bold;
        }

        .logo span {
            color: #ffc107;
        }

        .logo .sub {
            font-size: 0.8rem;
            color: #888;
            display: block;
        }

        .nav {
            display: flex;
            gap: 1.5rem;
            align-items: center;
        }

        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            transition: color 0.3s;
            font-weight: 500;
        }

        .nav a:hover {
            color: #ffc107;
        }

        /* Hero Section */
        .hero {
            background: linear-gradient(135deg, #1a1a2e 0%, #0a0a12 100%);
            text-align: center;
            padding: 4rem 2rem;
            position: relative;
            overflow: hidden;
        }

        .hero::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="none" stroke="%23ffc107" stroke-width="0.5" opacity="0.1"/></svg>') repeat;
            opacity: 0.1;
        }

        .hero h1 {
            font-size: 3rem;
            margin-bottom: 1rem;
            animation: fadeInUp 0.8s ease;
        }

        .hero h1 span {
            color: #ffc107;
        }

        .hero p {
            font-size: 1.2rem;
            color: #aaa;
            max-width: 600px;
            margin: 0 auto;
            animation: fadeInUp 0.8s ease 0.2s both;
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* Features */
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 2rem;
            padding: 4rem 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }

        .feature-card {
            background: rgba(26, 26, 46, 0.9);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 15px;
            text-align: center;
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 193, 7, 0.2);
        }

        .feature-card:hover {
            transform: translateY(-5px);
            border-color: #ffc107;
            box-shadow: 0 10px 30px rgba(255, 193, 7, 0.1);
        }

        .feature-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }

        .feature-card h3 {
            color: #ffc107;
            margin-bottom: 1rem;
            font-size: 1.3rem;
        }

        /* CTA Button */
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%);
            color: #0a0a12;
            text-decoration: none;
            border-radius: 50px;
            font-weight: bold;
            margin-top: 2rem;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(255, 193, 7, 0.3);
        }

        .btn-secondary {
            background: transparent;
            border: 2px solid #ffc107;
            color: #ffc107;
        }

        .btn-secondary:hover {
            background: #ffc107;
            color: #0a0a12;
        }

        /* Footer */
        .footer {
            text-align: center;
            padding: 2rem;
            background: #0a0a12;
            border-top: 1px solid #1a1a2e;
            margin-top: 2rem;
        }

        .footer a {
            color: #ffc107;
            text-decoration: none;
        }

        @media (max-width: 768px) {
            .hero h1 {
                font-size: 2rem;
            }
            .nav {
                gap: 1rem;
            }
            .header {
                flex-direction: column;
                gap: 1rem;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">
            O.P.S <span>Pawn Shop</span>
            <div class="sub">Online Pawn System</div>
        </div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/browse">Browse Items</a>
            <a href="/pawn">Pawn Item</a>
            {% if 'user_id' in session %}
                <a href="/dashboard">Dashboard</a>
                {% if session.is_admin %}
                    <a href="/admin">Admin Panel</a>
                {% endif %}
                <a href="/logout">Logout ({{ session.username }})</a>
            {% else %}
                <a href="/login">Login</a>
                <a href="/register">Register</a>
            {% endif %}
        </div>
    </div>

    <div class="hero">
        <h1>Welcome to <span>O.P.S</span> Online Pawn Shop</h1>
        <p>Get instant cash for your valuables with secure, transparent transactions. Best rates guaranteed!</p>
        {% if not 'user_id' in session %}
            <a href="/register" class="btn">Get Started →</a>
        {% else %}
            <a href="/pawn" class="btn">Pawn Your Item →</a>
        {% endif %}
    </div>

    <div class="features">
        <div class="feature-card">
            <div class="feature-icon">💰</div>
            <h3>Instant Cash</h3>
            <p>Get money in minutes after evaluation of your items. Same-day processing guaranteed.</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🔒</div>
            <h3>Secure Process</h3>
            <p>Your items are stored in secure vaults with full insurance coverage.</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">📱</div>
            <h3>Easy Tracking</h3>
            <p>Track your pawns, loans, and redemptions from your personal dashboard.</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🏦</div>
            <h3>Best Rates</h3>
            <p>Competitive interest rates with flexible repayment options.</p>
        </div>
    </div>

    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop | <a href="/privacy">Privacy Policy</a> | <a href="/terms">Terms of Service</a></p>
    </div>
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-container {
            background: rgba(26, 26, 46, 0.95);
            padding: 40px;
            border-radius: 15px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        h1 {
            color: #ffc107;
            text-align: center;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #aaa;
        }
        input {
            width: 100%;
            padding: 12px;
            background: #0a0a12;
            border: 1px solid #2a2a3e;
            color: #fff;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #ffc107;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%);
            color: #0a0a12;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            font-size: 16px;
            margin-top: 20px;
            transition: transform 0.3s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .error {
            background: rgba(220, 53, 69, 0.2);
            border: 1px solid #dc3545;
            color: #dc3545;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .links {
            text-align: center;
            margin-top: 20px;
        }
        .links a {
            color: #ffc107;
            text-decoration: none;
            margin: 0 10px;
        }
        .links a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Login to O.P.S</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Login</button>
        </form>
        <div class="links">
            <a href="/register">Create Account</a>
            <a href="/">Back to Home</a>
        </div>
    </div>
</body>
</html>
'''

REGISTER_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .register-container {
            background: rgba(26, 26, 46, 0.95);
            padding: 40px;
            border-radius: 15px;
            width: 100%;
            max-width: 450px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        h1 {
            color: #ffc107;
            text-align: center;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #aaa;
        }
        input {
            width: 100%;
            padding: 12px;
            background: #0a0a12;
            border: 1px solid #2a2a3e;
            color: #fff;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #ffc107;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%);
            color: #0a0a12;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            font-size: 16px;
            margin-top: 20px;
            transition: transform 0.3s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .error {
            background: rgba(220, 53, 69, 0.2);
            border: 1px solid #dc3545;
            color: #dc3545;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .links {
            text-align: center;
            margin-top: 20px;
        }
        .links a {
            color: #ffc107;
            text-decoration: none;
            margin: 0 10px;
        }
        .links a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="register-container">
        <h1>Create Account</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Register</button>
        </form>
        <div class="links">
            <a href="/login">Already have an account? Login</a>
            <a href="/">Back to Home</a>
        </div>
    </div>
</body>
</html>
'''

BROWSE_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browse Items - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .logo {
            font-size: 1.5rem;
            font-weight: bold;
        }
        .logo span { color: #ffc107; }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .nav a:hover { color: #ffc107; }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
        }
        .items-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 2rem;
        }
        .item-card {
            background: rgba(26, 26, 46, 0.9);
            border-radius: 10px;
            padding: 1.5rem;
            border: 1px solid rgba(255, 193, 7, 0.2);
            transition: transform 0.3s;
        }
        .item-card:hover {
            transform: translateY(-5px);
            border-color: #ffc107;
        }
        .item-name {
            font-size: 1.3rem;
            color: #ffc107;
            margin-bottom: 0.5rem;
        }
        .item-category {
            color: #aaa;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }
        .item-value {
            font-size: 1.5rem;
            font-weight: bold;
            margin: 1rem 0;
        }
        .item-status {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 5px;
            font-size: 0.8rem;
        }
        .status-available { background: #28a745; }
        .status-pending { background: #ffc107; color: #0a0a12; }
        .no-items {
            text-align: center;
            padding: 3rem;
            color: #aaa;
        }
        .footer {
            text-align: center;
            padding: 2rem;
            background: #0a0a12;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S <span>Pawn Shop</span></div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/browse">Browse</a>
            <a href="/pawn">Pawn</a>
            {% if 'user_id' in session %}
                <a href="/dashboard">Dashboard</a>
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login">Login</a>
                <a href="/register">Register</a>
            {% endif %}
        </div>
    </div>
    
    <div class="container">
        <h1>Available Items</h1>
        <div class="items-grid">
            {% for id, item in items.items() %}
                <div class="item-card">
                    <div class="item-name">{{ item.name }}</div>
                    <div class="item-category">{{ item.category or 'Uncategorized' }}</div>
                    <div class="item-value">₱{{ "%.2f"|format(item.value) }}</div>
                    <div class="item-desc">{{ item.desc[:100] }}{% if item.desc|length > 100 %}...{% endif %}</div>
                    <span class="item-status status-{{ item.status }}">{{ item.status }}</span>
                </div>
            {% else %}
                <div class="no-items">No items available at the moment.</div>
            {% endfor %}
        </div>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop</p>
    </div>
</body>
</html>
'''

PAWN_FORM_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pawn Item - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .logo {
            font-size: 1.5rem;
            font-weight: bold;
        }
        .logo span { color: #ffc107; }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .nav a:hover { color: #ffc107; }
        .container {
            max-width: 600px;
            margin: 3rem auto;
            padding: 2rem;
            background: rgba(26, 26, 46, 0.95);
            border-radius: 15px;
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
            text-align: center;
        }
        .form-group {
            margin-bottom: 1.5rem;
        }
        label {
            display: block;
            margin-bottom: 0.5rem;
            color: #aaa;
        }
        input, select, textarea {
            width: 100%;
            padding: 10px;
            background: #0a0a12;
            border: 1px solid #2a2a3e;
            color: #fff;
            border-radius: 5px;
        }
        textarea {
            resize: vertical;
            min-height: 100px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%);
            color: #0a0a12;
            border: none;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .footer {
            text-align: center;
            padding: 2rem;
            background: #0a0a12;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S <span>Pawn Shop</span></div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/browse">Browse</a>
            <a href="/pawn">Pawn</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <h1>Pawn Your Item</h1>
        <form method="POST">
            <div class="form-group">
                <label>Item Name</label>
                <input type="text" name="item_name" required>
            </div>
            <div class="form-group">
                <label>Category</label>
                <select name="category">
                    <option value="Electronics">Electronics</option>
                    <option value="Jewelry">Jewelry</option>
                    <option value="Collectibles">Collectibles</option>
                    <option value="Musical Instruments">Musical Instruments</option>
                    <option value="Tools">Tools</option>
                    <option value="Other">Other</option>
                </select>
            </div>
            <div class="form-group">
                <label>Description</label>
                <textarea name="description" placeholder="Describe your item in detail..." required></textarea>
            </div>
            <div class="form-group">
                <label>Estimated Value (₱)</label>
                <input type="number" name="estimated_value" step="0.01" required>
            </div>
            <button type="submit">Submit for Evaluation</button>
        </form>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop</p>
    </div>
</body>
</html>
'''

PAWN_SUCCESS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Submission Successful - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .success-container {
            background: rgba(26, 26, 46, 0.95);
            padding: 40px;
            border-radius: 15px;
            text-align: center;
            max-width: 500px;
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        .checkmark {
            font-size: 4rem;
            color: #28a745;
            margin-bottom: 1rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 1rem;
        }
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%);
            color: #0a0a12;
            text-decoration: none;
            border-radius: 5px;
            margin-top: 1rem;
        }
    </style>
</head>
<body>
    <div class="success-container">
        <div class="checkmark">✓</div>
        <h1>Item Submitted Successfully!</h1>
        <p>Your item "{{ item.name }}" has been submitted for evaluation.</p>
        <p>Our team will review your item and contact you within 24 hours.</p>
        <a href="/dashboard" class="btn">Go to Dashboard</a>
        <br><br>
        <a href="/" style="color: #ffc107;">Back to Home</a>
    </div>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Dashboard - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%);
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .logo {
            font-size: 1.5rem;
            font-weight: bold;
        }
        .logo span { color: #ffc107; }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .nav a:hover { color: #ffc107; }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
        }
        .welcome {
            background: rgba(255, 193, 7, 0.1);
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        .section {
            background: rgba(26, 26, 46, 0.9);
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        .section h2 {
            color: #ffc107;
            margin-bottom: 1rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #2a2a3e;
        }
        th {
            color: #ffc107;
        }
        .status-badge {
            padding: 3px 8px;
            border-radius: 5px;
            font-size: 0.8rem;
        }
        .status-pending { background: #ffc107; color: #0a0a12; }
        .status-approved { background: #28a745; }
        .status-rejected { background: #dc3545; }
        .status-active { background: #17a2b8; }
        .no-data {
            text-align: center;
            padding: 2rem;
            color: #aaa;
        }
        .footer {
            text-align: center;
            padding: 2rem;
            background: #0a0a12;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S <span>Pawn Shop</span></div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/browse">Browse</a>
            <a href="/pawn">Pawn</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <h1>My Dashboard</h1>
        
        <div class="welcome">
            <p>Welcome back, <strong>{{ user.username }}</strong>!</p>
            <p>Email: {{ user.email }} | Member since: {{ user.created[:10] if user.created else 'N/A' }}</p>
        </div>
        
        <div class="section">
            <h2>My Pawn Submissions</h2>
            {% if pawns %}
                <table>
                    <thead>
                        <tr><th>Item Name</th><th>Submitted</th><th>Status</th></tr>
                    </thead>
                    <tbody>
                        {% for pawn in pawns %}
                        <tr>
                            <td>{{ pawn.item.name }}</td>
                            <td>{{ pawn.submitted_at[:10] if pawn.submitted_at else 'N/A' }}</td>
                            <td><span class="status-badge status-{{ pawn.status }}">{{ pawn.status }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <div class="no-data">No pawn submissions yet. <a href="/pawn">Pawn an item</a></div>
            {% endif %}
        </div>
        
        <div class="section">
            <h2>My Active Loans</h2>
            {% if loans %}
                <table>
                    <thead>
                        <tr><th>Item</th><th>Amount</th><th>Due Date</th><th>Status</th></tr>
                    </thead>
                    <tbody>
                        {% for loan_data in loans %}
                        <tr>
                            <td>{{ loan_data.item.name }}</td>
                            <td>₱{{ "%.2f"|format(loan_data.loan.amount) }}</td>
                            <td>{{ loan_data.loan.due[:10] if loan_data.loan.due else 'N/A' }}</td>
                            <td><span class="status-badge status-{{ loan_data.loan.status }}">{{ loan_data.loan.status }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <div class="no-data">No active loans.</div>
            {% endif %}
        </div>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop</p>
    </div>
</body>
</html>
'''

ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - O.P.S Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a12;
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .logo {
            font-size: 1.5rem;
            font-weight: bold;
        }
        .logo span { color: #ffc107; }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .nav a:hover { color: #ffc107; }
        .container {
            max-width: 1400px;
            margin: 2rem auto;
            padding: 0 2rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: rgba(26, 26, 46, 0.95);
            padding: 1.5rem;
            border-radius: 10px;
            text-align: center;
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        .stat-number {
            font-size: 2rem;
            color: #ffc107;
            font-weight: bold;
        }
        .admin-sections {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-top: 2rem;
        }
        .admin-card {
            background: rgba(26, 26, 46, 0.95);
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid rgba(255, 193, 7, 0.2);
        }
        .admin-card h3 {
            color: #ffc107;
            margin-bottom: 1rem;
        }
        .admin-card a {
            color: #ffc107;
            text-decoration: none;
        }
        .footer {
            text-align: center;
            padding: 2rem;
            background: #0a0a12;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S <span>Admin Panel</span></div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/admin">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <h1>Admin Dashboard</h1>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{{ users|length }}</div>
                <div>Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ items|length }}</div>
                <div>Total Items</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ loans|length }}</div>
                <div>Active Loans</div>
            </div>
        </div>
        
        <div class="admin-sections">
            <div class="admin-card">
                <h3>📊 User Management</h3>
                <p>Manage registered users and their details.</p>
                <br>
                <a href="/admin/users">View All Users →</a>
            </div>
            <div class="admin-card">
                <h3>📦 Item Management</h3>
                <p>Review and manage pawned items.</p>
                <br>
                <a href="/admin/items">Manage Items →</a>
            </div>
            <div class="admin-card">
                <h3>💰 Loan Management</h3>
                <p>Track and manage active loans.</p>
                <br>
                <a href="/admin/loans">View Loans →</a>
            </div>
        </div>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop - Admin Panel</p>
    </div>
</body>
</html>
'''

ADMIN_USERS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>User Management - Admin</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a12;
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(26, 26, 46, 0.95);
            border-radius: 10px;
            overflow: hidden;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #2a2a3e;
        }
        th {
            background: #ffc107;
            color: #0a0a12;
        }
        .admin-badge {
            background: #ffc107;
            color: #0a0a12;
            padding: 3px 8px;
            border-radius: 5px;
            font-size: 0.8rem;
        }
        .back-link {
            display: inline-block;
            margin-bottom: 1rem;
            color: #ffc107;
            text-decoration: none;
        }
        .footer {
            text-align: center;
            padding: 2rem;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S Admin</div>
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/">Home</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <a href="/admin" class="back-link">← Back to Dashboard</a>
        <h1>User Management</h1>
        
        <table>
            <thead>
                <tr><th>Username</th><th>Email</th><th>Role</th><th>Registered</th></tr>
            </thead>
            <tbody>
                {% for uid, user in users.items() %}
                <tr>
                    <td>{{ user.username }}</td>
                    <td>{{ user.email }}</td>
                    <td>{% if user.is_admin %}<span class="admin-badge">Admin</span>{% else %}User{% endif %}</td>
                    <td>{{ user.created[:10] if user.created else 'N/A' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop</p>
    </div>
</body>
</html>
'''

ADMIN_ITEMS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Item Management - Admin</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a12;
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(26, 26, 46, 0.95);
            border-radius: 10px;
            overflow: hidden;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #2a2a3e;
        }
        th {
            background: #ffc107;
            color: #0a0a12;
        }
        .status-pending { color: #ffc107; }
        .status-approved { color: #28a745; }
        .back-link {
            display: inline-block;
            margin-bottom: 1rem;
            color: #ffc107;
            text-decoration: none;
        }
        .footer {
            text-align: center;
            padding: 2rem;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S Admin</div>
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/">Home</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <a href="/admin" class="back-link">← Back to Dashboard</a>
        <h1>Item Management</h1>
        
        <table>
            <thead>
                <tr><th>Name</th><th>Category</th><th>Value</th><th>Status</th><th>Created</th></tr>
            </thead>
            <tbody>
                {% for iid, item in items.items() %}
                <tr>
                    <td>{{ item.name }}</td>
                    <td>{{ item.category or 'N/A' }}</td>
                    <td>₱{{ "%.2f"|format(item.value) }}</td>
                    <td class="status-{{ item.status }}">{{ item.status }}</td>
                    <td>{{ item.created[:10] if item.created else 'N/A' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop</p>
    </div>
</body>
</html>
'''

ADMIN_LOANS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loan Management - Admin</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a12;
            color: #e0e0e0;
        }
        .header {
            background: rgba(0,0,0,0.95);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #ffc107;
        }
        .nav a {
            color: #e0e0e0;
            text-decoration: none;
            margin-left: 1.5rem;
        }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
        }
        h1 {
            color: #ffc107;
            margin-bottom: 2rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(26, 26, 46, 0.95);
            border-radius: 10px;
            overflow: hidden;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #2a2a3e;
        }
        th {
            background: #ffc107;
            color: #0a0a12;
        }
        .status-active { color: #28a745; }
        .status-completed { color: #17a2b8; }
        .status-defaulted { color: #dc3545; }
        .back-link {
            display: inline-block;
            margin-bottom: 1rem;
            color: #ffc107;
            text-decoration: none;
        }
        .footer {
            text-align: center;
            padding: 2rem;
            margin-top: 2rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S Admin</div>
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/">Home</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <a href="/admin" class="back-link">← Back to Dashboard</a>
        <h1>Loan Management</h1>
        
        <table>
            <thead>
                <tr><th>Loan ID</th><th>Amount</th><th>Due Date</th><th>Total Due</th><th>Status</th></tr>
            </thead>
            <tbody>
                {% for lid, loan in loans.items() %}
                <tr>
                    <td>{{ loan.id }}</td>
                    <td>₱{{ "%.2f"|format(loan.amount) }}</td>
                    <td>{{ loan.due[:10] if loan.due else 'N/A' }}</td>
                    <td>₱{{ "%.2f"|format(loan.total_due) }}</td>
                    <td class="status-{{ loan.status }}">{{ loan.status }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop</p>
    </div>
</body>
</html>
'''

PRIVACY_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - O.P.S Online Pawn Shop</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #0a0a12; color: #e0e0e0; line-height: 1.6; }
        h1 { color: #ffc107; text-align: center; }
        h2 { color: #ffc107; margin-top: 30px; }
        a { color: #ffc107; text-decoration: none; }
        .footer { text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #333; font-size: 12px; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Last Updated:</strong> April 2026</p>
    <h2>1. Information Collection</h2>
    <p>We collect personal information including name, email, phone number, and identification documents for pawn transactions.</p>
    <h2>2. Data Usage</h2>
    <p>Your data is used only for processing pawn transactions, loan management, and legal compliance.</p>
    <h2>3. Data Security</h2>
    <p>All sensitive data is encrypted and stored securely. We do not share your information with third parties.</p>
    <div class="footer"><a href="/">Home</a> | <a href="/terms">Terms</a></div>
</body>
</html>
'''

TERMS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service - O.P.S Online Pawn Shop</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #0a0a12; color: #e0e0e0; line-height: 1.6; }
        h1 { color: #ffc107; text-align: center; }
        h2 { color: #ffc107; margin-top: 30px; }
        a { color: #ffc107; text-decoration: none; }
        .footer { text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #333; font-size: 12px; }
    </style>
</head>
<body>
    <h1>Terms of Service</h1>
    <p><strong>Last Updated:</strong> April 2026</p>
    <h2>1. Acceptance</h2>
    <p>By using O.P.S Online Pawn Shop, you agree to these terms.</p>
    <h2>2. Pawn Terms</h2>
    <p>Items pawned must be legally owned by you. Interest rates apply as shown at time of pawn.</p>
    <h2>3. Default</h2>
    <p>Unredeemed items after the loan period become property of O.P.S Pawn Shop.</p>
    <div class="footer"><a href="/">Home</a> | <a href="/privacy">Privacy</a></div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
