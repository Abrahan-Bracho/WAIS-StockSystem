from app import db
from datetime import datetime

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    users = db.relationship('User', backref='company', lazy=True)
    products = db.relationship('Product', backref='company', lazy=True)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'Manager', 'Warehouse_Worker'
    is_active = db.Column(db.Boolean, default=True)  # Soft delete flag

    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.String(200), nullable=True, default='')

    min_stock = db.Column(db.Integer, default=0)

    single_units = db.Column(db.Integer, default=0)       # Loose units not in a package
    packages = db.Column(db.Integer, nullable=True, default=0)
    units_per_package = db.Column(db.Integer, nullable=True, default=0)

    is_active = db.Column(db.Boolean, default=True)  # Soft delete flag

    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relationships expose .user and .product on any Transaction instance
    user = db.relationship('User', backref='transactions')
    product = db.relationship('Product', backref='transactions')

    operation_type = db.Column(db.String(20), nullable=False)
    packages_affected = db.Column(db.Integer, nullable=False)
    units_affected = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
