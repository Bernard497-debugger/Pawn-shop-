from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import json
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pawn_shop_secret_2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pawn_shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============ DATABASE MODELS ============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    pawn_value = db.Column(db.Float, nullable=False)
    loan_duration_days = db.Column(db.Integer, default=30)
    interest_rate = db.Column(db.Float, default=15.0)
    image_url = db.Column(db.String(255))
    status = db.Column(db.String(20), default='available')  # available, pawned, sold
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    loan_amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)
    loan_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, repaid, forfeited
    amount_due = db.Column(db.Float, nullable=False)
    
    user = db.relationship('User', backref=db.backref('loans', lazy=True))
    item = db.relationship('Item', backref=db.backref('loans', lazy=True))

# ============ AUTHENTICATION ============

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# ============ ROUTES - AUTH ============

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        phone = data.get('phone')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username exists'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email exists'}), 400
        
        user = User(username=username, email=email, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Registered! Please login'}), 201
    
    return render_template_string(AUTH_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            return jsonify({'success': True, 'is_admin': user.is_admin}), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template_string(AUTH_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ============ ROUTES - MAIN ============

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/browse')
def browse():
    category = request.args.get('category', '')
    query = Item.query.filter_by(status='available')
    if category:
        query = query.filter_by(category=category)
    items = query.all()
    return render_template_string(BROWSE_TEMPLATE, items=items)

@app.route('/api/items')
def get_items():
    category = request.args.get('category', '')
    query = Item.query.filter_by(status='available')
    if category:
        query = query.filter_by(category=category)
    items = query.all()
    return jsonify([{
        'id': item.id,
        'name': item.name,
        'category': item.category,
        'description': item.description,
        'pawn_value': item.pawn_value,
        'loan_duration_days': item.loan_duration_days,
        'interest_rate': item.interest_rate,
        'image_url': item.image_url
    } for item in items])

@app.route('/api/pawn', methods=['POST'])
@login_required
def pawn_item():
    data = request.get_json()
    item_id = data.get('item_id')
    
    item = Item.query.get(item_id)
    if not item or item.status != 'available':
        return jsonify({'error': 'Item not available'}), 400
    
    loan_amount = item.pawn_value
    interest_rate = item.interest_rate
    due_date = datetime.utcnow() + timedelta(days=item.loan_duration_days)
    amount_due = loan_amount * (1 + interest_rate / 100)
    
    loan = Loan(
        user_id=session['user_id'],
        item_id=item_id,
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        due_date=due_date,
        amount_due=amount_due
    )
    
    item.status = 'pawned'
    db.session.add(loan)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'loan_id': loan.id,
        'loan_amount': loan_amount,
        'amount_due': round(amount_due, 2),
        'due_date': due_date.strftime('%Y-%m-%d')
    }), 201

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    loans = Loan.query.filter_by(user_id=user.id).all()
    return render_template_string(DASHBOARD_TEMPLATE, user=user, loans=loans)

@app.route('/api/loans')
@login_required
def get_user_loans():
    loans = Loan.query.filter_by(user_id=session['user_id']).all()
    return jsonify([{
        'id': loan.id,
        'item_name': loan.item.name,
        'loan_amount': loan.loan_amount,
        'amount_due': loan.amount_due,
        'status': loan.status,
        'due_date': loan.due_date.strftime('%Y-%m-%d'),
        'days_until_due': (loan.due_date - datetime.utcnow()).days
    } for loan in loans])

@app.route('/api/repay-loan/<int:loan_id>', methods=['POST'])
@login_required
def repay_loan(loan_id):
    loan = Loan.query.get(loan_id)
    if not loan or loan.user_id != session['user_id']:
        return jsonify({'error': 'Loan not found'}), 404
    
    loan.status = 'repaid'
    loan.item.status = 'available'
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Loan repaid successfully'}), 200

# ============ ADMIN ROUTES ============

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_items = Item.query.count()
    available_items = Item.query.filter_by(status='available').count()
    active_loans = Loan.query.filter_by(status='active').count()
    total_users = User.query.count()
    
    return render_template_string(ADMIN_TEMPLATE, 
        total_items=total_items,
        available_items=available_items,
        active_loans=active_loans,
        total_users=total_users
    )

@app.route('/admin/add-item', methods=['POST'])
@admin_required
def add_item():
    data = request.get_json()
    
    item = Item(
        name=data.get('name'),
        category=data.get('category'),
        description=data.get('description'),
        pawn_value=float(data.get('pawn_value')),
        loan_duration_days=int(data.get('loan_duration_days', 30)),
        interest_rate=float(data.get('interest_rate', 15.0)),
        image_url=data.get('image_url', '/static/placeholder.png')
    )
    
    db.session.add(item)
    db.session.commit()
    
    return jsonify({'success': True, 'item_id': item.id}), 201

@app.route('/admin/items')
@admin_required
def admin_items():
    items = Item.query.all()
    return render_template_string(ADMIN_ITEMS_TEMPLATE, items=items)

@app.route('/admin/loans')
@admin_required
def admin_loans():
    loans = Loan.query.all()
    return render_template_string(ADMIN_LOANS_TEMPLATE, loans=loans)

@app.route('/admin/delete-item/<int:item_id>', methods=['DELETE'])
@admin_required
def delete_item(item_id):
    item = Item.query.get(item_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True}), 200
    return jsonify({'error': 'Item not found'}), 404

