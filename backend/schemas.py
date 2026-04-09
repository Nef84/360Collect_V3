from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Auth ─────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserRead"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Users ────────────────────────────────────────────────────────────────────

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


# ── Clients ──────────────────────────────────────────────────────────────────

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


# ── Accounts ─────────────────────────────────────────────────────────────────

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


# ── Payments ─────────────────────────────────────────────────────────────────

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


# ── AI ───────────────────────────────────────────────────────────────────────

class PredictionResponse(BaseModel):
    cuenta_id: int
    probabilidad_pago_30d: float
    score_modelo: float
    recomendacion: str


# ── Collector ────────────────────────────────────────────────────────────────

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


class DemographicUpdate(BaseModel):
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    phones: list["DemographicPhoneItem"] = Field(default_factory=list)
    emails: list["DemographicEmailItem"] = Field(default_factory=list)
    addresses: list["DemographicAddressItem"] = Field(default_factory=list)


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


class DemographicProfileRead(BaseModel):
    cliente_id: int
    phones: list[DemographicPhoneItem] = Field(default_factory=list)
    emails: list[DemographicEmailItem] = Field(default_factory=list)
    addresses: list[DemographicAddressItem] = Field(default_factory=list)


# ── Supervisor ───────────────────────────────────────────────────────────────

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


# ── Admin ────────────────────────────────────────────────────────────────────

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


class WorklistGroupRead(BaseModel):
    strategy_code: Optional[str] = None
    placement_code: Optional[str] = None
    group_id: Optional[str] = None
    channel_scope: Optional[str] = None
    client_count: int
    display_name: str


class WorklistGroupAssignRequest(BaseModel):
    user_id: int
    group_id: str = Field(..., min_length=3, max_length=40)
    strategy_code: Optional[str] = None
    placement_code: Optional[str] = None
    reassign_existing: bool = True


class WorklistGroupUnassignRequest(BaseModel):
    user_id: int
    group_id: str = Field(..., min_length=3, max_length=40)
    strategy_code: Optional[str] = None
    placement_code: Optional[str] = None


class SupervisorCollectorAssignRequest(BaseModel):
    supervisor_id: int
    collector_id: int


class SupervisorCollectorAssignmentRead(BaseModel):
    supervisor: UserRead
    collectors: list[UserRead]


class AdminOverviewResponse(BaseModel):
    strategies: list[StrategyRead]
    collectors: list[UserRead]
    supervisors: list[UserRead]
    total_clients: int
    assigned_clients: int
    unassigned_clients: int
    hmr_clients: int
    omnichannel: dict
    alerts: list[dict] = Field(default_factory=list)


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
    recovery_clients: int = Field(default=1000, ge=0, le=10000)


class AdminDailySimulationResponse(BaseModel):
    simulation_key: str
    aged_accounts: int
    inserted_fmora1_clients: int
    inserted_preventivo_clients: int
    inserted_recovery_clients: int = 0
    simulated_payments: int = 0
    fully_cured_accounts: int = 0
    recovery_rotations: int = 0
    total_clients: int
    total_accounts: int
    message: str


class AdminDailySimulationPreviewResponse(BaseModel):
    simulation_key: str
    already_applied_today: bool = False
    aged_accounts: int
    inserted_fmora1_clients: int
    inserted_preventivo_clients: int
    inserted_recovery_clients: int = 0
    simulated_payments: int = 0
    fully_cured_accounts: int = 0
    recovery_rotations: int = 0
    projected_total_clients: int
    projected_total_accounts: int
    warnings: list[str] = Field(default_factory=list)
    message: str


class RecoveryVintagePlacementRead(BaseModel):
    placement_code: str
    client_count: int
    paying_clients_120d: int
    total_paid_120d: float
    total_balance: float = 0
    total_due: float = 0
    v11_eligible_clients: int
    best_group_id: Optional[str] = None
    best_group_rate_120d: float = 0
    lagging_group_id: Optional[str] = None
    lagging_group_rate_120d: float = 0
    agencies: list["RecoveryVintageAgencyRead"] = Field(default_factory=list)


class RecoveryVintageAgencyRead(BaseModel):
    group_id: str
    channel_scope: Optional[str] = None
    client_count: int
    paying_clients_120d: int
    total_paid_120d: float
    total_balance: float = 0
    total_due: float = 0
    v11_eligible_clients: int
    payment_rate_120d: float


