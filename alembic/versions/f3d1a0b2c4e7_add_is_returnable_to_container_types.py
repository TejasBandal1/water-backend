"""add is_returnable to container_types

Revision ID: f3d1a0b2c4e7
Revises: 6195492799a5
Create Date: 2026-02-24 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3d1a0b2c4e7"
down_revision: Union[str, Sequence[str], None] = "6195492799a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "container_types",
        sa.Column(
            "is_returnable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("container_types", "is_returnable", server_default=None)


def downgrade() -> None:
    op.drop_column("container_types", "is_returnable")
