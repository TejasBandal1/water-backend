"""STABLE_CHECKPOINT_2026_02_18

Revision ID: d8698751db36
Revises: bf0173f94cee
Create Date: 2026-02-18 13:32:14.931712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8698751db36'
down_revision: Union[str, Sequence[str], None] = 'bf0173f94cee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
