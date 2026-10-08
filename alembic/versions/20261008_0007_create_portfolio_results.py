"""Create portfolio_results table.

Revision ID: 20261008_0007
Revises: 20261008_0006
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20261008_0007"
down_revision = "20261008_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_results",
        sa.Column("portfolio_id", sa.String(length=36), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_tiv_kes", sa.Float(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        # Expected annual loss per return period tier
        sa.Column("eal_common_kes", sa.Float(), nullable=False),
        sa.Column("eal_occasional_kes", sa.Float(), nullable=False),
        sa.Column("eal_moderate_kes", sa.Float(), nullable=False),
        sa.Column("eal_severe_kes", sa.Float(), nullable=False),
        sa.Column("eal_extreme_kes", sa.Float(), nullable=False),
        sa.Column("eal_total_kes", sa.Float(), nullable=False),
        # Exceedance probability curve — JSON array of {return_period, loss_kes}
        sa.Column("exceedance_curve", sa.JSON(), nullable=False),
        # Top exposed locations — JSON array of {loc_id, lat, lon, tiv_kes, hazard_severity}
        sa.Column("top_locations", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("portfolio_results")
