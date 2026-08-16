"""add total_size_bytes to project

Revision ID: 6257c8a0bc81
Revises: 56235aba7fa9
Create Date: 2026-08-16 11:34:55.098880

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6257c8a0bc81'
down_revision: str | None = '56235aba7fa9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('total_size_bytes', sa.BigInteger(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('projects', 'total_size_bytes')