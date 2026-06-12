import os
import re
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from flask_wtf.csrf import CSRFProtect

# 1. Cargar las variables del archivo .env al sistema
load_dotenv()
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')
# Inicializamos la aplicación Flask
app = Flask(__name__)


# 2. Configuración básica de seguridad extrayendo el valor de la variable
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# 3. Actualizamos la URI apuntando a la variable de entorno
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializamos SQLAlchemy
db = SQLAlchemy(app)

csrf = CSRFProtect(app)

#--------------------------------------------------------
# ... (el resto de tu código queda exactamente igual) ...

#--------------------------------------------------------





# Decorador para proteger rutas que requieren sesión activa
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no hay un 'user_id' en la sesión, redirige al login
        if session.get('user_id') is None:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        # Si la sesión existe, permite que la ruta continúe normalmente
        return f(*args, **kwargs)
    return decorated_function

# Importamos los modelos (ahora en inglés)
from models import Company, User, Product, Transaction

# Esto crea automáticamente el archivo inventory.db y todas las tablas si no existen
with app.app_context():
    db.create_all()



# ==========================================
# FILTRO JINJA: ZONA HORARIA LOCAL
# ==========================================
@app.template_filter('localtime')
def localtime_filter(utc_dt):
    # Si por alguna razón el dato viene vacío, no hacemos nada
    if not utc_dt:
        return ""
    
    # Ajuste matemático: Restamos 4 horas al tiempo universal (UTC-4)
    local_dt = utc_dt - timedelta(hours=4)
    
    # Lo formateamos a un estilo de 12 horas más amigable (Ej: 2026-06-04 04:15 PM)
    return local_dt.strftime('%Y-%m-%d %I:%M %p')



# ==========================================
# PRACTICA PARA ORM
# ==========================================

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
            return redirect(url_for('test') )
        try:
            new_product = Product(
                name = test_name,
                sku = test_sku,
                notes = test_notes,
                single_units = test_units,
                min_stock = min,
                packages =test_packages,
                units_per_package = test_u_packages,
                company_id = session.get('company_id')
            )
            db.session.add(new_product)
            db.session.commit()
            flash(' funciono creo ._.  ', 'success')
            return redirect(url_for('test') )
        except Exception as e:
            db.session.rollback()
            flash(e)
    list_products = Product.query.all()
          
    return render_template('test.html', productos = list_products)













# ==========================================
# RUTA PRINCIPAL (EL DASHBOARD CON ESTADÍSTICAS)
# ==========================================
@app.route('/')
@login_required
def index():
    current_company_id = session.get('company_id')
    
    # 1. Consultas para las Estadísticas Rápidas (KPIs)
    total_products = Product.query.filter_by(company_id=current_company_id, is_active=True).count()
    total_staff = User.query.filter_by(company_id=current_company_id, is_active=True).count()
    total_movements = Transaction.query.join(Product).filter(Product.company_id == current_company_id).count()
    
    # 2. Consultamos las últimas 10 transacciones
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




    
    # 3. Enviamos todo a la vista
    return render_template('dashboard.html', 
                           transactions=recent_transactions,
                           total_products=total_products,
                           total_staff=total_staff,
                           total_movements=total_movements,
                           has_low_stock = has_low_stock)





# ==========================================
# RUTA: REGISTRO DE EMPRESA Y MANAGER (CREATE)
# ==========================================
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
            # 1. Creamos la empresa primero
            new_company = Company(name=company_name)
            db.session.add(new_company)
            # CRÍTICO: Usamos flush() para que SQLite asigne un ID a la empresa, 
            # pero sin guardar de forma definitiva aún.
            db.session.flush() 

            # 2. Creamos al usuario Manager conectándolo a esa nueva empresa
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(
                username=username,
                password_hash=hashed_password,
                role='Manager',
                company_id=new_company.id # Vinculamos el ID recién generado
            )
            db.session.add(new_user)
            
            # 3. Guardamos ambos en bloque
            db.session.commit()
            flash('Company registered successfully! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            # ¡MAGIA! Si falla el usuario, la empresa también se borra de la memoria temporal.
            db.session.rollback()
            print(f"CRITICAL DB ERROR (register): {e}")
            flash('An internal database error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')





# Ruta de Inicio de Sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Por seguridad, limpiamos cualquier sesión que pudiera estar activa antes de empezar
    session.clear()

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        # 1. Validación: Comprobar campos vacíos
        if not username or not password:
            flash('Please provide both username and password.', 'danger')
            return redirect(url_for('login'))

        # 2. Buscar al usuario en la base de datos
        user = User.query.filter_by(username=username).first()

        # 3. Validación de seguridad cruzada: 
        # Verificamos que el usuario exista Y que la contraseña coincida con el hash
        if user is None or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
        
        # 4. Validación de negocio (Borrado Lógico): Verificar que la cuenta no esté desactivada
        if not user.is_active:
            flash('This account has been deactivated. Contact administration.', 'danger')
            return redirect(url_for('login'))
        session.permanent = True

        # 5. Creación de la sesión: Guardamos datos vitales en la "cookie" segura
        session['user_id'] = user.id
        session['company_id'] = user.company_id
        session['role'] = user.role

        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')





#--------------------------------------------------------




@app.route('/logout')
def logout():
    # Destruir la sesión actual
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))





