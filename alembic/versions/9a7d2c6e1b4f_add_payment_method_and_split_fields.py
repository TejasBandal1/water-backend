"""add payment method and split fields

Revision ID: 9a7d2c6e1b4f
Revises: f3d1a0b2c4e7
Create Date: 2026-02-24 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a7d2c6e1b4f"
down_revision: Union[str, Sequence[str], None] = "f3d1a0b2c4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("method", sa.String(), nullable=False, server_default="CASH"),
    )
    op.add_column(
        "payments",
        sa.Column("cash_amount", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "payments",
        sa.Column("upi_amount", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "payments",
        sa.Column("upi_account", sa.String(), nullable=True),
    )

    op.execute(
        """
        UPDATE payments
        SET method = 'CASH',
            cash_amount = amount,
            upi_amount = 0
        """
    )

    op.alter_column("payments", "method", server_default=None)
    op.alter_column("payments", "cash_amount", server_default=None)
    op.alter_column("payments", "upi_amount", server_default=None)


def downgrade() -> None:
    op.drop_column("payments", "upi_account")
    op.drop_column("payments", "upi_amount")
    op.drop_column("payments", "cash_amount")
    op.drop_column("payments", "method")
