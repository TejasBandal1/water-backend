"""update billing structure

Revision ID: 6195492799a5
Revises: d8698751db36
Create Date: 2026-02-18 13:34:04.608307

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6195492799a5'
down_revision: Union[str, Sequence[str], None] = 'd8698751db36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1️⃣ Add columns as nullable first
    op.add_column(
        'clients',
        sa.Column('billing_type', sa.String(), nullable=True)
    )

    op.add_column(
        'clients',
        sa.Column('billing_interval', sa.Integer(), nullable=True)
    )

    # 2️⃣ Fill existing rows
    op.execute("UPDATE clients SET billing_type = 'monthly'")
    op.execute("UPDATE clients SET billing_interval = 1")

    # 3️⃣ Make columns NOT NULL
    op.alter_column('clients', 'billing_type', nullable=False)
    op.alter_column('clients', 'billing_interval', nullable=False)

    # 4️⃣ Drop old column
    op.drop_column('clients', 'billing_cycle')



def downgrade() -> None:
    """Downgrade schema."""

    op.add_column(
        'clients',
        sa.Column('billing_cycle', sa.String(), nullable=True)
    )

    op.execute("UPDATE clients SET billing_cycle = billing_type")

    op.drop_column('clients', 'billing_interval')
    op.drop_column('clients', 'billing_type')
