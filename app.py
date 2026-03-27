from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from uuid import uuid4
from functools import wraps
import json
import os
import sys
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pawn_shop_secret_key_2026'

# Database configuration
DB_PATH = 'pawn_shop.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize SQLite database"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Users table
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
            is_admin BOOLEAN DEFAULT 0,
            created TEXT,
            pawn_submissions TEXT,
            redeem_requests TEXT,
            purchases TEXT
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
            for_sale BOOLEAN DEFAULT 0,
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
            created TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        
        conn.commit()
        conn.close()
        print("✓ Database initialized")
    except Exception as e:
        print(f"Error initializing DB: {e}")

def load_data_from_db():
    """Load data from SQLite into memory"""
    global users_db, items_db, loans_db
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Load users
        c.execute('SELECT * FROM users')
        for row in c.fetchall():
            user_dict = dict(row)
            user_dict['pawn_submissions'] = json.loads(user_dict.get('pawn_submissions') or '{}')
            user_dict['redeem_requests'] = json.loads(user_dict.get('redeem_requests') or '{}')
            user_dict['purchases'] = json.loads(user_dict.get('purchases') or '{}')
            users_db[user_dict['id']] = user_dict
        
        # Load items
        c.execute('SELECT * FROM items')
        for row in c.fetchall():
            items_db[row['id']] = dict(row)
        
        # Load loans
        c.execute('SELECT * FROM loans')
        for row in c.fetchall():
            loans_db[row['id']] = dict(row)
        
        conn.close()
        if users_db or items_db or loans_db:
            print(f"✓ Loaded {len(users_db)} users, {len(items_db)} items, {len(loans_db)} loans from DB")
    except Exception as e:
        print(f"Error loading from DB: {e}")

