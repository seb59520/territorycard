import os
import uuid
import requests
import traceback
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
    app.logger.info("Login route accessed")
    if current_user.is_authenticated:
        app.logger.info("User already authenticated, redirecting to index")
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        app.logger.info(f"Login form submitted for email: {form.email.data}")
        user = User.query.filter_by(email=form.email.data).first()
        
        if user is None:
            app.logger.warning(f"No user found with email: {form.email.data}")
            flash('Email ou mot de passe invalide')
            return redirect(url_for('login'))
            
        if not user.check_password(form.password.data):
            app.logger.warning(f"Invalid password for user: {form.email.data}")
            flash('Email ou mot de passe invalide')
            return redirect(url_for('login'))
            
        if not user.is_active:
            app.logger.warning(f"Inactive user attempted login: {form.email.data}")
            flash('Ce compte est désactivé')
            return redirect(url_for('login'))
        
        app.logger.info(f"Successful login for user: {form.email.data}")
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    
    return render_template('login.html', title='Connexion', form=form)

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

import tempfile
import traceback

def parse_kml(kml_file):
    """Parse un fichier KML et retourne une liste de territoires avec leurs coordonnées"""
    app.logger.info("=== Début du parsing KML ===")
    try:
        # Créer un fichier temporaire
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, 'temp.kml')
        
        # Lire et réécrire le fichier pour gérer le BOM et autres problèmes d'encodage
        content = kml_file.read().decode('utf-8-sig')  # utf-8-sig gère le BOM
        app.logger.info(f"Contenu du fichier (premiers 500 caractères): {content[:500]}")
        
        # Vérifier si le contenu ressemble à du KML
        if not ('<kml' in content or '<Placemark' in content):
            app.logger.error("Le fichier ne semble pas être un KML valide")
            return False, "Le fichier ne semble pas être un KML valide"
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        app.logger.info(f"Fichier temporaire créé: {temp_path}")

        # Parser le fichier KML
        try:
            tree = ET.parse(temp_path)
            root = tree.getroot()
        except ET.ParseError as e:
            app.logger.error(f"Erreur de parsing XML: {str(e)}")
            return False, f"Erreur de parsing XML: {str(e)}"
        
        # Gérer l'espace de noms KML
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        # Trouver tous les placemarks
        placemarks = root.findall('.//kml:Placemark', ns)
        if not placemarks:
            placemarks = root.findall('.//Placemark')  # Essayer sans namespace
        
        if not placemarks:
            app.logger.error("Aucun Placemark trouvé dans le fichier KML")
            return False, "Aucun territoire (Placemark) trouvé dans le fichier KML"
        
        app.logger.info(f"Nombre total de territoires trouvés: {len(placemarks)}")
        
        territories = []
        for i, placemark in enumerate(placemarks, 1):
            try:
                app.logger.info(f"Traitement du territoire {i}/{len(placemarks)}")
                
                # Extraire le nom et les informations supplémentaires
                name = placemark.findtext('kml:name', '', ns) or placemark.findtext('name', '')
                territory_type = placemark.findtext('kml:territoryType', '', ns) or placemark.findtext('territoryType', '')
                territory_number = placemark.findtext('kml:territoryNumber', '', ns) or placemark.findtext('territoryNumber', '')
                
                app.logger.info(f"Nom du territoire: {name}")
                app.logger.info(f"Type de territoire: {territory_type}")
                app.logger.info(f"Numéro de territoire: {territory_number}")
                
                # Extraire les coordonnées
                coords_elem = None
                for path in ['.//kml:LinearRing/kml:coordinates', './/LinearRing/coordinates']:
                    coords_elem = placemark.find(path, ns)
                    if coords_elem is not None:
                        break
                
                if coords_elem is None or not coords_elem.text:
                    app.logger.warning(f"Pas de coordonnées trouvées pour le territoire {name}")
                    continue
                
                coords_text = coords_elem.text.strip()
                coords_list = []
                
                # Parser les coordonnées
                for coord in coords_text.split():
                    try:
                        parts = coord.split(',')
                        if len(parts) >= 2:
                            lon, lat = float(parts[0]), float(parts[1])
                            coords_list.append([lon, lat])
                    except (ValueError, IndexError) as e:
                        app.logger.warning(f"Erreur lors du parsing des coordonnées {coord}: {e}")
                        continue
                
                if not coords_list:
                    app.logger.warning(f"Aucune coordonnée valide trouvée pour le territoire {name}")
                    continue
                
                # Calculer le centre du polygone pour déterminer la ville
                center_lat = sum(point[1] for point in coords_list) / len(coords_list)
                center_lon = sum(point[0] for point in coords_list) / len(coords_list)
                
                # Obtenir le nom de la ville
                city = get_city_from_coordinates([[center_lon, center_lat]])
                app.logger.info(f"Ville déterminée pour le territoire {name}: {city}")
                
                territory = {
                    'name': name,
                    'type': territory_type,
                    'number': territory_number,
                    'coordinates': coords_list,
                    'city': city
                }
                territories.append(territory)
                app.logger.info(f"Territoire ajouté: {territory['name']} ({territory['number']})")
                
            except Exception as e:
                app.logger.error(f"Erreur lors du traitement du territoire {i}: {e}")
                app.logger.error(traceback.format_exc())
                continue
        
        if not territories:
            app.logger.error("Aucun territoire valide n'a pu être extrait du fichier KML")
            return False, "Aucun territoire valide n'a pu être extrait du fichier KML"
        
        app.logger.info(f"=== Fin du parsing KML avec succès: {len(territories)} territoires extraits ===")
        return True, territories
        
    except Exception as e:
        app.logger.error(f"Erreur lors du parsing KML: {e}")
        app.logger.error(traceback.format_exc())
        return False, str(e)
    finally:
        try:
            # Nettoyer les fichiers temporaires
            if os.path.exists(temp_path):
                os.remove(temp_path)
            os.rmdir(temp_dir)
            app.logger.info("Fichiers temporaires nettoyés")
        except Exception as e:
            app.logger.error(f"Erreur lors du nettoyage des fichiers temporaires: {e}")

