"""Add commentaire field to Territory

Revision ID: add_commentaire_field
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Ajouter la colonne commentaire
    op.add_column('territory', sa.Column('commentaire', sa.Text))

def downgrade():
    # Supprimer la colonne commentaire
    op.drop_column('territory', 'commentaire')