def save_data_to_db():
    """Save data from memory to SQLite"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Save users
        for uid, user in users_db.items():
            user_copy = user.copy()
            user_copy['pawn_submissions'] = json.dumps(user.get('pawn_submissions', {}))
            user_copy['redeem_requests'] = json.dumps(user.get('redeem_requests', {}))
            user_copy['purchases'] = json.dumps(user.get('purchases', {}))
            
            c.execute('''REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (user_copy['id'], user_copy['username'], user_copy['email'], 
                 user_copy['password_hash'], user_copy.get('phone'), user_copy.get('dob'),
                 user_copy.get('employment'), user_copy.get('residence_proof'),
                 user_copy.get('id_front'), user_copy.get('id_back'),
                 user_copy.get('banking_letter'), user_copy.get('bank_statement'),
                 user_copy.get('is_admin', False), user_copy.get('created'),
                 user_copy['pawn_submissions'], user_copy['redeem_requests'],
                 user_copy['purchases']))
        
        # Save items
        for iid, item in items_db.items():
            c.execute('''REPLACE INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (item['id'], item['name'], item.get('category'), item.get('desc'),
                 item.get('value'), item.get('rate'), item.get('days'),
                 item.get('image_url'), item.get('for_sale', False),
                 item.get('status', 'available'), item.get('created')))
        
        # Save loans
        for lid, loan in loans_db.items():
            c.execute('''REPLACE INTO loans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (loan['id'], loan['user'], loan['item'], loan['amount'],
                 loan['rate'], loan['due'], loan['status'], loan['total_due'],
                 loan['created']))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving to DB: {e}")

# Data file paths - try to use absolute paths for AppCreator24
try:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
except:
    DATA_DIR = 'data'

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
ITEMS_FILE = os.path.join(DATA_DIR, 'items.json')
LOANS_FILE = os.path.join(DATA_DIR, 'loans.json')

# Create data directory if it doesn't exist
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except:
    print("Warning: Could not create data directory, using in-memory storage only")

# In-memory storage (fallback for AppCreator24)
users_db = {}
items_db = {}
loans_db = {}
USE_JSON = True  # Toggle to False if JSON doesn't work

def toggle_storage(use_json=True):
    global USE_JSON
    USE_JSON = use_json
    if not use_json:
        print("Switched to in-memory storage mode")

def load_data():
    """Load data from SQLite database"""
    load_data_from_db()

def save_data():
    """Save data to SQLite database"""
    save_data_to_db()

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
        if not users_db[session['user_id']].get('is_admin'):
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

# ============ ROUTES ============

@app.route('/')
def home():
    return render_template_string(HOME)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        phone = data.get('phone', '').strip()
        dob = data.get('dob', '').strip()
        employment = data.get('employment', '').strip()
        residence_proof = data.get('residence_proof', '')
        id_front = data.get('id_front', '')
        id_back = data.get('id_back', '')
        banking_letter = data.get('banking_letter', '')
        bank_statement = data.get('bank_statement', '')
        
        # Validate - basic fields required
        if not all([username, email, password, dob, employment, phone]):
            missing = []
            if not username: missing.append('username')
            if not email: missing.append('email')
            if not password: missing.append('password')
            if not phone: missing.append('phone')
            if not dob: missing.append('dob')
            if not employment: missing.append('employment')
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
        
        # Check if user exists
        for u in users_db.values():
            if u['username'] == username:
                return jsonify({'error': 'Username taken'}), 400
            if u['email'] == email:
                return jsonify({'error': 'Email taken'}), 400
        
        # Create user with hashed password
        uid = gen_id()
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        users_db[uid] = {
            'id': uid,
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'phone': phone,
            'dob': dob,
            'employment': employment,
            'residence_proof': residence_proof,
            'id_front': id_front,
            'id_back': id_back,
            'banking_letter': banking_letter,
            'bank_statement': bank_statement,
            'is_admin': False,
            'created': datetime.now().isoformat(),
            'pawn_submissions': {},
            'redeem_requests': {},
            'purchases': {}
        }
        
        # Save to database
        try:
            save_data()
            print(f"✓ User created: {username} (ID: {uid})")
        except Exception as e:
            print(f"✗ Error saving user {username}: {e}")
            return jsonify({'error': 'Failed to save account'}), 500
        
        return jsonify({'success': True, 'msg': 'Account created! Login now', 'user_id': uid}), 201
    
    return render_template_string(AUTH_PAGE)

@app.route('/reset-admin', methods=['POST', 'GET'])
def reset_admin():
    """Emergency endpoint to reset admin account (for AppCreator24)"""
    global users_db
    # Clear all users first
    users_db.clear()
    
    aid = gen_id()
    users_db[aid] = {
        'id': aid, 'username': 'admin', 'email': 'admin@shop.com',
        'password_hash': 'pbkdf2:sha256:1000000$8oQcBveoiBLZh6KY$7a1d730b7dafee11463aa588d09258e1175111bb1b0703aae598bed26f290a03',
        'phone': '555-0000', 'dob': '1990-01-01', 'employment': 'employed',
        'residence_proof': '', 'id_front': '', 'id_back': '',
        'banking_letter': '', 'bank_statement': '',
        'is_admin': True, 'created': datetime.now().isoformat(),
        'pawn_submissions': {}, 'redeem_requests': {}, 'purchases': {}
    }
    save_data()
    return jsonify({'msg': 'Admin reset! Username: admin, Password: admin123', 'admin_id': aid}), 200

@app.route('/check-admin', methods=['GET'])
def check_admin():
    """Debug endpoint to check admin users"""
    admin_users = {k: v for k, v in users_db.items() if v.get('is_admin')}
    return jsonify({
        'total_users': len(users_db),
        'admin_count': len(admin_users),
        'admins': admin_users
    }), 200

@app.route('/db-status', methods=['GET'])
def db_status():
    """Check database status and connectivity"""
    db_info = {
        'database_file': DB_PATH,
        'file_exists': os.path.exists(DB_PATH),
        'memory_data': {
            'users': len(users_db),
            'items': len(items_db),
            'loans': len(loans_db)
        },
        'database_data': {}
    }
    
    # Check database connectivity
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Count users in DB
        c.execute('SELECT COUNT(*) as count FROM users')
        user_count = c.fetchone()['count']
        
        # Count items in DB
        c.execute('SELECT COUNT(*) as count FROM items')
        item_count = c.fetchone()['count']
        
        # Count loans in DB
        c.execute('SELECT COUNT(*) as count FROM loans')
        loan_count = c.fetchone()['count']
        
        db_info['database_data'] = {
            'users': user_count,
            'items': item_count,
            'loans': loan_count
        }
        
        db_info['database_connected'] = True
        db_info['status'] = '✓ Database working perfectly!'
        
        conn.close()
    except Exception as e:
        db_info['database_connected'] = False
        db_info['error'] = str(e)
        db_info['status'] = '✗ Database connection failed'
    
    return jsonify(db_info), 200

@app.route('/debug/users', methods=['GET'])
def debug_users():
    """Debug endpoint - list all users (development only)"""
    user_list = []
    for uid, u in users_db.items():
        user_list.append({
            'id': uid,
            'username': u.get('username'),
            'email': u.get('email'),
            'is_admin': u.get('is_admin'),
            'password_hash_preview': u.get('password_hash', '')[:30] + '...' if u.get('password_hash') else 'None',
            'created': u.get('created')
        })
    
    return jsonify({
        'total_users': len(users_db),
        'users': user_list
    }), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    # Search for user
    for uid, u in users_db.items():
        if u['username'] == username:
            # User found, check password
            try:
                if check_password_hash(u['password_hash'], password):
                    session['user_id'] = uid
                    session['username'] = username
                    print(f"✓ Login successful: {username}")
                    return jsonify({'success': True, 'is_admin': u['is_admin']}), 200
                else:
                    print(f"✗ Wrong password for user: {username}")
                    return jsonify({'error': 'Invalid credentials'}), 401
            except Exception as e:
                print(f"✗ Password check error for {username}: {e}")
                return jsonify({'error': 'Invalid credentials'}), 401
    
    print(f"✗ User not found: {username}")
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/browse')
@login_required
def browse():
    return render_template_string(BROWSE_PAGE)

@app.route('/api/items')
@login_required
def api_items():
    cat = request.args.get('cat', '')
    result = []
    for iid, item in items_db.items():
        # Only show items that are available AND NOT marked for sale (available for pawning)
        if item['status'] == 'available' and not item.get('for_sale'):
            if not cat or item['category'] == cat:
                result.append({
                    'id': iid,
                    'name': item['name'],
                    'category': item['category'],
                    'desc': item['desc'],
                    'value': item['value'],
                    'rate': item['rate'],
                    'days': item['days'],
                    'image_url': item.get('image_url', '')
                })
    return jsonify(result)

@app.route('/api/pawn', methods=['POST'])
@login_required
def api_pawn():
    data = request.get_json()
    iid = data.get('iid')
    
    if iid not in items_db:
        return jsonify({'error': 'Item not found'}), 404
    
    item = items_db[iid]
    if item['status'] != 'available':
        return jsonify({'error': 'Not available'}), 400
    
    loan_amt = item['value']
    interest = item['rate']
    due = datetime.now() + timedelta(days=item['days'])
    total_due = loan_amt * (1 + interest / 100)
    
    lid = gen_id()
    loans_db[lid] = {
        'id': lid,
        'user': session['user_id'],
        'item': iid,
        'amount': loan_amt,
        'rate': interest,
        'due': due.isoformat(),
        'status': 'active',
        'total_due': round(total_due, 2),
        'created': datetime.now().isoformat()
    }
    
    item['status'] = 'pawned'
    save_data()
    
    return jsonify({
        'success': True,
        'loan_id': lid,
        'amount': loan_amt,
        'total_due': round(total_due, 2),
        'due_date': due.strftime('%Y-%m-%d')
    }), 201

@app.route('/api/loans')
@login_required
def api_loans():
    uid = session['user_id']
    result = []
    
    for lid, loan in loans_db.items():
        if loan['user'] == uid:
            due_date = datetime.fromisoformat(loan['due'])
            now = datetime.now()
            days_left = (due_date - now).days
            
            result.append({
                'id': lid,
                'item': loan.get('item', 'Unknown Item'),  # Item name is stored directly
                'amount': loan['amount'],
                'rate': loan['rate'],
                'total_due': loan['total_due'],
                'due': loan['due'],
                'status': loan['status'],
                'days_left': max(0, days_left)
            })
    
    return jsonify(result)

@app.route('/api/repay/<lid>', methods=['POST'])
@login_required
def api_repay(lid):
    if lid not in loans_db:
        return jsonify({'error': 'Loan not found'}), 404
    
    loan = loans_db[lid]
    if loan['user'] != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if loan['status'] != 'active':
        return jsonify({'error': 'Loan is not active'}), 400
    
    # Mark loan as repaid
    loan['status'] = 'repaid'
    
    # Mark item as available again
    item_id = loan['item']
    if item_id in items_db:
        items_db[item_id]['status'] = 'available'
    
    save_data()
    
    return jsonify({
        'success': True,
        'msg': f"Loan repaid! Total paid: ${loan['total_due']}"
    }), 200

# ============ USER PAWN SUBMISSION ============

@app.route('/pawn-my-item')
@login_required
def pawn_my_item():
    return render_template_string(PAWN_ITEM_PAGE)

@app.route('/api/submit-pawn', methods=['POST'])
@login_required
def api_submit_pawn():
    data = request.get_json()
    item_name = data.get('item_name', '').strip()
    item_desc = data.get('item_desc', '').strip()
    loan_request = float(data.get('loan_request', 0))
    item_picture = data.get('item_picture', '')
    proof_ownership = data.get('proof_ownership', '')
    affidavit = data.get('affidavit', '')
    
    if not all([item_name, item_desc, loan_request, item_picture, proof_ownership, affidavit]):
        return jsonify({'error': 'All fields required'}), 400
    
    if loan_request <= 0:
        return jsonify({'error': 'Loan amount must be greater than 0'}), 400
    
    pawn_id = gen_id()
    users_db[session['user_id']].setdefault('pawn_submissions', {})[pawn_id] = {
        'id': pawn_id,
        'name': item_name,
        'desc': item_desc,
        'loan_amount': loan_request,
        'picture': item_picture,
        'ownership_proof': proof_ownership,
        'affidavit': affidavit,
        'status': 'pending',
        'created': datetime.now().isoformat()
    }
    save_data()
    
    return jsonify({'success': True, 'msg': 'Pawn request submitted! Admin will review soon'}), 201

# ============ BUY ITEMS (Admin Listed) ============

@app.route('/buy-items')
@login_required
def buy_items():
    return render_template_string(BUY_ITEMS_PAGE)

@app.route('/api/sale-items')
@login_required
def api_sale_items():
    result = []
    # Only show admin items (items_db) marked for sale
    for iid, item in items_db.items():
        if item['status'] == 'available' and item.get('for_sale'):
            result.append({
                'id': iid,
                'name': item['name'],
                'category': item['category'],
                'desc': item['desc'],
                'price': item['value'],
                'image_url': item.get('image_url', ''),
                'type': 'admin_item'
            })
    
    return jsonify(result)

@app.route('/api/buy-item/<iid>', methods=['POST'])
@login_required
def api_buy_item(iid):
    if iid not in items_db:
        return jsonify({'error': 'Item not found'}), 404
    
    item = items_db[iid]
    if item['status'] != 'available' or not item.get('for_sale'):
        return jsonify({'error': 'Item not available for sale'}), 400
    
    purchase_id = gen_id()
    users_db[session['user_id']].setdefault('purchases', {})[purchase_id] = {
        'id': purchase_id,
        'item_id': iid,
        'item_name': item['name'],
        'price': item['value'],
        'status': 'pending_approval',
        'created': datetime.now().isoformat()
    }
    save_data()
    
    return jsonify({
        'success': True,
        'purchase_id': purchase_id,
        'msg': f"Purchase request submitted for {item['name']}! Admin will contact you soon"
    }), 201

# ============ REDEEM PAWNED ITEMS ============

@app.route('/redeem')
@login_required
def redeem():
    return render_template_string(REDEEM_PAGE)

@app.route('/api/submit-redeem', methods=['POST'])
@login_required
def api_submit_redeem():
    data = request.get_json()
    loan_id = data.get('loan_id')
    payment_proof = data.get('payment_proof', '')
    collection_type = data.get('collection_type', '')
    
    if not all([loan_id, payment_proof, collection_type]):
        return jsonify({'error': 'All fields required'}), 400
    
    if collection_type not in ['collection', 'delivery']:
        return jsonify({'error': 'Invalid collection type'}), 400
    
    if loan_id not in loans_db:
        return jsonify({'error': 'Loan not found'}), 404
    
    loan = loans_db[loan_id]
    if loan['user'] != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if loan['status'] != 'active':
        return jsonify({'error': 'Loan must be active to redeem'}), 400
    
    redeem_id = gen_id()
    users_db[session['user_id']].setdefault('redeem_requests', {})[redeem_id] = {
        'id': redeem_id,
        'loan_id': loan_id,
        'item_name': items_db.get(loan['item'], {}).get('name', 'Unknown'),
        'payment_proof': payment_proof,
        'collection_type': collection_type,
        'status': 'pending',
        'created': datetime.now().isoformat()
    }
    save_data()
    
    return jsonify({'success': True, 'msg': 'Redeem request submitted! Admin will process soon'}), 201

@app.route('/api/pawn-submissions')
@login_required
def api_pawn_submissions():
    uid = session['user_id']
    user = users_db.get(uid, {})
    submissions = user.get('pawn_submissions', {})
    result = []
    for pid, pawn in submissions.items():
        result.append({
            'id': pid,
            'name': pawn['name'],
            'desc': pawn['desc'],
            'loan_amount': pawn['loan_amount'],
            'status': pawn['status'],
            'created': pawn['created']
        })
    return jsonify(result)

@app.route('/api/redeem-requests')
@login_required
def api_redeem_requests():
    uid = session['user_id']
    user = users_db.get(uid, {})
    requests = user.get('redeem_requests', {})
    result = []
    for rid, req in requests.items():
        result.append({
            'id': rid,
            'item_name': req['item_name'],
            'collection_type': req['collection_type'],
            'status': req['status'],
            'created': req['created']
        })
    return jsonify(result)

@app.route('/api/purchases')
@login_required
def api_purchases():
    uid = session['user_id']
    user = users_db.get(uid, {})
    purchases = user.get('purchases', {})
    result = []
    for pid, purch in purchases.items():
        result.append({
            'id': pid,
            'item_name': purch.get('item_name'),
            'price': purch.get('price'),
            'status': purch.get('status', 'completed'),
            'created': purch.get('created')
        })
    return jsonify(result)

@app.route('/api/messages')
@login_required
def api_messages():
    uid = session['user_id']
    user = users_db.get(uid, {})
    messages = user.get('messages', [])
    return jsonify(messages)

@app.route('/api/send-message', methods=['POST'])
@login_required
def api_send_message():
    uid = session['user_id']
    user = users_db.get(uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    if 'messages' not in user:
        user['messages'] = []
    
    message = {
        'sender': user['username'],
        'text': text,
        'created': datetime.now().isoformat()
    }
    
    user['messages'].append(message)
    save_data()
    
    return jsonify({'success': True, 'msg': 'Message sent!'}), 200

@app.route('/api/admin/messages/<uid>')
@admin_required
def api_admin_messages(uid):
    user = users_db.get(uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    messages = user.get('messages', [])
    return jsonify(messages)

@app.route('/api/admin/send-message/<uid>', methods=['POST'])
@admin_required
def api_admin_send_message(uid):
    user = users_db.get(uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    if 'messages' not in user:
        user['messages'] = []
    
    message = {
        'sender': 'admin',
        'text': text,
        'created': datetime.now().isoformat()
    }
    
    user['messages'].append(message)
    save_data()
    
    return jsonify({'success': True, 'msg': 'Message sent!'}), 200

@app.route('/api/admin/redeem-requests')
@admin_required
def api_admin_redeem_requests():
    result = []
    for uid, user in users_db.items():
        requests = user.get('redeem_requests', {})
        for rid, req in requests.items():
            result.append({
                'id': rid,
                'user_id': uid,
                'username': user['username'],
                'item_name': req['item_name'],
                'collection_type': req['collection_type'],
                'status': req['status'],
                'created': req['created']
            })
    return jsonify(result)

@app.route('/api/admin/purchases')
@admin_required
def api_admin_purchases():
    result = []
    for uid, user in users_db.items():
        purchases = user.get('purchases', {})
        for pid, purch in purchases.items():
            result.append({
                'id': pid,
                'user_id': uid,
                'username': user['username'],
                'item_name': purch['item_name'],
                'price': purch['price'],
                'status': purch['status'],
                'created': purch['created']
            })
    return jsonify(result)

@app.route('/api/admin/approve-purchase/<uid>/<pid>', methods=['POST'])
@admin_required
def api_approve_purchase(uid, pid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    purchases = user.get('purchases', {})
    
    if pid not in purchases:
        return jsonify({'error': 'Purchase not found'}), 404
    
    purch = purchases[pid]
    item_id = purch['item_id']
    
    # Check if it's an admin item or pawn item
    is_pawn = False
    for uid2, user2 in users_db.items():
        if item_id in user2.get('pawn_submissions', {}):
            is_pawn = True
            break
    
    if not is_pawn:
        # It's an admin item
        if item_id in items_db:
            items_db[item_id]['status'] = 'sold'
    
    purch['status'] = 'approved'
    save_data()
    return jsonify({'success': True, 'msg': 'Purchase approved'}), 200

@app.route('/api/admin/reject-purchase/<uid>/<pid>', methods=['POST'])
@admin_required
def api_reject_purchase(uid, pid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    purchases = user.get('purchases', {})
    
    if pid not in purchases:
        return jsonify({'error': 'Purchase not found'}), 404
    
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    
    purchases[pid]['status'] = 'rejected'
    purchases[pid]['rejection_reason'] = reason
    save_data()
    return jsonify({'success': True, 'msg': 'Purchase rejected'}), 200

@app.route('/api/admin/approve-redeem/<uid>/<rid>', methods=['POST'])
@admin_required
def api_approve_redeem(uid, rid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    requests = user.get('redeem_requests', {})
    
    if rid not in requests:
        return jsonify({'error': 'Redeem request not found'}), 404
    
    req = requests[rid]
    req['status'] = 'approved'
    
    return jsonify({'success': True, 'msg': 'Redeem request approved!'}), 200

@app.route('/api/admin/reject-redeem/<uid>/<rid>', methods=['POST'])
@admin_required
def api_reject_redeem(uid, rid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    requests = user.get('redeem_requests', {})
    
    if rid not in requests:
        return jsonify({'error': 'Redeem request not found'}), 404
    
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    req = requests[rid]
    req['status'] = 'rejected'
    req['rejection_reason'] = reason
    
    return jsonify({'success': True, 'msg': 'Redeem request rejected'}), 200

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    if uid not in users_db:
        return redirect(url_for('logout'))
    user = users_db[uid]
    return render_template_string(DASHBOARD_PAGE, user=user)

@app.route('/admin')
@admin_required
def admin():
    return render_template_string(ADMIN_PAGE, 
        total_items=len(items_db),
        available=sum(1 for i in items_db.values() if i['status'] == 'available'),
        active_loans=sum(1 for l in loans_db.values() if l['status'] == 'active'),
        total_users=len(users_db)
    )

@app.route('/api/admin/add-item', methods=['POST'])
@admin_required
def api_add_item():
    data = request.get_json()
    iid = gen_id()
    items_db[iid] = {
        'id': iid,
        'name': data.get('name'),
        'category': data.get('category'),
        'desc': data.get('desc'),
        'value': float(data.get('value')),
        'rate': float(data.get('rate', 15)),
        'days': int(data.get('days', 30)),
        'image_url': data.get('image_url', ''),
        'for_sale': data.get('for_sale') == True or data.get('for_sale') == 'true',
        'status': 'available',
        'created': datetime.now().isoformat()
    }
    save_data()
    return jsonify({'success': True, 'id': iid}), 201

@app.route('/api/admin/delete-item/<iid>', methods=['DELETE'])
@admin_required
def api_delete_item(iid):
    if iid in items_db:
        del items_db[iid]
        save_data()
        return jsonify({'success': True}), 200
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/admin/delete-pawn/<pid>', methods=['DELETE'])
@admin_required
def api_delete_pawn(pid):
    # Find and delete the pawn item
    for uid, user in users_db.items():
        submissions = user.get('pawn_submissions', {})
        if pid in submissions:
            del submissions[pid]
            save_data()
            return jsonify({'success': True}), 200
    
    return jsonify({'error': 'Pawn item not found'}), 404

@app.route('/api/admin/items')
@admin_required
def api_admin_items():
    result = []
    # Admin items
    for iid, item in items_db.items():
        result.append({
            'id': iid,
            'name': item['name'],
            'cat': item['category'],
            'val': item['value'],
            'status': item['status'],
            'type': 'admin'
        })
    
    # Pawned items from users
    for uid, user in users_db.items():
        submissions = user.get('pawn_submissions', {})
        for pid, pawn in submissions.items():
            result.append({
                'id': pid,
                'name': pawn['name'],
                'cat': 'User Pawn',
                'val': pawn['loan_amount'],
                'status': pawn['status'],
                'type': 'pawn',
                'user_id': uid,
                'username': user['username']
            })
    
    return jsonify(result)

@app.route('/api/admin/users')
@admin_required
def api_admin_users():
    result = []
    for uid, user in users_db.items():
        if not user.get('is_admin'):  # Don't show other admins
            result.append({
                'id': uid,
                'username': user['username'],
                'email': user['email'],
                'phone': user['phone'],
                'dob': user['dob'],
                'employment': user['employment'],
                'has_residence_proof': bool(user.get('residence_proof')),
                'has_id_front': bool(user.get('id_front')),
                'has_id_back': bool(user.get('id_back')),
                'has_banking_letter': bool(user.get('banking_letter')),
                'has_bank_statement': bool(user.get('bank_statement')),
                'created': user['created']
            })
    return jsonify(result)

@app.route('/api/admin/user-documents/<uid>')
@admin_required
def api_admin_user_documents(uid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    return jsonify({
        'username': user['username'],
        'email': user['email'],
        'phone': user['phone'],
        'dob': user['dob'],
        'employment': user['employment'],
        'residence_proof': user.get('residence_proof', ''),
        'id_front': user.get('id_front', ''),
        'id_back': user.get('id_back', ''),
        'banking_letter': user.get('banking_letter', ''),
        'bank_statement': user.get('bank_statement', '')
    })

# ============ ADMIN PAWN SUBMISSIONS ============

@app.route('/api/admin/pawn-submissions')
@admin_required
def api_admin_pawn_submissions():
    result = []
    for uid, user in users_db.items():
        submissions = user.get('pawn_submissions', {})
        for pid, pawn in submissions.items():
            result.append({
                'id': pid,
                'user_id': uid,
                'username': user['username'],
                'item_name': pawn['name'],
                'desc': pawn['desc'],
                'loan_amount': pawn['loan_amount'],
                'status': pawn['status'],
                'created': pawn['created']
            })
    return jsonify(result)

@app.route('/api/admin/approve-pawn/<uid>/<pid>', methods=['POST'])
@admin_required
def api_approve_pawn(uid, pid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    submissions = user.get('pawn_submissions', {})
    
    if pid not in submissions:
        return jsonify({'error': 'Pawn submission not found'}), 404
    
    pawn = submissions[pid]
    pawn['status'] = 'approved'
    
    # Create a loan from the pawn submission
    loan_amt = pawn['loan_amount']
    interest = 15.0  # Default interest rate
    due = datetime.now() + timedelta(days=30)
    total_due = loan_amt * (1 + interest / 100)
    
    lid = gen_id()
    loans_db[lid] = {
        'id': lid,
        'user': uid,
        'item': pawn.get('item_name', 'Unknown Item'),  # Store item name instead of pawn ID
        'item_description': pawn.get('description', ''),
        'amount': loan_amt,
        'rate': interest,
        'due': due.isoformat(),
        'status': 'active',
        'total_due': round(total_due, 2),
        'created': datetime.now().isoformat()
    }
    save_data()
    
    return jsonify({'success': True, 'msg': 'Pawn approved! Loan created', 'loan_id': lid}), 200

@app.route('/api/admin/reject-pawn/<uid>/<pid>', methods=['POST'])
@admin_required
def api_reject_pawn(uid, pid):
    if uid not in users_db:
        return jsonify({'error': 'User not found'}), 404
    
    user = users_db[uid]
    submissions = user.get('pawn_submissions', {})
    
    if pid not in submissions:
        return jsonify({'error': 'Pawn submission not found'}), 404
    
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    pawn = submissions[pid]
    pawn['status'] = 'rejected'
    pawn['rejection_reason'] = reason
    save_data()
    
    return jsonify({'success': True, 'msg': 'Pawn rejected'}), 200

# ============ TEMPLATES ============

HOME = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="text-align: center;">
                <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
                <div style="font-size: 11px; color: #ffc107; font-weight: bold; margin-top: 3px;">online pawn shop</div>
            </div>
            <h1 style="margin: 0;">O.P.S</h1>
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
            <a href="/register">Sign Up</a>
            <a onclick="window.location.href='#'; document.getElementById('loginform').style.display='flex';" style="cursor:pointer;">Login</a>
        </div>
    </nav>
    <div class="hero">
        <h1>Quick Pawn Loans</h1>
        <p>Sell or pawn your items for instant cash</p>
        <a href="/register" class="cta">Get Started</a>
    </div>

    <div class="carousel">
        <div class="carousel-inner">
            <div class="carousel-item active">
                <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="text-align: center; color: #000;">
                        <h2 style="font-size: 36px; margin-bottom: 10px;">💰 Quick Loans</h2>
                        <p style="font-size: 16px;">Get instant cash in minutes</p>
                    </div>
                </div>
            </div>
            <div class="carousel-item">
                <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #51cf66 0%, #40c057 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="text-align: center; color: #fff;">
                        <h2 style="font-size: 36px; margin-bottom: 10px;">✅ Secure & Safe</h2>
                        <p style="font-size: 16px;">Your data is fully protected</p>
                    </div>
                </div>
            </div>
            <div class="carousel-item">
                <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #4c6ef5 0%, #5c7cfa 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="text-align: center; color: #fff;">
                        <h2 style="font-size: 36px; margin-bottom: 10px;">🎯 Fair Rates</h2>
                        <p style="font-size: 16px;">Best interest rates in town</p>
                    </div>
                </div>
            </div>
            <div class="carousel-item">
                <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #f06595 0%, #f783ac 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="text-align: center; color: #fff;">
                        <h2 style="font-size: 36px; margin-bottom: 10px;">📱 Easy Access</h2>
                        <p style="font-size: 16px;">Available 24/7 online</p>
                    </div>
                </div>
            </div>
        </div>
        <button class="carousel-nav carousel-prev" onclick="changeCarousel(-1)">❮</button>
        <button class="carousel-nav carousel-next" onclick="changeCarousel(1)">❯</button>
        <div class="carousel-controls">
            <div class="carousel-dot active" onclick="currentCarousel(0)"></div>
            <div class="carousel-dot" onclick="currentCarousel(1)"></div>
            <div class="carousel-dot" onclick="currentCarousel(2)"></div>
            <div class="carousel-dot" onclick="currentCarousel(3)"></div>
        </div>
    </div>

    <script>
        let carouselIndex = 0;
        let carouselTimer;

        function changeCarousel(n) {
            showCarousel(carouselIndex += n);
            resetCarouselTimer();
        }

        function currentCarousel(n) {
            showCarousel(carouselIndex = n);
            resetCarouselTimer();
        }

        function showCarousel(n) {
            const items = document.querySelectorAll('.carousel-item');
            const dots = document.querySelectorAll('.carousel-dot');
            
            console.log('Showing carousel:', n, 'Total items:', items.length);
            
            if (n >= items.length) { carouselIndex = 0; }
            if (n < 0) { carouselIndex = items.length - 1; }
            
            items.forEach((item, idx) => {
                item.classList.remove('active');
                if (idx === carouselIndex) {
                    item.classList.add('active');
                }
            });
            
            dots.forEach((dot, idx) => {
                dot.classList.remove('active');
                if (idx === carouselIndex) {
                    dot.classList.add('active');
                }
            });
        }

        function autoCarousel() {
            changeCarousel(1);
        }

        function resetCarouselTimer() {
            clearInterval(carouselTimer);
            carouselTimer = setInterval(autoCarousel, 3000);
        }

        // Initialize and start auto-carousel
        window.addEventListener('load', () => {
            showCarousel(0);
            resetCarouselTimer();
        });
    </script>
    <div class="features">
        <div class="feature">
            <h3>⚡ Fast Cash</h3>
            <p>Get approved in minutes</p>
        </div>
        <div class="feature">
            <h3>🔒 Secure</h3>
            <p>Your data is protected</p>
        </div>
        <div class="feature">
            <h3>💎 Fair Rates</h3>
            <p>Competitive interest rates</p>
        </div>
        <div class="feature">
            <h3>📱 Easy</h3>
            <p>Simple online process</p>
        </div>
    </div>

    <div id="loginform" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);align-items:center;justify-content:center;z-index:999;">
        <div style="background:#1a1a1a;padding:35px;border-radius:10px;max-width:450px;width:90%;">
            <h2 style="color:#ffc107;margin-bottom:20px;">Login</h2>
            <form onsubmit="submitLogin(event)">
                <div style="margin-bottom:15px;">
                    <label style="display:block;margin-bottom:5px;font-weight:bold;">Username</label>
                    <input type="text" id="luname" required style="width:100%;padding:10px;background:#2a2a2a;color:#fff;border:1px solid #444;border-radius:5px;">
                </div>
                <div style="margin-bottom:15px;">
                    <label style="display:block;margin-bottom:5px;font-weight:bold;">Password</label>
                    <input type="password" id="lpass" required style="width:100%;padding:10px;background:#2a2a2a;color:#fff;border:1px solid #444;border-radius:5px;">
                </div>
                <button type="submit" style="width:100%;padding:12px;background:#ffc107;color:#000;border:none;border-radius:5px;font-weight:bold;cursor:pointer;">Login</button>
            </form>
            <p style="margin-top:15px;text-align:center;color:#aaa;">
                No account? <a href="/register" style="color:#ffc107;text-decoration:none;">Sign up</a>
            </p>
            <button onclick="document.getElementById('loginform').style.display='none'" style="margin-top:15px;width:100%;padding:10px;background:#666;color:#fff;border:none;border-radius:5px;cursor:pointer;">Close</button>
        </div>
    </div>

    <script>
        async function submitLogin(e) {
            e.preventDefault();
            const res = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: document.getElementById('luname').value,
                    password: document.getElementById('lpass').value
                })
            });
            const data = await res.json();
            if (res.ok) {
                window.location.href = data.is_admin ? '/admin' : '/browse';
            } else {
                alert(data.error || 'Login failed');
            }
        }
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

AUTH_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Sign Up - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Create Account</h1>
        <div id="msg"></div>
        <div class="scroll">
            <form id="form">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" id="uname" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="email" required>
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" id="pass" required>
                </div>
                <div class="form-group">
                    <label>Phone</label>
                    <input type="tel" id="phone">
                </div>
                <div class="row">
                    <div class="form-group">
                        <label>Date of Birth</label>
                        <input type="date" id="dob" required>
                    </div>
                    <div class="form-group">
                        <label>Employment Status</label>
                        <select id="emp" required>
                            <option value="">Select</option>
                            <option value="employed">Employed</option>
                            <option value="self-employed">Self-Employed</option>
                            <option value="unemployed">Unemployed</option>
                            <option value="student">Student</option>
                            <option value="retired">Retired</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>Proof of Residence (Photo)</label>
                    <div class="proof-preview" id="preview">📄</div>
                    <label for="proofFile" class="file-label">Click to upload proof</label>
                    <input type="file" id="proofFile" accept="image/*">
                </div>

                <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid #444;">
                    <h3 style="color: #ffc107; margin-bottom: 15px; font-size: 15px;">Government ID Photos</h3>
                    
                    <div class="id-row">
                        <div class="id-col">
                            <label style="margin-bottom: 8px;">ID Front Side</label>
                            <div class="proof-preview" id="previewFront">📷</div>
                            <label for="idFrontFile" class="file-label">Upload Front</label>
                            <input type="file" id="idFrontFile" accept="image/*">
                        </div>
                        <div class="id-col">
                            <label style="margin-bottom: 8px;">ID Back Side</label>
                            <div class="proof-preview" id="previewBack">📷</div>
                            <label for="idBackFile" class="file-label">Upload Back</label>
                            <input type="file" id="idBackFile" accept="image/*">
                        </div>
                    </div>
                </div>

                <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid #444;">
                    <h3 style="color: #ffc107; margin-bottom: 15px; font-size: 15px;">Banking Documents (PDF or Image)</h3>
                    
                    <div class="id-row">
                        <div class="id-col">
                            <label style="margin-bottom: 8px;">Banking Letter</label>
                            <div style="width: 100%; padding: 15px; background: #2a2a2a; border: 1px dashed #ffc107; border-radius: 5px; text-align: center; margin-bottom: 10px;" id="bankLetterStatus">📄 No file</div>
                            <label for="bankingLetterFile" class="file-label">Upload PDF or Image</label>
                            <input type="file" id="bankingLetterFile" accept=".pdf,image/*">
                        </div>
                        <div class="id-col">
                            <label style="margin-bottom: 8px;">Bank Statement</label>
                            <div style="width: 100%; padding: 15px; background: #2a2a2a; border: 1px dashed #ffc107; border-radius: 5px; text-align: center; margin-bottom: 10px;" id="bankStatementStatus">📄 No file</div>
                            <label for="bankStatementFile" class="file-label">Upload PDF or Image</label>
                            <input type="file" id="bankStatementFile" accept=".pdf,image/*">
                        </div>
                    </div>
                </div>
                
                <button type="submit" style="margin-top: 25px;">Create Account</button>
            </form>
        </div>
        <div class="home">
            <a href="/">← Home</a>
        </div>
    </div>

    <script>
        // Proof of Residence
        document.getElementById('proofFile').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('preview').innerHTML = `<img src="${ev.target.result}">`;
                    window.proofBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        // ID Front
        document.getElementById('idFrontFile').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('previewFront').innerHTML = `<img src="${ev.target.result}">`;
                    window.idFrontBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        // ID Back
        document.getElementById('idBackFile').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('previewBack').innerHTML = `<img src="${ev.target.result}">`;
                    window.idBackBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        // Banking Letter (PDF or Image)
        document.getElementById('bankingLetterFile').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const isPDF = file.type === 'application/pdf';
                const isImage = file.type.startsWith('image/');
                
                if (!isPDF && !isImage) {
                    show('error', 'Banking letter must be a PDF or image file');
                    this.value = '';
                    return;
                }
                if (file.size > 2000000) {
                    show('error', 'Banking letter file too large (max 2MB)');
                    this.value = '';
                    return;
                }
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('bankLetterStatus').innerHTML = `✅ ${file.name} (${(file.size / 1024).toFixed(0)}KB)`;
                    window.bankingLetterBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        // Bank Statement (PDF or Image)
        document.getElementById('bankStatementFile').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const isPDF = file.type === 'application/pdf';
                const isImage = file.type.startsWith('image/');
                
                if (!isPDF && !isImage) {
                    show('error', 'Bank statement must be a PDF or image file');
                    this.value = '';
                    return;
                }
                if (file.size > 2000000) {
                    show('error', 'Bank statement file too large (max 2MB)');
                    this.value = '';
                    return;
                }
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('bankStatementStatus').innerHTML = `✅ ${file.name} (${(file.size / 1024).toFixed(0)}KB)`;
                    window.bankStatementBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        document.getElementById('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!window.proofBase64) {
                show('error', 'Please upload proof of residence');
                return;
            }
            if (!window.idFrontBase64) {
                show('error', 'Please upload ID front side');
                return;
            }
            if (!window.idBackBase64) {
                show('error', 'Please upload ID back side');
                return;
            }
            if (!window.bankingLetterBase64) {
                show('error', 'Please upload banking letter (PDF required)');
                return;
            }
            if (!window.bankStatementBase64) {
                show('error', 'Please upload bank statement (PDF required)');
                return;
            }

            const body = {
                username: document.getElementById('uname').value,
                email: document.getElementById('email').value,
                password: document.getElementById('pass').value,
                phone: document.getElementById('phone').value,
                dob: document.getElementById('dob').value,
                employment: document.getElementById('emp').value,
                residence_proof: window.proofBase64,
                id_front: window.idFrontBase64,
                id_back: window.idBackBase64,
                banking_letter: window.bankingLetterBase64,
                bank_statement: window.bankStatementBase64
            };

            try {
                const res = await fetch('/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                
                if (res.ok) {
                    show('success', 'Account created! Redirecting to login...');
                    setTimeout(() => window.location.href = '/', 1500);
                } else {
                    show('error', data.error || 'Error');
                }
            } catch (err) {
                show('error', 'Connection failed');
            }
        });

        function show(type, text) {
            document.getElementById('msg').innerHTML = `<div class="${type}">${text}</div>`;
        }
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

BROWSE_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Browse - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
        </div>
        <div>
            <a href="/pawn-my-item">Pawn Item</a>
            <a href="/buy-items">Buy Items</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <h2 style="margin-bottom: 20px;">Shop Items</h2>
        
        <div class="carousel">
            <div class="carousel-inner">
                <div class="carousel-item active">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #000;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">💰 Quality Items</h2>
                            <p style="font-size: 16px;">Premium selection for you</p>
                        </div>
                    </div>
                </div>
                <div class="carousel-item">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #51cf66 0%, #40c057 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #fff;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">✅ Best Prices</h2>
                            <p style="font-size: 16px;">Affordable and verified items</p>
                        </div>
                    </div>
                </div>
                <div class="carousel-item">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #4c6ef5 0%, #5c7cfa 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #fff;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">🚀 Fast Delivery</h2>
                            <p style="font-size: 16px;">Quick and secure shipping</p>
                        </div>
                    </div>
                </div>
                <div class="carousel-item">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #f06595 0%, #f783ac 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #fff;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">🎁 Great Deals</h2>
                            <p style="font-size: 16px;">Special offers every week</p>
                        </div>
                    </div>
                </div>
            </div>
            <button class="carousel-nav carousel-prev" onclick="changeCarouselBrowse(-1)">❮</button>
            <button class="carousel-nav carousel-next" onclick="changeCarouselBrowse(1)">❯</button>
            <div class="carousel-controls">
                <div class="carousel-dot active" onclick="currentCarouselBrowse(0)"></div>
                <div class="carousel-dot" onclick="currentCarouselBrowse(1)"></div>
                <div class="carousel-dot" onclick="currentCarouselBrowse(2)"></div>
                <div class="carousel-dot" onclick="currentCarouselBrowse(3)"></div>
            </div>
        </div>
        
        <div class="filter">
            <label>Category: </label>
            <select onchange="load(this.value)">
                <option value="">All</option>
                <option value="Electronics">Electronics</option>
                <option value="Jewelry">Jewelry</option>
                <option value="Tools">Tools</option>
                <option value="Sports">Sports</option>
                <option value="Furniture">Furniture</option>
            </select>
        </div>
        <div class="grid" id="grid"></div>
    </div>

    <script>
        async function load(cat = '') {
            const url = cat ? `/api/sale-items?cat=${cat}` : '/api/sale-items';
            const res = await fetch(url);
            const items = await res.json();
            const grid = document.getElementById('grid');
            
            if (!items.length) {
                grid.innerHTML = '<div class="empty" style="grid-column: 1/-1;">No items</div>';
                return;
            }

            grid.innerHTML = items.map(i => `
                <div class="card">
                    <div class="card-img" style="background-size: cover; background-position: center;">
                        ${i.image_url ? `<img src="${i.image_url}" style="width: 100%; height: 100%; object-fit: cover;">` : getEmoji(i.category)}
                    </div>
                    <div class="card-body">
                        <div class="card-title">${i.name}</div>
                        <div class="card-cat">${i.category}</div>
                        ${i.type === 'pawn_item' ? `<div style="color: #ffc107; font-size: 11px; margin-bottom: 6px;">From: <strong>${i.username}</strong></div>` : ''}
                        <div class="card-desc">${i.desc || 'N/A'}</div>
                        <div class="card-price">$${i.price.toFixed(2)}</div>
                        <button class="btn" onclick="buy('${i.id}', '${i.type}')">Buy Now</button>
                    </div>
                </div>
            `).join('');
        }

        function getEmoji(cat) {
            const map = { 'Electronics': '📱', 'Jewelry': '💍', 'Tools': '🔧', 'Sports': '⚽', 'Furniture': '🛋️', 'User Pawn': '📦' };
            return map[cat] || '📦';
        }

        async function buy(id, type) {
            if (!confirm('Proceed with purchase?')) return;
            const res = await fetch(`/api/buy-item/${id}`, { method: 'POST' });
            const data = await res.json();
            
            if (res.ok) {
                alert(data.msg);
                load();
            } else {
                alert(data.error || 'Error');
            }
        }

        load();
        // Carousel variables
        let carouselIndexBrowse = 0;
        let carouselTimerBrowse;

        function changeCarouselBrowse(n) {
            showCarouselBrowse(carouselIndexBrowse += n);
            resetCarouselTimerBrowse();
        }

        function currentCarouselBrowse(n) {
            showCarouselBrowse(carouselIndexBrowse = n);
            resetCarouselTimerBrowse();
        }

        function showCarouselBrowse(n) {
            const items = document.querySelectorAll(".carousel-item");
            const dots = document.querySelectorAll(".carousel-dot");
            
            if (n >= items.length) { carouselIndexBrowse = 0; }
            if (n < 0) { carouselIndexBrowse = items.length - 1; }
            
            items.forEach((item, idx) => {
                item.classList.remove("active");
                if (idx === carouselIndexBrowse) {
                    item.classList.add("active");
                }
            });
            
            dots.forEach((dot, idx) => {
                dot.classList.remove("active");
                if (idx === carouselIndexBrowse) {
                    dot.classList.add("active");
                }
            });
        }

        function autoCarouselBrowse() {
            changeCarouselBrowse(1);
        }

        function resetCarouselTimerBrowse() {
            clearInterval(carouselTimerBrowse);
            carouselTimerBrowse = setInterval(autoCarouselBrowse, 5000);
        }

        // Initialize carousel
        window.addEventListener("load", () => {
            showCarouselBrowse(0);
            resetCarouselTimerBrowse();
        });

    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Dashboard - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="text-align: center;">
                <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
                <div style="font-size: 11px; color: #ffc107; font-weight: bold; margin-top: 3px;">online pawn shop</div>
            </div>
            <h1 style="font-size: 22px; margin: 0;">O.P.S</h1>
        </div>
        <div style="display: flex; gap: 10px;">
            <a href="/browse">Browse</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <div class="profile" style="padding: 8px; margin-bottom: 8px; max-width: 250px;">
            <div class="profile-pic" id="pic" style="font-size: 40px; width: 70px; height: 70px; line-height: 70px; margin: 0 auto 8px;">👤</div>
            <h2 style="font-size: 16px; margin-bottom: 6px;">{{ user.username }}</h2>
            <p style="font-size: 11px; margin-bottom: 3px;"><strong>Email:</strong> {{ user.email }}</p>
            <p style="font-size: 11px; margin-bottom: 3px;"><strong>Phone:</strong> {{ user.phone or 'N/A' }}</p>
            <p style="font-size: 11px; margin-bottom: 3px;"><strong>DOB:</strong> {{ user.dob or 'N/A' }}</p>
            <p style="font-size: 11px;"><strong>Employment:</strong> {{ user.employment or 'N/A' }}</p>
        </div>

        <div style="margin-top: 8px; display: flex; gap: 5px; border-bottom: 2px solid #333; margin-bottom: 12px; flex-wrap: wrap;">
            <button onclick="showTab('loans')" id="loansTab" style="padding: 8px 12px; background: #ffc107; color: #000; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; font-size: 11px;">My Loans</button>
            <button onclick="showTab('pawns')" id="pawnsTab" style="padding: 8px 12px; background: #666; color: #fff; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; font-size: 11px;">Pawn Submissions</button>
            <button onclick="showTab('purchases')" id="purchasesTab" style="padding: 8px 12px; background: #666; color: #fff; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; font-size: 11px;">Purchases</button>
            <button onclick="showTab('redeems')" id="redeemsTab" style="padding: 8px 12px; background: #666; color: #fff; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; font-size: 11px;">Redemptions</button>
            <button onclick="showTab('chat')" id="chatTab" style="padding: 8px 12px; background: #666; color: #fff; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; font-size: 11px;">💬 Chat Admin</button>
        </div>

        <div id="loansSection">
            <div class="loans">
                <h2>My Loans</h2>
                <div style="margin-bottom: 20px;">
                    <a href="/redeem" style="display: inline-block; padding: 10px 20px; background: #51cf66; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold;">+ Redeem Item</a>
                </div>
                <div id="loans"></div>
            </div>
        </div>

        <div id="pawnsSection" style="display: none;">
            <div class="loans">
                <h2>Pawn Submissions</h2>
                <div id="pawns"></div>
            </div>
        </div>

        <div id="redeemsSection" style="display: none;">
            <div class="loans">
                <h2>Redemptions</h2>
                <div id="redeems"></div>
            </div>
        </div>

        <div id="purchasesSection" style="display: none;">
            <div class="loans">
                <h2>My Purchases</h2>
                <div id="purchases"></div>
            </div>
        </div>

        <div id="chatSection" style="display: none;">
            <div class="loans" style="max-height: 600px; display: flex; flex-direction: column;">
                <h2>💬 Chat with Admin</h2>
                <div id="chatMessages" style="flex: 1; overflow-y: auto; background: #1a1a24; border: 1px solid #333; border-radius: 8px; padding: 12px; margin-bottom: 12px; max-height: 400px;">
                    <div class="empty">No messages yet</div>
                </div>
                <div style="display: flex; gap: 8px;">
                    <input type="text" id="chatInput" placeholder="Type a message..." style="flex: 1; padding: 8px; background: #222; color: #fff; border: 1px solid #444; border-radius: 4px; font-size: 12px;">
                    <button onclick="sendMessage()" style="padding: 8px 16px; background: #ffc107; color: #000; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">Send</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const pic = '{{ user.residence_proof or "" }}';
        if (pic && pic.length > 100) {
            document.getElementById('pic').innerHTML = `<img src="${pic}" style="width: 100%; height: 100%; object-fit: cover;">`;
        }

        async function loadChat() {
            const res = await fetch('/api/messages');
            const messages = await res.json();
            const div = document.getElementById('chatMessages');
            
            if (!messages.length) {
                div.innerHTML = '<div class="empty">No messages yet. Start a conversation!</div>';
                return;
            }

            div.innerHTML = messages.map(m => `
                <div style="margin-bottom: 12px; padding: 8px; background: ${m.sender === 'admin' ? '#2a4a8a' : '#1a3a2a'}; border-radius: 6px; border-left: 3px solid ${m.sender === 'admin' ? '#4a7aff' : '#51cf66'};">
                    <div style="font-size: 10px; color: #aaa; margin-bottom: 4px;"><strong>${m.sender === 'admin' ? '🔑 Admin' : '👤 You'}</strong> • ${new Date(m.created).toLocaleString()}</div>
                    <div style="color: #fff; font-size: 12px; word-wrap: break-word;">${m.text}</div>
                </div>
            `).join('');
            
            div.scrollTop = div.scrollHeight;
        }

        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const text = input.value.trim();
            
            if (!text) return;
            
            const res = await fetch('/api/send-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (res.ok) {
                input.value = '';
                loadChat();
            } else {
                alert('Failed to send message');
            }
        }

        async function loadPurchases() {
            const res = await fetch('/api/purchases');
            const purchases = await res.json();
            const div = document.getElementById('purchases');
            
            if (!purchases.length) {
                div.innerHTML = '<div class="empty">No purchases yet</div>';
                return;
            }

            div.innerHTML = purchases.map(p => `
                <div class="loan">
                    <div class="loan-head">
                        <span class="loan-title">${p.item_name}</span>
                        <span class="status status-${p.status}">${p.status.toUpperCase()}</span>
                    </div>
                    <div class="loan-info">
                        <div>
                            <span>Price</span>
                            <span class="info-val">$${p.price.toFixed(2)}</span>
                        </div>
                        <div>
                            <span>Purchased</span>
                            <span class="info-val">${new Date(p.created).toLocaleDateString()}</span>
                        </div>
                        <div>
                            <span>Status</span>
                            <span class="info-val">${p.status}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function load() {
            const res = await fetch('/api/loans');
            const loans = await res.json();
            const div = document.getElementById('loans');
            
            if (!loans.length) {
                div.innerHTML = '<div class="empty">No loans</div>';
                return;
            }

            div.innerHTML = loans.map(l => `
                <div class="loan">
                    <div class="loan-head">
                        <span class="loan-title">${l.item}</span>
                        <span class="status status-${l.status}">${l.status.toUpperCase()}</span>
                    </div>
                    <div class="loan-info">
                        <div>
                            <span>Loan Amount</span>
                            <span class="info-val">$${l.amount.toFixed(2)}</span>
                        </div>
                        <div>
                            <span>Total Due</span>
                            <span class="info-val">$${l.total_due.toFixed(2)}</span>
                        </div>
                        <div>
                            <span>Due Date</span>
                            <span class="info-val">${l.due}</span>
                        </div>
                        <div>
                            <span>Days Left</span>
                            <span class="info-val">${l.days_left}</span>
                        </div>
                    </div>
                    ${l.status === 'active' ? `<button class="repay" onclick="repay('${l.id}')">Repay</button>` : ''}
                </div>
            `).join('');
        }

        async function repay(id) {
            if (!confirm('Repay this loan?')) return;
            const res = await fetch(`/api/repay/${id}`, { method: 'POST' });
            if (res.ok) {
                alert('Loan repaid!');
                load();
            }
        }

        async function loadPawns() {
            const res = await fetch('/api/pawn-submissions');
            const pawns = await res.json();
            const div = document.getElementById('pawns');
            
            if (!pawns.length) {
                div.innerHTML = '<div class="empty">No pawn submissions</div>';
                return;
            }

            div.innerHTML = pawns.map(p => `
                <div class="loan">
                    <div class="loan-head">
                        <span class="loan-title">${p.name}</span>
                        <span class="status" style="background: ${p.status === 'pending' ? '#ff9800' : p.status === 'approved' ? '#51cf66' : '#ff6b6b'}; color: #fff;">${p.status.toUpperCase()}</span>
                    </div>
                    <div class="loan-info">
                        <div>
                            <span>Description</span>
                            <span class="info-val">${p.desc.substring(0, 30)}...</span>
                        </div>
                        <div>
                            <span>Requested Amount</span>
                            <span class="info-val">$${p.loan_amount.toFixed(2)}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function showTab(tab) {
            // Hide all sections
            document.getElementById('loansSection').style.display = 'none';
            document.getElementById('pawnsSection').style.display = 'none';
            document.getElementById('purchasesSection').style.display = 'none';
            document.getElementById('redeemsSection').style.display = 'none';
            document.getElementById('chatSection').style.display = 'none';
            
            // Reset all tabs
            document.getElementById('loansTab').style.background = '#666';
            document.getElementById('loansTab').style.color = '#fff';
            document.getElementById('pawnsTab').style.background = '#666';
            document.getElementById('pawnsTab').style.color = '#fff';
            document.getElementById('purchasesTab').style.background = '#666';
            document.getElementById('purchasesTab').style.color = '#fff';
            document.getElementById('redeemsTab').style.background = '#666';
            document.getElementById('redeemsTab').style.color = '#fff';
            document.getElementById('chatTab').style.background = '#666';
            document.getElementById('chatTab').style.color = '#fff';
            
            // Show selected section
            if (tab === 'loans') {
                document.getElementById('loansSection').style.display = 'block';
                document.getElementById('loansTab').style.background = '#ffc107';
                document.getElementById('loansTab').style.color = '#000';
                load();
            } else if (tab === 'pawns') {
                document.getElementById('pawnsSection').style.display = 'block';
                document.getElementById('pawnsTab').style.background = '#ffc107';
                document.getElementById('pawnsTab').style.color = '#000';
                loadPawns();
            } else if (tab === 'purchases') {
                document.getElementById('purchasesSection').style.display = 'block';
                document.getElementById('purchasesTab').style.background = '#ffc107';
                document.getElementById('purchasesTab').style.color = '#000';
                loadPurchases();
            } else if (tab === 'redeems') {
                document.getElementById('redeemsSection').style.display = 'block';
                document.getElementById('redeemsTab').style.background = '#ffc107';
                document.getElementById('redeemsTab').style.color = '#000';
                loadRedeems();
            } else if (tab === 'chat') {
                document.getElementById('chatSection').style.display = 'block';
                document.getElementById('chatTab').style.background = '#4a7aff';
                document.getElementById('chatTab').style.color = '#fff';
                loadChat();
            }
        }

        async function loadRedeems() {
            const res = await fetch('/api/redeem-requests');
            const redeems = await res.json();
            const div = document.getElementById('redeems');
            
            if (!redeems.length) {
                div.innerHTML = '<div class="empty">No redemptions</div>';
                return;
            }

            div.innerHTML = redeems.map(r => `
                <div class="loan">
                    <div class="loan-head">
                        <span class="loan-title">${r.item_name}</span>
                        <span class="status" style="background: ${r.status === 'pending' ? '#ff9800' : r.status === 'approved' ? '#51cf66' : '#ff6b6b'}; color: #fff;">${r.status.toUpperCase()}</span>
                    </div>
                    <div class="loan-info">
                        <div>
                            <span>Collection Method</span>
                            <span class="info-val">${r.collection_type === 'collection' ? 'Self Collection' : 'Home Delivery'}</span>
                        </div>
                        <div>
                            <span>Submitted</span>
                            <span class="info-val">${new Date(r.created).toLocaleDateString()}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        load();
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

ADMIN_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Admin - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="text-align: center;">
                <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
                <div style="font-size: 11px; color: #ffc107; font-weight: bold; margin-top: 3px;">online pawn shop</div>
            </div>
            <h1 style="font-size: 22px; margin: 0;">O.P.S Admin</h1>
        </div>
        <a href="/logout">Logout</a>
    </nav>
    <div class="container">
        <h2 style="margin-bottom: 20px;">Dashboard</h2>
        <div class="stats">
            <div class="stat">
                <div class="stat-num">{{ total_items }}</div>
                <div class="stat-label">Total Items</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ available }}</div>
                <div class="stat-label">Available</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ active_loans }}</div>
                <div class="stat-label">Active Loans</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ total_users }}</div>
                <div class="stat-label">Users</div>
            </div>
        </div>
        <div class="tabs">
            <button class="tab active" onclick="switchtab('add')">Add Item</button>
            <button class="tab" onclick="switchtab('items')">Items</button>
            <button class="tab" onclick="switchtab('users')">User Verification</button>
            <button class="tab" onclick="switchtab('pawns')">Pawn Requests</button>
            <button class="tab" onclick="switchtab('purchases')">Purchases</button>
            <button class="tab" onclick="switchtab('redeems')">Redemptions</button>
            <button class="tab" onclick="switchtab('chat')">💬 Admin Chat</button>
        </div>
        <div id="add" class="content active">
            <form onsubmit="additem(event)">
                <h3 style="margin-bottom: 20px;">Add New Item</h3>
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="name" required>
                </div>
                <div class="form-group">
                    <label>Category</label>
                    <select id="cat" required>
                        <option value="">Select</option>
                        <option value="Electronics">Electronics</option>
                        <option value="Jewelry">Jewelry</option>
                        <option value="Tools">Tools</option>
                        <option value="Sports">Sports</option>
                        <option value="Furniture">Furniture</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="desc" rows="3"></textarea>
                </div>
                <div class="form-group">
                    <label>Pawn Value ($)</label>
                    <input type="number" id="val" step="0.01" required>
                </div>
                <div class="form-group">
                    <label>Interest Rate (%)</label>
                    <input type="number" id="rate" value="15" required>
                </div>
                <div class="form-group">
                    <label>Loan Days</label>
                    <input type="number" id="days" value="30" required>
                </div>
                <div class="form-group">
                    <label>Item Image</label>
                    <div style="width: 100%; height: 150px; margin: 10px 0; background: #2a2a2a; border: 2px dashed #ffc107; border-radius: 5px; display: flex; align-items: center; justify-content: center;" id="imgPreview">📷</div>
                    <label for="itemImg" style="display: block; padding: 10px; background: #2a2a2a; border: 1px solid #ffc107; border-radius: 5px; text-align: center; cursor: pointer;">Upload Image</label>
                    <input type="file" id="itemImg" accept="image/*" style="display: none;">
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="forSale" style="width: auto; margin-right: 8px;">
                        Mark for Sale
                    </label>
                </div>
                <button type="submit">Add Item</button>
            </form>
        </div>
        <div id="items" class="content">
            <h3 style="margin-bottom: 20px;">Manage Items</h3>
            <div id="itemslist"></div>
        </div>
        <div id="users" class="content">
            <h3 style="margin-bottom: 20px;">User Verification</h3>
            <div id="userslist"></div>
        </div>
        <div id="pawns" class="content">
            <h3 style="margin-bottom: 20px;">Pawn Requests</h3>
            <div id="pawnslist"></div>
        </div>
        <div id="redeems" class="content">
            <h3 style="margin-bottom: 20px;">Redemption Requests</h3>
            <div id="redeemslist"></div>
        </div>
        <div id="purchases" class="content">
            <h3 style="margin-bottom: 20px;">Purchase Requests</h3>
            <div id="purchaseslist"></div>
        </div>
        <div id="chat" class="content">
            <h3 style="margin-bottom: 20px;">💬 Admin Chat Assistant</h3>
            <div style="display: flex; flex-direction: column; height: 600px; border: 1px solid rgba(255, 193, 7, 0.3); border-radius: 12px; background: rgba(42, 42, 62, 0.3); overflow: hidden;">
                <div id="chatMessages" style="flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px;">
                    <div style="display: flex; gap: 10px;">
                        <div style="background: rgba(255, 193, 7, 0.2); padding: 12px 16px; border-radius: 12px; max-width: 80%; border-left: 3px solid #ffc107;">
                            <p style="margin: 0; color: #ffc107; font-weight: 600; font-size: 12px;">Assistant</p>
                            <p style="margin: 5px 0 0 0; color: #e0e0e0;">Hi! 👋 I'm your Admin Chat Assistant. Ask me anything about your pawn shop—orders, inventory, user issues, or business insights. Type your question below!</p>
                        </div>
                    </div>
                </div>
                <div style="padding: 15px; border-top: 1px solid rgba(255, 193, 7, 0.2); display: flex; gap: 10px; background: rgba(42, 42, 62, 0.5);">
                    <input type="text" id="chatInput" placeholder="Ask me anything..." style="flex: 1; background: rgba(42, 42, 62, 0.8); border: 1px solid rgba(255, 193, 7, 0.3); padding: 12px 16px; border-radius: 8px; color: #e0e0e0;">
                    <button onclick="sendChat()" style="padding: 12px 24px; background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">Send</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        function switchtab(tab) {
            document.querySelectorAll('.content').forEach(x => x.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
            document.getElementById(tab).classList.add('active');
            event.target.classList.add('active');
            if (tab === 'items') loaditems();
            if (tab === 'users') loadUsers();
            if (tab === 'pawns') loadPawns();
            if (tab === 'purchases') loadPurchases();
            if (tab === 'redeems') loadAdminRedeems();
        }

        async function additem(e) {
            e.preventDefault();
            
            if (!window.itemImgBase64) {
                alert('Please upload an item image');
                return;
            }
            
            const data = {
                name: document.getElementById('name').value,
                category: document.getElementById('cat').value,
                desc: document.getElementById('desc').value,
                value: document.getElementById('val').value,
                rate: document.getElementById('rate').value,
                days: document.getElementById('days').value,
                image_url: window.itemImgBase64,
                for_sale: document.getElementById('forSale').checked
            };
            const res = await fetch('/api/admin/add-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (res.ok) {
                alert('Item added!');
                e.target.reset();
                document.getElementById('imgPreview').innerHTML = '📷';
                window.itemImgBase64 = null;
            }
        }

        // Handle item image upload
        document.getElementById('itemImg').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('imgPreview').innerHTML = `<img src="${ev.target.result}" style="width: 100%; height: 100%; object-fit: contain; border-radius: 5px;">`;
                    window.itemImgBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        async function loaditems() {
            const res = await fetch('/api/admin/items');
            const items = await res.json();
            const div = document.getElementById('itemslist');
            
            if (!items.length) {
                div.innerHTML = '<p>No items</p>';
                return;
            }

            div.innerHTML = `
                <table>
                    <thead>
                        <tr><th>Name</th><th>Category</th><th>Value</th><th>Status</th><th>Type</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        ${items.map(i => `
                            <tr>
                                <td>${i.name}</td>
                                <td>${i.cat}</td>
                                <td>$${i.val.toFixed(2)}</td>
                                <td>${i.status}</td>
                                <td>${i.type === 'pawn' ? `Pawn (${i.username})` : 'Admin'}</td>
                                <td><button class="del" onclick="delitem('${i.id}', '${i.type}')">Delete</button></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        async function loadUsers() {
            const res = await fetch('/api/admin/users');
            const users = await res.json();
            const div = document.getElementById('userslist');
            
            if (!users.length) {
                div.innerHTML = '<p>No users</p>';
                return;
            }

            div.innerHTML = users.map(u => `
                <div style="background: #1a1a1a; padding: 20px; border-radius: 5px; margin-bottom: 15px; ; ;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                        <div>
                            <strong style="color: #ffc107; font-size: 16px;">${u.username}</strong>
                            <div style="color: #999; font-size: 12px;">${u.email}</div>
                        </div>
                        <button onclick="viewUserDocs('${u.id}')" style="padding: 8px 16px; background: #ffc107; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">View Docs</button>
                    </div>
                    <div style="color: #ccc; font-size: 13px;">
                        <div><strong>Phone:</strong> ${u.phone || 'N/A'}</div>
                        <div><strong>DOB:</strong> ${u.dob || 'N/A'}</div>
                        <div><strong>Employment:</strong> ${u.employment || 'N/A'}</div>
                        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #444;">
                            📄 <strong>Documents:</strong>
                            <span style="color: ${u.has_residence_proof ? '#51cf66' : '#ff6b6b'}; margin-left: 5px;">Residence ${u.has_residence_proof ? '✓' : '✗'}</span>
                            <span style="color: ${u.has_id_front ? '#51cf66' : '#ff6b6b'}; margin-left: 5px;">ID Front ${u.has_id_front ? '✓' : '✗'}</span>
                            <span style="color: ${u.has_id_back ? '#51cf66' : '#ff6b6b'}; margin-left: 5px;">ID Back ${u.has_id_back ? '✓' : '✗'}</span>
                            <span style="color: ${u.has_banking_letter ? '#51cf66' : '#ff6b6b'}; margin-left: 5px;">Letter ${u.has_banking_letter ? '✓' : '✗'}</span>
                            <span style="color: ${u.has_bank_statement ? '#51cf66' : '#ff6b6b'}; margin-left: 5px;">Statement ${u.has_bank_statement ? '✓' : '✗'}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function viewUserDocs(uid) {
            const res = await fetch(`/api/admin/user-documents/${uid}`);
            const docs = await res.json();
            
            let html = `<div style="max-width: 900px; margin: 20px auto; background: #1a1a1a; padding: 25px; border-radius: 20px; ; ;">
                <h2 style="color: #ffc107; margin-bottom: 20px;">${docs.username}'s Documents</h2>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">`;
            
            const docs_list = [
                { name: 'Residence Proof', value: docs.residence_proof },
                { name: 'ID Front', value: docs.id_front },
                { name: 'ID Back', value: docs.id_back },
                { name: 'Banking Letter', value: docs.banking_letter },
                { name: 'Bank Statement', value: docs.bank_statement }
            ];
            
            docs_list.forEach(doc => {
                if (doc.value) {
                    html += `<div style="background: #2a2a2a; padding: 15px; border-radius: 5px; ; ;">
                        <h4 style="color: #ffc107; margin-bottom: 10px;">${doc.name}</h4>
                        ${doc.value.startsWith('data:image') ? 
                            `<img src="${doc.value}" style="width: 100%; max-height: 300px; border-radius: 5px; object-fit: contain;">` :
                            doc.value.startsWith('data:application/pdf') ?
                            `<div style="color: #999; padding: 40px; text-align: center; background: #1a1a1a; border-radius: 5px;">📄 PDF Document<br><a href="${doc.value}" download style="color: #ffc107; text-decoration: none; margin-top: 10px; display: inline-block;">Download PDF</a></div>` :
                            `<div style="color: #999;">Document not available</div>`
                        }
                    </div>`;
                }
            });
            
            html += `</div><button onclick="location.reload()" style="width: 100%; padding: 12px; margin-top: 20px; background: #666; color: #fff; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Close</button></div>`;
            
            document.body.innerHTML = html;
        }

        async function loadPawns() {
            const res = await fetch('/api/admin/pawn-submissions');
            const pawns = await res.json();
            const div = document.getElementById('pawnslist');
            
            if (!pawns.length) {
                div.innerHTML = '<p>No pawn submissions</p>';
                return;
            }

            div.innerHTML = pawns.map(p => `
                <div style="background: #2a2a2a; padding: 20px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid ${p.status === 'pending' ? '#ff9800' : p.status === 'approved' ? '#51cf66' : '#ff6b6b'};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                        <div>
                            <strong style="color: #ffc107;">${p.username}</strong> - ${p.item_name}
                        </div>
                        <span style="background: ${p.status === 'pending' ? '#ff9800' : p.status === 'approved' ? '#51cf66' : '#ff6b6b'}; color: #fff; padding: 5px 10px; border-radius: 3px; font-size: 11px;">${p.status.toUpperCase()}</span>
                    </div>
                    <div style="color: #ccc; font-size: 14px; margin-bottom: 12px;">
                        <p><strong>Description:</strong> ${p.desc}</p>
                        <p><strong>Requested Amount:</strong> $${p.loan_amount.toFixed(2)}</p>
                    </div>
                    ${p.status === 'pending' ? `
                        <div style="display: flex; gap: 10px;">
                            <button onclick="approvePawn('${p.user_id}', '${p.id}')" style="padding: 8px 16px; background: #51cf66; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Approve</button>
                            <button onclick="rejectPawn('${p.user_id}', '${p.id}')" style="padding: 8px 16px; background: #ff6b6b; color: #fff; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Reject</button>
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }

        async function loadPurchases() {
            const res = await fetch('/api/admin/purchases');
            const purchases = await res.json();
            const div = document.getElementById('purchaseslist');
            
            if (!purchases.length) {
                div.innerHTML = '<p>No purchase requests</p>';
                return;
            }

            div.innerHTML = purchases.map(p => `
                <div style="background: #2a2a2a; padding: 20px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid ${p.status === 'pending_approval' ? '#ff9800' : p.status === 'approved' ? '#51cf66' : '#ff6b6b'};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                        <div>
                            <strong style="color: #ffc107;">${p.username}</strong> - ${p.item_name}
                        </div>
                        <span style="background: ${p.status === 'pending_approval' ? '#ff9800' : p.status === 'approved' ? '#51cf66' : '#ff6b6b'}; color: #fff; padding: 5px 10px; border-radius: 3px; font-size: 11px;">${p.status.toUpperCase()}</span>
                    </div>
                    <div style="color: #ccc; font-size: 14px; margin-bottom: 12px;">
                        <p><strong>Price:</strong> $${p.price.toFixed(2)}</p>
                        <p><strong>Requested:</strong> ${new Date(p.created).toLocaleDateString()}</p>
                    </div>
                    ${p.status === 'pending_approval' ? `
                        <div style="display: flex; gap: 10px;">
                            <button onclick="approvePurchase('${p.user_id}', '${p.id}')" style="padding: 8px 16px; background: #51cf66; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Approve</button>
                            <button onclick="rejectPurchase('${p.user_id}', '${p.id}')" style="padding: 8px 16px; background: #ff6b6b; color: #fff; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Reject</button>
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }

        async function approvePurchase(uid, pid) {
            if (!confirm('Approve this purchase?')) return;
            const res = await fetch(`/api/admin/approve-purchase/${uid}/${pid}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                alert(data.msg);
                loadPurchases();
            } else {
                alert(data.error || 'Error');
            }
        }

        async function rejectPurchase(uid, pid) {
            const reason = prompt('Reason for rejection:');
            if (!reason) return;
            
            const res = await fetch(`/api/admin/reject-purchase/${uid}/${pid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            });
            const data = await res.json();
            if (res.ok) {
                alert(data.msg);
                loadPurchases();
            } else {
                alert(data.error || 'Error');
            }
        }

        async function approvePawn(uid, pid) {
            if (!confirm('Approve this pawn request?')) return;
            const res = await fetch(`/api/admin/approve-pawn/${uid}/${pid}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                alert(data.msg);
                loadPawns();
            } else {
                alert(data.error || 'Error');
            }
        }

        async function rejectPawn(uid, pid) {
            const reason = prompt('Reason for rejection:');
            if (!reason) return;
            
            const res = await fetch(`/api/admin/reject-pawn/${uid}/${pid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            });
            const data = await res.json();
            if (res.ok) {
                alert(data.msg);
                loadPawns();
            } else {
                alert(data.error || 'Error');
            }
        }

        async function delitem(id, type) {
            if (!confirm('Delete?')) return;
            const endpoint = type === 'pawn' ? `/api/admin/delete-pawn/${id}` : `/api/admin/delete-item/${id}`;
            const res = await fetch(endpoint, { method: 'DELETE' });
            if (res.ok) {
                alert('Deleted!');
                loaditems();
            } else {
                alert('Error deleting item');
            }
        }

        // Chat Assistant Functions
        async function sendChat() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Add user message to chat
            addChatMessage(message, 'user');
            input.value = '';
            
            // Show typing indicator
            addChatMessage('Typing...', 'assistant-typing');
            
            try {
                const res = await fetch('/api/admin/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await res.json();
                
                // Remove typing indicator
                const typingMsg = document.querySelector('[data-typing="true"]');
                if (typingMsg) typingMsg.remove();
                
                // Add assistant response
                if (data.response) {
                    addChatMessage(data.response, 'assistant');
                } else {
                    addChatMessage('Sorry, I had trouble processing that. Try again!', 'assistant');
                }
            } catch (error) {
                console.error('Chat error:', error);
                // Remove typing indicator
                const typingMsg = document.querySelector('[data-typing="true"]');
                if (typingMsg) typingMsg.remove();
                addChatMessage('Connection error. Please try again.', 'assistant');
            }
        }
        
        function addChatMessage(text, sender) {
            const messagesContainer = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            
            if (sender === 'user') {
                messageDiv.style.cssText = 'display: flex; justify-content: flex-end;';
                messageDiv.innerHTML = `<div style="background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 16px; border-radius: 12px; max-width: 80%; text-align: right; font-weight: 500;">${text}</div>`;
            } else if (sender === 'assistant-typing') {
                messageDiv.setAttribute('data-typing', 'true');
                messageDiv.style.cssText = 'display: flex; gap: 10px;';
                messageDiv.innerHTML = `<div style="background: rgba(255, 193, 7, 0.2); padding: 12px 16px; border-radius: 12px; border-left: 3px solid #ffc107; color: #ffc107;">
                    <div style="display: flex; gap: 4px;">
                        <span style="animation: bounce 0.6s infinite;">•</span>
                        <span style="animation: bounce 0.6s infinite 0.1s;">•</span>
                        <span style="animation: bounce 0.6s infinite 0.2s;">•</span>
                    </div>
                </div>`;
            } else {
                messageDiv.style.cssText = 'display: flex; gap: 10px;';
                messageDiv.innerHTML = `<div style="background: rgba(255, 193, 7, 0.2); padding: 12px 16px; border-radius: 12px; max-width: 80%; border-left: 3px solid #ffc107;">
                    <p style="margin: 0; color: #ffc107; font-weight: 600; font-size: 12px;">Assistant</p>
                    <p style="margin: 5px 0 0 0; color: #e0e0e0; white-space: pre-wrap;">${text}</p>
                </div>`;
            }
            
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        // Allow Enter key to send chat
        document.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && document.getElementById('chatInput') === document.activeElement) {
                sendChat();
            }
        });
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

# ============ REDEEM ITEM PAGE ============

REDEEM_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Redeem Item</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
        </div>
        <div>
            <a href="/browse">Browse</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <h2>Redeem Your Item</h2>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('redeem')">Submit Redeem</button>
            <button class="tab" onclick="showTab('requests')">My Requests</button>
        </div>

        <div id="redeem" class="tab-content active">
            <div id="msg" class="msg"></div>
            <form id="form">
                <div class="form-group">
                    <label>Select Item (Active Loan)</label>
                    <select id="loanSelect" required>
                        <option value="">Loading your loans...</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Proof of Payment</label>
                    <div class="preview" id="paymentPreview">📄</div>
                    <label for="paymentProof" class="file-label">Upload Proof (Receipt/Invoice/Screenshot)</label>
                    <input type="file" id="paymentProof" accept="image/*,.pdf">
                </div>
                <div class="form-group">
                    <label>Collection Method</label>
                    <select id="collectionType" required>
                        <option value="">Select</option>
                        <option value="collection">Pick Up / Self Collection</option>
                        <option value="delivery">Home Delivery</option>
                    </select>
                </div>
                <button type="submit" style="width: 100%; margin-top: 20px;">Submit Redeem Request</button>
            </form>
        </div>

        <div id="requests" class="tab-content">
            <div id="requestsList"></div>
        </div>
    </div>

    <script>
        async function loadLoans() {
            const res = await fetch('/api/active-loans');
            const loans = await res.json();
            const select = document.getElementById('loanSelect');
            
            if (!loans.length) {
                select.innerHTML = '<option value="">No active loans to redeem</option>';
                return;
            }

            select.innerHTML = loans.map(l => `
                <option value="${l.id}">
                    ${l.item_name} - $${l.amount.toFixed(2)} (Due: ${new Date(l.due).toLocaleDateString()})
                </option>
            `).join('');
        }

        document.getElementById('paymentProof').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                if (file.size > 2000000) {
                    show('error', 'File too large (max 2MB)');
                    this.value = '';
                    return;
                }
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('paymentPreview').innerHTML = `<img src="${ev.target.result}">`;
                    window.paymentProofBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        document.getElementById('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!window.paymentProofBase64) {
                show('error', 'Please upload proof of payment');
                return;
            }

            const body = {
                loan_id: document.getElementById('loanSelect').value,
                payment_proof: window.paymentProofBase64,
                collection_type: document.getElementById('collectionType').value
            };

            try {
                const res = await fetch('/api/submit-redeem', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                
                if (res.ok) {
                    show('success', data.msg);
                    setTimeout(() => loadRequests(), 1500);
                    document.getElementById('form').reset();
                } else {
                    show('error', data.error || 'Error');
                }
            } catch (err) {
                show('error', 'Connection failed');
            }
        });

        async function loadRequests() {
            const res = await fetch('/api/redeem-requests');
            const requests = await res.json();
            const div = document.getElementById('requestsList');
            
            if (!requests.length) {
                div.innerHTML = '<div class="empty">No redeem requests</div>';
                return;
            }

            div.innerHTML = requests.map(r => `
                <div class="loan-card">
                    <h4>${r.item_name}</h4>
                    <div class="loan-info">
                        <div><strong>Collection:</strong> ${r.collection_type === 'collection' ? 'Pick Up' : 'Home Delivery'}</div>
                        <div><strong>Status:</strong> <span style="background: ${r.status === 'pending' ? '#ff9800' : r.status === 'approved' ? '#51cf66' : '#ff6b6b'}; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">${r.status.toUpperCase()}</span></div>
                        <div><strong>Submitted:</strong> ${new Date(r.created).toLocaleDateString()}</div>
                    </div>
                </div>
            `).join('');
        }

        function showTab(tab) {
            document.querySelectorAll('.tab-content').forEach(x => x.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
            document.getElementById(tab).classList.add('active');
            event.target.classList.add('active');
            
            if (tab === 'requests') loadRequests();
            if (tab === 'redeem') loadLoans();
        }

        function show(type, text) {
            const el = document.getElementById('msg');
            el.className = 'msg ' + type;
            el.textContent = text;
        }

        loadLoans();
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

# ============ PAWN YOUR ITEM PAGE ============

PAWN_ITEM_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Pawn Your Item</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
        </div>
        <div>
            <a href="/browse">Browse</a>
            <a href="/buy-items">Buy Items</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <h2>Pawn Your Item</h2>
        <div id="msg" class="msg"></div>
        <form id="form">
            <div class="form-group">
                <label>Item Name</label>
                <input type="text" id="itemName" required>
            </div>
            <div class="form-group">
                <label>Item Description</label>
                <textarea id="itemDesc" rows="3" required></textarea>
            </div>
            <div class="form-group">
                <label>Requested Loan Amount ($)</label>
                <input type="number" id="loanAmount" step="0.01" required>
            </div>
            <div class="form-group">
                <label>Item Picture</label>
                <div class="preview" id="picPreview">📷</div>
                <label for="itemPic" class="file-label">Upload Item Photo</label>
                <input type="file" id="itemPic" accept="image/*">
            </div>
            <div class="form-group">
                <label>Proof of Ownership</label>
                <div class="preview" id="ownerPreview">📄</div>
                <label for="ownerProof" class="file-label">Upload Proof (Receipt/Invoice)</label>
                <input type="file" id="ownerProof" accept="image/*">
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="affidavit" required style="width: auto; margin-right: 8px;">
                    I confirm that all information provided is true and I own this item
                </label>
            </div>
            <button type="submit">Submit Pawn Request</button>
        </form>
    </div>

    <script>
        document.getElementById('itemPic').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('picPreview').innerHTML = `<img src="${ev.target.result}">`;
                    window.itemPicBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        document.getElementById('ownerProof').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('ownerPreview').innerHTML = `<img src="${ev.target.result}">`;
                    window.ownerProofBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        document.getElementById('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!window.itemPicBase64) {
                show('error', 'Please upload item picture');
                return;
            }
            if (!window.ownerProofBase64) {
                show('error', 'Please upload proof of ownership');
                return;
            }

            const body = {
                item_name: document.getElementById('itemName').value,
                item_desc: document.getElementById('itemDesc').value,
                loan_request: document.getElementById('loanAmount').value,
                item_picture: window.itemPicBase64,
                proof_ownership: window.ownerProofBase64,
                affidavit: document.getElementById('affidavit').checked ? '1' : '0'
            };

            try {
                const res = await fetch('/api/submit-pawn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                
                if (res.ok) {
                    show('success', data.msg);
                    setTimeout(() => window.location.href = '/dashboard', 1500);
                } else {
                    show('error', data.error || 'Error');
                }
            } catch (err) {
                show('error', 'Connection failed');
            }
        });

        function show(type, text) {
            const el = document.getElementById('msg');
            el.className = 'msg ' + type;
            el.textContent = text;
        }
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

# ============ BUY ITEMS PAGE ============

BUY_ITEMS_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Buy Items</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
        </div>
        <div>
            <a href="/browse">Browse Pawn</a>
            <a href="/pawn-my-item">Pawn Item</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <h2>Items For Sale</h2>
        
        <div class="carousel">
            <div class="carousel-inner">
                <div class="carousel-item active">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #000;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">💎 Premium Items</h2>
                            <p style="font-size: 16px;">Handpicked for quality</p>
                        </div>
                    </div>
                </div>
                <div class="carousel-item">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #51cf66 0%, #40c057 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #fff;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">💳 Easy Payment</h2>
                            <p style="font-size: 16px;">Multiple payment options</p>
                        </div>
                    </div>
                </div>
                <div class="carousel-item">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #4c6ef5 0%, #5c7cfa 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #fff;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">🛡️ Protected Buyer</h2>
                            <p style="font-size: 16px;">100% money-back guarantee</p>
                        </div>
                    </div>
                </div>
                <div class="carousel-item">
                    <div style="width: 100%; height: 100%; background: linear-gradient(135deg, #f06595 0%, #f783ac 100%); display: flex; align-items: center; justify-content: center;">
                        <div style="text-align: center; color: #fff;">
                            <h2 style="font-size: 36px; margin-bottom: 10px;">⭐ Verified Sellers</h2>
                            <p style="font-size: 16px;">Trusted and authentic</p>
                        </div>
                    </div>
                </div>
            </div>
            <button class="carousel-nav carousel-prev" onclick="changeCarouselBuy(-1)">❮</button>
            <button class="carousel-nav carousel-next" onclick="changeCarouselBuy(1)">❯</button>
            <div class="carousel-controls">
                <div class="carousel-dot active" onclick="currentCarouselBuy(0)"></div>
                <div class="carousel-dot" onclick="currentCarouselBuy(1)"></div>
                <div class="carousel-dot" onclick="currentCarouselBuy(2)"></div>
                <div class="carousel-dot" onclick="currentCarouselBuy(3)"></div>
            </div>
        </div>
        
        <div class="grid" id="grid"></div>
    </div>

    <script>
        async function load() {
            const res = await fetch('/api/sale-items');
            const items = await res.json();
            const grid = document.getElementById('grid');
            
            if (!items.length) {
                grid.innerHTML = '<div class="empty" style="grid-column: 1/-1;">No items available for sale</div>';
                return;
            }

            grid.innerHTML = items.map(i => `
                <div class="card">
                    <div class="card-img" style="background-size: cover; background-position: center; overflow: hidden;">
                        ${i.image_url ? `<img src="${i.image_url}" style="width: 100%; height: 100%; object-fit: cover;">` : getEmoji(i.category)}
                    </div>
                    <div class="card-body">
                        <div class="card-title">${i.name}</div>
                        <div class="card-cat">${i.category}</div>
                        ${i.type === 'pawn_item' ? `<div style="color: #ffc107; font-size: 11px; margin-bottom: 6px;">From: <strong>${i.username}</strong></div>` : ''}
                        <div class="card-desc">${i.desc || 'N/A'}</div>
                        <div class="card-price">$${i.price.toFixed(2)}</div>
                        <button class="btn" onclick="buy('${i.id}', '${i.type}')">Buy Now</button>
                    </div>
                </div>
            `).join('');
        }

        function getEmoji(cat) {
            const map = { 'Electronics': '📱', 'Jewelry': '💍', 'Tools': '🔧', 'Sports': '⚽', 'Furniture': '🛋️' };
            return map[cat] || '📦';
        }

        async function buy(id, type) {
            if (!confirm('Proceed with purchase?')) return;
            const res = await fetch(`/api/buy-item/${id}`, { method: 'POST' });
            const data = await res.json();
            
            if (res.ok) {
                alert(data.msg);
                load();
            } else {
                alert(data.error || 'Error');
            }
        }

        // Carousel variables
        let carouselIndexBuy = 0;
        let carouselTimerBuy;

        function changeCarouselBuy(n) {
            showCarouselBuy(carouselIndexBuy += n);
            resetCarouselTimerBuy();
        }

        function currentCarouselBuy(n) {
            showCarouselBuy(carouselIndexBuy = n);
            resetCarouselTimerBuy();
        }

        function showCarouselBuy(n) {
            const items = document.querySelectorAll(".carousel-item");
            const dots = document.querySelectorAll(".carousel-dot");
            
            if (n >= items.length) { carouselIndexBuy = 0; }
            if (n < 0) { carouselIndexBuy = items.length - 1; }
            
            items.forEach((item, idx) => {
                item.classList.remove("active");
                if (idx === carouselIndexBuy) {
                    item.classList.add("active");
                }
            });
            
            dots.forEach((dot, idx) => {
                dot.classList.remove("active");
                if (idx === carouselIndexBuy) {
                    dot.classList.add("active");
                }
            });
        }

        function autoCarouselBuy() {
            changeCarouselBuy(1);
        }

        function resetCarouselTimerBuy() {
            clearInterval(carouselTimerBuy);
            carouselTimerBuy = setInterval(autoCarouselBuy, 5000);
        }

        // Initialize carousel
        window.addEventListener("load", () => {
            showCarouselBuy(0);
            resetCarouselTimerBuy();
        });

        load();
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

# ============ REDEEM PAGE ============

REDEEM_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0, viewport-fit=cover">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.compat.css" integrity="sha512-gFn7XRm5v3GlgOwAQ80SXDT8pyg6uaV9JbW2OkNx5Im2jR8zx2X/3DbHymcZnUraU+klZjRJqNfNkFN7SyR3fg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <title>Redeem Item</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInLeft { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 5px rgba(255, 193, 7, 0.3); } 50% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.6); } }
        @keyframes smoothSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smoothFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInFromLeft { from { opacity: 0; transform: translateX(-50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes slideInFromRight { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        @keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 10px rgba(255, 193, 7, 0.3), 0 4px 30px rgba(0, 0, 0, 0.1); } 50% { box-shadow: 0 0 20px rgba(255, 193, 7, 0.6), 0 8px 40px rgba(0, 0, 0, 0.2); } }
        @keyframes bounce-top { from { opacity: 0; transform: translateY(40px); animation-timing-function: ease-out; } to { opacity: 1; transform: translateY(0); } }
        @keyframes text-pop-up-top { 0% { opacity: 0; transform: translateY(40px) scaleY(0.8); } 100% { opacity: 1; transform: translateY(0) scaleY(1); } }
        .text-pop-up-top { -webkit-animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        .bounce-top { -webkit-animation: bounce-top 0.9s both; animation: bounce-top 0.9s both; }
        body { font-size: 16px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #0a0a12 0%, #15151f 100%); color: #e0e0e0; min-height: 100vh; animation: fadeIn 0.6s ease-in; }
        nav { background: rgba(15, 15, 25, 0.95); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a2e; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        nav h1 { font-size: 20px; color: #ffc107; font-weight: 600; letter-spacing: 1px; animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        nav a { color: #e0e0e0; text-decoration: none; margin-left: 5px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; }
        nav a:hover { color: #ffc107; background: rgba(255, 193, 7, 0.1); transform: translateY(-2px); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; animation: fadeIn 0.8s ease-in 0.2s backwards; }
        h1 { color: #ffc107; font-size: 36px; margin-bottom: 30px; text-align: center; text-shadow: 0 2px 10px rgba(255, 193, 7, 0.2); animation: bounce-top 0.9s both; }
        h2 { color: #ffc107; margin-bottom: 25px; font-size: 24px; border-bottom: 2px solid rgba(255, 193, 7, 0.3); padding-bottom: 10px; animation: bounce-top 0.9s both; }
        h3 { color: #ffc107; margin-bottom: 15px; font-size: 18px; }
        h3 { animation: bounce-top 0.9s both; }
        label { display: block; margin-bottom: 8px; color: #b0b0b0; font-weight: 500; font-size: 14px; }
        input, select, textarea { width: 100%; padding: 12px 14px; background: rgba(42, 42, 62, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; margin-bottom: 15px; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; background: rgba(42, 42, 62, 0.9); box-shadow: 0 0 15px rgba(255, 193, 7, 0.2); }
        button { padding: 12px 24px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); animation: text-pop-up-top 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; position: relative; overflow: hidden; }
        button::before { content: ''; position: absolute; top: 50%; left: 50%; width: 0; height: 0; background: rgba(255, 255, 255, 0.3); border-radius: 50%; transform: translate(-50%, -50%); transition: width 0.6s, height 0.6s; }
        button:hover { animation: float 2s ease-in-out infinite; transform: translateY(-3px); box-shadow: 0 10px 25px rgba(255, 193, 7, 0.3); }
        button:hover::before { width: 300px; height: 300px; }
        button:active { transform: translateY(-1px); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(42, 42, 62, 0.4); border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2); animation: fadeIn 0.8s ease-in; }
        table th { background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; padding: 15px; text-align: left; font-weight: 600; }
        table td { padding: 12px 15px; border-bottom: 1px solid rgba(255, 193, 7, 0.1); }
        table tr { transition: all 0.3s ease; }
        table tr:hover { background: rgba(255, 193, 7, 0.05); transform: scale(1.01); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; margin-top: 25px; animation: fadeIn 0.8s ease-in; }
        .card { background: rgba(42, 42, 62, 0.5); padding: 25px; border-radius: 12px; border: 1px solid rgba(255, 193, 7, 0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter: blur(10px); animation: smoothSlideIn 0.6s ease-out; }
        .glass-card { background: rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 25px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: fadeIn 0.6s ease-in; }
        .card:hover { background: rgba(42, 42, 62, 0.8); border-color: #ffc107; box-shadow: 0 15px 40px rgba(255, 193, 7, 0.15); animation: glow-pulse 2s ease-in-out infinite; transform: translateY(-8px) scale(1.02); }
        .glass-card:hover { background: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
        .glass-effect { background: rgba(14, 39, 86, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px); border: 1px solid rgba(14, 39, 86, 0.3); }
        .glass-effect:hover { background: rgba(14, 39, 86, 0.05); box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15); border-color: rgba(14, 39, 86, 0.5); transform: translateY(-4px); }
        .card h3 { margin-bottom: 15px; }
        .card p { color: #b0b0b0; line-height: 1.8; }
        .form-group { margin-bottom: 20px; animation: fadeIn 0.6s ease-in; }
        .btn-primary { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 15px rgba(255, 193, 7, 0.2); }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.4); }
        .btn-secondary { background: rgba(100, 100, 130, 0.6); color: #e0e0e0; padding: 10px 20px; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; }
        .btn-secondary:hover { background: rgba(150, 150, 180, 0.8); border-color: #ffc107; }
        .status { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; animation: pulse 2s infinite; }
        .status-active { background: rgba(81, 207, 102, 0.2); color: #51cf66; border: 1px solid #51cf66; }
        .status-pending { background: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
        .status-rejected { background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid #ff6b6b; }
        .alert { padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid; animation: slideInRight 0.5s ease-out; backdrop-filter: blur(10px); }
        .alert-error { background: rgba(255, 107, 107, 0.1); border-left-color: #ff6b6b; color: #ff6b6b; }
        .alert-success { background: rgba(81, 207, 102, 0.1); border-left-color: #51cf66; color: #51cf66; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-button { padding: 10px 20px; background: rgba(100, 100, 130, 0.6); color: #e0e0e0; border: 1px solid rgba(255, 193, 7, 0.2); border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease; font-size: 13px; white-space: nowrap; }
        .tab-button.active { background: linear-gradient(135deg, #ffc107, #ffb600); color: #000; border-color: #ffc107; }
        .tab-button:hover { border-color: #ffc107; color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        body { font-size: 14px; -webkit-text-size-adjust: 100%; -moz-text-size-adjust: 100%; text-size-adjust: 100%; touch-action: manipulation; }
        footer { text-align: center; padding: 30px 20px; background: rgba(15, 15, 25, 0.95); border-top: 1px solid rgba(255, 193, 7, 0.2); margin-top: 60px; color: #999; font-size: 12px; backdrop-filter: blur(10px); }
        .hero { background: linear-gradient(135deg, rgba(255, 193, 7, 0.05) 0%, rgba(255, 193, 7, 0.02) 100%); padding: 60px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; animation: fadeIn 0.8s ease-in; }
        .cta { display: inline-block; padding: 16px 50px; background: linear-gradient(135deg, #ffc107 0%, #ffb600 100%); color: #000; text-decoration: none; border-radius: 50px; font-weight: 700; font-size: 16px; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3); position: relative; overflow: hidden; letter-spacing: 0.5px; }
        .cta:hover { transform: translateY(-4px); box-shadow: 0 12px 35px rgba(255, 193, 7, 0.5); letter-spacing: 1px; }
        p { animation: bounce-top 0.9s both 0.1s backwards; }
        .carousel { position: relative; width: 100%; max-width: 800px; margin: 40px auto; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(255, 193, 7, 0.2); animation: smoothSlideIn 0.8s ease-out; }
        .carousel-inner { position: relative; width: 100%; height: 250px; }
        .carousel-item { position: absolute; width: 100%; height: 100%; opacity: 0; transition: opacity 0.8s ease-in-out; }
        .carousel-item.active { opacity: 1; }
        .carousel-item img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-item-content { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent); color: #fff; padding: 30px; }
        .carousel-item-content h3 { color: #ffc107; font-size: 24px; margin-bottom: 10px; }
        h3 { animation: bounce-top 0.9s both; }
        .carousel-item-content p { font-size: 14px; color: #ddd; }
        .carousel-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10; }
        .carousel-dot { width: 12px; height: 12px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); cursor: pointer; transition: all 0.3s ease; border: 2px solid transparent; }
        .carousel-dot.active { background: #ffc107; width: 30px; border-radius: 6px; }
        .carousel-dot:hover { background: rgba(255, 193, 7, 0.8); transform: scale(1.2); }
        .carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 50px; height: 50px; background: rgba(255, 193, 7, 0.8); color: #000; border: none; font-size: 24px; cursor: pointer; border-radius: 50%; transition: all 0.3s ease; z-index: 10; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .carousel-nav:hover { background: #ffc107; transform: translateY(-50%) scale(1.1); }
        .carousel-prev { left: 20px; }
        .carousel-next { right: 20px; }
    </style>
</head>
<body>
    <nav>
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="https://i.postimg.cc/mkYS9JnD/large.png" style="height: 80px; width: auto; border-radius: 5px;">
        </div>
        <div>
            <a href="/browse">Browse</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <h2>Redeem Your Item</h2>
        <div id="msg" class="msg"></div>
        
        <div class="info-box">
            <p><strong>Instructions:</strong> Select your loan, upload proof of payment, and choose collection method.</p>
        </div>

        <form id="form">
            <div class="form-group">
                <label>Select Loan to Redeem</label>
                <select id="loanId" required style="cursor: pointer;">
                    <option value="">Loading loans...</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>Proof of Payment (Receipt/Invoice)</label>
                <div class="preview" id="paymentPreview">📄</div>
                <label for="paymentProof" class="file-label">Upload Proof (PDF or Image)</label>
                <input type="file" id="paymentProof" accept=".pdf,image/*">
            </div>

            <div class="form-group">
                <label>Collection Method</label>
                <select id="method" required style="cursor: pointer;">
                    <option value="">Select method</option>
                    <option value="collection">Self Collection</option>
                    <option value="delivery">Home Delivery</option>
                </select>
            </div>

            <button type="submit">Submit Redemption Request</button>
        </form>
    </div>

    <script>
        async function loadLoans() {
            const res = await fetch('/api/loans');
            const loans = await res.json();
            const select = document.getElementById('loanId');
            
            const activeLoans = loans.filter(l => l.status === 'active');
            
            if (!activeLoans.length) {
                select.innerHTML = '<option value="">No active loans to redeem</option>';
                return;
            }

            select.innerHTML = activeLoans.map(l => 
                `<option value="${l.id}">${l.item} - $${l.amount.toFixed(2)} (Due: ${l.due})</option>`
            ).join('');
        }

        document.getElementById('paymentProof').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const isPDF = file.type === 'application/pdf';
                const isImage = file.type.startsWith('image/');
                
                if (!isPDF && !isImage) {
                    show('error', 'Must be PDF or image');
                    this.value = '';
                    return;
                }
                if (file.size > 2000000) {
                    show('error', 'File too large (max 2MB)');
                    this.value = '';
                    return;
                }
                
                const reader = new FileReader();
                reader.onload = function(ev) {
                    if (isImage) {
                        document.getElementById('paymentPreview').innerHTML = `<img src="${ev.target.result}">`;
                    } else {
                        document.getElementById('paymentPreview').innerHTML = `✅ ${file.name}`;
                    }
                    window.paymentProofBase64 = ev.target.result;
                };
                reader.readAsDataURL(file);
            }
        });

        document.getElementById('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!window.paymentProofBase64) {
                show('error', 'Please upload proof of payment');
                return;
            }

            const body = {
                loan_id: document.getElementById('loanId').value,
                payment_proof: window.paymentProofBase64,
                collection_type: document.getElementById('method').value
            };

            try {
                const res = await fetch('/api/submit-redeem', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                
                if (res.ok) {
                    show('success', data.msg);
                    setTimeout(() => window.location.href = '/dashboard', 1500);
                } else {
                    show('error', data.error || 'Error');
                }
            } catch (err) {
                show('error', 'Connection failed');
            }
        });

        function show(type, text) {
            const el = document.getElementById('msg');
            el.className = 'msg ' + type;
            el.textContent = text;
        }

        loadLoans();
    </script>
    <footer style="text-align: center; padding: 20px; background: #1a1a1a; border-top: 1px solid #333; margin-top: 40px; color: #999; font-size: 12px;"><p>© 2026 O.P.S Online Pawn Shop - A subsidiary of Africa Micro Group by Keorate Lekolwane (MD - Tswelelo Lekolwane Group Adviser). All rights reserved.</p><p>Designed by Bee</p></footer></body>
</html>
'''

# ============ INIT & RUN ============

def init():
    # Initialize database
    init_db()
    
    # Load existing data from database
    try:
        load_data()
    except Exception as e:
        print(f"Error loading data: {e}")
    
    # Admin user - ALWAYS ensure admin exists
    admin_exists = any(u.get('username') == 'admin' for u in users_db.values())
    
    if not admin_exists:
        try:
            aid = gen_id()
            users_db[aid] = {
                'id': aid, 'username': 'admin', 'email': 'admin@shop.com',
                'password_hash': 'pbkdf2:sha256:1000000$8oQcBveoiBLZh6KY$7a1d730b7dafee11463aa588d09258e1175111bb1b0703aae598bed26f290a03',
                'phone': '555-0000', 'dob': '1990-01-01', 'employment': 'employed',
                'residence_proof': '', 'id_front': '', 'id_back': '',
                'banking_letter': '', 'bank_statement': '',
                'is_admin': True, 'created': datetime.now().isoformat(),
                'pawn_submissions': {}, 'redeem_requests': {}, 'purchases': {}
            }
            save_data()
            print("✓ Admin user initialized: admin / admin123")
        except Exception as e:
            print(f"Error creating admin: {e}")

if __name__ == '__main__':
    try:
        init()
    except Exception as e:
        print(f"Init error: {e}")
    app.run(debug=False, host='0.0.0.0', port=5000)
