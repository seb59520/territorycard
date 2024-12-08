# Territory Divider

Une application SAAS permettant de diviser une carte Google Maps en zones à partir d'un fichier KML et de générer des QR codes pour chaque zone.

## Fonctionnalités

- Upload de fichiers KML pour définir la zone principale
- Division de la zone en territoires plus petits
- Génération automatique de QR codes pour chaque territoire
- Visualisation des territoires sur Google Maps
- Interface utilisateur intuitive

## Prérequis

- Python 3.8+
- Clé API Google Maps

## Installation

1. Cloner le repository :
```bash
git clone <repository-url>
cd territory-divider
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. Configurer les variables d'environnement :
- Copier le fichier `.env.example` vers `.env`
- Ajouter votre clé API Google Maps dans le fichier `.env`

## Démarrage

1. Lancer l'application :
```bash
python app.py
```

2. Ouvrir un navigateur et accéder à `http://localhost:5000`

## Utilisation

1. Charger un fichier KML en utilisant le bouton "Charger"
2. Utiliser l'outil de dessin pour créer des zones sur la carte
3. Cliquer sur "Diviser le territoire" pour générer les QR codes
4. Les QR codes générés peuvent être téléchargés ou partagés

## Structure du projet

```
territory-divider/
├── app.py              # Application Flask principale
├── requirements.txt    # Dépendances Python
├── .env               # Variables d'environnement
├── static/
│   └── qrcodes/       # QR codes générés
├── templates/
│   ├── index.html     # Page principale
│   └── territory.html # Page de visualisation d'un territoire
└── uploads/           # Fichiers KML uploadés
```

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou à soumettre une pull request.