def count_buildings_and_apartments(coordinates):
    """Compte le nombre total de sonnettes dans un territoire"""
    try:
        # Convertir les coordonnées au format requis par Overpass
        overpass_coords = []
        for coord in coordinates:
            if isinstance(coord, dict):
                overpass_coords.append(f"{coord['lat']} {coord['lng']}")
            else:
                overpass_coords.append(f"{coord[1]} {coord[0]}")

        # Créer la requête Overpass
        area = " ".join(overpass_coords)
        query = f"""
        [out:json][timeout:25];
        (
          way(poly:"{area}")["building"];
          relation(poly:"{area}")["building"];
        );
        out body;
        >;
        out skel qt;
        """

        # Faire la requête à l'API Overpass
        overpass_url = "http://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data=query)
        data = response.json()

        total_doorbells = 0

        # Analyser chaque bâtiment
        for element in data['elements']:
            if element['type'] in ['way', 'relation'] and 'tags' in element:
                tags = element['tags']
                building_type = tags.get('building', 'unknown')
                
                # Compter les sonnettes
                if building_type in ['apartments', 'residential'] or 'apartments' in tags:
                    # Pour les immeubles, estimer le nombre d'appartements
                    levels = int(tags.get('building:levels', '3'))
                    apts_per_floor = int(tags.get('apartments_per_floor', '2'))
                    total_doorbells += levels * apts_per_floor
                else:
                    # Pour les autres bâtiments, ajouter une sonnette
                    total_doorbells += 1

        return {'total_doorbells': total_doorbells}

    except Exception as e:
        print(f"Erreur lors du comptage des sonnettes : {str(e)}")
        return {'total_doorbells': 0}

