from app import app, db
from models import Territory, User
import uuid

def create_test_territory():
    with app.app_context():
        # Récupérer l'utilisateur admin
        admin = User.query.filter_by(email='admin@example.com').first()
        
        if not admin:
            print("Erreur: L'utilisateur admin n'existe pas")
            return
        
        # Créer un territoire de test (coordonnées pour Paris)
        test_territory = Territory(
            uuid=str(uuid.uuid4()),
            name="Territoire Test",
            city="Paris",
            polygon_data={
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [2.3412, 48.8566],  # Centre de Paris
                        [2.3512, 48.8566],
                        [2.3512, 48.8666],
                        [2.3412, 48.8666],
                        [2.3412, 48.8566]
                    ]]
                }
            },
            building_stats={
                "building_count": 10,
                "apartment_count": 50
            },
            user_id=admin.id
        )
        
        # Ajouter et sauvegarder dans la base de données
        db.session.add(test_territory)
        db.session.commit()
        
        print(f"Territoire de test créé avec succès! UUID: {test_territory.uuid}")
        print(f"Vous pouvez y accéder à l'URL: /territory/{test_territory.uuid}")

if __name__ == '__main__':
    create_test_territory()
