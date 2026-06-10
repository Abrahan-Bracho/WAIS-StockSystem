from app import app, db
from models import Company, User, Product, Transaction

# Este script abre el contexto de la aplicación y crea todo desde cero
with app.app_context():
    db.drop_all() # Borra todo lo viejo
    db.create_all() # Crea todas las tablas basándose en tus clases actuales
    print("Base de datos reiniciada con éxito.")