def get_city_from_coordinates(polygon):
    """Récupère le nom de la ville à partir des coordonnées du centre du polygone"""
    try:
        # Calculer le centre du polygone
        lats = [p[1] for p in polygon]
        lngs = [p[0] for p in polygon]
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lngs) / len(lngs)
        
        # Utiliser Nominatim pour obtenir les informations de localisation
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={center_lat}&lon={center_lon}"
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
        app.logger.info("=== Début de l'upload KML ===")
        
        if 'file' not in request.files:
            app.logger.error("Aucun fichier n'a été uploadé")
            return jsonify({'error': 'Aucun fichier n\'a été uploadé'}), 400
            
        file = request.files['file']
        app.logger.info(f"Fichier reçu: {file.filename}")
        
        if file.filename == '':
            app.logger.error("Nom de fichier vide")
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
            
        if not file.filename.lower().endswith('.kml'):
            app.logger.error("Le fichier n'est pas un KML")
            return jsonify({'error': 'Le fichier doit être au format KML'}), 400
        
        # Parser le fichier KML
        app.logger.info("Parsing du fichier KML...")
        success, result = parse_kml(file)
        
        if not success:
            app.logger.error(f"Erreur lors du parsing: {result}")
            return jsonify({'error': result}), 400
        
        # Stocker les coordonnées pour une utilisation ultérieure
        territories_store['coordinates'] = result
        app.logger.info(f"Territoires stockés: {len(result)} territoires")
        
        app.logger.info("=== Fin de l'upload KML avec succès ===")
        return jsonify({
            'success': True,
            'message': f"{len(result)} territoires trouvés",
            'territories': result
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'upload: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            'error': 'Une erreur est survenue lors du traitement du fichier',
            'details': str(e)
        }), 500

def generate_territories(kml_data, user_id):
    """Génère des territoires à partir des données KML"""
    app.logger.info("=== Début de la génération des territoires ===")
    try:
        territories = []
        for territory_data in kml_data:
            try:
                # Générer un UUID pour le territoire
                territory_uuid = str(uuid.uuid4())
                app.logger.info(f"UUID généré: {territory_uuid}")

                # Récupérer ou générer le numéro de territoire
                territory_number = territory_data.get('number', '')
                if not territory_number:
                    territory_number = str(get_next_territory_number())
                
                # Récupérer le type de territoire
                territory_type = territory_data.get('type', 'standard')
                
                # Récupérer les coordonnées et calculer les statistiques
                polygon = territory_data.get('coordinates', [])
                if not polygon:
                    app.logger.warning(f"Pas de coordonnées pour le territoire {territory_data.get('name', 'sans nom')}")
                    continue
                
                # Obtenir la ville si elle n'est pas déjà définie
                city = territory_data.get('city')
                if not city:
                    city = get_city_from_coordinates(polygon)
                
                # Compter les bâtiments
                building_stats = count_buildings_and_apartments(polygon)
                
                # Créer le territoire
                territory = Territory(
                    uuid=territory_uuid,
                    name=territory_data.get('name', f'Territoire {territory_number}'),
                    type=territory_type,
                    number=territory_number,
                    city=city,
                    coordinates=polygon,
                    sonnettes=building_stats['total_doorbells'],  # Nombre total de sonnettes
                    user_id=user_id,
                    commentaire=territory_data.get('commentaire', '')
                )
                
                db.session.add(territory)
                territories.append(territory)
                app.logger.info(f"Territoire ajouté: {territory.name} ({territory.number})")
                
            except Exception as e:
                app.logger.error(f"Erreur lors de la génération d'un territoire: {str(e)}")
                app.logger.error(traceback.format_exc())
                continue
        
        if territories:
            try:
                db.session.commit()
                app.logger.info(f"{len(territories)} territoires créés avec succès")
                return True, f"{len(territories)} territoires créés avec succès"
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Erreur lors de la sauvegarde des territoires: {str(e)}")
                app.logger.error(traceback.format_exc())
                return False, f"Erreur lors de la sauvegarde des territoires: {str(e)}"
        else:
            app.logger.warning("Aucun territoire n'a été créé")
            return False, "Aucun territoire n'a été créé"
            
    except Exception as e:
        app.logger.error(f"Erreur lors de la génération des territoires: {str(e)}")
        app.logger.error(traceback.format_exc())
        return False, str(e)

