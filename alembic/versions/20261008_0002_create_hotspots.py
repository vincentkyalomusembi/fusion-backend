"""Create flood hotspots table.

Revision ID: 20261008_0002
Revises: 20261008_0001
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20261008_0002"
down_revision = "20261008_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hotspots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hotspots")
