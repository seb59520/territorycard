from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, IntegerField, FloatField
from wtforms.validators import DataRequired, Email, Length, Optional, NumberRange

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    remember_me = BooleanField('Se souvenir de moi')

class RegistrationForm(FlaskForm):
    name = StringField('Nom', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[DataRequired(), Length(min=6)])

class UserSettingsForm(FlaskForm):
    territory_number_format = StringField('Format du numéro de territoire', 
        validators=[DataRequired()],
        description="Utilisez {number} comme placeholder. Ex: T-{number} ou {number}-{year}")
    
    territory_start_number = IntegerField('Numéro de départ', 
        validators=[DataRequired(), NumberRange(min=1)],
        default=1)
    
    show_large_buildings = BooleanField('Afficher les grands immeubles',
        default=True)
    
    large_building_threshold = IntegerField('Seuil pour grands immeubles',
        validators=[DataRequired(), NumberRange(min=2)],
        default=10)
    
    default_map_center_lat = FloatField('Latitude par défaut',
        validators=[Optional()])
    
    default_map_center_lng = FloatField('Longitude par défaut',
        validators=[Optional()])
    
    default_map_zoom = IntegerField('Zoom par défaut',
        validators=[Optional(), NumberRange(min=1, max=20)],
        default=14)