@app.route('/generate_territories', methods=['POST'])
@login_required
def generate_territories_view():
    try:
        app.logger.info("=== Début de la génération des territoires ===")
        coordinates = territories_store.get('coordinates', [])
        app.logger.info(f"Nombre de territoires à générer: {len(coordinates)}")
        app.logger.info(f"Contenu du store: {coordinates}")

        if not coordinates:
            app.logger.error("Aucune coordonnée trouvée dans le store")
            return jsonify({'status': 'error', 'message': 'Aucune coordonnée trouvée'}), 400

        success, result = generate_territories(coordinates, current_user.id)
        if success:
            return jsonify({'status': 'success', 'message': f"Territoires créés avec succès: {', '.join(result)}"}), 200
        else:
            return jsonify({'status': 'error', 'message': f"Erreurs lors de la génération des territoires: {', '.join(result)}"}), 400

    except Exception as e:
        app.logger.error(f"Erreur générale: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500

def generate_google_maps_url(coordinates):
    # Calculer le centre du polygone
    lats = [coord[1] if isinstance(coord, list) else coord['lat'] for coord in coordinates]
    lngs = [coord[0] if isinstance(coord, list) else coord['lng'] for coord in coordinates]
    center_lat = sum(lats) / len(lats)
    center_lng = sum(lngs) / len(lngs)
    
    # Créer l'URL avec le centre et le zoom
    base_url = f"https://www.google.com/maps/search/?api=1&query={center_lat},{center_lng}"
    return base_url

@app.route('/territory/<uuid>')
@login_required
def view_territory(uuid):
    try:
        app.logger.info(f"Affichage du territoire {uuid}")
        territory = Territory.query.filter_by(uuid=uuid).first_or_404()
        
        # Vérifier que l'utilisateur est autorisé
        if territory.user_id != current_user.id:
            app.logger.warning(f"Accès non autorisé au territoire {uuid}")
            flash("Vous n'êtes pas autorisé à voir ce territoire.", "danger")
            return redirect(url_for('index'))
        
        app.logger.info(f"Territoire trouvé : {territory.name}")
        app.logger.info(f"Coordonnées : {territory.coordinates}")
        app.logger.info(f"Commentaire : {territory.commentaire}")
        
        # Générer le QR code pour Google Maps
        maps_url = generate_google_maps_url(territory.coordinates)
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(maps_url)
        qr.make(fit=True)
        
        # Créer l'image QR code
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config['QR_FOLDER'], f'{territory.uuid}.png')
        qr_img.save(qr_path)
        
        # Récupérer la clé API Google Maps
        google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if not google_maps_api_key:
            app.logger.error("Clé API Google Maps non trouvée")
            flash("Erreur : Clé API Google Maps manquante", "danger")
            return redirect(url_for('index'))
            
        app.logger.info("Rendu du template territory.html")
        return render_template('territory.html', 
                             territory=territory, 
                             google_maps_api_key=google_maps_api_key)
                             
    except Exception as e:
        app.logger.error(f"Erreur lors de l'affichage du territoire : {str(e)}")
        app.logger.exception(e)
        flash("Une erreur est survenue lors de l'affichage du territoire.", "danger")
        return redirect(url_for('index'))

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
    """Liste toutes les villes avec leurs statistiques"""
    try:
        app.logger.info("Récupération de la liste des villes...")
        territories = Territory.query.filter_by(user_id=current_user.id).all()
        
        # Pour les requêtes AJAX, renvoyer du JSON
        cities = {}
        for territory in territories:
            if not territory.city:  # Skip territories without city
                continue
                
            if territory.city not in cities:
                cities[territory.city] = {
                    'territories': 0,
                    'houses': 0,
                    'apartments': 0,
                    'sonnettes': 0
                }
            cities[territory.city]['territories'] += 1
            cities[territory.city]['houses'] += territory.buildings or 0
            cities[territory.city]['apartments'] += territory.apartments or 0
            # Gérer le cas où sonnettes n'est pas encore défini dans certains enregistrements
            if hasattr(territory, 'sonnettes'):
                cities[territory.city]['sonnettes'] += territory.sonnettes or 0
        
        # Convertir en liste pour le JSON
        cities_list = [
            {
                'name': city,
                'stats': stats
            }
            for city, stats in cities.items()
            if city  # Ne pas inclure les villes None ou vides
        ]
        
        # Trier par nom de ville
        cities_list.sort(key=lambda x: x['name'])
        
        app.logger.info(f"Villes trouvées : {[city['name'] for city in cities_list]}")
        return jsonify({'cities': cities_list})
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des villes : {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

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

@app.route('/territory/<uuid>/card')
@login_required
def territory_card(uuid):
    territory = Territory.query.filter_by(uuid=uuid).first_or_404()
    return render_template('territory_card.html',
                         territory=territory,
                         google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/territory/<uuid>/analyze', methods=['GET'])
@login_required
def analyze_territory(uuid):
    """Analyse détaillée des statistiques d'un territoire"""
    try:
        territory = Territory.query.filter_by(uuid=uuid).first_or_404()
        
        # Vérifier que l'utilisateur est autorisé
        if territory.user_id != current_user.id:
            flash('Vous n\'êtes pas autorisé à voir ce territoire.', 'danger')
            return redirect(url_for('index'))
        
        # Obtenir les statistiques détaillées
        building_stats = count_buildings_and_apartments(territory.coordinates)
        
        # Ajouter plus de détails sur les bâtiments
        detailed_stats = {
            'buildings': {
                'houses': 0,
                'apartment_buildings': 0,
                'apartments': 0,
                'total_doorbells': building_stats['total_doorbells'],
            },
            'building_types': {},
            'large_buildings': []
        }
        
        return render_template('territory_analysis.html',
                            territory=territory,
                            stats=detailed_stats,
                            google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))
        
    except Exception as e:
        flash(f'Une erreur est survenue : {str(e)}', 'danger')
        return redirect(url_for('view_territory', uuid=uuid))

def calculate_stats(territories):
    """Calcule les statistiques pour une liste de territoires"""
    stats = {
        'nb_territoires': len(territories),
        'nb_maisons': 0,
        'nb_appartements': 0,
        'nb_sonnettes': 0,
        'cities': {}
    }

    for territory in territories:
        city = territory.city or 'Unknown'
        
        # Initialize city stats if not exists
        if city not in stats['cities']:
            stats['cities'][city] = {
                'nb_territoires': 0,
                'nb_maisons': 0,
                'nb_appartements': 0,
                'nb_sonnettes': 0
            }
        
        # Increment territory count for the city
        stats['cities'][city]['nb_territoires'] += 1
        
        # Get building counts if they exist
        buildings = getattr(territory, 'buildings', 0) or 0
        apartments = getattr(territory, 'apartments', 0) or 0
        
        # Calculate total doorbells (sonnettes)
        sonnettes = buildings + apartments
        
        # Update city stats
        stats['cities'][city]['nb_maisons'] += buildings
        stats['cities'][city]['nb_appartements'] += apartments
        stats['cities'][city]['nb_sonnettes'] += sonnettes
        
        # Update global stats
        stats['nb_maisons'] += buildings
        stats['nb_appartements'] += apartments
        stats['nb_sonnettes'] += sonnettes

    return stats

@app.route('/statistics')
@login_required
def statistics():
    """Affiche les statistiques globales et par ville"""
    try:
        # Récupérer tous les territoires de l'utilisateur connecté
        all_territories = Territory.query.filter_by(user_id=current_user.id).all()
        
        # Calculer les statistiques globales
        global_stats = calculate_stats(all_territories)
        
        # Statistiques par ville
        city_stats = {}
        cities = db.session.query(Territory.city).filter_by(user_id=current_user.id).distinct().order_by(Territory.city).all()
        
        for city_tuple in cities:
            city = city_tuple[0]
            if city:  # Ignorer les villes None ou vides
                territories = Territory.query.filter_by(user_id=current_user.id, city=city).all()
                city_stats[city] = calculate_stats(territories)['cities'][city]
        
        return render_template(
            'statistics.html',
            global_stats=global_stats,
            city_stats=city_stats
        )
    except Exception as e:
        app.logger.error(f"Erreur lors du calcul des statistiques: {str(e)}")
        app.logger.error(traceback.format_exc())
        flash("Une erreur est survenue lors du calcul des statistiques.", "error")
        return redirect(url_for('index'))

@app.route('/list_territories')
@login_required
def list_territories():
    territories = Territory.query.filter_by(user=current_user).order_by(Territory.created_at.desc()).all()
    return jsonify({
        'territories': [t.to_dict() for t in territories]
    })

@app.route('/cities')
@login_required
def cities():
    """Affiche la page des villes"""
    return render_template('cities.html', title='Liste des Villes')

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

@app.route('/check_db')
def check_db():
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        db_status = "Database connection OK"
    except Exception as e:
        db_status = f"Database error: {str(e)}"
    
    try:
        # Count users
        user_count = User.query.count()
        users = User.query.all()
        users_info = [{"email": user.email, "is_active": user.is_active} for user in users]
    except Exception as e:
        return jsonify({
            "status": "error",
            "db_status": db_status,
            "error": f"Error querying users: {str(e)}"
        })
    
    return jsonify({
        "status": "success",
        "db_status": db_status,
        "user_count": user_count,
        "users": users_info
    })

def recalculate_territory_stats(territory):
    """Recalcule les statistiques pour un territoire donné"""
    try:
        # Compter les bâtiments
        building_stats = count_buildings_and_apartments(territory.coordinates)
        
        # Mettre à jour les statistiques
        territory.sonnettes = building_stats['total_doorbells']
        
        return True
    except Exception as e:
        app.logger.error(f"Erreur lors du recalcul des statistiques pour {territory.name}: {str(e)}")
        return False

@app.route('/territory/<uuid>/recalculate', methods=['POST'])
@login_required
def recalculate_territory(uuid):
    """Recalcule les statistiques pour un territoire spécifique"""
    try:
        territory = Territory.query.filter_by(uuid=uuid).first_or_404()
        
        # Vérifier que l'utilisateur est autorisé
        if territory.user_id != current_user.id:
            flash('Vous n\'êtes pas autorisé à modifier ce territoire.', 'danger')
            return redirect(url_for('view_territory', uuid=uuid))
        
        if recalculate_territory_stats(territory):
            db.session.commit()
            flash('Statistiques recalculées avec succès.', 'success')
        else:
            flash('Erreur lors du recalcul des statistiques.', 'danger')
            
        return redirect(url_for('view_territory', uuid=uuid))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Une erreur est survenue : {str(e)}', 'danger')
        return redirect(url_for('view_territory', uuid=uuid))

@app.route('/territories/recalculate_all', methods=['POST'])
@login_required
def recalculate_all_territories():
    """Recalcule les statistiques pour tous les territoires de l'utilisateur"""
    try:
        territories = Territory.query.filter_by(user_id=current_user.id).all()
        success_count = 0
        error_count = 0
        
        for territory in territories:
            if recalculate_territory_stats(territory):
                success_count += 1
            else:
                error_count += 1
        
        if success_count > 0:
            db.session.commit()
            
        if error_count == 0:
            flash(f'Statistiques recalculées avec succès pour {success_count} territoires.', 'success')
        else:
            flash(f'Statistiques recalculées pour {success_count} territoires. Erreurs sur {error_count} territoires.', 'warning')
            
        return redirect(url_for('list_territories'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Une erreur est survenue : {str(e)}', 'danger')
        return redirect(url_for('list_territories'))

def get_streets_in_territory(coordinates):
    """Récupère les noms des rues dans un territoire"""
    try:
        app.logger.info("Début de la récupération des rues")
        app.logger.info(f"Coordonnées reçues : {coordinates}")
        
        # Préparer les coordonnées pour la requête Overpass
        polygon_coords = []
        for coord in coordinates:
            if isinstance(coord, dict):
                polygon_coords.append(f"{coord['lat']} {coord['lng']}")
            else:
                polygon_coords.append(f"{coord[1]} {coord[0]}")
        
        # Créer une requête Overpass qui utilise le polygone exact
        polygon_str = " ".join(polygon_coords)
        query = f"""
        [out:json][timeout:60];
        (
          way(poly:"{polygon_str}")[highway][name];
        );
        out body;
        >;
        out skel qt;
        """
        
        app.logger.info(f"Requête Overpass : {query}")

        # Faire la requête à l'API Overpass
        response = requests.post("https://overpass-api.de/api/interpreter", 
                               data=query, 
                               timeout=30,
                               headers={'User-Agent': 'Territory-Divider/1.0'})
        
        app.logger.info(f"Statut de la réponse : {response.status_code}")
        app.logger.info(f"Contenu de la réponse : {response.text[:500]}")

        if response.status_code != 200:
            app.logger.error(f"Erreur Overpass : {response.text}")
            return []
        
        try:
            data = response.json()
        except Exception as e:
            app.logger.error(f"Erreur lors du parsing JSON : {str(e)}")
            app.logger.error(f"Réponse reçue : {response.text[:500]}")
            return []

        # Extraire les informations des rues
        streets_info = {}
        nodes = {node['id']: (node['lat'], node['lon']) for node in data.get('elements', []) if node['type'] == 'node'}
        
        for element in data.get('elements', []):
            if element.get('type') == 'way' and element.get('tags', {}).get('name'):
                name = element['tags']['name']
                nodes_list = element.get('nodes', [])
                
                if len(nodes_list) >= 2:
                    # Calculer le côté de la rue par rapport au polygone
                    start_node = nodes[nodes_list[0]]
                    end_node = nodes[nodes_list[-1]]
                    
                    # Vérifier si les points sont à gauche ou à droite du polygone
                    is_left_side = True
                    for node_id in nodes_list:
                        node = nodes[node_id]
                        point = (node[1], node[0])  # (lon, lat)
                        if point_in_polygon(point, coordinates):
                            is_left_side = False
                            break
                    
                    # Déterminer côté pair/impair
                    side = "côté pair" if is_left_side else "côté impair"
                    
                    if name in streets_info:
                        if side not in streets_info[name]:
                            streets_info[name].append(side)
                    else:
                        streets_info[name] = [side]

        # Formater les résultats
        formatted_streets = []
        for name, sides in sorted(streets_info.items()):
            sides_str = " et ".join(sides)
            formatted_streets.append(f"{name} ({sides_str})")

        app.logger.info(f"Rues trouvées : {formatted_streets}")
        return formatted_streets

    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des rues : {str(e)}")
        app.logger.exception(e)
        return []

def point_in_polygon(point, polygon):
    """Vérifie si un point est à l'intérieur d'un polygone"""
    x, y = point
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0][0], polygon[0][1]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n][0], polygon[i % n][1]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside

@app.route('/territory/<uuid>/streets')
@login_required
def get_territory_streets(uuid):
    """Route pour obtenir les rues d'un territoire"""
    try:
        app.logger.info(f"Demande de rues pour le territoire {uuid}")
        territory = Territory.query.filter_by(uuid=uuid).first_or_404()
        
        # Vérifier que l'utilisateur est autorisé
        if territory.user_id != current_user.id:
            app.logger.warning(f"Accès non autorisé au territoire {uuid}")
            return jsonify({'error': 'Non autorisé'}), 403
        
        app.logger.info(f"Récupération des rues pour le territoire {territory.name}")
        streets = get_streets_in_territory(territory.coordinates)
        
        response_data = {'streets': streets}
        app.logger.info(f"Rues trouvées : {streets}")
        
        return jsonify(response_data)
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des rues : {str(e)}")
        app.logger.exception(e)
        return jsonify({'error': str(e)}), 500

@app.route('/static/qrcodes/<path:filename>')
def serve_qr(filename):
    return send_from_directory(app.config['QR_FOLDER'], filename)

@app.route('/territories/<uuid>/print_card')
@login_required
def print_territory_card(uuid):
    territory = Territory.query.filter_by(uuid=uuid, user=current_user).first_or_404()
    
    # Récupérer le QR code
    qr_code_url = url_for('serve_qr', filename=f"{territory.uuid}.png")
    
    # Traitement des coordonnées
    try:
        # Si les coordonnées sont une chaîne JSON, les parser
        if isinstance(territory.coordinates, str):
            coordinates = json.loads(territory.coordinates)
        else:
            coordinates = territory.coordinates

        # S'assurer que les coordonnées sont dans le bon format (lat, lng)
        formatted_coordinates = []
        for coord in coordinates:
            if len(coord) == 2:
                # Inverser lat et lng si nécessaire
                formatted_coordinates.append([float(coord[0]), float(coord[1])])
        
        app.logger.info(f"Formatted coordinates for territory {territory.name}: {formatted_coordinates}")
        
        if not formatted_coordinates:
            app.logger.error(f"No valid coordinates found for territory {territory.name}")
            formatted_coordinates = []
            
    except Exception as e:
        app.logger.error(f"Error processing coordinates for territory {territory.name}: {str(e)}")
        formatted_coordinates = []
    
    return render_template('print_territory_card.html',
                         territory=territory,
                         territory_json=formatted_coordinates,
                         qr_code_url=qr_code_url,
                         google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

if __name__ == '__main__':
    import logging
    # Configuration du logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Définir le niveau de log pour notre application
    app.logger.setLevel(logging.INFO)
    # Définir le niveau de log pour Werkzeug
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    
    app.run(port=5001, debug=True)
