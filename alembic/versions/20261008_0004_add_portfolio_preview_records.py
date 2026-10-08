"""Add temporary portfolio review records.

Revision ID: 20261008_0004
Revises: 20261008_0003
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20261008_0004"
down_revision = "20261008_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_preview_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "portfolio_id",
            sa.String(length=36),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("loc_id", sa.String(length=64), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("record_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("portfolio_id", "loc_id", name="uq_portfolio_preview_loc"),
        sa.UniqueConstraint("portfolio_id", "record_hash", name="uq_portfolio_preview_hash"),
    )
    op.create_index(
        "ix_portfolio_preview_records_portfolio_id",
        "portfolio_preview_records",
        ["portfolio_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_preview_records_portfolio_id", table_name="portfolio_preview_records")
    op.drop_table("portfolio_preview_records")