# ============ TEMPLATES ============

AUTH_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pawn Shop - Auth</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a1a; color: #fff; }
        .container { max-width: 400px; margin: 100px auto; padding: 20px; background: #2a2a2a; border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }
        h1 { text-align: center; margin-bottom: 30px; color: #ffc107; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: 500; }
        input { width: 100%; padding: 12px; border: 1px solid #444; border-radius: 5px; background: #333; color: #fff; }
        input:focus { outline: none; border-color: #ffc107; background: #3a3a3a; }
        button { width: 100%; padding: 12px; background: #ffc107; color: #000; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; transition: all 0.3s; }
        button:hover { background: #ffb600; transform: translateY(-2px); }
        .toggle { text-align: center; margin-top: 20px; }
        .toggle a { color: #ffc107; text-decoration: none; }
        .error { color: #ff6b6b; text-align: center; margin: 10px 0; }
        .success { color: #51cf66; text-align: center; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1 id="title">Login</h1>
        <div id="message"></div>
        <form id="authForm">
            <div id="registerFields" style="display: none;">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" id="username" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="email" required>
                </div>
                <div class="form-group">
                    <label>Phone</label>
                    <input type="tel" id="phone">
                </div>
            </div>
            <div id="loginFields">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" id="username" required>
                </div>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" id="password" required>
            </div>
            <button type="submit">Submit</button>
        </form>
        <div class="toggle">
            <span id="toggleText">Don't have an account? </span>
            <a href="#" id="toggleLink" onclick="toggleMode(event)">Register</a>
            <a href="/" style="margin-left: 15px;">Back Home</a>
        </div>
    </div>

    <script>
        let isLoginMode = true;

        document.getElementById('authForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const url = isLoginMode ? '/login' : '/register';
            
            const body = { username, password };
            if (!isLoginMode) {
                body.email = document.getElementById('email').value;
                body.phone = document.getElementById('phone').value;
            }

            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                
                if (res.ok) {
                    if (isLoginMode) {
                        window.location.href = data.is_admin ? '/admin' : '/browse';
                    } else {
                        showMessage('success', data.message || 'Account created! Logging in...');
                        setTimeout(() => window.location.href = '/login', 1500);
                    }
                } else {
                    showMessage('error', data.error || 'Error');
                }
            } catch (err) {
                showMessage('error', 'Request failed');
            }
        });

        function toggleMode(e) {
            e.preventDefault();
            isLoginMode = !isLoginMode;
            document.getElementById('title').textContent = isLoginMode ? 'Login' : 'Register';
            document.getElementById('loginFields').style.display = isLoginMode ? 'block' : 'none';
            document.getElementById('registerFields').style.display = isLoginMode ? 'none' : 'block';
            document.getElementById('toggleText').textContent = isLoginMode ? "Don't have an account? " : 'Already have an account? ';
            document.getElementById('toggleLink').textContent = isLoginMode ? 'Register' : 'Login';
            document.getElementById('message').innerHTML = '';
        }

        function showMessage(type, msg) {
            document.getElementById('message').innerHTML = `<div class="${type}">${msg}</div>`;
        }
    </script>
</body>
</html>
'''

HOME_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Online Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f0f0f; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; font-size: 24px; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; padding: 8px 15px; border-radius: 5px; transition: all 0.3s; }
        nav a:hover { background: #ffc107; color: #000; }
        .hero { text-align: center; padding: 100px 20px; background: linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%); }
        .hero h1 { font-size: 48px; margin-bottom: 20px; color: #ffc107; }
        .hero p { font-size: 18px; margin-bottom: 30px; color: #ccc; }
        .cta { display: inline-block; padding: 15px 40px; background: #ffc107; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px; transition: all 0.3s; }
        .cta:hover { background: #ffb600; transform: translateY(-2px); }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 30px; padding: 60px 30px; max-width: 1200px; margin: 0 auto; }
        .feature { background: #1a1a1a; padding: 30px; border-radius: 10px; text-align: center; border: 1px solid #333; }
        .feature h3 { color: #ffc107; margin-bottom: 15px; font-size: 20px; }
        .feature p { color: #aaa; }
        footer { background: #1a1a1a; padding: 20px; text-align: center; border-top: 2px solid #ffc107; margin-top: 60px; }
    </style>
</head>
<body>
    <nav>
        <h1>💰 Pawn Shop</h1>
        <div>
            <a href="/register">Register</a>
            <a href="/login">Login</a>
        </div>
    </nav>

    <div class="hero">
        <h1>Welcome to Online Pawn Shop</h1>
        <p>Quick loans with valuable items. Easy process, fair rates.</p>
        <a href="/browse" class="cta">Browse Items Now</a>
    </div>

    <div class="features">
        <div class="feature">
            <h3>⚡ Fast Loans</h3>
            <p>Get instant cash loans against your items in minutes</p>
        </div>
        <div class="feature">
            <h3>💎 Secure</h3>
            <p>Your items are safely stored and insured</p>
        </div>
        <div class="feature">
            <h3>📱 Easy Process</h3>
            <p>Simple online application and quick approval</p>
        </div>
        <div class="feature">
            <h3>🔄 Flexible Terms</h3>
            <p>30-day loan periods with competitive interest rates</p>
        </div>
    </div>

    <footer>
        <p>&copy; 2024 Online Pawn Shop. All rights reserved.</p>
    </footer>
</body>
</html>
'''

BROWSE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browse Items - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f0f0f; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 30px 20px; }
        .filters { margin-bottom: 30px; }
        .filters select { padding: 10px 15px; background: #1a1a1a; color: #fff; border: 1px solid #ffc107; border-radius: 5px; cursor: pointer; }
        .items-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 25px; }
        .item-card { background: #1a1a1a; border-radius: 10px; overflow: hidden; border: 1px solid #333; transition: all 0.3s; }
        .item-card:hover { border-color: #ffc107; transform: translateY(-5px); }
        .item-image { width: 100%; height: 200px; background: #2a2a2a; display: flex; align-items: center; justify-content: center; font-size: 40px; }
        .item-info { padding: 20px; }
        .item-name { font-size: 18px; font-weight: bold; margin-bottom: 8px; color: #ffc107; }
        .item-category { color: #aaa; font-size: 12px; margin-bottom: 10px; }
        .item-description { color: #ccc; font-size: 14px; margin-bottom: 15px; line-height: 1.4; }
        .item-price { font-size: 20px; font-weight: bold; color: #51cf66; margin-bottom: 10px; }
        .item-terms { color: #999; font-size: 12px; margin-bottom: 15px; }
        .btn { padding: 10px 20px; background: #ffc107; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; transition: all 0.3s; width: 100%; }
        .btn:hover { background: #ffb600; }
        .btn:disabled { background: #666; cursor: not-allowed; }
        .empty { text-align: center; padding: 50px 20px; color: #aaa; }
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
        <h2 style="margin-bottom: 20px;">Browse Available Items</h2>
        
        <div class="filters">
            <label>Category: </label>
            <select id="categoryFilter" onchange="filterItems()">
                <option value="">All Categories</option>
                <option value="Electronics">Electronics</option>
                <option value="Jewelry">Jewelry</option>
                <option value="Tools">Tools</option>
                <option value="Sports">Sports Equipment</option>
                <option value="Furniture">Furniture</option>
                <option value="Other">Other</option>
            </select>
        </div>

        <div class="items-grid" id="itemsGrid">
            <!-- Items loaded here -->
        </div>
    </div>

    <script>
        async function loadItems(category = '') {
            try {
                const url = category ? `/api/items?category=${category}` : '/api/items';
                const res = await fetch(url);
                const items = await res.json();
                
                const grid = document.getElementById('itemsGrid');
                if (items.length === 0) {
                    grid.innerHTML = '<div class="empty" style="grid-column: 1/-1;">No items available</div>';
                    return;
                }

                grid.innerHTML = items.map(item => `
                    <div class="item-card">
                        <div class="item-image">${getEmoji(item.category)}</div>
                        <div class="item-info">
                            <div class="item-name">${item.name}</div>
                            <div class="item-category">${item.category}</div>
                            <div class="item-description">${item.description || 'N/A'}</div>
                            <div class="item-price">$${item.pawn_value.toFixed(2)}</div>
                            <div class="item-terms">${item.loan_duration_days} days • ${item.interest_rate}% interest</div>
                            <button class="btn" onclick="pawnItem(${item.id})">Pawn This Item</button>
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                document.getElementById('itemsGrid').innerHTML = '<div class="empty" style="grid-column: 1/-1;">Error loading items</div>';
            }
        }

        function getEmoji(category) {
            const emojis = {
                'Electronics': '📱',
                'Jewelry': '💍',
                'Tools': '🔧',
                'Sports': '⚽',
                'Furniture': '🛋️',
                'Other': '📦'
            };
            return emojis[category] || '📦';
        }

        async function pawnItem(itemId) {
            try {
                const res = await fetch('/api/pawn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ item_id: itemId })
                });
                const data = await res.json();
                
                if (res.ok) {
                    alert(`Loan approved!\nAmount: $${data.loan_amount.toFixed(2)}\nDue: ${data.due_date}`);
                    loadItems();
                } else {
                    alert(data.error || 'Error pawning item');
                }
            } catch (err) {
                alert('Error processing loan');
            }
        }

        function filterItems() {
            const category = document.getElementById('categoryFilter').value;
            loadItems(category);
        }

        loadItems();
    </script>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Dashboard - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f0f0f; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1000px; margin: 0 auto; padding: 30px 20px; }
        .profile { background: #1a1a1a; padding: 25px; border-radius: 10px; margin-bottom: 30px; border: 1px solid #333; }
        .profile h2 { color: #ffc107; margin-bottom: 15px; }
        .profile p { color: #ccc; margin-bottom: 8px; }
        .loans-section { background: #1a1a1a; padding: 25px; border-radius: 10px; border: 1px solid #333; }
        .loans-section h2 { color: #ffc107; margin-bottom: 20px; }
        .loan-card { background: #2a2a2a; padding: 20px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #ffc107; }
        .loan-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .loan-name { font-size: 18px; font-weight: bold; }
        .loan-status { padding: 5px 10px; border-radius: 3px; font-size: 12px; }
        .status-active { background: #51cf66; color: #000; }
        .status-repaid { background: #94d82d; color: #000; }
        .status-forfeited { background: #ff6b6b; color: #fff; }
        .loan-details { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; font-size: 14px; color: #aaa; }
        .loan-detail { display: flex; justify-content: space-between; }
        .loan-detail-value { color: #fff; }
        .repay-btn { padding: 10px 20px; background: #51cf66; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .repay-btn:hover { background: #40c057; }
        .repay-btn:disabled { background: #666; cursor: not-allowed; }
        .empty { text-align: center; padding: 40px 20px; color: #aaa; }
    </style>
</head>
<body>
    <nav>
        <h1>💰 Pawn Shop</h1>
        <div>
            <a href="/browse">Browse Items</a>
            <a href="/logout">Logout</a>
        </div>
    </nav>

    <div class="container">
        <div class="profile">
            <h2>My Profile</h2>
            <p><strong>Username:</strong> {{ user.username }}</p>
            <p><strong>Email:</strong> {{ user.email }}</p>
            <p><strong>Phone:</strong> {{ user.phone or 'Not provided' }}</p>
        </div>

        <div class="loans-section">
            <h2>My Loans</h2>
            <div id="loansContainer">
                <!-- Loans loaded here -->
            </div>
        </div>
    </div>

    <script>
        async function loadLoans() {
            try {
                const res = await fetch('/api/loans');
                const loans = await res.json();
                
                const container = document.getElementById('loansContainer');
                if (loans.length === 0) {
                    container.innerHTML = '<div class="empty">No active loans</div>';
                    return;
                }

                container.innerHTML = loans.map(loan => `
                    <div class="loan-card">
                        <div class="loan-header">
                            <div class="loan-name">${loan.item_name}</div>
                            <span class="loan-status status-${loan.status}">${loan.status.toUpperCase()}</span>
                        </div>
                        <div class="loan-details">
                            <div class="loan-detail">
                                <span>Loan Amount</span>
                                <span class="loan-detail-value">$${loan.loan_amount.toFixed(2)}</span>
                            </div>
                            <div class="loan-detail">
                                <span>Amount Due</span>
                                <span class="loan-detail-value">$${loan.amount_due.toFixed(2)}</span>
                            </div>
                            <div class="loan-detail">
                                <span>Due Date</span>
                                <span class="loan-detail-value">${loan.due_date}</span>
                            </div>
                            <div class="loan-detail">
                                <span>Days Until Due</span>
                                <span class="loan-detail-value">${loan.days_until_due}</span>
                            </div>
                        </div>
                        ${loan.status === 'active' ? `
                            <button class="repay-btn" onclick="repayLoan(${loan.id})">Repay Loan</button>
                        ` : ''}
                    </div>
                `).join('');
            } catch (err) {
                document.getElementById('loansContainer').innerHTML = '<div class="empty">Error loading loans</div>';
            }
        }

        async function repayLoan(loanId) {
            if (!confirm('Confirm repayment of this loan?')) return;
            
            try {
                const res = await fetch(`/api/repay-loan/${loanId}`, { method: 'POST' });
                const data = await res.json();
                
                if (res.ok) {
                    alert(data.message);
                    loadLoans();
                } else {
                    alert(data.error || 'Error repaying loan');
                }
            } catch (err) {
                alert('Error processing repayment');
            }
        }

        loadLoans();
    </script>
</body>
</html>
'''

ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - Pawn Shop</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f0f0f; color: #fff; }
        nav { background: #1a1a1a; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ffc107; }
        nav h1 { color: #ffc107; }
        nav a { color: #fff; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 30px 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #1a1a1a; padding: 25px; border-radius: 10px; border: 1px solid #333; text-align: center; }
        .stat-value { font-size: 32px; font-weight: bold; color: #ffc107; margin-bottom: 10px; }
        .stat-label { color: #aaa; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #333; }
        .tab-btn { padding: 12px 20px; background: none; color: #aaa; border: none; cursor: pointer; font-size: 16px; border-bottom: 3px solid transparent; transition: all 0.3s; }
        .tab-btn.active { color: #ffc107; border-bottom-color: #ffc107; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: 500; }
        input, select, textarea { width: 100%; padding: 10px; background: #1a1a1a; color: #fff; border: 1px solid #333; border-radius: 5px; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #ffc107; }
        button { padding: 12px 20px; background: #ffc107; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        button:hover { background: #ffb600; }
        .table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .table th { background: #1a1a1a; padding: 15px; text-align: left; border-bottom: 2px solid #ffc107; }
        .table td { padding: 15px; border-bottom: 1px solid #333; }
        .table tr:hover { background: #1a1a1a; }
        .delete-btn { padding: 5px 10px; background: #ff6b6b; color: #fff; border: none; border-radius: 3px; cursor: pointer; }
        .delete-btn:hover { background: #ff5252; }
    </style>
</head>
<body>
    <nav>
        <h1>💰 Admin Dashboard</h1>
        <div>
            <a href="/logout">Logout</a>
        </div>
    </nav>

    <div class="container">
        <h2 style="margin-bottom: 25px;">Admin Control Panel</h2>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{{ total_items }}</div>
                <div class="stat-label">Total Items</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ available_items }}</div>
                <div class="stat-label">Available</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ active_loans }}</div>
                <div class="stat-label">Active Loans</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ total_users }}</div>
                <div class="stat-label">Users</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('add-item')">Add Item</button>
            <button class="tab-btn" onclick="switchTab('items')">Manage Items</button>
            <button class="tab-btn" onclick="switchTab('loans')">Loans</button>
        </div>

        <div id="add-item" class="tab-content active">
            <form onsubmit="addItem(event)">
                <h3 style="margin-bottom: 20px;">Add New Item</h3>
                <div class="form-group">
                    <label>Item Name</label>
                    <input type="text" id="itemName" required>
                </div>
                <div class="form-group">
                    <label>Category</label>
                    <select id="itemCategory" required>
                        <option value="">Select Category</option>
                        <option value="Electronics">Electronics</option>
                        <option value="Jewelry">Jewelry</option>
                        <option value="Tools">Tools</option>
                        <option value="Sports">Sports Equipment</option>
                        <option value="Furniture">Furniture</option>
                        <option value="Other">Other</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="itemDescription" rows="4"></textarea>
                </div>
                <div class="form-group">
                    <label>Pawn Value ($)</label>
                    <input type="number" id="itemValue" step="0.01" required>
                </div>
                <div class="form-group">
                    <label>Loan Duration (Days)</label>
                    <input type="number" id="itemDuration" value="30" required>
                </div>
                <div class="form-group">
                    <label>Interest Rate (%)</label>
                    <input type="number" id="itemInterest" value="15" step="0.1" required>
                </div>
                <button type="submit">Add Item</button>
            </form>
        </div>

        <div id="items" class="tab-content">
            <h3 style="margin-bottom: 20px;">Manage Items</h3>
            <div id="itemsTable"></div>
        </div>

        <div id="loans" class="tab-content">
            <h3 style="margin-bottom: 20px;">Active Loans</h3>
            <div id="loansTable"></div>
        </div>
    </div>

    <script>
        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
            
            if (tabName === 'items') loadItems();
            if (tabName === 'loans') loadLoans();
        }

        async function addItem(e) {
            e.preventDefault();
            
            const data = {
                name: document.getElementById('itemName').value,
                category: document.getElementById('itemCategory').value,
                description: document.getElementById('itemDescription').value,
                pawn_value: document.getElementById('itemValue').value,
                loan_duration_days: document.getElementById('itemDuration').value,
                interest_rate: document.getElementById('itemInterest').value
            };

            try {
                const res = await fetch('/admin/add-item', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                
                if (res.ok) {
                    alert('Item added successfully!');
                    e.target.reset();
                } else {
                    alert('Error adding item');
                }
            } catch (err) {
                alert('Error');
            }
        }

        async function loadItems() {
            try {
                const res = await fetch('/api/items?category=');
                const items = await res.json();
                const container = document.getElementById('itemsTable');
                
                container.innerHTML = `
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Category</th>
                                <th>Value</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${items.map(item => `
                                <tr>
                                    <td>${item.name}</td>
                                    <td>${item.category}</td>
                                    <td>$${item.pawn_value.toFixed(2)}</td>
                                    <td>${item.status}</td>
                                    <td><button class="delete-btn" onclick="deleteItem(${item.id})">Delete</button></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } catch (err) {
                document.getElementById('itemsTable').innerHTML = 'Error loading items';
            }
        }

        async function deleteItem(itemId) {
            if (!confirm('Delete this item?')) return;
            
            try {
                const res = await fetch(`/admin/delete-item/${itemId}`, { method: 'DELETE' });
                if (res.ok) {
                    alert('Item deleted!');
                    loadItems();
                }
            } catch (err) {
                alert('Error deleting item');
            }
        }

        async function loadLoans() {
            const container = document.getElementById('loansTable');
            container.innerHTML = 'Loading...';
            // Loans would load from /admin/loans - simple table display
        }
    </script>
</body>
</html>
'''

ADMIN_ITEMS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Manage Items</title></head>
<body>
    <h1>Manage Items</h1>
    <table border="1">
        <tr><th>ID</th><th>Name</th><th>Category</th><th>Value</th><th>Status</th></tr>
        {% for item in items %}
        <tr>
            <td>{{ item.id }}</td>
            <td>{{ item.name }}</td>
            <td>{{ item.category }}</td>
            <td>${{ item.pawn_value }}</td>
            <td>{{ item.status }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
'''

ADMIN_LOANS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Active Loans</title></head>
<body>
    <h1>Active Loans</h1>
    <table border="1">
        <tr><th>ID</th><th>User</th><th>Item</th><th>Loan Amount</th><th>Status</th><th>Due Date</th></tr>
        {% for loan in loans %}
        <tr>
            <td>{{ loan.id }}</td>
            <td>{{ loan.user.username }}</td>
            <td>{{ loan.item.name }}</td>
            <td>${{ loan.loan_amount }}</td>
            <td>{{ loan.status }}</td>
            <td>{{ loan.due_date.strftime('%Y-%m-%d') }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
'''

# ============ DB INIT & RUN ============

def init_db():
    with app.app_context():
        db.create_all()
        
        # Create admin user if doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@pawnshop.com', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Add sample items
            sample_items = [
                Item(name='iPhone 14 Pro', category='Electronics', description='Mint condition', pawn_value=600, interest_rate=12),
                Item(name='Gold Necklace', category='Jewelry', description='18k gold', pawn_value=500, interest_rate=10),
                Item(name='Power Drill', category='Tools', description='DeWalt 20V', pawn_value=150, interest_rate=15),
                Item(name='Gaming Laptop', category='Electronics', description='RTX 3080', pawn_value=1000, interest_rate=14),
                Item(name='Mountain Bike', category='Sports', description='Trek full suspension', pawn_value=400, interest_rate=13),
                Item(name='Leather Sofa', category='Furniture', description='Brown 3-seater', pawn_value=350, interest_rate=15),
            ]
            
            for item in sample_items:
                db.session.add(item)
            
            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
