from app import db
from datetime import datetime

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # Relaciones
    users = db.relationship('User', backref='company', lazy=True)
    products = db.relationship('Product', backref='company', lazy=True)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'Manager', 'Warehouse_Worker'
    is_active = db.Column(db.Boolean, default=True) # Borrado lógico
    
    # Llave foránea: Relación con Company
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)




class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(50), nullable=False)

    notes = db.Column(db.String(200), nullable=True, default='') 

    single_units = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=0)
    
    # Lógica de empaques e inventario
    single_units = db.Column(db.Integer, default=0) # Cantidad suelta
    packages = db.Column(db.Integer, nullable=True, default=0) # Bultos
    units_per_package = db.Column(db.Integer, nullable=True, default=0)
    
    is_active = db.Column(db.Boolean, default=True) # Borrado lógico
    
    # Llave foránea: Relación con Company
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)


    



class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    
    # Llaves foráneas para la base de datos
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # ==========================================
    # RELACIONES (La magia para Jinja)
    # ==========================================
    user = db.relationship('User', backref='transactions')
    product = db.relationship('Product', backref='transactions')
    # ==========================================
    
    operation_type = db.Column(db.String(20), nullable=False)
    packages_affected = db.Column(db.Integer, nullable=False)
    units_affected = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)