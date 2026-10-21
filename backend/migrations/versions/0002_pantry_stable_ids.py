"""Keep deleted pantry IDs from being reassigned to new ingredients."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "pantry_items", recreate="always", table_kwargs={"sqlite_autoincrement": True}
    ):
        pass


def downgrade():
    with op.batch_alter_table(
        "pantry_items", recreate="always", table_kwargs={"sqlite_autoincrement": False}
    ):
        pass
