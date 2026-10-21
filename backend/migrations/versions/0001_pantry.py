"""Create the local owner, reviewed aliases and flexible pantry entries."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    users = op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
    )
    ingredients = op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("normalized_key", sa.String(300), nullable=False, unique=True),
    )
    aliases = op.create_table(
        "ingredient_aliases",
        sa.Column("normalized_key", sa.String(300), primary_key=True),
        sa.Column("ingredient_id", sa.Integer, sa.ForeignKey("ingredients.id"), nullable=False),
    )
    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ingredient_id", sa.Integer, sa.ForeignKey("ingredients.id"), nullable=True),
        sa.Column("original_input", sa.String(10000), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("normalized_key", sa.String(300), nullable=False),
        sa.Column("normalization_version", sa.Integer, nullable=False),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.UniqueConstraint("user_id", "normalized_key", name="uq_pantry_owner_key"),
        sa.CheckConstraint("length(display_name) BETWEEN 1 AND 100", name="ck_pantry_name_length"),
    )
    op.create_index("ix_pantry_items_user_id", "pantry_items", ["user_id"])
    op.bulk_insert(users, [{"id": 1, "display_name": "Local user"}])
    op.bulk_insert(
        ingredients, [{"id": 1, "display_name": "Greek yogurt", "normalized_key": "greek yogurt"}]
    )
    op.bulk_insert(
        aliases,
        [
            {"normalized_key": "greek yogurt", "ingredient_id": 1},
            {"normalized_key": "greek yoghurt", "ingredient_id": 1},
        ],
    )


def downgrade():
    op.drop_index("ix_pantry_items_user_id", table_name="pantry_items")
    op.drop_table("pantry_items")
    op.drop_table("ingredient_aliases")
    op.drop_table("ingredients")
    op.drop_table("users")
