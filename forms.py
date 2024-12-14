from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, FloatField, IntegerField, validators

class LoginForm(FlaskForm):
    email = StringField('Email', [validators.Email(), validators.DataRequired()])
    password = PasswordField('Mot de passe', [validators.DataRequired()])
    remember_me = BooleanField('Se souvenir de moi')

class RegistrationForm(FlaskForm):
    name = StringField('Nom', [validators.Length(min=2, max=100), validators.DataRequired()])
    email = StringField('Email', [validators.Length(min=6, max=35), validators.Email(), validators.DataRequired()])
    password = PasswordField('Mot de passe', [
        validators.DataRequired(),
        validators.Length(min=6)
    ])

class UserSettingsForm(FlaskForm):
    territory_number_format = StringField('Format du numéro de territoire', 
        [validators.DataRequired()],
        description="Utilisez {number} comme placeholder. Ex: T-{number} ou {number}-{year}")
    
    territory_start_number = IntegerField('Numéro de départ', 
        [validators.DataRequired(), validators.NumberRange(min=1)],
        default=1)
    
    show_large_buildings = BooleanField('Afficher les grands immeubles',
        default=True)
    
    large_building_threshold = IntegerField('Seuil pour grands immeubles',
        [validators.DataRequired(), validators.NumberRange(min=2)],
        default=10)
    
    default_map_center_lat = FloatField('Latitude par défaut',
        [validators.Optional()])
    
    default_map_center_lng = FloatField('Longitude par défaut',
        [validators.Optional()])
    
    default_map_zoom = IntegerField('Zoom par défaut',
        [validators.Optional(), validators.NumberRange(min=1, max=20)],
        default=14)
