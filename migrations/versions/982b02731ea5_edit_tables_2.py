"""edit tables 2

Revision ID: 982b02731ea5
Revises: 20f8ed053ad7
Create Date: 2026-03-28 12:45:45.095847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '982b02731ea5'
down_revision: Union[str, Sequence[str], None] = '20f8ed053ad7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    def has_table(table_name: str) -> bool:
        return table_name in tables

    def refresh_columns(table_name: str) -> set[str]:
        return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}

    if not has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("password", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
        op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
        tables.add("users")
    else:
        user_columns = refresh_columns("users")
        if "created_at" not in user_columns:
            op.add_column("users", sa.Column("created_at", sa.DateTime(), nullable=True))

    if has_table("chat") and not has_table("chats"):
        op.rename_table("chat", "chats")
        tables.remove("chat")
        tables.add("chats")
    elif not has_table("chats"):
        op.create_table(
            "chats",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        tables.add("chats")

    chat_columns = refresh_columns("chats")
    if "updated_at" not in chat_columns:
        op.add_column("chats", sa.Column("updated_at", sa.DateTime(), nullable=True))

    if has_table("members") and not has_table("chat_participants"):
        op.rename_table("members", "chat_participants")
        tables.remove("members")
        tables.add("chat_participants")
    elif not has_table("chat_participants"):
        op.create_table(
            "chat_participants",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("joined_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["chat_id"], ["chats.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        tables.add("chat_participants")

    if has_table("message") and not has_table("messages"):
        op.rename_table("message", "messages")
        tables.remove("message")
        tables.add("messages")
    elif not has_table("messages"):
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.Integer(), nullable=True),
            sa.Column("sender_id", sa.Integer(), nullable=True),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["chat_id"], ["chats.id"]),
            sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        tables.add("messages")

    message_columns = refresh_columns("messages")
    if "text" in message_columns:
        op.execute(sa.text("ALTER TABLE messages ALTER COLUMN text TYPE TEXT"))
        op.execute(sa.text("ALTER TABLE messages ALTER COLUMN text DROP NOT NULL"))
    if "is_edited" in message_columns:
        op.drop_column("messages", "is_edited")

    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_members_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_message_id"))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "messages" in tables:
        message_columns = {column["name"] for column in sa.inspect(bind).get_columns("messages")}
        if "is_edited" not in message_columns:
            op.add_column("messages", sa.Column("is_edited", sa.Boolean(), nullable=True))
        op.execute(sa.text("UPDATE messages SET text = '' WHERE text IS NULL"))
        op.alter_column(
            "messages",
            "text",
            existing_type=sa.Text(),
            type_=sa.String(),
            existing_nullable=True,
            nullable=False,
        )
        op.create_index(op.f("ix_message_id"), "messages", ["id"], unique=False)
        if "message" not in tables:
            op.rename_table("messages", "message")

    if "chat_participants" in tables:
        op.create_index(op.f("ix_members_id"), "chat_participants", ["id"], unique=False)
        if "members" not in tables:
            op.rename_table("chat_participants", "members")

    if "chats" in tables:
        chat_columns = {column["name"] for column in sa.inspect(bind).get_columns("chats")}
        if "updated_at" in chat_columns:
            op.drop_column("chats", "updated_at")
        op.create_index(op.f("ix_chat_id"), "chats", ["id"], unique=False)
        if "chat" not in tables:
            op.rename_table("chats", "chat")
