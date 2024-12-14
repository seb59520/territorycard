"""reset_territory_sequence

Revision ID: reset_territory_sequence
Revises: 71fc883ff3fa
Create Date: 2024-12-08 13:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'reset_territory_sequence'
down_revision = '71fc883ff3fa'
branch_labels = None
depends_on = None

def upgrade():
    # Récupérer la valeur maximale actuelle de l'ID
    connection = op.get_bind()
    result = connection.execute(text("SELECT MAX(id) FROM territory"))
    max_id = result.scalar() or 0
    
    # Réinitialiser la séquence à partir de la valeur maximale + 1
    op.execute(text(f"ALTER SEQUENCE territory_id_seq RESTART WITH {max_id + 1}"))

def downgrade():
    pass