#--------------------------------------------------------

# ==========================================
# RUTA: INVENTARIO (BÚSQUEDA + ORDENAMIENTO + PAGINACIÓN)
# ==========================================
@app.route('/inventory')
@login_required
def inventory():
    current_company_id = session.get('company_id')
    
    # 1. Capturamos los parámetros de la URL con valores por defecto
    page = request.args.get('page', 1, type=int)
    search_word = request.args.get('search', '', type=str)
    sort_by = request.args.get('sort_by', 'name', type=str) # Por defecto ordenamos por nombre
    order = request.args.get('order', 'asc', type=str)      # Por defecto de A a la Z
    
    # 2. Consulta base
    query = Product.query.filter_by(company_id=current_company_id, is_active=True)
    
    # 3. Filtro de búsqueda
    if search_word:
        search_term = f"%{search_word}%"
        query = query.filter(
            db.or_(
                Product.sku.ilike(search_term),
                Product.name.ilike(search_term)
            )
        )
    
    # 4. LÓGICA DE ORDENAMIENTO DINÁMICO
    if sort_by == 'sku':
        query = query.order_by(Product.sku.desc() if order == 'desc' else Product.sku.asc())
    elif sort_by == 'packages':
        query = query.order_by(Product.packages.desc() if order == 'desc' else Product.packages.asc())
    elif sort_by == 'single_units':
        query = query.order_by(Product.single_units.desc() if order == 'desc' else Product.single_units.asc())
    elif sort_by == 'total':
        # Cálculo matemático en vivo para ordenar por el total real
        total_calc = (Product.packages * Product.units_per_package) + Product.single_units
        query = query.order_by(total_calc.desc() if order == 'desc' else total_calc.asc())
    else:
        query = query.order_by(Product.name.desc() if order == 'desc' else Product.name.asc())
    
    # 5. Paginamos el resultado final
    pagination = query.paginate(page=page, per_page=15, error_out=False)
    
    # 6. Enviamos TODAS las variables al HTML para que la interfaz sepa qué flechas dibujar
    return render_template('inventory.html', 
                           pagination=pagination, 
                           search_word=search_word, 
                           sort_by=sort_by, 
                           order=order)




# ==========================================
# RUTA: AÑADIR PRODUCTO (CREATE) - VERSIÓN MASIVA
# ==========================================
@app.route('/add_product_bulk', methods=['POST'])
@login_required
def add_product_bulk():
    # ESCUDO RBAC: Solo Managers y Supervisores
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
                    min_stock=int(min_stocks[i] or 0), # <--- NUEVO VALOR
                    company_id=session.get('company_id')
                )
                db.session.add(new_product)
        
        db.session.commit()
        flash('Bulk products added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error saving bulk products.', 'danger')
        
    return redirect(url_for('inventory'))

# ==========================================
# RUTA: EDITAR PRODUCTO (UPDATE)
# ==========================================
@app.route('/edit_product/<int:id>', methods=['POST'])
@login_required
def edit_product(id):
    # ESCUDO RBAC: Solo Managers y Supervisores
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: You do not have permission to edit products.', 'danger')
        return redirect(url_for('inventory'))

    product = Product.query.get_or_404(id)
    
    if product.company_id != session.get('company_id'):
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('inventory'))
    
    try:
        new_packages = int(request.form.get('packages') or 0)
        # ... (el resto de tu código de edit_product se queda igual) ...
        new_single_units = int(request.form.get('single_units') or 0)
        
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

# ==========================================
# RUTA: BORRAR PRODUCTO (DELETE)
# ==========================================
@app.route('/delete_product/<int:id>')
@login_required
def delete_product(id):
    # ESCUDO RBAC: Solo Managers y Supervisores
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: You do not have permission to delete products.', 'danger')
        return redirect(url_for('inventory'))

    product = Product.query.get_or_404(id)
    
    # ... (el resto de tu código de delete_product se queda igual) ...
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







