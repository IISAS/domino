"""repository-level access token

Revision ID: b8c2e1f0a4d3
Revises: a3f1b2c4d5e6
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c2e1f0a4d3'
down_revision = 'a3f1b2c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('piece_repository', sa.Column('git_access_token', sa.String(), nullable=True))

    op.execute(
        """
        UPDATE piece_repository AS pr
        SET git_access_token = w.git_access_token
        FROM workspace AS w
        WHERE pr.workspace_id = w.id
          AND w.git_access_token IS NOT NULL
        """
    )

    op.drop_column('workspace', 'git_access_token')


def downgrade():
    op.add_column('workspace', sa.Column('git_access_token', sa.String(), nullable=True))

    # Best-effort restore: pick any non-null repository token per workspace.
    op.execute(
        """
        UPDATE workspace AS w
        SET git_access_token = sub.git_access_token
        FROM (
            SELECT DISTINCT ON (workspace_id) workspace_id, git_access_token
            FROM piece_repository
            WHERE git_access_token IS NOT NULL
            ORDER BY workspace_id, id
        ) AS sub
        WHERE w.id = sub.workspace_id
        """
    )

    op.drop_column('piece_repository', 'git_access_token')
