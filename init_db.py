from app import app, db
from models import User, Territory, UserSettings

def init_db():
    with app.app_context():
        # Créer toutes les tables
        db.create_all()
        
        # Vérifier si un utilisateur admin existe déjà
        admin = User.query.filter_by(email='admin@example.com').first()
        if not admin:
            # Créer un utilisateur admin par défaut
            admin = User(email='admin@example.com', name='Admin')
            admin.set_password('password123')  # Changez ce mot de passe en production !
            db.session.add(admin)
            
            # Créer les paramètres par défaut pour l'admin
            settings = UserSettings(
                user=admin,
                territory_number_format='T-{number}',
                territory_start_number=1,
                show_large_buildings=True,
                large_building_threshold=10,
                default_map_zoom=14
            )
            db.session.add(settings)
            
            db.session.commit()
            print("Base de données initialisée avec un utilisateur admin")
        else:
            print("L'utilisateur admin existe déjà")

if __name__ == '__main__':
    init_db()
