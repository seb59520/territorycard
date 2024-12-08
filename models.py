from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relations
    territories = db.relationship('Territory', backref='user', lazy=True)
    settings = db.relationship('UserSettings', backref='user', uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Territory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100))
    polygon_data = db.Column(db.JSON, nullable=False)
    building_stats = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'name': self.name,
            'city': self.city,
            'polygon_data': self.polygon_data,
            'building_stats': self.building_stats or {
                'houses': 0,
                'apartments': 0,
                'apartment_buildings': 0,
                'total_doorbells': 0,
                'large_buildings': []
            },
            'created_at': self.created_at.isoformat(),
            'last_updated': self.last_updated.isoformat()
        }

class UserSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    
    # Paramètres de formatage
    territory_number_format = db.Column(db.String(50), default='T-{number}')  # Ex: T-001, T-{number}-{year}
    territory_start_number = db.Column(db.Integer, default=1)
    
    # Préférences d'affichage
    show_large_buildings = db.Column(db.Boolean, default=True)
    large_building_threshold = db.Column(db.Integer, default=10)
    
    # Paramètres de carte
    default_map_center_lat = db.Column(db.Float)
    default_map_center_lng = db.Column(db.Float)
    default_map_zoom = db.Column(db.Integer, default=14)
    
    def to_dict(self):
        return {
            'territory_number_format': self.territory_number_format,
            'territory_start_number': self.territory_start_number,
            'show_large_buildings': self.show_large_buildings,
            'large_building_threshold': self.large_building_threshold,
            'default_map_center_lat': self.default_map_center_lat,
            'default_map_center_lng': self.default_map_center_lng,
            'default_map_zoom': self.default_map_zoom
        }
