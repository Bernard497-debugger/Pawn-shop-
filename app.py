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

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template_string(ADMIN_TEMPLATE, users=users_db, items=items_db, loans=loans_db)

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
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>O.P.S Online Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%); color: #e0e0e0; min-height: 100vh; }
        .header { background: rgba(0,0,0,0.8); backdrop-filter: blur(10px); padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #ffc107; position: sticky; top: 0; z-index: 100; }
        .logo { font-size: 1.8rem; font-weight: bold; color: #ffc107; }
        .logo span { color: #fff; }
        .nav a { color: #e0e0e0; text-decoration: none; margin-left: 1.5rem; transition: color 0.3s; }
        .nav a:hover { color: #ffc107; }
        .hero { text-align: center; padding: 4rem 2rem; background: linear-gradient(135deg, #1a1a2e 0%, #0a0a12 100%); }
        .hero h1 { font-size: 3rem; margin-bottom: 1rem; }
        .hero h1 span { color: #ffc107; }
        .hero p { font-size: 1.2rem; color: #aaa; max-width: 600px; margin: 0 auto; }
        .btn { display: inline-block; padding: 12px 30px; background: #ffc107; color: #0a0a12; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 2rem; transition: transform 0.3s, background 0.3s; }
        .btn:hover { background: #ffd454; transform: translateY(-2px); }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 2rem; padding: 4rem 2rem; max-width: 1200px; margin: 0 auto; }
        .feature-card { background: #1a1a2e; padding: 2rem; border-radius: 10px; text-align: center; transition: transform 0.3s; border: 1px solid #2a2a3e; }
        .feature-card:hover { transform: translateY(-5px); border-color: #ffc107; }
        .feature-card h3 { color: #ffc107; margin-bottom: 1rem; }
        .footer { text-align: center; padding: 2rem; background: #0a0a12; border-top: 1px solid #2a2a3e; margin-top: 2rem; }
        .user-info { display: flex; align-items: center; gap: 1rem; }
        .user-info a { color: #ffc107; text-decoration: none; }
        @media (max-width: 768px) { .hero h1 { font-size: 2rem; } .nav a { margin-left: 1rem; } }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">O.P.S <span>Pawn Shop</span></div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/browse">Browse Items</a>
            <a href="/pawn">Pawn Item</a>
            {% if 'user_id' in session %}
                <a href="/dashboard">Dashboard</a>
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
        <a href="/register" class="btn">Get Started →</a>
    </div>
    
    <div class="features">
        <div class="feature-card">
            <h3>💰 Instant Cash</h3>
            <p>Get money in minutes after evaluation of your items</p>
        </div>
        <div class="feature-card">
            <h3>🔒 Secure Process</h3>
            <p>Your items are stored in secure vaults with insurance</p>
        </div>
        <div class="feature-card">
            <h3>📱 Easy Tracking</h3>
            <p>Track your pawns and redemptions from your dashboard</p>
        </div>
    </div>
    
    <div class="footer">
        <p>&copy; 2026 O.P.S Online Pawn Shop | <a href="/privacy">Privacy</a> | <a href="/terms">Terms</a></p>
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
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%); color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #1a1a2e; padding: 40px; border-radius: 10px; width: 350px; box-shadow: 0 0 20px rgba(0,0,0,0.5); border: 1px solid #2a2a3e; }
        h1 { color: #ffc107; text-align: center; margin-bottom: 30px; }
        input { width: 100%; padding: 12px; margin: 10px 0; background: #0a0a12; border: 1px solid #2a2a3e; color: #fff; border-radius: 5px; }
        button { width: 100%; padding: 12px; background: #ffc107; color: #0a0a12; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; margin-top: 20px; }
        button:hover { background: #ffd454; }
        .error { background: #dc3545; color: #fff; padding: 10px; border-radius: 5px; margin-bottom: 20px; text-align: center; }
        a { color: #ffc107; text-decoration: none; display: block; text-align: center; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Login</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        <a href="/register">Don't have an account? Register</a>
        <a href="/">← Back to Home</a>
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
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%); color: #e0e0e0; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
        .register-box { background: #1a1a2e; padding: 40px; border-radius: 10px; width: 400px; box-shadow: 0 0 20px rgba(0,0,0,0.5); border: 1px solid #2a2a3e; }
        h1 { color: #ffc107; text-align: center; margin-bottom: 30px; }
        input { width: 100%; padding: 12px; margin: 10px 0; background: #0a0a12; border: 1px solid #2a2a3e; color: #fff; border-radius: 5px; }
        button { width: 100%; padding: 12px; background: #ffc107; color: #0a0a12; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; margin-top: 20px; }
        button:hover { background: #ffd454; }
        .error { background: #dc3545; color: #fff; padding: 10px; border-radius: 5px; margin-bottom: 20px; text-align: center; }
        a { color: #ffc107; text-decoration: none; display: block; text-align: center; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="register-box">
        <h1>Register</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="email" name="email" placeholder="Email" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Register</button>
        </form>
        <a href="/login">Already have an account? Login</a>
        <a href="/">← Back to Home</a>
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
        body { font-family: 'Segoe UI', sans-serif; background: #0a0a12; color: #e0e0e0; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #ffc107; }
        table { width: 100%; border-collapse: collapse; background: #1a1a2e; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #2a2a3e; }
        th { background: #ffc107; color: #0a0a12; }
        .badge { background: #28a745; padding: 3px 8px; border-radius: 3px; font-size: 12px; }
        .nav { background: #1a1a2e; padding: 15px; margin-bottom: 20px; border-radius: 5px; }
        .nav a { color: #ffc107; text-decoration: none; margin-right: 20px; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #1a1a2e; padding: 20px; border-radius: 10px; text-align: center; }
        .stat-number { font-size: 2rem; color: #ffc107; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">Home</a>
            <a href="/admin">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
        
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
        
        <h2>Users</h2>
        <table>
            <thead>
                <tr><th>Username</th><th>Email</th><th>Admin</th><th>Created</th></tr>
            </thead>
            <tbody>
                {% for uid, user in users.items() %}
                <tr>
                    <td>{{ user.username }}</td>
                    <td>{{ user.email }}</td>
                    <td>{% if user.is_admin %}<span class="badge">Admin</span>{% else %}User{% endif %}</td>
                    <td>{{ user.created[:10] if user.created else 'N/A' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
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
