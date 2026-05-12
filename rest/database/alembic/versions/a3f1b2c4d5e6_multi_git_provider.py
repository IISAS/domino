"""multi git provider support

Revision ID: a3f1b2c4d5e6
Revises: eb478b6619b0
Create Date: 2026-03-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f1b2c4d5e6'
down_revision = 'eb478b6619b0'
branch_labels = None
depends_on = None


def upgrade():
    # Rename github_access_token -> git_access_token in workspace table
    op.alter_column('workspace', 'github_access_token', new_column_name='git_access_token')

    # Add new values to the repositorysource enum (PostgreSQL-specific)
    op.execute("ALTER TYPE repositorysource ADD VALUE IF NOT EXISTS 'gitlab'")
    op.execute("ALTER TYPE repositorysource ADD VALUE IF NOT EXISTS 'generic'")


def downgrade():
    # Rename git_access_token back to github_access_token
    op.alter_column('workspace', 'git_access_token', new_column_name='github_access_token')

    # Note: PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade leaves the extra enum values in place.
