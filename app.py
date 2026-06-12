import os
import re
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
load_dotenv()
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SQLite concurrency: 15-second lock timeout
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {
        "timeout": 15
    }
}

db = SQLAlchemy(app)
csrf = CSRFProtect(app)


# Enable WAL mode for better read/write concurrency on SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# Decorator: redirects unauthenticated users to the login page
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_id') is None:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


from models import Company, User, Product, Transaction

# Create all tables on startup if they don't exist
with app.app_context():
    db.create_all()


# Jinja filter: converts UTC timestamps to local time (UTC-4) for display
@app.template_filter('localtime')
def localtime_filter(utc_dt):
    if not utc_dt:
        return ""
    local_dt = utc_dt - timedelta(hours=4)
    return local_dt.strftime('%Y-%m-%d %I:%M %p')


# --- TEST ROUTE (ORM sandbox, remove before production) ---
@app.route('/test', methods=['GET', 'POST'])
@login_required
def test():
    if request.method == 'POST':

        test_name = request.form.get('test_name')
        test_sku = request.form.get('test_sku')
        test_notes = request.form.get('test_notes')
        min = request.form.get('test_min')
        test_units = request.form.get('test_units')
        test_packages = request.form.get('test_packages')
        test_u_packages = request.form.get('test_u_packages')

        if not test_name or not test_sku:
            flash('please enter a product')
            return redirect(url_for('test'))
        try:
            new_product = Product(
                name = test_name,
                sku = test_sku,
                notes = test_notes,
                single_units = test_units,
                min_stock = min,
                packages = test_packages,
                units_per_package = test_u_packages,
                company_id = session.get('company_id')
            )
            db.session.add(new_product)
            db.session.commit()
            flash(' funciono creo ._.  ', 'success')
            return redirect(url_for('test'))
        except Exception as e:
            db.session.rollback()
            flash(e)
    list_products = Product.query.all()
    return render_template('test.html', productos=list_products)


# --- DASHBOARD ---
@app.route('/')
@login_required
def index():
    current_company_id = session.get('company_id')

    total_products = Product.query.filter_by(company_id=current_company_id, is_active=True).count()
    total_staff = User.query.filter_by(company_id=current_company_id, is_active=True).count()
    total_movements = Transaction.query.join(Product).filter(Product.company_id == current_company_id).count()

    recent_transactions = Transaction.query.join(Product).filter(
        Product.company_id == current_company_id
    ).order_by(Transaction.timestamp.desc()).limit(10).all()

    has_low_stock = db.session.query(Product).filter(
        Product.company_id == current_company_id,
        Product.is_active == True,
        Product.min_stock > 0,
        ((Product.packages * Product.units_per_package) + Product.single_units) <= Product.min_stock
    ).first()
    print(f"DEBUGGING: has_low_stock value is: {has_low_stock}")

    return render_template('dashboard.html',
                           transactions=recent_transactions,
                           total_products=total_products,
                           total_staff=total_staff,
                           total_movements=total_movements,
                           has_low_stock=has_low_stock)


# --- REGISTER: Creates a new company and its first Manager account ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        company_name = request.form.get('company_name').strip()
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        if not company_name or not username or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash(f'The username "{username}" is already taken.', 'warning')
            return redirect(url_for('register'))

        try:
            # Insert company first to get its auto-generated ID
            new_company = Company(name=company_name)
            db.session.add(new_company)
            db.session.flush()

            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(
                username=username,
                password_hash=hashed_password,
                role='Manager',
                company_id=new_company.id
            )
            db.session.add(new_user)

            db.session.commit()
            flash('Company registered successfully! Please log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            # Rollback ensures no partial data (orphan company) is persisted
            db.session.rollback()
            print(f"CRITICAL DB ERROR (register): {e}")
            flash('An internal database error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')


# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Clear any stale session before starting a new login
    session.clear()

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        if not username or not password:
            flash('Please provide both username and password.', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()

        # Single check for both missing user and wrong password (prevents user enumeration)
        if user is None or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

        if not user.is_active:
            flash('This account has been deactivated. Contact administration.', 'danger')
            return redirect(url_for('login'))

        session.permanent = True
        session['user_id'] = user.id
        session['company_id'] = user.company_id
        session['role'] = user.role

        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))


