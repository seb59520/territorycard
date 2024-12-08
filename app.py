import os
import uuid
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from urllib.parse import urlparse
from datetime import datetime
import qrcode
from models import db, User, Territory, UserSettings
from forms import LoginForm, RegistrationForm, UserSettingsForm
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/territory_divider')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuration des dossiers
app.config['QR_FOLDER'] = os.path.join('static', 'qrcodes')
os.makedirs(app.config['QR_FOLDER'], exist_ok=True)

# Initialisation des extensions
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Email ou mot de passe invalide')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Se connecter', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data, name=form.name.data)
        user.set_password(form.password.data)
        db.session.add(user)
        
        # Créer les paramètres par défaut
        settings = UserSettings(user=user)
        db.session.add(settings)
        
        db.session.commit()
        flash('Félicitations, vous êtes maintenant inscrit !')
        return redirect(url_for('login'))
    return render_template('register.html', title='Inscription', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = UserSettingsForm()
    if request.method == 'GET':
        # Pré-remplir le formulaire avec les paramètres actuels
        settings = current_user.settings
        if settings:
            form.territory_number_format.data = settings.territory_number_format
            form.territory_start_number.data = settings.territory_start_number
            form.show_large_buildings.data = settings.show_large_buildings
            form.large_building_threshold.data = settings.large_building_threshold
            form.default_map_center_lat.data = settings.default_map_center_lat
            form.default_map_center_lng.data = settings.default_map_center_lng
            form.default_map_zoom.data = settings.default_map_zoom
    
    if form.validate_on_submit():
        settings = current_user.settings or UserSettings(user=current_user)
        settings.territory_number_format = form.territory_number_format.data
        settings.territory_start_number = form.territory_start_number.data
        settings.show_large_buildings = form.show_large_buildings.data
        settings.large_building_threshold = form.large_building_threshold.data
        settings.default_map_center_lat = form.default_map_center_lat.data
        settings.default_map_center_lng = form.default_map_center_lng.data
        settings.default_map_zoom = form.default_map_zoom.data
        
        if not current_user.settings:
            db.session.add(settings)
        db.session.commit()
        
        flash('Paramètres mis à jour avec succès!')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', title='Paramètres', form=form)

from flask import send_from_directory
from dotenv import load_dotenv
import json
import xml.etree.ElementTree as ET
from PIL import Image
import qrcode
import uuid
import requests
from flask import jsonify
from datetime import datetime
import os

# Vérification de la clé API
api_key = os.getenv('GOOGLE_MAPS_API_KEY')
if not api_key:
    print("ERREUR: La clé API Google Maps n'est pas définie dans le fichier .env")
else:
    print(f"Clé API chargée: {api_key[:5]}...")  # Affiche seulement les 5 premiers caractères pour la sécurité

# Stockage des territoires en mémoire (dans un vrai système, cela serait dans une base de données)
territories_store = {}

def parse_kml(filepath):
    """Parse le fichier KML et retourne les coordonnées des polygones"""
    try:
        app.logger.info(f"Début du parsing du fichier KML: {filepath}")
        
        # Vérifier si le fichier existe
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Le fichier KML n'existe pas: {filepath}")
        
        # Vérifier la taille du fichier
        file_size = os.path.getsize(filepath)
        app.logger.info(f"Taille du fichier: {file_size} bytes")
        
        if file_size == 0:
            raise ValueError("Le fichier KML est vide")
        
        # Lire et afficher le contenu brut du fichier
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            app.logger.info(f"Contenu du fichier KML:\n{content[:1000]}...")  # Affiche les 1000 premiers caractères
        
        # Vérifier que le contenu contient des balises KML basiques
        if '<kml' not in content.lower():
            raise ValueError("Le fichier ne semble pas être un fichier KML valide (balise <kml> non trouvée)")
        
        tree = ET.parse(filepath)
        root = tree.getroot()
        
        app.logger.info(f"Tag racine: {root.tag}")
        app.logger.info(f"Attributs racine: {root.attrib}")
        
        # Afficher la structure du document
        def print_element_tree(element, level=0):
            app.logger.info("  " * level + f"- {element.tag}")
            for child in element:
                print_element_tree(child, level + 1)
        
        app.logger.info("\nStructure du document KML:")
        print_element_tree(root)
        
        # Gestion des namespaces, y compris les namespaces vides
        namespaces = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'ns': '',  # namespace vide
            None: '',  # namespace par défaut
            '': ''     # namespace explicitement vide
        }
        
        # Recherche des coordonnées dans tous les types de géométrie possibles
        coordinates = []
        
        # Chercher dans les Polygons avec différents namespaces et structures
        polygon_paths = [
            './/Polygon/outerBoundaryIs/LinearRing/coordinates',
            './/kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates',
            './/ns:Polygon/ns:outerBoundaryIs/ns:LinearRing/ns:coordinates',
            './/Placemark//Polygon//coordinates',
            './/kml:Placemark//kml:Polygon//kml:coordinates',
            './/Placemark/Polygon/outerBoundaryIs/LinearRing/coordinates',
            './/MultiGeometry/Polygon/outerBoundaryIs/LinearRing/coordinates',
            './/kml:MultiGeometry/kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates',
            './/coordinates',  # Recherche directe des balises coordinates
            './/kml:coordinates'  # Recherche directe avec namespace KML
        ]
        
        def extract_points(coord_str):
            points = []
            app.logger.info(f"Traitement des coordonnées brutes: {coord_str[:100]}...")  # Affiche le début des coordonnées
            
            # Nettoyer la chaîne de coordonnées
            coord_str = coord_str.strip()
            
            # Séparer les points
            coord_parts = [p for p in coord_str.split() if p.strip()]
            app.logger.info(f"Nombre de points trouvés: {len(coord_parts)}")
            
            for point in coord_parts:
                try:
                    parts = point.strip().split(',')
                    app.logger.info(f"Point brut: {point}, parties: {parts}")
                    
                    if len(parts) >= 2:
                        lon, lat = parts[:2]
                        lon = float(lon.strip())
                        lat = float(lat.strip())
                        points.append([lon, lat])
                except Exception as e:
                    app.logger.error(f"Erreur lors du parsing d'un point: {point} - {str(e)}")
            
            return points
        
        # Recherche avec les différents chemins
        for path in polygon_paths:
            app.logger.info(f"\nEssai du chemin: {path}")
            elements = root.findall(path, namespaces)
            app.logger.info(f"Nombre d'éléments trouvés: {len(elements)}")
            
            for coords in elements:
                app.logger.info(f"Trouvé des coordonnées avec le chemin: {path}")
                coord_str = coords.text
                if coord_str:
                    points = extract_points(coord_str)
                    if points:
                        app.logger.info(f"Nombre de points extraits: {len(points)}")
                        app.logger.info(f"Premier point: {points[0]}")
                        coordinates.append(points)
        
        # Si aucune coordonnée n'est trouvée, essayer une recherche récursive
        if not coordinates:
            app.logger.info("\nAucune coordonnée trouvée avec les chemins standards, tentative de recherche récursive...")
            for elem in root.iter():
                if elem.tag.endswith('coordinates'):
                    app.logger.info(f"Trouvé balise coordinates: {elem.tag}")
                    coord_str = elem.text
                    if coord_str:
                        points = extract_points(coord_str)
                        if points:
                            app.logger.info(f"Trouvé {len(points)} points en recherche récursive")
                            coordinates.append(points)
        
        app.logger.info(f"\nNombre total de formes trouvées: {len(coordinates)}")
        if coordinates:
            app.logger.info(f"Premier point du premier polygone: {coordinates[0][0]}")
            return coordinates
        else:
            app.logger.info("Aucune coordonnée trouvée dans le fichier KML")
            return None
            
    except ET.ParseError as e:
        app.logger.error(f"Erreur de parsing XML: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return None
    except Exception as e:
        app.logger.error(f"Erreur lors du parsing KML: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return None

def count_buildings_and_apartments(polygon):
    """Compte le nombre de bâtiments et d'appartements dans un polygone en utilisant Overpass API"""
    try:
        # Construire la requête Overpass pour obtenir plus de détails sur les bâtiments
        # Convertir les coordonnées [lng, lat] en format "lat lng"
        polygon_coords = " ".join([f"{coord[1]} {coord[0]}" for coord in polygon])
        
        # Requête pour obtenir tous les bâtiments avec leurs attributs
        query = f"""
        [out:json][timeout:25];
        (
            way(poly:"{polygon_coords}")["building"];
            relation(poly:"{polygon_coords}")["building"];
        );
        out body;
        >;
        out skel qt;
        """
        
        # Appeler l'API Overpass
        overpass_url = "https://overpass-api.de/api/interpreter"
        app.logger.info(f"Envoi de la requête Overpass : {query}")
        response = requests.post(overpass_url, data={"data": query})
        
        if response.status_code != 200:
            app.logger.error(f"Erreur Overpass API: {response.status_code}")
            app.logger.error(f"Réponse: {response.text}")
            return {'houses': 0, 'apartments': 0, 'apartment_buildings': 0, 'large_buildings': [], 'total_doorbells': 0}
            
        data = response.json()
        buildings = data.get('elements', [])
        app.logger.info(f"Nombre de bâtiments trouvés : {len(buildings)}")
        
        # Analyser les types de bâtiments
        building_types = {}
        for building in buildings:
            tags = building.get('tags', {})
            building_type = tags.get('building', 'unknown')
            if building_type not in building_types:
                building_types[building_type] = 0
            building_types[building_type] += 1
            
        app.logger.info(f"Types de bâtiments trouvés : {building_types}")
        
        # Analyser les attributs des bâtiments
        total_houses = 0
        total_apartments = 0
        apartment_buildings = 0
        total_doorbells = 0
        large_buildings = []
        
        for building in buildings:
            tags = building.get('tags', {})
            building_type = tags.get('building', '')
            
            # Loguer les tags pour analyse
            app.logger.info(f"Tags du bâtiment : {tags}")
            
            # Essayer de déterminer le type de bâtiment en utilisant d'autres tags
            if building_type in ['yes', 'unknown', '']:
                # Vérifier les autres tags pour deviner le type
                if 'building:levels' in tags:
                    levels = int(tags.get('building:levels', '1'))
                    if levels >= 3:  # Si le bâtiment a 3 étages ou plus, c'est probablement un immeuble
                        building_type = 'apartments'
                    else:
                        building_type = 'house'  # Sinon, c'est probablement une maison
                else:
                    # Par défaut, considérer comme une maison
                    building_type = 'house'
            
            # Compter les maisons
            if building_type in ['house', 'detached', 'residential', 'terrace', 'yes']:
                total_houses += 1
                total_doorbells += 1  # Une sonnette par maison
                
            # Compter les appartements et immeubles
            elif building_type in ['apartments', 'apartment']:
                apartment_buildings += 1
                # Estimer le nombre d'appartements basé sur les étages
                levels = int(tags.get('building:levels', '3'))  # Par défaut 3 étages
                apartments_per_level = 2  # estimation par défaut
                estimated_apartments = levels * apartments_per_level
                total_apartments += estimated_apartments
                total_doorbells += estimated_apartments
                
            # Vérifier les sonnettes explicitement définies
            doorbells = tags.get('building:doorbells', tags.get('addr:doorbells', '0'))
            try:
                explicit_doorbells = int(doorbells)
                if explicit_doorbells > 0:
                    # Si nous avons un nombre explicite de sonnettes, utiliser cette valeur
                    total_doorbells = total_doorbells - estimated_apartments + explicit_doorbells
                    total_apartments = total_apartments - estimated_apartments + explicit_doorbells
            except (ValueError, UnboundLocalError):
                pass
                
            # Identifier les grands bâtiments
            if building_type in ['commercial', 'retail', 'office', 'industrial']:
                large_buildings.append({
                    'type': building_type,
                    'levels': tags.get('building:levels', 'unknown'),
                    'name': tags.get('name', 'unknown')
                })
        
        result = {
            'houses': total_houses,
            'apartments': total_apartments,
            'apartment_buildings': apartment_buildings,
            'large_buildings': large_buildings,
            'total_doorbells': total_doorbells,
            'building_types': building_types  # Ajouter les statistiques détaillées
        }
        
        app.logger.info(f"Statistiques des bâtiments : {result}")
        return result
        
    except Exception as e:
        app.logger.error(f"Erreur lors du comptage des bâtiments: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return {'houses': 0, 'apartments': 0, 'apartment_buildings': 0, 'large_buildings': [], 'total_doorbells': 0}

def get_city_from_coordinates(polygon):
    """Récupère le nom de la ville à partir des coordonnées du centre du polygone"""
    try:
        # Calculer le centre du polygone
        lats = [p[1] for p in polygon]
        lngs = [p[0] for p in polygon]
        center_lat = sum(lats) / len(lats)
        center_lng = sum(lngs) / len(lngs)
        
        # Utiliser Nominatim pour obtenir les informations de localisation
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={center_lat}&lon={center_lng}"
        headers = {
            'User-Agent': 'TerritoryDivider/1.0'
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            
            # Essayer différents niveaux d'adresse pour obtenir la ville
            city = (
                address.get('city') or 
                address.get('town') or 
                address.get('village') or 
                address.get('municipality') or
                address.get('suburb') or
                'Ville inconnue'
            )
            
            return city
            
        return "Ville inconnue"
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération de la ville: {str(e)}")
        return "Ville inconnue"

def get_next_territory_number():
    """Retourne le prochain numéro de territoire disponible"""
    last_territory = Territory.query.filter(
        Territory.name.like('T%')
    ).order_by(Territory.name.desc()).first()
    
    if not last_territory:
        return 1
    
    try:
        # Extraire le numéro du nom (ex: T1-Paris -> 1)
        last_number = int(last_territory.name.split('-')[0][1:])
        return last_number + 1
    except (ValueError, IndexError):
        return 1

@app.route('/upload-kml', methods=['POST'])
@login_required
def upload_kml():
    try:
        if 'kml_file' not in request.files:
            app.logger.error("Erreur: Pas de fichier dans la requête")
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['kml_file']
        if file.filename == '':
            app.logger.error("Erreur: Nom de fichier vide")
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.kml'):
            app.logger.error("Erreur: Le fichier n'est pas un KML")
            return jsonify({'error': 'File must be a KML file'}), 400
        
        # Sauvegarde du fichier KML
        filename = str(uuid.uuid4()) + '.kml'
        filepath = os.path.join('uploads', filename)
        file.save(filepath)
        
        app.logger.info(f"Fichier KML sauvegardé: {filepath}")
        
        # Parser le fichier KML
        coordinates = parse_kml(filepath)
        
        if coordinates is None:
            return jsonify({'error': 'Failed to parse KML file'}), 400
        
        if not coordinates:
            return jsonify({'error': 'No valid coordinates found in KML file'}), 400
        
        app.logger.info(f"Coordonnées extraites: {len(coordinates)} polygones trouvés")
        
        # Vérifier la validité des coordonnées
        valid_coordinates = []
        for polygon in coordinates:
            if isinstance(polygon, list) and len(polygon) > 0:
                valid_points = []
                for point in polygon:
                    if isinstance(point, list) and len(point) == 2:
                        if isinstance(point[0], (int, float)) and isinstance(point[1], (int, float)):
                            valid_points.append(point)
                if valid_points:
                    valid_coordinates.append(valid_points)
        
        if not valid_coordinates:
            return jsonify({'error': 'No valid coordinates found after validation'}), 400
        
        app.logger.info(f"Nombre de polygones valides: {len(valid_coordinates)}")
        app.logger.info(f"Premier polygone: {valid_coordinates[0][:3]}...")  # Affiche les 3 premiers points
        
        return jsonify({
            'coordinates': valid_coordinates
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors du traitement du fichier KML: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/generate_territories', methods=['POST'])
@login_required
def generate_territories():
    try:
        app.logger.info("Début de generate_territories")
        data = request.json
        app.logger.info(f"Données reçues : {data}")
        
        if not data or 'coordinates' not in data:
            app.logger.error("Erreur : pas de coordonnées fournies")
            return jsonify({'error': 'No coordinates provided'}), 400

        coordinates = data['coordinates']
        app.logger.info(f"Coordonnées : {coordinates}")
        
        if not coordinates or not isinstance(coordinates, list):
            app.logger.error("Erreur : format de coordonnées invalide")
            return jsonify({'error': 'Invalid coordinates data'}), 400

        app.logger.info("Récupération de la ville...")
        city = get_city_from_coordinates(coordinates)
        app.logger.info(f"Ville trouvée : {city}")
        
        app.logger.info("Comptage des bâtiments...")
        building_stats = count_buildings_and_apartments(coordinates)
        app.logger.info(f"Statistiques des bâtiments : {building_stats}")
        
        # Créer le GeoJSON
        polygon_data = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coordinates]
            }
        }
        
        # Générer un UUID pour le territoire
        territory_id = str(uuid.uuid4())
        app.logger.info(f"ID du territoire : {territory_id}")
        
        # Obtenir le prochain numéro de territoire
        next_number = get_next_territory_number()
        territory_name = f"T{next_number}-{city}"
        app.logger.info(f"Nom du territoire : {territory_name}")
        
        # Créer le QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        territory_url = f"{request.host_url}territory/{territory_id}"
        qr.add_data(territory_url)
        qr.make(fit=True)

        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_filename = f"{territory_id}.png"
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        qr_image.save(qr_path)
        app.logger.info(f"QR code créé : {qr_path}")
        
        # Créer le territoire dans la base de données
        territory = Territory(
            uuid=territory_id,
            name=territory_name,
            city=city,
            polygon_data=polygon_data,
            building_stats=building_stats,
            user=current_user
        )
        app.logger.info("Territoire créé, ajout à la base de données...")
        db.session.add(territory)
        db.session.commit()
        app.logger.info("Territoire enregistré dans la base de données")
        
        # Ajouter le chemin du QR code à la réponse
        territory_dict = territory.to_dict()
        territory_dict['qr_code'] = url_for('static', filename=f'qrcodes/{qr_filename}')
        
        app.logger.info("Envoi de la réponse au client")
        return jsonify({
            'territories': [territory_dict]
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la génération des territoires: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/territory/<uuid>')
@login_required
def view_territory(uuid):
    territory = Territory.query.filter_by(uuid=uuid).first_or_404()
    return render_template('territory.html', 
                         territory=territory, 
                         google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/territory/<uuid>/delete', methods=['POST'])
@login_required
def delete_territory(uuid):
    territory = Territory.query.filter_by(uuid=uuid).first_or_404()
    
    # Vérifier que l'utilisateur est autorisé à supprimer ce territoire
    if territory.user_id != current_user.id:
        flash('Vous n\'êtes pas autorisé à supprimer ce territoire.', 'danger')
        return redirect(url_for('index'))
    
    try:
        # Supprimer le QR code associé
        qr_path = os.path.join(app.config['QR_FOLDER'], f'{territory.uuid}.png')
        if os.path.exists(qr_path):
            os.remove(qr_path)
        
        # Supprimer le territoire de la base de données
        db.session.delete(territory)
        db.session.commit()
        
        flash('Le territoire a été supprimé avec succès.', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Une erreur est survenue lors de la suppression du territoire : {str(e)}', 'danger')
        return redirect(url_for('view_territory', uuid=uuid))

@app.route('/territories/print/<city>')
@login_required
def print_territories_by_city(city):
    """Affiche tous les territoires d'une ville pour impression"""
    territories = Territory.query.filter_by(city=city).order_by(Territory.name).all()
    return render_template(
        'print_territories.html',
        territories=territories,
        city=city,
        google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY')
    )

@app.route('/territories/cities')
@login_required
def list_cities():
    # Récupérer tous les territoires de l'utilisateur
    territories = Territory.query.filter_by(user_id=current_user.id).all()
    
    # Organiser les territoires par ville
    cities = {}
    for territory in territories:
        if territory.city not in cities:
            cities[territory.city] = {
                'count': 0,
                'territories': []
            }
        cities[territory.city]['count'] += 1
        cities[territory.city]['territories'].append({
            'id': territory.uuid,
            'name': territory.name,
            'stats': territory.building_stats
        })
    
    return render_template('cities.html', cities=cities)

@app.route('/territory/<uuid>/rename', methods=['POST'])
@login_required
def rename_territory(uuid):
    territory = Territory.query.filter_by(uuid=uuid, user_id=current_user.id).first_or_404()
    new_name = request.json.get('name')
    if not new_name:
        return jsonify({'error': 'No name provided'}), 400
    
    territory.name = new_name
    db.session.commit()
    return jsonify({'success': True, 'name': new_name})

@app.route('/territories/delete', methods=['POST'])
@login_required
def delete_territories():
    territory_ids = request.json.get('territories', [])
    if not territory_ids:
        return jsonify({'error': 'No territories provided'}), 400
        
    try:
        # Supprimer les QR codes
        for uuid in territory_ids:
            qr_path = os.path.join(app.config['QR_FOLDER'], f"{uuid}.png")
            if os.path.exists(qr_path):
                os.remove(qr_path)
        
        # Supprimer les territoires de la base de données
        Territory.query.filter(
            Territory.uuid.in_(territory_ids),
            Territory.user_id == current_user.id
        ).delete(synchronize_session=False)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def calculate_stats(territories):
    """Calcule les statistiques pour une liste de territoires"""
    total_houses = 0
    total_apartments = 0
    total_buildings = 0
    
    for territory in territories:
        if territory.building_stats:
            total_houses += territory.building_stats.get('houses', 0)
            total_apartments += territory.building_stats.get('apartments', 0)
            total_buildings += territory.building_stats.get('apartment_buildings', 0)
    
    return {
        'nb_territoires': len(territories),
        'nb_maisons': total_houses,
        'nb_appartements': total_apartments,
        'nb_immeubles': total_buildings,
        'nb_sonnettes': total_houses + total_apartments
    }

@app.route('/statistics')
@login_required
def statistics():
    """Affiche les statistiques globales et par ville"""
    # Récupérer toutes les villes
    cities = db.session.query(Territory.city).distinct().order_by(Territory.city).all()
    cities = [city[0] for city in cities]
    
    # Statistiques globales
    all_territories = Territory.query.all()
    global_stats = calculate_stats(all_territories)
    
    # Statistiques par ville
    city_stats = {}
    for city in cities:
        territories = Territory.query.filter_by(city=city).all()
        stats = calculate_stats(territories)
        city_stats[city] = stats
    
    return render_template(
        'statistics.html',
        global_stats=global_stats,
        city_stats=city_stats
    )

@app.route('/list_territories')
@login_required
def list_territories():
    territories = Territory.query.filter_by(user=current_user).order_by(Territory.created_at.desc()).all()
    return jsonify({
        'territories': [t.to_dict() for t in territories]
    })

@app.route('/')
@login_required
def index():
    # Coordonnées de La Madeleine, 59
    default_center = {
        'lat': 50.6568,  # Latitude de La Madeleine
        'lng': 3.0726    # Longitude de La Madeleine
    }
    
    territories = Territory.query.filter_by(user=current_user).order_by(Territory.created_at.desc()).all()
    return render_template('index.html', 
                         territories=territories,
                         default_center=default_center,
                         google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    app.run(port=5001, debug=True)