# ==========================================
# RUTA: VER BITÁCORA (BÚSQUEDA + PAGINACIÓN)
# ==========================================
@app.route('/transactions')
@login_required
def transactions():
    current_company_id = session.get('company_id')
    
    # 1. Capturamos la página y la palabra de búsqueda desde la URL
    page = request.args.get('page', 1, type=int)
    search_word = request.args.get('search', '', type=str)
    
    # 2. Iniciamos la consulta base (El equivalente a un doble JOIN en SQL)
    # Unimos Transacciones con Productos y también con Usuarios para poder buscar por el nombre de la persona
    query = Transaction.query.join(Product).join(User).filter(
        Product.company_id == current_company_id
    )
    

    # 3. Si el usuario escribió algo, aplicamos los filtros avanzados
    if search_word:
        # Añadimos los comodines de SQL (%) para buscar coincidencias parciales
        search_term = f"%{search_word}%" 
        
        query = query.filter(
            db.or_(
                Product.sku.ilike(search_term),
                Product.name.ilike(search_term),
                User.username.ilike(search_term),
                Transaction.operation_type.ilike(search_term)
            )
        )
    
    # 4. Ordenamos y paginamos el resultado final
    pagination = query.order_by(Transaction.timestamp.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # 5. Enviamos también la palabra de búsqueda al HTML para mantenerla en la barra
    return render_template('transactions.html', pagination=pagination, search_word=search_word)


# ==========================================
# RUTA: GESTIÓN DE TRABAJADORES (BÚSQUEDA + PAGINACIÓN)
# ==========================================
@app.route('/workers')
@login_required
def workers():
# BLOQUEO ACTUALIZADO: Permitimos a Manager Y a Supervisor
    if session.get('role') not in ['Manager', 'Supervisor']:
        flash('Access Denied: This area is restricted.', 'danger')
        return redirect(url_for('inventory'))


    current_company_id = session.get('company_id')
    
    # 1. Capturamos la página y la palabra de búsqueda
    page = request.args.get('page', 1, type=int)
    search_word = request.args.get('search', '', type=str)
    
    # 2. Consulta base: Usuarios de la empresa actual que estén activos
    query = User.query.filter_by(company_id=current_company_id, is_active=True)
    
    # 3. Aplicamos el filtro si el usuario escribió algo en el buscador
    if search_word:
        search_term = f"%{search_word}%"
        query = query.filter(
            db.or_(
                User.username.ilike(search_term),
                User.role.ilike(search_term) # Permite buscar escribiendo "Manager" o "Worker"
            )
        )
    
    # 4. Ordenamos alfabéticamente y paginamos (10 trabajadores por página)
    pagination = query.order_by(User.username.asc()).paginate(
        page=page, per_page=10, error_out=False
    )
    
    # 5. Enviamos la paginación y la palabra buscada al HTML
    return render_template('workers.html', pagination=pagination, search_word=search_word)



# ==========================================
# RUTA: AÑADIR TRABAJADOR (CREATE)
# ==========================================
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

# ==========================================
# RUTA: EDITAR TRABAJADOR (UPDATE)
# ==========================================
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






# ==========================================
# RUTA: BORRAR TRABAJADOR (DELETE)
# ==========================================
@app.route('/delete_worker/<int:id>')
@login_required
def delete_worker(id):
    # BLOQUEO DE SEGURIDAD (RBAC)
    if session.get('role') != 'Manager':
        flash('Access Denied: This area is restricted to Management only.', 'danger')
        return redirect(url_for('inventory'))
        
    worker = User.query.get_or_404(id)
    
    try:

        # Seguridad de empresa
        if worker.company_id != session.get('company_id'):
            flash('Unauthorized action.', 'danger')
            return redirect(url_for('workers'))
            
        # Regla de negocio: Prevención de auto-borrado
        if worker.id == session.get('user_id'):
            flash('Action Denied: You cannot delete your own admin account.', 'danger')
            return redirect(url_for('workers'))
            
        # Borrado lógico
        worker.is_active = False
        db.session.commit()
        
        flash(f'Worker "{worker.username}" has been removed from the system.', 'success')
        return redirect(url_for('workers'))

    except Exception as e:
        # ¡EL SALVAVIDAS! Si algo falla arriba, deshacemos todo para evitar datos corruptos
        db.session.rollback()
        
        # Imprimimos el error real en la terminal para que nosotros (los ingenieros) lo veamos
        print(f"CRITICAL DB ERROR (delete_worker): {e}")
        
        # Le mostramos un mensaje amable y genérico al usuario final
        flash('An internal database error occurred. Please try again.', 'danger')
    # ---------------------------------------------------------




# ==========================================
# RUTA: REPORTE DE STOCK BAJO
# ==========================================
@app.route('/low_stock_report')
@login_required
def low_stock_report():
    current_company_id = session.get('company_id')
    
    # Buscamos productos donde (paquetes*unidad_por_paquete + sueltas) <= min_stock
    # Solo si min_stock es mayor a 0 (para que no alerte productos sin configurar)
    low_stock_products = Product.query.filter(
        Product.company_id == current_company_id,
        Product.is_active == True,
        Product.min_stock > 0,
        ((Product.packages * Product.units_per_package) + Product.single_units) <= Product.min_stock
    ).all()
    
    return render_template('low_stock_report.html', products=low_stock_products)