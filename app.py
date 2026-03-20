from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from uuid import uuid4
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pawn_shop_secret_key_2024'

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
        password = data.get('password')
        phone = data.get('phone', '').strip()
        dob = data.get('dob')
        employment = data.get('employment')
        residence_proof = data.get('residence_proof', '')
        
        # Validate
        if not all([username, email, password, dob, employment, residence_proof]):
            return jsonify({'error': 'All fields required'}), 400
        
        # Check if user exists
        for u in users_db.values():
            if u['username'] == username:
                return jsonify({'error': 'Username taken'}), 400
            if u['email'] == email:
                return jsonify({'error': 'Email taken'}), 400
        
        # Create user
        uid = gen_id()
        users_db[uid] = {
            'id': uid,
            'username': username,
            'email': email,
            'password_hash': generate_password_hash(password),
            'phone': phone,
            'dob': dob,
            'employment': employment,
            'residence_proof': residence_proof,
            'is_admin': False,
            'created': datetime.utcnow().isoformat()
        }
        
        return jsonify({'success': True, 'msg': 'Account created! Login now'}), 201
    
    return render_template_string(AUTH_PAGE)

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    for uid, u in users_db.items():
        if u['username'] == username and check_password_hash(u['password_hash'], password):
            session['user_id'] = uid
            session['username'] = username
            return jsonify({'success': True, 'is_admin': u['is_admin']}), 200
    
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
        if item['status'] == 'available':
            if not cat or item['category'] == cat:
                result.append({
                    'id': iid,
                    'name': item['name'],
                    'category': item['category'],
                    'desc': item['desc'],
                    'value': item['value'],
                    'rate': item['rate'],
                    'days': item['days']
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
    due = datetime.utcnow() + timedelta(days=item['days'])
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
        'created': datetime.utcnow().isoformat()
    }
    
    item['status'] = 'pawned'
    
    return jsonify({
        'success': True,
        'loan_id': lid,
        'amount': loan_amt,
        'total_due': round(total_due, 2),
        'due_date': due.strftime('%Y-%m-%d')
    }), 201

@app.route('/dashboard')
@login_required
def dashboard():
    user = users_db[session['user_id']]
    return render_template_string(DASHBOARD_PAGE, user=user)

@app.route('/api/loans')
@login_required
def api_loans():
    uid = session['user_id']
    result = []
    for lid, loan in loans_db.items():
        if loan['user'] == uid:
            item = items_db.get(loan['item'], {})
            due = datetime.fromisoformat(loan['due'])
            days_left = (due - datetime.utcnow()).days
            result.append({
                'id': lid,
                'item': item.get('name', 'Unknown'),
                'amount': loan['amount'],
                'total_due': loan['total_due'],
                'status': loan['status'],
                'due': due.strftime('%Y-%m-%d'),
                'days_left': days_left
            })
    return jsonify(result)

@app.route('/api/repay/<lid>', methods=['POST'])
@login_required
def api_repay(lid):
    if lid not in loans_db:
        return jsonify({'error': 'Not found'}), 404
    
    loan = loans_db[lid]
    if loan['user'] != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    loan['status'] = 'repaid'
    items_db[loan['item']]['status'] = 'available'
    
    return jsonify({'success': True}), 200

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
        'status': 'available',
        'created': datetime.utcnow().isoformat()
    }
    return jsonify({'success': True, 'id': iid}), 201

@app.route('/api/admin/delete-item/<iid>', methods=['DELETE'])
@admin_required
def api_delete_item(iid):
    if iid in items_db:
        del items_db[iid]
        return jsonify({'success': True}), 200
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/admin/items')
@admin_required
def api_admin_items():
    result = []
    for iid, item in items_db.items():
        result.append({
            'id': iid,
            'name': item['name'],
            'cat': item['category'],
            'val': item['value'],
            'status': item['status']
        })
    return jsonify(result)

# ============ TEMPLATES ============

