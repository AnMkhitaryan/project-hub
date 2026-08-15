"""add uniqueness, indexes, and project cascade

Revision ID: 56235aba7fa9
Revises: bf10f6de2a91
Create Date: 2026-08-15 14:34:46.762595

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '56235aba7fa9'
down_revision: str | None = 'bf10f6de2a91'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_documents_project_id'), 'documents', ['project_id'], unique=False
    )
    op.drop_constraint(
        op.f('documents_project_id_fkey'), 'documents', type_='foreignkey'
    )
    op.create_foreign_key(
        None, 'documents', 'projects', ['project_id'], ['id'], ondelete='CASCADE'
    )
    op.create_index(
        op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False
    )
    op.drop_constraint(
        op.f('project_members_project_id_fkey'), 'project_members', type_='foreignkey'
    )
    op.create_foreign_key(
        None, 'project_members', 'projects', ['project_id'], ['id'], ondelete='CASCADE'
    )
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.create_unique_constraint('users_login_key', 'users', ['login'])


def downgrade() -> None:
    op.drop_constraint('users_login_key', 'users', type_='unique')
    op.drop_constraint('users_email_key', 'users', type_='unique')
    op.drop_constraint('project_members_project_id_fkey', 'project_members', type_='foreignkey')
    op.create_foreign_key(
        op.f('project_members_project_id_fkey'),
        'project_members', 'projects', ['project_id'], ['id'],
    )
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_constraint('documents_project_id_fkey', 'documents', type_='foreignkey')
    op.create_foreign_key(
        op.f('documents_project_id_fkey'), 'documents', 'projects', ['project_id'], ['id']
    )
    op.drop_index(op.f('ix_documents_project_id'), table_name='documents')