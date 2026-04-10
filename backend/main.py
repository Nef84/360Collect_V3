from __future__ import annotations

import io
import json
import logging
import re
import threading
import unicodedata
import zipfile
import csv
import base64
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Generator, Optional
from uuid import uuid4
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from jose import jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

# ── Local modules ─────────────────────────────────────────────────────────────
from config import settings, COLLECTOR_DAILY_WORKLIST_LIMIT, PLACEMENT_SEQUENCE, PLACEMENT_EXTERNAL_SUFFIX, EXTERNAL_AGENCY_SLOTS, INTERNAL_WORKLIST_SLOTS
from database import Base, engine, SessionLocal, get_db, get_readonly_connection, wait_for_database
from models import (
    Usuario, Cliente, Cuenta, Pago, PrediccionIA, Promesa,
    History, Strategy, WorklistAssignment, AssignmentHistory, WhatsAppBotSession,
)
from schemas import (
    TokenResponse, RefreshRequest,
    UserCreate, UserUpdate, UserRead,
    ClienteCreate, ClienteUpdate, ClienteRead,
    CuentaCreate, CuentaUpdate, CuentaRead,
    PagoCreate, PagoRead,
    PredictionResponse,
    CollectorPortfolioResponse, CollectorMetrics, CollectorClientRead,
    CollectorAccountRead, CollectorManagementCreate, DemographicUpdate, DemographicProfileRead,
    DemographicPhoneItem, DemographicEmailItem, DemographicAddressItem,
    PromiseRead, ManagementHistoryRead,
    SupervisorOverviewResponse, SupervisorCollectorMetric,
    StrategyCreate, StrategyRead,
    WorklistAssignRequest, WorklistGroupRead, WorklistGroupAssignRequest, WorklistGroupUnassignRequest,
    AdminOverviewResponse, AssignmentHistoryRead,
    SupervisorCollectorAssignRequest, SupervisorCollectorAssignmentRead,
    AdminDocumentProposalResponse, AdminDocumentProposalUpdate,
    AdminImportProposalResponse,
    AdminGeneratedReportRequest, AdminGeneratedReportResponse,
    AdminDailySimulationRequest, AdminDailySimulationResponse, AdminDailySimulationPreviewResponse,
    RecoveryVintageOverviewResponse, RecoveryVintagePlacementRead, RecoveryVintageClientRead, RecoveryVintageAgencyRead, RecoveryVintageCompareResponse, RecoveryVintageCompareItem,
    AdminOmnichannelConfigUpdate, AdminWhatsAppDemoSendRequest,
    AdminEmailDemoRequest, AdminSMSDemoRequest, AdminCallbotDemoRequest, AdminOmnichannelPreviewResponse,
    AdminAssistantRequest, AdminAssistantResponse,
    AdminSqlQueryRequest, AdminSqlQueryResponse, AdminHistoryEventRead,
)
from omnichannel_channels import (
    build_collection_email_html, send_email_resend, send_email_smtp,
    build_collection_sms, send_sms_textbelt, send_sms_twilio,
    build_collection_email_html,
    build_twiml_initial_call, build_twiml_gather_response,
    build_twiml_no_answer, initiate_callbot_twilio,
)
from security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_refresh_token,
    get_current_user, require_roles, check_login_rate_limit,
    oauth2_scheme, pwd_context,
)
from fastapi.security import OAuth2PasswordRequestForm

# ── In-memory proposal stores (NOTE: consider Redis/DB for multi-process) ────
ADMIN_DOCUMENT_PROPOSALS: dict[str, dict] = {}
ADMIN_IMPORT_PROPOSALS: dict[str, dict] = {}
ADMIN_USER_IMPORT_PROPOSALS: dict[str, dict] = {}
RECOVERY_VINTAGE_START_YEAR = 2000
BOOTSTRAP_STATE = {"status": "pending", "error": None}
BOOTSTRAP_LOCK = threading.Lock()
logger = logging.getLogger("360collect.bootstrap")


def resolve_init_sql_path() -> Optional[Path]:
    candidates = [
        Path(__file__).resolve().parent.parent / "database" / "init.sql",
        Path(__file__).resolve().parent / "database" / "init.sql",
        Path.cwd() / "database" / "init.sql",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def seed_database_from_init_sql_if_empty() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        user_count = connection.execute(text("SELECT COUNT(*) FROM usuarios")).scalar() or 0
        if int(user_count) > 0:
            return

    init_sql_path = resolve_init_sql_path()
    if not init_sql_path:
        raise RuntimeError("No se encontró database/init.sql para sembrar la base de datos inicial.")

    script = init_sql_path.read_text(encoding="utf-8")
    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        cursor.execute(script)
        raw_connection.commit()
    finally:
        raw_connection.close()


def ensure_minimal_demo_users() -> None:
    Base.metadata.create_all(bind=engine)
    demo_users = [
        {
            "nombre": "Administrador General",
            "email": "admin@360collectplus.demo",
            "username": "admin",
            "rol": "Admin",
        },
        {
            "nombre": "Collector Uno",
            "email": "collector1@360collectplus.demo",
            "username": "collector1",
            "rol": "Collector",
        },
        {
            "nombre": "Supervisor Uno",
            "email": "supervisor1@360collectplus.demo",
            "username": "supervisor1",
            "rol": "Supervisor",
        },
    ]
    db = SessionLocal()
    try:
        for payload in demo_users:
            existing = db.query(Usuario).filter(Usuario.username == payload["username"]).first()
            if existing:
                continue
            db.add(
                Usuario(
                    nombre=payload["nombre"],
                    email=payload["email"],
                    username=payload["username"],
                    rol=payload["rol"],
                    activo=True,
                    password_hash=hash_password("Password123!"),
                )
            )
        db.commit()
    finally:
        db.close()


def bootstrap_runtime() -> None:
    with BOOTSTRAP_LOCK:
        if BOOTSTRAP_STATE["status"] in {"running", "ready"}:
            return
        BOOTSTRAP_STATE["status"] = "running"
        BOOTSTRAP_STATE["error"] = None
    try:
        wait_for_database()
        seed_database_from_init_sql_if_empty()
        ensure_runtime_schema()
        BOOTSTRAP_STATE["status"] = "ready"
        logger.info("Bootstrap completed successfully.")
    except Exception as exc:  # pragma: no cover - startup background path
        BOOTSTRAP_STATE["status"] = "error"
        BOOTSTRAP_STATE["error"] = str(exc)
        logger.exception("Bootstrap failed.")



def ensure_runtime_schema() -> None:
    ddl = """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'clientes' AND column_name = 'codigo_cliente'
        ) AND NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'clientes' AND column_name = 'identity_code'
        ) THEN
            ALTER TABLE clientes RENAME COLUMN codigo_cliente TO identity_code;
        END IF;
    END $$;
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS identity_code VARCHAR(30);
    UPDATE clientes
    SET identity_code = LPAD(REGEXP_REPLACE(COALESCE(identity_code, ''), '\\D', '', 'g'), 11, '0')
    WHERE identity_code IS NULL
       OR BTRIM(identity_code) = ''
       OR identity_code !~ '^\\d{11}$';
    ALTER TABLE clientes ALTER COLUMN identity_code SET NOT NULL;
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'clientes_identity_code_key'
        ) THEN
            ALTER TABLE clientes ADD CONSTRAINT clientes_identity_code_key UNIQUE (identity_code);
        END IF;
    END $$;
    CREATE INDEX IF NOT EXISTS ix_clientes_identity_code ON clientes(identity_code);
    CREATE TABLE IF NOT EXISTS assignment_history (
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id),
        usuario_id INTEGER REFERENCES usuarios(id),
        assignment_id INTEGER REFERENCES asignaciones_cartera(id),
        strategy_code VARCHAR(50),
        placement_code VARCHAR(30),
        channel_scope VARCHAR(30),
        group_id VARCHAR(40),
        sublista_codigo VARCHAR(50),
        assigned_share_pct DOUBLE PRECISION,
        efficiency_pct DOUBLE PRECISION,
        tenure_days INTEGER NOT NULL DEFAULT 120,
        minimum_payment_to_progress NUMERIC(12,2) NOT NULL DEFAULT 10,
        segment_snapshot VARCHAR(40),
        account_status_snapshot VARCHAR(30),
        max_days_past_due_snapshot INTEGER,
        total_due_snapshot NUMERIC(12,2),
        notes TEXT,
        start_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        end_at TIMESTAMP NULL,
        is_current BOOLEAN NOT NULL DEFAULT TRUE
    );
    CREATE INDEX IF NOT EXISTS ix_assignment_history_cliente_id ON assignment_history(cliente_id);
    CREATE INDEX IF NOT EXISTS ix_assignment_history_strategy_code ON assignment_history(strategy_code);
    CREATE INDEX IF NOT EXISTS ix_assignment_history_group_id ON assignment_history(group_id);
    ALTER TABLE cuentas ADD COLUMN IF NOT EXISTS fecha_separacion DATE;
    CREATE INDEX IF NOT EXISTS ix_cuentas_fecha_separacion ON cuentas(fecha_separacion);
    UPDATE cuentas
    SET fecha_separacion = DATE '2025-01-01' + ((id - 1) % 365)
    WHERE fecha_separacion IS NULL
      AND estado IN ('LIQUIDADO', 'Z');
    DO $$
    DECLARE
        recovery_accounts INTEGER;
        distinct_vintage_years INTEGER;
        span_days INTEGER;
        end_date DATE;
    BEGIN
        SELECT COUNT(*), COUNT(DISTINCT EXTRACT(YEAR FROM fecha_separacion))
        INTO recovery_accounts, distinct_vintage_years
        FROM cuentas
        WHERE estado IN ('LIQUIDADO', 'Z');

        end_date := (DATE_TRUNC('year', CURRENT_DATE) + INTERVAL '1 year' - INTERVAL '1 day')::date;
        span_days := end_date - DATE '2000-01-01';

        IF recovery_accounts > 0 AND distinct_vintage_years <= 1 THEN
            UPDATE cuentas
            SET fecha_separacion = DATE '2000-01-01' + (((id * 17) % GREATEST(span_days, 365)))
            WHERE estado IN ('LIQUIDADO', 'Z');
        END IF;
    END $$;
    CREATE TABLE IF NOT EXISTS supervisor_assignments (
        id SERIAL PRIMARY KEY,
        supervisor_id INTEGER NOT NULL REFERENCES usuarios(id),
        collector_id INTEGER NOT NULL REFERENCES usuarios(id),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(supervisor_id, collector_id)
    );
    CREATE INDEX IF NOT EXISTS ix_supervisor_assignments_supervisor_id ON supervisor_assignments(supervisor_id);
    CREATE INDEX IF NOT EXISTS ix_supervisor_assignments_collector_id ON supervisor_assignments(collector_id);
    CREATE TABLE IF NOT EXISTS client_contact_points (
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id),
        contact_kind VARCHAR(20) NOT NULL,
        phone_type VARCHAR(20),
        value TEXT NOT NULL,
        is_primary BOOLEAN NOT NULL DEFAULT FALSE,
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_client_contact_points_cliente_id ON client_contact_points(cliente_id);
    CREATE INDEX IF NOT EXISTS ix_client_contact_points_kind ON client_contact_points(contact_kind);
    CREATE TABLE IF NOT EXISTS client_addresses (
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id),
        address_type VARCHAR(20),
        value TEXT NOT NULL,
        is_primary BOOLEAN NOT NULL DEFAULT FALSE,
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_client_addresses_cliente_id ON client_addresses(cliente_id);
    CREATE TABLE IF NOT EXISTS whatsapp_bot_sessions (
        id SERIAL PRIMARY KEY,
        phone_number VARCHAR(30) NOT NULL,
        client_id INTEGER REFERENCES clientes(id),
        strategy_code VARCHAR(50),
        status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        last_inbound_message TEXT,
        last_outbound_message TEXT,
        context_json TEXT,
        last_message_at TIMESTAMP NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_whatsapp_bot_sessions_phone_number ON whatsapp_bot_sessions(phone_number);
    CREATE TABLE IF NOT EXISTS omnichannel_settings (
        id INTEGER PRIMARY KEY,
        whatsapp_bot_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        email_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        callbot_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        inbound_bot_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        automation_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        webhooks_configured BOOLEAN NOT NULL DEFAULT FALSE,
        template_library_ready BOOLEAN NOT NULL DEFAULT FALSE,
        twilio_account_sid TEXT,
        twilio_auth_token TEXT,
        twilio_whatsapp_from TEXT,
        twilio_demo_phone TEXT,
        resend_api_key TEXT,
        email_from TEXT,
        smtp_host TEXT,
        smtp_port INTEGER DEFAULT 587,
        smtp_user TEXT,
        smtp_password TEXT,
        sms_provider TEXT DEFAULT 'textbelt',
        textbelt_api_key TEXT DEFAULT 'textbelt',
        twilio_sms_from TEXT,
        callbot_webhook_url TEXT,
        twilio_voice_from TEXT,
        notes TEXT,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS twilio_account_sid TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS twilio_auth_token TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS twilio_whatsapp_from TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS twilio_demo_phone TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS resend_api_key TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS email_from TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS smtp_host TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS smtp_port INTEGER DEFAULT 587;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS smtp_user TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS smtp_password TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS sms_provider TEXT DEFAULT 'textbelt';
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS textbelt_api_key TEXT DEFAULT 'textbelt';
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS twilio_sms_from TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS callbot_webhook_url TEXT;
    ALTER TABLE omnichannel_settings ADD COLUMN IF NOT EXISTS twilio_voice_from TEXT;
    INSERT INTO omnichannel_settings (
        id,
        whatsapp_bot_enabled,
        email_enabled,
        callbot_enabled,
        inbound_bot_enabled,
        automation_enabled,
        webhooks_configured,
        template_library_ready,
        twilio_account_sid,
        twilio_auth_token,
        twilio_whatsapp_from,
        twilio_demo_phone,
        notes
    )
    SELECT
        1,
        FALSE,
        FALSE,
        FALSE,
        FALSE,
        FALSE,
        FALSE,
        FALSE,
        '',
        '',
        'whatsapp:+14155238886',
        '',
        'Pendiente de conectar proveedores reales y habilitar webhooks.'
    WHERE NOT EXISTS (SELECT 1 FROM omnichannel_settings WHERE id = 1);
    """
    with engine.begin() as connection:
        raw_connection = connection.connection
        cursor = raw_connection.cursor()
        try:
            cursor.execute(ddl)
        finally:
            cursor.close()
    rebalance_recovery_vintage_assignments()


def target_recovery_placement_for_vintage(separation_date: Optional[date], seed_value: int) -> str:
    if not separation_date:
        return "V11"
    age_years = max(0, date.today().year - separation_date.year)
    bucket = abs(seed_value) % 10
    if age_years <= 1:
        return "V11" if bucket < 8 else "V12"
    if age_years <= 3:
        return "V12" if bucket < 6 else ("V11" if bucket < 8 else "V13")
    if age_years <= 6:
        return "V13" if bucket < 6 else ("V12" if bucket < 8 else "V16")
    if age_years <= 10:
        return "V16" if bucket < 6 else ("V13" if bucket < 8 else "V18")
    return "V18" if bucket < 7 else "V16"


def rebalance_recovery_vintage_assignments() -> None:
    db = SessionLocal()
    try:
        current_histories = (
            db.query(AssignmentHistory, Cuenta)
            .join(Cuenta, Cuenta.cliente_id == AssignmentHistory.cliente_id)
            .filter(
                AssignmentHistory.strategy_code == "VAGENCIASEXTERNASINTERNO",
                AssignmentHistory.is_current.is_(True),
                Cuenta.fecha_separacion.isnot(None),
            )
            .order_by(AssignmentHistory.id.asc(), Cuenta.id.asc())
            .all()
        )
        processed_clients: set[int] = set()
        changed = False
        for history, account in current_histories:
            if history.cliente_id in processed_clients:
                continue
            processed_clients.add(history.cliente_id)
            target_placement = target_recovery_placement_for_vintage(account.fecha_separacion, history.cliente_id)
            current_scope = history.channel_scope or "EXTERNO"
            if current_scope == "EXTERNO":
                slot = EXTERNAL_AGENCY_SLOTS[history.cliente_id % len(EXTERNAL_AGENCY_SLOTS)]
                target_group = format_external_group_id(target_placement, slot)
            else:
                slot = INTERNAL_WORKLIST_SLOTS[history.cliente_id % len(INTERNAL_WORKLIST_SLOTS)]
                target_group = format_internal_group_id(target_placement, slot)
            if history.placement_code != target_placement or history.group_id != target_group:
                history.placement_code = target_placement
                history.group_id = target_group
                changed = True
        if changed:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()


def backfill_assignment_history() -> None:
    db = SessionLocal()
    try:
        active_assignments = db.query(WorklistAssignment).filter(WorklistAssignment.activa.is_(True)).all()
        for assignment in active_assignments:
            exists = (
                db.query(AssignmentHistory)
                .filter(
                    AssignmentHistory.assignment_id == assignment.id,
                    AssignmentHistory.is_current.is_(True),
                )
                .first()
            )
            if exists:
                continue
            client = db.get(Cliente, assignment.cliente_id)
            user = db.get(Usuario, assignment.usuario_id)
            if not client:
                continue
            record_assignment_history(
                db,
                client,
                assignment,
                strategy_code=assignment.estrategia_codigo,
                notes="Backfill automático del historial de asignación.",
                user=user,
            )
        db.commit()
    finally:
        db.close()


def get_omnichannel_settings(db: Session) -> dict:
    row = db.execute(
        text(
            """
            SELECT
                whatsapp_bot_enabled,
                email_enabled,
                callbot_enabled,
                inbound_bot_enabled,
                automation_enabled,
                webhooks_configured,
                template_library_ready,
                twilio_account_sid,
                twilio_auth_token,
                twilio_whatsapp_from,
                twilio_demo_phone,
                resend_api_key,
                email_from,
                smtp_host,
                smtp_port,
                smtp_user,
                smtp_password,
                sms_provider,
                textbelt_api_key,
                twilio_sms_from,
                callbot_webhook_url,
                twilio_voice_from,
                notes,
                updated_at
            FROM omnichannel_settings
            WHERE id = 1
            """
        )
    ).mappings().first()
    return dict(row) if row else {
        "whatsapp_bot_enabled": False,
        "email_enabled": False,
        "callbot_enabled": False,
        "inbound_bot_enabled": False,
        "automation_enabled": False,
        "webhooks_configured": False,
        "template_library_ready": False,
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_whatsapp_from": "whatsapp:+14155238886",
        "twilio_demo_phone": "",
        "resend_api_key": "",
        "email_from": "",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "sms_provider": "textbelt",
        "textbelt_api_key": "textbelt",
        "twilio_sms_from": "",
        "callbot_webhook_url": "",
        "twilio_voice_from": "",
        "notes": "",
        "updated_at": None,
    }


def build_admin_omnichannel_overview(db: Session) -> dict:
    settings_row = get_omnichannel_settings(db)
    whatsapp_candidates = (
        db.query(Cuenta.cliente_id)
        .join(Cliente, Cliente.id == Cuenta.cliente_id)
        .filter(Cliente.telefono.is_not(None), Cuenta.dias_mora <= 60)
        .distinct()
        .count()
    )
    email_candidates = (
        db.query(Cuenta.cliente_id)
        .join(Cliente, Cliente.id == Cuenta.cliente_id)
        .filter(Cliente.email.is_not(None), Cuenta.dias_mora <= 30)
        .distinct()
        .count()
    )
    callbot_candidates = (
        db.query(Cuenta.cliente_id)
        .join(Cliente, Cliente.id == Cuenta.cliente_id)
        .filter(Cliente.telefono.is_not(None), Cuenta.dias_mora >= 61)
        .distinct()
        .count()
    )
    rulebook = [
        {"strategy": "AL_DIA", "primary_channel": "Monitoreo sin contacto", "goal": "Seguimiento silencioso sin tocar al cliente."},
        {"strategy": "PREVENTIVO", "primary_channel": "Chatbot WhatsApp + correo", "goal": "Recordatorio preventivo y link de pago."},
        {"strategy": "FMORA1 / MMORA2", "primary_channel": "Chatbot WhatsApp + SMS", "goal": "Contención temprana y promesa corta."},
        {"strategy": "HMORA3 / AMORA4", "primary_channel": "Llamada + WhatsApp asistido", "goal": "Negociación humana y seguimiento cercano."},
        {"strategy": "BMORA5 / CMORA6 / DMORA7", "primary_channel": "Callbot + llamada humana", "goal": "Gestión intensiva con cierre o escalamiento."},
        {"strategy": "VAGENCIASEXTERNASINTERNO", "primary_channel": "Callbot + llamada humana + WhatsApp", "goal": "Recovery con placements, agencias y ruteo operativo."},
    ]
    flags = [
        settings_row["whatsapp_bot_enabled"],
        settings_row["email_enabled"],
        settings_row["callbot_enabled"],
        settings_row["inbound_bot_enabled"],
        settings_row["automation_enabled"],
        settings_row["webhooks_configured"],
        settings_row["template_library_ready"],
    ]
    readiness_score = round((sum(1 for flag in flags if flag) / len(flags)) * 100)
    if not settings_row["whatsapp_bot_enabled"]:
        next_step = "Activar WhatsApp bot para mora temprana y recordatorios preventivos."
    elif not settings_row["email_enabled"]:
        next_step = "Habilitar correo automatizado para preventivo, promesas y confirmaciones."
    elif not settings_row["callbot_enabled"]:
        next_step = "Conectar callbot para tramos HMORA3+ y campañas de recuperación intensiva."
    elif not settings_row["webhooks_configured"]:
        next_step = "Configurar webhooks para recibir respuestas, entregas y eventos de conversación."
    else:
        next_step = "Ajustar journeys y reglas de orquestación para operación omnicanal completa."
    return {
        "readiness_score": readiness_score,
        "notes": settings_row.get("notes") or "",
        "updated_at": settings_row.get("updated_at").isoformat() if settings_row.get("updated_at") else None,
        "next_step": next_step,
        "channels": [
            {
                "code": "whatsapp",
                "name": "WhatsApp bot",
                "enabled": bool(settings_row["whatsapp_bot_enabled"]),
                "candidates": whatsapp_candidates,
                "provider": "Twilio",
                "free_option": "Sandbox Twilio (cuenta trial)",
                "status": "Listo para mora temprana" if settings_row["whatsapp_bot_enabled"] else "Pendiente de activación",
            },
            {
                "code": "email",
                "name": "Correo automatizado",
                "enabled": bool(settings_row["email_enabled"]),
                "candidates": email_candidates,
                "provider": "Resend.com",
                "free_option": "100 emails/día gratis sin tarjeta — resend.com/signup",
                "status": "Listo para preventivo y confirmaciones" if settings_row["email_enabled"] else "Pendiente de activación",
            },
            {
                "code": "sms",
                "name": "SMS automatizado",
                "enabled": bool(settings_row.get("sms_provider") not in {None, ""}),
                "candidates": whatsapp_candidates,
                "provider": settings_row.get("sms_provider") or "textbelt",
                "free_option": "TextBelt: 1 SMS/día gratis sin cuenta — textbelt.com",
                "status": "Activo con TextBelt demo" if settings_row.get("sms_provider") == "textbelt" else "Pendiente de activación",
            },
            {
                "code": "callbot",
                "name": "Callbot / voz IVR",
                "enabled": bool(settings_row["callbot_enabled"]),
                "candidates": callbot_candidates,
                "provider": "Twilio Voice",
                "free_option": "Twilio trial: llama a números verificados gratis — twilio.com/try-twilio",
                "status": "Listo para mora alta y barridos" if settings_row["callbot_enabled"] else "Pendiente de activación",
            },
        ],
        "controls": {
            "whatsapp_bot_enabled": bool(settings_row["whatsapp_bot_enabled"]),
            "email_enabled": bool(settings_row["email_enabled"]),
            "callbot_enabled": bool(settings_row["callbot_enabled"]),
            "inbound_bot_enabled": bool(settings_row["inbound_bot_enabled"]),
            "automation_enabled": bool(settings_row["automation_enabled"]),
            "webhooks_configured": bool(settings_row["webhooks_configured"]),
            "template_library_ready": bool(settings_row["template_library_ready"]),
            "twilio_account_sid": settings_row.get("twilio_account_sid") or "",
            "twilio_auth_token": settings_row.get("twilio_auth_token") or "",
            "twilio_whatsapp_from": settings_row.get("twilio_whatsapp_from") or "whatsapp:+14155238886",
            "twilio_demo_phone": settings_row.get("twilio_demo_phone") or "",
        },
        "journeys": rulebook,
    }


def build_admin_alerts(
    db: Session,
    *,
    total_clients: int,
    assigned_clients: int,
    omnichannel_overview: dict,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    unassigned_clients = max(0, total_clients - assigned_clients)
    if unassigned_clients > 0:
        alerts.append(
            {
                "severity": "warning",
                "title": "Clientes sin asignar",
                "detail": f"Hay {unassigned_clients} clientes sin cartera visible. Conviene asignarlos para no perder cobertura operativa.",
                "module": "assignments",
            }
        )

    readiness_score = int(omnichannel_overview.get("readiness_score") or 0)
    if readiness_score < 100:
        alerts.append(
            {
                "severity": "info",
                "title": "Omnicanalidad incompleta",
                "detail": f"El readiness actual es {readiness_score}%. Aún quedan integraciones o canales por activar.",
                "module": "omnichannel",
            }
        )

    pending_supervisor_reviews = db.query(Promesa).filter(Promesa.estado == "REVISION_SUPERVISOR").count()
    if pending_supervisor_reviews > 0:
        alerts.append(
            {
                "severity": "warning",
                "title": "Revisiones supervisor pendientes",
                "detail": f"Hay {pending_supervisor_reviews} acuerdos fuera de política esperando revisión.",
                "module": "summary",
            }
        )

    callbacks_today = db.query(History).filter(
        History.accion == "CALLBACK_PROGRAMADO",
        func.date(History.created_at) == date.today(),
    ).count()
    if callbacks_today > 25:
        alerts.append(
            {
                "severity": "info",
                "title": "Alta carga de callbacks",
                "detail": f"Se detectaron {callbacks_today} callbacks programados hoy. Revisa capacidad operativa del equipo.",
                "module": "collector_preview",
            }
        )

    return alerts


def normalize_whatsapp_phone(raw_phone: str) -> str:
    digits = re.sub(r"\D", "", raw_phone or "")
    if not digits:
        raise HTTPException(status_code=400, detail="Debes ingresar un número destino válido para WhatsApp.")
    if not digits.startswith("503") and len(digits) == 8:
        digits = f"503{digits}"
    if not digits.startswith("503") and not digits.startswith("1"):
        digits = digits
    return f"whatsapp:+{digits}"


def build_whatsapp_demo_message(client: Optional[Cliente], strategy_code: Optional[str], custom_message: Optional[str], account_reference: Optional[str] = None) -> str:
    if custom_message and custom_message.strip():
        return custom_message.strip()
    greeting_name = client.nombres if client else "cliente"
    last4 = account_reference or "****"
    body = (
        f"Buenas tardes, le saluda 360CollectPlus. ¿Hablo con {greeting_name}? "
        "Tenemos información sobre una cuenta en seguimiento con terminación "
        f"{last4}. Responda SI si es el titular o ASESOR si desea atención humana."
    )
    return body


def send_twilio_whatsapp_message(account_sid: str, auth_token: str, from_whatsapp: str, to_whatsapp: str, body: str) -> dict:
    pair = f"{account_sid}:{auth_token}"
    basic_auth = base64.b64encode(pair.encode("ascii")).decode("ascii")
    encoded = urllib_parse.urlencode({
        "To": to_whatsapp,
        "From": from_whatsapp,
        "Body": body,
    }).encode("utf-8")
    request = urllib_request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=400, detail=f"Twilio rechazó el envío: {detail or error.reason}")
    except URLError as error:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con Twilio: {error.reason}")


def get_or_create_whatsapp_bot_session(
    db: Session,
    phone_number: str,
    client: Optional[Cliente] = None,
    strategy_code: Optional[str] = None,
) -> WhatsAppBotSession:
    session = (
        db.query(WhatsAppBotSession)
        .filter(WhatsAppBotSession.phone_number == phone_number, WhatsAppBotSession.status == "ACTIVE")
        .order_by(WhatsAppBotSession.updated_at.desc())
        .first()
    )
    if session:
        if client and not session.client_id:
            session.client_id = client.id
        if strategy_code:
            session.strategy_code = strategy_code
        session.updated_at = datetime.utcnow()
        return session
    session = WhatsAppBotSession(
        phone_number=phone_number,
        client_id=client.id if client else None,
        strategy_code=strategy_code,
        status="ACTIVE",
        context_json=json.dumps({"step": "menu"}),
        last_message_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(session)
    db.flush()
    return session


def load_whatsapp_session_context(session: WhatsAppBotSession) -> dict:
    if not session.context_json:
        return {"step": "menu"}
    try:
        return json.loads(session.context_json)
    except json.JSONDecodeError:
        return {"step": "menu"}


def save_whatsapp_session_context(session: WhatsAppBotSession, context: dict) -> None:
    session.context_json = json.dumps(context)
    session.updated_at = datetime.utcnow()
    session.last_message_at = datetime.utcnow()


def find_client_for_whatsapp_session(db: Session, phone_number: str, session: Optional[WhatsAppBotSession]) -> Optional[Cliente]:
    if session and session.client_id:
        return db.get(Cliente, session.client_id)
    normalized_digits = re.sub(r"\D", "", phone_number or "")
    local_digits = normalized_digits[-8:] if len(normalized_digits) >= 8 else normalized_digits
    return (
        db.query(Cliente)
        .filter(
            (Cliente.telefono == phone_number)
            | (Cliente.telefono == normalized_digits)
            | (Cliente.telefono == local_digits)
            | (Cliente.telefono == f"+{normalized_digits}")
        )
        .first()
    )


def render_twiml_message(body: str) -> str:
    safe_body = (
        body.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_body}</Message></Response>'


def extract_whatsapp_amount_and_date(message: str) -> tuple[Optional[float], Optional[date]]:
    text_value = (message or "").strip().lower()
    amount_match = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", text_value)
    amount = float(amount_match.group(1)) if amount_match else None

    date_match = re.search(r"(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?", text_value)
    promise_date = None
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else datetime.utcnow().year
        if year < 100:
            year += 2000
        try:
            promise_date = date(year, month, day)
        except ValueError:
            promise_date = None
    return amount, promise_date


def register_bot_promise(
    db: Session,
    client: Cliente,
    accounts: list[Cuenta],
    amount: float,
    promise_date: date,
    strategy_code: str,
    phone_number: str,
) -> tuple[list[Promesa], float]:
    minimum_total = round(sum(calculate_minimum_payment(account) for account in accounts), 2)
    total_minimum = max(minimum_total, 0.01)
    created_promises: list[Promesa] = []
    now_ts = datetime.now(timezone.utc)
    for account in accounts:
        account_minimum = calculate_minimum_payment(account)
        allocated_amount = round(float(amount) * (account_minimum / total_minimum), 2)
        promise = Promesa(
            cuenta_id=account.id,
            usuario_id=None,
            fecha_promesa=promise_date,
            monto_prometido=allocated_amount,
            estado="PENDIENTE",
            created_at=now_ts,
        )
        db.add(promise)
        created_promises.append(promise)
    db.add(
        History(
            entidad="clientes",
            entidad_id=client.id,
            accion="PROMESA_CREADA_BOT",
            descripcion=(
                f"Promesa capturada por bot WhatsApp. Estrategia: {strategy_code}. "
                f"Telefono: {phone_number}. Monto total: {amount:.2f}. Fecha: {promise_date.isoformat()}."
            ),
            usuario_id=None,
            created_at=now_ts,
        )
    )
    return created_promises, minimum_total


def build_whatsapp_bot_reply(db: Session, client: Optional[Cliente], session: WhatsAppBotSession, inbound_message: str) -> str:
    message = (inbound_message or "").strip().lower()
    context = load_whatsapp_session_context(session)
    strategy_code = session.strategy_code or "GENERAL"

    if not client:
        save_whatsapp_session_context(session, {"step": "menu"})
        return (
            "Hola, soy el bot de cobranza de 360CollectPlus. "
            "Aún no pude vincular tu número a una cuenta específica. "
            "Responde con tu código de cliente o escribe ASESOR para enviarte con un gestor."
        )

    accounts = (
        db.query(Cuenta)
        .filter(Cuenta.cliente_id == client.id, Cuenta.saldo_mora > 0)
        .order_by(Cuenta.dias_mora.desc(), Cuenta.saldo_mora.desc())
        .all()
    )
    if not accounts:
        save_whatsapp_session_context(session, {"step": "menu", "identified": True})
        return (
            f"Hola {client.nombres}, por el momento no vemos cuentas vencidas activas en tu expediente. "
            "Gracias por atendernos. Si necesitas apoyo adicional, responde ASESOR."
        )
    total_due = round(sum(float(account.saldo_mora or 0) for account in accounts), 2)
    total_balance = round(sum(float(account.saldo_total or 0) for account in accounts), 2)
    minimum_total = round(sum(calculate_minimum_payment(account) for account in accounts), 2)
    latest_due_date = add_business_days(datetime.utcnow().date(), 5)
    primary_account = accounts[0]
    primary_last4 = primary_account.numero_cuenta[-4:]
    pending_promises = (
        db.query(Promesa)
        .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
        .filter(Cuenta.cliente_id == client.id, Promesa.estado.in_(["PENDIENTE", "REVISION_SUPERVISOR"]))
        .all()
    )
    identified = bool(context.get("identified"))
    if message in {"hola", "menu", "menú", "ayuda", "inicio"}:
        save_whatsapp_session_context(
            session,
            {
                "step": "await_identity",
                "identified": False,
                "minimum_total": minimum_total,
                "latest_due_date": latest_due_date.isoformat(),
                "primary_last4": primary_last4,
            },
        )
        return (
            f"Buenas tardes, le saluda 360CollectPlus. ¿Hablo con {client.nombres}? "
            f"Tengo información sobre su cuenta con terminación {primary_last4}. "
            "Responda SI si es el titular o ASESOR si desea atención humana."
        )

    if message in {"4", "asesor", "humano", "gestor"}:
        save_whatsapp_session_context(session, {"step": "handoff", "identified": identified})
        return (
            "Gracias por su tiempo. Un asesor se estará comunicando posteriormente para continuar la gestión. "
            "Quedamos a la orden."
        )

    if not identified:
        if message in {"si", "sí", "soy yo", "yo", "correcto", "confirmo"}:
            save_whatsapp_session_context(
                session,
                {
                    "step": "offer_payment",
                    "identified": True,
                    "minimum_total": minimum_total,
                    "latest_due_date": latest_due_date.isoformat(),
                    "primary_last4": primary_last4,
                },
            )
            return (
                f"Gracias por confirmar identidad, {client.nombres}. "
                f"Vemos {len(accounts)} cuenta(s) en mora con saldo vencido total de ${total_due:,.2f}. "
                f"Para regularizar hoy necesitamos al menos ${minimum_total:,.2f} "
                f"con compromiso máximo al {latest_due_date.strftime('%d/%m/%Y')} (5 días hábiles). "
                "Responda ACEPTAR para registrar ese acuerdo, o envíe MONTO y FECHA en formato: 281.06 02/04/2026. "
                "Si no es posible, responda ASESOR."
            )
        return (
            f"Para continuar necesito confirmar identidad del titular de la cuenta terminación {primary_last4}. "
            "Responda SI si es el cliente o ASESOR para seguimiento humano."
        )

    if message in {"1", "saldo", "consulta saldo"}:
        save_whatsapp_session_context(session, {"step": "offer_payment", "identified": True, "minimum_total": minimum_total, "latest_due_date": latest_due_date.isoformat(), "primary_last4": primary_last4})
        return (
            f"Actualmente tiene {len(accounts)} cuenta(s) en mora. "
            f"Saldo vencido total: ${total_due:,.2f}. Saldo total visible: ${total_balance:,.2f}. "
            f"El pago mínimo sugerido es ${minimum_total:,.2f} con fecha máxima {latest_due_date.strftime('%d/%m/%Y')}. "
            "Responda ACEPTAR para registrarlo o indique MONTO y FECHA."
        )

    if message in {"2", "promesa", "acuerdo", "promesa de pago", "aceptar", "acepto"}:
        if pending_promises:
            nearest = min(pending_promises, key=lambda item: item.fecha_promesa)
            save_whatsapp_session_context(session, {"step": "handoff", "identified": True})
            return (
                f"Ya existe una promesa pendiente por ${float(nearest.monto_prometido or 0):,.2f} con fecha {nearest.fecha_promesa}. "
                "Gracias por su tiempo. Un asesor se estará comunicando posteriormente para revisar el caso."
            )
        register_bot_promise(db, client, accounts, minimum_total, latest_due_date, strategy_code, session.phone_number)
        save_whatsapp_session_context(session, {"step": "closed", "identified": True})
        return (
            f"Gracias, {client.nombres}. Se registró su acuerdo por ${minimum_total:,.2f} con fecha {latest_due_date.strftime('%d/%m/%Y')}. "
            "Agradecemos su compromiso de pago. Quedamos atentos y gracias por su tiempo."
        )

    custom_amount, custom_date = extract_whatsapp_amount_and_date(message)
    if custom_amount is not None or custom_date is not None:
        if custom_amount is None or custom_date is None:
            return "Para registrar el acuerdo necesito MONTO y FECHA. Ejemplo: 281.06 02/04/2026."
        if custom_amount < minimum_total:
            return (
                f"El monto propuesto es menor al mínimo sugerido de ${minimum_total:,.2f}. "
                "Por política, necesito al menos ese monto para los próximos 5 días hábiles. "
                f"Puedes responder ACEPTAR o proponer un monto mayor con fecha máxima {latest_due_date.strftime('%d/%m/%Y')}."
            )
        if custom_date > latest_due_date:
            return (
                f"La fecha propuesta excede el máximo permitido de 5 días hábiles. "
                f"La fecha límite disponible es {latest_due_date.strftime('%d/%m/%Y')}. "
                "Puedes responder nuevamente con monto y una fecha válida."
            )
        if pending_promises:
            save_whatsapp_session_context(session, {"step": "handoff", "identified": True})
            return "Ya existe una promesa activa en el sistema. Gracias por su tiempo; un asesor se estará comunicando posteriormente."
        register_bot_promise(db, client, accounts, custom_amount, custom_date, strategy_code, session.phone_number)
        save_whatsapp_session_context(session, {"step": "closed", "identified": True})
        return (
            f"Gracias, {client.nombres}. Se registró su acuerdo por ${custom_amount:,.2f} con fecha {custom_date.strftime('%d/%m/%Y')}. "
            "Agradecemos su compromiso de pago. Quedamos atentos y gracias por su tiempo."
        )

    if message in {"3", "pagar", "pago", "link"}:
        save_whatsapp_session_context(session, {"step": "offer_payment", "identified": True, "minimum_total": minimum_total, "latest_due_date": latest_due_date.isoformat(), "primary_last4": primary_last4})
        return (
            f"Para esta fase del bot trabajaremos con acuerdo de pago. "
            f"El compromiso mínimo requerido es ${minimum_total:,.2f} con fecha máxima {latest_due_date.strftime('%d/%m/%Y')}. "
            "Responda ACEPTAR para registrarlo o envíe MONTO y FECHA."
        )

    if message in {"no", "no puedo", "no es posible", "no deseo", "despues", "después"}:
        save_whatsapp_session_context(session, {"step": "handoff", "identified": True})
        return (
            "Entendido. Gracias por su tiempo. Un asesor se estará comunicando posteriormente para continuar la gestión. "
            "Que tenga buena tarde."
        )

    if context.get("step") in {"offer_payment", "promise", "payment", "menu", "await_identity"}:
        return (
            f"Mi objetivo es ayudarte a regularizar tu saldo vencido de ${total_due:,.2f}. "
            f"Necesitamos al menos ${minimum_total:,.2f} para una fecha no mayor al {latest_due_date.strftime('%d/%m/%Y')}. "
            "Responda ACEPTAR, o envíe MONTO y FECHA, o escriba ASESOR."
        )

    return "Gracias por escribirnos. Si deseas continuar la gestión, responde ACEPTAR, indica MONTO y FECHA, o escribe ASESOR."


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$2"):
        return pwd_context.verify(plain_password, hashed_password)
    return plain_password == hashed_password


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class UserBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=120)
    email: str
    username: str = Field(..., min_length=3, max_length=80)
    rol: str = Field(..., min_length=3, max_length=40)
    activo: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=64)


class UserUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=120)
    email: Optional[str] = None
    username: Optional[str] = Field(None, min_length=3, max_length=80)
    rol: Optional[str] = Field(None, min_length=3, max_length=40)
    activo: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=64)


class UserRead(UserBase):
    id: int
    ultimo_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ClienteBase(BaseModel):
    identity_code: str
    nombres: str
    apellidos: str
    dui: str
    nit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    score_riesgo: float = 0.5
    segmento: Optional[str] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    score_riesgo: Optional[float] = None
    segmento: Optional[str] = None


class ClienteRead(ClienteBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CuentaBase(BaseModel):
    cliente_id: int
    numero_cuenta: str
    tipo_producto: str
    subtipo_producto: Optional[str] = None
    saldo_capital: float
    saldo_mora: float = 0
    saldo_total: float
    dias_mora: int = 0
    bucket_actual: str = "0-30"
    estado: str = "ACTIVA"
    fecha_separacion: Optional[date] = None
    tasa_interes: float = 0
    es_estrafinanciamiento: bool = False


class CuentaCreate(CuentaBase):
    pass


class CuentaUpdate(BaseModel):
    saldo_capital: Optional[float] = None
    saldo_mora: Optional[float] = None
    saldo_total: Optional[float] = None
    dias_mora: Optional[int] = None
    bucket_actual: Optional[str] = None
    estado: Optional[str] = None


class CuentaRead(CuentaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class PagoBase(BaseModel):
    cuenta_id: int
    monto: float
    fecha_pago: datetime
    canal: str = "digital"
    referencia: Optional[str] = None
    observacion: Optional[str] = None


class PagoCreate(PagoBase):
    pass


class PagoRead(PagoBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class PredictionResponse(BaseModel):
    cuenta_id: int
    probabilidad_pago_30d: float
    score_modelo: float
    recomendacion: str


class PromiseRead(BaseModel):
    id: int
    cuenta_id: int
    fecha_promesa: str
    monto_prometido: float
    estado: str


class CollectorAccountRead(BaseModel):
    id: int
    numero_cuenta: str
    numero_plastico: Optional[str] = None
    codigo_ubicacion: Optional[str] = None
    tipo_producto: str
    producto_nombre: Optional[str] = None
    subtipo_producto: Optional[str] = None
    segmento_producto: Optional[str] = None
    estado: str
    saldo_total: float
    saldo_mora: float
    dias_mora: int
    bucket_actual: str
    es_estrafinanciamiento: bool
    ciclo_corte: int
    dia_vencimiento: int
    estrategia: str
    hmr_elegible: bool
    pago_minimo: float
    ai_probability: Optional[float] = None
    ai_score: Optional[float] = None
    ai_recommendation: Optional[str] = None


class ManagementHistoryRead(BaseModel):
    id: int
    fecha: str
    accion: str
    descripcion: Optional[str] = None
    usuario_id: Optional[int] = None


class CollectorClientRead(BaseModel):
    id: int
    identity_code: str
    dui: Optional[str] = None
    nombres: str
    apellidos: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    segmento: Optional[str] = None
    score_riesgo: float
    accounts: list[CollectorAccountRead]
    pending_promises: list[PromiseRead]
    last_management: Optional[str] = None
    worked_today: bool = False
    estrategia_principal: str
    estrategia_subgrupo: Optional[str] = None
    segmento_operativo: Optional[str] = None
    producto_cabeza: Optional[str] = None
    dias_mora_cabeza: Optional[int] = None
    hmr_elegible: bool
    total_outstanding: float
    next_callback_at: Optional[str] = None
    requires_supervisor_review: bool = False
    management_history: list[ManagementHistoryRead]
    ai_best_channel: Optional[str] = None
    ai_promise_break_probability: Optional[float] = None
    ai_next_action: Optional[str] = None
    ai_talk_track: Optional[str] = None
    placement_code: Optional[str] = None
    group_id: Optional[str] = None
    sublista_trabajo: Optional[str] = None
    sublista_descripcion: Optional[str] = None


class CollectorMetrics(BaseModel):
    assigned_today: int
    remaining_today: int
    worked_today: int
    payment_agreements_today: int
    due_promises_today: int
    total_outstanding: float
    hmr_candidates: int
    strategy_summary: dict[str, int]
    scheduled_callbacks_today: int
    supervisor_reviews_pending: int


class StrategyRead(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    orden: int
    activa: bool

    model_config = ConfigDict(from_attributes=True)


class StrategyCreate(BaseModel):
    codigo: str = Field(..., min_length=3, max_length=50)
    nombre: str = Field(..., min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    categoria: Optional[str] = Field(default="COBRANZA", max_length=50)
    orden: int = 0
    activa: bool = True


class WorklistAssignRequest(BaseModel):
    user_id: int
    strategy_code: Optional[str] = None
    client_ids: list[int]


class AdminOverviewResponse(BaseModel):
    strategies: list[StrategyRead]
    collectors: list[UserRead]
    total_clients: int
    assigned_clients: int
    unassigned_clients: int
    hmr_clients: int
    omnichannel: dict


class AssignmentHistoryRead(BaseModel):
    id: int
    cliente_id: int
    usuario_id: Optional[int] = None
    strategy_code: Optional[str] = None
    placement_code: Optional[str] = None
    channel_scope: Optional[str] = None
    group_id: Optional[str] = None
    sublista_codigo: Optional[str] = None
    assigned_share_pct: Optional[float] = None
    efficiency_pct: Optional[float] = None
    tenure_days: int
    minimum_payment_to_progress: float
    segment_snapshot: Optional[str] = None
    account_status_snapshot: Optional[str] = None
    max_days_past_due_snapshot: Optional[int] = None
    total_due_snapshot: Optional[float] = None
    notes: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    is_current: bool

    model_config = ConfigDict(from_attributes=True)


class AdminDocumentProposalResponse(BaseModel):
    proposal_id: str
    file_name: str
    generated_at: datetime
    status: str
    summary: str
    extracted_context: list[str]
    suggested_strategies: list[dict]
    suggested_channel_rules: list[dict]
    suggested_sublists: list[dict]
    implementation_notes: list[str]


class AdminDocumentProposalUpdate(BaseModel):
    summary: str
    suggested_strategies: list[dict]
    suggested_channel_rules: list[dict]
    suggested_sublists: list[dict]
    implementation_notes: list[str]


class AdminImportProposalResponse(BaseModel):
    proposal_id: str
    file_name: str
    generated_at: datetime
    status: str
    summary: str
    total_rows: int
    valid_rows: int
    error_rows: int
    new_clients: int
    existing_clients: int
    new_accounts: int
    existing_accounts: int
    assignments_ready: int
    preview_rows: list[dict]
    sample_errors: list[str]
    expected_columns: list[str]


class AdminGeneratedReportRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=1000)


class AdminGeneratedReportResponse(BaseModel):
    title: str
    summary: str
    cards: list[dict]
    charts: list[dict]
    insights: list[str]


class AdminDailySimulationRequest(BaseModel):
    fmora1_clients: int = Field(default=250, ge=0, le=5000)
    preventivo_clients: int = Field(default=120, ge=0, le=5000)
    recovery_clients: int = Field(default=1000, ge=0, le=5000)


class AdminDailySimulationResponse(BaseModel):
    simulation_key: str
    aged_accounts: int
    inserted_fmora1_clients: int
    inserted_preventivo_clients: int
    inserted_recovery_clients: int
    simulated_payments: int
    fully_cured_accounts: int
    recovery_rotations: int
    total_clients: int
    total_accounts: int
    message: str


class AdminOmnichannelConfigUpdate(BaseModel):
    whatsapp_bot_enabled: bool
    email_enabled: bool
    callbot_enabled: bool
    inbound_bot_enabled: bool
    automation_enabled: bool
    webhooks_configured: bool
    template_library_ready: bool
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_demo_phone: Optional[str] = None
    twilio_sms_from: Optional[str] = None
    twilio_voice_from: Optional[str] = None
    callbot_webhook_url: Optional[str] = None
    resend_api_key: Optional[str] = None
    email_from: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    sms_provider: Optional[str] = "textbelt"
    textbelt_api_key: Optional[str] = "textbelt"
    notes: Optional[str] = None


class AdminWhatsAppDemoSendRequest(BaseModel):
    to_phone: str = Field(..., min_length=8, max_length=30)
    client_id: Optional[int] = None
    strategy_code: Optional[str] = None
    custom_message: Optional[str] = None


class SupervisorCollectorMetric(BaseModel):
    user: UserRead
    assigned_clients: int
    managed_today: int
    payment_agreements_today: int
    recovered_balance_today: float


class SupervisorOverviewResponse(BaseModel):
    supervisor: UserRead
    team_size: int
    managed_today: int
    payment_agreements_today: int
    recovered_balance_today: float
    collectors: list[SupervisorCollectorMetric]
    review_queue: list[dict]
    alerts: list[dict]


class CollectorPortfolioResponse(BaseModel):
    collector: UserRead
    metrics: CollectorMetrics
    clients: list[CollectorClientRead]


class CollectorManagementCreate(BaseModel):
    client_id: int
    account_id: int
    account_ids: list[int] = Field(default_factory=list)
    contact_channel: str = Field(..., min_length=3, max_length=40)
    called_phone: Optional[str] = Field(default=None, max_length=40)
    rdm: Optional[str] = Field(default=None, max_length=80)
    management_type: str = Field(..., min_length=3, max_length=60)
    result: str = Field(..., min_length=3, max_length=60)
    notes: str = Field(..., min_length=3, max_length=500)
    promise_date: Optional[datetime] = None
    promise_amount: Optional[float] = None
    callback_at: Optional[datetime] = None


class DemographicPhoneItem(BaseModel):
    id: Optional[int] = None
    phone_type: str = Field(default="CEL", min_length=3, max_length=20)
    value: str = Field(..., min_length=3, max_length=40)
    is_primary: bool = False


class DemographicEmailItem(BaseModel):
    id: Optional[int] = None
    value: str = Field(..., min_length=5, max_length=180)
    is_primary: bool = False


class DemographicAddressItem(BaseModel):
    id: Optional[int] = None
    address_type: str = Field(default="CASA", min_length=3, max_length=20)
    value: str = Field(..., min_length=5, max_length=500)
    is_primary: bool = False


class DemographicUpdate(BaseModel):
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    phones: list[DemographicPhoneItem] = Field(default_factory=list)
    emails: list[DemographicEmailItem] = Field(default_factory=list)
    addresses: list[DemographicAddressItem] = Field(default_factory=list)


class DemographicProfileRead(BaseModel):
    cliente_id: int
    phones: list[DemographicPhoneItem] = Field(default_factory=list)
    emails: list[DemographicEmailItem] = Field(default_factory=list)
    addresses: list[DemographicAddressItem] = Field(default_factory=list)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


def get_user_by_username(db: Session, username: str) -> Optional[Usuario]:
    return db.query(Usuario).filter(Usuario.username == username).first()


def get_collectors(db: Session) -> list[Usuario]:
    return db.query(Usuario).filter(Usuario.rol == "Collector", Usuario.activo.is_(True)).order_by(Usuario.id).all()


def get_supervisors(db: Session) -> list[Usuario]:
    return db.query(Usuario).filter(Usuario.rol == "Supervisor", Usuario.activo.is_(True)).order_by(Usuario.id).all()


def get_explicit_collectors_for_supervisor(db: Session, supervisor_id: int) -> list[Usuario]:
    rows = db.execute(
        text(
            """
            SELECT u.*
            FROM supervisor_assignments sa
            JOIN usuarios u ON u.id = sa.collector_id
            WHERE sa.supervisor_id = :supervisor_id
              AND u.rol = 'Collector'
              AND u.activo = TRUE
            ORDER BY u.id
            """
        ),
        {"supervisor_id": supervisor_id},
    ).mappings().all()
    if not rows:
        return []
    return [db.get(Usuario, row["id"]) for row in rows if db.get(Usuario, row["id"])]


def get_collectors_for_supervisor(db: Session, supervisor: Usuario) -> list[Usuario]:
    explicit_collectors = get_explicit_collectors_for_supervisor(db, supervisor.id)
    if explicit_collectors:
        return explicit_collectors

    supervisors = get_supervisors(db)
    collectors = get_collectors(db)
    if not supervisors or not collectors:
        return []

    supervisor_ids = [item.id for item in supervisors]
    supervisor_index = supervisor_ids.index(supervisor.id)
    return [collector for index, collector in enumerate(collectors) if index % len(supervisors) == supervisor_index]


def format_worklist_group_display(strategy_code: Optional[str], placement_code: Optional[str], group_id: Optional[str]) -> str:
    if placement_code and group_id:
        return f"{strategy_code or 'SIN_ESTRATEGIA'} · {placement_code} · {group_id}"
    if group_id:
        return f"{strategy_code or 'SIN_ESTRATEGIA'} · {group_id}"
    return strategy_code or "SIN_GRUPO"


def get_worklist_groups_for_user(db: Session, user_id: int) -> list[WorklistGroupRead]:
    rows = db.execute(
        text(
            """
            SELECT
                ah.strategy_code,
                ah.placement_code,
                ah.group_id,
                ah.channel_scope,
                COUNT(DISTINCT a.cliente_id) AS client_count
            FROM asignaciones_cartera a
            JOIN assignment_history ah
              ON ah.cliente_id = a.cliente_id
             AND ah.usuario_id = a.usuario_id
             AND ah.is_current = TRUE
            WHERE a.usuario_id = :user_id
              AND a.activa = TRUE
            GROUP BY ah.strategy_code, ah.placement_code, ah.group_id, ah.channel_scope
            ORDER BY ah.strategy_code, ah.placement_code, ah.group_id
            """
        ),
        {"user_id": user_id},
    ).mappings().all()
    return [
        WorklistGroupRead(
            strategy_code=row["strategy_code"],
            placement_code=row["placement_code"],
            group_id=row["group_id"],
            channel_scope=row["channel_scope"],
            client_count=int(row["client_count"] or 0),
            display_name=format_worklist_group_display(row["strategy_code"], row["placement_code"], row["group_id"]),
        )
        for row in rows
    ]


def get_worklist_group_catalog(db: Session) -> list[WorklistGroupRead]:
    rows = db.execute(
        text(
            """
            SELECT
                ah.strategy_code,
                ah.placement_code,
                ah.group_id,
                ah.channel_scope,
                COUNT(DISTINCT ah.cliente_id) AS client_count
            FROM assignment_history ah
            WHERE ah.is_current = TRUE
              AND ah.group_id IS NOT NULL
            GROUP BY ah.strategy_code, ah.placement_code, ah.group_id, ah.channel_scope
            ORDER BY ah.strategy_code, ah.placement_code, ah.group_id
            """
        )
    ).mappings().all()
    return [
        WorklistGroupRead(
            strategy_code=row["strategy_code"],
            placement_code=row["placement_code"],
            group_id=row["group_id"],
            channel_scope=row["channel_scope"],
            client_count=int(row["client_count"] or 0),
            display_name=format_worklist_group_display(row["strategy_code"], row["placement_code"], row["group_id"]),
        )
        for row in rows
    ]


def normalize_phone_type(value: Optional[str]) -> str:
    normalized = (value or "CEL").strip().upper()
    return normalized if normalized in {"CASA", "TRABAJO", "CEL"} else "CEL"


def normalize_address_type(value: Optional[str]) -> str:
    normalized = (value or "CASA").strip().upper()
    return normalized if normalized in {"CASA", "TRABAJO", "OTRA"} else "CASA"


def _ensure_primary_flag(items: list[dict]) -> list[dict]:
    if not items:
        return []
    primary_index = next((index for index, item in enumerate(items) if item.get("is_primary")), 0)
    for index, item in enumerate(items):
        item["is_primary"] = index == primary_index
    return items


def get_client_demographic_profile(db: Session, client: Cliente) -> DemographicProfileRead:
    phone_rows = db.execute(
        text(
            """
            SELECT id, phone_type, value, is_primary
            FROM client_contact_points
            WHERE cliente_id = :client_id
              AND contact_kind = 'PHONE'
              AND activa = TRUE
            ORDER BY is_primary DESC, id ASC
            """
        ),
        {"client_id": client.id},
    ).mappings().all()
    email_rows = db.execute(
        text(
            """
            SELECT id, value, is_primary
            FROM client_contact_points
            WHERE cliente_id = :client_id
              AND contact_kind = 'EMAIL'
              AND activa = TRUE
            ORDER BY is_primary DESC, id ASC
            """
        ),
        {"client_id": client.id},
    ).mappings().all()
    address_rows = db.execute(
        text(
            """
            SELECT id, address_type, value, is_primary
            FROM client_addresses
            WHERE cliente_id = :client_id
              AND activa = TRUE
            ORDER BY is_primary DESC, id ASC
            """
        ),
        {"client_id": client.id},
    ).mappings().all()

    phones = [
        DemographicPhoneItem(
            id=row["id"],
            phone_type=normalize_phone_type(row["phone_type"]),
            value=row["value"],
            is_primary=bool(row["is_primary"]),
        )
        for row in phone_rows
    ]
    emails = [
        DemographicEmailItem(
            id=row["id"],
            value=row["value"],
            is_primary=bool(row["is_primary"]),
        )
        for row in email_rows
    ]
    addresses = [
        DemographicAddressItem(
            id=row["id"],
            address_type=normalize_address_type(row["address_type"]),
            value=row["value"],
            is_primary=bool(row["is_primary"]),
        )
        for row in address_rows
    ]

    if not phones and client.telefono:
        phones = [DemographicPhoneItem(id=None, phone_type="CEL", value=client.telefono, is_primary=True)]
    if not emails and client.email:
        emails = [DemographicEmailItem(id=None, value=client.email, is_primary=True)]
    if not addresses and client.direccion:
        addresses = [DemographicAddressItem(id=None, address_type="CASA", value=client.direccion, is_primary=True)]

    return DemographicProfileRead(cliente_id=client.id, phones=phones, emails=emails, addresses=addresses)


def format_demographic_history(profile: DemographicProfileRead) -> str:
    phone_text = ", ".join(f"{item.phone_type}: {item.value}" for item in profile.phones) or "Sin telefonos"
    email_text = ", ".join(item.value for item in profile.emails) or "Sin correos"
    address_text = ", ".join(f"{item.address_type}: {item.value}" for item in profile.addresses) or "Sin direcciones"
    return f"Datos demograficos actualizados. Telefonos [{phone_text}] | Correos [{email_text}] | Direcciones [{address_text}]"


def save_client_demographic_profile(db: Session, client: Cliente, payload: DemographicUpdate, current_user: Usuario) -> DemographicProfileRead:
    phones = [
        {
            "phone_type": normalize_phone_type(item.phone_type),
            "value": item.value.strip(),
            "is_primary": bool(item.is_primary),
        }
        for item in payload.phones
        if item.value and item.value.strip()
    ]
    emails = [
        {
            "value": item.value.strip(),
            "is_primary": bool(item.is_primary),
        }
        for item in payload.emails
        if item.value and item.value.strip()
    ]
    addresses = [
        {
            "address_type": normalize_address_type(item.address_type),
            "value": item.value.strip(),
            "is_primary": bool(item.is_primary),
        }
        for item in payload.addresses
        if item.value and item.value.strip()
    ]

    if not phones and payload.telefono and payload.telefono.strip():
        phones = [{"phone_type": "CEL", "value": payload.telefono.strip(), "is_primary": True}]
    if not emails and payload.email and payload.email.strip():
        emails = [{"value": payload.email.strip(), "is_primary": True}]
    if not addresses and payload.direccion and payload.direccion.strip():
        addresses = [{"address_type": "CASA", "value": payload.direccion.strip(), "is_primary": True}]

    phones = _ensure_primary_flag(phones)
    emails = _ensure_primary_flag(emails)
    addresses = _ensure_primary_flag(addresses)

    db.execute(
        text(
            """
            UPDATE client_contact_points
            SET activa = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE cliente_id = :client_id
              AND activa = TRUE
            """
        ),
        {"client_id": client.id},
    )
    db.execute(
        text(
            """
            UPDATE client_addresses
            SET activa = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE cliente_id = :client_id
              AND activa = TRUE
            """
        ),
        {"client_id": client.id},
    )

    for item in phones:
        db.execute(
            text(
                """
                INSERT INTO client_contact_points (cliente_id, contact_kind, phone_type, value, is_primary, activa)
                VALUES (:client_id, 'PHONE', :phone_type, :value, :is_primary, TRUE)
                """
            ),
            {
                "client_id": client.id,
                "phone_type": item["phone_type"],
                "value": item["value"],
                "is_primary": item["is_primary"],
            },
        )
    for item in emails:
        db.execute(
            text(
                """
                INSERT INTO client_contact_points (cliente_id, contact_kind, phone_type, value, is_primary, activa)
                VALUES (:client_id, 'EMAIL', NULL, :value, :is_primary, TRUE)
                """
            ),
            {
                "client_id": client.id,
                "value": item["value"],
                "is_primary": item["is_primary"],
            },
        )
    for item in addresses:
        db.execute(
            text(
                """
                INSERT INTO client_addresses (cliente_id, address_type, value, is_primary, activa)
                VALUES (:client_id, :address_type, :value, :is_primary, TRUE)
                """
            ),
            {
                "client_id": client.id,
                "address_type": item["address_type"],
                "value": item["value"],
                "is_primary": item["is_primary"],
            },
        )

    client.telefono = next((item["value"] for item in phones if item["is_primary"]), phones[0]["value"] if phones else None)
    client.email = next((item["value"] for item in emails if item["is_primary"]), emails[0]["value"] if emails else None)
    client.direccion = next((item["value"] for item in addresses if item["is_primary"]), addresses[0]["value"] if addresses else None)

    profile = get_client_demographic_profile(db, client)
    db.add(
        History(
            entidad="clientes",
            entidad_id=client.id,
            accion="DEMOGRAFIA_ACTUALIZADA",
            descripcion=format_demographic_history(profile),
            usuario_id=current_user.id,
        )
    )
    return profile


def get_assigned_clients_for_collector(db: Session, collector: Usuario) -> list[Cliente]:
    explicit_assignments = (
        db.query(WorklistAssignment)
        .filter(WorklistAssignment.usuario_id == collector.id, WorklistAssignment.activa.is_(True))
        .order_by(WorklistAssignment.fecha_asignacion.desc())
        .all()
    )
    if explicit_assignments:
        assigned_ids = []
        seen = set()
        for item in explicit_assignments:
            if item.cliente_id not in seen:
                seen.add(item.cliente_id)
                assigned_ids.append(item.cliente_id)
        clients = db.query(Cliente).filter(Cliente.id.in_(assigned_ids)).all()
        clients_by_id = {client.id: client for client in clients}
        current_assignments = (
            db.query(AssignmentHistory)
            .filter(AssignmentHistory.cliente_id.in_(assigned_ids), AssignmentHistory.is_current.is_(True))
            .order_by(AssignmentHistory.start_at.desc(), AssignmentHistory.id.desc())
            .all()
        )
        current_by_client: dict[int, AssignmentHistory] = {}
        for row in current_assignments:
            current_by_client.setdefault(row.cliente_id, row)

        bucket_order = [
            "PREVENTIVO",
            "FMORA1",
            "MMORA2",
            "HMORA3",
            "AMORA4",
            "BMORA5",
            "CMORA6",
            "DMORA7",
            "VAGENCIASEXTERNASINTERNO",
            "HMR",
            "AL_DIA",
        ]
        buckets: dict[str, list[Cliente]] = {}
        for client_id in assigned_ids:
            client = clients_by_id.get(client_id)
            if not client:
                continue
            assignment_snapshot = current_by_client.get(client_id)
            if assignment_snapshot and assignment_snapshot.strategy_code == "VAGENCIASEXTERNASINTERNO":
                bucket_key = f"RECOVERY::{assignment_snapshot.placement_code or 'SIN_PLACEMENT'}::{assignment_snapshot.group_id or 'GENERAL'}"
            else:
                bucket_key = assignment_snapshot.strategy_code if assignment_snapshot and assignment_snapshot.strategy_code else "AL_DIA"
            buckets.setdefault(bucket_key, []).append(client)

        recovery_bucket_keys = sorted([key for key in buckets if key.startswith("RECOVERY::")])
        ordered_bucket_keys = [key for key in bucket_order if key in buckets] + recovery_bucket_keys + [
            key for key in buckets.keys() if key not in bucket_order and key not in recovery_bucket_keys
        ]

        balanced_clients: list[Cliente] = []
        active_bucket_keys = [key for key in ordered_bucket_keys if buckets.get(key)]
        while active_bucket_keys:
            next_active: list[str] = []
            for key in active_bucket_keys:
                bucket = buckets.get(key, [])
                if bucket:
                    balanced_clients.append(bucket.pop(0))
                if bucket:
                    next_active.append(key)
            active_bucket_keys = next_active
        return balanced_clients

    collectors = get_collectors(db)
    if not collectors:
        return []
    collector_ids = [item.id for item in collectors]
    collector_index = collector_ids.index(collector.id)
    clients = db.query(Cliente).order_by(Cliente.id).all()
    return [client for client in clients if (client.id - 1) % len(collectors) == collector_index]


def is_external_agency_collector(db: Session, user: Usuario) -> bool:
    if user.rol != "Collector":
        return False
    groups = get_worklist_groups_for_user(db, user.id)
    if not groups:
        return False
    scopes = {(item.channel_scope or "").upper() for item in groups if item.group_id}
    return bool(scopes) and scopes == {"EXTERNO"}


def get_visible_clients_for_user(db: Session, user: Usuario) -> list[Cliente]:
    if user.rol in {"Admin", "Supervisor", "Auditor", "GestorUsuarios"}:
        return db.query(Cliente).order_by(Cliente.id).all()
    if user.rol == "Collector":
        if is_external_agency_collector(db, user):
            return get_assigned_clients_for_collector(db, user)
        return db.query(Cliente).order_by(Cliente.id).all()
    return []


def client_matches_search(
    client: Cliente,
    search: str,
    mode: str,
    account_snapshots: list[dict[str, Any]],
) -> bool:
    normalized_query = re.sub(r"[^a-z0-9]", "", (search or "").lower())
    raw_query = (search or "").strip().lower()
    if not raw_query:
        return True

    def matches_value(value: Optional[str]) -> bool:
        raw_value = str(value or "").lower()
        normalized_value = re.sub(r"[^a-z0-9]", "", raw_value)
        return raw_query in raw_value or (normalized_query and normalized_query in normalized_value)

    account_values = []
    for item in account_snapshots:
        account_values.extend(
            [
                item.get("numero_cuenta"),
                item.get("numero_plastico"),
                str(item.get("numero_plastico") or "").replace("-", ""),
                item.get("producto_nombre"),
                item.get("codigo_ubicacion"),
            ]
        )

    lookup_values = {
        "all": [
            str(client.id),
            format_identity_code(client.identity_code, client.id),
            client.dui,
            client.nombres,
            client.apellidos,
            f"{client.nombres or ''} {client.apellidos or ''}".strip(),
            client.telefono,
            client.email,
            *account_values,
        ],
        "unico": [str(client.id), format_identity_code(client.identity_code, client.id)],
        "dui": [client.dui],
        "nombre": [client.nombres, client.apellidos, f"{client.nombres or ''} {client.apellidos or ''}".strip()],
        "cuenta": [item.get("numero_cuenta") for item in account_snapshots],
        "plastico": [value for value in account_values if value and ("-" in str(value) or str(value).isdigit())],
        "telefono": [client.telefono],
    }
    return any(matches_value(value) for value in lookup_values.get(mode, lookup_values["all"]) if value)


def get_client_lookup_score(client: Cliente, search: str, mode: str) -> int:
    normalized_query = re.sub(r"[^a-z0-9]", "", (search or "").lower())
    raw_query = (search or "").strip().lower()
    if not raw_query:
        return 0

    identity_code = format_identity_code(client.identity_code, client.id)
    client_id_text = str(client.id)
    code_digits = re.sub(r"\D", "", client.identity_code or "")
    full_name = f"{client.nombres or ''} {client.apellidos or ''}".strip()

    def normalized(value: Optional[str]) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

    def score_value(value: Optional[str], exact_score: int, prefix_score: int, contains_score: int) -> int:
        raw_value = str(value or "").lower()
        normalized_value = normalized(value)
        if raw_query == raw_value or normalized_query == normalized_value:
            return exact_score
        if raw_value.startswith(raw_query) or (normalized_query and normalized_value.startswith(normalized_query)):
            return prefix_score
        if raw_query in raw_value or (normalized_query and normalized_query in normalized_value):
            return contains_score
        return 0

    if mode in {"all", "unico"}:
        best = max(
            score_value(client_id_text, 1200, 1100, 1000),
            score_value(identity_code, 1150, 1050, 950),
            score_value(code_digits, 900, 850, 700),
        )
        if best:
            return best

    if mode in {"all", "dui"}:
        best = score_value(client.dui, 800, 700, 600)
        if best:
            return best

    if mode in {"all", "nombre"}:
        best = max(
            score_value(client.nombres, 500, 420, 320),
            score_value(client.apellidos, 500, 420, 320),
            score_value(full_name, 650, 560, 460),
        )
        if best:
            return best

    if mode in {"all", "telefono"}:
        best = score_value(client.telefono, 780, 680, 580)
        if best:
            return best

    return 0


def build_collector_client_snapshot(db: Session, current_user: Usuario, client: Cliente) -> CollectorClientRead:
    today = datetime.utcnow().date()
    start_of_day = get_start_of_day(today)
    accounts = db.query(Cuenta).filter(Cuenta.cliente_id == client.id).order_by(Cuenta.id).all()
    assignment_snapshot = (
        db.query(AssignmentHistory)
        .filter(AssignmentHistory.cliente_id == client.id, AssignmentHistory.is_current.is_(True))
        .order_by(AssignmentHistory.start_at.desc(), AssignmentHistory.id.desc())
        .first()
    )
    contextual_accounts = select_accounts_for_operational_context(accounts, assignment_snapshot, datetime.utcnow())
    account_ids = [item.id for item in accounts]
    predictions = (
        db.query(PrediccionIA)
        .filter(PrediccionIA.cuenta_id.in_(account_ids))
        .all()
        if account_ids
        else []
    )
    predictions_by_account = {prediction.cuenta_id: prediction for prediction in predictions}
    pending_promises = (
        db.query(Promesa)
        .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
        .filter(Cuenta.cliente_id == client.id, Promesa.estado.in_(["PENDIENTE", "REVISION_SUPERVISOR"]))
        .order_by(Promesa.fecha_promesa.asc())
        .all()
    )
    all_promises = (
        db.query(Promesa, Cuenta.numero_cuenta.label("numero_cuenta"))
        .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
        .filter(Cuenta.cliente_id == client.id)
        .order_by(Promesa.created_at.desc(), Promesa.fecha_promesa.desc())
        .all()
    )
    payments = (
        db.query(Pago, Cuenta.numero_cuenta.label("numero_cuenta"))
        .join(Cuenta, Cuenta.id == Pago.cuenta_id)
        .filter(Cuenta.cliente_id == client.id)
        .order_by(Pago.fecha_pago.desc(), Pago.created_at.desc())
        .all()
    )
    history_rows = (
        db.query(History)
        .filter(History.entidad == "clientes", History.entidad_id == client.id)
        .order_by(History.created_at.desc(), History.id.desc())
        .all()
    )
    actual_management_history = [
        ManagementHistoryRead(
            id=item.id,
            fecha=item.created_at.isoformat() if item.created_at else "",
            accion=item.accion,
            descripcion=item.descripcion,
            usuario_id=item.usuario_id,
        )
        for item in history_rows[:60]
    ]
    latest_history = next((item for item in history_rows if item.accion != "CALLBACK_PROGRAMADO"), None)
    callback_history = next((item for item in history_rows if item.accion == "CALLBACK_PROGRAMADO"), None)
    callback_at, _ = parse_callback_description(callback_history.descripcion if callback_history else None)
    worked_today = any(
        item.created_at and item.created_at >= start_of_day and item.accion in ["GESTION_REGISTRADA", "PROMESA_CREADA", "CLIENTE_ACTUALIZADO"]
        for item in history_rows
    )
    strategy_context = derive_client_strategy_context(contextual_accounts, datetime.utcnow())
    primary_strategy = (
        assignment_snapshot.strategy_code
        if assignment_snapshot and assignment_snapshot.strategy_code == "VAGENCIASEXTERNASINTERNO"
        else strategy_context["primary_strategy"]
    )
    account_rows: list[CollectorAccountRead] = []
    client_hmr = False
    client_total = 0.0
    account_snapshots: list[dict[str, Any]] = []

    for account in contextual_accounts:
        cycle_cut_day = get_cycle_cut_day(account)
        due_day = get_due_day(cycle_cut_day)
        strategy = resolve_strategy(account, datetime.utcnow())
        account_display = derive_account_display_metadata(account)
        hmr = is_hmr_candidate(account)
        prediction = predictions_by_account.get(account.id)
        if prediction:
            ai_probability = float(prediction.probabilidad_pago_30d)
            ai_score = float(prediction.score_modelo)
            ai_recommendation = prediction.recomendacion
        else:
            ai_probability, ai_score, ai_recommendation = build_ai_fallback(account)
        client_hmr = client_hmr or hmr
        client_total += float(account.saldo_total)
        account_snapshots.append(
            {
                "numero_cuenta": account.numero_cuenta,
                "numero_plastico": account_display["plastic_number"],
                "codigo_ubicacion": account_display["location_code"],
                "producto_nombre": account_display["product_name"],
            }
        )
        account_rows.append(
            CollectorAccountRead(
                id=account.id,
                numero_cuenta=account.numero_cuenta,
                numero_plastico=account_display["plastic_number"],
                codigo_ubicacion=account_display["location_code"],
                tipo_producto=account.tipo_producto,
                producto_nombre=account_display["product_name"],
                subtipo_producto=account.subtipo_producto,
                segmento_producto=account_display["product_segment"],
                estado=account.estado,
                saldo_total=float(account.saldo_total),
                saldo_mora=float(account.saldo_mora),
                dias_mora=account.dias_mora,
                bucket_actual=account.bucket_actual,
                es_estrafinanciamiento=account.es_estrafinanciamiento,
                ciclo_corte=cycle_cut_day,
                dia_vencimiento=due_day,
                estrategia=strategy,
                hmr_elegible=hmr,
                pago_minimo=calculate_minimum_payment(account),
                ai_probability=round(ai_probability, 4),
                ai_score=round(ai_score, 2),
                ai_recommendation=ai_recommendation,
            )
        )

    synthetic_history: list[ManagementHistoryRead] = []
    for promise, numero_cuenta in all_promises[:20]:
        synthetic_history.append(
            ManagementHistoryRead(
                id=-(200000000 + promise.id),
                fecha=(promise.created_at or datetime.combine(promise.fecha_promesa, datetime.min.time())).isoformat(),
                accion="PROMESA_CREADA",
                descripcion=(
                    f"Promesa {promise.estado.lower()} registrada para la cuenta {numero_cuenta} "
                    f"con fecha {promise.fecha_promesa.isoformat()} por {float(promise.monto_prometido):,.2f}."
                ),
                usuario_id=promise.usuario_id,
            )
        )
    for payment, numero_cuenta in payments[:20]:
        synthetic_history.append(
            ManagementHistoryRead(
                id=-(300000000 + payment.id),
                fecha=(payment.fecha_pago or payment.created_at or datetime.utcnow()).isoformat(),
                accion="PAGO_REGISTRADO",
                descripcion=(
                    f"Pago registrado en la cuenta {numero_cuenta} por {float(payment.monto):,.2f} "
                    f"via {payment.canal or 'canal no identificado'}."
                ),
                usuario_id=None,
            )
        )
    if not actual_management_history:
        synthetic_history.extend(
            [
                ManagementHistoryRead(
                    id=-(400000000 + account.id),
                    fecha=(account.created_at or datetime.utcnow()).isoformat(),
                    accion="CUENTA_EN_SEGUIMIENTO",
                    descripcion=(
                        f"Cuenta {account.numero_cuenta} en {resolve_strategy(account, datetime.utcnow())} "
                        f"con {account.dias_mora} dias de mora y saldo vencido de {float(account.saldo_mora):,.2f}."
                    ),
                    usuario_id=None,
                )
                for account in accounts[:3]
            ]
        )
    management_history = sorted([*actual_management_history, *synthetic_history], key=lambda item: item.fecha or "", reverse=True)[:60]
    last_management_text = latest_history.descripcion if latest_history else (management_history[0].descripcion if management_history else None)
    lead_account = next((item for item in account_rows if strategy_context["lead_account"] and item.id == strategy_context["lead_account"].id), account_rows[0] if account_rows else None)
    ai_probability = float(lead_account.ai_probability if lead_account and lead_account.ai_probability is not None else client.score_riesgo)
    promise_break_probability = (
        predict_promise_break_probability(strategy_context["lead_account"] or contextual_accounts[0], pending_promises, callback_at, float(client.score_riesgo))
        if contextual_accounts
        else float(np.clip(float(client.score_riesgo) * 0.65, 0.08, 0.9))
    )
    best_channel = suggest_best_channel(
        primary_strategy,
        promise_break_probability,
        ai_probability,
        bool(client.telefono),
        bool(client.email),
    )
    review_pending = any(item.estado == "REVISION_SUPERVISOR" for item in pending_promises)
    sublista_trabajo, sublista_descripcion = derive_worklist_sublist(client, accounts, pending_promises, callback_at, review_pending)
    if primary_strategy == "VAGENCIASEXTERNASINTERNO" and assignment_snapshot and assignment_snapshot.group_id:
        sublista_trabajo = assignment_snapshot.group_id
        sublista_descripcion = (
            f"{assignment_snapshot.channel_scope or 'MIXTO'} · "
            f"{assignment_snapshot.placement_code or 'SIN PLACEMENT'} · "
            f"Lista {assignment_snapshot.group_id}"
        )
    ai_next_action, ai_talk_track = build_copilot_guidance(
        client,
        primary_strategy,
        best_channel,
        promise_break_probability,
        ai_probability,
        pending_promises,
        round(client_total, 2),
    )

    return CollectorClientRead(
        id=client.id,
        identity_code=format_identity_code(client.identity_code, client.id),
        dui=client.dui,
        nombres=client.nombres,
        apellidos=client.apellidos,
        telefono=client.telefono,
        email=client.email,
        direccion=client.direccion,
        segmento=client.segmento,
        score_riesgo=float(client.score_riesgo),
        accounts=account_rows,
        pending_promises=[
            PromiseRead(
                id=item.id,
                cuenta_id=item.cuenta_id,
                fecha_promesa=item.fecha_promesa.isoformat(),
                monto_prometido=float(item.monto_prometido),
                estado=item.estado,
            )
            for item in pending_promises
        ],
        last_management=last_management_text,
        worked_today=worked_today,
        estrategia_principal=primary_strategy,
        estrategia_subgrupo=strategy_context["strategy_subgroup"],
        segmento_operativo=strategy_context["operational_segment"],
        producto_cabeza=strategy_context["head_product_name"],
        dias_mora_cabeza=strategy_context["head_days_past_due"],
        hmr_elegible=client_hmr,
        total_outstanding=round(client_total, 2),
        next_callback_at=callback_at.isoformat() if callback_at else None,
        requires_supervisor_review=review_pending,
        management_history=management_history,
        ai_best_channel=best_channel,
        ai_promise_break_probability=round(promise_break_probability, 4),
        ai_next_action=ai_next_action,
        ai_talk_track=ai_talk_track,
        placement_code=assignment_snapshot.placement_code if assignment_snapshot else None,
        group_id=assignment_snapshot.group_id if assignment_snapshot else None,
        sublista_trabajo=sublista_trabajo,
        sublista_descripcion=sublista_descripcion,
    )


def get_cycle_cut_day(account: Cuenta) -> int:
    return ((account.id - 1) % 30) + 1


def get_due_day(cut_day: int) -> int:
    return cut_day - 5 if cut_day > 5 else 1


STRATEGY_PRIORITY_ORDER = {
    "AL_DIA": 0,
    "PREVENTIVO": 1,
    "FMORA1": 2,
    "MMORA2": 3,
    "HMORA3": 4,
    "AMORA4": 5,
    "BMORA5": 6,
    "CMORA6": 7,
    "DMORA7": 8,
    "VAGENCIASEXTERNASINTERNO": 9,
}


def format_card_plastic_number(seed: int) -> str:
    suffix = str(261584513654 + int(seed)).zfill(12)[-12:]
    normalized = f"8706{suffix}"
    return "-".join(normalized[index:index + 4] for index in range(0, 16, 4))


def build_identity_code(seed: int) -> str:
    return str(int(seed)).zfill(11)


def format_identity_code(raw_value: Optional[str], fallback_seed: Optional[int] = None) -> str:
    digits = re.sub(r"\D", "", raw_value or "")
    if digits:
        return digits[-11:].zfill(11)
    if fallback_seed is not None:
        return build_identity_code(fallback_seed)
    return "00000000000"


def classify_product_family(account: Cuenta) -> str:
    raw_type = (account.tipo_producto or "").strip().lower()
    raw_subtype = (account.subtipo_producto or "").strip().lower()
    if "hipotec" in raw_subtype:
        return "HIPOTECAS"
    if raw_type == "prestamo" or raw_subtype in {"pil", "personal", "consumo", "vehiculo", "microcredito", "hipotecario"}:
        return "PIL"
    return "CARDS"


def derive_account_display_metadata(account: Cuenta) -> dict:
    raw_type = (account.tipo_producto or "").strip().lower()
    raw_subtype = (account.subtipo_producto or "").strip().lower()

    if raw_type == "tarjeta":
        if "plat" in raw_subtype:
            product_name = "Tarjeta Platino"
            location_code = "503109"
        elif "oro" in raw_subtype or "gold" in raw_subtype:
            product_name = "Tarjeta Gold"
            location_code = "503107"
        else:
            product_name = "Tarjeta Clasica"
            location_code = "503101"
        return {
            "product_name": product_name,
            "product_segment": "Tarjetas",
            "plastic_number": format_card_plastic_number(account.id or 0),
            "account_reference_last4": re.sub(r"\D", "", format_card_plastic_number(account.id or 0))[-4:],
            "location_code": location_code,
        }

    if "hipotec" in raw_subtype:
        product_name = "Prestamo Hipotecario"
        location_code = "101401"
    elif raw_subtype in {"pil", "personal", "consumo", ""}:
        product_name = "Prestamo PIL"
        location_code = "101201"
    else:
        product_name = f"Prestamo {account.subtipo_producto}".strip()
        location_code = "101000"

    return {
        "product_name": product_name,
        "product_segment": "Retail",
        "plastic_number": None,
        "account_reference_last4": (account.numero_cuenta or "")[-4:],
        "location_code": location_code,
    }


def derive_client_strategy_context(accounts: list[Cuenta], today: datetime) -> dict:
    if not accounts:
        return {
            "lead_account": None,
            "primary_strategy": "AL_DIA",
            "strategy_subgroup": "AL_DIACARDS",
            "operational_segment": "Cards",
            "head_product_name": None,
            "head_days_past_due": 0,
        }

    ranked_accounts = sorted(
        accounts,
        key=lambda account: (
            STRATEGY_PRIORITY_ORDER.get(resolve_strategy(account, today), 0),
            int(account.dias_mora or 0),
            float(account.saldo_mora or 0),
            float(account.saldo_total or 0),
            account.id or 0,
        ),
        reverse=True,
    )
    lead_account = ranked_accounts[0]
    primary_strategy = resolve_strategy(lead_account, today)
    considered_accounts = [account for account in ranked_accounts if int(account.dias_mora or 0) > 0] or ranked_accounts
    families = {classify_product_family(account) for account in considered_accounts}
    if "HIPOTECAS" in families:
        subgroup_suffix = "HIPOTECAS"
        operational_segment = "Hipotecas"
    elif "PIL" in families:
        subgroup_suffix = "PIL"
        operational_segment = "PIL"
    else:
        subgroup_suffix = "CARDS"
        operational_segment = "Cards"
    lead_account_display = derive_account_display_metadata(lead_account)
    return {
        "lead_account": lead_account,
        "primary_strategy": primary_strategy,
        "strategy_subgroup": f"{primary_strategy}{subgroup_suffix}",
        "operational_segment": operational_segment,
        "head_product_name": lead_account_display["product_name"],
        "head_days_past_due": int(lead_account.dias_mora or 0),
    }


def select_accounts_for_operational_context(
    accounts: list[Cuenta],
    assignment_snapshot: Optional[AssignmentHistory],
    today: datetime,
) -> list[Cuenta]:
    if not accounts:
        return accounts
    if not assignment_snapshot or assignment_snapshot.strategy_code != "VAGENCIASEXTERNASINTERNO":
        return accounts
    recovery_accounts = [
        account
        for account in accounts
        if account.fecha_separacion is not None
        or (account.estado or "").upper() in {"LIQUIDADO", "Z"}
        or resolve_strategy(account, today) == "VAGENCIASEXTERNASINTERNO"
    ]
    return recovery_accounts or accounts


def get_start_of_day(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time())


def next_cycle_cut_account_id(starting_from: int, target_cut_days: set[int]) -> int:
    candidate = starting_from
    while True:
        candidate += 1
        cut_day = ((candidate - 1) % 30) + 1
        if cut_day in target_cut_days:
            return candidate


def extract_pdf_like_text(payload: bytes) -> str:
    decoded = payload.decode("latin-1", errors="ignore")
    matches = re.findall(r"[A-Za-z0-9_/@\-\.\,\:\;\(\) ]{6,}", decoded)
    cleaned = [item.strip() for item in matches if len(item.strip()) >= 6]
    return " ".join(cleaned[:1200])


def build_document_proposal(file_name: str, extracted_text: str, admin_notes: str) -> dict:
    source = f"{file_name} {extracted_text} {admin_notes}".upper()
    strategy_catalog = [
        ("AL_DIA", "Seguimiento preventivo y recordatorio temprano."),
        ("PREVENTIVO", "Clientes posteriores al vencimiento pero antes del corte."),
        ("FMORA1", "Mora temprana de 1 a 30 dias."),
        ("MMORA2", "Mora media de 31 a 60 dias."),
        ("HMORA3", "Mora alta de 61 a 90 dias con contacto intensivo."),
        ("AMORA4", "Tramo avanzado con control supervisor."),
        ("BMORA5", "Cartera critica con escalamiento agresivo."),
        ("CMORA6", "Recuperacion severa con foco de mitigacion."),
        ("DMORA7", "Mayor a 190 dias aun vigente."),
        ("VAGENCIASEXTERNASINTERNO", "Canal interno o externo segun estatus."),
        ("HERRAMIENTAS", "Mitigacion HMR y soluciones.")
    ]
    detected_strategies = [
        {
            "codigo": code,
            "nombre": code.replace("_", " "),
            "descripcion": description,
            "action": "Crear o ajustar parametros"
        }
        for code, description in strategy_catalog
        if code in source
    ]
    if not detected_strategies:
        detected_strategies = [
            {
                "codigo": "ESTRATEGIA_PROPUESTA",
                "nombre": "Estrategia propuesta desde manual",
                "descripcion": "El documento no expone codigos claros. Requiere afinacion manual del administrador.",
                "action": "Revisar y ajustar"
            }
        ]

    sublists = []
    for code in ["F02SALDOSBAJOS", "NOCONTACTO", "PROMESAS", "CALLBACK", "REVSUP", "QALDIA", "ASISTELEFONICA"]:
        if code in source:
            sublists.append(
                {
                    "codigo": code,
                    "descripcion": f"Sublista detectada en documento para {code}.",
                    "strategy": "Asignar a estrategia relacionada"
                }
            )
    if not sublists:
        sublists = [
            {"codigo": "F02SALDOSBAJOS", "descripcion": "Clientes con saldo bajo para resolucion rapida.", "strategy": "FMORA1/MMORA2"},
            {"codigo": "NOCONTACTO", "descripcion": "Clientes sin contacto efectivo previo.", "strategy": "FMORA1/HMORA3"},
            {"codigo": "REVSUP", "descripcion": "Acuerdos fuera de politica pendientes de revision.", "strategy": "Todas"}
        ]

    if any(code in source for code in ["HMORA3", "AMORA4", "BMORA5", "CMORA6", "DMORA7"]):
        channel_rules = [
            {"segment": "HMORA3+", "channel": "Llamada telefonica + WhatsApp", "reason": "Documento sugiere gestion agresiva desde mora alta."},
            {"segment": "FMORA1/MMORA2", "channel": "Chatbot WhatsApp + SMS", "reason": "Mora temprana con contencion digital."},
        ]
    else:
        channel_rules = [
            {"segment": "AL_DIA/PREVENTIVO", "channel": "Correo + SMS", "reason": "Seguimiento preventivo de bajo roce."},
            {"segment": "FMORA1/MMORA2", "channel": "Chatbot WhatsApp + SMS", "reason": "Recuperacion temprana digital."},
        ]

    snippets = [part.strip() for part in re.split(r"[\.|;]", extracted_text) if part.strip()][:5]
    summary = (
        "Se detectaron lineamientos operativos y estrategias que pueden incorporarse al sistema. "
        "Revisa las propuestas antes de aplicarlas para evitar cambios no deseados."
    )
    notes = [
        "La propuesta no se aplica automaticamente. Debe ser aprobada o ajustada por un administrador.",
        "Las estrategias nuevas se agregan al catalogo y se deja trazabilidad en history.",
        "Las reglas de canal y sublistas quedan como propuesta operativa para afinacion funcional."
    ]
    return {
        "proposal_id": f"proposal-{int(datetime.now(timezone.utc).timestamp())}",
        "file_name": file_name,
        "generated_at": datetime.now(timezone.utc),
        "status": "PENDIENTE_APROBACION",
        "summary": summary,
        "extracted_context": snippets or ["No se pudo extraer texto claro del PDF. Usa notas del administrador para afinar la propuesta."],
        "suggested_strategies": detected_strategies,
        "suggested_channel_rules": channel_rules,
        "suggested_sublists": sublists,
        "implementation_notes": notes,
    }


def build_admin_template_docx_bytes() -> bytes:
    paragraphs = [
        "360CollectPlus - Plantilla de Estrategia, Manual Operativo y Ajustes del Sistema",
        "Objetivo del documento",
        "Describir una nueva estrategia, sublista, regla de canal, ajuste visual o cambio funcional para que el administrador pueda cargar el PDF, revisar la propuesta sugerida por el sistema y aprobar su implementación.",
        "1. Datos generales",
        "Nombre del documento:",
        "Organización o unidad solicitante:",
        "Fecha de emisión:",
        "Versión del documento:",
        "Responsable funcional:",
        "Responsable operativo:",
        "2. Tipo de solicitud",
        "Nueva estrategia / Ajuste de estrategia / Nuevo canal / Nueva sublista / Cambio de política / Cambio visual / Cambio de aprobaciones.",
        "3. Estrategia principal",
        "Código sugerido de estrategia:",
        "Nombre de estrategia:",
        "Descripción operativa:",
        "Tramo de mora aplicable:",
        "Segmento de clientes:",
        "Estados de cuenta aplicables:",
        "Roles involucrados:",
        "4. Reglas operativas",
        "Canal inicial sugerido:",
        "Canal secundario sugerido:",
        "Momento para escalar a llamada telefónica:",
        "Condiciones para revisión supervisor:",
        "Condiciones para HMR o mitigación:",
        "Condiciones para canal externo o interno:",
        "5. Sublistas de trabajo",
        "Usar formato: CÓDIGO | NOMBRE | DESCRIPCIÓN | ESTRATEGIA PADRE | PRIORIDAD.",
        "Ejemplo: F02SALDOSBAJOS | Saldos bajos | Clientes con saldo menor al umbral definido | FMORA1 | Alta.",
        "Ejemplo: NOCONTACTO | Sin contacto efectivo | Clientes sin contacto en intentos previos | FMORA1/HMORA3 | Media.",
        "Ejemplo: REVSUP | Revisión supervisor | Acuerdos fuera de política o plazo extendido | Todas | Alta.",
        "6. Datos que debe capturar el sistema",
        "Indicar si deben capturarse o volverse obligatorios campos como RDM, teléfono gestionado, promesa, callback, sublista, canal, motivo de rechazo, observaciones o aprobador.",
        "7. Ajustes visuales o de experiencia",
        "Describir cambios deseados en dashboards, botones, filtros, columnas, indicadores, formularios o alertas.",
        "8. Reglas de IA o analítica",
        "Indicar si se requiere predicción de pago, mejor canal sugerido, ruptura de promesa, copiloto de discurso, priorización especial o alertas nuevas.",
        "9. Criterios de aprobación",
        "Impacto esperado:",
        "Riesgos de implementación:",
        "Dependencias con otras áreas o sistemas:",
        "10. Aprobaciones",
        "Aprobado por negocio:",
        "Aprobado por operación:",
        "Aprobado por tecnología:",
        "Fecha de aprobación final:",
        "Instrucción simple para quien complete el documento",
        "Usar nombres de estrategia, sublistas y reglas de canal de forma explícita. Mientras más estructurado esté el contenido, más precisa será la propuesta que el sistema genere para revisión del administrador."
    ]

    def paragraph_xml(text: str, bold: bool = False) -> str:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if bold:
            return f'<w:p><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'
        return f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'

    body = [paragraph_xml(paragraphs[0], bold=True)] + [paragraph_xml(item) for item in paragraphs[1:]]
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body)}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Plantilla Estrategia y Ajustes 360CollectPlus</dc:title>
  <dc:creator>360CollectPlus</dc:creator>
  <cp:lastModifiedBy>360CollectPlus</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-03-26T20:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-03-26T20:00:00Z</dcterms:modified>
</cp:coreProperties>"""

    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("word/document.xml", document_xml)
    buffer.seek(0)
    return buffer.getvalue()


def build_admin_import_template_csv_bytes() -> bytes:
    sample_rows = [
        "identity_code,nombres,apellidos,dui,telefono,email,direccion,segmento,score_riesgo,numero_cuenta,tipo_producto,subtipo_producto,saldo_capital,saldo_mora,saldo_total,dias_mora,bucket_actual,estado,fecha_apertura,fecha_vencimiento,tasa_interes,es_estrafinanciamiento,estrategia_codigo,collector_username",
        "000090001,Ana Lucia,Martinez Cruz,01234567-8,7000-1001,ana.demo@empresa.com,San Salvador Centro,Preferente,0.35,PRE-90001,Prestamo,Consumo,2800,325,3125,25,FMORA1,ACTIVA,2024-01-15,2026-04-10,18.5,false,FMORA1,collector1",
        "000090001,Ana Lucia,Martinez Cruz,01234567-8,7000-1001,ana.demo@empresa.com,San Salvador Centro,Preferente,0.35,TAR-90001,Tarjeta,Clasica,1400,210,1610,25,FMORA1,ACTIVA,2024-06-01,2026-04-10,29.9,false,FMORA1,collector1",
    ]
    return "\n".join(sample_rows).encode("utf-8")


def parse_optional_float(value, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    return float(text)


def parse_optional_int(value, default: int = 0) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    return int(float(text))


def parse_optional_bool(value, default: bool = False) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip().lower() in {"1", "true", "si", "sí", "yes", "y", "x"}


def parse_optional_date(value) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def load_admin_import_rows(file_name: str, payload: bytes) -> pd.DataFrame:
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(payload), dtype=str).fillna("")
    if lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(payload), dtype=str).fillna("")
    raise HTTPException(status_code=400, detail="Formato no soportado. Usa CSV o XLSX.")


def normalize_import_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    return frame


def build_admin_import_proposal(file_name: str, payload: bytes, db: Session) -> dict:
    if "identity_code" not in frame.columns and "codigo_cliente" in frame.columns:
        frame = frame.rename(columns={"codigo_cliente": "identity_code"})
    required_columns = ["identity_code", "nombres", "apellidos", "dui", "numero_cuenta", "tipo_producto"]
    optional_columns = [
        "telefono",
        "email",
        "direccion",
        "segmento",
        "score_riesgo",
        "subtipo_producto",
        "saldo_capital",
        "saldo_mora",
        "saldo_total",
        "dias_mora",
        "bucket_actual",
        "estado",
        "fecha_apertura",
        "fecha_vencimiento",
        "tasa_interes",
        "es_estrafinanciamiento",
        "estrategia_codigo",
        "collector_username",
    ]
    frame = normalize_import_columns(load_admin_import_rows(file_name, payload))
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Faltan columnas obligatorias: {', '.join(missing)}.")

    users_by_username = {item.username: item for item in db.query(Usuario).filter(Usuario.rol == "Collector").all()}
    existing_clients_map = {item.identity_code: item for item in db.query(Cliente).all()}
    existing_accounts_map = {item.numero_cuenta: item for item in db.query(Cuenta).all()}

    clean_rows: list[dict] = []
    sample_errors: list[str] = []
    new_clients = 0
    existing_clients_count = 0
    new_accounts = 0
    existing_accounts_count = 0
    assignments_ready = 0

    for index, record in frame.iterrows():
        row_number = index + 2
        row = {
            column: (record.get(column, "") or "").strip() if hasattr(record.get(column, ""), "strip") else record.get(column, "")
            for column in frame.columns
        }
        row_errors = []
        for column in required_columns:
            if not str(row.get(column, "")).strip():
                row_errors.append(f"Fila {row_number}: falta {column}.")

        collector_username = str(row.get("collector_username", "")).strip()
        collector_user = None
        if collector_username:
            collector_user = users_by_username.get(collector_username)
            if not collector_user:
                row_errors.append(f"Fila {row_number}: collector_username '{collector_username}' no existe.")

        strategy_code = str(row.get("estrategia_codigo", "")).strip().upper()
        if not strategy_code:
            temp_account = Cuenta(
                numero_cuenta=str(row.get("numero_cuenta", "")).strip() or f"TEMP-{row_number}",
                cliente_id=0,
                tipo_producto=str(row.get("tipo_producto", "Prestamo")).strip() or "Prestamo",
                subtipo_producto=str(row.get("subtipo_producto", "")).strip() or None,
                saldo_capital=parse_optional_float(row.get("saldo_capital"), 0),
                saldo_mora=parse_optional_float(row.get("saldo_mora"), 0),
                saldo_total=parse_optional_float(row.get("saldo_total"), 0),
                dias_mora=parse_optional_int(row.get("dias_mora"), 0),
                bucket_actual=str(row.get("bucket_actual", "")).strip() or "0-30",
                estado=str(row.get("estado", "")).strip().upper() or "ACTIVA",
                fecha_apertura=parse_optional_date(row.get("fecha_apertura")),
                fecha_vencimiento=parse_optional_date(row.get("fecha_vencimiento")),
                tasa_interes=parse_optional_float(row.get("tasa_interes"), 0),
                es_estrafinanciamiento=parse_optional_bool(row.get("es_estrafinanciamiento"), False),
            )
            strategy_code = derive_strategy_code(temp_account)

        if row_errors:
            sample_errors.extend(row_errors[:3])
            continue

        client_exists = existing_clients_map.get(str(row["identity_code"]).strip())
        account_exists = existing_accounts_map.get(str(row["numero_cuenta"]).strip())
        new_clients += 0 if client_exists else 1
        existing_clients_count += 1 if client_exists else 0
        new_accounts += 0 if account_exists else 1
        existing_accounts_count += 1 if account_exists else 0
        assignments_ready += 1 if collector_user else 0

        clean_rows.append(
            {
                "identity_code": str(row["identity_code"]).strip(),
                "nombres": str(row["nombres"]).strip(),
                "apellidos": str(row["apellidos"]).strip(),
                "dui": str(row["dui"]).strip(),
                "telefono": str(row.get("telefono", "")).strip() or None,
                "email": str(row.get("email", "")).strip() or None,
                "direccion": str(row.get("direccion", "")).strip() or None,
                "segmento": str(row.get("segmento", "")).strip() or "Masivo",
                "score_riesgo": parse_optional_float(row.get("score_riesgo"), 0.5),
                "numero_cuenta": str(row["numero_cuenta"]).strip(),
                "tipo_producto": str(row["tipo_producto"]).strip() or "Prestamo",
                "subtipo_producto": str(row.get("subtipo_producto", "")).strip() or None,
                "saldo_capital": parse_optional_float(row.get("saldo_capital"), 0),
                "saldo_mora": parse_optional_float(row.get("saldo_mora"), 0),
                "saldo_total": parse_optional_float(row.get("saldo_total"), 0),
                "dias_mora": parse_optional_int(row.get("dias_mora"), 0),
                "bucket_actual": str(row.get("bucket_actual", "")).strip() or "0-30",
                "estado": str(row.get("estado", "")).strip().upper() or "ACTIVA",
                "fecha_apertura": parse_optional_date(row.get("fecha_apertura")),
                "fecha_vencimiento": parse_optional_date(row.get("fecha_vencimiento")),
                "tasa_interes": parse_optional_float(row.get("tasa_interes"), 0),
                "es_estrafinanciamiento": parse_optional_bool(row.get("es_estrafinanciamiento"), False),
                "estrategia_codigo": strategy_code,
                "collector_username": collector_username or None,
                "collector_user_id": collector_user.id if collector_user else None,
            }
        )

    preview_rows = [
        {
            "identity_code": item["identity_code"],
            "cliente": f"{item['nombres']} {item['apellidos']}",
            "numero_cuenta": item["numero_cuenta"],
            "tipo_producto": item["tipo_producto"],
            "dias_mora": item["dias_mora"],
            "estrategia_codigo": item["estrategia_codigo"],
            "collector_username": item["collector_username"] or "Sin asignar",
        }
        for item in clean_rows[:12]
    ]

    return {
        "proposal_id": f"import-{uuid4().hex[:12]}",
        "file_name": file_name,
        "generated_at": datetime.now(timezone.utc),
        "status": "PENDIENTE_APLICACION",
        "summary": "La carga fue validada y quedó lista para revisión administrativa antes de aplicarla al sistema.",
        "total_rows": int(len(frame)),
        "valid_rows": int(len(clean_rows)),
        "error_rows": int(max(len(frame) - len(clean_rows), 0)),
        "new_clients": int(new_clients),
        "existing_clients": int(existing_clients_count),
        "new_accounts": int(new_accounts),
        "existing_accounts": int(existing_accounts_count),
        "assignments_ready": int(assignments_ready),
        "preview_rows": preview_rows,
        "sample_errors": sample_errors[:20],
        "expected_columns": required_columns + optional_columns,
        "clean_rows": clean_rows,
    }


def build_admin_user_import_template_csv_bytes() -> bytes:
    sample_rows = [
        "nombre,email,username,rol,password,activo",
        "Collector Demo,collector.demo@empresa.com,collector_demo,Collector,Password123!,true",
        "Supervisor Demo,supervisor.demo@empresa.com,supervisor_demo,Supervisor,Password123!,true",
    ]
    return "\n".join(sample_rows).encode("utf-8")


def build_admin_user_import_proposal(file_name: str, payload: bytes, db: Session) -> dict:
    required_columns = ["nombre", "email", "username", "rol", "password"]
    frame = normalize_import_columns(load_admin_import_rows(file_name, payload))
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Faltan columnas obligatorias: {', '.join(missing)}.")

    existing_users = {item.username: item for item in db.query(Usuario).all()}
    clean_rows: list[dict] = []
    sample_errors: list[str] = []
    new_users = 0
    existing_users_count = 0

    for index, record in frame.iterrows():
        row_number = index + 2
        row = {column: (record.get(column, "") or "").strip() if hasattr(record.get(column, ""), "strip") else record.get(column, "") for column in frame.columns}
        row_errors = []
        for column in required_columns:
            if not str(row.get(column, "")).strip():
                row_errors.append(f"Fila {row_number}: falta {column}.")
        role = str(row.get("rol", "")).strip()
        if role not in {"Admin", "Collector", "Supervisor", "Auditor", "GestorUsuarios"}:
            row_errors.append(f"Fila {row_number}: rol '{role}' no es válido.")
        if row_errors:
            sample_errors.extend(row_errors[:3])
            continue
        exists = existing_users.get(str(row["username"]).strip())
        new_users += 0 if exists else 1
        existing_users_count += 1 if exists else 0
        clean_rows.append(
            {
                "nombre": str(row["nombre"]).strip(),
                "email": str(row["email"]).strip(),
                "username": str(row["username"]).strip(),
                "rol": role,
                "password": str(row["password"]).strip(),
                "activo": parse_optional_bool(row.get("activo"), True),
            }
        )

    preview_rows = clean_rows[:12]
    return {
        "proposal_id": f"user-import-{uuid4().hex[:12]}",
        "file_name": file_name,
        "generated_at": datetime.now(timezone.utc),
        "status": "PENDIENTE_APLICACION",
        "summary": "La carga de usuarios fue validada y quedó lista para revisión antes de aplicarse.",
        "total_rows": int(len(frame)),
        "valid_rows": int(len(clean_rows)),
        "error_rows": int(max(len(frame) - len(clean_rows), 0)),
        "new_clients": int(new_users),
        "existing_clients": int(existing_users_count),
        "new_accounts": 0,
        "existing_accounts": 0,
        "assignments_ready": 0,
        "preview_rows": preview_rows,
        "sample_errors": sample_errors[:20],
        "expected_columns": required_columns + ["activo"],
        "clean_rows": clean_rows,
    }


def parse_report_description_filters(description: str) -> dict:
    source = (description or "").upper()
    strategy_aliases = {
        "ALDIA": "AL_DIA",
        "AL_DIA": "AL_DIA",
        "PREVENT": "PREVENTIVO",
        "PREVENTIVO": "PREVENTIVO",
        "FMORA1": "FMORA1",
        "MMORA2": "MMORA2",
        "MMORA3": "MMORA2",
        "HMORA3": "HMORA3",
        "AMORA4": "AMORA4",
        "BMORA5": "BMORA5",
        "CMORA6": "CMORA6",
        "DMORA7": "DMORA7",
        "VAGENCIAEXTERNASINTERNO": "VAGENCIASEXTERNASINTERNO",
        "VAGENCIASEXTERNASINTERNO": "VAGENCIASEXTERNASINTERNO",
        "HMR": "HMR",
    }
    transition_match = re.search(
        r"(?:PASARON|CAMBIARON|MIGRARON|TRANSITARON)\s+DE\s+([A-Z0-9_]+)\s+A\s+([A-Z0-9_]+)",
        source,
    )
    from_strategy = strategy_aliases.get(transition_match.group(1)) if transition_match else None
    to_strategy = strategy_aliases.get(transition_match.group(2)) if transition_match else None
    strategy = next(
        (
            code
            for token, code in strategy_aliases.items()
            if token in source and code in ["AL_DIA", "PREVENTIVO", "FMORA1", "MMORA2", "HMORA3", "AMORA4", "BMORA5", "CMORA6", "DMORA7", "VAGENCIASEXTERNASINTERNO", "HMR"]
        ),
        None,
    )
    amount_match = re.search(r"(?:ARRIBA DE|MAYOR A|MAYOR DE|SUPERIOR A)\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", source)
    min_balance = float(amount_match.group(1)) if amount_match else None
    probability_band = None
    if "BAJAS PROBABILIDADES" in source or "BAJA PROBABILIDAD" in source:
        probability_band = "LOW"
    elif "ALTAS PROBABILIDADES" in source or "ALTA PROBABILIDAD" in source:
        probability_band = "HIGH"
    elif "PROBABILIDADES MEDIAS" in source or "PROBABILIDAD MEDIA" in source:
        probability_band = "MEDIUM"
    wants_strategy = "ESTRATEGIA" in source or "ESTRATEGIAS" in source
    count_by_strategy = any(
        token in source
        for token in [
            "CANTIDAD DE CUENTAS EN CADA ESTRATEGIA",
            "CANTIDAD DE CLIENTES EN CADA ESTRATEGIA",
            "CUANTOS CLIENTES TENGO EN CADA ESTRATEGIA",
            "CUANTAS CUENTAS TENGO EN CADA ESTRATEGIA",
            "CANTIDAD POR ESTRATEGIA",
            "DISTRIBUCION POR ESTRATEGIA",
            "REPORTE POR ESTRATEGIA",
            "EN CADA ESTRATEGIA",
        ]
    ) or wants_strategy
    strategy_metric = "CLIENTES" if any(
        token in source
        for token in [
            "CLIENTES EN CADA ESTRATEGIA",
            "CUANTOS CLIENTES TENGO EN CADA ESTRATEGIA",
            "CUENTOS CLIENTES TENGO EN CADA ESTRATEGIA",
            "MUESTREME LOS CLIENTES POR ESTRATEGIA",
            "MUESTRE CUANTOS CLIENTES",
            "CUANTIDAD DE CLIENTES",
        ]
    ) else "CUENTAS"
    include_balance_by_strategy = any(
        token in source
        for token in [
            "BALANCE",
            "BALANCES",
            "SALDO",
            "SALDOS",
            "MONTO",
            "MONTOS",
        ]
    )
    ordered_by_mora = any(
        token in source
        for token in [
            "DIAS MORA DE MENOR A MAYOR",
            "MORA DE MENOR A MAYOR",
            "ORDENA LAS ESTRATEGIAS POR DIAS MORA",
            "ORDENADO POR MORA",
            "DE MENOR A MAYOR",
        ]
    )
    unsupported_keywords = [
        "PREDICCION MENSUAL",
        "PROYECCION ANUAL",
        "MAPA GEOGRAFICO",
        "CALOR POR MUNICIPIO",
        "SENTIMIENTO DE LLAMADAS",
        "TRANSCRIPCION DE AUDIO",
    ]
    unsupported_reason = None
    if any(token in source for token in unsupported_keywords):
        unsupported_reason = "La solicitud requiere una capacidad analítica o fuente de datos que no está disponible todavía en el sistema actual."
    recognized_request = any(
        [
            strategy is not None,
            min_balance is not None,
            probability_band is not None,
            from_strategy is not None,
            to_strategy is not None,
            count_by_strategy,
            "SEGMENTO" in source,
            "PROMESA" in source,
            "REVISION SUPERVISOR" in source,
            "COLLECTOR" in source,
            "GESTOR" in source,
        ]
    )
    return {
        "strategy_code": strategy,
        "min_balance": min_balance,
        "probability_band": probability_band,
        "transition_from": from_strategy,
        "transition_to": to_strategy,
        "day_transition": any(token in source for token in ["DE AYER PARA HOY", "DE AYER A HOY", "AYER PARA HOY", "AYER A HOY", "HOY PASARON"]),
        "count_by_strategy": count_by_strategy,
        "strategy_metric": strategy_metric,
        "include_balance_by_strategy": include_balance_by_strategy,
        "ordered_by_mora": ordered_by_mora,
        "unsupported_reason": unsupported_reason,
        "recognized_request": recognized_request,
    }


def derive_strategy_code(account: "Cuenta") -> str:
    days_past_due = int(account.dias_mora or 0)
    status = (account.estado or "").upper()

    if days_past_due <= 0:
        return "AL_DIA"
    if 1 <= days_past_due <= 30:
        return "FMORA1"
    if 31 <= days_past_due <= 60:
        return "MMORA2"
    if 61 <= days_past_due <= 90:
        return "HMORA3"
    if 91 <= days_past_due <= 120:
        return "AMORA4"
    if 121 <= days_past_due <= 150:
        return "BMORA5"
    if 151 <= days_past_due <= 180:
        return "CMORA6"
    if days_past_due > 180 and status in {"LIQUIDADO", "Z"}:
        return "VAGENCIASEXTERNASINTERNO"
    if days_past_due > 190 and status in {"VIGENTE", "ACTIVA"}:
        return "DMORA7"
    return "DMORA7" if days_past_due > 180 else "PREVENTIVO"


def build_admin_report_rows(description: str, db: Session) -> tuple[dict, list[dict]]:
    filters = parse_report_description_filters(description)
    rows = (
        db.query(
            Cuenta.id.label("cuenta_id"),
            Cuenta.numero_cuenta,
            Cuenta.tipo_producto,
            Cuenta.subtipo_producto,
            Cuenta.saldo_mora,
            Cuenta.saldo_capital,
            Cuenta.saldo_total,
            Cuenta.dias_mora,
            Cuenta.estado,
            Cliente.identity_code,
            Cliente.nombres,
            Cliente.apellidos,
            Cliente.telefono,
            Cliente.email,
            Cliente.direccion,
            Cliente.segmento,
            Cliente.score_riesgo,
            PrediccionIA.probabilidad_pago_30d,
            PrediccionIA.recomendacion,
        )
        .join(Cliente, Cliente.id == Cuenta.cliente_id)
        .outerjoin(PrediccionIA, PrediccionIA.cuenta_id == Cuenta.id)
        .all()
    )

    prepared_rows = []
    for row in rows:
        strategy_code = derive_strategy_code(
            Cuenta(
                cliente_id=0,
                numero_cuenta=row.numero_cuenta,
                tipo_producto=row.tipo_producto,
                subtipo_producto=None,
                saldo_capital=0,
                saldo_mora=row.saldo_mora,
                saldo_total=row.saldo_total,
                dias_mora=row.dias_mora,
                bucket_actual="",
                estado=row.estado,
                fecha_apertura=None,
                fecha_vencimiento=None,
                tasa_interes=0,
                es_estrafinanciamiento=False,
            )
        )
        previous_strategy_code = derive_strategy_code(
            Cuenta(
                cliente_id=0,
                numero_cuenta=row.numero_cuenta,
                tipo_producto=row.tipo_producto,
                subtipo_producto=None,
                saldo_capital=0,
                saldo_mora=row.saldo_mora,
                saldo_total=row.saldo_total,
                dias_mora=max(int(row.dias_mora or 0) - 1, 0),
                bucket_actual="",
                estado=row.estado,
                fecha_apertura=None,
                fecha_vencimiento=None,
                tasa_interes=0,
                es_estrafinanciamiento=False,
            )
        )
        probability = float(row.probabilidad_pago_30d if row.probabilidad_pago_30d is not None else row.score_riesgo or 0)
        prepared_rows.append(
            {
                "cuenta_id": row.cuenta_id,
                "numero_cuenta": row.numero_cuenta,
                "tipo_producto": row.tipo_producto,
                "subtipo_producto": row.subtipo_producto or "",
                "identity_code": row.identity_code,
                "cliente_nombre": f"{row.nombres} {row.apellidos}",
                "telefono": row.telefono or "",
                "email": row.email or "",
                "direccion": row.direccion or "",
                "segmento": row.segmento or "Sin segmento",
                "score_riesgo": float(row.score_riesgo or 0),
                "saldo_capital": float(row.saldo_capital or 0),
                "saldo_mora": float(row.saldo_mora or 0),
                "saldo_total": float(row.saldo_total or 0),
                "dias_mora": int(row.dias_mora or 0),
                "estado": row.estado,
                "strategy_code": strategy_code,
                "previous_strategy_code": previous_strategy_code,
                "probability": probability,
                "ai_recommendation": row.recomendacion or "",
                "channel": (
                    "Monitoreo sin contacto"
                    if strategy_code == "AL_DIA"
                    else "Chatbot WhatsApp + SMS"
                    if strategy_code in {"PREVENTIVO", "FMORA1", "MMORA2"}
                    else "Callbot + llamada humana + WhatsApp"
                    if strategy_code == "VAGENCIASEXTERNASINTERNO"
                    else "Llamada telefónica + WhatsApp"
                ),
            }
        )

    filtered_rows = prepared_rows
    if filters["transition_from"] and filters["transition_to"]:
        filtered_rows = [
            row
            for row in filtered_rows
            if row["previous_strategy_code"] == filters["transition_from"] and row["strategy_code"] == filters["transition_to"]
        ]
    if filters["strategy_code"] and not (filters["transition_from"] and filters["transition_to"]):
        filtered_rows = [row for row in filtered_rows if row["strategy_code"] == filters["strategy_code"]]
    if filters["min_balance"] is not None:
        filtered_rows = [row for row in filtered_rows if row["saldo_mora"] >= filters["min_balance"]]
    if filters["probability_band"] == "LOW":
        filtered_rows = [row for row in filtered_rows if row["probability"] <= 0.45]
    elif filters["probability_band"] == "MEDIUM":
        filtered_rows = [row for row in filtered_rows if 0.46 <= row["probability"] <= 0.70]
    elif filters["probability_band"] == "HIGH":
        filtered_rows = [row for row in filtered_rows if row["probability"] >= 0.71]
    return filters, filtered_rows


def build_admin_generated_report(description: str, db: Session) -> dict:
    filters, filtered_rows = build_admin_report_rows(description, db)

    if filters.get("unsupported_reason"):
        return {
            "title": "Solicitud no disponible con precisión automática",
            "summary": filters["unsupported_reason"],
            "cards": [
                {"title": "Estado", "value": "No generado", "detail": "El sistema identificó una solicitud fuera del alcance actual del generador."},
                {"title": "Sugerencia 1", "value": "Clientes por estrategia", "detail": "Puedes pedir clientes, cuentas o saldos por estrategia."},
                {"title": "Sugerencia 2", "value": "Transiciones diarias", "detail": "Puedes pedir cambios de ayer a hoy entre tramos de mora."},
                {"title": "Sugerencia 3", "value": "Promesas y riesgo", "detail": "Puedes pedir promesas en riesgo, revisión supervisor o bajas probabilidades de pago."},
            ],
            "charts": [
                {
                    "title": "Solicitudes sugeridas",
                    "type": "table",
                    "items": [
                        {"label": "Ejemplo 1", "value": "Clientes por estrategia con balance vencido"},
                        {"label": "Ejemplo 2", "value": "Casos que pasaron de FMORA1 a MMORA2 de ayer para hoy"},
                        {"label": "Ejemplo 3", "value": "Clientes HMORA3+ con bajas probabilidades y saldo mayor a $300"},
                    ],
                }
            ],
            "insights": [
                "No fue posible interpretar la solicitud con precisión suficiente para construir un reporte confiable.",
                "Intenta pedir el reporte indicando universo, filtro y métrica principal.",
                f"Solicitud recibida: {description}",
            ],
        }

    if not filters.get("recognized_request") and not description.strip():
        return {
            "title": "Describe el reporte que necesitas",
            "summary": "El generador necesita una solicitud con más contexto para construir un reporte exacto.",
            "cards": [],
            "charts": [],
            "insights": [
                "Ejemplo: clientes por estrategia con balances vencidos.",
                "Ejemplo: casos que pasaron de FMORA1 a MMORA2 de ayer para hoy.",
                "Ejemplo: cartera HMORA3 con bajas probabilidades de pago y saldo mayor a $300.",
            ],
        }

    if filters.get("count_by_strategy"):
        strategy_order = {
            "AL_DIA": 0,
            "PREVENTIVO": 1,
            "FMORA1": 2,
            "MMORA2": 3,
            "HMORA3": 4,
            "AMORA4": 5,
            "BMORA5": 6,
            "CMORA6": 7,
            "DMORA7": 8,
            "VAGENCIASEXTERNASINTERNO": 9,
            "HMR": 10,
        }
        account_counts: dict[str, int] = {}
        client_counts: dict[str, set[str]] = {}
        balance_counts: dict[str, float] = {}
        for row in filtered_rows:
            strategy_code = row["strategy_code"]
            account_counts[strategy_code] = account_counts.get(strategy_code, 0) + 1
            client_counts.setdefault(strategy_code, set()).add(row["identity_code"])
            balance_counts[strategy_code] = balance_counts.get(strategy_code, 0.0) + float(row["saldo_mora"] or 0)

        ordered_items = [
            {
                "label": strategy,
                "clients": len(client_counts.get(strategy, set())),
                "accounts": account_counts.get(strategy, 0),
                "balance": round(balance_counts.get(strategy, 0.0), 2),
            }
            for strategy in sorted(account_counts.keys(), key=lambda key: strategy_order.get(key, 99))
        ]
        total_accounts = sum(account_counts.values())
        total_clients = len({row["identity_code"] for row in filtered_rows})
        metric_key = "clients" if filters.get("strategy_metric") == "CLIENTES" else "accounts"
        top_strategy = max(ordered_items, key=lambda item: item[metric_key])["label"] if ordered_items else "Sin datos"
        top_strategy_value = max(ordered_items, key=lambda item: item[metric_key])[metric_key] if ordered_items else 0
        main_chart_title = "Clientes por estrategia" if filters.get("strategy_metric") == "CLIENTES" else "Cuentas por estrategia"
        report_title = "Distribución de clientes por estrategia" if filters.get("strategy_metric") == "CLIENTES" else "Distribución de cuentas por estrategia"
        report_summary = (
            "Vista consolidada ordenada por mora de menor a mayor, mostrando clientes únicos y balance vencido por estrategia."
            if filters.get("strategy_metric") == "CLIENTES"
            else "Vista consolidada ordenada por mora de menor a mayor, mostrando cuentas, clientes únicos y balance vencido por estrategia."
        )
        return {
            "title": report_title,
            "summary": report_summary,
            "cards": [
                {"title": "Clientes únicos", "value": total_clients, "detail": "Clientes con al menos una cuenta en la cartera analizada"},
                {"title": "Cuentas operativas", "value": total_accounts, "detail": "Total de cuentas consideradas en el reporte"},
                {"title": "Saldo vencido total", "value": f"${sum(item['balance'] for item in ordered_items):,.2f}", "detail": "Balance agregado de las estrategias visibles"},
                {"title": "Estrategias con casos", "value": len(account_counts), "detail": "Frentes de cobranza actualmente poblados"},
                {"title": "Estrategia más cargada", "value": top_strategy, "detail": f"{top_strategy_value} {'clientes' if filters.get('strategy_metric') == 'CLIENTES' else 'cuentas'}"},
            ],
            "charts": [
                {
                    "title": main_chart_title,
                    "type": "bar",
                    "items": [{"label": item["label"], "value": item[metric_key]} for item in ordered_items],
                },
                {
                    "title": "Balances por estrategia",
                    "type": "table",
                    "items": [{"label": item["label"], "value": f"${item['balance']:,.2f}"} for item in ordered_items],
                },
            ],
            "insights": [
                f"La cartera actual suma {total_clients} clientes únicos distribuidos en {len(account_counts)} estrategias.",
                f"La estrategia con mayor volumen es {top_strategy} con {top_strategy_value} {'clientes' if filters.get('strategy_metric') == 'CLIENTES' else 'cuentas'}.",
                "El reporte está ordenado por severidad de mora, de menor a mayor.",
                "El balance se presenta segmentado por estrategia para facilitar lectura gerencial.",
                f"Reporte generado a partir de la solicitud: {description}",
            ],
        }

    total_cases = len(filtered_rows)
    avg_probability = round((sum(row["probability"] for row in filtered_rows) / total_cases) * 100, 2) if total_cases else 0
    total_balance = sum(row["saldo_mora"] for row in filtered_rows)
    severe_cases = sum(1 for row in filtered_rows if row["dias_mora"] >= 61)
    dominant_channel = "Sin recomendación"
    if filtered_rows:
        channel_counts: dict[str, int] = {}
        for row in filtered_rows:
            channel_counts[row["channel"]] = channel_counts.get(row["channel"], 0) + 1
        dominant_channel = max(channel_counts.items(), key=lambda item: item[1])[0]

    segment_counts: dict[str, int] = {}
    for row in filtered_rows:
        segment_counts[row["segmento"]] = segment_counts.get(row["segmento"], 0) + 1

    top_accounts = sorted(filtered_rows, key=lambda row: (row["saldo_mora"], -row["probability"]), reverse=True)[:10]

    report_title = "Reporte ejecutivo generado"
    report_summary = "Reporte construido desde la solicitud del usuario con filtros por estrategia, saldo y probabilidad cuando fueron identificados en la descripción."
    if filters["transition_from"] and filters["transition_to"]:
        report_title = f"Transición {filters['transition_from']} a {filters['transition_to']}"
        report_summary = "Reporte de transición entre tramos usando la estrategia actual contra la del día anterior para identificar cambios entre ayer y hoy."

    cards = [
        {"title": "Casos filtrados", "value": total_cases, "detail": "Clientes/cuentas que cumplen la solicitud"},
        {"title": "Saldo vencido objetivo", "value": f"${float(total_balance):,.2f}", "detail": "Monto agregado del universo filtrado"},
        {"title": "Prob. promedio de pago", "value": f"{avg_probability}%", "detail": "Recuperabilidad estimada del grupo"},
        {"title": "Canal recomendado", "value": dominant_channel, "detail": "Canal predominante sugerido para la gestión"},
    ]
    charts = [
        {
            "title": "Top cuentas del reporte",
            "type": "table",
            "items": [
                {
                    "label": f"{row['identity_code']} · {row['numero_cuenta']}",
                    "value": f"${row['saldo_mora']:,.2f} · {round(row['probability'] * 100, 2)}%",
                }
                for row in top_accounts
            ],
        },
        {
            "title": "Distribución por segmento del filtro",
            "type": "donut",
            "items": [{"label": label, "value": value} for label, value in sorted(segment_counts.items(), key=lambda item: item[1], reverse=True)[:6]],
        },
    ]
    insights = [
        (
            f"Se identificaron {total_cases} casos que pasaron de {filters['transition_from']} a {filters['transition_to']} entre ayer y hoy."
            if filters["transition_from"] and filters["transition_to"]
            else f"Se filtraron {total_cases} casos para la estrategia {filters['strategy_code'] or 'solicitada por texto libre'}."
        ),
        f"El saldo vencido agregado del reporte asciende a ${float(total_balance):,.2f}.",
        f"{severe_cases} casos del grupo filtrado tienen mora severa (61+ días).",
        f"La recomendación operativa dominante para este grupo es: {dominant_channel}.",
    ]
    return {
        "title": report_title,
        "summary": report_summary,
        "cards": cards,
        "charts": charts,
        "insights": insights,
    }


def build_admin_report_csv(description: str, db: Session) -> bytes:
    filters, filtered_rows = build_admin_report_rows(description, db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "descripcion_solicitud",
            "estrategia_filtrada",
            "filtro_saldo_minimo",
            "filtro_probabilidad",
            "identity_code",
            "cliente_nombre",
            "telefono",
            "email",
            "direccion",
            "segmento",
            "score_riesgo",
            "numero_cuenta",
            "tipo_producto",
            "subtipo_producto",
            "estado_cuenta",
            "estrategia_actual",
            "dias_mora",
            "saldo_capital",
            "saldo_mora",
            "saldo_total",
            "probabilidad_pago",
            "canal_sugerido",
            "recomendacion_ia",
        ]
    )
    for row in filtered_rows:
        writer.writerow(
            [
                description,
                filters["strategy_code"] or "",
                filters["min_balance"] if filters["min_balance"] is not None else "",
                filters["probability_band"] or "",
                row["identity_code"],
                row["cliente_nombre"],
                row["telefono"],
                row["email"],
                row["direccion"],
                row["segmento"],
                row["score_riesgo"],
                row["numero_cuenta"],
                row["tipo_producto"],
                row["subtipo_producto"],
                row["estado"],
                row["strategy_code"],
                row["dias_mora"],
                row["saldo_capital"],
                row["saldo_mora"],
                row["saldo_total"],
                round(row["probability"] * 100, 2),
                row["channel"],
                row["ai_recommendation"],
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def run_daily_operational_simulation(
    db: Session,
    current_user: Usuario,
    fmora1_clients: int = 250,
    preventivo_clients: int = 120,
    recovery_clients: int = 1000,
) -> dict:
    today = date.today()
    simulation_key = f"SIM-DAY-{today.isoformat()}"
    existing = (
        db.query(History)
        .filter(
            History.entidad == "system",
            History.accion == "SIMULACION_DIA_OPERATIVO",
            History.descripcion.ilike(f"%{simulation_key}%"),
        )
        .first()
    )
    if existing:
        return {
            "simulation_key": simulation_key,
            "aged_accounts": 0,
            "inserted_fmora1_clients": 0,
            "inserted_preventivo_clients": 0,
            "inserted_recovery_clients": 0,
            "simulated_payments": 0,
            "fully_cured_accounts": 0,
            "recovery_rotations": 0,
            "total_clients": db.query(Cliente).count(),
            "total_accounts": db.query(Cuenta).count(),
            "message": "La simulacion del dia ya habia sido aplicada previamente.",
        }

    current_timestamp = datetime.now(timezone.utc)
    active_collectors = db.query(Usuario).filter(Usuario.rol == "Collector", Usuario.activo.is_(True)).order_by(Usuario.id).all()
    if not active_collectors:
        raise HTTPException(status_code=400, detail="No hay collectors activos para asignar la nueva cartera.")

    def bucket_from_days(days: int) -> str:
        return (
            "0-30" if days <= 30 else
            "31-60" if days <= 60 else
            "61-90" if days <= 90 else
            "91-120" if days <= 120 else
            "121-150" if days <= 150 else
            "151-180" if days <= 180 else
            "181+"
        )

    simulated_payments = 0
    fully_cured_accounts = 0

    def apply_payment_effect(account: Cuenta, payment_amount: float) -> None:
        nonlocal fully_cured_accounts
        previous_total = float(account.saldo_total or 0)
        previous_mora = float(account.saldo_mora or 0)
        if previous_total <= 0:
            return
        applied_amount = min(payment_amount, previous_total)
        account.saldo_total = round(max(0.0, previous_total - applied_amount), 2)
        account.saldo_mora = round(max(0.0, previous_mora - min(applied_amount, previous_mora)), 2)
        if account.saldo_total <= 0.5 or applied_amount >= previous_total * 0.92:
            account.saldo_total = 0.0
            account.saldo_mora = 0.0
            account.dias_mora = 0
            account.bucket_actual = "0-30"
            account.estado = "ACTIVA"
            fully_cured_accounts += 1
            return

        minimum_reference = max(calculate_minimum_payment(account), 1.0)
        if applied_amount >= previous_mora:
            reduction_band = 45
        elif applied_amount >= minimum_reference * 2:
            reduction_band = 25
        elif applied_amount >= minimum_reference:
            reduction_band = 12
        else:
            reduction_band = 5

        account.dias_mora = max(0, int(account.dias_mora or 0) - reduction_band)
        account.bucket_actual = bucket_from_days(int(account.dias_mora or 0))
        if account.dias_mora == 0 or (account.estado in {"LIQUIDADO", "Z"} and account.dias_mora <= 180):
            account.estado = "ACTIVA"

    aged_accounts = 0
    accounts_to_age = db.query(Cuenta).filter(Cuenta.dias_mora > 0, Cuenta.estado.in_(["ACTIVA", "VIGENTE", "LIQUIDADO", "Z"])).all()
    for account in accounts_to_age:
        aged_accounts += 1
        new_days = int(account.dias_mora or 0) + 1
        account.dias_mora = new_days
        account.bucket_actual = bucket_from_days(new_days)
        account.saldo_mora = round(float(account.saldo_mora or 0) * 1.01 + (1.5 if new_days <= 30 else 3.0 if new_days <= 90 else 5.0), 2)
        account.saldo_total = round(float(account.saldo_capital or 0) + float(account.saldo_mora or 0), 2)

    current_max_client = db.query(func.coalesce(func.max(Cliente.id), 0)).scalar() or 0
    current_max_identity_seed = db.execute(
        text("SELECT COALESCE(MAX(CAST(identity_code AS BIGINT)), 0) FROM clientes")
    ).scalar() or 0
    current_max_account = db.query(func.coalesce(func.max(Cuenta.id), 0)).scalar() or 0
    inserted_fmora1_clients = 0
    inserted_preventivo_clients = 0
    inserted_recovery_clients = 0
    recovery_rotations = 0
    seeded_recovery_client_ids: set[int] = set()

    payable_accounts = (
        db.query(Cuenta)
        .filter(Cuenta.dias_mora > 0, Cuenta.saldo_total > 0, Cuenta.estado.in_(["ACTIVA", "VIGENTE", "LIQUIDADO", "Z"]))
        .order_by(Cuenta.id.asc())
        .all()
    )
    for index, account in enumerate(payable_accounts, start=1):
        payment_amount = None
        if index % 11 == 0:
            payment_amount = float(account.saldo_total or 0)
        elif index % 7 == 0:
            payment_amount = min(float(account.saldo_total or 0), round(max(calculate_minimum_payment(account) * 2.2, float(account.saldo_mora or 0) * 0.85), 2))
        elif index % 5 == 0:
            payment_amount = min(float(account.saldo_total or 0), round(max(calculate_minimum_payment(account), float(account.saldo_mora or 0) * 0.45), 2))
        if not payment_amount or payment_amount <= 0:
            continue
        db.add(
            Pago(
                cuenta_id=account.id,
                monto=round(payment_amount, 2),
                fecha_pago=current_timestamp,
                canal="Simulacion diaria",
                referencia=f"{simulation_key}-PAY-{account.id}",
                observacion="Pago simulado para reflejar movimiento entre estrategias.",
            )
        )
        apply_payment_effect(account, float(payment_amount))
        simulated_payments += 1

    for index in range(1, fmora1_clients + 1):
        client = Cliente(
            identity_code=build_identity_code(current_max_identity_seed + index),
            nombres=["Luis Alberto", "Andrea Sofia", "Carlos Mauricio", "Diana Marcela", "Jose Ricardo", "Paola Fernanda", "Mario Ernesto", "Melissa Carolina"][index % 8],
            apellidos=["Martinez Cruz", "Hernandez Flores", "Lopez Ayala", "Ramirez Ruiz", "Guardado Perez", "Pineda Torres", "Castro Molina", "Reyes Sorto"][(index + 3) % 8],
            dui=f"8{str(current_max_identity_seed + index).zfill(7)}-{(current_max_identity_seed + index) % 10}",
            nit=f"0614-{str(current_max_identity_seed + index).zfill(6)}-{str((current_max_identity_seed + index) % 1000).zfill(3)}-{(current_max_identity_seed + index) % 10}",
            telefono=f"75{str((current_max_identity_seed + index) % 1000000).zfill(6)}",
            email=f"fmora1.{current_max_identity_seed + index}@demo360collectplus.com",
            direccion=(
                f"San Salvador, Colonia Medica, Pasaje {current_max_identity_seed + index}"
                if index % 4 == 0 else
                f"Santa Ana, Residencial Primavera, Casa {current_max_identity_seed + index}"
                if index % 4 == 1 else
                f"Soyapango, Colonia Guadalupe, Avenida {current_max_identity_seed + index}"
                if index % 4 == 2 else
                f"San Miguel, Residencial El Sitio, Poligono {current_max_identity_seed + index}"
            ),
            score_riesgo=round(0.24 + ((index % 30) / 100.0), 2),
            segmento=["Preferente", "Masivo", "Riesgo", "Recuperacion"][index % 4],
        )
        db.add(client)
        db.flush()
        account = Cuenta(
            cliente_id=client.id,
            numero_cuenta=f"{'PRE' if index % 2 == 0 else 'TAR'}-{str(client.id).zfill(6)}",
            tipo_producto="Prestamo" if index % 2 == 0 else "Tarjeta",
            subtipo_producto="Consumo" if index % 2 == 0 else ("Oro" if index % 5 == 0 else "Clasica"),
            saldo_capital=round(650 + (index % 40) * 55, 2),
            saldo_mora=round(35 + (index % 12) * 6, 2),
            saldo_total=round(685 + (index % 40) * 58, 2),
            dias_mora=1,
            bucket_actual="0-30",
            estado="ACTIVA",
            fecha_apertura=today - timedelta(days=((index % 540) + 30)),
            fecha_vencimiento=today - timedelta(days=1),
            tasa_interes=round(14 + (index % 10) * 0.85, 2),
            es_estrafinanciamiento=False,
        )
        db.add(account)
        db.flush()
        collector = active_collectors[(index - 1) % len(active_collectors)]
        assignment = WorklistAssignment(usuario_id=collector.id, cliente_id=client.id, estrategia_codigo="FMORA1", activa=True)
        db.add(assignment)
        db.flush()
        record_assignment_history(db, client, assignment, strategy_code="FMORA1", notes="Simulacion diaria automatica: cliente nuevo con 1 dia de mora.", user=collector)
        db.add(History(entidad="clientes", entidad_id=client.id, accion="CARGA_NUEVA_CARTERA", descripcion=f"Cliente ingresado en carga diaria con 1 dia de mora. Cuenta {account.numero_cuenta} asignada a FMORA1.", usuario_id=collector.id, created_at=current_timestamp))
        db.add(PrediccionIA(cuenta_id=account.id, probabilidad_pago_30d=round(0.58 - ((index % 10) * 0.015), 4), score_modelo=round((58 - ((index % 10) * 1.5)) * 10, 2), modelo_version="xgb-v2-demo", recomendacion="Mora temprana con alta recuperabilidad. Priorizar chatbot WhatsApp y seguimiento liviano."))
        inserted_fmora1_clients += 1

    # Recalculate after the FMORA1 inserts because those accounts use the DB sequence
    # and may already have consumed ids above the snapshot taken at the start.
    next_manual_account_id = db.query(func.coalesce(func.max(Cuenta.id), 0)).scalar() or current_max_account
    for index in range(1, preventivo_clients + 1):
        client = Cliente(
            identity_code=build_identity_code(current_max_identity_seed + fmora1_clients + index),
            nombres=["Karen Patricia", "Victor Manuel", "Gloria Beatriz", "Oscar David", "Roxana Isabel", "Francisco Javier"][index % 6],
            apellidos=["Arias Portillo", "Baires Mendoza", "Chavez Dubon", "Navarrete Rivas", "Calderon Ponce", "Serrano Mejia"][(index + 4) % 6],
            dui=f"7{str(current_max_identity_seed + fmora1_clients + index).zfill(7)}-{(current_max_identity_seed + fmora1_clients + index) % 10}",
            nit=f"0614-{str(current_max_identity_seed + fmora1_clients + index).zfill(6)}-{str(700 + index).zfill(3)}-{(current_max_identity_seed + fmora1_clients + index) % 10}",
            telefono=f"74{str((current_max_identity_seed + fmora1_clients + index) % 1000000).zfill(6)}",
            email=f"preventivo.{current_max_identity_seed + fmora1_clients + index}@demo360collectplus.com",
            direccion=(
                f"San Salvador, Residencial Escalon Norte, Casa {current_max_identity_seed + fmora1_clients + index}"
                if index % 3 == 0 else
                f"Santa Tecla, Colonia Quezaltepec, Pasaje {current_max_identity_seed + fmora1_clients + index}"
                if index % 3 == 1 else
                f"Antiguo Cuscatlan, Urbanizacion Madreselva, Casa {current_max_identity_seed + fmora1_clients + index}"
            ),
            score_riesgo=round(0.16 + ((index % 14) / 100.0), 2),
            segmento=["Preferente", "Masivo", "Recuperacion"][index % 3],
        )
        db.add(client)
        db.flush()
        account_id = next_cycle_cut_account_id(next_manual_account_id, {29, 30})
        next_manual_account_id = account_id
        account = Cuenta(
            id=account_id,
            cliente_id=client.id,
            numero_cuenta=f"PRV-{str(client.id).zfill(6)}",
            tipo_producto="Tarjeta" if index % 2 == 0 else "Prestamo",
            subtipo_producto="Clasica" if index % 2 == 0 else "Consumo",
            saldo_capital=round(520 + (index % 25) * 40, 2),
            saldo_mora=round(18 + (index % 7) * 4, 2),
            saldo_total=round(538 + (index % 25) * 42, 2),
            dias_mora=0,
            bucket_actual="0-30",
            estado="ACTIVA",
            fecha_apertura=today - timedelta(days=((index % 480) + 20)),
            fecha_vencimiento=today - timedelta(days=3 if index % 2 == 0 else 2),
            tasa_interes=round(13 + (index % 6) * 0.75, 2),
            es_estrafinanciamiento=False,
        )
        db.add(account)
        db.flush()
        collector = active_collectors[(index - 1) % len(active_collectors)]
        assignment = WorklistAssignment(usuario_id=collector.id, cliente_id=client.id, estrategia_codigo="PREVENTIVO", activa=True)
        db.add(assignment)
        db.flush()
        record_assignment_history(db, client, assignment, strategy_code="PREVENTIVO", notes="Simulacion diaria automatica: cliente vencido antes de corte, aun con 0 dias de mora.", user=collector)
        db.add(History(entidad="clientes", entidad_id=client.id, accion="CARGA_PREVENTIVO", descripcion=f"Cliente ingresado a PREVENTIVO: fecha de vencimiento ya paso, aun no llega fecha de corte. Cuenta {account.numero_cuenta} con 0 dias mora.", usuario_id=collector.id, created_at=current_timestamp))
        db.add(PrediccionIA(cuenta_id=account.id, probabilidad_pago_30d=round(0.71 - ((index % 8) * 0.01), 4), score_modelo=round((71 - ((index % 8) * 1.0)) * 10, 2), modelo_version="xgb-v2-demo", recomendacion="Seguimiento preventivo con recordatorio digital y priorizacion de chatbot antes de contacto humano."))
        inserted_preventivo_clients += 1

    # Preventivo inserts explicit account ids to avoid cycle-cut collisions.
    # Sync the database sequence before inserting Recovery accounts with automatic ids.
    db.flush()
    db.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('cuentas', 'id'), COALESCE((SELECT MAX(id) FROM cuentas), 1), true)"
        )
    )

    for index in range(1, recovery_clients + 1):
        sequence_base = current_max_identity_seed + fmora1_clients + preventivo_clients + index
        separation_date = build_recovery_separation_date(sequence_base, today)
        client = Cliente(
            identity_code=build_identity_code(sequence_base),
            nombres=["Samuel Antonio", "Gabriela Elena", "Mauricio Jose", "Patricia Lorena", "Edwin Rafael", "Marisela Beatriz"][index % 6],
            apellidos=["Rivera Diaz", "Mejia Paredes", "Portillo Castillo", "Linares Castro", "Rivas Sandoval", "Bonilla Flores"][(index + 2) % 6],
            dui=f"6{str(sequence_base).zfill(7)}-{sequence_base % 10}",
            nit=f"0614-{str(sequence_base).zfill(6)}-{str(500 + index).zfill(3)}-{sequence_base % 10}",
            telefono=f"73{str(sequence_base % 1000000).zfill(6)}",
            email=f"recovery.{sequence_base}@demo360collectplus.com",
            direccion=f"San Salvador, Ruta Recovery, placement {index}, cliente {sequence_base}",
            score_riesgo=round(0.72 + ((index % 18) / 100.0), 2),
            segmento="Recovery",
        )
        db.add(client)
        db.flush()
        account = Cuenta(
            cliente_id=client.id,
            numero_cuenta=f"RCV-{str(client.id).zfill(6)}",
            tipo_producto="Tarjeta" if index % 2 == 0 else "Prestamo",
            subtipo_producto="Recuperacion",
            saldo_capital=round(850 + (index % 60) * 45, 2),
            saldo_mora=round(420 + (index % 25) * 24, 2),
            saldo_total=round(1270 + (index % 60) * 61, 2),
            dias_mora=185 + (index % 45),
            bucket_actual="181+",
            estado="LIQUIDADO" if index % 2 == 0 else "Z",
            fecha_apertura=today - timedelta(days=((index % 1600) + 420)),
            fecha_vencimiento=today - timedelta(days=185 + (index % 45)),
            fecha_separacion=separation_date,
            tasa_interes=round(18 + (index % 6) * 0.9, 2),
            es_estrafinanciamiento=False,
        )
        db.add(account)
        db.flush()
        collector = active_collectors[(index - 1) % len(active_collectors)]
        assignment = WorklistAssignment(usuario_id=collector.id, cliente_id=client.id, estrategia_codigo="VAGENCIASEXTERNASINTERNO", activa=True)
        db.add(assignment)
        db.flush()
        record_assignment_history(db, client, assignment, strategy_code="VAGENCIASEXTERNASINTERNO", notes="Simulacion diaria automatica: cliente Recovery distribuido en placement y agencia.", user=collector)
        db.add(History(entidad="clientes", entidad_id=client.id, accion="CARGA_RECOVERY", descripcion=f"Cliente Recovery ingresado en VAGENCIASEXTERNASINTERNO. Cuenta {account.numero_cuenta} asignada a placement inicial.", usuario_id=collector.id, created_at=current_timestamp))
        db.add(PrediccionIA(cuenta_id=account.id, probabilidad_pago_30d=round(0.34 - ((index % 9) * 0.012), 4), score_modelo=round((34 - ((index % 9) * 1.2)) * 10, 2), modelo_version="xgb-v2-demo", recomendacion="Recovery de alta severidad. Priorizar callbot, llamada humana y refuerzo por WhatsApp."))
        inserted_recovery_clients += 1
        seeded_recovery_client_ids.add(client.id)

    db.flush()
    recovery_assignments = (
        db.query(WorklistAssignment)
        .join(Cuenta, Cuenta.cliente_id == WorklistAssignment.cliente_id)
        .filter(
            WorklistAssignment.activa.is_(True),
            Cuenta.dias_mora > 180,
            Cuenta.estado.in_(["LIQUIDADO", "Z"]),
        )
        .distinct()
        .all()
    )
    rotated_clients: set[int] = set()
    for assignment in recovery_assignments:
        if assignment.cliente_id in rotated_clients:
            continue
        if assignment.cliente_id in seeded_recovery_client_ids:
            continue
        rotated_clients.add(assignment.cliente_id)
        client = db.get(Cliente, assignment.cliente_id)
        if not client:
            continue
        assignment.estrategia_codigo = "VAGENCIASEXTERNASINTERNO"
        record_assignment_history(
            db,
            client,
            assignment,
            strategy_code="VAGENCIASEXTERNASINTERNO",
            notes="Rotacion diaria de placement Recovery segun simulacion operativa.",
            user=db.get(Usuario, assignment.usuario_id) if assignment.usuario_id else None,
        )
        recovery_rotations += 1

    db.execute(text("SELECT setval(pg_get_serial_sequence('cuentas', 'id'), (SELECT MAX(id) FROM cuentas))"))
    db.add(History(entidad="system", entidad_id=0, accion="SIMULACION_DIA_OPERATIVO", descripcion=f"{simulation_key}: mora +1 aplicada a cuentas vencidas, pagos simulados {simulated_payments}, {inserted_fmora1_clients} clientes FMORA1 nuevos, {inserted_preventivo_clients} clientes PREVENTIVO nuevos, {inserted_recovery_clients} clientes Recovery nuevos y {recovery_rotations} rotaciones de placement.", usuario_id=current_user.id, created_at=current_timestamp))
    db.commit()
    return {
        "simulation_key": simulation_key,
        "aged_accounts": aged_accounts,
        "inserted_fmora1_clients": inserted_fmora1_clients,
        "inserted_preventivo_clients": inserted_preventivo_clients,
        "inserted_recovery_clients": inserted_recovery_clients,
        "simulated_payments": simulated_payments,
        "fully_cured_accounts": fully_cured_accounts,
        "recovery_rotations": recovery_rotations,
        "total_clients": db.query(Cliente).count(),
        "total_accounts": db.query(Cuenta).count(),
        "message": "Dia operativo simulado correctamente.",
    }


def is_hmr_candidate(account: Cuenta) -> bool:
    return account.estado in {"ACTIVA", "VIGENTE"} and (
        account.es_estrafinanciamiento or (31 <= account.dias_mora <= 180 and float(account.saldo_total) >= 900)
    )


def calculate_minimum_payment(account: Cuenta) -> float:
    saldo_total = float(account.saldo_total or 0)
    saldo_mora = float(account.saldo_mora or 0)
    saldo_capital = float(account.saldo_capital or 0)
    if saldo_total <= 0:
        return 0.0
    minimum = max(25.0, saldo_mora + max(saldo_total * 0.03, saldo_capital * 0.015))
    return round(min(minimum, saldo_total), 2)


def parse_callback_description(value: Optional[str]) -> tuple[Optional[datetime], Optional[str]]:
    if not value:
        return None, None
    try:
        payload = json.loads(value)
        callback_raw = payload.get("callback_at")
        callback_at = datetime.fromisoformat(callback_raw) if callback_raw else None
        return callback_at, payload.get("notes")
    except (ValueError, json.JSONDecodeError, TypeError):
        return None, None


def add_business_days(start_date: date, business_days: int) -> date:
    current = start_date
    added = 0
    while added < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def build_recovery_separation_date(seed_index: int, reference_date: Optional[date] = None) -> date:
    target_date = reference_date or date.today()
    start = date(RECOVERY_VINTAGE_START_YEAR, 1, 1)
    end = date(target_date.year, 12, 31)
    span_days = max((end - start).days + 1, 365)
    return start + timedelta(days=((seed_index * 17) % span_days))


def build_recovery_vintage_overview(
    db: Session,
    year: int,
    lookback_days: int = 120,
    payment_threshold: float = 10.0,
    sample_limit: int = 60,
) -> RecoveryVintageOverviewResponse:
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    vintage_rows = (
        db.query(Cuenta, Cliente)
        .join(Cliente, Cliente.id == Cuenta.cliente_id)
        .filter(
            Cuenta.fecha_separacion.isnot(None),
            func.extract("year", Cuenta.fecha_separacion) == year,
        )
        .order_by(Cuenta.fecha_separacion.asc(), Cuenta.id.asc())
        .all()
    )

    if not vintage_rows:
        return RecoveryVintageOverviewResponse(
            year=year,
            lookback_days=lookback_days,
            payment_threshold=payment_threshold,
            total_clients=0,
            total_balance=0,
            total_due=0,
            active_payers_120d=0,
            v11_clients=0,
            placements_tracked=0,
            placements=[],
            sample_clients=[],
        )

    clients_by_id: dict[int, dict[str, Any]] = {}
    account_ids: list[int] = []
    for account, client in vintage_rows:
        payload = clients_by_id.setdefault(
            client.id,
            {
                "client": client,
                "separation_date": account.fecha_separacion,
                "statuses": set(),
                "account_count": 0,
                "account_numbers": [],
                "total_balance": 0.0,
                "total_due": 0.0,
            },
        )
        if account.fecha_separacion and (
            payload["separation_date"] is None or account.fecha_separacion < payload["separation_date"]
        ):
            payload["separation_date"] = account.fecha_separacion
        payload["statuses"].add(account.estado)
        payload["account_count"] += 1
        payload["account_numbers"].append(account.numero_cuenta)
        payload["total_balance"] = round(float(payload["total_balance"] or 0) + float(account.saldo_total or 0), 2)
        payload["total_due"] = round(float(payload["total_due"] or 0) + float(account.saldo_mora or 0), 2)
        account_ids.append(account.id)

    client_ids = list(clients_by_id.keys())
    current_histories = (
        db.query(AssignmentHistory)
        .filter(
            AssignmentHistory.cliente_id.in_(client_ids),
            AssignmentHistory.strategy_code == "VAGENCIASEXTERNASINTERNO",
            AssignmentHistory.is_current.is_(True),
        )
        .order_by(AssignmentHistory.start_at.desc(), AssignmentHistory.id.desc())
        .all()
    )
    current_history_by_client: dict[int, AssignmentHistory] = {}
    for row in current_histories:
        current_history_by_client.setdefault(row.cliente_id, row)

    movement_histories = (
        db.query(AssignmentHistory)
        .filter(
            AssignmentHistory.cliente_id.in_(client_ids),
            AssignmentHistory.strategy_code == "VAGENCIASEXTERNASINTERNO",
        )
        .order_by(AssignmentHistory.cliente_id.asc(), AssignmentHistory.start_at.asc(), AssignmentHistory.id.asc())
        .all()
    )
    movement_paths: dict[int, list[str]] = defaultdict(list)
    for row in movement_histories:
        placement_label = row.placement_code or "SIN_PLACEMENT"
        if not movement_paths[row.cliente_id] or movement_paths[row.cliente_id][-1] != placement_label:
            movement_paths[row.cliente_id].append(placement_label)

    recent_payments = (
        db.query(Pago, Cuenta.cliente_id)
        .join(Cuenta, Cuenta.id == Pago.cuenta_id)
        .filter(
            Cuenta.id.in_(account_ids),
            Pago.fecha_pago >= cutoff_dt,
            Pago.monto >= payment_threshold,
        )
        .order_by(Pago.fecha_pago.desc(), Pago.id.desc())
        .all()
    )
    payment_summary_by_client: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "payment_count": 0,
            "total_paid": 0.0,
            "max_payment": 0.0,
            "last_payment_date": None,
        }
    )
    for payment, client_id in recent_payments:
        summary = payment_summary_by_client[client_id]
        amount = round(float(payment.monto or 0), 2)
        summary["payment_count"] += 1
        summary["total_paid"] = round(summary["total_paid"] + amount, 2)
        summary["max_payment"] = max(summary["max_payment"], amount)
        if summary["last_payment_date"] is None or payment.fecha_pago > summary["last_payment_date"]:
            summary["last_payment_date"] = payment.fecha_pago

    placement_summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "placement_code": "SIN_PLACEMENT",
            "client_count": 0,
            "paying_clients_120d": 0,
            "total_paid_120d": 0.0,
            "total_balance": 0.0,
            "total_due": 0.0,
            "v11_eligible_clients": 0,
            "agencies": defaultdict(
                lambda: {
                    "group_id": "SIN_CARTERA",
                    "channel_scope": None,
                    "client_count": 0,
                    "paying_clients_120d": 0,
                    "total_paid_120d": 0.0,
                    "total_balance": 0.0,
                    "total_due": 0.0,
                    "v11_eligible_clients": 0,
                }
            ),
        }
    )
    sample_clients: list[RecoveryVintageClientRead] = []

    for client_id, payload in clients_by_id.items():
        current_history = current_history_by_client.get(client_id)
        placement_code = current_history.placement_code if current_history and current_history.placement_code else "SIN_PLACEMENT"
        group_id = current_history.group_id if current_history and current_history.group_id else "SIN_CARTERA"
        channel_scope = current_history.channel_scope if current_history else None
        payment_summary = payment_summary_by_client.get(client_id, {})
        total_paid = round(float(payment_summary.get("total_paid", 0.0) or 0.0), 2)
        payment_count = int(payment_summary.get("payment_count", 0) or 0)
        max_payment = round(float(payment_summary.get("max_payment", 0.0) or 0.0), 2)
        last_payment_date = payment_summary.get("last_payment_date")
        qualifies_for_v11 = payment_count > 0
        current_status = sorted(payload["statuses"])[0] if payload["statuses"] else None
        total_balance = round(float(payload["total_balance"] or 0), 2)
        total_due = round(float(payload["total_due"] or 0), 2)

        placement_item = placement_summary[placement_code]
        placement_item["placement_code"] = placement_code
        placement_item["client_count"] += 1
        placement_item["total_paid_120d"] = round(placement_item["total_paid_120d"] + total_paid, 2)
        placement_item["total_balance"] = round(placement_item["total_balance"] + total_balance, 2)
        placement_item["total_due"] = round(placement_item["total_due"] + total_due, 2)
        if payment_count > 0:
            placement_item["paying_clients_120d"] += 1
            placement_item["v11_eligible_clients"] += 1

        agency_item = placement_item["agencies"][group_id]
        agency_item["group_id"] = group_id
        agency_item["channel_scope"] = channel_scope
        agency_item["client_count"] += 1
        agency_item["total_paid_120d"] = round(agency_item["total_paid_120d"] + total_paid, 2)
        agency_item["total_balance"] = round(agency_item["total_balance"] + total_balance, 2)
        agency_item["total_due"] = round(agency_item["total_due"] + total_due, 2)
        if payment_count > 0:
            agency_item["paying_clients_120d"] += 1
            agency_item["v11_eligible_clients"] += 1

        client_model = RecoveryVintageClientRead(
            client_id=client_id,
            identity_code=format_identity_code(payload["client"].identity_code, payload["client"].id),
            client_name=f"{payload['client'].nombres} {payload['client'].apellidos}".strip(),
            separation_date=payload["separation_date"],
            current_status=current_status,
            current_placement=placement_code,
            current_group_id=current_history.group_id if current_history else None,
            current_scope=current_history.channel_scope if current_history else None,
            account_count=payload["account_count"],
            total_balance=total_balance,
            total_due=total_due,
            qualifying_payment_count_120d=payment_count,
            total_paid_120d=total_paid,
            max_payment_120d=max_payment,
            last_payment_date=last_payment_date,
            movement_path=" → ".join(movement_paths.get(client_id, [placement_code])),
            qualifies_for_v11=qualifies_for_v11,
        )
        sample_clients.append(client_model)

    placement_order = {code: index for index, code in enumerate(PLACEMENT_SEQUENCE)}
    placements: list[RecoveryVintagePlacementRead] = []
    for item in placement_summary.values():
        agencies = sorted(
            (
                RecoveryVintageAgencyRead(
                    group_id=agency["group_id"],
                    channel_scope=agency["channel_scope"],
                    client_count=agency["client_count"],
                    paying_clients_120d=agency["paying_clients_120d"],
                    total_paid_120d=round(float(agency["total_paid_120d"] or 0), 2),
                    total_balance=round(float(agency["total_balance"] or 0), 2),
                    total_due=round(float(agency["total_due"] or 0), 2),
                    v11_eligible_clients=agency["v11_eligible_clients"],
                    payment_rate_120d=round(
                        ((float(agency["paying_clients_120d"]) / float(agency["client_count"])) * 100) if agency["client_count"] else 0,
                        1,
                    ),
                )
                for agency in item["agencies"].values()
            ),
            key=lambda agency: (
                -(agency.payment_rate_120d or 0),
                -(agency.total_paid_120d or 0),
                -(agency.paying_clients_120d or 0),
                agency.group_id,
            ),
        )
        placements.append(
            RecoveryVintagePlacementRead(
                placement_code=item["placement_code"],
                client_count=item["client_count"],
                paying_clients_120d=item["paying_clients_120d"],
                total_paid_120d=round(float(item["total_paid_120d"] or 0), 2),
                total_balance=round(float(item["total_balance"] or 0), 2),
                total_due=round(float(item["total_due"] or 0), 2),
                v11_eligible_clients=item["v11_eligible_clients"],
                best_group_id=agencies[0].group_id if agencies else None,
                best_group_rate_120d=agencies[0].payment_rate_120d if agencies else 0,
                lagging_group_id=agencies[-1].group_id if agencies else None,
                lagging_group_rate_120d=agencies[-1].payment_rate_120d if agencies else 0,
                agencies=agencies,
            )
        )
    placements.sort(key=lambda item: (placement_order.get(item.placement_code, 999), item.placement_code))
    sample_clients.sort(
        key=lambda item: (
            placement_order.get(item.current_placement or "SIN_PLACEMENT", 999),
            -(item.total_paid_120d or 0),
            item.identity_code,
        )
    )

    return RecoveryVintageOverviewResponse(
        year=year,
        lookback_days=lookback_days,
        payment_threshold=payment_threshold,
        total_clients=len(sample_clients),
        total_balance=round(sum(float(item.total_balance or 0) for item in sample_clients), 2),
        total_due=round(sum(float(item.total_due or 0) for item in sample_clients), 2),
        active_payers_120d=sum(1 for item in sample_clients if item.qualifying_payment_count_120d > 0),
        v11_clients=next((item.client_count for item in placements if item.placement_code == "V11"), 0),
        placements_tracked=len(placements),
        placements=placements,
        sample_clients=sample_clients[:sample_limit],
    )


def resolve_strategy(account: Cuenta, today: datetime) -> str:
    if account.dias_mora > 180 and account.estado in {"LIQUIDADO", "Z"}:
        return "VAGENCIASEXTERNASINTERNO"
    if account.dias_mora > 190 and account.estado in {"VIGENTE", "ACTIVA"}:
        return "DMORA7"
    if 151 <= account.dias_mora <= 180:
        return "CMORA6"
    if 121 <= account.dias_mora <= 150:
        return "BMORA5"
    if 91 <= account.dias_mora <= 120:
        return "AMORA4"
    if 61 <= account.dias_mora <= 90:
        return "HMORA3"
    if 31 <= account.dias_mora <= 60:
        return "MMORA2"
    if 1 <= account.dias_mora <= 30:
        return "FMORA1"

    cycle_cut_day = get_cycle_cut_day(account)
    due_day = get_due_day(cycle_cut_day)
    if account.dias_mora <= 0 and account.estado in {"ACTIVA", "VIGENTE"} and due_day <= today.day < cycle_cut_day:
        return "PREVENTIVO"

    return "AL_DIA"





# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(title=settings.app_name, version="2.0.0", docs_url="/docs", redoc_url="/redoc")

allowed_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_origin_regex=r"^https:\/\/([a-z0-9-]+\.trycloudflare\.com|[a-z0-9-]+\.onrender\.com)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        ensure_minimal_demo_users()
    except Exception:
        logger.exception("No se pudieron garantizar los usuarios demo iniciales.")
    threading.Thread(target=bootstrap_runtime, daemon=True).start()


@app.get("/health")
def healthcheck():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "2.0.0",
        "bootstrap": BOOTSTRAP_STATE["status"],
        "bootstrap_error": BOOTSTRAP_STATE["error"],
    }


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/auth/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    check_login_rate_limit(request)
    user = db.query(Usuario).filter(Usuario.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    user.ultimo_login = datetime.now(timezone.utc)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.username),
        refresh_token=create_refresh_token(user.username),
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


@app.post("/auth/refresh", response_model=TokenResponse)
def refresh_token_endpoint(payload: RefreshRequest, db: Session = Depends(get_db)):
    username = decode_refresh_token(payload.refresh_token)
    if not username:
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado.")
    user = db.query(Usuario).filter(Usuario.username == username, Usuario.activo.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado.")
    return TokenResponse(
        access_token=create_access_token(user.username),
        refresh_token=create_refresh_token(user.username),
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


@app.get("/auth/me", response_model=UserRead)
def me(current_user: Usuario = Depends(get_current_user)):
    return current_user

def list_users(
    role: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "GestorUsuarios", "Auditor")),
):
    query = db.query(Usuario)
    if role:
        query = query.filter(Usuario.rol == role)
    return query.order_by(Usuario.id).all()




@app.get("/users", response_model=list[UserRead])
def list_users(
    role: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "GestorUsuarios", "Auditor")),
):
    query = db.query(Usuario)
    if role:
        query = query.filter(Usuario.rol == role)
    return query.order_by(Usuario.id).all()


@app.post("/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "GestorUsuarios")),
):
    if db.query(Usuario).filter((Usuario.username == payload.username) | (Usuario.email == payload.email)).first():
        raise HTTPException(status_code=400, detail="Usuario o correo ya registrado.")

    user = Usuario(
        nombre=payload.nombre,
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        rol=payload.rol,
        activo=payload.activo,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.put("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "GestorUsuarios")),
):
    user = db.get(Usuario, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "password":
            user.password_hash = hash_password(value)
        else:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@app.get("/clients", response_model=list[ClienteRead])
def list_clients(
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    visible_clients = get_visible_clients_for_user(db, current_user)
    visible_ids = [item.id for item in visible_clients]
    query = db.query(Cliente)
    if current_user.rol == "Collector" and is_external_agency_collector(db, current_user):
        if not visible_ids:
            return []
        query = query.filter(Cliente.id.in_(visible_ids))
    if search:
        like_value = f"%{search}%"
        query = query.filter(
            (Cliente.nombres.ilike(like_value))
            | (Cliente.apellidos.ilike(like_value))
            | (Cliente.identity_code.ilike(like_value))
            | (Cliente.dui.ilike(like_value))
        )
    return query.order_by(Cliente.id).all()


@app.get("/collector/client-lookup", response_model=Optional[CollectorClientRead])
def lookup_visible_client(
    search: str = Query(..., min_length=1),
    mode: str = Query(default="all"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    visible_clients: Optional[list[Cliente]] = None
    visible_ids: Optional[list[int]] = None
    if current_user.rol == "Collector" and is_external_agency_collector(db, current_user):
        visible_clients = get_visible_clients_for_user(db, current_user)
        visible_ids = [item.id for item in visible_clients]
        if not visible_ids:
            return None

    normalized_query = re.sub(r"\D", "", search or "")
    if normalized_query:
        target_id = int(normalized_query)
        exact_query = db.query(Cliente).filter(Cliente.id == target_id)
        if visible_ids is not None:
            exact_query = exact_query.filter(Cliente.id.in_(visible_ids))
        exact_client = exact_query.first()
        if exact_client:
            return build_collector_client_snapshot(db, current_user, exact_client)

    if visible_clients is None:
        visible_clients = get_visible_clients_for_user(db, current_user)
    if not visible_clients:
        return None
    if visible_ids is None:
        visible_ids = [item.id for item in visible_clients]

    accounts_by_client: dict[int, list[dict[str, Any]]] = {}
    if visible_ids:
        account_rows = (
            db.query(Cuenta.id, Cuenta.cliente_id, Cuenta.numero_cuenta, Cuenta.tipo_producto, Cuenta.subtipo_producto)
            .filter(Cuenta.cliente_id.in_(visible_ids))
            .all()
        )
        for row in account_rows:
            account_display = derive_account_display_metadata(
                type(
                    "AccountSnapshot",
                    (),
                    {
                        "id": row.id,
                        "numero_cuenta": row.numero_cuenta,
                        "tipo_producto": row.tipo_producto,
                        "subtipo_producto": row.subtipo_producto,
                        "estado": None,
                    },
                )()
            )
            accounts_by_client.setdefault(
                row.cliente_id,
                [],
            ).append(
                {
                    "numero_cuenta": row.numero_cuenta,
                    "numero_plastico": account_display["plastic_number"],
                    "codigo_ubicacion": account_display["location_code"],
                    "producto_nombre": account_display["product_name"],
                }
            )

    scored_matches: list[tuple[int, int]] = []
    for client in visible_clients:
        score = get_client_lookup_score(client, search, mode)
        if score > 0:
            scored_matches.append((score, client.id))

    if scored_matches:
        scored_matches.sort(key=lambda item: (-item[0], item[1]))
        target_client = next((client for client in visible_clients if client.id == scored_matches[0][1]), None)
        if target_client:
            return build_collector_client_snapshot(db, current_user, target_client)

    for client in visible_clients:
        if client_matches_search(client, search, mode, accounts_by_client.get(client.id, [])):
            return build_collector_client_snapshot(db, current_user, client)
    return None


@app.post("/clients", response_model=ClienteRead, status_code=201)
def create_client(
    payload: ClienteCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "Collector", "Supervisor")),
):
    client = Cliente(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@app.put("/clients/{client_id}", response_model=ClienteRead)
def update_client(
    client_id: int,
    payload: ClienteUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "Collector", "Supervisor")),
):
    client = db.get(Cliente, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    return client


@app.get("/accounts", response_model=list[CuentaRead])
def list_accounts(
    client_id: Optional[int] = Query(default=None),
    bucket: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    query = db.query(Cuenta)
    if client_id:
        query = query.filter(Cuenta.cliente_id == client_id)
    if bucket:
        query = query.filter(Cuenta.bucket_actual == bucket)
    return query.order_by(Cuenta.id).all()


@app.post("/accounts", response_model=CuentaRead, status_code=201)
def create_account(
    payload: CuentaCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "Collector", "Supervisor")),
):
    if not db.get(Cliente, payload.cliente_id):
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    account = Cuenta(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@app.put("/accounts/{account_id}", response_model=CuentaRead)
def update_account(
    account_id: int,
    payload: CuentaUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "Collector", "Supervisor")),
):
    account = db.get(Cuenta, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)

    db.commit()
    db.refresh(account)
    return account


@app.get("/payments", response_model=list[PagoRead])
def list_payments(
    account_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    query = db.query(Pago)
    if account_id:
        query = query.filter(Pago.cuenta_id == account_id)
    return query.order_by(Pago.fecha_pago.desc()).all()


@app.post("/payments", response_model=PagoRead, status_code=201)
def create_payment(
    payload: PagoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "Collector", "Supervisor")),
):
    account = db.get(Cuenta, payload.cuenta_id)
    if not account:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")

    payment = Pago(**payload.model_dump())
    account.saldo_total = float(max(0, float(account.saldo_total) - payload.monto))
    account.saldo_mora = float(max(0, float(account.saldo_mora) - min(payload.monto, float(account.saldo_mora))))
    account.bucket_actual = "0-30" if account.saldo_total <= 0 else account.bucket_actual
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def build_collector_portfolio_response(
    db: Session,
    current_user: Usuario,
) -> CollectorPortfolioResponse:
    assigned_clients = get_assigned_clients_for_collector(db, current_user)[:COLLECTOR_DAILY_WORKLIST_LIMIT]
    assigned_client_ids = [client.id for client in assigned_clients]
    today = datetime.utcnow().date()

    if not assigned_client_ids:
        return CollectorPortfolioResponse(
            collector=UserRead.model_validate(current_user),
            metrics=CollectorMetrics(
                assigned_today=0,
                remaining_today=0,
                worked_today=0,
                payment_agreements_today=0,
                due_promises_today=0,
                total_outstanding=0.0,
                hmr_candidates=0,
                strategy_summary={},
                scheduled_callbacks_today=0,
                supervisor_reviews_pending=0,
            ),
            clients=[],
        )

    collector_histories = (
        db.query(History)
        .filter(
            History.usuario_id == current_user.id,
            History.entidad == "clientes",
            History.entidad_id.in_(assigned_client_ids),
        )
        .order_by(History.created_at.desc())
        .all()
    )
    client_histories = (
        db.query(History)
        .filter(
            History.entidad == "clientes",
            History.entidad_id.in_(assigned_client_ids),
        )
        .order_by(History.created_at.desc())
        .all()
    )
    history_by_client: dict[int, list[History]] = {}
    latest_history_by_client: dict[int, History] = {}
    callback_history_by_client: dict[int, History] = {}
    for item in client_histories:
        history_by_client.setdefault(item.entidad_id, [])
        if len(history_by_client[item.entidad_id]) < 60:
            history_by_client[item.entidad_id].append(item)
        if item.entidad_id not in latest_history_by_client and item.accion != "CALLBACK_PROGRAMADO":
            latest_history_by_client[item.entidad_id] = item
        if item.entidad_id not in callback_history_by_client and item.accion == "CALLBACK_PROGRAMADO":
            callback_history_by_client[item.entidad_id] = item

    worked_today_ids = {
        item.entidad_id
        for item in collector_histories
        if item.created_at and item.created_at.date() == today and item.accion in {"GESTION_REGISTRADA", "PROMESA_CREADA", "CLIENTE_ACTUALIZADO"}
    }
    promises_today = (
        db.query(Promesa)
        .filter(Promesa.usuario_id == current_user.id, Promesa.created_at >= datetime.combine(today, datetime.min.time()))
        .all()
    )
    accounts = (
        db.query(Cuenta)
        .filter(Cuenta.cliente_id.in_(assigned_client_ids))
        .order_by(Cuenta.cliente_id.asc(), Cuenta.dias_mora.desc())
        .all()
    )
    account_ids = [account.id for account in accounts]
    predictions = (
        db.query(PrediccionIA)
        .filter(PrediccionIA.cuenta_id.in_(account_ids))
        .all()
        if account_ids
        else []
    )
    predictions_by_account = {prediction.cuenta_id: prediction for prediction in predictions}
    accounts_by_client: dict[int, list[Cuenta]] = {}
    for account in accounts:
        accounts_by_client.setdefault(account.cliente_id, []).append(account)

    pending_promises_query = (
        db.query(Promesa, Cuenta.cliente_id.label("client_id"))
        .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
        .filter(Cuenta.cliente_id.in_(assigned_client_ids), Promesa.estado.in_(["PENDIENTE", "REVISION_SUPERVISOR"]))
        .order_by(Cuenta.cliente_id.asc(), Promesa.fecha_promesa.asc())
        .all()
    )
    all_promises_query = (
        db.query(Promesa, Cuenta.cliente_id.label("client_id"), Cuenta.numero_cuenta.label("numero_cuenta"))
        .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
        .filter(Cuenta.cliente_id.in_(assigned_client_ids))
        .order_by(Promesa.created_at.desc(), Promesa.fecha_promesa.desc())
        .all()
    )
    payments_query = (
        db.query(Pago, Cuenta.cliente_id.label("client_id"), Cuenta.numero_cuenta.label("numero_cuenta"))
        .join(Cuenta, Cuenta.id == Pago.cuenta_id)
        .filter(Cuenta.cliente_id.in_(assigned_client_ids))
        .order_by(Pago.fecha_pago.desc(), Pago.created_at.desc())
        .all()
    )
    pending_promises_by_client: dict[int, list[Promesa]] = {}
    for promise, client_id in pending_promises_query:
        pending_promises_by_client.setdefault(client_id, []).append(promise)
    assignment_history_rows = (
        db.query(AssignmentHistory)
        .filter(
            AssignmentHistory.cliente_id.in_(assigned_client_ids),
            AssignmentHistory.is_current.is_(True),
        )
        .order_by(AssignmentHistory.start_at.desc(), AssignmentHistory.id.desc())
        .all()
    )
    current_assignment_by_client: dict[int, AssignmentHistory] = {}
    for assignment_history in assignment_history_rows:
        current_assignment_by_client.setdefault(assignment_history.cliente_id, assignment_history)
    synthetic_history_by_client: dict[int, list[ManagementHistoryRead]] = {}

    for promise, client_id, numero_cuenta in all_promises_query:
        synthetic_history_by_client.setdefault(client_id, [])
        if len(synthetic_history_by_client[client_id]) >= 20:
            continue
        synthetic_history_by_client[client_id].append(
            ManagementHistoryRead(
                id=-(200000000 + promise.id),
                fecha=(promise.created_at or datetime.combine(promise.fecha_promesa, datetime.min.time())).isoformat(),
                accion="PROMESA_CREADA",
                descripcion=(
                    f"Promesa {promise.estado.lower()} registrada para la cuenta {numero_cuenta} "
                    f"con fecha {promise.fecha_promesa.isoformat()} por {float(promise.monto_prometido):,.2f}."
                ),
                usuario_id=promise.usuario_id,
            )
        )

    for payment, client_id, numero_cuenta in payments_query:
        synthetic_history_by_client.setdefault(client_id, [])
        if len(synthetic_history_by_client[client_id]) >= 30:
            continue
        synthetic_history_by_client[client_id].append(
            ManagementHistoryRead(
                id=-(300000000 + payment.id),
                fecha=(payment.fecha_pago or payment.created_at or datetime.utcnow()).isoformat(),
                accion="PAGO_REGISTRADO",
                descripcion=(
                    f"Pago registrado en la cuenta {numero_cuenta} por {float(payment.monto):,.2f} "
                    f"via {payment.canal or 'canal no identificado'}."
                ),
                usuario_id=None,
            )
        )

    missing_history_client_ids = [client_id for client_id in assigned_client_ids if not history_by_client.get(client_id)]
    if missing_history_client_ids:
        generated_history_rows: list[History] = []
        for client_id in missing_history_client_ids:
            client_accounts = accounts_by_client.get(client_id, [])
            client_promises = [promise for promise, promise_client_id, _ in all_promises_query if promise_client_id == client_id]
            client_payments = [payment for payment, payment_client_id, _ in payments_query if payment_client_id == client_id]

            if client_accounts:
                lead_account = client_accounts[0]
                generated_history_rows.append(
                    History(
                        entidad="clientes",
                        entidad_id=client_id,
                        accion="CUENTA_EN_SEGUIMIENTO",
                        descripcion=(
                            f"Cliente cargado a gestion con la cuenta {lead_account.numero_cuenta} "
                            f"en {resolve_strategy(lead_account, datetime.utcnow())}, "
                            f"{lead_account.dias_mora} dias de mora y saldo vencido de {float(lead_account.saldo_mora):,.2f}."
                        ),
                        usuario_id=current_user.id,
                        created_at=datetime.utcnow() - timedelta(days=5),
                    )
                )

            if client_promises:
                latest_promise = client_promises[0]
                generated_history_rows.append(
                    History(
                        entidad="clientes",
                        entidad_id=client_id,
                        accion="PROMESA_CREADA",
                        descripcion=(
                            f"Promesa {latest_promise.estado.lower()} detectada en historico "
                            f"por {float(latest_promise.monto_prometido):,.2f} con fecha "
                            f"{latest_promise.fecha_promesa.isoformat()}."
                        ),
                        usuario_id=latest_promise.usuario_id or current_user.id,
                        created_at=latest_promise.created_at or (datetime.utcnow() - timedelta(days=3)),
                    )
                )

            if client_payments:
                latest_payment = client_payments[0]
                generated_history_rows.append(
                    History(
                        entidad="clientes",
                        entidad_id=client_id,
                        accion="PAGO_REGISTRADO",
                        descripcion=(
                            f"Pago historico identificado por {float(latest_payment.monto):,.2f} "
                            f"via {latest_payment.canal or 'canal no identificado'}."
                        ),
                        usuario_id=current_user.id,
                        created_at=latest_payment.fecha_pago or latest_payment.created_at or (datetime.utcnow() - timedelta(days=1)),
                    )
                )

            if not client_accounts and not client_promises and not client_payments:
                generated_history_rows.append(
                    History(
                        entidad="clientes",
                        entidad_id=client_id,
                        accion="GESTION_REGISTRADA",
                        descripcion="Cliente incorporado a la cartera diaria para inicio de gestion de cobro.",
                        usuario_id=current_user.id,
                        created_at=datetime.utcnow() - timedelta(days=2),
                    )
                )

        if generated_history_rows:
            db.add_all(generated_history_rows)
            db.flush()
            for item in sorted(generated_history_rows, key=lambda row: row.created_at or datetime.utcnow(), reverse=True):
                history_by_client.setdefault(item.entidad_id, [])
                if len(history_by_client[item.entidad_id]) < 60:
                    history_by_client[item.entidad_id].append(item)
                if item.entidad_id not in latest_history_by_client and item.accion != "CALLBACK_PROGRAMADO":
                    latest_history_by_client[item.entidad_id] = item
            db.commit()

    client_rows: list[CollectorClientRead] = []
    total_outstanding = 0.0
    strategy_summary: dict[str, int] = {}
    hmr_candidates = 0
    scheduled_callbacks_today = 0
    supervisor_reviews_pending = 0

    for client in assigned_clients:
        accounts = accounts_by_client.get(client.id, [])
        assignment_snapshot = current_assignment_by_client.get(client.id)
        contextual_accounts = select_accounts_for_operational_context(accounts, assignment_snapshot, datetime.utcnow())
        account_rows = []
        strategy_context = derive_client_strategy_context(contextual_accounts, datetime.utcnow())
        primary_strategy = (
            assignment_snapshot.strategy_code
            if assignment_snapshot and assignment_snapshot.strategy_code == "VAGENCIASEXTERNASINTERNO"
            else strategy_context["primary_strategy"]
        )
        client_hmr = False
        client_total = 0.0
        for account in contextual_accounts:
            cycle_cut_day = get_cycle_cut_day(account)
            due_day = get_due_day(cycle_cut_day)
            strategy = resolve_strategy(account, datetime.utcnow())
            account_display = derive_account_display_metadata(account)
            hmr = is_hmr_candidate(account)
            prediction = predictions_by_account.get(account.id)
            if prediction:
                ai_probability = float(prediction.probabilidad_pago_30d)
                ai_score = float(prediction.score_modelo)
                ai_recommendation = prediction.recomendacion
            else:
                ai_probability, ai_score, ai_recommendation = build_ai_fallback(account)
            client_hmr = client_hmr or hmr
            client_total += float(account.saldo_total)
            account_rows.append(
                CollectorAccountRead(
                    id=account.id,
                    numero_cuenta=account.numero_cuenta,
                    numero_plastico=account_display["plastic_number"],
                    codigo_ubicacion=account_display["location_code"],
                    tipo_producto=account.tipo_producto,
                    producto_nombre=account_display["product_name"],
                    subtipo_producto=account.subtipo_producto,
                    segmento_producto=account_display["product_segment"],
                    estado=account.estado,
                    saldo_total=float(account.saldo_total),
                    saldo_mora=float(account.saldo_mora),
                    dias_mora=account.dias_mora,
                    bucket_actual=account.bucket_actual,
                    es_estrafinanciamiento=account.es_estrafinanciamiento,
                    ciclo_corte=cycle_cut_day,
                    dia_vencimiento=due_day,
                    estrategia=strategy,
                    hmr_elegible=hmr,
                    pago_minimo=calculate_minimum_payment(account),
                    ai_probability=round(ai_probability, 4),
                    ai_score=round(ai_score, 2),
                    ai_recommendation=ai_recommendation,
                )
            )
        total_outstanding += client_total
        strategy_summary[primary_strategy] = strategy_summary.get(primary_strategy, 0) + 1
        if client_hmr:
            hmr_candidates += 1
        pending_promises = pending_promises_by_client.get(client.id, [])
        latest_history = latest_history_by_client.get(client.id)
        callback_history = callback_history_by_client.get(client.id)
        callback_at, _ = parse_callback_description(callback_history.descripcion if callback_history else None)
        if callback_at and callback_at.date() == today:
            scheduled_callbacks_today += 1
        review_pending = any(item.estado == "REVISION_SUPERVISOR" for item in pending_promises)
        if review_pending:
            supervisor_reviews_pending += 1
        actual_management_history = [
            ManagementHistoryRead(
                id=item.id,
                fecha=item.created_at.isoformat() if item.created_at else "",
                accion=item.accion,
                descripcion=item.descripcion,
                usuario_id=item.usuario_id,
            )
            for item in history_by_client.get(client.id, [])
        ]
        derived_management_history = synthetic_history_by_client.get(client.id, [])
        if not actual_management_history:
            derived_management_history = [
                *derived_management_history,
                *[
                    ManagementHistoryRead(
                        id=-(400000000 + account.id),
                        fecha=(account.created_at or datetime.utcnow()).isoformat(),
                        accion="CUENTA_EN_SEGUIMIENTO",
                        descripcion=(
                            f"Cuenta {account.numero_cuenta} en {resolve_strategy(account, datetime.utcnow())} "
                            f"con {account.dias_mora} dias de mora y saldo vencido de {float(account.saldo_mora):,.2f}."
                        ),
                        usuario_id=None,
                    )
                    for account in accounts[:3]
                ],
            ]
        management_history = sorted(
            [*actual_management_history, *derived_management_history],
            key=lambda item: item.fecha or "",
            reverse=True,
        )[:60]
        last_management_text = latest_history.descripcion if latest_history else (management_history[0].descripcion if management_history else None)
        lead_account = next((item for item in account_rows if strategy_context["lead_account"] and item.id == strategy_context["lead_account"].id), account_rows[0] if account_rows else None)
        ai_probability = float(lead_account.ai_probability if lead_account and lead_account.ai_probability is not None else client.score_riesgo)
        promise_break_probability = (
            predict_promise_break_probability(strategy_context["lead_account"] or accounts[0], pending_promises, callback_at, float(client.score_riesgo))
            if accounts
            else float(np.clip(float(client.score_riesgo) * 0.65, 0.08, 0.9))
        )
        best_channel = suggest_best_channel(
            primary_strategy,
            promise_break_probability,
            ai_probability,
            bool(client.telefono),
            bool(client.email),
        )
        sublista_trabajo, sublista_descripcion = derive_worklist_sublist(
            client,
            accounts,
            pending_promises,
            callback_at,
            review_pending,
        )
        if primary_strategy == "VAGENCIASEXTERNASINTERNO" and assignment_snapshot and assignment_snapshot.group_id:
            sublista_trabajo = assignment_snapshot.group_id
            sublista_descripcion = (
                f"{assignment_snapshot.channel_scope or 'MIXTO'} · "
                f"{assignment_snapshot.placement_code or 'SIN PLACEMENT'} · "
                f"Lista {assignment_snapshot.group_id}"
            )
        ai_next_action, ai_talk_track = build_copilot_guidance(
            client,
            primary_strategy,
            best_channel,
            promise_break_probability,
            ai_probability,
            pending_promises,
            round(client_total, 2),
        )
        client_rows.append(
            CollectorClientRead(
                id=client.id,
                identity_code=format_identity_code(client.identity_code, client.id),
                dui=client.dui,
                nombres=client.nombres,
                apellidos=client.apellidos,
                telefono=client.telefono,
                email=client.email,
                direccion=client.direccion,
                segmento=client.segmento,
                score_riesgo=float(client.score_riesgo),
                accounts=account_rows,
                pending_promises=[
                    PromiseRead(
                        id=item.id,
                        cuenta_id=item.cuenta_id,
                        fecha_promesa=item.fecha_promesa.isoformat(),
                        monto_prometido=float(item.monto_prometido),
                        estado=item.estado,
                    )
                    for item in pending_promises
                ],
                last_management=last_management_text,
                worked_today=client.id in worked_today_ids,
                estrategia_principal=primary_strategy,
                estrategia_subgrupo=strategy_context["strategy_subgroup"],
                segmento_operativo=strategy_context["operational_segment"],
                producto_cabeza=strategy_context["head_product_name"],
                dias_mora_cabeza=strategy_context["head_days_past_due"],
                hmr_elegible=client_hmr,
                total_outstanding=round(client_total, 2),
                next_callback_at=callback_at.isoformat() if callback_at else None,
                requires_supervisor_review=review_pending,
                management_history=management_history,
                ai_best_channel=best_channel,
                ai_promise_break_probability=round(promise_break_probability, 4),
                ai_next_action=ai_next_action,
                ai_talk_track=ai_talk_track,
                placement_code=assignment_snapshot.placement_code if assignment_snapshot else None,
                group_id=assignment_snapshot.group_id if assignment_snapshot else None,
                sublista_trabajo=sublista_trabajo,
                sublista_descripcion=sublista_descripcion,
            )
        )

    due_promises_today = 0
    if assigned_client_ids:
        due_promises_today = (
            db.query(Promesa)
            .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
            .filter(Cuenta.cliente_id.in_(assigned_client_ids), Promesa.fecha_promesa == today, Promesa.estado == "PENDIENTE")
            .count()
        )

    metrics = CollectorMetrics(
        assigned_today=len(client_rows),
        remaining_today=max(0, len(client_rows) - len(worked_today_ids)),
        worked_today=len(worked_today_ids),
        payment_agreements_today=len(promises_today),
        due_promises_today=due_promises_today,
        total_outstanding=round(total_outstanding, 2),
        hmr_candidates=hmr_candidates,
        strategy_summary=strategy_summary,
        scheduled_callbacks_today=scheduled_callbacks_today,
        supervisor_reviews_pending=supervisor_reviews_pending,
    )

    return CollectorPortfolioResponse(
        collector=UserRead.model_validate(current_user),
        metrics=metrics,
        clients=client_rows,
    )


@app.get("/collector/portfolio/me", response_model=CollectorPortfolioResponse)
def get_collector_portfolio(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Collector")),
):
    return build_collector_portfolio_response(db, current_user)


@app.get("/admin/collector-portfolio/{collector_id}", response_model=CollectorPortfolioResponse)
def get_admin_collector_portfolio(
    collector_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    collector = (
        db.query(Usuario)
        .filter(Usuario.id == collector_id, Usuario.rol == "Collector", Usuario.activo.is_(True))
        .first()
    )
    if not collector:
        raise HTTPException(status_code=404, detail="Collector no encontrado.")
    return build_collector_portfolio_response(db, collector)


@app.get("/supervisor/collector-portfolio/{collector_id}", response_model=CollectorPortfolioResponse)
def get_supervisor_collector_portfolio(
    collector_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Supervisor")),
):
    collector = (
        db.query(Usuario)
        .filter(Usuario.id == collector_id, Usuario.rol == "Collector", Usuario.activo.is_(True))
        .first()
    )
    if not collector:
        raise HTTPException(status_code=404, detail="Collector no encontrado.")
    allowed_collectors = {item.id for item in get_collectors_for_supervisor(db, current_user)}
    if collector.id not in allowed_collectors:
        raise HTTPException(status_code=403, detail="Ese collector no pertenece a tu equipo.")
    return build_collector_portfolio_response(db, collector)


@app.get("/supervisor/overview/me", response_model=SupervisorOverviewResponse)
def get_supervisor_overview(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Supervisor")),
):
    today = datetime.utcnow().date()
    start_of_day = get_start_of_day(today)
    assigned_collectors = get_collectors_for_supervisor(db, current_user)
    collector_metrics: list[SupervisorCollectorMetric] = []

    total_managed_today = 0
    total_payment_agreements = 0
    total_recovered_balance = 0.0
    review_queue: list[dict] = []
    alerts: list[dict] = []

    for collector in assigned_collectors:
        assigned_clients = get_assigned_clients_for_collector(db, collector)
        histories = (
            db.query(History)
            .filter(
                History.usuario_id == collector.id,
                History.entidad == "clientes",
                History.created_at >= start_of_day,
                History.accion.in_(["GESTION_REGISTRADA", "PROMESA_CREADA", "CLIENTE_ACTUALIZADO"]),
            )
            .all()
        )
        managed_today = len({item.entidad_id for item in histories})
        agreements_today = (
            db.query(Promesa)
            .filter(Promesa.usuario_id == collector.id, Promesa.created_at >= start_of_day)
            .all()
        )
        collector_promises = db.query(Promesa).filter(Promesa.usuario_id == collector.id, Promesa.estado.in_(["PENDIENTE", "REVISION_SUPERVISOR"])).all()
        review_promises = [item for item in agreements_today if item.estado == "REVISION_SUPERVISOR"]
        recovered_balance_today = round(sum(float(item.monto_prometido or 0) for item in agreements_today), 2)

        total_managed_today += managed_today
        total_payment_agreements += len(agreements_today)
        total_recovered_balance += recovered_balance_today

        collector_metrics.append(
            SupervisorCollectorMetric(
                user=UserRead.model_validate(collector),
                assigned_clients=len(assigned_clients),
                managed_today=managed_today,
                payment_agreements_today=len(agreements_today),
                recovered_balance_today=recovered_balance_today,
            )
        )

        for promise in review_promises:
            account = db.get(Cuenta, promise.cuenta_id)
            if not account:
                continue
            client = db.get(Cliente, account.cliente_id)
            if not client:
                continue
            review_queue.append(
                {
                    "promise_id": promise.id,
                    "collector_name": collector.nombre,
                    "collector_username": collector.username,
                    "client_id": client.id,
                    "client_name": f"{client.nombres} {client.apellidos}",
                    "account_number": account.numero_cuenta,
                    "scheduled_date": promise.fecha_promesa.isoformat(),
                    "agreed_amount": float(promise.monto_prometido),
                    "minimum_amount": calculate_minimum_payment(account),
                }
            )

        for promise in collector_promises:
            if (promise.fecha_promesa - today).days <= 10:
                continue
            account = db.get(Cuenta, promise.cuenta_id)
            if not account:
                continue
            client = db.get(Cliente, account.cliente_id)
            if not client:
                continue
            alerts.append(
                {
                    "promise_id": promise.id,
                    "collector_name": collector.nombre,
                    "client_name": f"{client.nombres} {client.apellidos}",
                    "account_number": account.numero_cuenta,
                    "scheduled_date": promise.fecha_promesa.isoformat(),
                    "days_out": (promise.fecha_promesa - today).days,
                    "status": promise.estado,
                }
            )

    return SupervisorOverviewResponse(
        supervisor=UserRead.model_validate(current_user),
        team_size=len(assigned_collectors),
        managed_today=total_managed_today,
        payment_agreements_today=total_payment_agreements,
        recovered_balance_today=round(total_recovered_balance, 2),
        collectors=collector_metrics,
        review_queue=review_queue,
        alerts=alerts,
    )


@app.post("/supervisor/reviews/{promise_id}/approve")
def approve_supervisor_review(
    promise_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Supervisor")),
):
    promise = db.get(Promesa, promise_id)
    if not promise:
        raise HTTPException(status_code=404, detail="Promesa no encontrada.")
    if promise.estado != "REVISION_SUPERVISOR":
        raise HTTPException(status_code=400, detail="La promesa no esta en revision supervisor.")

    collector = db.get(Usuario, promise.usuario_id) if promise.usuario_id else None
    assigned_collectors = {item.id for item in get_collectors_for_supervisor(db, current_user)}
    if collector and collector.id not in assigned_collectors:
        raise HTTPException(status_code=403, detail="La promesa no pertenece a un gestor asignado a este supervisor.")

    promise.estado = "PENDIENTE"
    db.add(
        History(
            entidad="promesas",
            entidad_id=promise.id,
            accion="SUPERVISOR_APPROVED",
            descripcion=f"Promesa aprobada por supervisor {current_user.username} y devuelta a estado PENDIENTE.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": "Promesa revisada y actualizada a PENDIENTE.", "promise_id": promise.id, "estado": promise.estado}


@app.post("/collector/managements", status_code=201)
def create_collector_management(
    payload: CollectorManagementCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Collector")),
):
    assigned_ids = {client.id for client in get_assigned_clients_for_collector(db, current_user)}
    if payload.client_id not in assigned_ids:
        raise HTTPException(status_code=403, detail="El cliente no pertenece a tu cartera asignada.")

    target_account_ids = sorted(set([payload.account_id, *payload.account_ids]))
    accounts = db.query(Cuenta).filter(Cuenta.id.in_(target_account_ids), Cuenta.cliente_id == payload.client_id).all()
    if len(accounts) != len(target_account_ids):
        raise HTTPException(status_code=404, detail="Una o mas cuentas no pertenecen al cliente seleccionado.")

    primary_account = next((account for account in accounts if account.id == payload.account_id), accounts[0])
    minimum_payment = sum(calculate_minimum_payment(account) for account in accounts)
    exceeds_business_day_limit = False
    if payload.promise_date:
        max_promise_date = add_business_days(datetime.utcnow().date(), 5)
        exceeds_business_day_limit = payload.promise_date.date() > max_promise_date
    requires_supervisor_review = bool(
        (payload.promise_amount is not None and payload.promise_date and payload.promise_amount < minimum_payment)
        or exceeds_business_day_limit
    )
    current_timestamp = datetime.now(timezone.utc)

    selected_accounts_text = ", ".join(account.numero_cuenta for account in accounts)
    called_phone_text = payload.called_phone or "No especificado"
    rdm_text = payload.rdm or "No especificada"
    description = (
        f"{payload.management_type} | Resultado: {payload.result} | Canal: {payload.contact_channel} "
        f"| Telefono llamado: {called_phone_text} | RDM: {rdm_text} | Cuentas: {selected_accounts_text} | Notas de gestion: {payload.notes}"
    )
    history = History(
        entidad="clientes",
        entidad_id=payload.client_id,
        accion="REVISION_SUPERVISOR" if requires_supervisor_review else ("PROMESA_CREADA" if payload.promise_amount and payload.promise_date else "GESTION_REGISTRADA"),
        descripcion=(
            f"{description} | Revision supervisor requerida por condiciones fuera de politica. "
            f"Minimo sugerido: {minimum_payment:.2f}. Excede 5 dias habiles: {'Si' if exceeds_business_day_limit else 'No'}."
            if requires_supervisor_review
            else description
        ),
        usuario_id=current_user.id,
        created_at=current_timestamp,
    )
    db.add(history)

    promises_created = []
    if payload.promise_amount and payload.promise_date:
        total_minimum = max(minimum_payment, 0.01)
        for account in accounts:
            account_minimum = calculate_minimum_payment(account)
            allocated_amount = round(float(payload.promise_amount) * (account_minimum / total_minimum), 2)
            promise = Promesa(
                cuenta_id=account.id,
                usuario_id=current_user.id,
                fecha_promesa=payload.promise_date.date(),
                monto_prometido=allocated_amount,
                estado="REVISION_SUPERVISOR" if requires_supervisor_review else "PENDIENTE",
                created_at=current_timestamp,
            )
            db.add(promise)
            promises_created.append(promise)

    if payload.callback_at:
        db.add(
            History(
                entidad="clientes",
                entidad_id=payload.client_id,
                accion="CALLBACK_PROGRAMADO",
                descripcion=json.dumps(
                    {
                        "callback_at": payload.callback_at.isoformat(),
                        "notes": payload.notes,
                        "called_phone": called_phone_text,
                        "account_id": primary_account.id,
                        "account_ids": target_account_ids,
                    }
                ),
                usuario_id=current_user.id,
                created_at=current_timestamp,
            )
        )

    db.commit()
    return {
        "message": "Gestion registrada correctamente.",
        "agreement_created": bool(promises_created),
        "accounts_included": len(accounts),
        "requires_supervisor_review": requires_supervisor_review,
    }


@app.get("/collector/clients/{client_id}/demographics", response_model=DemographicProfileRead)
def get_collector_client_demographics(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Collector", "Supervisor", "Admin")),
):
    if current_user.rol == "Collector":
        assigned_ids = {client.id for client in get_assigned_clients_for_collector(db, current_user)}
        if client_id not in assigned_ids:
            raise HTTPException(status_code=403, detail="El cliente no pertenece a tu cartera asignada.")

    client = db.get(Cliente, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    return get_client_demographic_profile(db, client)


@app.put("/collector/clients/{client_id}/demographics", response_model=DemographicProfileRead)
def update_collector_client_demographics(
    client_id: int,
    payload: DemographicUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Collector", "Supervisor", "Admin")),
):
    if current_user.rol == "Collector":
        assigned_ids = {client.id for client in get_assigned_clients_for_collector(db, current_user)}
        if client_id not in assigned_ids:
            raise HTTPException(status_code=403, detail="El cliente no pertenece a tu cartera asignada.")

    client = db.get(Cliente, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    profile = save_client_demographic_profile(db, client, payload, current_user)
    db.commit()
    db.refresh(client)
    return profile


@app.get("/admin/overview", response_model=AdminOverviewResponse)
def get_admin_overview(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    strategies = db.query(Strategy).filter(Strategy.activa.is_(True)).order_by(Strategy.orden, Strategy.codigo).all()
    collectors = db.query(Usuario).filter(Usuario.activo.is_(True), Usuario.rol == "Collector").order_by(Usuario.id).all()
    supervisors = db.query(Usuario).filter(Usuario.activo.is_(True), Usuario.rol == "Supervisor").order_by(Usuario.id).all()
    total_clients = db.query(Cliente).count()
    assigned_clients = db.query(WorklistAssignment.cliente_id).filter(WorklistAssignment.activa.is_(True)).distinct().count()
    hmr_clients = (
        db.query(Cuenta.cliente_id)
        .filter((Cuenta.es_estrafinanciamiento.is_(True)) | ((Cuenta.dias_mora >= 31) & (Cuenta.dias_mora <= 180) & (Cuenta.saldo_total >= 900)))
        .distinct()
        .count()
    )
    omnichannel = build_admin_omnichannel_overview(db)
    return AdminOverviewResponse(
        strategies=[StrategyRead.model_validate(item) for item in strategies],
        collectors=[UserRead.model_validate(item) for item in collectors],
        supervisors=[UserRead.model_validate(item) for item in supervisors],
        total_clients=total_clients,
        assigned_clients=assigned_clients,
        unassigned_clients=max(0, total_clients - assigned_clients),
        hmr_clients=hmr_clients,
        omnichannel=omnichannel,
        alerts=build_admin_alerts(
            db,
            total_clients=total_clients,
            assigned_clients=assigned_clients,
            omnichannel_overview=omnichannel,
        ),
    )


@app.get("/admin/recovery-vintage", response_model=RecoveryVintageOverviewResponse)
def get_admin_recovery_vintage(
    year: int = Query(..., ge=2000, le=2100),
    lookback_days: int = Query(default=120, ge=30, le=365),
    payment_threshold: float = Query(default=10.0, ge=1, le=5000),
    sample_limit: int = Query(default=20000, ge=10, le=100000),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    return build_recovery_vintage_overview(
        db,
        year=year,
        lookback_days=lookback_days,
        payment_threshold=payment_threshold,
        sample_limit=sample_limit,
    )


@app.get("/admin/recovery-vintage/export")
def export_admin_recovery_vintage(
    year: int = Query(..., ge=2000, le=2100),
    lookback_days: int = Query(default=120, ge=30, le=365),
    payment_threshold: float = Query(default=10.0, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    overview = build_recovery_vintage_overview(
        db,
        year=year,
        lookback_days=lookback_days,
        payment_threshold=payment_threshold,
        sample_limit=100000,
    )

    placement_rows = [
        {
            "placement_code": placement.placement_code,
            "client_count": placement.client_count,
            "paying_clients_120d": placement.paying_clients_120d,
            "payment_rate_120d": round((placement.paying_clients_120d / placement.client_count) * 100, 1) if placement.client_count else 0,
            "total_paid_120d": placement.total_paid_120d,
            "v11_eligible_clients": placement.v11_eligible_clients,
            "best_group_id": placement.best_group_id,
            "best_group_rate_120d": placement.best_group_rate_120d,
            "lagging_group_id": placement.lagging_group_id,
            "lagging_group_rate_120d": placement.lagging_group_rate_120d,
        }
        for placement in overview.placements
    ]
    agency_rows = [
        {
            "placement_code": placement.placement_code,
            "group_id": agency.group_id,
            "channel_scope": agency.channel_scope,
            "client_count": agency.client_count,
            "paying_clients_120d": agency.paying_clients_120d,
            "payment_rate_120d": agency.payment_rate_120d,
            "total_paid_120d": agency.total_paid_120d,
            "v11_eligible_clients": agency.v11_eligible_clients,
        }
        for placement in overview.placements
        for agency in placement.agencies
    ]
    client_rows = [
        {
            "identity_code": client.identity_code,
            "client_name": client.client_name,
            "separation_date": client.separation_date,
            "current_status": client.current_status,
            "current_placement": client.current_placement,
            "current_group_id": client.current_group_id,
            "current_scope": client.current_scope,
            "account_count": client.account_count,
            "qualifying_payment_count_120d": client.qualifying_payment_count_120d,
            "total_paid_120d": client.total_paid_120d,
            "max_payment_120d": client.max_payment_120d,
            "last_payment_date": client.last_payment_date,
            "movement_path": client.movement_path,
            "qualifies_for_v11": client.qualifies_for_v11,
        }
        for client in overview.sample_clients
    ]

    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                {
                    "year": overview.year,
                    "lookback_days": overview.lookback_days,
                    "payment_threshold": overview.payment_threshold,
                    "total_clients": overview.total_clients,
                    "active_payers_120d": overview.active_payers_120d,
                    "v11_clients": overview.v11_clients,
                    "placements_tracked": overview.placements_tracked,
                }
            ]
        ).to_excel(writer, index=False, sheet_name="Resumen")
        pd.DataFrame(placement_rows).to_excel(writer, index=False, sheet_name="Placements")
        pd.DataFrame(agency_rows).to_excel(writer, index=False, sheet_name="Agencias")
        pd.DataFrame(client_rows).to_excel(writer, index=False, sheet_name="Clientes")
    workbook.seek(0)

    return StreamingResponse(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="recovery_cosecha_{year}.xlsx"'},
    )


@app.get("/admin/recovery-vintage/executive-export")
def export_admin_recovery_vintage_executive_dashboard(
    year: int = Query(..., ge=2000, le=2100),
    compare_years: str = Query(default=""),
    lookback_days: int = Query(default=120, ge=30, le=365),
    payment_threshold: float = Query(default=10.0, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    overview = build_recovery_vintage_overview(
        db,
        year=year,
        lookback_days=lookback_days,
        payment_threshold=payment_threshold,
        sample_limit=100000,
    )

    parsed_compare_years = [int(value.strip()) for value in (compare_years or "").split(",") if value.strip().isdigit()]
    compare_response = build_recovery_vintage_compare(
        db,
        years=parsed_compare_years or [year, max(RECOVERY_VINTAGE_START_YEAR, year - 1)],
        lookback_days=lookback_days,
        payment_threshold=payment_threshold,
    )

    placements = overview.placements or []
    total_recovered = round(sum(float(item.total_paid_120d or 0) for item in placements), 2)
    placement_leader = max(placements, key=lambda item: float(item.total_paid_120d or 0), default=None)
    placement_laggard = min(placements, key=lambda item: float(item.total_paid_120d or 0), default=None)
    best_vintage = max(
        compare_response.items,
        key=lambda item: (float(item.active_payers_120d or 0) / max(float(item.total_clients or 1), 1)),
        default=None,
    )

    executive_rows = [
        {"indicador": "Cosecha analizada", "valor": year},
        {"indicador": "Clientes separados", "valor": overview.total_clients},
        {"indicador": f"Clientes con pago >= USD {payment_threshold:.2f} / {lookback_days} días", "valor": overview.active_payers_120d},
        {"indicador": "Clientes hoy en V11", "valor": overview.v11_clients},
        {"indicador": "Placements activos", "valor": overview.placements_tracked},
        {"indicador": "Monto recuperado visible", "valor": total_recovered},
        {"indicador": "Placement líder", "valor": placement_leader.placement_code if placement_leader else "N/D"},
        {"indicador": "Placement rezagado", "valor": placement_laggard.placement_code if placement_laggard else "N/D"},
        {"indicador": "Mejor añada comparada", "valor": best_vintage.year if best_vintage else "N/D"},
    ]

    placement_rows = [
        {
            "placement_code": placement.placement_code,
            "client_count": placement.client_count,
            "paying_clients_120d": placement.paying_clients_120d,
            "payment_rate_120d": round((placement.paying_clients_120d / placement.client_count) * 100, 1) if placement.client_count else 0,
            "total_paid_120d": float(placement.total_paid_120d or 0),
            "v11_eligible_clients": placement.v11_eligible_clients,
            "best_group_id": placement.best_group_id,
            "lagging_group_id": placement.lagging_group_id,
        }
        for placement in placements
    ]

    compare_rows = [
        {
            "year": item.year,
            "total_clients": item.total_clients,
            "active_payers_120d": item.active_payers_120d,
            "payment_rate_120d": round((item.active_payers_120d / item.total_clients) * 100, 1) if item.total_clients else 0,
            "placements_tracked": item.placements_tracked,
            "placement_distribution": ", ".join(f"{code}: {count}" for code, count in (item.placement_distribution or {}).items()),
        }
        for item in compare_response.items
    ]

    client_rows = [
        {
            "identity_code": client.identity_code,
            "client_name": client.client_name,
            "separation_date": client.separation_date,
            "current_placement": client.current_placement,
            "current_group_id": client.current_group_id,
            "total_paid_120d": float(client.total_paid_120d or 0),
            "qualifying_payment_count_120d": client.qualifying_payment_count_120d,
            "movement_path": client.movement_path,
        }
        for client in overview.sample_clients
    ]

    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame(executive_rows).to_excel(writer, index=False, sheet_name="Resumen Ejecutivo")
        pd.DataFrame(placement_rows).to_excel(writer, index=False, sheet_name="Placement Recovery")
        pd.DataFrame(compare_rows).to_excel(writer, index=False, sheet_name="Comparativo Añadas")
        pd.DataFrame(client_rows).to_excel(writer, index=False, sheet_name="Muestra Clientes")
    workbook.seek(0)

    return StreamingResponse(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="dashboard_recovery_cosecha_{year}.xlsx"'},
    )


@app.get("/admin/recovery-vintage/compare", response_model=RecoveryVintageCompareResponse)
def compare_admin_recovery_vintage(
    years: str = Query(..., description="Lista de años separada por comas"),
    lookback_days: int = Query(default=120, ge=30, le=365),
    payment_threshold: float = Query(default=10.0, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    parsed_years = [int(value.strip()) for value in years.split(",") if value.strip().isdigit()]
    if not parsed_years:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un año válido para comparar.")
    return build_recovery_vintage_compare(
        db,
        years=parsed_years,
        lookback_days=lookback_days,
        payment_threshold=payment_threshold,
    )


@app.get("/admin/executive-log", response_model=list[AdminHistoryEventRead])
def get_admin_executive_log(
    limit: int = Query(default=80, ge=10, le=200),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    return build_admin_executive_log(db, limit=limit)


def find_user_by_identifier(db: Session, raw_identifier: str) -> Optional[Usuario]:
    identifier = (raw_identifier or "").strip()
    if not identifier:
        return None
    lowered = identifier.lower()
    return (
        db.query(Usuario)
        .filter(
            (func.lower(Usuario.username) == lowered)
            | (func.lower(Usuario.nombre) == lowered)
            | (func.lower(func.replace(Usuario.nombre, " ", "")) == lowered.replace(" ", ""))
        )
        .first()
    )


def normalize_admin_assistant_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def validate_admin_sql_query(raw_query: str) -> str:
    normalized = (raw_query or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="La consulta no puede estar vacía.")
    compact = re.sub(r"\s+", " ", normalized).strip()
    lowered = compact.lower()
    if ";" in compact.rstrip(";"):
        raise HTTPException(status_code=400, detail="Solo se permite una sentencia por consulta.")
    blocked_tokens = [
        "insert ", "update ", "delete ", "drop ", "alter ", "truncate ", "create ",
        "grant ", "revoke ", "comment ", "vacuum ", "analyze ", "refresh ",
        "merge ", "call ", "copy ", "set ", "reset ", "begin", "commit", "rollback",
        "lock ", "do ", "execute ", "prepare ", "deallocate ", "listen ", "notify ",
        "pg_sleep", "dblink", "postgres_fdw",
    ]
    if any(token in lowered for token in blocked_tokens):
        raise HTTPException(status_code=400, detail="Solo se permiten consultas SQL de lectura.")
    if not (lowered.startswith("select ") or lowered.startswith("with ") or lowered.startswith("explain select ") or lowered.startswith("explain with ")):
        raise HTTPException(status_code=400, detail="La consulta debe iniciar con SELECT, WITH o EXPLAIN.")
    return compact.rstrip(";")


def build_daily_operational_simulation_preview(
    db: Session,
    fmora1_clients: int = 250,
    preventivo_clients: int = 120,
    recovery_clients: int = 1000,
) -> dict[str, Any]:
    today = date.today()
    simulation_key = f"SIM-DAY-{today.isoformat()}"
    already_applied_today = (
        db.query(History)
        .filter(
            History.entidad == "system",
            History.accion == "SIMULACION_DIA_OPERATIVO",
            History.descripcion.ilike(f"%{simulation_key}%"),
        )
        .first()
        is not None
    )
    aged_accounts = db.query(Cuenta).filter(
        Cuenta.dias_mora > 0,
        Cuenta.estado.in_(["ACTIVA", "VIGENTE", "LIQUIDADO", "Z"]),
    ).count()
    payable_accounts = (
        db.query(Cuenta.id, Cuenta.saldo_total)
        .filter(Cuenta.dias_mora > 0, Cuenta.saldo_total > 0, Cuenta.estado.in_(["ACTIVA", "VIGENTE", "LIQUIDADO", "Z"]))
        .order_by(Cuenta.id.asc())
        .all()
    )
    simulated_payments = 0
    fully_cured_accounts = 0
    for index, account in enumerate(payable_accounts, start=1):
        if index % 11 == 0 or index % 7 == 0 or index % 5 == 0:
            simulated_payments += 1
        if index % 11 == 0 and float(account.saldo_total or 0) > 0:
            fully_cured_accounts += 1

    recovery_rotations = (
        db.query(WorklistAssignment.cliente_id)
        .join(Cuenta, Cuenta.cliente_id == WorklistAssignment.cliente_id)
        .filter(
            WorklistAssignment.activa.is_(True),
            Cuenta.dias_mora > 180,
            Cuenta.estado.in_(["LIQUIDADO", "Z"]),
        )
        .distinct()
        .count()
    )

    total_clients = db.query(Cliente).count()
    total_accounts = db.query(Cuenta).count()
    warnings: list[str] = []
    if already_applied_today:
        warnings.append("La simulación del día ya fue aplicada previamente. Si deseas volver a correrla, primero tendrás que habilitar una ejecución forzada.")
    if recovery_clients > 2500:
        warnings.append("La carga Recovery solicitada es alta; conviene revisar placement y asignaciones antes de aplicarla.")
    if simulated_payments > max(2000, aged_accounts * 0.35):
        warnings.append("El volumen proyectado de pagos es relevante; úsalo para validar campañas y movimientos de estrategia antes de ejecutar.")

    return {
        "simulation_key": simulation_key,
        "already_applied_today": already_applied_today,
        "aged_accounts": aged_accounts,
        "inserted_fmora1_clients": fmora1_clients,
        "inserted_preventivo_clients": preventivo_clients,
        "inserted_recovery_clients": recovery_clients,
        "simulated_payments": simulated_payments,
        "fully_cured_accounts": fully_cured_accounts,
        "recovery_rotations": recovery_rotations,
        "projected_total_clients": total_clients + fmora1_clients + preventivo_clients + recovery_clients,
        "projected_total_accounts": total_accounts + fmora1_clients + preventivo_clients + recovery_clients,
        "warnings": warnings,
        "message": "Previsualización generada. No se modificó ninguna tabla ni se aplicó ningún movimiento en la base.",
    }


def build_recovery_vintage_compare(
    db: Session,
    years: list[int],
    lookback_days: int = 120,
    payment_threshold: float = 10.0,
) -> RecoveryVintageCompareResponse:
    unique_years = sorted({int(year) for year in years if RECOVERY_VINTAGE_START_YEAR <= int(year) <= 2100}, reverse=True)
    items: list[RecoveryVintageCompareItem] = []
    for year in unique_years:
        overview = build_recovery_vintage_overview(
            db,
            year=year,
            lookback_days=lookback_days,
            payment_threshold=payment_threshold,
            sample_limit=2000,
        )
        items.append(
            RecoveryVintageCompareItem(
                year=year,
                total_clients=overview.total_clients,
                total_balance=overview.total_balance,
                total_due=overview.total_due,
                active_payers_120d=overview.active_payers_120d,
                placements_tracked=overview.placements_tracked,
                placement_distribution={placement.placement_code: placement.client_count for placement in overview.placements},
            )
        )
    return RecoveryVintageCompareResponse(years=unique_years, items=items)


def build_admin_executive_log(db: Session, limit: int = 80) -> list[AdminHistoryEventRead]:
    rows = (
        db.query(History, Usuario.nombre)
        .outerjoin(Usuario, Usuario.id == History.usuario_id)
        .filter(
            History.accion.in_(
                [
                    "SIMULACION_DIA_OPERATIVO",
                    "OMNICHANNEL_CONFIG_UPDATED",
                    "EMAIL_DEMO_SENT",
                    "SMS_DEMO_SENT",
                    "WHATSAPP_DEMO_SENT",
                    "CALLBOT_DEMO_SENT",
                    "WORKLIST_GROUP_ASSIGNED",
                    "WORKLIST_GROUP_UNASSIGNED",
                    "SUPERVISOR_ASSIGNMENT_CREATED",
                    "SUPERVISOR_ASSIGNMENT_REMOVED",
                    "DEMOGRAFIA_ACTUALIZADA",
                ]
            )
        )
        .order_by(History.created_at.desc(), History.id.desc())
        .limit(limit)
        .all()
    )
    return [
        AdminHistoryEventRead(
            id=history.id,
            entidad=history.entidad,
            entidad_id=history.entidad_id,
            accion=history.accion,
            descripcion=history.descripcion,
            usuario_id=history.usuario_id,
            usuario_nombre=user_name,
            created_at=history.created_at,
        )
        for history, user_name in rows
    ]


def resolve_omnichannel_client_context(
    db: Session,
    client_id: Optional[int],
    requested_strategy_code: Optional[str],
) -> dict[str, Any]:
    client = db.get(Cliente, client_id) if client_id else None
    strategy_code = (requested_strategy_code or "").upper() or "FMORA1"
    client_name = "Cliente"
    total_due = 0.0
    minimum_payment = 0.0
    account_reference = "sin referencia"
    account_last4 = "****"
    today = datetime.utcnow().date()
    due_date = today + timedelta(days=5)

    if client:
        client_name = f"{client.nombres} {client.apellidos}"
        accounts = (
            db.query(Cuenta)
            .filter(Cuenta.cliente_id == client.id)
            .order_by(Cuenta.dias_mora.desc(), Cuenta.id.asc())
            .all()
        )
        if accounts:
            strategy_context = derive_client_strategy_context(accounts, datetime.utcnow())
            lead_account = strategy_context["lead_account"] or accounts[0]
            strategy_code = strategy_context["primary_strategy"] or strategy_code
            total_due = round(float(lead_account.saldo_mora or 0), 2)
            minimum_payment = round(float(calculate_minimum_payment(lead_account) or 0), 2)
            account_reference = lead_account.numero_cuenta or "sin referencia"
            account_last4 = account_reference[-4:] if account_reference and account_reference != "sin referencia" else "****"
            if lead_account.fecha_vencimiento and lead_account.fecha_vencimiento >= today:
                due_date = lead_account.fecha_vencimiento

    return {
        "client": client,
        "strategy_code": strategy_code,
        "client_name": client_name,
        "total_due": total_due,
        "minimum_payment": minimum_payment,
        "account_reference": account_reference,
        "account_last4": account_last4,
        "due_date_str": due_date.strftime("%d/%m/%Y"),
    }


def parse_admin_assistant_message(message: str) -> dict[str, Any]:
    raw = (message or "").strip()
    normalized = normalize_admin_assistant_text(raw)
    explain_only = any(
        token in normalized
        for token in [
            "explicame",
            "explica",
            "como hacerlo",
            "como lo hago",
            "como se hace",
            "ayudame con",
            "ayuda con",
        ]
    )

    if any(
        token in normalized
        for token in [
            "que puedes hacer",
            "que haces",
            "que soportas",
            "como funciona el agente",
            "ayuda",
            "ayudame",
            "explicame como hacerlo",
        ]
    ):
        return {"action_code": "help"}

    year_match = re.search(r"(20\d{2})", raw)
    if ("cosecha" in normalized or "recovery" in normalized) and year_match:
        return {"action_code": "recovery_vintage", "year": int(year_match.group(1)), "explain_only": explain_only}

    if any(token in normalized for token in ["simula", "simular", "simulacion", "simulacion diaria"]):
        fmora1_match = re.search(r"(?:fmora1\s+(\d+)|(\d+)\s+fmora1)", normalized)
        preventivo_match = re.search(r"(?:preventivo\s+(\d+)|(\d+)\s+preventivo)", normalized)
        recovery_match = re.search(r"(?:recovery\s+(\d+)|(\d+)\s+recovery)", normalized)
        return {
            "action_code": "daily_simulation",
            "fmora1_clients": int((fmora1_match.group(1) or fmora1_match.group(2))) if fmora1_match else 250,
            "preventivo_clients": int((preventivo_match.group(1) or preventivo_match.group(2))) if preventivo_match else 120,
            "recovery_clients": int((recovery_match.group(1) or recovery_match.group(2))) if recovery_match else 1000,
            "explain_only": explain_only,
        }

    group_match = re.search(
        r"(asigna|asignar|agrega|agregar|vincula|vincular|pone|poner|pon|desasigna|desasignar|quita|quitar|retira|retirar)\s+(?:la\s+)?(?:cartera|grupo|lista)\s+([A-Za-z0-9]+)\s+(?:al|a|para|del|de)\s+(?:usuario|collector|gestor)?\s*([A-Za-z0-9_]+)",
        raw,
        re.IGNORECASE,
    )
    if group_match:
        is_assign = group_match.group(1).lower() in {"asigna", "asignar", "agrega", "agregar", "vincula", "vincular", "pone", "poner", "pon"}
        return {
            "action_code": "assign_group" if is_assign else "unassign_group",
            "group_id": group_match.group(2).upper(),
            "user_identifier": group_match.group(3),
            "explain_only": explain_only,
        }

    supervisor_match = re.search(
        r"(asigna|asignar|agrega|agregar|vincula|vincular|pone|poner|pon|desasigna|desasignar|quita|quitar|retira|retirar)\s+(?:collector|usuario|gestor)?\s*([A-Za-z0-9_]+)\s+(?:al|a|para|del|de)\s+supervisor\s+([A-Za-z0-9_]+)",
        raw,
        re.IGNORECASE,
    )
    if supervisor_match:
        is_assign = supervisor_match.group(1).lower() in {"asigna", "asignar", "agrega", "agregar", "vincula", "vincular", "pone", "poner", "pon"}
        return {
            "action_code": "assign_supervisor" if is_assign else "unassign_supervisor",
            "collector_identifier": supervisor_match.group(2),
            "supervisor_identifier": supervisor_match.group(3),
            "explain_only": explain_only,
        }

    toggle_match = re.search(r"(activa|desactiva|habilita|deshabilita|enciende|apaga)\s+(email|whatsapp|callbot)", normalized)
    if toggle_match:
        return {
            "action_code": "toggle_channel",
            "channel": toggle_match.group(2),
            "enabled": toggle_match.group(1) in {"activa", "habilita", "enciende"},
            "explain_only": explain_only,
        }

    groups_match = re.search(
        r"(?:muestra|ver|consulta|listar|listame|que grupos tiene|que carteras tiene).*(?:usuario|collector|gestor)?\s*([A-Za-z0-9_]+)",
        raw,
        re.IGNORECASE,
    )
    if groups_match:
        return {"action_code": "show_user_groups", "user_identifier": groups_match.group(1), "explain_only": explain_only}

    return {"action_code": "unsupported"}


@app.post("/admin/assistant/chat", response_model=AdminAssistantResponse)
def admin_assistant_chat(
    payload: AdminAssistantRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    parsed = parse_admin_assistant_message(payload.message)
    action_code = parsed["action_code"]

    if action_code == "help":
        return AdminAssistantResponse(
            action_code="help",
            interpreted_message="Mostrar ayuda del agente administrativo",
            response_message=(
                "Puedo ayudarte con 1) cosechas Recovery por año, 2) simulación diaria, 3) asignar o quitar carteras a un usuario, "
                "4) asignar o retirar collectors de un supervisor, 5) activar o desactivar email, WhatsApp o callbot, y 6) consultar "
                "qué grupos tiene un usuario. Ejemplos: `ver cosecha recovery 2025`, `asigna cartera V13A082 al usuario collector1`, "
                "`quita collector2 del supervisor supervisor1`, `activa email`, `simula fmora1 300 preventivo 120 recovery 900`, "
                "`qué grupos tiene collector1`."
            ),
            requires_confirmation=False,
            can_apply=False,
            executed=False,
        )

    if action_code == "unsupported":
        return AdminAssistantResponse(
            action_code="unsupported",
            interpreted_message=payload.message,
            response_message=(
                "No interpreté bien la instrucción. Puedo ayudarte con cosechas Recovery, simulación diaria, asignación de grupos, "
                "supervisores y canales omnicanal. Si quieres, prueba con frases como `ver cosecha recovery 2025`, "
                "`asigna cartera V13A082 al usuario collector1` o `explícame cómo activar email`."
            ),
            requires_confirmation=False,
            can_apply=False,
            executed=False,
        )

    if action_code == "recovery_vintage":
        overview = build_recovery_vintage_overview(db, year=parsed["year"], sample_limit=20000)
        return AdminAssistantResponse(
            action_code=action_code,
            interpreted_message=f"Consultar cosecha Recovery {parsed['year']}",
            response_message=(
                f"{'Te explico cómo leerla y además ' if parsed.get('explain_only') else ''}"
                f"preparé la lectura de la cosecha Recovery {parsed['year']}. Ya puedes revisar placements, agencias y clientes."
            ),
            executed=True,
            data={"recovery_vintage": overview.model_dump(mode="json")},
        )

    if action_code == "show_user_groups":
        user = find_user_by_identifier(db, parsed["user_identifier"])
        if not user:
            raise HTTPException(status_code=404, detail="No encontré ese usuario.")
        groups = get_worklist_groups_for_user(db, user.id)
        return AdminAssistantResponse(
            action_code=action_code,
            interpreted_message=f"Consultar grupos de {user.username}",
            response_message=(
                f"{user.username} tiene {len(groups)} grupos visibles en este momento."
                if not parsed.get("explain_only")
                else f"{user.username} tiene {len(groups)} grupos visibles. Te los muestro para que desde el panel admin puedas decidir si asignas, desasignas o cambias la cobertura."
            ),
            executed=True,
            data={"user": UserRead.model_validate(user).model_dump(mode='json'), "groups": [group.model_dump(mode='json') for group in groups]},
        )

    if action_code == "toggle_channel":
        channel = parsed["channel"]
        enabled = parsed["enabled"]
        if parsed.get("explain_only") and not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message=f"{'Activar' if enabled else 'Desactivar'} {channel}",
                response_message=(
                    f"Para {'activar' if enabled else 'desactivar'} {channel} el agente primero prepara el cambio y luego te pide confirmación. "
                    f"Si quieres que lo aplique ahora, envíame la misma instrucción sin pedir explicación o pulsa confirmar cuando aparezca la propuesta."
                ),
                requires_confirmation=False,
                can_apply=False,
                executed=False,
                data={"channel": channel, "enabled": enabled},
            )
        if not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message=f"{'Activar' if enabled else 'Desactivar'} {channel}",
                response_message=f"Voy a {'activar' if enabled else 'desactivar'} {channel} en el centro omnicanal. Si estás listo, confirma para aplicar el cambio.",
                requires_confirmation=True,
                can_apply=True,
                executed=False,
                data={"channel": channel, "enabled": enabled},
            )
        cfg = get_omnichannel_settings(db)
        channel_field_map = {
            "email": "email_enabled",
            "whatsapp": "whatsapp_bot_enabled",
            "callbot": "callbot_enabled",
        }
        field_name = channel_field_map[channel]
        cfg[field_name] = enabled
        updated = update_admin_omnichannel_config(AdminOmnichannelConfigUpdate(**cfg), db, current_user)
        return AdminAssistantResponse(
            action_code=action_code,
            interpreted_message=f"{'Activar' if enabled else 'Desactivar'} {channel}",
            response_message=f"{channel.capitalize()} quedó {'activo' if enabled else 'inactivo'} en la configuración omnicanal.",
            requires_confirmation=False,
            can_apply=False,
            executed=True,
            data={"omnichannel": updated},
        )

    if action_code in {"assign_group", "unassign_group"}:
        user = find_user_by_identifier(db, parsed["user_identifier"])
        if not user:
            raise HTTPException(status_code=404, detail="No encontré el usuario indicado.")
        matching = (
            db.query(AssignmentHistory)
            .filter(AssignmentHistory.is_current.is_(True), AssignmentHistory.group_id == parsed["group_id"])
            .first()
        )
        if not matching:
            raise HTTPException(status_code=404, detail="No encontré esa cartera o grupo.")
        request_payload = {
            "user_id": user.id,
            "group_id": parsed["group_id"],
            "strategy_code": matching.strategy_code,
            "placement_code": matching.placement_code,
        }
        if action_code == "assign_group":
            request_payload["reassign_existing"] = True
        if parsed.get("explain_only") and not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message=f"{'Asignar' if action_code == 'assign_group' else 'Desasignar'} grupo {parsed['group_id']} a {user.username}",
                response_message=(
                    f"Para {'asignar' if action_code == 'assign_group' else 'desasignar'} una cartera, el agente identifica el grupo {parsed['group_id']}, "
                    f"valida a qué estrategia y placement pertenece y prepara el cambio para {user.username}. Luego te pide confirmación antes de aplicarlo."
                ),
                requires_confirmation=False,
                can_apply=False,
                executed=False,
                data=request_payload,
            )
        if not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message=f"{'Asignar' if action_code == 'assign_group' else 'Desasignar'} grupo {parsed['group_id']} a {user.username}",
                response_message=f"Listo para {'asignar' if action_code == 'assign_group' else 'desasignar'} la cartera {parsed['group_id']} {'a' if action_code == 'assign_group' else 'de'} {user.username}. Confirma para aplicar.",
                requires_confirmation=True,
                can_apply=True,
                executed=False,
                data=request_payload,
            )
        result = (
            assign_worklist_group(WorklistGroupAssignRequest(**request_payload), db, current_user)
            if action_code == "assign_group"
            else unassign_worklist_group(WorklistGroupUnassignRequest(**request_payload), db, current_user)
        )
        return AdminAssistantResponse(
            action_code=action_code,
            interpreted_message=f"{'Asignar' if action_code == 'assign_group' else 'Desasignar'} grupo {parsed['group_id']} a {user.username}",
            response_message=result.get("message") or "Cambio aplicado correctamente.",
            executed=True,
            data=result,
        )

    if action_code in {"assign_supervisor", "unassign_supervisor"}:
        collector = find_user_by_identifier(db, parsed["collector_identifier"])
        supervisor = find_user_by_identifier(db, parsed["supervisor_identifier"])
        if not collector or not supervisor:
            raise HTTPException(status_code=404, detail="No encontré el collector o supervisor indicado.")
        request_payload = {"collector_id": collector.id, "supervisor_id": supervisor.id}
        if parsed.get("explain_only") and not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message=f"{'Asignar' if action_code == 'assign_supervisor' else 'Desasignar'} {collector.username} {'a' if action_code == 'assign_supervisor' else 'de'} {supervisor.username}",
                response_message=(
                    f"El flujo es: identificar al collector {collector.username}, ubicar al supervisor {supervisor.username}, "
                    f"preparar la relación y pedirte confirmación antes de grabarla en el sistema."
                ),
                requires_confirmation=False,
                can_apply=False,
                executed=False,
                data=request_payload,
            )
        if not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message=f"{'Asignar' if action_code == 'assign_supervisor' else 'Desasignar'} {collector.username} {'a' if action_code == 'assign_supervisor' else 'de'} {supervisor.username}",
                response_message=f"Listo para {'asignar' if action_code == 'assign_supervisor' else 'retirar'} a {collector.username} {'bajo' if action_code == 'assign_supervisor' else 'de'} {supervisor.username}. Confirma para aplicar.",
                requires_confirmation=True,
                can_apply=True,
                executed=False,
                data=request_payload,
            )
        result = (
            assign_collector_to_supervisor(SupervisorCollectorAssignRequest(**request_payload), db, current_user)
            if action_code == "assign_supervisor"
            else unassign_collector_from_supervisor(SupervisorCollectorAssignRequest(**request_payload), db, current_user)
        )
        return AdminAssistantResponse(
            action_code=action_code,
            interpreted_message=f"{'Asignar' if action_code == 'assign_supervisor' else 'Desasignar'} {collector.username} {'a' if action_code == 'assign_supervisor' else 'de'} {supervisor.username}",
            response_message=result.get("message") or "Cambio aplicado correctamente.",
            executed=True,
            data=result,
        )

    if action_code == "daily_simulation":
        if parsed.get("explain_only") and not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message="Simular día operativo",
                response_message=(
                    "La simulación diaria envejece cuentas, genera pagos, mueve clientes entre estrategias y rota placements Recovery. "
                    f"Con tu instrucción actual quedaría FMORA1={parsed['fmora1_clients']}, PREVENTIVO={parsed['preventivo_clients']} y RECOVERY={parsed['recovery_clients']}."
                ),
                requires_confirmation=False,
                can_apply=False,
                executed=False,
                data=parsed,
            )
        if not payload.apply_change:
            return AdminAssistantResponse(
                action_code=action_code,
                interpreted_message="Simular día operativo",
                response_message=f"Listo para simular un día operativo con FMORA1={parsed['fmora1_clients']}, PREVENTIVO={parsed['preventivo_clients']} y RECOVERY={parsed['recovery_clients']}. Confirma para ejecutar.",
                requires_confirmation=True,
                can_apply=True,
                executed=False,
                data=parsed,
            )
        result = run_admin_daily_rollover(
            AdminDailySimulationRequest(
                fmora1_clients=parsed["fmora1_clients"],
                preventivo_clients=parsed["preventivo_clients"],
                recovery_clients=parsed["recovery_clients"],
            ),
            db,
            current_user,
        )
        return AdminAssistantResponse(
            action_code=action_code,
            interpreted_message="Simular día operativo",
            response_message=result.message,
            executed=True,
            data=result.model_dump(mode="json"),
        )

    raise HTTPException(status_code=400, detail="No pude procesar la instrucción solicitada.")


@app.post("/admin/sql/query", response_model=AdminSqlQueryResponse)
def run_admin_sql_query(
    payload: AdminSqlQueryRequest,
    current_user: Usuario = Depends(require_roles("Admin")),
):
    normalized_query = validate_admin_sql_query(payload.query)
    is_explain_query = normalized_query.lower().startswith("explain ")
    started_at = datetime.now(timezone.utc)
    with get_readonly_connection() as connection:
        connection.execute(text("SET statement_timeout = 15000"))
        connection.execute(text("SET lock_timeout = 3000"))
        connection.execute(text("SET idle_in_transaction_session_timeout = 15000"))
        connection.execute(text("SET default_transaction_read_only = on"))
        statement = (
            text(normalized_query)
            if is_explain_query
            else text(f"SELECT * FROM ({normalized_query}) AS admin_sql_query LIMIT :max_rows_plus_one")
        )
        params = {} if is_explain_query else {"max_rows_plus_one": payload.max_rows + 1}
        result = connection.execute(statement, params)
        fetched_rows = result.mappings().all()
        columns = list(result.keys())

    truncated = len(fetched_rows) > payload.max_rows
    visible_rows = fetched_rows[: payload.max_rows]
    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    return AdminSqlQueryResponse(
        columns=columns,
        rows=[dict(row) for row in visible_rows],
        row_count=len(visible_rows),
        truncated=truncated,
        duration_ms=duration_ms,
        normalized_query=normalized_query,
    )


@app.put("/admin/omnichannel/config")
def update_admin_omnichannel_config(
    payload: AdminOmnichannelConfigUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    db.execute(
        text(
            """
            UPDATE omnichannel_settings
            SET
                whatsapp_bot_enabled = :whatsapp_bot_enabled,
                email_enabled = :email_enabled,
                callbot_enabled = :callbot_enabled,
                inbound_bot_enabled = :inbound_bot_enabled,
                automation_enabled = :automation_enabled,
                webhooks_configured = :webhooks_configured,
                template_library_ready = :template_library_ready,
                twilio_account_sid = :twilio_account_sid,
                twilio_auth_token = :twilio_auth_token,
                twilio_whatsapp_from = :twilio_whatsapp_from,
                twilio_demo_phone = :twilio_demo_phone,
                twilio_sms_from = :twilio_sms_from,
                twilio_voice_from = :twilio_voice_from,
                callbot_webhook_url = :callbot_webhook_url,
                resend_api_key = :resend_api_key,
                email_from = :email_from,
                smtp_host = :smtp_host,
                smtp_port = :smtp_port,
                smtp_user = :smtp_user,
                smtp_password = :smtp_password,
                sms_provider = :sms_provider,
                textbelt_api_key = :textbelt_api_key,
                notes = :notes,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """
        ),
        {
            "whatsapp_bot_enabled": payload.whatsapp_bot_enabled,
            "email_enabled": payload.email_enabled,
            "callbot_enabled": payload.callbot_enabled,
            "inbound_bot_enabled": payload.inbound_bot_enabled,
            "automation_enabled": payload.automation_enabled,
            "webhooks_configured": payload.webhooks_configured,
            "template_library_ready": payload.template_library_ready,
            "twilio_account_sid": payload.twilio_account_sid or "",
            "twilio_auth_token": payload.twilio_auth_token or "",
            "twilio_whatsapp_from": payload.twilio_whatsapp_from or "whatsapp:+14155238886",
            "twilio_demo_phone": payload.twilio_demo_phone or "",
            "twilio_sms_from": payload.twilio_sms_from or "",
            "twilio_voice_from": payload.twilio_voice_from or "",
            "callbot_webhook_url": payload.callbot_webhook_url or "",
            "resend_api_key": payload.resend_api_key or "",
            "email_from": payload.email_from or "",
            "smtp_host": payload.smtp_host or "",
            "smtp_port": payload.smtp_port or 587,
            "smtp_user": payload.smtp_user or "",
            "smtp_password": payload.smtp_password or "",
            "sms_provider": payload.sms_provider or "textbelt",
            "textbelt_api_key": payload.textbelt_api_key or "textbelt",
            "notes": payload.notes or "",
        },
    )
    db.add(
        History(
            entidad="admin",
            entidad_id=current_user.id,
            accion="OMNICHANNEL_CONFIG_UPDATED",
            descripcion=(
                f"Configuración omnicanal actualizada. WhatsApp={payload.whatsapp_bot_enabled}, "
                f"Email={payload.email_enabled}, Callbot={payload.callbot_enabled}, "
                f"Automatización={payload.automation_enabled}, Webhooks={payload.webhooks_configured}."
            ),
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return build_admin_omnichannel_overview(db)


@app.post("/admin/omnichannel/preview", response_model=AdminOmnichannelPreviewResponse)
def preview_admin_omnichannel_message(
    payload: dict,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    channel = str(payload.get("channel") or "").lower().strip()
    client_id = int(payload["client_id"]) if payload.get("client_id") not in {None, ""} else None
    strategy_code = payload.get("strategy_code")
    custom_message = payload.get("custom_message")
    custom_subject = payload.get("custom_subject")
    custom_html = payload.get("custom_html")
    if channel not in {"email", "sms", "whatsapp"}:
        raise HTTPException(status_code=400, detail="Canal no soportado para previsualización.")

    context = resolve_omnichannel_client_context(db, client_id, strategy_code)
    client = context["client"]

    if channel == "email":
        subject, html = build_collection_email_html(
            client_name=context["client_name"],
            strategy_code=context["strategy_code"],
            total_due=context["total_due"],
            minimum_payment=context["minimum_payment"],
            account_reference=context["account_reference"],
            due_date_str=context["due_date_str"],
        )
        return AdminOmnichannelPreviewResponse(
            channel="email",
            strategy_code=context["strategy_code"],
            client_name=context["client_name"],
            identity_code=client.identity_code if client else None,
            account_reference=context["account_reference"],
            subject=custom_subject or subject,
            html=custom_html or html,
        )

    if channel == "sms":
        message = custom_message or build_collection_sms(
            client_name=context["client_name"],
            strategy_code=context["strategy_code"],
            total_due=context["total_due"],
            minimum_payment=context["minimum_payment"],
            account_last4=context["account_last4"],
            due_date_str=context["due_date_str"],
        )
        return AdminOmnichannelPreviewResponse(
            channel="sms",
            strategy_code=context["strategy_code"],
            client_name=context["client_name"],
            identity_code=client.identity_code if client else None,
            account_reference=context["account_reference"],
            message=message,
        )

    message = build_whatsapp_demo_message(
        client,
        context["strategy_code"],
        custom_message,
        account_reference=context["account_last4"],
    )
    return AdminOmnichannelPreviewResponse(
        channel="whatsapp",
        strategy_code=context["strategy_code"],
        client_name=context["client_name"],
        identity_code=client.identity_code if client else None,
        account_reference=context["account_reference"],
        message=message,
    )


@app.post("/admin/omnichannel/whatsapp/demo-send")
def send_admin_whatsapp_demo(
    payload: AdminWhatsAppDemoSendRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    settings_row = get_omnichannel_settings(db)
    account_sid = settings_row.get("twilio_account_sid") or ""
    auth_token = settings_row.get("twilio_auth_token") or ""
    from_whatsapp = settings_row.get("twilio_whatsapp_from") or "whatsapp:+14155238886"
    if not account_sid or not auth_token:
        raise HTTPException(status_code=400, detail="Primero configura Account SID y Auth Token de Twilio en el Centro omnicanal.")

    client = db.get(Cliente, payload.client_id) if payload.client_id else None
    strategy_code = (payload.strategy_code or "").upper() or None
    if not strategy_code and client:
        client_accounts = db.query(Cuenta).filter(Cuenta.cliente_id == client.id).all()
        if client_accounts:
            strategy_code = derive_strategy_code(max(client_accounts, key=lambda item: int(item.dias_mora or 0)))
    account_reference = None
    if client:
        client_accounts = db.query(Cuenta).filter(Cuenta.cliente_id == client.id, Cuenta.saldo_mora > 0).order_by(Cuenta.dias_mora.desc()).all()
        if client_accounts:
            account_reference = client_accounts[0].numero_cuenta[-4:]
    message_body = build_whatsapp_demo_message(client, strategy_code, payload.custom_message, account_reference=account_reference)
    to_whatsapp = normalize_whatsapp_phone(payload.to_phone)
    session = get_or_create_whatsapp_bot_session(db, to_whatsapp, client=client, strategy_code=strategy_code)
    session.last_outbound_message = message_body
    save_whatsapp_session_context(session, {"step": "await_identity", "identified": False, "primary_last4": account_reference or "****"})
    twilio_response = send_twilio_whatsapp_message(account_sid, auth_token, from_whatsapp, to_whatsapp, message_body)

    db.add(
        History(
            entidad="omnichannel",
            entidad_id=client.id if client else current_user.id,
            accion="WHATSAPP_DEMO_SENT",
            descripcion=(
                f"WhatsApp demo enviado a {to_whatsapp} | Estrategia: {strategy_code or 'GENERAL'} | "
                f"Cliente: {(client.identity_code if client else 'N/A')} | SID: {twilio_response.get('sid', '')} | "
                f"Mensaje: {message_body}"
            ),
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {
        "status": twilio_response.get("status", "queued"),
        "sid": twilio_response.get("sid"),
        "to": twilio_response.get("to", to_whatsapp),
        "message": "Mensaje de demo enviado correctamente por WhatsApp.",
    }




# ── Email demo send ────────────────────────────────────────────────────────────
@app.post("/admin/omnichannel/email/demo-send")
def send_admin_email_demo(
    payload: AdminEmailDemoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    """
    Envía un email de demo de cobranza.
    Proveedor primario : Resend.com   (gratis 100/día — resend.com/signup)
    Proveedor fallback : SMTP genérico (Gmail, Outlook, etc.)
    Si payload.use_smtp=True usa SMTP directamente.
    """
    cfg = get_omnichannel_settings(db)
    client = db.get(Cliente, payload.client_id) if payload.client_id else None
    strategy_code = (payload.strategy_code or "").upper() or "FMORA1"
    total_due = 0.0
    minimum_payment = 0.0
    account_reference = "sin referencia"
    today = datetime.utcnow().date()
    due_date = today + timedelta(days=5)
    due_date_str = due_date.strftime("%d/%m/%Y")
    client_name = "Cliente"

    if client:
        client_name = f"{client.nombres} {client.apellidos}"
        accounts = (
            db.query(Cuenta)
            .filter(Cuenta.cliente_id == client.id)
            .order_by(Cuenta.dias_mora.desc(), Cuenta.id.asc())
            .all()
        )
        if accounts:
            strategy_context = derive_client_strategy_context(accounts, datetime.utcnow())
            lead_account = strategy_context["lead_account"] or accounts[0]
            strategy_code = strategy_context["primary_strategy"] or strategy_code
            total_due = round(float(lead_account.saldo_mora or 0), 2)
            minimum_payment = round(float(calculate_minimum_payment(lead_account) or 0), 2)
            account_reference = lead_account.numero_cuenta or "sin referencia"
            if lead_account.fecha_vencimiento and lead_account.fecha_vencimiento >= today:
                due_date = lead_account.fecha_vencimiento
            due_date_str = due_date.strftime("%d/%m/%Y")

    subject, html = build_collection_email_html(
        client_name=client_name,
        strategy_code=strategy_code,
        total_due=total_due,
        minimum_payment=minimum_payment,
        account_reference=account_reference,
        due_date_str=due_date_str,
    )
    if payload.custom_subject:
        subject = payload.custom_subject
    if payload.custom_html:
        html = payload.custom_html

    from_email = cfg.get("email_from") or "cobranza@360collectplus.com"
    result: dict

    if payload.use_smtp:
        smtp_host = cfg.get("smtp_host") or ""
        smtp_port = int(cfg.get("smtp_port") or 587)
        smtp_user = cfg.get("smtp_user") or ""
        smtp_password = cfg.get("smtp_password") or ""
        if not smtp_host or not smtp_user:
            raise HTTPException(
                status_code=400,
                detail="Configura smtp_host, smtp_user y smtp_password en el Centro omnicanal antes de usar SMTP.",
            )
        result = send_email_smtp(smtp_host, smtp_port, smtp_user, smtp_password, from_email, payload.to_email, subject, html)
    else:
        resend_key = cfg.get("resend_api_key") or ""
        if not resend_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Configura resend_api_key en el Centro omnicanal. "
                    "Registro gratuito en resend.com/signup — 100 emails/día sin tarjeta."
                ),
            )
        result = send_email_resend(resend_key, from_email, payload.to_email, subject, html)

    db.add(History(
        entidad="omnichannel",
        entidad_id=client.id if client else current_user.id,
        accion="EMAIL_DEMO_SENT",
        descripcion=(
            f"Email demo enviado a {payload.to_email} | Estrategia: {strategy_code} | "
            f"Proveedor: {'SMTP' if payload.use_smtp else 'Resend'} | Asunto: {subject}"
        ),
        usuario_id=current_user.id,
    ))
    db.commit()
    return {
        "status": "sent",
        "provider": "smtp" if payload.use_smtp else "resend",
        "to": payload.to_email,
        "subject": subject,
        "message": "Email de demo enviado correctamente.",
        "result": result,
    }


# ── SMS demo send ─────────────────────────────────────────────────────────────
@app.post("/admin/omnichannel/sms/demo-send")
def send_admin_sms_demo(
    payload: AdminSMSDemoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    """
    Envía un SMS de demo de cobranza.
    Proveedor TextBelt (por defecto/gratis):
      - Usa api_key='textbelt' → 1 SMS gratuito/día por IP, sin cuenta.
      - Demo instantáneo para validar el flujo. textbelt.com
    Proveedor Twilio SMS:
      - Usa la misma cuenta Twilio que WhatsApp.
      - Necesita un número SMS (diferente al de WhatsApp).
    """
    cfg = get_omnichannel_settings(db)
    client = db.get(Cliente, payload.client_id) if payload.client_id else None
    strategy_code = (payload.strategy_code or "").upper() or "FMORA1"
    total_due = 0.0
    minimum_payment = 0.0
    account_last4 = "****"
    due_date_str = (datetime.utcnow().date() + timedelta(days=5)).strftime("%d/%m/%Y")
    client_name = "Cliente"

    if client is None:
        candidate_accounts = (
            db.query(Cuenta)
            .filter(Cuenta.saldo_mora > 0)
            .order_by(Cuenta.dias_mora.desc(), Cuenta.saldo_mora.desc())
            .all()
        )
        for account in candidate_accounts:
            if derive_strategy_code(account) == strategy_code:
                client = db.get(Cliente, account.cliente_id)
                break

    if client:
        client_name = f"{client.nombres} {client.apellidos}"
        accounts = (
            db.query(Cuenta)
            .filter(Cuenta.cliente_id == client.id, Cuenta.saldo_mora > 0)
            .order_by(Cuenta.dias_mora.desc())
            .all()
        )
        if accounts:
            total_due = round(sum(float(a.saldo_mora) for a in accounts), 2)
            minimum_payment = round(sum(calculate_minimum_payment(a) for a in accounts), 2)
            account_last4 = accounts[0].numero_cuenta[-4:]
            strategy_code = derive_strategy_code(accounts[0])

    message = payload.custom_message or build_collection_sms(
        client_name=client_name,
        strategy_code=strategy_code,
        total_due=total_due,
        minimum_payment=minimum_payment,
        account_last4=account_last4,
        due_date_str=due_date_str,
    )

    provider = (payload.provider or cfg.get("sms_provider") or "textbelt").lower()
    result: dict

    if provider == "twilio":
        account_sid = cfg.get("twilio_account_sid") or ""
        auth_token = cfg.get("twilio_auth_token") or ""
        sms_from = cfg.get("twilio_sms_from") or ""
        if not account_sid or not auth_token or not sms_from:
            raise HTTPException(
                status_code=400,
                detail="Configura twilio_account_sid, twilio_auth_token y twilio_sms_from en el Centro omnicanal.",
            )
        result = send_sms_twilio(account_sid, auth_token, sms_from, payload.to_phone, message)
    else:
        textbelt_key = cfg.get("textbelt_api_key") or "textbelt"
        result = send_sms_textbelt(payload.to_phone, message, textbelt_key)

    db.add(History(
        entidad="omnichannel",
        entidad_id=client.id if client else current_user.id,
        accion="SMS_DEMO_SENT",
        descripcion=(
            f"SMS demo enviado a {payload.to_phone} | Proveedor: {provider} | "
            f"Estrategia: {strategy_code} | Mensaje: {message[:80]}..."
        ),
        usuario_id=current_user.id,
    ))
    db.commit()
    return {
        "status": "sent",
        "provider": provider,
        "to": payload.to_phone,
        "client_name": client_name,
        "account_last4": account_last4,
        "total_due": total_due,
        "minimum_payment": minimum_payment,
        "message_preview": message[:80] + "..." if len(message) > 80 else message,
        "result": result,
    }


# ── CallBot demo call ─────────────────────────────────────────────────────────
@app.post("/admin/omnichannel/callbot/demo-call")
def send_admin_callbot_demo(
    payload: AdminCallbotDemoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    """
    Inicia una llamada de callbot IVR de cobranza vía Twilio Voice.
    La llamada reproduce un guión adaptado a la estrategia del cliente
    y permite al destinatario presionar dígitos para responder.

    Requisitos:
      - Cuenta Twilio (trial sirve para números verificados)
      - twilio_voice_from: número Twilio con capacidad de voz (+15551234567)
      - callbot_webhook_url: URL pública del backend (ej: https://tu-ngrok.ngrok.io)
        El webhook /webhooks/twilio/voice debe ser accesible desde Internet.
        Para pruebas locales usa: ngrok http 8000

    Gratis con cuenta trial: registra en twilio.com/try-twilio, obtienes $15 de crédito.
    """
    cfg = get_omnichannel_settings(db)
    account_sid = cfg.get("twilio_account_sid") or ""
    auth_token = cfg.get("twilio_auth_token") or ""
    voice_from = cfg.get("twilio_voice_from") or ""
    webhook_url = (cfg.get("callbot_webhook_url") or "").rstrip("/")

    if not account_sid or not auth_token:
        raise HTTPException(
            status_code=400,
            detail="Configura twilio_account_sid y twilio_auth_token en el Centro omnicanal.",
        )
    if not voice_from:
        raise HTTPException(
            status_code=400,
            detail="Configura twilio_voice_from (número Twilio con voz, ej: +15551234567).",
        )
    if not webhook_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "Configura callbot_webhook_url con la URL pública de tu backend "
                "(ej: https://tu-ngrok.ngrok.io). Para pruebas locales usa: ngrok http 8000"
            ),
        )

    client = db.get(Cliente, payload.client_id) if payload.client_id else None
    strategy_code = (payload.strategy_code or "").upper() or "FMORA1"
    total_due = 0.0
    minimum_payment = 0.0
    account_last4 = "****"
    due_date_str = (datetime.utcnow().date() + timedelta(days=5)).strftime("%d/%m/%Y")
    client_name = "Cliente"

    if client:
        client_name = f"{client.nombres} {client.apellidos}"
        accounts = (
            db.query(Cuenta)
            .filter(Cuenta.cliente_id == client.id, Cuenta.saldo_mora > 0)
            .order_by(Cuenta.dias_mora.desc())
            .all()
        )
        if accounts:
            total_due = round(sum(float(a.saldo_mora) for a in accounts), 2)
            minimum_payment = round(sum(calculate_minimum_payment(a) for a in accounts), 2)
            account_last4 = accounts[0].numero_cuenta[-4:]
            strategy_code = derive_strategy_code(accounts[0])

    twiml_url = f"{webhook_url}/webhooks/twilio/voice"
    # Pass context to voice webhook via query params
    import urllib.parse as up
    ctx_params = up.urlencode({
        "client_name": client_name,
        "strategy_code": strategy_code,
        "total_due": str(total_due),
        "minimum_payment": str(minimum_payment),
        "account_last4": account_last4,
        "due_date_str": due_date_str,
    })
    twiml_url_with_ctx = f"{twiml_url}?{ctx_params}"

    twilio_resp = initiate_callbot_twilio(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=voice_from,
        to_number=payload.to_phone,
        twiml_webhook_url=twiml_url_with_ctx,
        status_callback_url=f"{webhook_url}/webhooks/twilio/voice/status",
    )

    db.add(History(
        entidad="omnichannel",
        entidad_id=client.id if client else current_user.id,
        accion="CALLBOT_DEMO_INITIATED",
        descripcion=(
            f"Llamada callbot iniciada a {payload.to_phone} | "
            f"Estrategia: {strategy_code} | Cliente: {client_name} | "
            f"SID: {twilio_resp.get('sid', '')} | Estado: {twilio_resp.get('status', '')}"
        ),
        usuario_id=current_user.id,
    ))
    db.commit()
    return {
        "status": twilio_resp.get("status", "queued"),
        "sid": twilio_resp.get("sid"),
        "to": payload.to_phone,
        "message": "Llamada de callbot iniciada. El destinatario recibirá la llamada en segundos.",
        "note": "Con cuenta trial solo puedes llamar a números verificados en la consola Twilio.",
    }


# ── Twilio Voice webhook — TwiML inicial ──────────────────────────────────────
@app.post("/webhooks/twilio/voice")
def twilio_voice_webhook(
    request: Request,
    CallSid: str = Form(default=""),
    To: str = Form(default=""),
    From: str = Form(default=""),
    CallStatus: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """
    Twilio llama a este endpoint cuando la llamada conecta.
    Devuelve TwiML con el guión del IVR de cobranza.
    Los parámetros del cliente vienen como query params (pasados desde el demo-call).
    """
    cfg = get_omnichannel_settings(db)
    webhook_base = (cfg.get("callbot_webhook_url") or "http://localhost:8000").rstrip("/")
    params = dict(request.query_params)
    client_name = params.get("client_name", "cliente")
    strategy_code = params.get("strategy_code", "FMORA1")
    total_due = float(params.get("total_due", "0"))
    minimum_payment = float(params.get("minimum_payment", "0"))
    account_last4 = params.get("account_last4", "****")
    due_date_str = params.get("due_date_str", "próximamente")

    twiml = build_twiml_initial_call(
        client_name=client_name,
        strategy_code=strategy_code,
        total_due=total_due,
        minimum_payment=minimum_payment,
        account_last4=account_last4,
        due_date_str=due_date_str,
        gather_webhook_url=webhook_base,
    )

    if CallSid:
        db.add(History(
            entidad="omnichannel",
            entidad_id=0,
            accion="CALLBOT_CONNECTED",
            descripcion=f"Callbot conectado | SID: {CallSid} | De: {From} | A: {To} | Estado: {CallStatus}",
            usuario_id=None,
        ))
        db.commit()

    return Response(content=twiml, media_type="application/xml")


# ── Twilio Voice gather — respuesta IVR ───────────────────────────────────────
@app.post("/webhooks/twilio/voice/gather")
def twilio_voice_gather(
    request: Request,
    Digits: str = Form(default=""),
    CallSid: str = Form(default=""),
    To: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """
    Twilio llama aquí con el dígito presionado por el cliente.
    Devuelve TwiML con la respuesta apropiada.
    """
    params = dict(request.query_params)
    context = {
        "client_name": params.get("client_name", "cliente"),
        "minimum_payment": float(params.get("minimum_payment", "0")),
        "due_date_str": params.get("due_date_str", "próximamente"),
        "account_last4": params.get("account_last4", "****"),
    }
    twiml = build_twiml_gather_response(Digits, context)

    db.add(History(
        entidad="omnichannel",
        entidad_id=0,
        accion="CALLBOT_DIGIT_PRESSED",
        descripcion=(
            f"IVR dígito: {Digits or 'sin respuesta'} | "
            f"SID: {CallSid} | A: {To} | Cliente: {context['client_name']}"
        ),
        usuario_id=None,
    ))
    db.commit()
    return Response(content=twiml, media_type="application/xml")


# ── Twilio Voice status callback ──────────────────────────────────────────────
@app.post("/webhooks/twilio/voice/status")
def twilio_voice_status(
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    To: str = Form(default=""),
    Duration: str = Form(default="0"),
    db: Session = Depends(get_db),
):
    """Recibe el estado final de la llamada (completed, no-answer, busy, failed)."""
    db.add(History(
        entidad="omnichannel",
        entidad_id=0,
        accion=f"CALLBOT_STATUS_{CallStatus.upper().replace('-','_')}",
        descripcion=f"Llamada {CallSid} a {To} terminó con estado '{CallStatus}'. Duración: {Duration}s.",
        usuario_id=None,
    ))
    db.commit()
    return {"received": True}

@app.post("/webhooks/twilio/whatsapp")
def twilio_whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(default=""),
    db: Session = Depends(get_db),
):
    inbound_phone = normalize_whatsapp_phone(From)
    session = get_or_create_whatsapp_bot_session(db, inbound_phone)
    client = find_client_for_whatsapp_session(db, inbound_phone, session)
    if client and not session.client_id:
        session.client_id = client.id
    session.last_inbound_message = Body
    reply_body = build_whatsapp_bot_reply(db, client, session, Body)
    session.last_outbound_message = reply_body
    session.last_message_at = datetime.utcnow()
    session.updated_at = datetime.utcnow()

    db.add(
        History(
            entidad="omnichannel",
            entidad_id=client.id if client else session.id,
            accion="WHATSAPP_BOT_INBOUND",
            descripcion=f"Inbound WhatsApp desde {inbound_phone}: {Body}",
            usuario_id=None,
        )
    )
    db.add(
        History(
            entidad="omnichannel",
            entidad_id=client.id if client else session.id,
            accion="WHATSAPP_BOT_REPLY",
            descripcion=f"Respuesta bot a {inbound_phone}: {reply_body}",
            usuario_id=None,
        )
    )
    db.commit()
    return Response(content=render_twiml_message(reply_body), media_type="application/xml")


@app.get("/clients/{client_id}/assignment-history", response_model=list[AssignmentHistoryRead])
def get_client_assignment_history(
    client_id: int,
    as_of: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin", "Supervisor", "Collector", "Auditor", "GestorUsuarios")),
):
    client = db.get(Cliente, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    query = db.query(AssignmentHistory).filter(AssignmentHistory.cliente_id == client_id)
    if as_of:
        cutoff = datetime.combine(as_of, datetime.max.time())
        query = query.filter(
            AssignmentHistory.start_at <= cutoff,
            (AssignmentHistory.end_at.is_(None)) | (AssignmentHistory.end_at >= cutoff),
        )
    return [AssignmentHistoryRead.model_validate(item) for item in query.order_by(AssignmentHistory.start_at.desc()).all()]


@app.post("/admin/strategies", response_model=StrategyRead, status_code=201)
def create_strategy(
    payload: StrategyCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    existing = db.query(Strategy).filter(Strategy.codigo == payload.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una estrategia con ese código.")
    strategy = Strategy(**payload.model_dump())
    db.add(strategy)
    db.add(
        History(
            entidad="estrategias",
            entidad_id=0,
            accion="STRATEGY_CREATED",
            descripcion=f"Estrategia {payload.codigo} creada por administrador.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    db.refresh(strategy)
    return strategy


@app.post("/admin/worklists/assign", status_code=201)
def assign_worklist_clients(
    payload: WorklistAssignRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    target_user = db.get(Usuario, payload.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario destino no encontrado.")

    client_ids = sorted(set(payload.client_ids))
    found_clients = db.query(Cliente.id).filter(Cliente.id.in_(client_ids)).all()
    if len(found_clients) != len(client_ids):
        raise HTTPException(status_code=400, detail="Uno o más clientes no existen.")

    for client_id in client_ids:
        client = db.get(Cliente, client_id)
        existing = (
            db.query(WorklistAssignment)
            .filter(
                WorklistAssignment.usuario_id == payload.user_id,
                WorklistAssignment.cliente_id == client_id,
                WorklistAssignment.activa.is_(True),
            )
            .first()
        )
        if existing:
            continue
        assignment = WorklistAssignment(
            usuario_id=payload.user_id,
            cliente_id=client_id,
            estrategia_codigo=payload.strategy_code,
            activa=True,
        )
        db.add(assignment)
        db.flush()
        if client:
            record_assignment_history(
                db,
                client,
                assignment,
                strategy_code=payload.strategy_code,
                notes=f"Asignacion administrativa directa a {target_user.username}.",
                user=target_user,
            )

    db.add(
        History(
            entidad="asignaciones_cartera",
            entidad_id=payload.user_id,
            accion="WORKLIST_ASSIGNED",
            descripcion=f"Administrador asignó {len(client_ids)} clientes a {target_user.username}.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": "Clientes asignados a la lista de trabajo correctamente."}


@app.get("/admin/worklists/groups/catalog", response_model=list[WorklistGroupRead])
def get_admin_worklist_group_catalog(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    return get_worklist_group_catalog(db)


@app.get("/admin/worklists/users/{user_id}/groups", response_model=list[WorklistGroupRead])
def get_admin_user_worklist_groups(
    user_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    user = db.get(Usuario, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return get_worklist_groups_for_user(db, user_id)


@app.post("/admin/worklists/groups/assign", status_code=201)
def assign_worklist_group(
    payload: WorklistGroupAssignRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    target_user = db.get(Usuario, payload.user_id)
    if not target_user or target_user.rol != "Collector":
        raise HTTPException(status_code=404, detail="Collector destino no encontrado.")

    matching_rows = (
        db.query(AssignmentHistory)
        .filter(
            AssignmentHistory.is_current.is_(True),
            AssignmentHistory.group_id == payload.group_id,
            AssignmentHistory.strategy_code == payload.strategy_code if payload.strategy_code else text("TRUE"),
            AssignmentHistory.placement_code == payload.placement_code if payload.placement_code else text("TRUE"),
        )
        .all()
    )
    if not matching_rows:
        raise HTTPException(status_code=404, detail="No se encontró la cartera solicitada.")

    client_ids = sorted({row.cliente_id for row in matching_rows})
    if payload.reassign_existing:
        db.query(WorklistAssignment).filter(
            WorklistAssignment.cliente_id.in_(client_ids),
            WorklistAssignment.activa.is_(True),
        ).update({WorklistAssignment.activa: False}, synchronize_session=False)

    created = 0
    for client_id in client_ids:
        existing = (
            db.query(WorklistAssignment)
            .filter(
                WorklistAssignment.usuario_id == target_user.id,
                WorklistAssignment.cliente_id == client_id,
                WorklistAssignment.activa.is_(True),
            )
            .first()
        )
        if existing:
            continue
        client = db.get(Cliente, client_id)
        if not client:
            continue
        assignment = WorklistAssignment(
            usuario_id=target_user.id,
            cliente_id=client_id,
            estrategia_codigo=payload.strategy_code or matching_rows[0].strategy_code,
            activa=True,
        )
        db.add(assignment)
        db.flush()
        record_assignment_history(
            db,
            client,
            assignment,
            strategy_code=payload.strategy_code or matching_rows[0].strategy_code,
            notes=f"Asignacion administrativa de cartera {payload.group_id} a {target_user.username}.",
            user=target_user,
        )
        current_history = (
            db.query(AssignmentHistory)
            .filter(AssignmentHistory.assignment_id == assignment.id, AssignmentHistory.is_current.is_(True))
            .first()
        )
        if current_history:
            current_history.group_id = payload.group_id
            current_history.placement_code = payload.placement_code or current_history.placement_code
            current_history.strategy_code = payload.strategy_code or current_history.strategy_code
        created += 1

    db.add(
        History(
            entidad="asignaciones_cartera",
            entidad_id=target_user.id,
            accion="WORKLIST_GROUP_ASSIGNED",
            descripcion=f"Administrador asignó la cartera {payload.group_id} ({created} clientes) a {target_user.username}.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": f"Cartera {payload.group_id} asignada correctamente.", "clients_assigned": created}


@app.post("/admin/worklists/groups/unassign")
def unassign_worklist_group(
    payload: WorklistGroupUnassignRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    target_user = db.get(Usuario, payload.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    matching_history = (
        db.query(AssignmentHistory)
        .filter(
            AssignmentHistory.usuario_id == payload.user_id,
            AssignmentHistory.is_current.is_(True),
            AssignmentHistory.group_id == payload.group_id,
            AssignmentHistory.strategy_code == payload.strategy_code if payload.strategy_code else text("TRUE"),
            AssignmentHistory.placement_code == payload.placement_code if payload.placement_code else text("TRUE"),
        )
        .all()
    )
    if not matching_history:
        raise HTTPException(status_code=404, detail="No se encontró esa cartera asignada al usuario.")

    client_ids = sorted({row.cliente_id for row in matching_history})
    db.query(WorklistAssignment).filter(
        WorklistAssignment.usuario_id == payload.user_id,
        WorklistAssignment.cliente_id.in_(client_ids),
        WorklistAssignment.activa.is_(True),
    ).update({WorklistAssignment.activa: False}, synchronize_session=False)

    db.add(
        History(
            entidad="asignaciones_cartera",
            entidad_id=target_user.id,
            accion="WORKLIST_GROUP_UNASSIGNED",
            descripcion=f"Administrador desasignó la cartera {payload.group_id} de {target_user.username}.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": f"Cartera {payload.group_id} desasignada correctamente.", "clients_unassigned": len(client_ids)}


@app.get("/admin/supervisor-assignments", response_model=list[SupervisorCollectorAssignmentRead])
def get_admin_supervisor_assignments(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    supervisors = get_supervisors(db)
    return [
        SupervisorCollectorAssignmentRead(
            supervisor=UserRead.model_validate(supervisor),
            collectors=[UserRead.model_validate(item) for item in get_collectors_for_supervisor(db, supervisor)],
        )
        for supervisor in supervisors
    ]


@app.post("/admin/supervisor-assignments", status_code=201)
def assign_collector_to_supervisor(
    payload: SupervisorCollectorAssignRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    supervisor = db.get(Usuario, payload.supervisor_id)
    collector = db.get(Usuario, payload.collector_id)
    if not supervisor or supervisor.rol != "Supervisor":
        raise HTTPException(status_code=404, detail="Supervisor no encontrado.")
    if not collector or collector.rol != "Collector":
        raise HTTPException(status_code=404, detail="Collector no encontrado.")
    db.execute(
        text(
            """
            INSERT INTO supervisor_assignments (supervisor_id, collector_id)
            VALUES (:supervisor_id, :collector_id)
            ON CONFLICT (supervisor_id, collector_id) DO NOTHING
            """
        ),
        {"supervisor_id": supervisor.id, "collector_id": collector.id},
    )
    db.add(
        History(
            entidad="usuarios",
            entidad_id=collector.id,
            accion="SUPERVISOR_ASSIGNMENT_CREATED",
            descripcion=f"Administrador asignó a {collector.username} bajo el supervisor {supervisor.username}.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": f"{collector.username} fue asignado a {supervisor.username}."}


@app.post("/admin/supervisor-assignments/remove")
def unassign_collector_from_supervisor(
    payload: SupervisorCollectorAssignRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    supervisor = db.get(Usuario, payload.supervisor_id)
    collector = db.get(Usuario, payload.collector_id)
    if not supervisor or supervisor.rol != "Supervisor":
        raise HTTPException(status_code=404, detail="Supervisor no encontrado.")
    if not collector or collector.rol != "Collector":
        raise HTTPException(status_code=404, detail="Collector no encontrado.")
    db.execute(
        text(
            """
            DELETE FROM supervisor_assignments
            WHERE supervisor_id = :supervisor_id
              AND collector_id = :collector_id
            """
        ),
        {"supervisor_id": supervisor.id, "collector_id": collector.id},
    )
    db.add(
        History(
            entidad="usuarios",
            entidad_id=collector.id,
            accion="SUPERVISOR_ASSIGNMENT_REMOVED",
            descripcion=f"Administrador retiró a {collector.username} del supervisor {supervisor.username}.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": f"{collector.username} fue desasignado de {supervisor.username}."}


@app.post("/admin/documents/analyze", response_model=AdminDocumentProposalResponse)
async def analyze_admin_document(
    file: UploadFile = File(...),
    admin_notes: str = Form(default=""),
    _: Usuario = Depends(require_roles("Admin")),
):
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="El documento está vacío.")
    proposal = build_document_proposal(file.filename or "manual.pdf", extract_pdf_like_text(payload), admin_notes)
    ADMIN_DOCUMENT_PROPOSALS[proposal["proposal_id"]] = proposal
    return AdminDocumentProposalResponse(**proposal)


@app.get("/admin/documents/template")
def download_admin_document_template(_: Usuario = Depends(require_roles("Admin"))):
    file_stream = io.BytesIO(build_admin_template_docx_bytes())
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="plantilla-estrategia-ajustes-360collectplus.docx"'},
    )


@app.get("/admin/imports/template")
def download_admin_import_template(_: Usuario = Depends(require_roles("Admin"))):
    file_stream = io.BytesIO(build_admin_import_template_csv_bytes())
    return StreamingResponse(
        file_stream,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="plantilla-carga-clientes-360collectplus.csv"'},
    )


@app.post("/admin/imports/clients/analyze", response_model=AdminImportProposalResponse)
async def analyze_admin_client_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    proposal = build_admin_import_proposal(file.filename or "carga-clientes.csv", payload, db)
    ADMIN_IMPORT_PROPOSALS[proposal["proposal_id"]] = proposal
    return AdminImportProposalResponse(**{key: value for key, value in proposal.items() if key != "clean_rows"})


@app.post("/admin/imports/clients/{proposal_id}/discard")
def discard_admin_client_import(
    proposal_id: str,
    _: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_IMPORT_PROPOSALS.pop(proposal_id, None)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la carga validada solicitada.")
    return {"message": "La carga validada fue descartada.", "proposal_id": proposal_id}


@app.post("/admin/imports/clients/{proposal_id}/apply")
def apply_admin_client_import(
    proposal_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_IMPORT_PROPOSALS.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la carga validada solicitada.")

    created_clients = 0
    updated_clients = 0
    created_accounts = 0
    updated_accounts = 0
    assignment_updates = 0

    for row in proposal.get("clean_rows", []):
        client = db.query(Cliente).filter(Cliente.identity_code == row["identity_code"]).first()
        if client:
            updated_clients += 1
        else:
            client = Cliente(
                identity_code=row["identity_code"],
                nombres=row["nombres"],
                apellidos=row["apellidos"],
                dui=row["dui"],
            )
            db.add(client)
            db.flush()
            created_clients += 1

        client.nombres = row["nombres"]
        client.apellidos = row["apellidos"]
        client.dui = row["dui"]
        client.telefono = row["telefono"]
        client.email = row["email"]
        client.direccion = row["direccion"]
        client.segmento = row["segmento"]
        client.score_riesgo = row["score_riesgo"]

        account = db.query(Cuenta).filter(Cuenta.numero_cuenta == row["numero_cuenta"]).first()
        if account:
            updated_accounts += 1
        else:
            account = Cuenta(numero_cuenta=row["numero_cuenta"], cliente_id=client.id, tipo_producto=row["tipo_producto"])
            db.add(account)
            created_accounts += 1

        account.cliente_id = client.id
        account.tipo_producto = row["tipo_producto"]
        account.subtipo_producto = row["subtipo_producto"]
        account.saldo_capital = row["saldo_capital"]
        account.saldo_mora = row["saldo_mora"]
        account.saldo_total = row["saldo_total"]
        account.dias_mora = row["dias_mora"]
        account.bucket_actual = row["bucket_actual"]
        account.estado = row["estado"]
        account.fecha_apertura = row["fecha_apertura"]
        account.fecha_vencimiento = row["fecha_vencimiento"]
        account.tasa_interes = row["tasa_interes"]
        account.es_estrafinanciamiento = row["es_estrafinanciamiento"]

        collector_user_id = row.get("collector_user_id")
        if collector_user_id:
            collector_user = db.get(Usuario, collector_user_id)
            assignment = (
                db.query(WorklistAssignment)
                .filter(WorklistAssignment.cliente_id == client.id, WorklistAssignment.activa.is_(True))
                .order_by(WorklistAssignment.id.desc())
                .first()
            )
            if assignment:
                assignment.usuario_id = collector_user_id
                assignment.estrategia_codigo = row["estrategia_codigo"]
            else:
                assignment = WorklistAssignment(
                    usuario_id=collector_user_id,
                    cliente_id=client.id,
                    estrategia_codigo=row["estrategia_codigo"],
                    activa=True,
                )
                db.add(assignment)
            db.flush()
            record_assignment_history(
                db,
                client,
                assignment,
                strategy_code=row["estrategia_codigo"],
                notes=f"Carga masiva aplicada desde {proposal['file_name']}.",
                user=collector_user,
            )
            assignment_updates += 1

    proposal["status"] = "APLICADA"
    db.add(
        History(
            entidad="clientes",
            entidad_id=0,
            accion="CLIENT_IMPORT_APPLIED",
            descripcion=(
                f"Administrador aplicó la carga {proposal_id} desde {proposal['file_name']}. "
                f"Clientes nuevos: {created_clients}, actualizados: {updated_clients}, "
                f"cuentas nuevas: {created_accounts}, cuentas actualizadas: {updated_accounts}, "
                f"asignaciones listas: {assignment_updates}."
            ),
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {
        "message": "Carga masiva aplicada correctamente.",
        "proposal_id": proposal_id,
        "created_clients": created_clients,
        "updated_clients": updated_clients,
        "created_accounts": created_accounts,
        "updated_accounts": updated_accounts,
        "assignment_updates": assignment_updates,
        "status": proposal["status"],
    }


@app.get("/admin/imports/users/template")
def download_admin_user_import_template(_: Usuario = Depends(require_roles("Admin"))):
    file_stream = io.BytesIO(build_admin_user_import_template_csv_bytes())
    return StreamingResponse(
        file_stream,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="plantilla-carga-usuarios-360collectplus.csv"'},
    )


@app.post("/admin/imports/users/analyze", response_model=AdminImportProposalResponse)
async def analyze_admin_user_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    proposal = build_admin_user_import_proposal(file.filename or "carga-usuarios.csv", payload, db)
    ADMIN_USER_IMPORT_PROPOSALS[proposal["proposal_id"]] = proposal
    return AdminImportProposalResponse(**{key: value for key, value in proposal.items() if key != "clean_rows"})


@app.post("/admin/imports/users/{proposal_id}/discard")
def discard_admin_user_import(
    proposal_id: str,
    _: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_USER_IMPORT_PROPOSALS.pop(proposal_id, None)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la carga de usuarios validada.")
    return {"message": "La carga validada de usuarios fue descartada.", "proposal_id": proposal_id}


@app.post("/admin/imports/users/{proposal_id}/apply")
def apply_admin_user_import(
    proposal_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_USER_IMPORT_PROPOSALS.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la carga de usuarios validada.")

    created_users = 0
    updated_users = 0
    for row in proposal.get("clean_rows", []):
        user = db.query(Usuario).filter(Usuario.username == row["username"]).first()
        if user:
            updated_users += 1
        else:
            user = Usuario(username=row["username"], email=row["email"], nombre=row["nombre"], rol=row["rol"], password_hash=hash_password(row["password"]), activo=row["activo"])
            db.add(user)
            created_users += 1
        user.nombre = row["nombre"]
        user.email = row["email"]
        user.rol = row["rol"]
        user.activo = row["activo"]
        if row["password"]:
            user.password_hash = hash_password(row["password"])

    proposal["status"] = "APLICADA"
    db.add(
        History(
            entidad="usuarios",
            entidad_id=0,
            accion="USER_IMPORT_APPLIED",
            descripcion=f"Administrador aplicó la carga {proposal_id}. Usuarios nuevos: {created_users}, actualizados: {updated_users}.",
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {"message": "Carga de usuarios aplicada correctamente.", "proposal_id": proposal_id, "created_users": created_users, "updated_users": updated_users, "status": proposal["status"]}


@app.post("/admin/reports/generate", response_model=AdminGeneratedReportResponse)
def generate_admin_report(
    payload: AdminGeneratedReportRequest,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    return AdminGeneratedReportResponse(**build_admin_generated_report(payload.description, db))


@app.get("/admin/reports/download")
def download_admin_report(
    description: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    csv_bytes = build_admin_report_csv(description, db)
    safe_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="reporte-gerencial-{safe_stamp}.csv"'},
    )


@app.post("/admin/simulations/daily-rollover", response_model=AdminDailySimulationResponse)
def run_admin_daily_rollover(
    payload: AdminDailySimulationRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    return AdminDailySimulationResponse(
        **run_daily_operational_simulation(
            db,
            current_user,
            fmora1_clients=payload.fmora1_clients,
            preventivo_clients=payload.preventivo_clients,
            recovery_clients=payload.recovery_clients,
        )
    )


@app.post("/admin/simulations/daily-rollover/preview", response_model=AdminDailySimulationPreviewResponse)
def preview_admin_daily_rollover(
    payload: AdminDailySimulationRequest,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Admin")),
):
    return AdminDailySimulationPreviewResponse(
        **build_daily_operational_simulation_preview(
            db,
            fmora1_clients=payload.fmora1_clients,
            preventivo_clients=payload.preventivo_clients,
            recovery_clients=payload.recovery_clients,
        )
    )


@app.post("/admin/documents/{proposal_id}/discard")
def discard_admin_document_proposal(
    proposal_id: str,
    _: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_DOCUMENT_PROPOSALS.pop(proposal_id, None)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la propuesta solicitada.")
    return {"message": "La propuesta fue descartada correctamente.", "proposal_id": proposal_id}


@app.post("/admin/documents/{proposal_id}/update", response_model=AdminDocumentProposalResponse)
def update_admin_document_proposal(
    proposal_id: str,
    payload: AdminDocumentProposalUpdate,
    _: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_DOCUMENT_PROPOSALS.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la propuesta solicitada.")
    proposal["summary"] = payload.summary
    proposal["suggested_strategies"] = payload.suggested_strategies
    proposal["suggested_channel_rules"] = payload.suggested_channel_rules
    proposal["suggested_sublists"] = payload.suggested_sublists
    proposal["implementation_notes"] = payload.implementation_notes
    proposal["status"] = "AJUSTADA_POR_ADMIN"
    return AdminDocumentProposalResponse(**proposal)


@app.post("/admin/documents/{proposal_id}/apply")
def apply_admin_document_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Admin")),
):
    proposal = ADMIN_DOCUMENT_PROPOSALS.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="No se encontró la propuesta solicitada.")

    created_codes: list[str] = []
    for item in proposal.get("suggested_strategies", []):
        code = item.get("codigo")
        if not code or code == "ESTRATEGIA_PROPUESTA":
            continue
        existing = db.query(Strategy).filter(Strategy.codigo == code).first()
        if existing:
            continue
        strategy = Strategy(
            codigo=code,
            nombre=item.get("nombre") or code,
            descripcion=item.get("descripcion"),
            categoria="COBRANZA",
            orden=(db.query(func.count(Strategy.id)).scalar() or 0) + 1,
            activa=True,
        )
        db.add(strategy)
        created_codes.append(code)

    proposal["status"] = "APLICADA"
    db.add(
        History(
            entidad="estrategias",
            entidad_id=0,
            accion="DOCUMENT_PROPOSAL_APPLIED",
            descripcion=(
                f"Administrador aplicó la propuesta {proposal_id} desde {proposal['file_name']}. "
                f"Estrategias creadas: {', '.join(created_codes) if created_codes else 'ninguna nueva'}."
            ),
            usuario_id=current_user.id,
        )
    )
    db.commit()
    return {
        "message": "Propuesta aplicada correctamente.",
        "proposal_id": proposal_id,
        "created_strategies": created_codes,
        "status": proposal["status"],
    }


def build_training_frame(db: Session) -> pd.DataFrame:
    rows = (
        db.query(
            Cuenta.id.label("cuenta_id"),
            Cuenta.saldo_total,
            Cuenta.saldo_mora,
            Cuenta.dias_mora,
            Cuenta.tasa_interes,
            Cuenta.es_estrafinanciamiento,
            func.count(Pago.id).label("cantidad_pagos"),
            func.coalesce(func.sum(Pago.monto), 0).label("total_pagado"),
        )
        .outerjoin(Pago, Pago.cuenta_id == Cuenta.id)
        .group_by(Cuenta.id)
        .all()
    )

    data = []
    for row in rows:
        total_paid = float(row.total_pagado or 0)
        balance = float(row.saldo_total or 0)
        label = 1 if total_paid >= max(50, balance * 0.08) else 0
        data.append(
            {
                "cuenta_id": row.cuenta_id,
                "saldo_total": balance,
                "saldo_mora": float(row.saldo_mora or 0),
                "dias_mora": int(row.dias_mora or 0),
                "tasa_interes": float(row.tasa_interes or 0),
                "es_estrafinanciamiento": 1 if row.es_estrafinanciamiento else 0,
                "cantidad_pagos": int(row.cantidad_pagos or 0),
                "total_pagado": total_paid,
                "label": label,
            }
        )

    return pd.DataFrame(data)


def train_xgb_model(frame: pd.DataFrame) -> xgb.XGBClassifier:
    model = xgb.XGBClassifier(
        n_estimators=40,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )
    features = frame[
        [
            "saldo_total",
            "saldo_mora",
            "dias_mora",
            "tasa_interes",
            "es_estrafinanciamiento",
            "cantidad_pagos",
            "total_pagado",
        ]
    ]
    labels = frame["label"]
    model.fit(features, labels)
    return model


def build_ai_fallback(account: Cuenta) -> tuple[float, float, str]:
    base_probability = 0.88
    base_probability -= min(account.dias_mora, 240) / 420
    base_probability -= min(float(account.saldo_mora or 0) / max(float(account.saldo_total or 1), 1.0), 1.0) * 0.12
    if account.estado in {"LIQUIDADO", "Z"}:
        base_probability -= 0.12
    if account.es_estrafinanciamiento:
        base_probability -= 0.05
    probability = float(np.clip(base_probability, 0.08, 0.96))
    score = float(np.clip(probability * 100, 0, 100))
    recommendation = (
        "Priorizar gestion digital y recordatorio amistoso."
        if probability >= 0.7
        else "Escalar a llamada y promesa de pago con seguimiento diario."
        if probability >= 0.4
        else "Aplicar estrategia intensiva con supervisor y visita."
    )
    return probability, score, recommendation


def predict_promise_break_probability(
    account: Cuenta,
    pending_promises: list[Promesa],
    callback_at: Optional[datetime],
    client_score_risk: float,
) -> float:
    base = 0.18
    base += min(account.dias_mora, 210) / 260
    base += min(float(account.saldo_mora or 0) / max(float(account.saldo_total or 1), 1.0), 1.0) * 0.18
    base += float(client_score_risk or 0) * 0.15
    if pending_promises:
        base += 0.12
        nearest = min(pending_promises, key=lambda item: item.fecha_promesa)
        days_out = max(0, (nearest.fecha_promesa - datetime.utcnow().date()).days)
        if days_out > 5:
            base += 0.12
        elif days_out <= 2:
            base -= 0.06
    if callback_at:
        base -= 0.05
    if account.estado in {"LIQUIDADO", "Z"}:
        base += 0.08
    return float(np.clip(base, 0.08, 0.97))


def suggest_best_channel(strategy: str, break_probability: float, ai_probability: float, has_phone: bool, has_email: bool) -> str:
    if strategy == "AL_DIA":
        return "Monitoreo sin contacto"
    if strategy == "PREVENTIVO":
        return "Chatbot WhatsApp" if has_phone else "Correo automatizado"
    if strategy in {"FMORA1", "MMORA2"}:
        if ai_probability >= 0.6:
            return "Chatbot WhatsApp + SMS" if has_phone else "Correo + SMS"
        return "WhatsApp asistido" if has_phone else "Correo de seguimiento"
    if strategy in {"HMORA3", "AMORA4"}:
        return "Llamada telefonica + WhatsApp" if has_phone else "Correo con seguimiento humano"
    if strategy in {"BMORA5", "CMORA6", "DMORA7"}:
        return "Llamada telefonica intensiva" if has_phone else "Escalamiento supervisor"
    if strategy == "VAGENCIASEXTERNASINTERNO":
        return "Callbot + llamada humana + WhatsApp" if has_phone else "Callbot + escalamiento interno/externo"
    if strategy == "HMR":
        return "Llamada consultiva" if has_phone else "Correo consultivo"
    return "Llamada telefonica" if break_probability >= 0.55 and has_phone else ("Correo" if has_email else "Gestion manual")


def build_copilot_guidance(
    client: Cliente,
    strategy: str,
    best_channel: str,
    break_probability: float,
    ai_probability: float,
    pending_promises: list[Promesa],
    total_outstanding: float,
) -> tuple[str, str]:
    if strategy == "AL_DIA":
        next_action = "Mantener monitoreo, no contactar y esperar entrada a preventivo si aplica."
        talk_track = (
            f"{client.nombres} se mantiene al día. No se recomienda contacto en esta etapa; solo monitoreo preventivo y seguimiento silencioso."
        )
    elif strategy == "PREVENTIVO":
        next_action = "Enviar recordatorio preventivo y ofrecer link de pago inmediato."
        talk_track = (
            f"Hola {client.nombres}, te contactamos para ayudarte a mantener tu cuenta al dia. "
            f"Hoy la mejor opcion es cerrar el pago por un canal rapido y sin friccion."
        )
    elif strategy in {"FMORA1", "MMORA2"}:
        next_action = "Abrir con canal digital, validar intencion y capturar promesa corta."
        talk_track = (
            f"Hola {client.nombres}, vemos una mora temprana en tu cuenta. "
            f"Podemos apoyarte a normalizarla hoy con una promesa breve o un pago parcial guiado."
        )
    elif strategy in {"HMORA3", "AMORA4"}:
        next_action = "Priorizar llamada humana, aislar objecion y negociar fecha cercana."
        talk_track = (
            f"Hola {client.nombres}, tu cuenta ya requiere una regularizacion prioritaria. "
            f"Quiero ayudarte a definir un compromiso realista y evitar mayor escalamiento."
        )
    elif strategy in {"BMORA5", "CMORA6", "DMORA7"}:
        next_action = "Gestion agresiva con llamada, cierre de promesa y posible escalamiento."
        talk_track = (
            f"Hola {client.nombres}, tu saldo vencido requiere atencion inmediata. "
            f"Necesitamos acordar hoy una accion concreta para detener el deterioro de la cuenta."
        )
    elif strategy == "VAGENCIASEXTERNASINTERNO":
        next_action = "Abrir con callbot, escalar a llamada humana y reforzar por WhatsApp si hay contacto."
        talk_track = (
            f"Hola {client.nombres}, tu caso se encuentra en Recovery. "
            f"Vamos a validar respuesta inmediata, ubicar capacidad real de pago y direccionar el placement correcto."
        )
    elif strategy == "HMR":
        next_action = "Explorar herramienta de mitigacion y validar capacidad de pago."
        talk_track = (
            f"Hola {client.nombres}, identificamos que tu caso puede optar por una alternativa de solucion. "
            f"Revisemos juntos una salida viable segun tu capacidad actual."
        )
    else:
        next_action = "Contactar, validar situacion y decidir siguiente escalamiento."
        talk_track = f"Hola {client.nombres}, te contactamos para revisar el estado actual de tu cuenta y definir el siguiente paso."

    if pending_promises:
        next_action += " Revisar primero promesa existente antes de crear una nueva."
    if break_probability >= 0.65:
        next_action += " Riesgo alto de incumplimiento: exigir fecha corta y seguimiento diario."
    elif ai_probability >= 0.7:
        next_action += " Alta probabilidad de recuperacion: priorizar cierre en este contacto."
    talk_track += f" Canal sugerido por IA: {best_channel}. Saldo visible aproximado: {total_outstanding:,.2f}."
    return next_action, talk_track


def derive_worklist_sublist(
    client: Cliente,
    accounts: list[Cuenta],
    pending_promises: list[Promesa],
    callback_at: Optional[datetime],
    review_pending: bool,
) -> tuple[str, str]:
    total_due = sum(float(account.saldo_mora or 0) for account in accounts)
    if review_pending:
        return "REVSUP", "Revision supervisor por acuerdo fuera de politica."
    if callback_at:
        return "CALLBACK", "Cliente con llamada reprogramada para seguimiento."
    if pending_promises:
        return "PROMESAS", "Cliente con acuerdo pendiente de cumplimiento."
    if not client.telefono and not client.email:
        return "NOCONTACTO", "Cliente sin datos de contacto efectivos."
    if total_due <= 175:
        return "F02SALDOSBAJOS", "Cliente con saldo vencido bajo para barrido de recuperacion temprana."
    if any(account.dias_mora >= 151 for account in accounts):
        return "ALTOIMP", "Cliente en tramo severo con enfoque intensivo."
    return "QALDIA", "Cliente en flujo operativo general de la estrategia."


def format_external_group_id(placement_code: str, agency_slot: int) -> str:
    suffix = PLACEMENT_EXTERNAL_SUFFIX.get(placement_code, "0")
    return f"{placement_code}A{agency_slot:02d}{suffix}"


def format_internal_group_id(placement_code: str, worklist_slot: int) -> str:
    return f"{placement_code}INT{worklist_slot:02d}"


def extract_slot_from_group_id(group_id: Optional[str], scope: Optional[str]) -> Optional[int]:
    if not group_id:
        return None
    if scope == "EXTERNO":
        match = re.search(r"A(\d{2})\d$", group_id)
    else:
        match = re.search(r"INT(\d{2})$", group_id)
    return int(match.group(1)) if match else None


def next_placement_code(previous_history: Optional[AssignmentHistory]) -> str:
    previous_code = (previous_history.placement_code or "").upper() if previous_history else ""
    if previous_code in PLACEMENT_SEQUENCE:
        current_index = PLACEMENT_SEQUENCE.index(previous_code)
        return PLACEMENT_SEQUENCE[min(current_index + 1, len(PLACEMENT_SEQUENCE) - 1)]
    return "V11"


def choose_next_group_id(placement_code: str, channel_scope: str, previous_history: Optional[AssignmentHistory]) -> str:
    previous_slot = extract_slot_from_group_id(previous_history.group_id if previous_history else None, channel_scope)
    if channel_scope == "EXTERNO":
        if previous_slot in EXTERNAL_AGENCY_SLOTS:
            next_slot = EXTERNAL_AGENCY_SLOTS[(EXTERNAL_AGENCY_SLOTS.index(previous_slot) + 1) % len(EXTERNAL_AGENCY_SLOTS)]
        else:
            next_slot = EXTERNAL_AGENCY_SLOTS[0]
        return format_external_group_id(placement_code, next_slot)

    if previous_slot in INTERNAL_WORKLIST_SLOTS:
        next_slot = INTERNAL_WORKLIST_SLOTS[(INTERNAL_WORKLIST_SLOTS.index(previous_slot) + 1) % len(INTERNAL_WORKLIST_SLOTS)]
    else:
        next_slot = INTERNAL_WORKLIST_SLOTS[0]
    return format_internal_group_id(placement_code, next_slot)


def derive_assignment_distribution(
    strategy_code: Optional[str],
    user: Optional[Usuario],
    previous_history: Optional[AssignmentHistory] = None,
    seed_value: Optional[int] = None,
) -> tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[str]]:
    normalized = (strategy_code or "").upper()
    if normalized != "VAGENCIASEXTERNASINTERNO":
        return None, None, None, None, None

    if previous_history:
        placement_code = next_placement_code(previous_history)
        channel_scope = previous_history.channel_scope or "EXTERNO"
        group_id = choose_next_group_id(placement_code, channel_scope, previous_history)
    else:
        seed_index = max(0, int(seed_value or 0))
        placement_code = PLACEMENT_SEQUENCE[seed_index % len(PLACEMENT_SEQUENCE)]
        channel_scope = "EXTERNO"
        group_id = format_external_group_id(placement_code, EXTERNAL_AGENCY_SLOTS[seed_index % len(EXTERNAL_AGENCY_SLOTS)])
    assigned_share_pct = 100.0 if channel_scope == "EXTERNO" else 20.0
    return placement_code, channel_scope, assigned_share_pct, None, group_id


def record_assignment_history(
    db: Session,
    client: Cliente,
    assignment: WorklistAssignment,
    *,
    strategy_code: Optional[str],
    notes: str,
    user: Optional[Usuario] = None,
) -> None:
    accounts = list(client.cuentas or db.query(Cuenta).filter(Cuenta.cliente_id == client.id).all())
    pending_promises = (
        db.query(Promesa)
        .join(Cuenta, Cuenta.id == Promesa.cuenta_id)
        .filter(Cuenta.cliente_id == client.id, Promesa.estado.in_(["PENDIENTE", "REVISION_SUPERVISOR"]))
        .all()
    )
    callback_history = (
        db.query(History)
        .filter(History.entidad == "clientes", History.entidad_id == client.id, History.accion == "CALLBACK_PROGRAMADO")
        .order_by(History.created_at.desc())
        .first()
    )
    callback_at, _ = parse_callback_description(callback_history.descripcion if callback_history else None)
    review_pending = any(item.estado == "REVISION_SUPERVISOR" for item in pending_promises)
    sublista_codigo, _ = derive_worklist_sublist(client, accounts, pending_promises, callback_at, review_pending)
    total_due = round(sum(float(account.saldo_mora or 0) for account in accounts), 2)
    max_days_past_due = max([int(account.dias_mora or 0) for account in accounts], default=0)
    status_snapshot = max(
        [(account.estado or "").upper() for account in accounts],
        key=lambda value: (value in {"Z", "LIQUIDADO"}, value in {"ACTIVA", "VIGENTE"}, value),
        default=None,
    )
    previous_history = (
        db.query(AssignmentHistory)
        .filter(AssignmentHistory.cliente_id == client.id)
        .order_by(AssignmentHistory.start_at.desc(), AssignmentHistory.id.desc())
        .first()
    )
    placement_code, channel_scope, assigned_share_pct, efficiency_pct, group_id = derive_assignment_distribution(
        strategy_code,
        user,
        previous_history,
        assignment.id or client.id,
    )
    if not group_id:
        group_id = user.username.upper() if user else None

    (
        db.query(AssignmentHistory)
        .filter(AssignmentHistory.cliente_id == client.id, AssignmentHistory.is_current.is_(True))
        .update(
            {
                AssignmentHistory.is_current: False,
                AssignmentHistory.end_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    db.add(
        AssignmentHistory(
            cliente_id=client.id,
            usuario_id=assignment.usuario_id,
            assignment_id=assignment.id,
            strategy_code=strategy_code,
            placement_code=placement_code,
            channel_scope=channel_scope,
            group_id=group_id,
            sublista_codigo=sublista_codigo,
            assigned_share_pct=assigned_share_pct,
            efficiency_pct=efficiency_pct,
            tenure_days=120,
            minimum_payment_to_progress=10,
            segment_snapshot=client.segmento,
            account_status_snapshot=status_snapshot,
            max_days_past_due_snapshot=max_days_past_due,
            total_due_snapshot=total_due,
            notes=notes,
            start_at=datetime.now(timezone.utc),
            is_current=True,
        )
    )


@app.on_event("startup")
def hydrate_assignment_history() -> None:
    return None



@app.get("/ai/predictions/{account_id}", response_model=PredictionResponse)
def predict_payment_probability(
    account_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    frame = build_training_frame(db)
    if frame.empty:
        raise HTTPException(status_code=404, detail="No hay datos suficientes para entrenar el modelo.")

    row = frame[frame["cuenta_id"] == account_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada en el dataset.")

    if len(frame["label"].unique()) == 1:
        probability = 0.85 if int(frame["label"].iloc[0]) == 1 else 0.15
        score = 50.0
    else:
        model = train_xgb_model(frame)
        feature_row = row[
            [
                "saldo_total",
                "saldo_mora",
                "dias_mora",
                "tasa_interes",
                "es_estrafinanciamiento",
                "cantidad_pagos",
                "total_pagado",
            ]
        ]
        probability = float(model.predict_proba(feature_row)[0][1])
        score = float(np.clip(probability * 100, 0, 100))

    recommendation = (
        "Priorizar gestion digital y recordatorio amistoso."
        if probability >= 0.7
        else "Escalar a llamada y promesa de pago con seguimiento diario."
        if probability >= 0.4
        else "Aplicar estrategia intensiva con supervisor y visita."
    )

    existing = db.query(PrediccionIA).filter(PrediccionIA.cuenta_id == account_id).first()
    if existing:
        existing.probabilidad_pago_30d = probability
        existing.score_modelo = score
        existing.recomendacion = recommendation
        existing.fecha_prediccion = datetime.now(timezone.utc)
    else:
        db.add(
            PrediccionIA(
                cuenta_id=account_id,
                probabilidad_pago_30d=probability,
                score_modelo=score,
                recomendacion=recommendation,
            )
        )
    db.commit()

    return PredictionResponse(
        cuenta_id=account_id,
        probabilidad_pago_30d=round(probability, 4),
        score_modelo=round(score, 2),
        recomendacion=recommendation,
    )