class RecoveryVintageClientRead(BaseModel):
    client_id: int
    identity_code: str
    client_name: str
    separation_date: date
    current_status: Optional[str] = None
    current_placement: Optional[str] = None
    current_group_id: Optional[str] = None
    current_scope: Optional[str] = None
    account_count: int
    total_balance: float = 0
    total_due: float = 0
    qualifying_payment_count_120d: int
    total_paid_120d: float
    max_payment_120d: float
    last_payment_date: Optional[datetime] = None
    movement_path: str
    qualifies_for_v11: bool


class RecoveryVintageOverviewResponse(BaseModel):
    year: int
    lookback_days: int
    payment_threshold: float
    total_clients: int
    total_balance: float = 0
    total_due: float = 0
    active_payers_120d: int
    v11_clients: int
    placements_tracked: int
    placements: list[RecoveryVintagePlacementRead]
    sample_clients: list[RecoveryVintageClientRead]


class RecoveryVintageCompareItem(BaseModel):
    year: int
    total_clients: int
    total_balance: float = 0
    total_due: float = 0
    active_payers_120d: int
    placements_tracked: int
    placement_distribution: dict[str, int] = Field(default_factory=dict)


class RecoveryVintageCompareResponse(BaseModel):
    years: list[int]
    items: list[RecoveryVintageCompareItem]


class AdminOmnichannelConfigUpdate(BaseModel):
    whatsapp_bot_enabled: bool
    email_enabled: bool
    callbot_enabled: bool
    inbound_bot_enabled: bool
    automation_enabled: bool
    webhooks_configured: bool
    template_library_ready: bool
    # Twilio (WhatsApp + SMS + Voice)
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_demo_phone: Optional[str] = None
    twilio_sms_from: Optional[str] = None
    twilio_voice_from: Optional[str] = None
    callbot_webhook_url: Optional[str] = None
    # Email — Resend (gratis)
    resend_api_key: Optional[str] = None
    email_from: Optional[str] = None
    # Email — SMTP fallback
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    # SMS
    sms_provider: Optional[str] = "textbelt"  # "textbelt" | "twilio"
    textbelt_api_key: Optional[str] = "textbelt"
    notes: Optional[str] = None


class AdminEmailDemoRequest(BaseModel):
    to_email: str = Field(..., min_length=5, max_length=180)
    client_id: Optional[int] = None
    strategy_code: Optional[str] = None
    custom_subject: Optional[str] = None
    custom_html: Optional[str] = None
    use_smtp: bool = False


class AdminSMSDemoRequest(BaseModel):
    to_phone: str = Field(..., min_length=8, max_length=30)
    client_id: Optional[int] = None
    strategy_code: Optional[str] = None
    custom_message: Optional[str] = None
    provider: Optional[str] = "textbelt"  # "textbelt" | "twilio"


class AdminCallbotDemoRequest(BaseModel):
    to_phone: str = Field(..., min_length=8, max_length=30)
    client_id: Optional[int] = None
    strategy_code: Optional[str] = None


class AdminWhatsAppDemoSendRequest(BaseModel):
    to_phone: str = Field(..., min_length=8, max_length=30)
    client_id: Optional[int] = None
    strategy_code: Optional[str] = None
    custom_message: Optional[str] = None


class AdminOmnichannelPreviewResponse(BaseModel):
    channel: str
    strategy_code: str
    client_name: Optional[str] = None
    identity_code: Optional[str] = None
    account_reference: Optional[str] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    message: Optional[str] = None


class AdminAssistantRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=1000)
    apply_change: bool = False


class AdminAssistantResponse(BaseModel):
    action_code: str
    interpreted_message: str
    response_message: str
    requires_confirmation: bool = False
    can_apply: bool = False
    executed: bool = False
    data: dict = Field(default_factory=dict)


class AdminSqlQueryRequest(BaseModel):
    query: str = Field(..., min_length=6, max_length=12000)
    max_rows: int = Field(default=200, ge=1, le=1000)


class AdminSqlQueryResponse(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    duration_ms: int = 0
    normalized_query: str = ""


class AdminHistoryEventRead(BaseModel):
    id: int
    entidad: str
    entidad_id: int
    accion: str
    descripcion: Optional[str] = None
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