HOME = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #0a0a0a; color: #fff; }
        nav { background: #1a1a1a; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #ffc107; }
        nav h1 { font-size: 28px; color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 25px; padding: 8px 16px; border-radius: 5px; transition: 0.3s; }
        nav a:hover { background: #ffc107; color: #000; }
        .hero { text-align: center; padding: 120px 20px; background: linear-gradient(135deg, #1a1a1a, #2a2a2a); }
        .hero h1 { font-size: 52px; margin-bottom: 15px; color: #ffc107; }
        .hero p { font-size: 20px; color: #ccc; margin-bottom: 35px; }
        .cta { display: inline-block; padding: 16px 45px; background: #ffc107; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 18px; transition: 0.3s; }
        .cta:hover { background: #ffb600; transform: scale(1.05); }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 30px; padding: 80px 30px; max-width: 1200px; margin: 0 auto; }
        .feature { background: #1a1a1a; padding: 35px; border-radius: 10px; border: 1px solid #333; text-align: center; }
        .feature h3 { color: #ffc107; margin-bottom: 15px; font-size: 22px; }
        .feature p { color: #aaa; font-size: 15px; }
        footer { text-align: center; padding: 25px; background: #1a1a1a; border-top: 2px solid #ffc107; margin-top: 60px; }
    </style>
</head>
<body>
    <nav>
        <h1>💰 Pawn Shop</h1>
        <div>
            <a href="/register">Sign Up</a>
            <a onclick="window.location.href='#'; document.getElementById('loginform').style.display='flex';" style="cursor:pointer;">Login</a>
        </div>
    </nav>
    <div class="hero">
        <h1>Quick Pawn Loans</h1>
        <p>Sell or pawn your items for instant cash</p>
        <a href="/register" class="cta">Get Started</a>
    </div>
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
    <footer><p>&copy; 2024 Pawn Shop. All rights reserved.</p></footer>

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
</body>
</html>
'''

AUTH_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #0a0a0a; color: #fff; }
        .container { max-width: 500px; margin: 40px auto; padding: 35px; background: #1a1a1a; border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,0.8); }
        h1 { text-align: center; margin-bottom: 35px; color: #ffc107; font-size: 26px; }
        .form-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 6px; font-weight: bold; font-size: 13px; }
        input, select, textarea { width: 100%; padding: 10px; border: 1px solid #444; background: #2a2a2a; color: #fff; border-radius: 5px; font-size: 14px; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .row .form-group { margin-bottom: 0; }
        button { width: 100%; padding: 12px; background: #ffc107; color: #000; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; font-size: 16px; transition: 0.3s; }
        button:hover { background: #ffb600; }
        .error { color: #ff6b6b; text-align: center; margin: 10px 0; font-size: 12px; }
        .success { color: #51cf66; text-align: center; margin: 10px 0; font-size: 12px; }
        .proof-preview { width: 100px; height: 100px; margin: 10px auto; border-radius: 5px; background: #2a2a2a; display: flex; align-items: center; justify-content: center; border: 2px solid #ffc107; }
        .proof-preview img { width: 100%; height: 100%; object-fit: cover; border-radius: 5px; }
        .file-label { display: block; padding: 10px; background: #2a2a2a; border: 1px dashed #ffc107; border-radius: 5px; text-align: center; cursor: pointer; font-size: 12px; transition: 0.3s; }
        .file-label:hover { background: #333; }
        #proofFile { display: none; }
        .home { text-align: center; margin-top: 15px; }
        .home a { color: #ffc107; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Create Account</h1>
        <div id="msg"></div>
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
            <button type="submit">Create Account</button>
        </form>
        <div class="home">
            <a href="/">← Home</a>
        </div>
    </div>

    <script>
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

        document.getElementById('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!window.proofBase64) {
                show('error', 'Please upload proof of residence');
                return;
            }

            const body = {
                username: document.getElementById('uname').value,
                email: document.getElementById('email').value,
                password: document.getElementById('pass').value,
                phone: document.getElementById('phone').value,
                dob: document.getElementById('dob').value,
                employment: document.getElementById('emp').value,
                residence_proof: window.proofBase64
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
</body>
</html>
'''

BROWSE_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browse - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #0a0a0a; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 30px 20px; }
        .filter { margin-bottom: 25px; }
        .filter select { padding: 10px 15px; background: #1a1a1a; color: #fff; border: 1px solid #ffc107; border-radius: 5px; cursor: pointer; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
        .card { background: #1a1a1a; border-radius: 8px; overflow: hidden; border: 1px solid #333; transition: 0.3s; }
        .card:hover { border-color: #ffc107; transform: translateY(-5px); }
        .card-img { width: 100%; height: 180px; background: #2a2a2a; display: flex; align-items: center; justify-content: center; font-size: 50px; }
        .card-body { padding: 18px; }
        .card-title { font-size: 16px; font-weight: bold; color: #ffc107; margin-bottom: 6px; }
        .card-cat { color: #999; font-size: 12px; margin-bottom: 8px; }
        .card-desc { color: #ccc; font-size: 13px; margin-bottom: 12px; }
        .card-price { font-size: 18px; font-weight: bold; color: #51cf66; margin-bottom: 8px; }
        .card-terms { color: #888; font-size: 11px; margin-bottom: 12px; }
        .btn { width: 100%; padding: 10px; background: #ffc107; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; transition: 0.3s; }
        .btn:hover { background: #ffb600; }
        .empty { text-align: center; padding: 50px 20px; color: #888; }
    </style>
</head>
<body>
    <nav>
        <h1>💰 Pawn Shop</h1>
        <div>
            <a href="/dashboard">My Loans</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <h2 style="margin-bottom: 20px;">Available Items</h2>
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
            const url = cat ? `/api/items?cat=${cat}` : '/api/items';
            const res = await fetch(url);
            const items = await res.json();
            const grid = document.getElementById('grid');
            
            if (!items.length) {
                grid.innerHTML = '<div class="empty" style="grid-column: 1/-1;">No items</div>';
                return;
            }

            grid.innerHTML = items.map(i => `
                <div class="card">
                    <div class="card-img">${getEmoji(i.category)}</div>
                    <div class="card-body">
                        <div class="card-title">${i.name}</div>
                        <div class="card-cat">${i.category}</div>
                        <div class="card-desc">${i.desc || 'N/A'}</div>
                        <div class="card-price">$${i.value.toFixed(2)}</div>
                        <div class="card-terms">${i.days} days • ${i.rate}% APR</div>
                        <button class="btn" onclick="pawn('${i.id}')">Pawn</button>
                    </div>
                </div>
            `).join('');
        }

        function getEmoji(cat) {
            const map = { 'Electronics': '📱', 'Jewelry': '💍', 'Tools': '🔧', 'Sports': '⚽', 'Furniture': '🛋️' };
            return map[cat] || '📦';
        }

        async function pawn(id) {
            const res = await fetch('/api/pawn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ iid: id })
            });
            const data = await res.json();
            
            if (res.ok) {
                alert(`Loan Approved!\nAmount: $${data.amount.toFixed(2)}\nTotal Due: $${data.total_due.toFixed(2)}\nDue: ${data.due_date}`);
                load();
            } else {
                alert(data.error || 'Error');
            }
        }

        load();
    </script>
</body>
</html>
'''

DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #0a0a0a; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1000px; margin: 0 auto; padding: 30px 20px; }
        .profile { background: #1a1a1a; padding: 25px; border-radius: 10px; margin-bottom: 30px; border: 1px solid #333; }
        .profile-pic { width: 140px; height: 140px; background: #2a2a2a; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 50px; border: 2px solid #ffc107; margin-bottom: 15px; overflow: hidden; }
        .profile-pic img { width: 100%; height: 100%; object-fit: cover; }
        .profile h2 { color: #ffc107; margin-bottom: 15px; font-size: 24px; }
        .profile p { color: #ccc; margin-bottom: 8px; font-size: 14px; }
        .profile strong { color: #ffc107; }
        .loans { background: #1a1a1a; padding: 25px; border-radius: 10px; border: 1px solid #333; }
        .loans h2 { color: #ffc107; margin-bottom: 20px; }
        .loan { background: #2a2a2a; padding: 20px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #ffc107; }
        .loan-head { display: flex; justify-content: space-between; margin-bottom: 15px; }
        .loan-title { font-weight: bold; font-size: 16px; }
        .status { padding: 4px 10px; border-radius: 3px; font-size: 11px; }
        .status-active { background: #51cf66; color: #000; }
        .status-repaid { background: #94d82d; color: #000; }
        .loan-info { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; font-size: 13px; color: #aaa; margin-bottom: 15px; }
        .loan-info div { display: flex; justify-content: space-between; }
        .info-val { color: #fff; }
        .repay { padding: 10px 20px; background: #51cf66; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .repay:hover { background: #40c057; }
        .empty { text-align: center; padding: 40px 20px; color: #888; }
    </style>
</head>
<body>
    <nav>
        <h1>💰 Pawn Shop</h1>
        <div>
            <a href="/browse">Browse</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>
    <div class="container">
        <div class="profile">
            <div class="profile-pic" id="pic">👤</div>
            <h2>{{ user.username }}</h2>
            <p><strong>Email:</strong> {{ user.email }}</p>
            <p><strong>Phone:</strong> {{ user.phone or 'N/A' }}</p>
            <p><strong>DOB:</strong> {{ user.dob or 'N/A' }}</p>
            <p><strong>Employment:</strong> {{ user.employment or 'N/A' }}</p>
        </div>
        <div class="loans">
            <h2>My Loans</h2>
            <div id="loans"></div>
        </div>
    </div>

    <script>
        const pic = '{{ user.residence_proof or "" }}';
        if (pic && pic.length > 100) {
            document.getElementById('pic').innerHTML = `<img src="${pic}">`;
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

        load();
    </script>
</body>
</html>
'''

ADMIN_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #0a0a0a; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 30px 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat { background: #1a1a1a; padding: 25px; border-radius: 10px; border: 1px solid #333; text-align: center; }
        .stat-num { font-size: 32px; font-weight: bold; color: #ffc107; margin-bottom: 10px; }
        .stat-label { color: #999; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #333; }
        .tab { padding: 12px 20px; background: none; color: #999; border: none; cursor: pointer; border-bottom: 3px solid transparent; transition: 0.3s; }
        .tab.active { color: #ffc107; border-bottom-color: #ffc107; }
        .content { display: none; }
        .content.active { display: block; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, select, textarea { width: 100%; padding: 10px; background: #2a2a2a; color: #fff; border: 1px solid #444; border-radius: 5px; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; }
        button { padding: 10px 20px; background: #ffc107; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        button:hover { background: #ffb600; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        table th { background: #2a2a2a; padding: 12px; text-align: left; border-bottom: 2px solid #ffc107; }
        table td { padding: 12px; border-bottom: 1px solid #333; }
        .del { background: #ff6b6b; color: #fff; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; }
    </style>
</head>
<body>
    <nav>
        <h1>Admin</h1>
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
                <button type="submit">Add Item</button>
            </form>
        </div>
        <div id="items" class="content">
            <h3 style="margin-bottom: 20px;">Manage Items</h3>
            <div id="itemslist"></div>
        </div>
    </div>

    <script>
        function switchtab(tab) {
            document.querySelectorAll('.content').forEach(x => x.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
            document.getElementById(tab).classList.add('active');
            event.target.classList.add('active');
            if (tab === 'items') loaditems();
        }

        async function additem(e) {
            e.preventDefault();
            const data = {
                name: document.getElementById('name').value,
                category: document.getElementById('cat').value,
                desc: document.getElementById('desc').value,
                value: document.getElementById('val').value,
                rate: document.getElementById('rate').value,
                days: document.getElementById('days').value
            };
            const res = await fetch('/api/admin/add-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (res.ok) {
                alert('Item added!');
                e.target.reset();
            }
        }

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
                        <tr><th>Name</th><th>Category</th><th>Value</th><th>Status</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        ${items.map(i => `
                            <tr>
                                <td>${i.name}</td>
                                <td>${i.cat}</td>
                                <td>$${i.val.toFixed(2)}</td>
                                <td>${i.status}</td>
                                <td><button class="del" onclick="delitem('${i.id}')">Delete</button></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        async function delitem(id) {
            if (!confirm('Delete?')) return;
            const res = await fetch(`/api/admin/delete-item/${id}`, { method: 'DELETE' });
            if (res.ok) {
                alert('Deleted!');
                loaditems();
            }
        }
    </script>
</body>
</html>
'''

# ============ INIT & RUN ============

def init():
    # Sample items
    sample = [
        {'name': 'iPhone 14', 'category': 'Electronics', 'desc': 'Mint', 'value': 600, 'rate': 12, 'days': 30},
        {'name': 'Gold Ring', 'category': 'Jewelry', 'desc': '18k', 'value': 500, 'rate': 10, 'days': 30},
        {'name': 'Power Drill', 'category': 'Tools', 'desc': 'DeWalt', 'value': 150, 'rate': 15, 'days': 30},
        {'name': 'Gaming PC', 'category': 'Electronics', 'desc': 'RTX 3080', 'value': 1000, 'rate': 14, 'days': 30},
    ]
    for s in sample:
        iid = gen_id()
        items_db[iid] = {**s, 'id': iid, 'status': 'available', 'created': datetime.utcnow().isoformat()}
    
    # Admin user
    aid = gen_id()
    users_db[aid] = {
        'id': aid, 'username': 'admin', 'email': 'admin@shop.com',
        'password_hash': generate_password_hash('admin123'),
        'phone': '555-0000', 'dob': '1990-01-01', 'employment': 'employed',
        'residence_proof': '', 'is_admin': True, 'created': datetime.utcnow().isoformat()
    }

if __name__ == '__main__':
    init()
    app.run(debug=True, host='0.0.0.0', port=5000)
