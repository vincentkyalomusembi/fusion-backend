"""Create locations table.

Revision ID: 20261008_0001
Revises:
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20261008_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("loc_id", sa.String(length=32), primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("housing_class", sa.String(length=64), nullable=False),
        sa.Column("floor_area_m2", sa.Float(), nullable=False),
        sa.Column("cost_per_m2_kes", sa.Float(), nullable=False),
        sa.Column("tiv_kes", sa.Float(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("hazard_score_common", sa.Float(), nullable=False),
        sa.Column("hazard_score_occasional", sa.Float(), nullable=False),
        sa.Column("hazard_score_moderate", sa.Float(), nullable=False),
        sa.Column("hazard_score_severe", sa.Float(), nullable=False),
        sa.Column("hazard_score_extreme", sa.Float(), nullable=False),
        sa.Column("hazard_severity", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("locations")
