# app/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, ForeignKey, Text, Float, UniqueConstraint,
    Index, Boolean
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.db_base import Base


# ---------- User ----------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    creds: Mapped[list["ApiCredentials"]] = relationship(
        "ApiCredentials", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    generations: Mapped[list["Generation"]] = relationship(
        "Generation", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    settings: Mapped[Optional["UserSettings"]] = relationship(
        "UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
    loras: Mapped[list["UserLora"]] = relationship(
        "UserLora", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


# ---------- ApiCredentials ----------
class ApiCredentials(Base):
    __tablename__ = "api_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "service", name="uq_user_service"),
        Index("ix_api_creds_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service: Mapped[str] = mapped_column(String(32), nullable=False)

    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="creds")


# ---------- Generation ----------
class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (Index("ix_generations_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags_csv: Mapped[str] = mapped_column(Text, nullable=False)

    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    style: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="text_ready", nullable=False)

    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_cost_credits: Mapped[Optional[float]] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="generations")


# ---------- UserSettings ----------
class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_settings_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    width:  Mapped[int] = mapped_column(Integer, default=768, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    steps:  Mapped[int] = mapped_column(Integer, default=28, nullable=False)
    cfg_scale: Mapped[float] = mapped_column(Float, default=7.0, nullable=False)

    sampler:   Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scheduler: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    model_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

     # добавляем:
    sd_model_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # добавляем clip_skip (для SDXL/SD1.5 конфигов это бывает нужно)
    clip_skip: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    loras_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    show_costs: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credits_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="settings")


# ---------- UserLora ----------
class UserLora(Base):
    __tablename__ = "user_loras"
    __table_args__ = (Index("ix_user_loras_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    lora_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title:   Mapped[str] = mapped_column(String(128), nullable=False)
    weight:  Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="loras")