# --- INVENTORY: List with search, sort, and pagination ---
@app.route('/inventory')
@login_required
def inventory():
    current_company_id = session.get('company_id')

    page = request.args.get('page', 1, type=int)
    search_word = request.args.get('search', '', type=str)
    sort_by = request.args.get('sort_by', 'name', type=str)
    order = request.args.get('order', 'asc', type=str)

    query = Product.query.filter_by(company_id=current_company_id, is_active=True)

    if search_word:
        search_term = f"%{search_word}%"
        query = query.filter(
            db.or_(
                Product.sku.ilike(search_term),
                Product.name.ilike(search_term)
            )
        )

    # Dynamic sort: computes total stock on-the-fly for the 'total' column
    if sort_by == 'sku':
        query = query.order_by(Product.sku.desc() if order == 'desc' else Product.sku.asc())
    elif sort_by == 'packages':
        query = query.order_by(Product.packages.desc() if order == 'desc' else Product.packages.asc())
    elif sort_by == 'single_units':
        query = query.order_by(Product.single_units.desc() if order == 'desc' else Product.single_units.asc())
    elif sort_by == 'total':
        total_calc = (Product.packages * Product.units_per_package) + Product.single_units
        query = query.order_by(total_calc.desc() if order == 'desc' else total_calc.asc())
    else:
        query = query.order_by(Product.name.desc() if order == 'desc' else Product.name.asc())

    pagination = query.paginate(page=page, per_page=15, error_out=False)

    return render_template('inventory.html',
                           pagination=pagination,
                           search_word=search_word,
                           sort_by=sort_by,
                           order=order)


# --- ADD PRODUCTS (bulk form submission) ---
@app.route('/add_product_bulk', methods=['POST'])
@login_required
def add_product_bulk():
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: Only Managers and Supervisors can add products.', 'danger')
        return redirect(url_for('inventory'))

    names = request.form.getlist('name[]')
    skus = request.form.getlist('sku[]')
    notes = request.form.getlist('notes[]')
    packages = request.form.getlist('packages[]')
    units_pkg = request.form.getlist('units_per_package[]')
    singles = request.form.getlist('single_units[]')
    min_stocks = request.form.getlist('min_stock[]')

    try:
        for i in range(len(names)):
            if names[i] and skus[i]:
                new_product = Product(
                    name=names[i], sku=skus[i], notes=notes[i],
                    packages=int(packages[i] or 0),
                    units_per_package=int(units_pkg[i] or 0),
                    single_units=int(singles[i] or 0),
                    min_stock=int(min_stocks[i] or 0),
                    company_id=session.get('company_id')
                )
                db.session.add(new_product)

        db.session.commit()
        flash('Bulk products added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error saving bulk products.', 'danger')

    return redirect(url_for('inventory'))


