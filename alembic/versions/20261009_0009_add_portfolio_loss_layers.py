"""Persist building losses and insurance loss layers."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_0009"
down_revision = "20261008_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolio_results", sa.Column("building_losses", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("portfolio_results", sa.Column("insurance_curve", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("portfolio_results", sa.Column("insurance_program", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("portfolio_results", "insurance_program")
    op.drop_column("portfolio_results", "insurance_curve")
    op.drop_column("portfolio_results", "building_losses")