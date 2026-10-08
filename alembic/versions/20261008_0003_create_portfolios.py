"""Create portfolio import metadata.

Revision ID: 20261008_0003
Revises: 20261008_0002
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20261008_0003"
down_revision = "20261008_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("table_name", sa.String(length=63), nullable=False, unique=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_portfolios_status", "portfolios", ["status"])


def downgrade() -> None:
    op.drop_index("ix_portfolios_status", table_name="portfolios")
    op.drop_table("portfolios")