# --- EDIT PRODUCT ---
@app.route('/edit_product/<int:id>', methods=['POST'])
@login_required
def edit_product(id):
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: You do not have permission to edit products.', 'danger')
        return redirect(url_for('inventory'))

    product = Product.query.get_or_404(id)

    if product.company_id != session.get('company_id'):
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('inventory'))

    try:
        new_packages = int(request.form.get('packages') or 0)
        new_single_units = int(request.form.get('single_units') or 0)

        # Calculate the delta to log in the transaction audit trail
        diff_packages = new_packages - product.packages
        diff_units = new_single_units - product.single_units

        product.name = request.form.get('name')
        product.sku = request.form.get('sku')
        product.notes = request.form.get('notes')
        product.min_stock = int(request.form.get('min_stock') or 0)
        product.units_per_package = int(request.form.get('units_per_package') or 0)
        product.packages = new_packages
        product.single_units = new_single_units

        if diff_packages != 0 or diff_units != 0:
            new_transaction = Transaction(
                product_id=product.id,
                user_id=session.get('user_id'),
                operation_type='EDIT',
                packages_affected=diff_packages,
                units_affected=diff_units
            )
            db.session.add(new_transaction)

        db.session.commit()
        flash(f'Product "{product.name}" updated successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL DB ERROR (edit_product): {e}")
        flash('Internal error: Could not update the product.', 'danger')

    return redirect(url_for('inventory'))


# --- DELETE PRODUCT (soft delete) ---
@app.route('/delete_product/<int:id>')
@login_required
def delete_product(id):
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: You do not have permission to delete products.', 'danger')
        return redirect(url_for('inventory'))

    product = Product.query.get_or_404(id)

    if product.company_id != session.get('company_id'):
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('inventory'))

    try:
        product.is_active = False

        new_transaction = Transaction(
            product_id=product.id,
            user_id=session.get('user_id'),
            operation_type='DELETE',
            packages_affected=-product.packages,
            units_affected=-product.single_units
        )
        db.session.add(new_transaction)

        db.session.commit()
        flash(f'Product "{product.name}" has been removed from inventory.', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL DB ERROR (delete_product): {e}")
        flash('Internal error: Could not delete the product.', 'danger')

    return redirect(url_for('inventory'))


# --- TRANSACTIONS: Audit trail with search and pagination ---
@app.route('/transactions')
@login_required
def transactions():
    current_company_id = session.get('company_id')

    page = request.args.get('page', 1, type=int)
    search_word = request.args.get('search', '', type=str)

    # Join Product and User so we can filter by SKU, product name, username, or operation type
    query = Transaction.query.join(Product).join(User).filter(
        Product.company_id == current_company_id
    )

    if search_word:
        search_term = f"%{search_word}%"
        query = query.filter(
            db.or_(
                Product.sku.ilike(search_term),
                Product.name.ilike(search_term),
                User.username.ilike(search_term),
                Transaction.operation_type.ilike(search_term)
            )
        )

    pagination = query.order_by(Transaction.timestamp.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('transactions.html', pagination=pagination, search_word=search_word)


# --- STAFF: List workers (Managers and Supervisors only) ---
@app.route('/workers')
@login_required
def workers():
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: This area is restricted.', 'danger')
        return redirect(url_for('inventory'))

    current_company_id = session.get('company_id')

    page = request.args.get('page', 1, type=int)
    search_word = request.args.get('search', '', type=str)

    query = User.query.filter_by(company_id=current_company_id, is_active=True)

    if search_word:
        search_term = f"%{search_word}%"
        query = query.filter(
            db.or_(
                User.username.ilike(search_term),
                User.role.ilike(search_term)
            )
        )

    pagination = query.order_by(User.username.asc()).paginate(
        page=page, per_page=10, error_out=False
    )

    return render_template('workers.html', pagination=pagination, search_word=search_word)


# --- ADD WORKER (Manager only) ---
@app.route('/add_worker', methods=['POST'])
@login_required
def add_worker():
    if session.get('role') != 'Manager':
        flash('Access Denied: This area is restricted to Management only.', 'danger')
        return redirect(url_for('inventory'))

    username = request.form.get('username').strip()
    password = request.form.get('password').strip()
    role = request.form.get('role')

    if not username or not password or not role:
        flash('All fields are required.', 'danger')
        return redirect(url_for('workers'))

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash(f'The username "{username}" is already taken.', 'warning')
        return redirect(url_for('workers'))

    try:
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(
            username=username,
            password_hash=hashed_password,
            role=role,
            company_id=session.get('company_id')
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f'Worker "{username}" added successfully as {role}.', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL DB ERROR (add_worker): {e}")
        flash('Internal error: Could not register the worker.', 'danger')

    return redirect(url_for('workers'))


# --- EDIT WORKER (Manager only) ---
@app.route('/edit_worker/<int:id>', methods=['POST'])
@login_required
def edit_worker(id):
    if session.get('role') != 'Manager':
        flash('Access Denied: This area is restricted to Management only.', 'danger')
        return redirect(url_for('inventory'))

    worker = User.query.get_or_404(id)

    if worker.company_id != session.get('company_id'):
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('workers'))

    new_username = request.form.get('username').strip()
    new_role = request.form.get('role').strip()
    new_password = request.form.get('password').strip()

    existing_user = User.query.filter(User.username == new_username, User.id != id).first()
    if existing_user:
        flash(f'The username "{new_username}" is already taken.', 'warning')
        return redirect(url_for('workers'))

    try:
        worker.username = new_username
        worker.role = new_role

        if new_password:
            worker.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')

        db.session.commit()
        flash(f'Worker "{worker.username}" updated successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL DB ERROR (edit_worker): {e}")
        flash('Internal error: Could not update the worker.', 'danger')

    return redirect(url_for('workers'))


# --- DELETE WORKER (soft delete, Manager only) ---
@app.route('/delete_worker/<int:id>')
@login_required
def delete_worker(id):
    if session.get('role') != 'Manager':
        flash('Access Denied: This area is restricted to Management only.', 'danger')
        return redirect(url_for('inventory'))

    worker = User.query.get_or_404(id)

    try:
        if worker.company_id != session.get('company_id'):
            flash('Unauthorized action.', 'danger')
            return redirect(url_for('workers'))

        # Prevent a Manager from deleting their own account
        if worker.id == session.get('user_id'):
            flash('Action Denied: You cannot delete your own admin account.', 'danger')
            return redirect(url_for('workers'))

        worker.is_active = False
        db.session.commit()

        flash(f'Worker "{worker.username}" has been removed from the system.', 'success')
        return redirect(url_for('workers'))

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL DB ERROR (delete_worker): {e}")
        flash('An internal database error occurred. Please try again.', 'danger')


# --- LOW STOCK REPORT ---
@app.route('/low_stock_report')
@login_required
def low_stock_report():
    current_company_id = session.get('company_id')

    # Only flags products with min_stock > 0 (products set to 0 have alerts disabled)
    low_stock_products = Product.query.filter(
        Product.company_id == current_company_id,
        Product.is_active == True,
        Product.min_stock > 0,
        ((Product.packages * Product.units_per_package) + Product.single_units) <= Product.min_stock
    ).all()

    return render_template('low_stock_report.html', products=low_stock_products)



