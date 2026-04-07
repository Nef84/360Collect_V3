from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ultimo_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo_cliente: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nombres: Mapped[str] = mapped_column(String(120), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(120), nullable=False)
    dui: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nit: Mapped[Optional[str]] = mapped_column(String(30))
    telefono: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    direccion: Mapped[Optional[str]] = mapped_column(Text)
    score_riesgo: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    segmento: Mapped[Optional[str]] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cuentas: Mapped[list["Cuenta"]] = relationship(back_populates="cliente")


class Cuenta(Base):
    __tablename__ = "cuentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    numero_cuenta: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    tipo_producto: Mapped[str] = mapped_column(String(40), nullable=False)
    subtipo_producto: Mapped[Optional[str]] = mapped_column(String(60))
    saldo_capital: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    saldo_mora: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    saldo_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    dias_mora: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bucket_actual: Mapped[str] = mapped_column(String(30), nullable=False, default="0-30")
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVA")
    fecha_apertura: Mapped[Optional[datetime]] = mapped_column(Date)
    fecha_vencimiento: Mapped[Optional[datetime]] = mapped_column(Date)
    tasa_interes: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    es_estrafinanciamiento: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="cuentas")
    pagos: Mapped[list["Pago"]] = relationship(back_populates="cuenta")


class Pago(Base):
    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuentas.id"), nullable=False, index=True)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_pago: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canal: Mapped[str] = mapped_column(String(50), nullable=False, default="digital")
    referencia: Mapped[Optional[str]] = mapped_column(String(80))
    observacion: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cuenta: Mapped["Cuenta"] = relationship(back_populates="pagos")


class PrediccionIA(Base):
    __tablename__ = "predicciones_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuentas.id"), nullable=False, index=True)
    probabilidad_pago_30d: Mapped[float] = mapped_column(Float, nullable=False)
    score_modelo: Mapped[float] = mapped_column(Float, nullable=False)
    modelo_version: Mapped[str] = mapped_column(String(40), nullable=False, default="xgb-v1")
    fecha_prediccion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    recomendacion: Mapped[Optional[str]] = mapped_column(Text)


class Promesa(Base):
    __tablename__ = "promesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuentas.id"), nullable=False, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"))
    fecha_promesa: Mapped[datetime] = mapped_column(Date, nullable=False)
    monto_prometido: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDIENTE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class History(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entidad: Mapped[str] = mapped_column(String(60), nullable=False)
    entidad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    accion: Mapped[str] = mapped_column(String(60), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Strategy(Base):
    __tablename__ = "estrategias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    categoria: Mapped[Optional[str]] = mapped_column(String(50))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WorklistAssignment(Base):
    __tablename__ = "asignaciones_cartera"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    estrategia_codigo: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_asignacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AssignmentHistory(Base):
    __tablename__ = "assignment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), index=True)
    assignment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("asignaciones_cartera.id"), index=True)
    strategy_code: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    placement_code: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    channel_scope: Mapped[Optional[str]] = mapped_column(String(30))
    group_id: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    sublista_codigo: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    assigned_share_pct: Mapped[Optional[float]] = mapped_column(Float)
    efficiency_pct: Mapped[Optional[float]] = mapped_column(Float)
    tenure_days: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    minimum_payment_to_progress: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=10)
    segment_snapshot: Mapped[Optional[str]] = mapped_column(String(40))
    account_status_snapshot: Mapped[Optional[str]] = mapped_column(String(30))
    max_days_past_due_snapshot: Mapped[Optional[int]] = mapped_column(Integer)
    total_due_snapshot: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WhatsAppBotSession(Base):
    __tablename__ = "whatsapp_bot_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clientes.id"), index=True)
    strategy_code: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    last_inbound_message: Mapped[Optional[str]] = mapped_column(Text)
    last_outbound_message: Mapped[Optional[str]] = mapped_column(Text)
    context_json: Mapped[Optional[str]] = mapped_column(Text)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
