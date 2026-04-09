"""add avatar_url to users

Revision ID: d4a6f57f7a2b
Revises: c1f3d9a8e6b1
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a6f57f7a2b"
down_revision: Union[str, Sequence[str], None] = "c1f3d9a8e6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
