"""add availability table

Revision ID: xxx
Revises: previous_revision
Create Date: 2024-01-xx

"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('availability',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lecturer_id', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=True),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['lecturer_id'], ['lecturer.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('availability') 