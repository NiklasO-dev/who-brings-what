import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key_reveal_pending: Mapped[bool] = mapped_column(default=False)
    key_reveal_wrapped: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=generate_token
    )
    guest_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=generate_token
    )
    organizer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, onupdate=utcnow
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bring_items: Mapped[list["BringItem"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="BringItem.position",
    )

    @property
    def is_done(self) -> bool:
        return self.done_at is not None

    @property
    def scheduled_deletion(self) -> datetime:
        from datetime import timedelta

        from app.config import settings

        base = self.created_at
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base + timedelta(days=settings.event_max_age_days)


class BringItem(Base):
    __tablename__ = "bring_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="guest")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["Event"] = relationship(back_populates="bring_items")
    participations: Mapped[list["Participation"]] = relationship(
        back_populates="bring_item", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="bring_item", cascade="all, delete-orphan"
    )

    @property
    def is_removed(self) -> bool:
        return self.removed_at is not None

    @property
    def is_preset(self) -> bool:
        return self.source == "preset"

    @property
    def active_participations(self) -> list["Participation"]:
        return [p for p in self.participations if p.removed_at is None]

    @property
    def active_comments(self) -> list["Comment"]:
        return [c for c in self.comments if c.removed_at is None]


class Participation(Base):
    __tablename__ = "participations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bring_item_id: Mapped[int] = mapped_column(ForeignKey("bring_items.id"), nullable=False)
    person_name: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bring_item: Mapped["BringItem"] = relationship(back_populates="participations")

    @property
    def is_removed(self) -> bool:
        return self.removed_at is not None


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bring_item_id: Mapped[int] = mapped_column(ForeignKey("bring_items.id"), nullable=False)
    author_name: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bring_item: Mapped["BringItem"] = relationship(back_populates="comments")

    @property
    def is_removed(self) -> bool:
        return self.removed_at is not None


class SiteStats(Base):
    __tablename__ = "site_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    removed_event_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_bring_item_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, onupdate=utcnow
    )
