import { useEffect, useMemo, useRef, useState } from "react";
import brandLogo from "./assets/collectplus-logo-final-cropped.png";

const API_URL = import.meta.env.VITE_API_URL || "/api";

const roleText = {
  Admin: "Control de estrategias, asignacion de listas de trabajo, usuarios y operacion omnicanal.",
  Collector: "Agenda diaria, cartera asignada y captura de gestiones de cobranza.",
  Supervisor: "Seguimiento por bucket, productividad y alertas operativas.",
  Auditor: "Revision de trazabilidad, cambios y cumplimiento.",
  GestorUsuarios: "Altas, roles, permisos y estado de usuarios."
};

const strategyLabels = {
  AL_DIA: "Al dia",
  PREVENTIVO: "Preventivo",
  FMORA1: "F Mora 1",
  MMORA2: "M Mora 2",
  HMORA3: "H Mora 3",
  AMORA4: "A Mora 4",
  BMORA5: "B Mora 5",
  CMORA6: "C Mora 6",
  DMORA7: "D Mora 7",
  VAGENCIASEXTERNASINTERNO: "Recovery",
  HMR: "Herramientas HMR"
};

const strategyDescriptions = {
  AL_DIA: "Cartera al corriente con seguimiento fino y deteccion temprana.",
  PREVENTIVO: "Vencimiento reciente antes del corte. Prioriza contencion y recordatorio.",
  FMORA1: "Mora temprana con alta probabilidad de recuperacion rapida.",
  MMORA2: "Seguimiento estructurado con promesas controladas y callbacks.",
  HMORA3: "Tramo intermedio con mayor friccion y necesidad de contacto efectivo.",
  AMORA4: "Riesgo alto con presion comercial y control supervisor.",
  BMORA5: "Cartera avanzada que requiere gestion intensiva y rutas alternas.",
  CMORA6: "Tramo severo con foco en recuperacion agresiva y mitigacion.",
  DMORA7: "Mas de 190 dias en vigente. Priorizacion de maxima severidad.",
  VAGENCIASEXTERNASINTERNO: "Segmento Recovery con placements y listas internas/externas por antiguedad o estatus.",
  HMR: "Clientes con opciones de mitigacion y herramientas de solucion."
};

const moraReasonOptions = [
  "Desempleo",
  "Disminucion de ingresos",
  "Olvido de fecha",
  "Problemas de salud",
  "Sobreendeudamiento",
  "Inconformidad con el producto",
  "Pendiente de pago de tercero",
  "Viaje o ausencia",
  "Sin contacto efectivo",
  "Emergencia familiar",
  "Atraso temporal de liquidez",
  "Otro"
];

function currency(value) {
  return `$${Number(value || 0).toLocaleString("es-SV", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function getClientOperationalStatus(client) {
  if (!client) return { label: "Sin estado", tone: "bg-slate-100 text-slate-700" };
  if (client.requires_supervisor_review) return { label: "Revision Supervisor", tone: "bg-orange-100 text-orange-700" };
  if (client.next_callback_at) return { label: "Llamada pendiente", tone: "bg-amber-100 text-amber-700" };
  if (client.worked_today) return { label: "Gestionado", tone: "bg-emerald-100 text-emerald-700" };
  return { label: "Pendiente de gestion", tone: "bg-slate-100 text-slate-700" };
}

function normalizeLookupValue(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

const strategyStateCodes = {
  AL_DIA: "A00",
  PREVENTIVO: "P00",
  FMORA1: "F01",
  MMORA2: "F02",
  HMORA3: "F03",
  AMORA4: "F04",
  BMORA5: "F05",
  CMORA6: "F06",
  DMORA7: "F07",
  VAGENCIASEXTERNASINTERNO: "X01",
  HMR: "HMR",
};

function getSearchModeLabel(mode) {
  const labels = {
    all: "Busqueda general",
    unico: "Numero Unico",
    dui: "DUI",
    nombre: "Nombre",
    cuenta: "Numero de cuenta",
    plastico: "Numero de plastico",
    telefono: "Numero de telefono",
  };
  return labels[mode] || "Busqueda general";
}

function getSubgroupFamilyLabel(subgroupKey) {
  if (!subgroupKey) return "General";
  if (subgroupKey.startsWith("PLACEMENT_")) return subgroupKey.replace("PLACEMENT_", "").replace(/_/g, " ");
  if (subgroupKey.endsWith("HIPOTECAS")) return "Hipotecas";
  if (subgroupKey.endsWith("PIL")) return "Prestamos PIL";
  if (subgroupKey.endsWith("CARDS")) return "Tarjetas";
  return "General";
}

function formatChannelErrorMessage(raw) {
  if (!raw) return "No se pudo completar la solicitud.";
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    const first = raw[0];
    if (typeof first === "string") return first;
    if (first?.msg) return first.msg;
  }
  if (typeof raw === "object") {
    if (typeof raw.detail === "string") return raw.detail;
    if (Array.isArray(raw.detail)) {
      const first = raw.detail[0];
      if (typeof first === "string") return first;
      if (first?.msg) return first.msg;
    }
    if (typeof raw.msg === "string") return raw.msg;
    try {
      return JSON.stringify(raw);
    } catch {
      return "No se pudo completar la solicitud.";
    }
  }
  return String(raw);
}

function buildEmptyDemographicProfile(baseClient = null) {
  return {
    cliente_id: baseClient?.id || null,
    phones: baseClient?.telefono ? [{ id: null, phone_type: "CEL", value: baseClient.telefono, is_primary: true }] : [{ id: null, phone_type: "CEL", value: "", is_primary: true }],
    emails: baseClient?.email ? [{ id: null, value: baseClient.email, is_primary: true }] : [],
    addresses: baseClient?.direccion ? [{ id: null, address_type: "CASA", value: baseClient.direccion, is_primary: true }] : [],
  };
}

function formatDisplayIdentityCode(client) {
  if (!client) return "00000000000";
  const explicitValue = String(client.identity_code || client.numero_unico || "").trim();
  if (explicitValue) return explicitValue;
  const codeDigits = String(client.identity_code || "").replace(/\D/g, "");
  if (codeDigits) return codeDigits.slice(-11).padStart(11, "0");
  if (client.id != null) return String(client.id).padStart(11, "0");
  return "00000000000";
}

function formatOmnichannelClientOption(client) {
  if (!client) return "Cliente";
  const numeroUnico = formatDisplayIdentityCode(client);
  const nombre = [client.nombres, client.apellidos].filter(Boolean).join(" ").trim();
  return `${numeroUnico} · ${nombre || "Cliente sin nombre"}`;
}

function BrandBadge({ compact = false, dark = false }) {
  return (
    <div className={`flex items-center gap-2 ${compact ? "" : "mb-6"}`}>
      <BrandLogo size={compact ? "compact" : "default"} align="center" />
      {!compact && (
        <div className="ml-1">
          <p className="text-xs uppercase tracking-[0.32em] text-mint font-semibold">Plataforma de cobranza</p>
          <p className="text-sm text-white/80 leading-tight">IA · Omnicanalidad · Control total</p>
        </div>
      )}
    </div>
  );
}

function BrandLogo({ size = "header", align = "left", className = "" }) {
  const sizeMap = {
    compact: "h-[5.2rem] w-[250px]",
    default: "h-[8.8rem] w-[470px]",
    hero: "h-[10rem] w-[540px]",
    mobile: "h-[8.4rem] w-[450px]",
    header: "h-[7rem] w-[400px]",
    headerLg: "h-[8.4rem] w-[450px]",
  };
  const objectPositionMap = {
    compact: "54% center",
    default: "55% center",
    hero: "57% center",
    mobile: "56% center",
    header: "55% center",
    headerLg: "56% center",
  };
  const scaleMap = {
    compact: "scale(1.12)",
    default: "scale(1.13)",
    hero: "scale(1.16)",
    mobile: "scale(1.15)",
    header: "scale(1.12)",
    headerLg: "scale(1.14)",
  };
  const resolvedSize = sizeMap[size] ? size : "header";
  const objectPosition = align === "center" ? "center center" : (objectPositionMap[resolvedSize] || "55% center");

  return (
    <div className={`relative ${sizeMap[resolvedSize]} ${className}`}>
      <img
        src={brandLogo}
        alt="360CollectPlus"
        className="relative z-10 h-full w-full object-contain"
        style={{
          filter: "brightness(1.12) contrast(1.08) saturate(1.1) drop-shadow(0 16px 30px rgba(88, 232, 219, 0.22))",
          opacity: 1,
          transform: scaleMap[resolvedSize] || "scale(1.12)",
          transformOrigin: align === "center" ? "center center" : "center center",
          objectPosition,
        }}
      />
      <div
        className="pointer-events-none absolute inset-0 z-20"
        style={{
          background:
            "radial-gradient(circle at 38% 42%, rgba(255,255,255,0.4) 0%, rgba(180,245,255,0.2) 9%, rgba(180,245,255,0.08) 17%, transparent 28%)",
          mixBlendMode: "screen",
          opacity: 0.9,
        }}
      />
    </div>
  );
}

function StatCard({ title, value, detail, accent = "teal", icon = null }) {
  const accentMap = {
    teal:  "from-teal/10 to-ocean/5 border-teal/20",
    green: "from-green-50 to-emerald-50/80 border-green-100",
    amber: "from-amber-50 to-orange-50/80 border-amber-100",
    red:   "from-red-50 to-rose-50/80 border-red-100",
    blue:  "from-blue-50 to-sky-50/80 border-blue-100",
    purple:"from-purple-50 to-violet-50/80 border-purple-100",
  };
  const textMap = {
    teal:  "text-teal",
    green: "text-green-600",
    amber: "text-amber-600",
    red:   "text-red-600",
    blue:  "text-blue-600",
    purple:"text-purple-600",
  };
  return (
    <div className={`card-hover rounded-2xl border bg-gradient-to-br p-5 shadow-card ${accentMap[accent] || accentMap.teal}`}>
      <div className="flex items-start justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{title}</p>
        {icon && <span className="text-xl opacity-70">{icon}</span>}
      </div>
      <p className={`mt-2 text-3xl font-bold leading-none ${textMap[accent] || textMap.teal}`}>{value}</p>
      <p className="mt-2 text-xs leading-5 text-slate-500">{detail}</p>
    </div>
  );
}

function DataTable({ title, rows, columns, emptyText, compact = false }) {
  return (
    <section className="glass rounded-2xl border border-white/70 shadow-card overflow-hidden">
      <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-slate-100">
        <h3 className="text-base font-bold text-ink">{title}</h3>
        <span className="rounded-full bg-ocean/10 px-3 py-1 text-xs font-bold text-ocean">
          {rows.length.toLocaleString()} reg.
        </span>
      </div>
      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center px-6">
          <p className="text-4xl opacity-30">📋</p>
          <p className="mt-3 text-sm font-medium text-slate-400">{emptyText || "Sin registros"}</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left">
            <thead>
              <tr className="bg-slate-50/80">
                {columns.map((column) => (
                  <th key={column.key} className="px-4 py-3 text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {rows.map((row, index) => (
                <tr key={row.id || `${title}-${index}`} className="hover:bg-teal/[0.03] transition-colors">
                  {columns.map((column) => (
                    <td key={column.key} className={`px-4 text-slate-700 ${compact ? "py-2 text-xs" : "py-3 text-sm"}`}>
                      {column.render ? column.render(row[column.key], row) : row[column.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LoginForm({ onLogin, loading, error }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("Password123!");

  const features = [
    { icon: "🧠", label: "IA Predictiva", desc: "XGBoost por cliente" },
    { icon: "📱", label: "Omnicanal", desc: "WhatsApp · Email · SMS · Voz" },
    { icon: "📊", label: "Tiempo Real", desc: "Métricas en vivo" },
    { icon: "🔒", label: "Seguridad", desc: "JWT · Roles · Auditoría" },
  ];

  return (
    <div className="flex min-h-screen items-stretch">
      {/* Left panel */}
      <div className="login-gradient hidden w-[52%] flex-col justify-between p-12 lg:flex relative">
        <div className="relative z-10">
          <BrandLogo size="hero" />
          <div className="mt-8">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-teal">Plataforma de cobranza omnicanal</p>
            <h1 className="mt-3 text-[2.6rem] font-bold leading-[1.15] text-white">
              Gestión inteligente.<br />
              <span className="text-teal">Resultados reales.</span>
            </h1>
            <p className="mt-4 max-w-md text-base leading-7 text-slate-300">
              Organiza estrategias por tramo de mora, prioriza la cartera con IA y da seguimiento a cada gestión con trazabilidad completa.
            </p>
          </div>
          <div className="mt-10 grid grid-cols-2 gap-3">
            {features.map(f => (
              <div key={f.label} className="rounded-2xl border border-white/10 bg-white/8 px-4 py-4 backdrop-blur-sm">
                <p className="text-2xl">{f.icon}</p>
                <p className="mt-2 text-sm font-semibold text-white">{f.label}</p>
                <p className="mt-0.5 text-xs text-slate-400">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="relative z-10">
          <div className="mt-8 flex items-center gap-3 rounded-2xl border border-white/10 bg-white/6 px-5 py-4">
            <div className="h-2 w-2 rounded-full bg-teal pulse-dot" />
            <p className="text-sm text-slate-300">Sistema operativo · <span className="text-teal font-medium">API conectada</span></p>
          </div>
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="flex flex-1 flex-col items-center justify-center bg-white px-8 py-12">
        {/* Mobile logo */}
        <div className="mb-8 lg:hidden">
          <BrandLogo size="mobile" align="center" className="mx-auto" />
        </div>

        <div className="w-full max-w-sm fade-in">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-ocean">Bienvenido de vuelta</p>
          <h2 className="mt-2 text-3xl font-bold text-ink">Iniciar sesión</h2>
          <p className="mt-1 text-sm text-slate-400">Ingresa tus credenciales para continuar</p>

          <div className="mt-8 space-y-5">
            <div>
              <label className="block text-sm font-semibold text-slate-600 mb-1.5">Usuario</label>
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-ink placeholder-slate-400 transition-all"
                placeholder="usuario@empresa.com"
                autoComplete="username"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-600 mb-1.5">Contraseña</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={e => e.key === "Enter" && onLogin({ username, password })}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-ink placeholder-slate-400 transition-all"
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>
          </div>

          {error && (
            <div className="mt-4 flex items-start gap-3 rounded-xl bg-red-50 border border-red-100 px-4 py-3">
              <span className="text-red-500 mt-0.5">⚠</span>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <button
            onClick={() => onLogin({ username, password })}
            disabled={loading}
            className="mt-6 w-full rounded-xl bg-ink py-3.5 text-sm font-bold text-white shadow-card transition-all hover:bg-brand-blue hover:shadow-teal disabled:opacity-60"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4 text-white" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                Ingresando...
              </span>
            ) : "Ingresar al sistema →"}
          </button>

          <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
            <p className="text-xs font-semibold text-slate-500 mb-2">Credenciales demo:</p>
            <div className="grid grid-cols-2 gap-1 text-xs text-slate-600">
              <span>Admin: <code className="text-ocean font-mono">admin</code></span>
              <span>Collector: <code className="text-ocean font-mono">collector1</code></span>
              <span>Supervisor: <code className="text-ocean font-mono">supervisor1</code></span>
              <span className="col-span-2">Contraseña: <code className="text-ocean font-mono">Password123!</code></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CollectorWorkspace({ auth, portfolio, onLogout, onRefresh, onSubmitManagement, onLoadDemographics, onUpdateDemographics, onLookupClient, saving, error, success, exitLabel = "Cerrar sesión" }) {
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [selectedSubgroup, setSelectedSubgroup] = useState(null);
  const [activeTab, setActiveTab] = useState("deudor");
  const [queueMode, setQueueMode] = useState(false);
  const [queueIndex, setQueueIndex] = useState(0);
  const [queueSearchInput, setQueueSearchInput] = useState("");
  const [queueSearch, setQueueSearch] = useState("");
  const [queueSearchMode, setQueueSearchMode] = useState("all");
  const [managementSearch, setManagementSearch] = useState("");
  const [managementPage, setManagementPage] = useState(1);
  const [managementForm, setManagementForm] = useState({
    account_id: "",
    account_ids: [],
    contact_channel: "Llamada",
    called_phone: "",
    rdm: "",
    management_type: "Llamada de cobranza",
    result: "Contactado",
    notes: "",
    promise_date: "",
    promise_amount: "",
    callback_at: ""
  });
  const [demographicForm, setDemographicForm] = useState({ telefono: "", email: "", direccion: "" });
  const [collapsedSections, setCollapsedSections] = useState({
    client: false,
    finance: false,
    actionForm: false,
    history: false,
  });
  const [demographicModalOpen, setDemographicModalOpen] = useState(false);
  const [demographicModalLoading, setDemographicModalLoading] = useState(false);
  const [demographicModalData, setDemographicModalData] = useState(buildEmptyDemographicProfile());
  const [lookupClient, setLookupClient] = useState(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const managementSearchRef = useRef(null);
  const scrollToTop = () => window.scrollTo({ top: 0, behavior: "smooth" });
  const toggleSection = (sectionKey) =>
    setCollapsedSections((current) => ({ ...current, [sectionKey]: !current[sectionKey] }));
  const openDemographicEditor = async () => {
    if (!activeClient) return;
    setDemographicModalLoading(true);
    setDemographicModalOpen(true);
    try {
      const profile = await onLoadDemographics(activeClient);
      setDemographicModalData(profile || buildEmptyDemographicProfile(activeClient));
    } catch {
      setDemographicModalData(buildEmptyDemographicProfile(activeClient));
    } finally {
      setDemographicModalLoading(false);
    }
  };

  const filteredClients = useMemo(() => {
    if (!portfolio) return [];
    if (!selectedStrategy) return [];
    const strategyClients = selectedStrategy === "HMR"
      ? portfolio.clients.filter((item) => item.hmr_elegible)
      : portfolio.clients.filter((item) => item.estrategia_principal === selectedStrategy);
    if (!selectedSubgroup) return strategyClients;
    return strategyClients.filter((item) => {
      if (selectedStrategy === "VAGENCIASEXTERNASINTERNO") {
        const placementCode = item.placement_code || "SIN_PLACEMENT";
        const listCode = item.group_id || item.sublista_trabajo || "GENERAL";
        return `PLACEMENT_${placementCode}_${listCode}` === selectedSubgroup;
      }
      return (item.estrategia_subgrupo || `${selectedStrategy}CARDS`) === selectedSubgroup;
    });
  }, [portfolio, selectedStrategy, selectedSubgroup]);

  const selectedClient = useMemo(
    () => filteredClients.find((item) => item.id === selectedClientId) ?? filteredClients[0] ?? null,
    [filteredClients, selectedClientId]
  );
  const queueClients = useMemo(
    () =>
      [...filteredClients].sort((left, right) => {
        const now = Date.now();
        const leftCallback = left.next_callback_at ? new Date(left.next_callback_at).getTime() : null;
        const rightCallback = right.next_callback_at ? new Date(right.next_callback_at).getTime() : null;
        const leftRank = leftCallback ? (leftCallback <= now ? 0 : 2) : 1;
        const rightRank = rightCallback ? (rightCallback <= now ? 0 : 2) : 1;
        if (leftRank !== rightRank) return leftRank - rightRank;
        if ((leftCallback || 0) !== (rightCallback || 0)) return (leftCallback || 0) - (rightCallback || 0);
        if (left.worked_today !== right.worked_today) return left.worked_today ? 1 : -1;
        if (left.total_outstanding !== right.total_outstanding) return right.total_outstanding - left.total_outstanding;
        return (left.identity_code || "").localeCompare(right.identity_code || "");
      }),
    [filteredClients]
  );
  const searchedQueueClients = useMemo(() => {
    const query = queueSearch.trim().toLowerCase();
    const normalizedQuery = normalizeLookupValue(query);
    if (!query) return queueClients;
    const matchesField = (value) => {
      const rawValue = String(value || "").toLowerCase();
      const normalizedValue = normalizeLookupValue(value);
      return rawValue.includes(query) || (normalizedQuery ? normalizedValue.includes(normalizedQuery) : false);
    };
    return queueClients.filter((client) =>
      ({
        all: [
          client.identity_code,
          client.dui,
          client.nombres,
          client.apellidos,
          `${client.nombres || ""} ${client.apellidos || ""}`.trim(),
          client.telefono,
          client.email,
          client.estrategia_subgrupo,
          client.segmento_operativo,
          ...(client.accounts || []).flatMap((account) => [
            account.numero_cuenta,
            account.numero_plastico,
            account.numero_plastico?.replace(/-/g, ""),
            account.producto_nombre,
            account.codigo_ubicacion,
          ]),
        ],
        unico: [client.identity_code],
        dui: [client.dui],
        nombre: [client.nombres, client.apellidos, `${client.nombres || ""} ${client.apellidos || ""}`.trim()],
        cuenta: (client.accounts || []).map((account) => account.numero_cuenta),
        plastico: (client.accounts || []).flatMap((account) => [account.numero_plastico, account.numero_plastico?.replace(/-/g, "")]),
        telefono: [client.telefono],
      })[queueSearchMode]
        .filter(Boolean)
        .some((value) => matchesField(value))
    );
  }, [queueClients, queueSearch, queueSearchMode]);
  const queueSearchHelp = {
    all: "Busca por Numero Unico, DUI, nombre, cuenta o plastico.",
    unico: "Ingresa el Numero Unico exacto o parcial.",
    dui: "Busca por DUI con o sin guion.",
    nombre: "Busca por nombres o apellidos del cliente.",
    cuenta: "Busca por numero de cuenta del producto.",
    plastico: "Busca por numero de plastico con o sin guiones.",
    telefono: "Busca por numero de telefono con o sin espacios.",
  };
  const applyQueueSearch = async () => {
    setQueueSearch(queueSearchInput);
    setQueueIndex(0);
    if (!queueSearchInput.trim()) {
      setLookupClient(null);
      return;
    }
    if (!onLookupClient) return;
    setLookupLoading(true);
    try {
      const foundClient = await onLookupClient(queueSearchInput.trim(), queueSearchMode);
      setLookupClient(foundClient || null);
    } catch {
      setLookupClient(null);
    } finally {
      setLookupLoading(false);
    }
  };
  const scopedCollectorLabel = portfolio?.collector?.nombre || portfolio?.collector?.username || "Collector";
  const hasAppliedQueueSearch = Boolean(queueSearch.trim());
  const strategyStateCode = selectedStrategy ? strategyStateCodes[selectedStrategy] || selectedStrategy : null;
  const lookupMatchesCurrentFilters = useMemo(() => {
    if (!lookupClient) return false;
    if (selectedStrategy && lookupClient.estrategia_principal !== selectedStrategy) return false;
    if (!selectedSubgroup) return true;
    if (selectedStrategy === "VAGENCIASEXTERNASINTERNO") {
      const placementCode = lookupClient.placement_code || "SIN_PLACEMENT";
      const listCode = lookupClient.group_id || lookupClient.sublista_trabajo || "GENERAL";
      return `PLACEMENT_${placementCode}_${listCode}` === selectedSubgroup;
    }
    return (lookupClient.estrategia_subgrupo || `${selectedStrategy}CARDS`) === selectedSubgroup;
  }, [lookupClient, selectedStrategy, selectedSubgroup]);
  const visibleQueueClients = searchedQueueClients.length > 0 ? searchedQueueClients : (lookupClient ? [lookupClient] : []);
  const activeClient = queueMode
    ? visibleQueueClients[queueIndex] ?? visibleQueueClients[0] ?? (hasAppliedQueueSearch ? null : selectedClient ?? queueClients[0] ?? null)
    : selectedClient;
  const historyPageSize = 15;

  const selectedAccount = useMemo(
    () => activeClient?.accounts.find((account) => String(account.id) === String(managementForm.account_id)) ?? activeClient?.accounts[0] ?? null,
    [activeClient, managementForm.account_id]
  );
  const filteredManagementHistory = useMemo(() => {
    const records = activeClient?.management_history || [];
    const query = managementSearch.trim().toLowerCase();
    if (!query) return records;
    return records.filter((item) =>
      [item.accion, item.descripcion, item.fecha, item.usuario_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [activeClient?.management_history, managementSearch]);
  const totalHistoryPages = Math.max(1, Math.ceil(filteredManagementHistory.length / historyPageSize));
  const paginatedManagementHistory = useMemo(() => {
    const start = (managementPage - 1) * historyPageSize;
    return filteredManagementHistory.slice(start, start + historyPageSize);
  }, [filteredManagementHistory, managementPage]);
  useEffect(() => {
    if (!activeClient) return;
    setSelectedClientId(activeClient.id);
    setManagementForm((current) => ({
      ...current,
      account_id: String(activeClient.accounts[0]?.id || ""),
      account_ids: activeClient.accounts[0]?.id ? [String(activeClient.accounts[0].id)] : [],
      called_phone: activeClient.telefono || "",
      rdm: "",
      promise_amount: String(activeClient.accounts[0]?.pago_minimo || "")
    }));
    setDemographicForm({
      telefono: activeClient.telefono || "",
      email: activeClient.email || "",
      direccion: activeClient.direccion || ""
    });
  }, [activeClient?.id]);

  useEffect(() => {
    setManagementSearch("");
    setManagementPage(1);
  }, [activeClient?.id]);

  useEffect(() => {
    setQueueSearchInput("");
    setQueueSearch("");
    setLookupClient(null);
    setQueueIndex(0);
    setSelectedClientId(null);
  }, [selectedStrategy, selectedSubgroup]);

  useEffect(() => {
    if (!queueMode) return;
    if (queueIndex < visibleQueueClients.length) return;
    setQueueIndex(0);
  }, [queueMode, queueIndex, visibleQueueClients.length]);

  useEffect(() => {
    if (managementPage <= totalHistoryPages) return;
    setManagementPage(totalHistoryPages);
  }, [managementPage, totalHistoryPages]);

  useEffect(() => {
    if (!queueMode) return undefined;
    const handleKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        managementSearchRef.current?.focus();
        managementSearchRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [queueMode]);

  const updateModalCollectionItem = (collectionKey, index, field, value) => {
    setDemographicModalData((current) => ({
      ...current,
      [collectionKey]: current[collectionKey].map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item
      ),
    }));
  };

  const setPrimaryModalItem = (collectionKey, index) => {
    setDemographicModalData((current) => ({
      ...current,
      [collectionKey]: current[collectionKey].map((item, itemIndex) => ({
        ...item,
        is_primary: itemIndex === index,
      })),
    }));
  };

  const addModalItem = (collectionKey) => {
    setDemographicModalData((current) => ({
      ...current,
      [collectionKey]: [
        ...current[collectionKey],
        collectionKey === "phones"
          ? { id: null, phone_type: "CEL", value: "", is_primary: current.phones.length === 0 }
          : collectionKey === "emails"
            ? { id: null, value: "", is_primary: current.emails.length === 0 }
            : { id: null, address_type: "CASA", value: "", is_primary: current.addresses.length === 0 },
      ],
    }));
  };

  const removeModalItem = (collectionKey, index) => {
    setDemographicModalData((current) => {
      const nextItems = current[collectionKey].filter((_, itemIndex) => itemIndex !== index);
      const normalizedItems = nextItems.map((item) => ({ ...item }));
      if (normalizedItems.length > 0 && !normalizedItems.some((item) => item.is_primary)) {
        normalizedItems[0] = { ...normalizedItems[0], is_primary: true };
      }
      return {
        ...current,
        [collectionKey]: normalizedItems,
      };
    });
  };

  const demographicModal = demographicModalOpen ? (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 py-6 backdrop-blur-sm">
      <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-[28px] bg-white shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ocean">Datos demograficos</p>
            <h3 className="mt-1 text-2xl font-bold text-ink">
              {activeClient ? `${activeClient.nombres} ${activeClient.apellidos}` : "Cliente"}
            </h3>
            <p className="mt-1 text-sm text-slate-500">Agrega, modifica o elimina telefonos, correos y direcciones. El cambio quedara en el historico del cliente.</p>
          </div>
          <button
            type="button"
            onClick={() => setDemographicModalOpen(false)}
            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-ink"
          >
            Cerrar
          </button>
        </div>

        <div className="grid gap-6 px-6 py-6 xl:grid-cols-3">
          <section className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <div className="flex items-center justify-between">
              <h4 className="text-lg font-semibold text-ink">Telefonos</h4>
              <button type="button" onClick={() => addModalItem("phones")} className="rounded-full bg-ocean px-3 py-1.5 text-xs font-semibold text-white">Agregar</button>
            </div>
            <div className="mt-4 space-y-4">
              {(demographicModalData.phones || []).map((phone, index) => (
                <div key={`phone-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="grid gap-3">
                    <select value={phone.phone_type || "CEL"} onChange={(event) => updateModalCollectionItem("phones", index, "phone_type", event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                      <option value="CASA">Tel Casa</option>
                      <option value="TRABAJO">Tel Trabajo</option>
                      <option value="CEL">Cel</option>
                    </select>
                    <input value={phone.value || ""} onChange={(event) => updateModalCollectionItem("phones", index, "value", event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Numero de telefono" />
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-sm text-slate-700">
                        <input type="radio" name="primary-phone" checked={Boolean(phone.is_primary)} onChange={() => setPrimaryModalItem("phones", index)} />
                        Principal
                      </label>
                      <button type="button" onClick={() => removeModalItem("phones", index)} className="text-sm font-semibold text-red-600">Eliminar</button>
                    </div>
                  </div>
                </div>
              ))}
              {(!demographicModalData.phones || demographicModalData.phones.length === 0) ? <p className="text-sm text-slate-500">No hay telefonos registrados.</p> : null}
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <div className="flex items-center justify-between">
              <h4 className="text-lg font-semibold text-ink">Correos</h4>
              <button type="button" onClick={() => addModalItem("emails")} className="rounded-full bg-ocean px-3 py-1.5 text-xs font-semibold text-white">Agregar</button>
            </div>
            <div className="mt-4 space-y-4">
              {(demographicModalData.emails || []).map((email, index) => (
                <div key={`email-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="grid gap-3">
                    <input value={email.value || ""} onChange={(event) => updateModalCollectionItem("emails", index, "value", event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="correo@cliente.com" />
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-sm text-slate-700">
                        <input type="radio" name="primary-email" checked={Boolean(email.is_primary)} onChange={() => setPrimaryModalItem("emails", index)} />
                        Principal
                      </label>
                      <button type="button" onClick={() => removeModalItem("emails", index)} className="text-sm font-semibold text-red-600">Eliminar</button>
                    </div>
                  </div>
                </div>
              ))}
              {(!demographicModalData.emails || demographicModalData.emails.length === 0) ? <p className="text-sm text-slate-500">No hay correos registrados.</p> : null}
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <div className="flex items-center justify-between">
              <h4 className="text-lg font-semibold text-ink">Direcciones</h4>
              <button type="button" onClick={() => addModalItem("addresses")} className="rounded-full bg-ocean px-3 py-1.5 text-xs font-semibold text-white">Agregar</button>
            </div>
            <div className="mt-4 space-y-4">
              {(demographicModalData.addresses || []).map((address, index) => (
                <div key={`address-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="grid gap-3">
                    <select value={address.address_type || "CASA"} onChange={(event) => updateModalCollectionItem("addresses", index, "address_type", event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                      <option value="CASA">Casa</option>
                      <option value="TRABAJO">Trabajo</option>
                      <option value="OTRA">Otra</option>
                    </select>
                    <textarea value={address.value || ""} onChange={(event) => updateModalCollectionItem("addresses", index, "value", event.target.value)} rows="4" className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Direccion fisica completa" />
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-sm text-slate-700">
                        <input type="radio" name="primary-address" checked={Boolean(address.is_primary)} onChange={() => setPrimaryModalItem("addresses", index)} />
                        Principal
                      </label>
                      <button type="button" onClick={() => removeModalItem("addresses", index)} className="text-sm font-semibold text-red-600">Eliminar</button>
                    </div>
                  </div>
                </div>
              ))}
              {(!demographicModalData.addresses || demographicModalData.addresses.length === 0) ? <p className="text-sm text-slate-500">No hay direcciones registradas.</p> : null}
            </div>
          </section>
        </div>

        <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-slate-200 bg-white px-6 py-4">
          <p className="text-sm text-slate-500">
            {demographicModalLoading ? "Cargando datos..." : "Los cambios actualizaran la ficha del cliente y quedaran registrados en el historico."}
          </p>
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setDemographicModalOpen(false)} className="rounded-2xl border border-slate-200 px-4 py-3 font-semibold text-ink">
              Cancelar
            </button>
            <button
              type="button"
              disabled={saving || demographicModalLoading || !activeClient}
              onClick={() => onUpdateDemographics(activeClient, demographicModalData, onRefresh, () => setDemographicModalOpen(false))}
              className="rounded-2xl bg-ocean px-5 py-3 font-semibold text-white disabled:opacity-50"
            >
              {saving ? "Guardando..." : "Guardar cambios"}
            </button>
          </div>
        </div>
      </div>
    </div>
  ) : null;

  const worklistSections = useMemo(() => {
    if (!selectedStrategy) return [];
    const sections = [
      {
        key: "pendientes",
        title: "Pendientes del dia",
        description: "Clientes listos para iniciar gestion inmediata.",
        clients: filteredClients.filter((client) => !client.worked_today && !client.next_callback_at && !client.requires_supervisor_review),
      },
      {
        key: "callbacks",
        title: "Llamadas programadas",
        description: "Recontactos y compromisos agendados para hoy.",
        clients: filteredClients.filter((client) => Boolean(client.next_callback_at)),
      },
      {
        key: "revision",
        title: "Revision supervisor",
        description: "Casos con acuerdos fuera de politica que requieren seguimiento.",
        clients: filteredClients.filter((client) => client.requires_supervisor_review),
      },
      {
        key: "gestionados",
        title: "Gestionados hoy",
        description: "Clientes ya trabajados durante la jornada actual.",
        clients: filteredClients.filter((client) => client.worked_today),
      },
    ];
    return sections.filter((section) => section.clients.length > 0);
  }, [filteredClients, selectedStrategy]);
  const strategySublistSections = useMemo(() => {
    if (!selectedStrategy) return [];
    const strategyClients = selectedStrategy === "HMR"
      ? portfolio.clients.filter((item) => item.hmr_elegible)
      : portfolio.clients.filter((item) => item.estrategia_principal === selectedStrategy);
    if (selectedStrategy === "VAGENCIASEXTERNASINTERNO") {
      const grouped = strategyClients.reduce((accumulator, client) => {
        const placementCode = client.placement_code || "SIN_PLACEMENT";
        const listCode = client.group_id || client.sublista_trabajo || "GENERAL";
        const key = `PLACEMENT_${placementCode}_${listCode}`;
        if (!accumulator[key]) {
          accumulator[key] = {
            key,
            title: `${placementCode} · ${listCode}`,
            description: client.sublista_descripcion || `Placement ${placementCode} con lista ${listCode}.`,
            clients: [],
            placementCode,
            listCode,
          };
        }
        accumulator[key].clients.push(client);
        return accumulator;
      }, {});
      return Object.values(grouped).sort((left, right) => right.clients.length - left.clients.length);
    }
    const grouped = strategyClients.reduce((accumulator, client) => {
      const key = client.estrategia_subgrupo || `${selectedStrategy}CARDS`;
      if (!accumulator[key]) {
        accumulator[key] = {
          key,
          title: key,
          description: client.segmento_operativo
            ? `Subgrupo operativo ${client.segmento_operativo} dentro de ${selectedStrategy}.`
            : "Subgrupo operativo de la estrategia seleccionada.",
          clients: [],
        };
      }
      accumulator[key].clients.push(client);
      return accumulator;
    }, {});
    return Object.values(grouped).sort((left, right) => right.clients.length - left.clients.length);
  }, [portfolio, selectedStrategy]);
  const subgroupCards = strategySublistSections.map((section, index) => ({
    ...section,
    stateCode:
      selectedStrategy === "VAGENCIASEXTERNASINTERNO"
        ? section.placementCode || section.listCode || `R${String(index + 1).padStart(2, "0")}`
        : strategyStateCode || `G${String(index + 1).padStart(2, "0")}`,
    familyLabel: getSubgroupFamilyLabel(section.key),
    pendingCount: section.clients.filter((client) => !client.worked_today && !client.next_callback_at && !client.requires_supervisor_review).length,
    callbackCount: section.clients.filter((client) => Boolean(client.next_callback_at)).length,
  }));
  const activeSubgroupCard = subgroupCards.find((section) => section.key === selectedSubgroup) || null;
  const recoveryPlacementGroups = useMemo(() => {
    if (selectedStrategy !== "VAGENCIASEXTERNASINTERNO") return [];
    const grouped = subgroupCards.reduce((accumulator, section) => {
      const placementKey = section.placementCode || "SIN_PLACEMENT";
      if (!accumulator[placementKey]) {
        accumulator[placementKey] = {
          placementCode: placementKey,
          totalClients: 0,
          pendingCount: 0,
          callbackCount: 0,
          lists: [],
        };
      }
      accumulator[placementKey].totalClients += section.clients.length;
      accumulator[placementKey].pendingCount += section.pendingCount;
      accumulator[placementKey].callbackCount += section.callbackCount;
      accumulator[placementKey].lists.push(section);
      return accumulator;
    }, {});
    return Object.values(grouped)
      .map((group) => ({
        ...group,
        lists: group.lists.sort((left, right) => right.clients.length - left.clients.length),
      }))
      .sort((left, right) => left.placementCode.localeCompare(right.placementCode));
  }, [selectedStrategy, subgroupCards]);

  if (!portfolio) {
    return <p className="p-8 text-sm text-slate-500">Cargando cartera asignada...</p>;
  }

  const { metrics } = portfolio;
  const strategyOrder = ["AL_DIA", "PREVENTIVO", "FMORA1", "MMORA2", "HMORA3", "AMORA4", "BMORA5", "CMORA6", "DMORA7", "VAGENCIASEXTERNASINTERNO"];
  const strategyCards = [
    ...strategyOrder
      .map((key) => ({ key, label: key, value: (metrics.strategy_summary || {})[key] || 0 })),
    { key: "HMR", label: "HMR", value: metrics.hmr_candidates }
  ];
  const maxStrategyValue = Math.max(1, ...strategyCards.map((item) => item.value || 0));
  const leadingStrategy = strategyCards.reduce((best, current) => (current.value > (best?.value || 0) ? current : best), null);
  const strategyDashboardCards = strategyCards.map((item) => {
    const section = item.key === "HMR"
      ? {
          key: "hmr",
          title: "Herramientas HMR",
          clients: portfolio.clients.filter((client) => client.hmr_elegible),
        }
      : worklistSections.find((section) => section.clients.some((client) => client.estrategia_principal === item.key)) || {
          key: "pendientes",
          title: "Pendientes del dia",
          clients: filteredClients,
        };
    return {
      ...item,
      displayLabel: strategyLabels[item.key] || item.label,
      description: strategyDescriptions[item.key] || "Cartera lista para gestion operativa.",
      ratio: Math.max(8, Math.round((item.value / maxStrategyValue) * 100)),
      spotlight:
        item.key === "HMR"
          ? `${metrics.hmr_candidates} oportunidades de mitigacion`
          : `${section.clients.filter((client) => !client.worked_today).length} pendientes por trabajar`,
    };
  });
  const selectedStrategyInsights = (() => {
    if (!selectedStrategy) {
      return {
        avgRisk: 0,
        avgProbability: 0,
        confidence: "Sin calcular",
        digitalChannel: "Selecciona una estrategia",
        pendingCount: 0,
        callbackCount: 0,
        reviewCount: 0,
        topRecommendedClients: [],
        recommendationTitle: "Esperando estrategia",
        recommendationBody: "Selecciona una estrategia para recibir una recomendacion de canal y foco operativo.",
      };
    }
    const clients = filteredClients;
    const strategyAccounts = clients.flatMap((client) => client.accounts || []);
    const avgProbability = strategyAccounts.length
      ? Math.round(
          (strategyAccounts.reduce((sum, account) => sum + Number(account.ai_probability ?? 0), 0) / strategyAccounts.length) * 100
        )
      : clients.length
        ? Math.round((clients.reduce((sum, client) => sum + Number(client.score_riesgo || 0), 0) / clients.length) * 100)
        : 0;
    const avgRisk = avgProbability;
    const topRecommendedClients = [...clients]
      .map((client) => {
        const accountProbabilities = (client.accounts || []).map((account) => Number(account.ai_probability ?? client.score_riesgo ?? 0));
        const avgClientProbability = accountProbabilities.length
          ? accountProbabilities.reduce((sum, value) => sum + value, 0) / accountProbabilities.length
          : Number(client.score_riesgo || 0);
        const leadAccount =
          [...(client.accounts || [])].sort((left, right) => Number(right.ai_probability ?? 0) - Number(left.ai_probability ?? 0))[0] ||
          client.accounts?.[0];
        const expectedRecovery = avgClientProbability * Number(client.total_outstanding || 0);
        return {
          id: client.id,
          nombre: `${client.nombres} ${client.apellidos}`,
          numeroUnico: client.identity_code || "SIN NUMERO UNICO",
          probability: Math.round(avgClientProbability * 100),
          expectedRecovery,
          channel: leadAccount?.ai_recommendation || "Gestion priorizada por score operativo.",
        };
      })
      .sort((left, right) => right.expectedRecovery - left.expectedRecovery)
      .slice(0, 3);
    let digitalChannel = "WhatsApp + SMS";
    if (selectedStrategy === "AL_DIA") digitalChannel = "Monitoreo sin contacto";
    else if (selectedStrategy === "PREVENTIVO") digitalChannel = "Chatbot WhatsApp + SMS";
    else if (selectedStrategy === "FMORA1" || selectedStrategy === "MMORA2") digitalChannel = "Chatbot WhatsApp + SMS";
    else if (["HMORA3", "AMORA4"].includes(selectedStrategy)) digitalChannel = "Llamada telefonica + WhatsApp";
    else if (["BMORA5", "CMORA6", "DMORA7"].includes(selectedStrategy)) digitalChannel = "Llamada telefonica intensiva + WhatsApp";
    else if (selectedStrategy === "VAGENCIASEXTERNASINTERNO") digitalChannel = "Callbot + llamada humana + WhatsApp";
    else if (selectedStrategy === "HMR") digitalChannel = "Llamada consultiva + WhatsApp";
    else if (avgRisk >= 80) digitalChannel = "Llamada telefonica + WhatsApp";
    else if (avgRisk >= 60) digitalChannel = "WhatsApp guiado + SMS";
    else if (avgRisk >= 35) digitalChannel = "SMS + correo";
    else digitalChannel = "Correo + push de autogestion";

    let recommendationTitle = "Recuperacion guiada por IA";
    let recommendationBody = `${clients.filter((client) => !client.worked_today).length} clientes pendientes. La IA recomienda iniciar por ${digitalChannel.toLowerCase()} segun el perfil consolidado de la estrategia.`;

    if (selectedStrategy === "AL_DIA") {
      recommendationTitle = "Seguimiento silencioso";
      recommendationBody = "La cuenta está al día. En esta estrategia no se recomienda contacto; solo monitoreo y preparación para actuar si entra a Preventivo.";
    } else if (selectedStrategy === "PREVENTIVO") {
      recommendationTitle = "Contencion temprana";
      recommendationBody = `La IA detecta cartera de baja friccion. Prioriza ${digitalChannel.toLowerCase()} y recordatorios breves para capturar pago antes de que escale la mora. El chatbot debe resolver saldo, fecha y link de pago sin friccion.`;
    } else if (selectedStrategy === "FMORA1" || selectedStrategy === "MMORA2") {
      recommendationTitle = "Recuperacion temprana";
      recommendationBody = `La estrategia muestra ${avgRisk}% de riesgo promedio. Conviene abrir con ${digitalChannel.toLowerCase()} y empujar promesas cortas con seguimiento en 24 a 48 horas. El chatbot puede filtrar intencion y dejar al gestor solo los casos con objecion o negociacion.`;
    } else if (selectedStrategy === "HMORA3" || selectedStrategy === "AMORA4") {
      recommendationTitle = "Intensidad controlada";
      recommendationBody = `La IA eleva el tono de gestion: desde este tramo conviene abrir con ${digitalChannel.toLowerCase()} porque la friccion ya es media/alta y hay ${clients.length} casos visibles en este tramo.`;
    } else if (selectedStrategy === "BMORA5" || selectedStrategy === "CMORA6" || selectedStrategy === "DMORA7") {
      recommendationTitle = "Recuperacion intensiva";
      recommendationBody = `La severidad de mora pide una postura agresiva. La IA prioriza ${digitalChannel.toLowerCase()} como canal de apertura y recomienda escalar rapido los casos sin contacto efectivo.`;
    } else if (selectedStrategy === "VAGENCIASEXTERNASINTERNO") {
      recommendationTitle = "Recovery por placements";
      recommendationBody = `La IA detecta cartera Recovery. Prioriza ${digitalChannel.toLowerCase()} y mueve los casos entre placement, agencia y lista operativa según respuesta y pago.`;
    } else if (selectedStrategy === "HMR") {
      recommendationTitle = "Mitigacion y solucion";
      recommendationBody = `La IA identifica oportunidad de herramientas HMR. Prioriza ${digitalChannel.toLowerCase()} con discurso de solucion y enfoque en capacidad de pago.`;
    }

    if (clients.filter((client) => client.requires_supervisor_review).length >= 10) {
      recommendationBody += " Hay presion relevante de revision supervisor, asi que conviene aislar acuerdos fuera de politica desde el primer contacto.";
    } else if (clients.filter((client) => Boolean(client.next_callback_at)).length >= 8) {
      recommendationBody += " Existen varios callbacks activos, por lo que la mejor ventana esta en recontactar primero a quienes ya mostraron intencion.";
    }

    return {
      avgRisk,
      avgProbability,
      confidence: avgProbability >= 75 ? "Alta" : avgProbability >= 45 ? "Media" : "Baja",
      digitalChannel,
      pendingCount: clients.filter((client) => !client.worked_today).length,
      callbackCount: clients.filter((client) => Boolean(client.next_callback_at)).length,
      reviewCount: clients.filter((client) => client.requires_supervisor_review).length,
      topRecommendedClients,
      recommendationTitle,
      recommendationBody,
    };
  })();
  const tabs = [
    { key: "deudor", label: "Informacion del deudor" },
    { key: "demografica", label: "Informacion demografica" },
    { key: "financiera", label: "Informacion financiera" },
    { key: "gestion", label: "Gestion de cobro" }
  ];
  const activeStatus = getClientOperationalStatus(activeClient);
  const selectedAccounts = activeClient?.accounts.filter((account) => managementForm.account_ids.includes(String(account.id))) || [];
  const selectedAccountsMinimum = selectedAccounts.reduce((sum, account) => sum + Number(account.pago_minimo || 0), 0);

  if (queueMode && !activeClient) {
    return (
      <div className="min-h-screen bg-[linear-gradient(180deg,#ebf1f7,#f8fafc)] px-4 py-4 md:px-6">
        {demographicModal}
        <div className="mx-auto max-w-[1760px]">
          <header className="overflow-hidden rounded-[28px] bg-[#24384d] text-white shadow-panel">
            <div className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-4">
                <BrandLogo size="header" />
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-cyan-200">Lista de trabajo diaria</p>
                  <h1 className="mt-2 text-[2.25rem] font-bold leading-tight">Consola de gestion del collector</h1>
                </div>
              </div>
              <div className="grid gap-2 text-sm text-slate-200 lg:text-right">
                <p>Usuario: {auth.user.nombre}</p>
                {(auth.user.rol === "Admin" || auth.user.rol === "Supervisor") ? <p>Vista de cartera: {scopedCollectorLabel}</p> : null}
                <p>Cola activa: 0 de 0</p>
                <p>Fecha: {new Date().toLocaleDateString("es-SV")}</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 bg-[#31485f] px-5 py-3 text-sm font-semibold">
              <button onClick={() => setQueueMode(false)} className="rounded-full bg-white px-4 py-2 text-ink">Volver al panel</button>
              <button onClick={() => setQueueIndex(0)} className="rounded-full bg-white/10 px-4 py-2">Anterior</button>
              <button onClick={() => setQueueIndex(0)} className="rounded-full bg-white/10 px-4 py-2">Siguiente</button>
              <span className="rounded-full bg-emerald-500/20 px-4 py-2">Pendientes: {metrics.remaining_today}</span>
              <span className="rounded-full bg-amber-500/20 px-4 py-2">Callbacks hoy: {metrics.scheduled_callbacks_today}</span>
              <div className="flex min-w-[420px] flex-1 flex-wrap items-center gap-2 rounded-[22px] border border-white/10 bg-white/10 p-2">
                <select
                  value={queueSearchMode}
                  onChange={(event) => {
                    setQueueSearchMode(event.target.value);
                    setQueueSearchInput("");
                    setQueueSearch("");
                    setQueueIndex(0);
                  }}
                  className="rounded-2xl border border-white/10 bg-[#24384d] px-4 py-2 text-sm font-semibold text-white outline-none"
                >
                  <option value="all">Busqueda general</option>
                  <option value="unico">Numero Unico</option>
                  <option value="dui">DUI</option>
                  <option value="nombre">Nombre</option>
                  <option value="cuenta">Numero de cuenta</option>
                  <option value="plastico">Numero de plastico</option>
                  <option value="telefono">Numero de telefono</option>
                </select>
                <input
                  value={queueSearchInput}
                  onChange={(event) => setQueueSearchInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      applyQueueSearch();
                    }
                  }}
                  placeholder={`Buscar por ${getSearchModeLabel(queueSearchMode).toLowerCase()}...`}
                  className="min-w-[220px] flex-1 rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-white placeholder:text-slate-300 outline-none"
                />
                <button
                  type="button"
                  onClick={applyQueueSearch}
                  className="rounded-2xl bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors hover:bg-cyan-300"
                >
                  Buscar
                </button>
              </div>
              <span className="rounded-full bg-white/10 px-4 py-2 text-xs text-slate-100">
                {queueSearchHelp[queueSearchMode]}
              </span>
              {lookupLoading ? (
                <span className="rounded-full bg-cyan-500/20 px-4 py-2 text-xs text-cyan-100">
                  Buscando cliente en el sistema...
                </span>
              ) : queueSearch.trim() ? (
                <span className="rounded-full bg-red-500/20 px-4 py-2 text-xs text-red-100">
                  Sin coincidencias para la búsqueda actual.
                </span>
              ) : null}
            </div>
          </header>

          <section className="mt-4 rounded-[28px] border border-slate-200 bg-white p-8 shadow-panel">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-ocean">Sin resultados en esta cola</p>
            <h2 className="mt-3 text-3xl font-bold text-ink">La búsqueda no coincide con la cartera visible</h2>
            <p className="mt-3 max-w-4xl text-base leading-7 text-slate-600">
              {auth.user.rol === "Admin" || auth.user.rol === "Supervisor"
                ? `Esta pantalla muestra únicamente la cartera asignada a ${scopedCollectorLabel}. Un cliente puede existir en la base general y aún así no aparecer aquí si no está dentro de esta cola de trabajo.`
                : "Si eres usuario interno, la búsqueda también consulta el sistema completo; si eres agencia externa, solo consulta tus cuentas asignadas."}
            </p>
          </section>
        </div>
      </div>
    );
  }

  if (queueMode && activeClient) {
    return (
      <div className="min-h-screen bg-[linear-gradient(180deg,#ebf1f7,#f8fafc)] px-4 py-4 md:px-6">
        {demographicModal}
        <div className="mx-auto max-w-[1760px]">
          <header className="overflow-hidden rounded-[28px] bg-[#24384d] text-white shadow-panel">
            <div className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-4">
                <BrandLogo size="header" />
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-cyan-200">Lista de trabajo diaria</p>
                  <h1 className="mt-2 text-[2.25rem] font-bold leading-tight">Consola de gestion del collector</h1>
                </div>
              </div>
              <div className="grid gap-2 text-sm text-slate-200 lg:text-right">
                <p>Usuario: {auth.user.nombre}</p>
                {(auth.user.rol === "Admin" || auth.user.rol === "Supervisor") ? <p>Vista de cartera: {scopedCollectorLabel}</p> : null}
                <p>Cola activa: {visibleQueueClients.length ? queueIndex + 1 : 0} de {visibleQueueClients.length}</p>
                <p>Fecha: {new Date().toLocaleDateString("es-SV")}</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 bg-[#31485f] px-5 py-3 text-sm font-semibold">
              <button onClick={() => setQueueMode(false)} className="rounded-full bg-white px-4 py-2 text-ink">Volver al panel</button>
              <button onClick={() => setQueueIndex((current) => Math.max(0, current - 1))} className="rounded-full bg-white/10 px-4 py-2">Anterior</button>
              <button onClick={() => setQueueIndex((current) => Math.min(visibleQueueClients.length - 1, current + 1))} className="rounded-full bg-white/10 px-4 py-2">Siguiente</button>
              <span className="rounded-full bg-emerald-500/20 px-4 py-2">Pendientes: {metrics.remaining_today}</span>
              <span className="rounded-full bg-amber-500/20 px-4 py-2">Callbacks hoy: {metrics.scheduled_callbacks_today}</span>
              <div className="flex min-w-[420px] flex-1 flex-wrap items-center gap-2 rounded-[22px] border border-white/10 bg-white/10 p-2">
                <select
                  value={queueSearchMode}
                  onChange={(event) => {
                    setQueueSearchMode(event.target.value);
                    setQueueSearchInput("");
                    setQueueSearch("");
                    setQueueIndex(0);
                  }}
                  className="rounded-2xl border border-white/10 bg-[#24384d] px-4 py-2 text-sm font-semibold text-white outline-none"
                >
                  <option value="all">Busqueda general</option>
                  <option value="unico">Numero Unico</option>
                  <option value="dui">DUI</option>
                  <option value="nombre">Nombre</option>
                  <option value="cuenta">Numero de cuenta</option>
                  <option value="plastico">Numero de plastico</option>
                  <option value="telefono">Numero de telefono</option>
                </select>
                <input
                  value={queueSearchInput}
                  onChange={(event) => setQueueSearchInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      applyQueueSearch();
                    }
                  }}
                  placeholder={`Buscar por ${getSearchModeLabel(queueSearchMode).toLowerCase()}...`}
                  className="min-w-[220px] flex-1 rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-white placeholder:text-slate-300 outline-none"
                />
                <button
                  type="button"
                  onClick={applyQueueSearch}
                  className="rounded-2xl bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors hover:bg-cyan-300"
                >
                  Buscar
                </button>
              </div>
              <span className="rounded-full bg-white/10 px-4 py-2 text-xs text-slate-100">
                {queueSearchHelp[queueSearchMode]}
              </span>
              {lookupLoading ? (
                <span className="rounded-full bg-cyan-500/20 px-4 py-2 text-xs text-cyan-100">
                  Buscando cliente en el sistema...
                </span>
              ) : queueSearch.trim() && visibleQueueClients.length === 0 ? (
                <span className="rounded-full bg-red-500/20 px-4 py-2 text-xs text-red-100">
                  Sin coincidencias para la búsqueda actual.
                </span>
              ) : null}
              {queueSearch.trim() && searchedQueueClients.length === 0 && lookupClient ? (
                <span className="rounded-full bg-emerald-500/20 px-4 py-2 text-xs text-emerald-100">
                  Resultado encontrado fuera de la cola visible.
                </span>
              ) : null}
              {queueSearch.trim() && searchedQueueClients.length === 0 && lookupClient && !lookupMatchesCurrentFilters ? (
                <span className="rounded-full bg-amber-500/20 px-4 py-2 text-xs text-amber-100">
                  Cliente encontrado en {lookupClient.estrategia_principal || "otra estrategia"}.
                </span>
              ) : null}
            </div>
          </header>

          {error ? <p className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">{error}</p> : null}
          {success ? <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

          <section className="mt-4 grid gap-4 xl:grid-cols-[0.95fr_0.95fr_0.8fr]">
            <section className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-panel">
              <div className="flex items-center justify-between border-b border-cyan-200 pb-2">
                <h2 className="text-[1.7rem] font-bold text-ink">Cliente</h2>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={openDemographicEditor}
                    className="rounded-full bg-ocean px-3 py-1.5 text-xs font-semibold text-white"
                  >
                    Editar datos
                  </button>
                  <button type="button" onClick={() => toggleSection("client")} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
                    {collapsedSections.client ? "Expandir" : "Minimizar"}
                  </button>
                </div>
              </div>
              {!collapsedSections.client ? <div className="mt-3 grid gap-2 text-sm text-slate-700">
                <p><span className="font-semibold text-ink">Nombre:</span> {activeClient.nombres} {activeClient.apellidos}</p>
                <p><span className="font-semibold text-ink">Numero Unico:</span> {activeClient.identity_code || "No disponible"}</p>
                <p><span className="font-semibold text-ink">DUI:</span> {activeClient.dui || "No disponible"}</p>
                <p><span className="font-semibold text-ink">Estado:</span> {activeStatus.label}</p>
                <p><span className="font-semibold text-ink">Telefono principal:</span> {activeClient.telefono || "Pendiente"}</p>
                <p><span className="font-semibold text-ink">Email:</span> {activeClient.email || "Pendiente"}</p>
                <p><span className="font-semibold text-ink">Direccion:</span> {activeClient.direccion || "Sin direccion registrada"}</p>
                <p><span className="font-semibold text-ink">Segmento:</span> {activeClient.segmento || "Sin segmento"}</p>
                <p><span className="font-semibold text-ink">Subgrupo:</span> {activeClient.estrategia_subgrupo || activeClient.estrategia_principal}</p>
                <p><span className="font-semibold text-ink">Cartera asignada:</span> {activeClient.group_id || activeClient.sublista_trabajo || "GENERAL"}</p>
                <p><span className="font-semibold text-ink">Placement:</span> {activeClient.placement_code || "N/D"}</p>
                <p><span className="font-semibold text-ink">Cabeza de mora:</span> {activeClient.producto_cabeza || "Sin definir"} · {activeClient.dias_mora_cabeza || 0} dias</p>
                <p><span className="font-semibold text-ink">Riesgo:</span> {Math.round(activeClient.score_riesgo * 100)}%</p>
                <p><span className="font-semibold text-ink">Contacto sugerido:</span> {activeClient.telefono ? "Telefono principal" : activeClient.email ? "Correo" : "Actualizar datos"}</p>
              </div> : <p className="pt-3 text-sm text-slate-500">Seccion minimizada.</p>}
            </section>

            <section className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-panel">
              <div className="flex items-center justify-between border-b border-cyan-200 pb-2">
                <h2 className="text-[1.7rem] font-bold text-ink">Finanzas</h2>
                <button type="button" onClick={() => toggleSection("finance")} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
                  {collapsedSections.finance ? "Expandir" : "Minimizar"}
                </button>
              </div>
              {!collapsedSections.finance ? <div className="mt-3 grid gap-3">
                {(activeClient.accounts || []).map((account) => (
                  <button
                    key={account.id}
                    type="button"
                    onClick={() => setManagementForm((current) => ({ ...current, account_id: String(account.id), promise_amount: String(account.pago_minimo || "") }))}
                    className={`rounded-2xl border p-3 text-left ${selectedAccount?.id === account.id ? "border-cyan-400 bg-cyan-50" : "border-slate-200"}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-ink">Cuenta: {account.numero_cuenta}</p>
                        <p className="mt-1 text-sm text-slate-600">{account.producto_nombre || account.tipo_producto} · {account.estrategia}</p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{account.bucket_actual}</span>
                    </div>
                    <div className="mt-2 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
                      <p><span className="font-semibold text-ink">Saldo actual:</span> {currency(account.saldo_total)}</p>
                      <p><span className="font-semibold text-ink">Monto adeudado:</span> {currency(account.saldo_mora)}</p>
                      <p><span className="font-semibold text-ink">Dias mora:</span> {account.dias_mora}</p>
                      <p><span className="font-semibold text-ink">Pago minimo:</span> {currency(account.pago_minimo)}</p>
                      <p><span className="font-semibold text-ink">Estado:</span> {account.estado}</p>
                      <p><span className="font-semibold text-ink">Ciclo:</span> {account.ciclo_corte} / {account.dia_vencimiento}</p>
                      <p><span className="font-semibold text-ink">Plastico:</span> {account.numero_plastico || "No aplica"}</p>
                      <p><span className="font-semibold text-ink">Ubicacion:</span> {account.codigo_ubicacion || "N/D"}</p>
                    </div>
                  </button>
                ))}
              </div> : <p className="pt-3 text-sm text-slate-500">Seccion minimizada.</p>}
            </section>

            <section className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-panel">
              <div className="border-b border-cyan-200 pb-2">
                <h2 className="text-[1.7rem] font-bold text-ink">Indicadores</h2>
              </div>
              <div className="mt-3 grid gap-2 text-sm text-slate-700">
                <p><span className="font-semibold text-ink">Probabilidad de pago:</span> {(activeClient.score_riesgo * 100).toFixed(0)}%</p>
                <p><span className="font-semibold text-ink">Historial de atraso:</span> {selectedAccount?.dias_mora || 0} dias</p>
                <p><span className="font-semibold text-ink">Segmento de riesgo:</span> {activeClient.segmento || "General"}</p>
                <p><span className="font-semibold text-ink">Mitigacion HMR:</span> {activeClient.hmr_elegible ? "Aplicable" : "No aplica"}</p>
                <p><span className="font-semibold text-ink">Nota del gestor:</span> {activeClient.last_management || "Sin observaciones registradas"}</p>
                <p><span className="font-semibold text-ink">Estado operativo:</span> {activeStatus.label}</p>
                <div className={`mt-2 rounded-2xl px-4 py-3 text-sm font-semibold ${selectedAccount?.dias_mora >= 60 ? "bg-red-500 text-white" : "bg-amber-100 text-amber-800"}`}>
                  {selectedAccount?.dias_mora >= 60 ? "Cliente en mora alta" : "Cliente requiere seguimiento"}
                </div>
                <div className="mt-3 rounded-2xl border border-cyan-200 bg-cyan-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700">Siguiente mejor acción</p>
                  <p className="mt-2 text-sm font-semibold text-ink">{activeClient.ai_next_action || "Inicia por la cuenta cabeza y valida intención de pago."}</p>
                  <p className="mt-2 text-sm text-slate-700">Canal sugerido: <span className="font-semibold text-ink">{activeClient.ai_best_channel || "Llamada"}</span></p>
                  <p className="mt-1 text-sm text-slate-700">Riesgo de ruptura: <span className="font-semibold text-ink">{((activeClient.ai_promise_break_probability || 0) * 100).toFixed(0)}%</span></p>
                  <p className="mt-2 text-sm text-slate-600">{activeClient.ai_talk_track || "Usa un discurso breve, valida capacidad de pago y lleva el caso al siguiente paso concreto."}</p>
                  <button
                    type="button"
                    onClick={() => setManagementForm((current) => ({
                      ...current,
                      contact_channel: (activeClient.ai_best_channel || "").toLowerCase().includes("whatsapp") ? "WhatsApp" : (activeClient.ai_best_channel || "").toLowerCase().includes("sms") ? "SMS" : "Llamada",
                      notes: current.notes?.trim()
                        ? current.notes
                        : `${activeClient.ai_next_action || "Seguimiento guiado por IA"}\n\nGuion sugerido: ${activeClient.ai_talk_track || "Validar intención de pago y ofrecer siguiente paso concreto."}`,
                    }))}
                    className="mt-3 rounded-xl bg-ocean px-4 py-2 text-sm font-semibold text-white"
                  >
                    Aplicar sugerencia al formulario
                  </button>
                </div>
              </div>
            </section>
          </section>

          <section className="mt-4 rounded-[24px] border border-slate-200 bg-white p-4 shadow-panel">
            <div className="flex items-center justify-between border-b border-cyan-200 pb-2">
              <h2 className="text-[1.7rem] font-bold text-ink">Registrar nueva accion de cobranza</h2>
              <button type="button" onClick={() => toggleSection("actionForm")} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
                {collapsedSections.actionForm ? "Expandir" : "Minimizar"}
              </button>
            </div>
            {!collapsedSections.actionForm ? <form
              onSubmit={(event) => {
                event.preventDefault();
                onSubmitManagement(activeClient, managementForm, selectedAccount, () =>
                  setManagementForm((current) => ({
                    ...current,
                    notes: "",
                    promise_date: "",
                    promise_amount: String(selectedAccount?.pago_minimo || ""),
                    callback_at: ""
                  }))
                );
              }}
              className="mt-4 grid gap-4"
            >
              <div className="grid gap-3 lg:grid-cols-[1fr_1fr_0.9fr_0.9fr_auto]">
                <select value={managementForm.management_type} onChange={(event) => setManagementForm((current) => ({ ...current, management_type: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm">
                  <option>Llamada de cobranza</option>
                  <option>Seguimiento a promesa</option>
                  <option>Recordatorio preventivo</option>
                  <option>Escalamiento supervisor</option>
                </select>
                <select value={managementForm.result} onChange={(event) => setManagementForm((current) => ({ ...current, result: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm">
                  <option>Contactado</option>
                  <option>No localizado</option>
                  <option>Promesa de pago</option>
                  <option>Rechazo</option>
                  <option>Escalar visita</option>
                </select>
                <input type="date" value={managementForm.promise_date} onChange={(event) => setManagementForm((current) => ({ ...current, promise_date: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm" />
                <input type="number" min="0" step="0.01" value={managementForm.promise_amount} onChange={(event) => setManagementForm((current) => ({ ...current, promise_amount: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm" placeholder="Monto acuerdo" />
                <button disabled={saving} className="rounded-2xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-70">
                  {saving ? "Guardando..." : "Guardar accion"}
                </button>
              </div>

              <div className="grid gap-3 lg:grid-cols-[1fr_1fr]">
                <div>
                  <label className="text-sm font-medium text-slate-700">Fecha y hora de llamada reprogramada</label>
                  <input type="datetime-local" value={managementForm.callback_at} onChange={(event) => setManagementForm((current) => ({ ...current, callback_at: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm" />
                </div>
                <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
                  <p>Cuenta activa: <span className="font-semibold text-ink">{selectedAccount?.numero_cuenta || "Sin cuenta"}</span></p>
                  <p className="mt-1">Pago minimo sugerido: <span className="font-semibold text-ink">{currency(selectedAccount?.pago_minimo || 0)}</span></p>
                  <p className="mt-1">Si el monto o plazo exceden politica, pasara a Revision Supervisor.</p>
                </div>
              </div>

              <textarea value={managementForm.notes} onChange={(event) => setManagementForm((current) => ({ ...current, notes: event.target.value }))} rows="5" className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm" placeholder="Escriba detalles de la gestion, objeciones y siguientes pasos..." />
            </form> : <p className="pt-3 text-sm text-slate-500">Seccion minimizada.</p>}
          </section>

          <section className="mt-5 rounded-[26px] border border-slate-200 bg-white p-5 shadow-panel">
            <div className="flex flex-col gap-3 border-b border-cyan-200 pb-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-bold text-ink">Historial de gestiones del cliente</h2>
                  <button type="button" onClick={() => toggleSection("history")} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
                    {collapsedSections.history ? "Expandir" : "Minimizar"}
                  </button>
                </div>
                <p className="mt-1 text-sm text-slate-600">Usa `Ctrl + F` para enfocar el buscador y localizar gestiones previas sin salir de la consola.</p>
              </div>
              {!collapsedSections.history ? <div className="grid gap-3 lg:min-w-[380px]">
                <label className="text-sm font-medium text-slate-700">Buscar en gestiones</label>
                <input
                  ref={managementSearchRef}
                  value={managementSearch}
                  onChange={(event) => {
                    setManagementSearch(event.target.value);
                    setManagementPage(1);
                  }}
                  type="search"
                  placeholder="Buscar por accion, detalle, fecha o usuario..."
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm"
                />
              </div> : null}
            </div>

            {!collapsedSections.history ? <>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="px-3 py-2 font-medium">Fecha</th>
                    <th className="px-3 py-2 font-medium">Accion</th>
                    <th className="px-3 py-2 font-medium">Detalle</th>
                    <th className="px-3 py-2 font-medium">Usuario</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedManagementHistory.length === 0 ? (
                    <tr>
                      <td colSpan="4" className="px-3 py-8 text-center text-sm text-slate-500">
                        No se encontraron gestiones para este filtro.
                      </td>
                    </tr>
                  ) : (
                    paginatedManagementHistory.map((item) => (
                      <tr key={item.id} className="border-b border-slate-100 align-top">
                        <td className="px-3 py-3 text-slate-700">{item.fecha ? new Date(item.fecha).toLocaleString("es-SV") : "Sin fecha"}</td>
                        <td className="px-3 py-3">
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700">
                            {String(item.accion || "Sin accion").replaceAll("_", " ")}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-slate-700">{item.descripcion || "Sin detalle adicional"}</td>
                        <td className="px-3 py-3 text-slate-700">Usuario #{item.usuario_id || "N/D"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <p className="text-sm text-slate-600">
                Mostrando {paginatedManagementHistory.length} de {filteredManagementHistory.length} gestiones.
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setManagementPage((current) => Math.max(1, current - 1))}
                  disabled={managementPage === 1}
                  className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Pagina anterior
                </button>
                <span className="text-sm font-medium text-slate-600">
                  Pagina {managementPage} de {totalHistoryPages}
                </span>
                <button
                  type="button"
                  onClick={() => setManagementPage((current) => Math.min(totalHistoryPages, current + 1))}
                  disabled={managementPage === totalHistoryPages}
                  className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Pagina siguiente
                </button>
              </div>
            </div>
            </> : <p className="pt-4 text-sm text-slate-500">Seccion minimizada.</p>}
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen px-4 py-5 md:px-8">
      <div className="mx-auto max-w-[1500px]">
        <header className="rounded-2xl bg-brand-gradient px-6 py-5 shadow-card-lg md:flex md:items-center md:justify-between relative overflow-hidden">
          <div className="absolute inset-0 opacity-10" style={{background:"radial-gradient(circle at 80% 50%, rgba(0,180,166,0.6) 0%, transparent 60%)"}} />
          <div className="relative flex items-center gap-4">
            <BrandLogo size="header" className="flex-shrink-0" />
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-teal">
                <span className="h-1.5 w-1.5 rounded-full bg-teal pulse-dot" />{auth.user.rol}
              </span>
              <h1 className="mt-1.5 text-xl font-bold text-white">Mesa integral del gestor</h1>
              <p className="mt-0.5 text-sm text-slate-300">Cartera diaria · Gestiones · Acuerdos · Copiloto IA</p>
            </div>
          </div>
          <div className="relative mt-4 flex items-center gap-3 md:mt-0">
            <div className="rounded-xl border border-white/10 bg-white/8 px-4 py-2.5 text-right">
              <p className="text-xs text-slate-400">Sesión activa</p>
              <p className="text-sm font-bold text-white">{auth.user.nombre}</p>
            </div>
            <button onClick={onRefresh} disabled={saving} className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20 disabled:opacity-50">
              ↻ Actualizar
            </button>
            <button onClick={onLogout} className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20">{exitLabel}</button>
          </div>
        </header>

        <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <StatCard title="Asignados hoy" value={metrics.assigned_today} detail="Clientes en agenda diaria" />
          <StatCard title="Pendientes" value={metrics.remaining_today} detail={`${metrics.worked_today} ya gestionados`} />
          <StatCard title="Acuerdos hoy" value={metrics.payment_agreements_today} detail={`${metrics.due_promises_today} vencen hoy`} />
          <StatCard title="Llamadas programadas" value={metrics.scheduled_callbacks_today} detail="Callbacks activos para hoy" />
          <StatCard title="Revision supervisor" value={metrics.supervisor_reviews_pending} detail="Acuerdos enviados a revision" />
        </section>

        <section className="mt-6 overflow-hidden rounded-[34px] border border-[#163046]/10 bg-[linear-gradient(135deg,#13293d,#1e4767_55%,#0b7285)] shadow-panel">
          <div className="grid gap-5 px-5 py-5 xl:grid-cols-[0.78fr_1.22fr]">
            <div className="text-white">
              <p className="text-xs uppercase tracking-[0.32em] text-cyan-200">Mapa inteligente de estrategias</p>
              <h2 className="mt-3 max-w-xl text-[2.1rem] font-bold leading-tight">Selecciona el frente de cobranza y entra a la lista con contexto, prioridad y lectura IA.</h2>
              <p className="mt-4 max-w-xl text-sm leading-7 text-slate-200">
                El tablero resume volumen, severidad y foco operativo por estrategia para que el collector no entre a una cartera plana, sino a una lista alineada al momento de mora y a la accion sugerida.
              </p>

              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <div className="rounded-3xl border border-white/10 bg-white/10 p-4 backdrop-blur">
                  <p className="text-xs uppercase tracking-[0.22em] text-cyan-100">Estrategia con mas clientes</p>
                  <p className="mt-3 text-2xl font-bold">{strategyLabels[leadingStrategy?.key] || "Sin datos"}</p>
                  <p className="mt-2 text-sm text-slate-200">{leadingStrategy?.value || 0} clientes visibles hoy</p>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/10 p-4 backdrop-blur">
                  <p className="text-xs uppercase tracking-[0.22em] text-cyan-100">Recomendacion IA</p>
                  <p className="mt-3 text-2xl font-bold">{metrics.hmr_candidates}</p>
                  <p className="mt-2 text-sm text-slate-200">casos con opcion de mitigacion HMR</p>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/10 p-4 backdrop-blur">
                  <p className="text-xs uppercase tracking-[0.22em] text-cyan-100">Tension operativa</p>
                  <p className="mt-3 text-2xl font-bold">{metrics.supervisor_reviews_pending}</p>
                  <p className="mt-2 text-sm text-slate-200">casos escalados a revision supervisor</p>
                </div>
              </div>

            </div>

            <div className="rounded-[28px] border border-white/10 bg-white/95 p-4 shadow-2xl">
              <div className="grid gap-3 xl:grid-cols-[1fr_0.62fr]">
                <div className="flex items-start justify-between gap-4 rounded-[24px] border border-slate-200 bg-white p-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.24em] text-ocean">Entrada por estrategia</p>
                    <h3 className="mt-2 text-[1.75rem] font-bold leading-tight text-ink">
                      {selectedStrategy ? `Trabajando ${strategyLabels[selectedStrategy] || selectedStrategy}` : "Elige una estrategia para comenzar"}
                    </h3>
                    <p className="mt-1 text-sm text-slate-600">
                      {selectedStrategy
                        ? strategyDescriptions[selectedStrategy] || "Lista operativa lista para gestion."
                        : "Cada tarjeta resume volumen, prioridad y lectura operacional para entrar a la cola correcta."}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-slate-100 px-3 py-2 text-right">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Visibles hoy</p>
                    <p className="mt-1 text-xl font-bold text-ink">{selectedStrategy ? filteredClients.length : metrics.assigned_today}</p>
                  </div>
                </div>

                <div className="rounded-[24px] border border-slate-200 bg-[#f8fbfd] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-ocean">Accion recomendada por IA</p>
                  <p className="mt-2 text-base font-semibold text-ink">
                    {selectedStrategy ? selectedStrategyInsights.recommendationTitle : "Selecciona una estrategia para recibir recomendacion"}
                  </p>
                  <p className="mt-1 text-sm font-medium text-ocean">
                    {selectedStrategy ? `Canal sugerido: ${selectedStrategyInsights.digitalChannel}` : ""}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">
                    {selectedStrategy ? selectedStrategyInsights.recommendationBody : "El sistema te sugerira el mejor canal de inicio segun riesgo, mora y recuperabilidad."}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button
                      onClick={() => {
                        if (!selectedStrategy || !queueClients.length) return;
                        const firstPendingIndex = Math.max(0, queueClients.findIndex((item) => !item.worked_today));
                        setQueueMode(true);
                        setQueueSearch("");
                        setQueueIndex(firstPendingIndex === -1 ? 0 : firstPendingIndex);
                        setSelectedClientId(queueClients[firstPendingIndex === -1 ? 0 : firstPendingIndex]?.id || null);
                        scrollToTop();
                      }}
                      disabled={!selectedStrategy || !queueClients.length}
                      className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Iniciar cola de trabajo
                    </button>
                    <span className="rounded-full bg-white px-4 py-3 text-sm text-slate-700">
                      {selectedStrategy
                        ? `${selectedSubgroup || strategyLabels[selectedStrategy] || selectedStrategy} lista para trabajar`
                        : "Esperando estrategia"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-4 grid gap-3 xl:grid-cols-4">
                {strategyDashboardCards.map((item) => (
                  <button
                    key={item.key}
                    onClick={() => {
                      setSelectedStrategy(item.key);
                      setSelectedSubgroup(null);
                      scrollToTop();
                    }}
                    onDoubleClick={() => {
                      setSelectedStrategy(item.key);
                      const strategyClients = item.key === "HMR"
                        ? portfolio.clients.filter((client) => client.hmr_elegible)
                        : portfolio.clients.filter((client) => client.estrategia_principal === item.key);
                      if (!strategyClients.length || item.key === "AL_DIA") return;
                      const nextSubgroup = item.key === "VAGENCIASEXTERNASINTERNO"
                        ? (() => {
                            const firstRecovery = strategyClients[0];
                            const placementCode = firstRecovery?.placement_code || "SIN_PLACEMENT";
                            const listCode = firstRecovery?.group_id || firstRecovery?.sublista_trabajo || "GENERAL";
                            return `PLACEMENT_${placementCode}_${listCode}`;
                          })()
                        : (strategyClients[0]?.estrategia_subgrupo || `${item.key}CARDS`);
                      setSelectedSubgroup(nextSubgroup);
                      setQueueMode(true);
                      setQueueSearch("");
                      setQueueIndex(0);
                      setSelectedClientId(strategyClients[0]?.id || null);
                      scrollToTop();
                    }}
                    className={`rounded-[24px] border p-3 text-left transition ${selectedStrategy === item.key ? "border-ocean bg-[linear-gradient(135deg,#e4fbff,#f6fbff)] shadow-lg" : "border-slate-200 bg-white hover:-translate-y-0.5 hover:border-cyan-200 hover:shadow-lg"}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{item.key}</p>
                        <h4 className="mt-2 text-base font-semibold text-ink">{item.displayLabel}</h4>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${selectedStrategy === item.key ? "bg-ink text-white" : "bg-mint text-ink"}`}>
                        {item.value}
                      </span>
                    </div>
                    <p className="mt-2 min-h-[52px] text-sm text-slate-600">{item.description}</p>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-[linear-gradient(90deg,#0b7285,#34d399)]" style={{ width: `${item.ratio}%` }} />
                    </div>
                    <p className="mt-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">{item.spotlight}</p>
                  </button>
                ))}
              </div>

              <div className="mt-4 grid gap-3 xl:grid-cols-1">
                <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Resumen de estrategia</p>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-base font-semibold text-ink">{selectedStrategy ? strategyLabels[selectedStrategy] || selectedStrategy : "Pendiente de seleccion"}</p>
                      <p className="mt-1 text-sm text-slate-600">
                        {selectedStrategy
                          ? `${filteredClients.length} clientes visibles${selectedSubgroup ? ` en ${selectedSubgroup}` : " para esta estrategia"}.`
                          : "Elige una estrategia para habilitar el ingreso a la cola."}
                      </p>
                    </div>
                    <span className="rounded-full bg-white px-3 py-2 text-sm font-semibold text-ink">
                      {selectedStrategy ? filteredClients.length : 0}
                    </span>
                  </div>

                  {selectedStrategy ? (
                    <div className="mt-4 rounded-[24px] border border-cyan-100 bg-[linear-gradient(135deg,#f3fbff,#eef8ff)] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-ocean">Estados y subgrupos</p>
                          <p className="mt-2 text-base font-semibold text-ink">
                            {activeSubgroupCard
                              ? selectedStrategy === "VAGENCIASEXTERNASINTERNO"
                                ? `${activeSubgroupCard.stateCode} · ${activeSubgroupCard.listCode || activeSubgroupCard.familyLabel}`
                                : `${activeSubgroupCard.stateCode} · ${activeSubgroupCard.familyLabel}`
                              : "Selecciona un subgrupo para entrar a la cola"}
                          </p>
                          <p className="mt-1 text-sm text-slate-600">
                            {activeSubgroupCard
                              ? `${activeSubgroupCard.key} con ${activeSubgroupCard.clients.length} clientes visibles para gestionar.`
                              : selectedStrategy === "VAGENCIASEXTERNASINTERNO"
                                ? "Recovery se divide por placement y lista operativa para iniciar cola de trabajo."
                                : `El estado principal de esta estrategia es ${strategyStateCode || "N/D"} y se divide por familia de producto.`}
                          </p>
                        </div>
                        <span className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink">
                          {subgroupCards.length} subgrupos
                        </span>
                      </div>

                      {selectedStrategy === "VAGENCIASEXTERNASINTERNO" ? (
                        <div className="mt-4 space-y-4">
                          {recoveryPlacementGroups.map((placement) => (
                            <section key={`placement-${placement.placementCode}`} className="rounded-[24px] border border-cyan-100 bg-white/75 p-4">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Placement</p>
                                  <h4 className="mt-2 text-lg font-semibold text-ink">{placement.placementCode}</h4>
                                  <p className="mt-1 text-sm text-slate-600">Carteras activas de este placement dentro de Recovery.</p>
                                </div>
                                <div className="flex flex-wrap gap-2 text-xs">
                                  <span className="rounded-full bg-cyan-50 px-3 py-1 font-semibold text-ocean">{placement.totalClients} clientes</span>
                                  <span className="rounded-full bg-white px-3 py-1 font-semibold text-slate-700">Pendientes {placement.pendingCount}</span>
                                  <span className="rounded-full bg-white px-3 py-1 font-semibold text-slate-700">Callbacks {placement.callbackCount}</span>
                                </div>
                              </div>
                              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                                {placement.lists.map((section) => (
                                  <button
                                    key={`subgroup-card-${section.key}`}
                                    type="button"
                                    onClick={() => {
                                      setSelectedSubgroup(section.key);
                                      setSelectedClientId(section.clients[0]?.id || null);
                                    }}
                                    onDoubleClick={() => {
                                      setSelectedSubgroup(section.key);
                                      setQueueMode(true);
                                      setQueueSearch("");
                                      setQueueIndex(0);
                                      setSelectedClientId(section.clients[0]?.id || null);
                                      scrollToTop();
                                    }}
                                    className={`rounded-[22px] border p-4 text-left transition ${
                                      selectedSubgroup === section.key
                                        ? "border-ocean bg-white shadow-lg"
                                        : "border-white/70 bg-slate-50/85 hover:-translate-y-0.5 hover:border-cyan-200 hover:bg-white"
                                    }`}
                                  >
                                    <div className="flex items-start justify-between gap-3">
                                      <div>
                                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{section.stateCode}</p>
                                        <h4 className="mt-2 text-sm font-semibold text-ink">{section.listCode || section.familyLabel}</h4>
                                        <p className="mt-1 text-xs text-slate-500">{section.description}</p>
                                      </div>
                                      <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-ocean">
                                        {section.clients.length}
                                      </span>
                                    </div>
                                    <div className="mt-4 grid gap-2 text-xs text-slate-600">
                                      <p>Pendientes: <span className="font-semibold text-ink">{section.pendingCount}</span></p>
                                      <p>Callbacks: <span className="font-semibold text-ink">{section.callbackCount}</span></p>
                                      <p>Cartera: <span className="font-semibold text-ink">{section.listCode || "GENERAL"}</span></p>
                                    </div>
                                  </button>
                                ))}
                              </div>
                            </section>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                          {subgroupCards.map((section) => (
                            <button
                              key={`subgroup-card-${section.key}`}
                              type="button"
                              onClick={() => {
                                setSelectedSubgroup(section.key);
                                setSelectedClientId(section.clients[0]?.id || null);
                              }}
                              onDoubleClick={() => {
                                setSelectedSubgroup(section.key);
                                if (selectedStrategy === "AL_DIA") return;
                                setQueueMode(true);
                                setQueueSearch("");
                                setQueueIndex(0);
                                setSelectedClientId(section.clients[0]?.id || null);
                                scrollToTop();
                              }}
                              className={`rounded-[22px] border p-4 text-left transition ${
                                selectedSubgroup === section.key
                                  ? "border-ocean bg-white shadow-lg"
                                  : "border-white/70 bg-white/80 hover:-translate-y-0.5 hover:border-cyan-200 hover:bg-white"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{section.stateCode}</p>
                                  <h4 className="mt-2 text-sm font-semibold text-ink">{section.familyLabel}</h4>
                                  <p className="mt-1 text-xs text-slate-500">{section.key}</p>
                                </div>
                                <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-ocean">
                                  {section.clients.length}
                                </span>
                              </div>
                              <div className="mt-4 grid gap-2 text-xs text-slate-600">
                                <p>Pendientes: <span className="font-semibold text-ink">{section.pendingCount}</span></p>
                                <p>Callbacks: <span className="font-semibold text-ink">{section.callbackCount}</span></p>
                                <p>Estado manual: <span className="font-semibold text-ink">{section.stateCode}</span></p>
                              </div>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : null}

                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Prob. IA promedio</p>
                      <p className="mt-1 text-xl font-bold text-ink">{selectedStrategyInsights.avgProbability}%</p>
                    </div>
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Confianza modelo</p>
                      <p className="mt-1 text-xl font-bold text-ink">{selectedStrategyInsights.confidence}</p>
                    </div>
                    <div className="rounded-2xl bg-white p-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Revision sup.</p>
                      <p className="mt-1 text-xl font-bold text-ink">{selectedStrategyInsights.reviewCount}</p>
                    </div>
                  </div>

                  <div className="mt-3 rounded-2xl bg-white p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Top clientes recomendados por IA</p>
                      <span className="text-xs font-semibold text-slate-500">{selectedStrategyInsights.topRecommendedClients.length} visibles</span>
                    </div>
                    <div className="mt-3 grid gap-2">
                      {selectedStrategyInsights.topRecommendedClients.length ? (
                        selectedStrategyInsights.topRecommendedClients.map((client) => (
                          <button
                            key={`ai-priority-${client.id}`}
                            type="button"
                            onClick={() => setSelectedClientId(client.id)}
                            className="rounded-2xl border border-slate-200 px-3 py-3 text-left transition hover:border-cyan-200 hover:bg-cyan-50"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="font-semibold text-ink">{client.nombre}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">{client.numeroUnico}</p>
                              </div>
                              <span className="rounded-full bg-mint px-3 py-1 text-xs font-semibold text-ink">{client.probability}%</span>
                            </div>
                            <p className="mt-2 text-sm text-slate-600">{client.channel}</p>
                          </button>
                        ))
                      ) : (
                        <p className="text-sm text-slate-500">Selecciona una estrategia para ver priorizacion por IA.</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-end gap-3">
                {selectedStrategy ? (
                  <button
                    onClick={() => {
                      setSelectedStrategy(null);
                      setSelectedSubgroup(null);
                      setSelectedClientId(null);
                    }}
                    className="rounded-full bg-slate-100 px-5 py-3 text-sm font-semibold text-ink"
                  >
                    Volver al mapa
                  </button>
                ) : null}
                {queueMode ? (
                  <button onClick={() => setQueueMode(false)} className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-ink">
                    Salir de cola
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </section>

        {error ? <p className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">{error}</p> : null}
        {success ? <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

        <section className="mt-6 grid gap-5 xl:grid-cols-[340px_1fr]">
          <aside className="glass rounded-3xl border border-white/60 p-5 shadow-panel">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-ink">Listas de trabajo</h2>
                <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">
                  {selectedStrategy
                    ? `${selectedSubgroup || `Estado ${strategyStateCode || selectedStrategy}`}`
                    : "Selecciona una estrategia para comenzar"}
                </p>
              </div>
              <span className="rounded-full bg-mint px-3 py-1 text-xs font-semibold text-ink">{filteredClients.length}</span>
            </div>
            <div className="max-h-[520px] space-y-4 overflow-y-auto pr-1">
              {!selectedStrategy ? (
                <section className="rounded-3xl border border-dashed border-slate-300 bg-white p-5">
                  <h3 className="text-sm font-semibold text-ink">Entrada por estrategia</h3>
                  <p className="mt-2 text-sm text-slate-600">
                    Selecciona arriba la estrategia que vas a trabajar. Luego veras sus listas de trabajo y podras entrar a la cola operativa.
                  </p>
                </section>
              ) : null}
              {selectedStrategy === "VAGENCIASEXTERNASINTERNO"
                ? recoveryPlacementGroups.map((placement) => (
                    <section key={`sidebar-placement-${placement.placementCode}`} className="rounded-3xl border border-cyan-100 bg-cyan-50/60 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-semibold text-ink">{placement.placementCode}</h3>
                          <p className="mt-1 text-xs text-slate-500">Placement Recovery</p>
                        </div>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink">{placement.totalClients}</span>
                      </div>
                      <div className="mt-3 space-y-3">
                        {placement.lists.map((section) => (
                          <div key={`sublist-${section.key}`} className={`rounded-2xl border p-3 ${selectedSubgroup === section.key ? "border-ocean bg-white" : "border-white/80 bg-white/80"}`}>
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <h4 className="text-sm font-semibold text-ink">{section.listCode || section.key}</h4>
                                <p className="mt-1 text-xs text-slate-500">{section.description}</p>
                              </div>
                              <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-ocean">{section.clients.length}</span>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.14em] text-slate-600">
                              <span className="rounded-full bg-white px-3 py-1">Pendientes {section.pendingCount}</span>
                              <span className="rounded-full bg-white px-3 py-1">Callbacks {section.callbackCount}</span>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setSelectedSubgroup(section.key);
                                  setSelectedClientId(section.clients[0]?.id || null);
                                }}
                                className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white"
                              >
                                Ver cartera
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setSelectedSubgroup(section.key);
                                  setQueueMode(true);
                                  setQueueSearch("");
                                  setQueueIndex(0);
                                  setSelectedClientId(section.clients[0]?.id || null);
                                  scrollToTop();
                                }}
                                className="rounded-full bg-white px-4 py-2 text-xs font-semibold text-ink"
                              >
                                Iniciar cola
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  ))
                : subgroupCards.map((section) => (
                    <section
                      key={`sublist-${section.key}`}
                      className={`rounded-3xl border p-4 ${selectedSubgroup === section.key ? "border-ocean bg-cyan-100/80" : "border-cyan-100 bg-cyan-50/60"}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-semibold text-ink">{section.stateCode} · {section.familyLabel}</h3>
                          <p className="mt-1 text-xs text-slate-500">{section.key} · {section.description}</p>
                        </div>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink">{section.clients.length}</span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.14em] text-slate-600">
                        <span className="rounded-full bg-white px-3 py-1">Pendientes {section.pendingCount}</span>
                        <span className="rounded-full bg-white px-3 py-1">Callbacks {section.callbackCount}</span>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedSubgroup(section.key);
                            setSelectedClientId(section.clients[0]?.id || null);
                          }}
                          className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white"
                        >
                          Ver subgrupo
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedSubgroup(section.key);
                            setQueueMode(true);
                            setQueueSearch("");
                            setQueueIndex(0);
                            setSelectedClientId(section.clients[0]?.id || null);
                            scrollToTop();
                          }}
                          disabled={selectedStrategy === "AL_DIA"}
                          className="rounded-full bg-white px-4 py-2 text-xs font-semibold text-ink"
                        >
                          {selectedStrategy === "AL_DIA" ? "Solo monitoreo" : "Iniciar cola"}
                        </button>
                      </div>
                    </section>
                  ))}
              {selectedSubgroup ? (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedSubgroup(null);
                    setSelectedClientId(null);
                  }}
                  className="w-full rounded-3xl border border-dashed border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-600"
                >
                  Ver todos los subgrupos y estados de {selectedStrategy}
                </button>
              ) : null}
              {worklistSections.map((section) => (
                <section key={section.key} className="rounded-3xl border border-slate-200 bg-white p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-ink">{section.title}</h3>
                      <p className="mt-1 text-xs text-slate-500">{section.description}</p>
                    </div>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{section.clients.length}</span>
                  </div>
                  <div className="mt-4 space-y-3">
                    {section.clients.length === 0 ? (
                      <p className="text-sm text-slate-500">No hay clientes en esta lista para la estrategia seleccionada.</p>
                    ) : (
                      section.clients.slice(0, 8).map((client) => (
                        <button
                          key={client.id}
                          onClick={() => {
                            setSelectedClientId(client.id);
                            if (queueMode) {
                              const targetIndex = queueClients.findIndex((item) => item.id === client.id);
                              if (targetIndex >= 0) setQueueIndex(targetIndex);
                            }
                          }}
                          className={`w-full rounded-3xl border p-4 text-left transition ${activeClient?.id === client.id ? "border-ocean bg-cyan-50" : "border-slate-200 bg-slate-50/70 hover:bg-white"}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-ink">{client.nombres} {client.apellidos}</p>
                              <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">{client.identity_code || "SIN NUMERO UNICO"} · {client.estrategia_principal}</p>
                              <p className="mt-1 text-[11px] uppercase tracking-[0.16em] text-ocean">
                                {selectedStrategy === "VAGENCIASEXTERNASINTERNO"
                                  ? `${client.placement_code || "SIN PLACEMENT"} · ${client.group_id || client.sublista_trabajo || "GENERAL"}`
                                  : (client.estrategia_subgrupo || client.sublista_trabajo || "GENERAL")}
                              </p>
                            </div>
                            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getClientOperationalStatus(client).tone}`}>
                              {getClientOperationalStatus(client).label}
                            </span>
                          </div>
                          <div className="mt-3 grid gap-1 text-sm text-slate-600">
                            <p>{client.segmento || "Sin segmento"} · {currency(client.total_outstanding)}</p>
                            <p>{client.producto_cabeza || "Sin producto cabeza"} · {client.dias_mora_cabeza || 0} dias</p>
                            <p>
                              {selectedStrategy === "VAGENCIASEXTERNASINTERNO"
                                ? (client.sublista_descripcion || "Lista de trabajo del placement actual")
                                : (client.segmento_operativo ? `Subgrupo ${client.segmento_operativo}` : (client.sublista_descripcion || "Lista operativa general"))}
                            </p>
                            <p>{client.telefono || "Sin telefono"} · {client.pending_promises.length} acuerdos activos</p>
                          </div>
                        </button>
                      ))
                    )}
                    {section.clients.length > 8 ? (
                      <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                        {section.clients.length - 8} clientes mas en esta lista
                      </p>
                    ) : null}
                  </div>
                </section>
              ))}
            </div>
          </aside>

          <div className="grid gap-6">
            {!selectedStrategy ? (
              <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
                <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                  <div className="rounded-[30px] border border-slate-200 bg-white p-6">
                    <p className="text-xs uppercase tracking-[0.24em] text-ocean">Vision IA del dia</p>
                    <h2 className="mt-3 text-3xl font-bold text-ink">Selecciona una estrategia para abrir su lista de trabajo especializada.</h2>
                    <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">
                      El sistema ordena el trabajo por momento de mora y te entrega un frente operativo listo para gestionar. Cada estrategia ya resume volumen visible, severidad y foco sugerido.
                    </p>
                    <div className="mt-5 grid gap-3 md:grid-cols-3">
                      <div className="rounded-3xl bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Volumen diario</p>
                        <p className="mt-2 text-3xl font-bold text-ink">{metrics.assigned_today}</p>
                        <p className="mt-2 text-sm text-slate-600">clientes visibles para la jornada</p>
                      </div>
                      <div className="rounded-3xl bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Promesas hoy</p>
                        <p className="mt-2 text-3xl font-bold text-ink">{metrics.payment_agreements_today}</p>
                        <p className="mt-2 text-sm text-slate-600">acuerdos creados en el dia</p>
                      </div>
                      <div className="rounded-3xl bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Recuperacion guiada</p>
                        <p className="mt-2 text-3xl font-bold text-ink">{metrics.hmr_candidates}</p>
                        <p className="mt-2 text-sm text-slate-600">casos candidatos a mitigacion</p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[30px] border border-slate-200 bg-[#10283c] p-6 text-white">
                    <p className="text-xs uppercase tracking-[0.24em] text-cyan-200">Radar operativo</p>
                    <div className="mt-5 grid gap-3">
                      {strategyDashboardCards.slice(0, 4).map((item) => (
                        <div key={`radar-${item.key}`} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold">{item.displayLabel}</p>
                              <p className="mt-1 text-xs text-slate-300">{item.spotlight}</p>
                            </div>
                            <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold">{item.value}</span>
                          </div>
                          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                            <div className="h-full rounded-full bg-[linear-gradient(90deg,#34d399,#67e8f9)]" style={{ width: `${item.ratio}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </section>
            ) : activeClient ? (
              <>
                <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
                  <div className="grid gap-5 xl:grid-cols-[1.25fr_0.95fr]">
                    <div>
                      <p className="text-sm uppercase tracking-[0.22em] text-ocean">Cliente activo</p>
                      <h2 className="mt-2 text-3xl font-bold text-ink">{activeClient.nombres} {activeClient.apellidos}</h2>
                      <p className="mt-2 text-sm text-slate-600">Estrategia {activeClient.estrategia_principal} · Riesgo {Math.round(activeClient.score_riesgo * 100)}%</p>
                      <div className="mt-4 flex flex-wrap gap-3 text-sm">
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">Numero Unico: {activeClient.identity_code || "No disponible"}</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">DUI: {activeClient.dui || "No disponible"}</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">Segmento: {activeClient.segmento || "Sin segmento"}</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">Subgrupo: {activeClient.estrategia_subgrupo || activeClient.estrategia_principal}</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">
                          {selectedStrategy === "VAGENCIASEXTERNASINTERNO"
                            ? `Placement: ${activeClient.placement_code || "N/D"} · Lista: ${activeClient.group_id || activeClient.sublista_trabajo || "GENERAL"}`
                            : `Sublista: ${activeClient.sublista_trabajo || "GENERAL"}`}
                        </span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">Cabeza: {activeClient.producto_cabeza || "N/D"} · {activeClient.dias_mora_cabeza || 0} dias</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">HMR: {activeClient.hmr_elegible ? "Aplica" : "No aplica"}</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">Promesas activas: {activeClient.pending_promises.length}</span>
                        <span className="rounded-full bg-white px-3 py-2 text-slate-700">Callback: {activeClient.next_callback_at ? new Date(activeClient.next_callback_at).toLocaleString("es-SV") : "No programado"}</span>
                        <span className={`rounded-full px-3 py-2 font-semibold ${activeStatus.tone}`}>Estado: {activeStatus.label}</span>
                      </div>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                      <div className="rounded-3xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Contacto</p>
                        <p className="mt-2 text-sm text-slate-700">{activeClient.telefono || "Pendiente"}</p>
                        <p className="mt-1 text-sm text-slate-700">{activeClient.email || "Pendiente"}</p>
                        <button
                          type="button"
                          onClick={openDemographicEditor}
                          className="mt-3 rounded-full bg-ocean px-4 py-2 text-xs font-semibold text-white"
                        >
                          Agregar o modificar datos
                        </button>
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Agenda y gestion</p>
                        <p className="mt-2 text-sm text-slate-700">Ultima gestion: {activeClient.last_management || "Sin registro"}</p>
                        <p className="mt-1 text-sm text-slate-700">Direccion: {activeClient.direccion || "No registrada"}</p>
                        {queueMode ? <p className="mt-1 text-sm text-slate-700">Cola diaria: <span className="font-semibold text-ink">{queueIndex + 1} de {queueClients.length}</span></p> : null}
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white p-4 md:col-span-2 xl:col-span-1">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Copiloto de cobranza</p>
                        <p className="mt-2 text-sm font-semibold text-ink">Canal optimo: {activeClient.ai_best_channel || "Sin sugerencia"}</p>
                        <p className="mt-1 text-sm text-slate-700">
                          Ruptura de promesa: {activeClient.ai_promise_break_probability != null ? `${(activeClient.ai_promise_break_probability * 100).toFixed(0)}%` : "Sin calcular"}
                        </p>
                        <p className="mt-2 text-sm text-slate-700">Siguiente accion: {activeClient.ai_next_action || "Sin sugerencia disponible"}</p>
                        <p className="mt-2 text-sm text-slate-600">{activeClient.ai_talk_track || "El copiloto generara un discurso segun estrategia, mora y riesgo."}</p>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="glass rounded-3xl border border-white/60 p-5 shadow-panel">
                  <div className="flex flex-wrap gap-3">
                    {tabs.map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        className={`rounded-full px-4 py-2 text-sm font-semibold ${activeTab === tab.key ? "bg-ink text-white" : "bg-white text-ink"}`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {activeTab === "deudor" ? (
                    <div className="mt-5 grid gap-6 xl:grid-cols-[1fr_0.9fr]">
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Informacion del deudor</h3>
                        <div className="mt-4 grid gap-3 text-sm text-slate-700 md:grid-cols-2">
                          <p><span className="font-semibold text-ink">Numero Unico:</span> {activeClient.identity_code || "No disponible"}</p>
                          <p><span className="font-semibold text-ink">DUI:</span> {activeClient.dui || "No disponible"}</p>
                          <p><span className="font-semibold text-ink">Segmento:</span> {activeClient.segmento || "Sin segmento"}</p>
                          <p><span className="font-semibold text-ink">Telefono:</span> {activeClient.telefono || "Pendiente"}</p>
                          <p><span className="font-semibold text-ink">Correo:</span> {activeClient.email || "Pendiente"}</p>
                          <p className="md:col-span-2"><span className="font-semibold text-ink">Direccion:</span> {activeClient.direccion || "Sin direccion registrada"}</p>
                        </div>
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Agenda del cliente</h3>
                        <div className="mt-4 space-y-3 text-sm text-slate-700">
                          <p>Estado del dia: <span className="font-semibold text-ink">{activeClient.worked_today ? "Ya gestionado" : "Pendiente de contactar"}</span></p>
                          <p>Acuerdos pendientes: <span className="font-semibold text-ink">{activeClient.pending_promises.length}</span></p>
                          <p>Saldo total en cartera: <span className="font-semibold text-ink">{currency(activeClient.total_outstanding)}</span></p>
                          <p>Ultima gestion: <span className="font-semibold text-ink">{activeClient.last_management || "Sin registro"}</span></p>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {activeTab === "demografica" ? (
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        onUpdateDemographics(activeClient, demographicForm, onRefresh);
                      }}
                      className="mt-5 grid gap-6 xl:grid-cols-[1fr_0.95fr]"
                    >
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Informacion demografica</h3>
                        <div className="mt-4 grid gap-4">
                          <div>
                            <label className="text-sm font-medium text-slate-700">Telefono</label>
                            <input value={demographicForm.telefono} onChange={(event) => setDemographicForm((current) => ({ ...current, telefono: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" />
                          </div>
                          <div>
                            <label className="text-sm font-medium text-slate-700">Correo electronico</label>
                            <input value={demographicForm.email} onChange={(event) => setDemographicForm((current) => ({ ...current, email: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" />
                          </div>
                          <div>
                            <label className="text-sm font-medium text-slate-700">Direccion fisica</label>
                            <textarea value={demographicForm.direccion} onChange={(event) => setDemographicForm((current) => ({ ...current, direccion: event.target.value }))} rows="6" className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" />
                          </div>
                        </div>
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Verificacion de contacto</h3>
                        <div className="mt-4 space-y-3 text-sm text-slate-700">
                          <p>Telefono vigente: <span className="font-semibold text-ink">{demographicForm.telefono || "No"}</span></p>
                          <p>Correo vigente: <span className="font-semibold text-ink">{demographicForm.email || "No"}</span></p>
                          <p>Direccion vigente: <span className="font-semibold text-ink">{demographicForm.direccion ? "Si" : "No"}</span></p>
                        </div>
                        <button disabled={saving} className="mt-6 w-full rounded-2xl bg-ocean px-4 py-3 font-semibold text-white disabled:opacity-70">
                          {saving ? "Actualizando..." : "Guardar datos del cliente"}
                        </button>
                      </div>
                    </form>
                  ) : null}

                  {activeTab === "financiera" ? (
                    <div className="mt-5 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Cuentas en mora y datos financieros</h3>
                        <div className="mt-4 space-y-3">
                          {activeClient.accounts.map((account) => (
                            <div key={account.id} className={`rounded-2xl border p-4 ${selectedAccount?.id === account.id ? "border-ocean bg-cyan-50" : "border-slate-200"}`}>
                              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                <div>
                                  <p className="font-semibold text-ink">{account.numero_cuenta}</p>
                                  <p className="text-sm text-slate-600">{account.producto_nombre || account.tipo_producto} · {account.subtipo_producto || "Base"} · {account.estrategia}</p>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => setManagementForm((current) => ({ ...current, account_id: String(account.id), promise_amount: String(account.pago_minimo || "") }))}
                                  className="rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white"
                                >
                                  Seleccionar
                                </button>
                              </div>
                              <div className="mt-3 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
                                <p>Saldo total: <span className="font-semibold text-ink">{currency(account.saldo_total)}</span></p>
                                <p>Saldo mora: <span className="font-semibold text-ink">{currency(account.saldo_mora)}</span></p>
                                <p>Dias de mora: <span className="font-semibold text-ink">{account.dias_mora}</span></p>
                                <p>Bucket: <span className="font-semibold text-ink">{account.bucket_actual}</span></p>
                                <p>Ciclo / vencimiento: <span className="font-semibold text-ink">{account.ciclo_corte} / {account.dia_vencimiento}</span></p>
                                <p>Pago minimo: <span className="font-semibold text-ink">{currency(account.pago_minimo)}</span></p>
                                <p>Estado: <span className="font-semibold text-ink">{account.estado}</span></p>
                                <p>HMR: <span className="font-semibold text-ink">{account.hmr_elegible ? "Aplica" : "No aplica"}</span></p>
                                <p>Plastico: <span className="font-semibold text-ink">{account.numero_plastico || "No aplica"}</span></p>
                                <p>Ubicacion: <span className="font-semibold text-ink">{account.codigo_ubicacion || "N/D"}</span></p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Agenda y acuerdos</h3>
                        <div className="mt-4 space-y-3">
                          {activeClient.pending_promises.length === 0 ? (
                            <p className="text-sm text-slate-500">No hay acuerdos de pago pendientes para este cliente.</p>
                          ) : (
                            activeClient.pending_promises.map((promise) => (
                              <div key={promise.id} className="rounded-2xl border border-slate-200 p-4">
                                <p className="font-semibold text-ink">Promesa #{promise.id}</p>
                                <p className="mt-2 text-sm text-slate-600">Cuenta #{promise.cuenta_id}</p>
                                <p className="text-sm text-slate-600">Fecha comprometida: {new Date(promise.fecha_promesa).toLocaleDateString("es-SV")}</p>
                                <p className="text-sm text-slate-600">Monto: {currency(promise.monto_prometido)}</p>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {activeTab === "gestion" ? (
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        onSubmitManagement(activeClient, managementForm, selectedAccount, () =>
                          setManagementForm((current) => ({
                            ...current,
                            notes: "",
                            promise_date: "",
                            account_ids: activeClient.accounts?.length ? [String(activeClient.accounts[0].id)] : [],
                            called_phone: activeClient.telefono || "",
                            rdm: "",
                            promise_amount: String(activeClient.accounts?.[0]?.pago_minimo || ""),
                            callback_at: ""
                          }))
                        );
                      }}
                      className="mt-5 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]"
                    >
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Registrar gestion de cobranza</h3>
                        <div className="mt-4 grid gap-4">
                          <div>
                            <label className="text-sm font-medium text-slate-700">Cuenta a gestionar</label>
                            <select value={managementForm.account_id} onChange={(event) => setManagementForm((current) => ({ ...current, account_id: event.target.value, account_ids: [event.target.value], promise_amount: String(activeClient.accounts.find((account) => String(account.id) === event.target.value)?.pago_minimo || "") }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3">
                              {activeClient.accounts.map((account) => (
                                <option key={account.id} value={account.id}>{account.numero_cuenta} · {currency(account.saldo_total)}</option>
                              ))}
                            </select>
                          </div>
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <label className="text-sm font-medium text-slate-700">Canal</label>
                              <select value={managementForm.contact_channel} onChange={(event) => setManagementForm((current) => ({ ...current, contact_channel: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3">
                                <option>Llamada</option>
                                <option>WhatsApp</option>
                                <option>SMS</option>
                                <option>Correo</option>
                                <option>Visita</option>
                              </select>
                            </div>
                            <div>
                              <label className="text-sm font-medium text-slate-700">Telefono gestionado</label>
                              <input value={managementForm.called_phone} onChange={(event) => setManagementForm((current) => ({ ...current, called_phone: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Numero al que se llamo o contacto" />
                            </div>
                            <div>
                              <label className="text-sm font-medium text-slate-700">Razon de mora (RDM)</label>
                              <select value={managementForm.rdm} onChange={(event) => setManagementForm((current) => ({ ...current, rdm: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3">
                                <option value="">Seleccionar razon de mora</option>
                                {moraReasonOptions.map((option) => (
                                  <option key={option} value={option}>
                                    {option}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <label className="text-sm font-medium text-slate-700">Tipo de gestion</label>
                              <select value={managementForm.management_type} onChange={(event) => setManagementForm((current) => ({ ...current, management_type: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3">
                                <option>Llamada de cobranza</option>
                                <option>Seguimiento a promesa</option>
                                <option>Recordatorio preventivo</option>
                                <option>Escalamiento supervisor</option>
                              </select>
                            </div>
                          </div>
                          <div>
                            <label className="text-sm font-medium text-slate-700">Resultado</label>
                            <select value={managementForm.result} onChange={(event) => setManagementForm((current) => ({ ...current, result: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3">
                              <option>Contactado</option>
                              <option>No localizado</option>
                              <option>Promesa de pago</option>
                              <option>Rechazo</option>
                              <option>Escalar visita</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-sm font-medium text-slate-700">Notas de gestion</label>
                            <textarea value={managementForm.notes} onChange={(event) => setManagementForm((current) => ({ ...current, notes: event.target.value }))} rows="5" className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Detalle de la gestion, objeciones y siguientes pasos." />
                          </div>
                        </div>
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white p-5">
                        <h3 className="text-lg font-semibold text-ink">Acuerdo de pago</h3>
                        <div className="mt-4 grid gap-4">
                          <div>
                            <label className="text-sm font-medium text-slate-700">Productos incluidos en el acuerdo</label>
                            <div className="mt-2 grid gap-2">
                              {activeClient.accounts.map((account) => {
                                const checked = managementForm.account_ids.includes(String(account.id));
                                return (
                                  <label key={`promise-account-${account.id}`} className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                                    <div>
                                      <p className="font-semibold text-ink">{account.numero_cuenta} · {account.tipo_producto}</p>
                                      <p className="mt-1 text-xs text-slate-500">{account.estrategia} · Pago minimo {currency(account.pago_minimo)}</p>
                                    </div>
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={(event) => {
                                        setManagementForm((current) => {
                                          const nextIds = event.target.checked
                                            ? Array.from(new Set([...current.account_ids, String(account.id)]))
                                            : current.account_ids.filter((id) => id !== String(account.id));
                                          const fallbackId = nextIds[0] || String(account.id);
                                          const nextMinimum = activeClient.accounts
                                            .filter((item) => nextIds.includes(String(item.id)))
                                            .reduce((sum, item) => sum + Number(item.pago_minimo || 0), 0);
                                          return {
                                            ...current,
                                            account_id: fallbackId,
                                            account_ids: nextIds,
                                            promise_amount: nextIds.length ? String(nextMinimum.toFixed(2)) : current.promise_amount,
                                          };
                                        });
                                      }}
                                    />
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <label className="text-sm font-medium text-slate-700">Fecha y hora callback</label>
                              <input type="datetime-local" value={managementForm.callback_at} onChange={(event) => setManagementForm((current) => ({ ...current, callback_at: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" />
                            </div>
                            <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
                              <p>Callback actual: <span className="font-semibold text-ink">{activeClient.next_callback_at ? new Date(activeClient.next_callback_at).toLocaleString("es-SV") : "No programado"}</span></p>
                              <p className="mt-1">Revision supervisor: <span className="font-semibold text-ink">{activeClient.requires_supervisor_review ? "Pendiente" : "Sin revision"}</span></p>
                            </div>
                          </div>
                          <div>
                            <label className="text-sm font-medium text-slate-700">Fecha de acuerdo</label>
                            <input type="date" value={managementForm.promise_date} onChange={(event) => setManagementForm((current) => ({ ...current, promise_date: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" />
                          </div>
                          <div>
                            <label className="text-sm font-medium text-slate-700">Monto acordado</label>
                            <input type="number" min="0" step="0.01" value={managementForm.promise_amount} onChange={(event) => setManagementForm((current) => ({ ...current, promise_amount: event.target.value }))} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="0.00" />
                            <p className="mt-2 text-xs text-slate-500">Pago minimo sugerido: {currency(selectedAccountsMinimum || selectedAccount?.pago_minimo || 0)}</p>
                          </div>
                          <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
                            <p>Cuentas incluidas: <span className="font-semibold text-ink">{selectedAccounts.length || 1}</span></p>
                            <p className="mt-1">Principal: <span className="font-semibold text-ink">{selectedAccount?.numero_cuenta || "Sin cuenta"}</span></p>
                            <p className="mt-1">Pago minimo total: <span className="font-semibold text-ink">{currency(selectedAccountsMinimum || selectedAccount?.pago_minimo || 0)}</span></p>
                          </div>
                          <button disabled={saving} className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70">
                            {saving ? "Guardando..." : "Registrar gestion"}
                          </button>
                          {queueMode ? (
                            <div className="flex gap-3">
                              <button type="button" onClick={() => setQueueIndex((current) => Math.max(0, current - 1))} className="flex-1 rounded-2xl bg-white px-4 py-3 font-semibold text-ink">
                                Cliente anterior
                              </button>
                              <button type="button" onClick={() => setQueueIndex((current) => Math.min(queueClients.length - 1, current + 1))} className="flex-1 rounded-2xl bg-mint px-4 py-3 font-semibold text-ink">
                                Siguiente cliente
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </form>
                  ) : null}
                </section>
              </>
            ) : (
              <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
                <p className="text-sm text-slate-500">No hay clientes asignados en la cartera del collector.</p>
              </section>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function SupervisorWorkspace({ auth, overview, systemClients, onSearchSystemClients, onLogout, onRefresh, onApproveReview, onApproveReviewBatch, onOpenCollectorPreview, collectorPreviewLoading, saving, error }) {
  const [showReviewQueue, setShowReviewQueue] = useState(false);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [reviewPage, setReviewPage] = useState(1);
  const [reviewProgress, setReviewProgress] = useState({});
  const [selectedCollectorId, setSelectedCollectorId] = useState("");
  const [systemSearch, setSystemSearch] = useState("");
  const supervisedCollectors = (overview?.collectors || []).map((collector) => collector.user || collector).filter((collector) => collector?.id);
  useEffect(() => {
    if (!supervisedCollectors.length) {
      setSelectedCollectorId("");
      return;
    }
    setSelectedCollectorId((current) => current || String(supervisedCollectors[0].id));
  }, [overview]);

  if (!overview) {
    return <p className="p-8 text-sm text-slate-500">Cargando equipo supervisado...</p>;
  }

  const reviewQueue = overview.review_queue || [];
  const reviewPageSize = 10;
  const totalReviewPages = Math.max(1, Math.ceil(reviewQueue.length / reviewPageSize));
  const currentPage = Math.min(reviewPage, totalReviewPages);
  const pageStart = (currentPage - 1) * reviewPageSize;
  const paginatedReviewQueue = reviewQueue.slice(pageStart, pageStart + reviewPageSize);
  const visibleStart = reviewQueue.length ? pageStart + 1 : 0;
  const visibleEnd = reviewQueue.length ? Math.min(pageStart + reviewPageSize, reviewQueue.length) : 0;
  const activeReview = reviewQueue[reviewIndex] || null;
  const activeProgress = activeReview ? reviewProgress[activeReview.promise_id] || { reviewing: false, reviewed: false } : { reviewing: false, reviewed: false };

  if (showReviewQueue && activeReview) {
    return (
      <div className="min-h-screen bg-[linear-gradient(180deg,#eef3f8,#f9fbfd)] px-4 py-5 md:px-8">
        <div className="mx-auto max-w-[1500px]">
          <header className="overflow-hidden rounded-[30px] bg-[#24384d] text-white shadow-panel">
            <div className="flex flex-col gap-4 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-4">
                <BrandLogo size="header" />
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-orange-200">Revision supervisor</p>
                  <h1 className="mt-2 text-3xl font-bold">Cola de acuerdos fuera de politica</h1>
                </div>
              </div>
              <div className="grid gap-2 text-sm text-slate-200 lg:text-right">
                <p>Supervisor: {auth.user.nombre}</p>
                <p>Caso activo: {reviewIndex + 1} de {reviewQueue.length}</p>
                <p>Fecha: {new Date().toLocaleDateString("es-SV")}</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 bg-[#31485f] px-6 py-4 text-sm font-semibold">
              <button onClick={() => setShowReviewQueue(false)} className="rounded-full bg-white px-4 py-2 text-ink">Volver al panel</button>
              <button
                onClick={() => {
                  const nextIndex = Math.max(0, reviewIndex - 1);
                  setReviewIndex(nextIndex);
                  setReviewPage(Math.floor(nextIndex / reviewPageSize) + 1);
                }}
                className="rounded-full bg-white/10 px-4 py-2"
              >
                Anterior
              </button>
              <button
                onClick={() => {
                  const nextIndex = Math.min(reviewQueue.length - 1, reviewIndex + 1);
                  setReviewIndex(nextIndex);
                  setReviewPage(Math.floor(nextIndex / reviewPageSize) + 1);
                }}
                disabled={!activeProgress.reviewed}
                className="rounded-full bg-white/10 px-4 py-2 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Siguiente
              </button>
              <span className="rounded-full bg-orange-500/20 px-4 py-2">Revision: {reviewQueue.length} casos</span>
              <span className="rounded-full bg-red-500/20 px-4 py-2">Alertas: {(overview.alerts || []).length}</span>
            </div>
          </header>

          {error ? <p className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">{error}</p> : null}

          <section className="mt-5 grid gap-4 xl:grid-cols-[1fr_1fr_0.9fr]">
            <section className="rounded-[26px] border border-slate-200 bg-white p-5 shadow-panel">
              <h2 className="border-b border-orange-200 pb-3 text-2xl font-bold text-ink">Cliente en revision</h2>
              <div className="mt-4 grid gap-2 text-sm text-slate-700">
                <p><span className="font-semibold text-ink">Cliente:</span> {activeReview.client_name}</p>
                <p><span className="font-semibold text-ink">Cuenta:</span> {activeReview.account_number}</p>
                <p><span className="font-semibold text-ink">Gestor asignado:</span> {activeReview.collector_name}</p>
                <p><span className="font-semibold text-ink">Usuario gestor:</span> {activeReview.collector_username}</p>
                <p><span className="font-semibold text-ink">Id cliente:</span> {activeReview.client_id}</p>
              </div>
            </section>

            <section className="rounded-[26px] border border-slate-200 bg-white p-5 shadow-panel">
              <h2 className="border-b border-orange-200 pb-3 text-2xl font-bold text-ink">Condiciones del acuerdo</h2>
              <div className="mt-4 grid gap-2 text-sm text-slate-700">
                <p><span className="font-semibold text-ink">Monto acordado:</span> {currency(activeReview.agreed_amount)}</p>
                <p><span className="font-semibold text-ink">Monto minimo:</span> {currency(activeReview.minimum_amount)}</p>
                <p><span className="font-semibold text-ink">Fecha compromiso:</span> {new Date(activeReview.scheduled_date).toLocaleDateString("es-SV")}</p>
                <p><span className="font-semibold text-ink">Diferencia:</span> {currency((activeReview.minimum_amount || 0) - (activeReview.agreed_amount || 0))}</p>
              </div>
              <div className="mt-4 rounded-2xl bg-orange-50 p-4 text-sm text-orange-800">
                Este acuerdo fue enviado por politicas de monto o plazo y requiere validacion del supervisor.
              </div>
            </section>

            <section className="rounded-[26px] border border-slate-200 bg-white p-5 shadow-panel">
              <h2 className="border-b border-orange-200 pb-3 text-2xl font-bold text-ink">Indicadores</h2>
              <div className="mt-4 grid gap-2 text-sm text-slate-700">
                <p><span className="font-semibold text-ink">Estado:</span> Revision Supervisor</p>
                <p><span className="font-semibold text-ink">Casos pendientes:</span> {reviewQueue.length}</p>
                <p><span className="font-semibold text-ink">Alertas de plazo:</span> {(overview.alerts || []).filter((item) => item.promise_id === activeReview.promise_id).length > 0 ? "Si" : "No"}</p>
              </div>
              <div className={`mt-4 rounded-2xl px-4 py-3 text-sm font-semibold ${(overview.alerts || []).filter((item) => item.promise_id === activeReview.promise_id).length > 0 ? "bg-red-500 text-white" : "bg-amber-100 text-amber-800"}`}>
                {(overview.alerts || []).filter((item) => item.promise_id === activeReview.promise_id).length > 0 ? "Acuerdo con alerta por plazo mayor a 10 dias" : "Pendiente de decision del supervisor"}
              </div>
            </section>
          </section>

          <section className="mt-5 rounded-[26px] border border-slate-200 bg-white p-5 shadow-panel">
            <h2 className="border-b border-orange-200 pb-3 text-2xl font-bold text-ink">Revision enfocada</h2>
            <div className="mt-5 grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <h3 className="text-lg font-semibold text-ink">Navegacion</h3>
                <div className="mt-4 grid gap-3 text-sm text-slate-700">
                  <p>La cola se divide en bloques de 10 para que la pantalla no se vuelva pesada.</p>
                  <p>Caso actual: <span className="font-semibold text-ink">{reviewIndex + 1}</span> de <span className="font-semibold text-ink">{reviewQueue.length}</span></p>
                  <p>Mostrando: <span className="font-semibold text-ink">{visibleStart}-{visibleEnd}</span> de <span className="font-semibold text-ink">{reviewQueue.length}</span></p>
                  <p>Pagina: <span className="font-semibold text-ink">{currentPage}</span> de <span className="font-semibold text-ink">{totalReviewPages}</span></p>
                  <p>Cliente activo: <span className="font-semibold text-ink">{activeReview.client_name}</span></p>
                  <p>Usa los botones <span className="font-semibold text-ink">Anterior</span> y <span className="font-semibold text-ink">Siguiente</span> del encabezado para recorrer la cola.</p>
                </div>
                <div className="mt-5 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      const nextPage = Math.max(1, currentPage - 1);
                      setReviewPage(nextPage);
                      setReviewIndex((nextPage - 1) * reviewPageSize);
                    }}
                    disabled={currentPage === 1}
                    className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-ink disabled:opacity-40"
                  >
                    Pagina anterior
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const nextPage = Math.min(totalReviewPages, currentPage + 1);
                      setReviewPage(nextPage);
                      setReviewIndex((nextPage - 1) * reviewPageSize);
                    }}
                    disabled={currentPage === totalReviewPages}
                    className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-ink disabled:opacity-40"
                  >
                    Pagina siguiente
                  </button>
                </div>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <h3 className="text-lg font-semibold text-ink">Accion sugerida</h3>
                <div className="mt-4 grid gap-3 text-sm text-slate-700">
                  <p>1. Validar si el plazo o monto cumplen excepcion operativa.</p>
                  <p>2. Revisar historial del gestor y trazabilidad del cliente.</p>
                  <p>3. Aprobar, ajustar o devolver el caso en siguiente iteracion.</p>
                </div>
                <div className="mt-5 grid gap-3">
                  <button
                    type="button"
                    onClick={() =>
                      setReviewProgress((current) => ({
                        ...current,
                        [activeReview.promise_id]: {
                          ...(current[activeReview.promise_id] || {}),
                          reviewing: true,
                          reviewed: false
                        }
                      }))
                    }
                    className={`rounded-2xl px-4 py-3 font-semibold ${activeProgress.reviewing ? "bg-amber-500 text-white" : "bg-white text-ink"}`}
                  >
                    Revisar deudor
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onApproveReview(activeReview.promise_id, () => {
                        setReviewProgress((current) => ({
                          ...current,
                          [activeReview.promise_id]: {
                            ...(current[activeReview.promise_id] || {}),
                            reviewing: true,
                            reviewed: true
                          }
                        }));
                        setReviewIndex((current) => Math.max(0, Math.min(current, reviewQueue.length - 2)));
                      })
                    }
                    disabled={!activeProgress.reviewing || saving}
                    className="rounded-2xl bg-emerald-600 px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {saving ? "Actualizando..." : "Revisado"}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onApproveReviewBatch(
                        paginatedReviewQueue.map((item) => item.promise_id),
                        () => {
                          setReviewProgress((current) => {
                            const next = { ...current };
                            paginatedReviewQueue.forEach((item) => {
                              next[item.promise_id] = { reviewing: true, reviewed: true };
                            });
                            return next;
                          });
                        }
                      )
                    }
                    disabled={saving || paginatedReviewQueue.length === 0}
                    className="rounded-2xl bg-ocean px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {saving ? "Procesando..." : `Revisar pagina (${paginatedReviewQueue.length})`}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onApproveReviewBatch(
                        reviewQueue.map((item) => item.promise_id),
                        () => {
                          setReviewProgress((current) => {
                            const next = { ...current };
                            reviewQueue.forEach((item) => {
                              next[item.promise_id] = { reviewing: true, reviewed: true };
                            });
                            return next;
                          });
                        }
                      )
                    }
                    disabled={saving || reviewQueue.length === 0}
                    className="rounded-2xl bg-brand-blue px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {saving ? "Procesando..." : `Revisar todos (${reviewQueue.length})`}
                  </button>
                  <p className="text-sm text-slate-600">
                    {activeProgress.reviewed
                      ? "Caso revisado. Ya puedes pasar al siguiente cliente."
                      : activeProgress.reviewing
                        ? "Marca el caso como revisado para continuar."
                        : "Primero debes revisar el deudor antes de continuar."}
                  </p>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen px-4 py-5 md:px-8">
      <div className="mx-auto max-w-[1680px]">
        <header className="rounded-2xl bg-brand-gradient px-6 py-5 shadow-card-lg md:flex md:items-center md:justify-between relative overflow-hidden">
          <div className="absolute inset-0 opacity-10" style={{background:"radial-gradient(circle at 80% 50%, rgba(0,180,166,0.6) 0%, transparent 60%)"}} />
          <div className="relative flex items-center gap-4">
            <BrandLogo size="header" className="flex-shrink-0" />
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-teal">
                <span className="h-1.5 w-1.5 rounded-full bg-teal pulse-dot" />{auth.user.rol}
              </span>
              <h1 className="mt-1.5 text-xl font-bold text-white">Mesa de supervisión</h1>
              <p className="mt-0.5 text-sm text-slate-300">Equipo · Métricas · Revisión de promesas · Alertas</p>
            </div>
          </div>
          <div className="relative mt-4 flex items-center gap-3 md:mt-0">
            <div className="rounded-xl border border-white/10 bg-white/8 px-4 py-2.5 text-right">
              <p className="text-xs text-slate-400">Sesión activa</p>
              <p className="text-sm font-bold text-white">{auth.user.nombre}</p>
            </div>
            <button onClick={onRefresh} disabled={saving} className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20 disabled:opacity-50">
              ↻ Actualizar
            </button>
            <button onClick={onLogout} className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20">Cerrar sesión</button>
          </div>
        </header>

        {error ? <p className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">{error}</p> : null}

        <section className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          <StatCard title="Gestores asignados" value={overview.team_size} detail="Equipo bajo supervision" />
          <StatCard title="Gestiones del dia" value={overview.managed_today} detail="Clientes trabajados hoy" />
          <StatCard title="Acuerdos de pago" value={overview.payment_agreements_today} detail="Compromisos creados por el equipo" />
          <StatCard title="Balance salvado" value={currency(overview.recovered_balance_today)} detail="Monto comprometido hoy" />
        </section>

        {(overview.alerts || []).length > 0 ? (
          <section className="mt-6 rounded-3xl border border-orange-200 bg-orange-50 p-5 shadow-panel">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm uppercase tracking-[0.22em] text-orange-700">Alerta supervisor</p>
                <h3 className="mt-2 text-xl font-semibold text-ink">Acuerdos con mas de 10 dias</h3>
              </div>
              <span className="rounded-full bg-orange-100 px-3 py-1 text-xs font-semibold text-orange-700">{overview.alerts.length} alertas</span>
            </div>
            <div className="mt-4 grid gap-3">
              {overview.alerts.map((alert) => (
                <div key={alert.promise_id} className="rounded-2xl border border-orange-200 bg-white p-4 text-sm text-slate-700">
                  <p className="font-semibold text-ink">{alert.client_name}</p>
                  <p className="mt-1">{alert.account_number} · Gestor: {alert.collector_name}</p>
                  <p className="mt-1">Compromiso para {new Date(alert.scheduled_date).toLocaleDateString("es-SV")} · {alert.days_out} dias</p>
                  <p className="mt-1">Estado: <span className="font-semibold text-ink">{alert.status}</span></p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <DataTable
            title="Gestores asignados y metricas"
            rows={overview.collectors || []}
            emptyText="No hay gestores asignados a este supervisor."
            columns={[
              { key: "user", label: "Gestor", render: (_, row) => row.user?.nombre || "N/D" },
              { key: "assigned_clients", label: "Cartera" },
              { key: "managed_today", label: "Gestiones hoy" },
              { key: "payment_agreements_today", label: "Acuerdos" },
              { key: "recovered_balance_today", label: "Balance salvado", render: (value) => currency(value) }
            ]}
          />

          <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
            <h3 className="text-xl font-semibold text-ink">Lectura del equipo</h3>
            <button
              onClick={() => {
                setReviewIndex(0);
                setReviewPage(1);
                setShowReviewQueue((current) => !current);
              }}
              className="mt-4 rounded-2xl bg-ink px-4 py-3 text-sm font-semibold text-white"
            >
              {showReviewQueue ? "Ocultar revision supervisor" : "Iniciar revision supervisor"}
            </button>
            <div className="mt-4 space-y-4">
              {(overview.collectors || []).map((collector) => (
                <div key={collector.user.id} className="rounded-3xl border border-slate-200 bg-white p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-semibold text-ink">{collector.user.nombre}</p>
                      <p className="mt-1 text-sm text-slate-500">{collector.user.username} · {collector.user.rol}</p>
                    </div>
                    <span className="rounded-full bg-mint px-3 py-1 text-xs font-semibold text-ink">{collector.assigned_clients} clientes</span>
                  </div>
                  <div className="mt-4 grid gap-3 text-sm text-slate-700 md:grid-cols-3">
                    <p>Gestiones: <span className="font-semibold text-ink">{collector.managed_today}</span></p>
                    <p>Acuerdos: <span className="font-semibold text-ink">{collector.payment_agreements_today}</span></p>
                    <p>Balance: <span className="font-semibold text-ink">{currency(collector.recovered_balance_today)}</span></p>
                  </div>
                </div>
              ))}
            </div>
            {showReviewQueue ? (
              <div className="mt-6 rounded-3xl border border-slate-200 bg-white p-5">
                <div className="mb-4 flex items-center justify-between">
                  <h4 className="text-lg font-semibold text-ink">Revision supervisor activa</h4>
                  <span className="rounded-full bg-orange-100 px-3 py-1 text-xs font-semibold text-orange-700">{overview.review_queue?.length || 0} casos</span>
                </div>
                {(overview.review_queue || []).length === 0 ? (
                  <p className="text-sm text-slate-500">No hay clientes pendientes de revision supervisor.</p>
                ) : (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                    <p>La lista detallada se muestra solo en modo enfocado, un cliente a la vez.</p>
                    <p className="mt-1">Desde aquí solo se mantiene el acceso al botón para entrar a revisión sin cargar la cola completa abajo.</p>
                  </div>
                )}
              </div>
            ) : null}
          </section>
        </section>

        <section className="mt-6 glass rounded-3xl border border-white/60 p-6 shadow-panel">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-ink">Clientes del sistema</h3>
              <p className="mt-2 text-sm text-slate-600">El supervisor puede buscar cualquier cliente del sistema sin depender solo de la cartera del collector.</p>
            </div>
            <div className="flex w-full max-w-xl gap-3">
              <input
                value={systemSearch}
                onChange={(event) => setSystemSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") onSearchSystemClients(systemSearch);
                }}
                className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3"
                placeholder="Buscar por nombre, código o DUI"
              />
              <button
                type="button"
                onClick={() => onSearchSystemClients(systemSearch)}
                className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white"
              >
                Buscar
              </button>
            </div>
          </div>
          <div className="mt-4">
            <DataTable
              title="Resultado de búsqueda global"
              rows={(systemClients || []).slice(0, 80)}
              emptyText="Escribe un criterio y busca clientes del sistema."
              columns={[
                { key: "identity_code", label: "Numero Unico" },
                { key: "nombres", label: "Nombres" },
                { key: "apellidos", label: "Apellidos" },
                { key: "dui", label: "DUI" },
                { key: "segmento", label: "Segmento" },
                { key: "telefono", label: "Telefono" },
              ]}
              compact
            />
          </div>
        </section>
      </div>
    </div>
  );
}

function AdminWorkspace({ auth, overview, clients, proposal, importProposal, userImportProposal, generatedReport, dailySimulationSummary, dailySimulationPreview, recoveryVintage, recoveryVintageLoading, recoveryVintageCompare, executiveLog, collectorPreviewPortfolio, collectorPreviewId, collectorPreviewLoading, worklistGroupCatalog, selectedUserGroups, selectedUserGroupsUserId, supervisorAssignments, onOpenCollectorPreview, onLoadUserGroups, onAssignGroupToUser, onUnassignGroupFromUser, onAssignCollectorToSupervisor, onUnassignCollectorFromSupervisor, onLoadRecoveryVintage, onLoadRecoveryVintageCompare, onLoadExecutiveLog, onDownloadRecoveryVintage, onDownloadRecoveryExecutiveDashboard, onRunSqlQuery, onAdminAssistantMessage, onPreviewOmnichannel, onLogout, onCreateStrategy, onAssignWorklist, onAnalyzeDocument, onApplyProposal, onAdjustProposal, onDiscardProposal, onDownloadTemplate, onAnalyzeImport, onApplyImport, onDiscardImport, onDownloadImportTemplate, onAnalyzeUserImport, onApplyUserImport, onDiscardUserImport, onDownloadUserImportTemplate, onGenerateReport, onDownloadGeneratedReport, onRunDailySimulation, onPreviewDailySimulation, onSaveOmnichannelConfig, onSendWhatsAppDemo, saving, error, success }) {
  const [strategyForm, setStrategyForm] = useState({ codigo: "", nombre: "", descripcion: "", categoria: "COBRANZA", orden: 0 });
  const [assignForm, setAssignForm] = useState({ user_id: "", strategy_code: "", client_ids: "" });
  const [documentFile, setDocumentFile] = useState(null);
  const [importFile, setImportFile] = useState(null);
  const [userImportFile, setUserImportFile] = useState(null);
  const [documentNotes, setDocumentNotes] = useState("");
  const [reportPrompt, setReportPrompt] = useState("");
  const [simulationForm, setSimulationForm] = useState({ fmora1_clients: 250, preventivo_clients: 120, recovery_clients: 1000 });
  const [proposalDraft, setProposalDraft] = useState(null);
  const [reportMessage, setReportMessage] = useState("");
  const [omnichannelDraft, setOmnichannelDraft] = useState(null);
  const [whatsAppDemoForm, setWhatsAppDemoForm] = useState({ to_phone: "", client_id: "", strategy_code: "FMORA1", custom_message: "" });
  const [emailDemoForm, setEmailDemoForm] = useState({ to_email: "", client_id: "", strategy_code: "FMORA1", use_smtp: false });
  const [smsDemoForm, setSmsDemoForm] = useState({ to_phone: "", client_id: "", strategy_code: "FMORA1", provider: "textbelt" });
  const [callbotDemoForm, setCallbotDemoForm] = useState({ to_phone: "", client_id: "", strategy_code: "FMORA1" });
  const [channelDemoResult, setChannelDemoResult] = useState(null);
  const [channelSending, setChannelSending] = useState("");
  const [selectedPreviewCollectorId, setSelectedPreviewCollectorId] = useState("");
  const [selectedManagedCollectorId, setSelectedManagedCollectorId] = useState("");
  const [selectedCatalogGroupKey, setSelectedCatalogGroupKey] = useState("");
  const [selectedSupervisorId, setSelectedSupervisorId] = useState("");
  const [selectedSupervisorCollectorId, setSelectedSupervisorCollectorId] = useState("");
  const [recoveryVintageYear, setRecoveryVintageYear] = useState(String(recoveryVintage?.year || new Date().getFullYear() - 1));
  const [recoveryCompareYears, setRecoveryCompareYears] = useState(`${new Date().getFullYear() - 1}, ${new Date().getFullYear() - 2}`);
  const [recoveryVintagePage, setRecoveryVintagePage] = useState(1);
  const [recoveryVintagePageSize, setRecoveryVintagePageSize] = useState(10);
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantMessages, setAssistantMessages] = useState([]);
  const [assistantPendingPrompt, setAssistantPendingPrompt] = useState("");
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [adminSection, setAdminSection] = useState("assistant");
  const [sqlQueryText, setSqlQueryText] = useState("select current_database() as base, current_user as usuario");
  const [sqlQueryMaxRows, setSqlQueryMaxRows] = useState(200);
  const [sqlQueryResult, setSqlQueryResult] = useState(null);
  const [sqlQueryLoading, setSqlQueryLoading] = useState(false);
  const [simulationPreviewLoading, setSimulationPreviewLoading] = useState(false);
  const [recoveryCompareLoading, setRecoveryCompareLoading] = useState(false);
  const [executiveLogLoading, setExecutiveLogLoading] = useState(false);
  const [omnichannelPreview, setOmnichannelPreview] = useState(null);
  const [omnichannelPreviewLoading, setOmnichannelPreviewLoading] = useState(false);
  const previewCollectors = useMemo(
    () => (overview?.collectors || []).map((collector) => collector.user || collector).filter((collector) => collector?.id),
    [overview]
  );
  const availableSupervisors = useMemo(
    () => {
      const fromOverview = overview?.supervisors || [];
      if (fromOverview.length) return fromOverview;
      return (supervisorAssignments || []).map((item) => item.supervisor).filter((supervisor) => supervisor?.id);
    },
    [overview, supervisorAssignments]
  );

  useEffect(() => {
    setProposalDraft(proposal ? JSON.parse(JSON.stringify(proposal)) : null);
  }, [proposal]);

  useEffect(() => {
    if (!overview?.omnichannel) {
      setOmnichannelDraft(null);
      return;
    }
    setOmnichannelDraft({
      ...(overview.omnichannel.controls || {}),
      notes: overview.omnichannel.notes || "",
    });
    setWhatsAppDemoForm((current) => ({
      ...current,
      to_phone: current.to_phone || overview.omnichannel.controls?.twilio_demo_phone || "",
      strategy_code: current.strategy_code || "FMORA1",
    }));
  }, [overview]);

  useEffect(() => {
    if (!previewCollectors.length) {
      setSelectedPreviewCollectorId("");
      return;
    }
    if (collectorPreviewId) {
      setSelectedPreviewCollectorId(String(collectorPreviewId));
      return;
    }
    setSelectedPreviewCollectorId(String(previewCollectors[0].id));
  }, [previewCollectors, collectorPreviewId]);

  useEffect(() => {
    if (!previewCollectors.length) {
      setSelectedManagedCollectorId("");
      return;
    }
    setSelectedManagedCollectorId((current) => current || String(previewCollectors[0].id));
  }, [previewCollectors]);

  useEffect(() => {
    if (!selectedManagedCollectorId) return;
    if (selectedUserGroupsUserId === Number(selectedManagedCollectorId)) return;
    onLoadUserGroups(Number(selectedManagedCollectorId));
  }, [selectedManagedCollectorId, selectedUserGroupsUserId]);

  useEffect(() => {
    if (!availableSupervisors.length) {
      setSelectedSupervisorId("");
      return;
    }
    setSelectedSupervisorId((current) => current || String(availableSupervisors[0].id));
  }, [availableSupervisors]);

  useEffect(() => {
    if (recoveryVintage?.year) {
      setRecoveryVintageYear(String(recoveryVintage.year));
    }
  }, [recoveryVintage]);

  useEffect(() => {
    if (!auth?.token || executiveLog?.length) return;
    void refreshExecutiveLog();
  }, [auth?.token]);

  useEffect(() => {
    if (!executiveLog?.length) return;
    setExecutiveLogLoading(false);
  }, [executiveLog]);

  useEffect(() => {
    setRecoveryVintagePage(1);
  }, [recoveryVintage?.year, recoveryVintage?.sample_clients?.length]);

  const recoveryVintageClients = recoveryVintage?.sample_clients || [];
  const recoveryVintageTotalPages = Math.max(1, Math.ceil(recoveryVintageClients.length / recoveryVintagePageSize));
  const recoveryVintageSafePage = Math.min(recoveryVintagePage, recoveryVintageTotalPages);
  const recoveryVintageStartIndex = (recoveryVintageSafePage - 1) * recoveryVintagePageSize;
  const recoveryVintageVisibleClients = recoveryVintageClients.slice(recoveryVintageStartIndex, recoveryVintageStartIndex + recoveryVintagePageSize);
  const recoveryPlacementChartData = useMemo(() => {
    const placements = recoveryVintage?.placements || [];
    const maxRecovered = Math.max(...placements.map((item) => Number(item.total_paid_120d || 0)), 1);
    return placements.map((item) => ({
      ...item,
      recoveredAmount: Number(item.total_paid_120d || 0),
      paymentRate: item.client_count ? (Number(item.paying_clients_120d || 0) / Number(item.client_count || 1)) * 100 : 0,
      recoveredWidth: `${Math.max(8, (Number(item.total_paid_120d || 0) / maxRecovered) * 100)}%`,
    }));
  }, [recoveryVintage]);
  const recoveryCompareChartData = useMemo(() => {
    const items = recoveryVintageCompare?.items || [];
    const maxPayers = Math.max(...items.map((item) => Number(item.active_payers_120d || 0)), 1);
    return items.map((item) => ({
      ...item,
      payerWidth: `${Math.max(8, (Number(item.active_payers_120d || 0) / maxPayers) * 100)}%`,
      paymentRate: item.total_clients ? (Number(item.active_payers_120d || 0) / Number(item.total_clients || 1)) * 100 : 0,
    }));
  }, [recoveryVintageCompare]);
  const recoveryPlacementLeader = recoveryPlacementChartData.length
    ? [...recoveryPlacementChartData].sort((left, right) => right.recoveredAmount - left.recoveredAmount)[0]
    : null;
  const recoveryPlacementLaggard = recoveryPlacementChartData.length
    ? [...recoveryPlacementChartData].sort((left, right) => left.recoveredAmount - right.recoveredAmount)[0]
    : null;
  const recoveryBestVintage = recoveryCompareChartData.length
    ? [...recoveryCompareChartData].sort((left, right) => right.paymentRate - left.paymentRate)[0]
    : null;
  const recoveryTotalRecovered = recoveryPlacementChartData.reduce((sum, item) => sum + Number(item.recoveredAmount || 0), 0);
  const recoveryTotalBalance = Number(recoveryVintage?.total_balance || 0);
  const recoveryTotalDue = Number(recoveryVintage?.total_due || 0);
  const recoveryPlacementVisualData = useMemo(() => {
    const items = recoveryPlacementChartData || [];
    const maxRecovered = Math.max(...items.map((item) => Number(item.recoveredAmount || 0)), 1);
    const maxBalance = Math.max(...items.map((item) => Number(item.total_balance || 0)), 1);
    return items.map((item) => ({
      ...item,
      recoveredHeight: Math.max(12, (Number(item.recoveredAmount || 0) / maxRecovered) * 190),
      balanceHeight: Math.max(12, (Number(item.total_balance || 0) / maxBalance) * 190),
      dueShare: Number(item.total_balance || 0) > 0 ? (Number(item.total_due || 0) / Number(item.total_balance || 1)) * 100 : 0,
    }));
  }, [recoveryPlacementChartData]);
  const recoveryCompareVisualData = useMemo(() => {
    const items = recoveryCompareChartData || [];
    if (!items.length) return { points: "", areaPoints: "", maxRate: 1, enriched: [] };
    const maxRate = Math.max(...items.map((item) => Number(item.paymentRate || 0)), 1);
    const width = 620;
    const height = 220;
    const step = items.length > 1 ? width / (items.length - 1) : width;
    const enriched = items.map((item, index) => {
      const x = items.length > 1 ? index * step : width / 2;
      const y = height - (Number(item.paymentRate || 0) / maxRate) * 180 - 12;
      return { ...item, x, y };
    });
    const points = enriched.map((item) => `${item.x},${item.y}`).join(" ");
    const areaPoints = `0,${height} ${points} ${width},${height}`;
    return { points, areaPoints, maxRate, enriched };
  }, [recoveryCompareChartData]);

  const submitAssistantPrompt = async (prompt, applyChange = false) => {
    if (!prompt?.trim()) return;
    setAssistantLoading(true);
    if (!applyChange) {
      setAssistantMessages((current) => [...current, { role: "user", text: prompt.trim() }]);
    }
    try {
      const response = await onAdminAssistantMessage(prompt.trim(), applyChange);
      if (response.action_code === "recovery_vintage") setAdminSection("recovery_vintage");
      else if (response.action_code === "show_user_groups" || response.action_code === "assign_group" || response.action_code === "unassign_group" || response.action_code === "assign_supervisor" || response.action_code === "unassign_supervisor") setAdminSection("assignments");
      else if (response.action_code === "toggle_channel") setAdminSection("omnichannel");
      else if (response.action_code === "daily_simulation") setAdminSection("daily_simulation");
      else setAdminSection("assistant");
      setAssistantMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.response_message,
          meta: response,
        },
      ]);
      if (response.requires_confirmation && response.can_apply) {
        setAssistantPendingPrompt(prompt.trim());
      } else if (response.executed) {
        setAssistantPendingPrompt("");
      }
      if (!applyChange) setAssistantPrompt("");
    } finally {
      setAssistantLoading(false);
    }
  };

  const executeSqlQuery = async () => {
    if (!sqlQueryText.trim()) return;
    setSqlQueryLoading(true);
    try {
      const result = await onRunSqlQuery({ query: sqlQueryText, max_rows: Number(sqlQueryMaxRows || 200) });
      setSqlQueryResult(result);
    } finally {
      setSqlQueryLoading(false);
    }
  };

  const runRecoveryCompare = async () => {
    if (!recoveryCompareYears.trim()) return;
    setRecoveryCompareLoading(true);
    try {
      await onLoadRecoveryVintageCompare(recoveryCompareYears);
    } finally {
      setRecoveryCompareLoading(false);
    }
  };

  const refreshExecutiveLog = async () => {
    setExecutiveLogLoading(true);
    try {
      await onLoadExecutiveLog();
    } finally {
      setExecutiveLogLoading(false);
    }
  };

  const sendChannelDemo = async (channelName, url, payload, successMessageBuilder) => {
    setChannelSending(channelName);
    setChannelDemoResult({ ch: channelName, ok: true, msg: `Procesando ${channelName}...` });
    try {
      const response = await fetch(`${API_URL}${url}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.token}`,
        },
        body: JSON.stringify(payload),
      });
      const isJson = response.headers.get("content-type")?.includes("application/json");
      const data = isJson ? await response.json() : await response.text();
      setChannelDemoResult({
        ch: channelName,
        ok: response.ok,
        msg: response.ok ? successMessageBuilder(data) : formatChannelErrorMessage(data),
      });
    } catch (e) {
      setChannelDemoResult({
        ch: channelName,
        ok: false,
        msg: formatChannelErrorMessage(e?.message || e),
      });
    } finally {
      setChannelSending("");
    }
  };

  const groupCatalogOptions = useMemo(
    () => (worklistGroupCatalog || []).map((group) => ({
      ...group,
      key: `${group.strategy_code || ""}|${group.placement_code || ""}|${group.group_id || ""}`,
    })),
    [worklistGroupCatalog]
  );
  const selectedSupervisorAssignment = useMemo(
    () => (supervisorAssignments || []).find((item) => String(item.supervisor.id) === String(selectedSupervisorId)) || null,
    [supervisorAssignments, selectedSupervisorId]
  );
  const alreadyAssignedCollectorIds = new Set((selectedSupervisorAssignment?.collectors || []).map((collector) => collector.id));
  const availableCollectorsForSupervisor = previewCollectors.filter((collector) => !alreadyAssignedCollectorIds.has(collector.id));
  const adminAlerts = useMemo(() => {
    const alerts = [...(overview?.alerts || [])];
    if ((overview?.hmr_clients || 0) > 0) {
      alerts.push({
        severity: "info",
        title: "Oportunidades HMR activas",
        detail: `${overview.hmr_clients} clientes requieren herramientas de mitigación o solución.`,
        module: "summary",
      });
    }
    if ((overview?.omnichannel?.channels || []).some((channel) => !channel.enabled)) {
      const pending = overview.omnichannel.channels.filter((channel) => !channel.enabled).map((channel) => channel.name).join(", ");
      alerts.push({
        severity: "info",
        title: "Canales pendientes de activación",
        detail: `Aún faltan por activar: ${pending}.`,
        module: "omnichannel",
      });
    }
    return alerts;
  }, [overview]);
  const adminMenuItems = [
    { key: "assistant", label: "Agente Admin", hint: "Pedidos en lenguaje natural" },
    { key: "summary", label: "Resumen", hint: "KPIs generales" },
    { key: "recovery_vintage", label: "Cosechas Recovery", hint: "Añadas y placements" },
    { key: "collector_preview", label: "Vista gestor", hint: "Experiencia del collector" },
    { key: "omnichannel", label: "Centro omnicanal", hint: "Canales y demos" },
    { key: "daily_simulation", label: "Simulación diaria", hint: "Envejecimiento y pagos" },
    { key: "documents", label: "Documentos", hint: "PDFs y propuestas" },
    { key: "user_import", label: "Usuarios", hint: "Carga y validación" },
    { key: "reports", label: "Reportes", hint: "Vista gerencial" },
    { key: "client_import", label: "Cartera", hint: "Carga de clientes" },
    { key: "strategies", label: "Estrategias", hint: "Crear y asignar" },
    { key: "assignments", label: "Asignaciones", hint: "Grupos y supervisores" },
    { key: "sql_query", label: "Consultas SQL", hint: "Extracción segura de datos" },
  ];
  const assistantQuickPrompts = [
    "Ver cosecha recovery 2025",
    "Que grupos tiene collector1",
    "Asigna cartera V13A082 al usuario collector1",
    "Explicame como activar email",
    "Simula fmora1 300 preventivo 120 recovery 800",
  ];
  const runSimulationPreview = async () => {
    setSimulationPreviewLoading(true);
    try {
      await onPreviewDailySimulation(simulationForm);
    } finally {
      setSimulationPreviewLoading(false);
    }
  };

  const savedPlaybooks = [
    { title: "Campaña cosecha 2024", detail: "Clientes Recovery con bajo pago reciente y placements V13+.", action: () => { setAdminSection("recovery_vintage"); setRecoveryVintageYear("2024"); } },
    { title: "Reactivación V11", detail: "Clientes con pago >= USD 10 en 120 días y opción de regreso a placement inicial.", action: () => { setAdminSection("recovery_vintage"); setRecoveryCompareYears(`${new Date().getFullYear() - 1}, ${new Date().getFullYear() - 2}`); } },
    { title: "Canales caídos", detail: "Revisar readiness omnicanal y previsualizar mensajes antes de activar campañas.", action: () => setAdminSection("omnichannel") },
  ];

  const previewChannelMessage = async (channel, payload) => {
    setOmnichannelPreviewLoading(true);
    try {
      const preview = await onPreviewOmnichannel({ channel, ...payload });
      setOmnichannelPreview(preview);
    } finally {
      setOmnichannelPreviewLoading(false);
    }
  };
  const showAdminSection = (...sectionKeys) => sectionKeys.includes(adminSection);

  return (
    <div className="min-h-screen px-4 py-5 md:px-6 2xl:px-8">
      <div className="mx-auto max-w-[1760px]">
        <header className="rounded-2xl bg-brand-gradient px-6 py-5 shadow-card-lg md:flex md:items-center md:justify-between relative overflow-hidden">
          <div className="absolute inset-0 opacity-10" style={{background:"radial-gradient(circle at 80% 50%, rgba(0,180,166,0.6) 0%, transparent 60%)"}} />
          <div className="relative flex items-center gap-4">
            <BrandLogo size="headerLg" className="flex-shrink-0" />
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-teal">
                <span className="h-1.5 w-1.5 rounded-full bg-teal pulse-dot" />
                {auth.user.rol}
              </span>
              <h1 className="mt-1.5 text-2xl font-bold text-white">Consola administrativa</h1>
              <p className="mt-0.5 text-sm text-slate-300">Estrategias · Asignaciones · Usuarios · Omnicanalidad</p>
            </div>
          </div>
          <div className="relative mt-4 flex items-center gap-3 md:mt-0">
            <div className="rounded-xl border border-white/10 bg-white/8 px-4 py-2.5 text-right">
              <p className="text-xs text-slate-400">Sesión activa</p>
              <p className="text-sm font-bold text-white">{auth.user.nombre}</p>
            </div>
            <button
              type="button"
              onClick={() => selectedPreviewCollectorId && onOpenCollectorPreview(Number(selectedPreviewCollectorId))}
              disabled={!selectedPreviewCollectorId || collectorPreviewLoading}
              className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20 disabled:opacity-60"
            >
              {collectorPreviewLoading ? "Abriendo..." : "Ver estrategias"}
            </button>
            <button onClick={onLogout} className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20">
              Cerrar sesión
            </button>
          </div>
        </header>

        {error ? <p className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">{error}</p> : null}
        {success ? <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

        <div className="mt-6 grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)] 2xl:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="glass h-fit rounded-3xl border border-white/60 p-4 shadow-panel xl:sticky xl:top-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Menu administrativo</p>
            <div className="mt-4 space-y-2">
              {adminMenuItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setAdminSection(item.key)}
                  className={`w-full rounded-2xl border px-4 py-3 text-left transition-all ${
                    adminSection === item.key
                      ? "border-ocean/30 bg-cyan-50 shadow-sm"
                      : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <p className={`text-sm font-semibold ${adminSection === item.key ? "text-ocean" : "text-ink"}`}>{item.label}</p>
                  <p className="mt-1 text-xs text-slate-500">{item.hint}</p>
                </button>
              ))}
            </div>
          </aside>

          <div className="min-w-0">
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          <span className="font-semibold text-ink">Módulo activo:</span> {adminMenuItems.find((item) => item.key === adminSection)?.label || "Agente Admin"}
        </div>
        <section className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("assistant") ? "" : "hidden"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-ink">Agente Admin</h3>
              <p className="mt-2 text-sm text-slate-600">Pídele cambios operativos en lenguaje natural. El agente ahora también puede explicarte el paso a paso antes de proponer o aplicar el cambio.</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
              Ejemplos: `ver cosecha recovery 2025`, `asigna cartera V13A082 al usuario collector1`, `explicame como activar email`, `simula fmora1 300 preventivo 120 recovery 800`
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {assistantQuickPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => setAssistantPrompt(prompt)}
                className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:border-slate-300 hover:bg-slate-50"
              >
                {prompt}
              </button>
            ))}
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                submitAssistantPrompt(assistantPrompt, false);
              }}
              className="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <textarea
                value={assistantPrompt}
                onChange={(event) => setAssistantPrompt(event.target.value)}
                rows={4}
                placeholder="Escribe lo que quieres hacer en el sistema..."
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button type="submit" disabled={assistantLoading || !assistantPrompt.trim()} className="rounded-2xl bg-ink px-5 py-3 font-semibold text-white disabled:opacity-70">
                  {assistantLoading ? "Analizando..." : "Analizar solicitud"}
                </button>
                {assistantPendingPrompt ? (
                  <button type="button" onClick={() => submitAssistantPrompt(assistantPendingPrompt, true)} disabled={assistantLoading} className="rounded-2xl bg-teal px-5 py-3 font-semibold text-white disabled:opacity-70">
                    Confirmar y aplicar
                  </button>
                ) : null}
              </div>
            </form>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Conversación</p>
              <div className="mt-3 max-h-72 space-y-3 overflow-y-auto pr-1">
                {assistantMessages.length ? (
                  assistantMessages.map((item, index) => (
                    <div key={`assistant-message-${index}`} className={`rounded-2xl px-4 py-3 text-sm ${item.role === "user" ? "bg-slate-100 text-slate-700" : "bg-cyan-50 text-ink"}`}>
                      <p className="font-semibold">{item.role === "user" ? "Admin" : "Agente"}</p>
                      <p className="mt-1">{item.text}</p>
                      {item.meta?.data?.groups?.length ? (
                        <p className="mt-2 text-xs text-slate-500">Grupos encontrados: {item.meta.data.groups.map((group) => group.display_name || group.group_id).join(" · ")}</p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="rounded-2xl bg-slate-50 px-4 py-4 text-sm text-slate-500">Aquí aparecerán las propuestas y resultados del agente administrativo.</p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className={`mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-4 ${showAdminSection("summary") ? "" : "hidden"}`}>
          <StatCard title="Clientes totales" value={overview?.total_clients || 0} detail="Base completa disponible" />
          <StatCard title="Clientes asignados" value={overview?.assigned_clients || 0} detail={`${overview?.unassigned_clients || 0} pendientes de asignar`} />
          <StatCard title="Clientes HMR" value={overview?.hmr_clients || 0} detail="Elegibles para mitigacion" />
          <StatCard title="Estrategias activas" value={overview?.strategies?.length || 0} detail="Alineadas al manual de cobranza" />
        </section>

        <section className={`mt-6 glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("summary") ? "" : "hidden"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-ink">Centro de alertas</h3>
              <p className="mt-2 text-sm text-slate-600">Señales rápidas para priorizar decisiones sin recorrer todo el panel.</p>
            </div>
            <span className="rounded-full bg-slate-100 px-4 py-2 text-xs font-semibold text-slate-700">
              {adminAlerts.length} alertas visibles
            </span>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {adminAlerts.length ? adminAlerts.map((alert, index) => (
              <button
                key={`admin-alert-${index}`}
                type="button"
                onClick={() => alert.module ? setAdminSection(alert.module) : null}
                className={`rounded-2xl border p-4 text-left transition-all ${
                  alert.severity === "warning"
                    ? "border-amber-200 bg-amber-50 hover:bg-amber-100"
                    : "border-cyan-200 bg-cyan-50 hover:bg-cyan-100"
                }`}
              >
                <p className="text-sm font-semibold text-ink">{alert.title}</p>
                <p className="mt-2 text-sm text-slate-700">{alert.detail}</p>
                {alert.module ? <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Ir a {adminMenuItems.find((item) => item.key === alert.module)?.label || "módulo"}</p> : null}
              </button>
            )) : (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
                No hay alertas críticas en este momento. La operación luce estable.
              </div>
            )}
          </div>
        </section>

        <section className={`mt-6 grid gap-4 xl:grid-cols-[0.95fr_1.05fr] ${showAdminSection("summary") ? "" : "hidden"}`}>
          <div className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Playbooks operativos</h3>
                <p className="mt-2 text-sm text-slate-600">Accesos rápidos a campañas o lecturas operativas recurrentes.</p>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {savedPlaybooks.map((playbook) => (
                <button key={playbook.title} type="button" onClick={playbook.action} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-4 text-left hover:border-slate-300 hover:bg-slate-50">
                  <p className="font-semibold text-ink">{playbook.title}</p>
                  <p className="mt-1 text-sm text-slate-600">{playbook.detail}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Bitácora ejecutiva</h3>
                <p className="mt-2 text-sm text-slate-600">Quién cambió qué, cuándo lo hizo y sobre qué módulo impactó.</p>
              </div>
              <button type="button" onClick={refreshExecutiveLog} disabled={executiveLogLoading} className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-ink disabled:opacity-60">
                {executiveLogLoading ? "Actualizando..." : "Actualizar"}
              </button>
            </div>
            <div className="mt-4 max-h-[420px] space-y-3 overflow-y-auto pr-1">
              {(executiveLog || []).length ? executiveLog.map((event) => (
                <div key={`executive-log-${event.id}`} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-ink">{String(event.accion || "").replaceAll("_", " ")}</p>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{event.created_at ? new Date(event.created_at).toLocaleString("es-SV") : "Sin fecha"}</span>
                  </div>
                  <p className="mt-2 text-sm text-slate-700">{event.descripcion || "Sin descripción registrada."}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">{event.usuario_nombre || "Sistema"} · {event.entidad}</p>
                </div>
              )) : (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">No hay eventos relevantes todavía.</div>
              )}
            </div>
          </div>
        </section>

        <section className={`mt-6 overflow-hidden rounded-[34px] border border-cyan-900/60 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.18),_transparent_25%),radial-gradient(circle_at_top_right,_rgba(59,130,246,0.12),_transparent_18%),linear-gradient(180deg,_#081321_0%,_#0b1828_36%,_#0d1f31_100%)] p-6 shadow-[0_32px_90px_rgba(2,8,23,0.45)] ${showAdminSection("recovery_vintage") ? "" : "hidden"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300/80">Executive Vintage Dashboard</p>
              <h3 className="mt-3 text-3xl font-semibold text-white">Cosecha Recovery añejada</h3>
              <p className="mt-2 max-w-3xl text-sm text-slate-300">Analiza la cartera que se separó en un año específico y mira cómo hoy está distribuida entre `V11`, `V12`, `V13`, `V16` y `V18`, incluyendo clientes con pagos de al menos USD 10 en los últimos 120 días.</p>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                onLoadRecoveryVintage(Number(recoveryVintageYear || new Date().getFullYear() - 1));
              }}
              className="flex flex-wrap items-center gap-3"
            >
              <input
                type="number"
                min="2000"
                max="2100"
                value={recoveryVintageYear}
                onChange={(event) => setRecoveryVintageYear(event.target.value)}
                className="w-32 rounded-2xl border border-cyan-400/20 bg-slate-950/60 px-4 py-3 text-white shadow-inner shadow-cyan-950/30 outline-none placeholder:text-slate-500"
                placeholder="2000"
              />
              <button
                type="submit"
                disabled={recoveryVintageLoading || !recoveryVintageYear}
                className="rounded-2xl bg-gradient-to-r from-cyan-500 to-sky-500 px-5 py-3 font-semibold text-slate-950 shadow-[0_12px_35px_rgba(14,165,233,0.35)] disabled:opacity-70"
              >
                {recoveryVintageLoading ? "Cargando..." : "Ver cosecha"}
              </button>
              <button
                type="button"
                disabled={!recoveryVintageYear || recoveryVintageLoading}
                onClick={() => onDownloadRecoveryVintage(Number(recoveryVintageYear || new Date().getFullYear() - 1))}
                className="rounded-2xl border border-slate-700 bg-slate-950/60 px-5 py-3 font-semibold text-slate-100 disabled:opacity-70"
              >
                Descargar Excel
              </button>
              <button
                type="button"
                disabled={!recoveryVintageYear || recoveryVintageLoading}
                onClick={() => onDownloadRecoveryExecutiveDashboard(Number(recoveryVintageYear || new Date().getFullYear() - 1), recoveryCompareYears)}
                className="rounded-2xl border border-cyan-400/25 bg-cyan-500/10 px-5 py-3 font-semibold text-cyan-200 disabled:opacity-70"
              >
                Descargar dashboard ejecutivo
              </button>
            </form>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
            <div className="relative overflow-hidden rounded-[28px] bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.28),_transparent_35%),linear-gradient(135deg,_#0b1f3a_0%,_#123b57_45%,_#0e7490_100%)] p-6 text-white shadow-[0_30px_80px_rgba(15,23,42,0.24)]">
              <div className="absolute -right-16 top-0 h-44 w-44 rounded-full bg-white/10 blur-3xl" />
              <div className="relative flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-100/90">Executive Recovery View</p>
                  <h4 className="mt-3 text-3xl font-bold">Cosecha {recoveryVintage?.year || recoveryVintageYear}</h4>
                  <p className="mt-2 max-w-2xl text-sm text-cyan-50/85">
                    Lectura gerencial de recuperación para identificar dónde se está convirtiendo mejor la cosecha y en qué placement se está frenando el flujo.
                  </p>
                </div>
                  <div className="rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-right backdrop-blur-sm">
                    <p className="text-xs uppercase tracking-[0.22em] text-cyan-100/80">Recuperado 120d</p>
                    <p className="mt-2 text-3xl font-bold text-white">{currency(recoveryTotalRecovered)}</p>
                    <p className="mt-2 text-xs text-cyan-100/75">Suma visible por placement</p>
                  </div>
              </div>

              <div className="relative mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {[
                  {
                    title: "Clientes separados",
                    value: recoveryVintage?.total_clients || 0,
                    detail: `Cosecha ${recoveryVintage?.year || recoveryVintageYear}`,
                    tone: "from-cyan-400/20 to-cyan-500/5",
                  },
                  {
                    title: `Con pago USD 10+ / ${recoveryVintage?.lookback_days || 120} días`,
                    value: recoveryVintage?.active_payers_120d || 0,
                    detail: "Elegibles para reactivación",
                    tone: "from-emerald-400/20 to-emerald-500/5",
                  },
                  {
                    title: "Hoy en V11",
                    value: recoveryVintage?.v11_clients || 0,
                    detail: "Placement inicial vigente",
                    tone: "from-amber-400/20 to-amber-500/5",
                  },
                  {
                    title: "Placements activos",
                    value: recoveryVintage?.placements_tracked || 0,
                    detail: "Distribución actual",
                    tone: "from-fuchsia-400/20 to-fuchsia-500/5",
                  },
                  {
                    title: "Saldo total visible",
                    value: currency(recoveryTotalBalance),
                    detail: "Balance que representa la cosecha",
                    tone: "from-sky-400/20 to-sky-500/5",
                  },
                  {
                    title: "Saldo vencido",
                    value: currency(recoveryTotalDue),
                    detail: "Monto vencido hoy en la cosecha",
                    tone: "from-rose-400/20 to-rose-500/5",
                  },
                ].map((card) => (
                  <div key={card.title} className={`rounded-2xl border border-white/12 bg-gradient-to-br ${card.tone} px-4 py-4 backdrop-blur-sm`}>
                    <p className="text-xs uppercase tracking-[0.2em] text-cyan-100/80">{card.title}</p>
                    <p className="mt-3 text-3xl font-bold text-white">{card.value}</p>
                    <p className="mt-2 text-sm text-cyan-50/80">{card.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4">
              <div className="rounded-[26px] border border-emerald-400/20 bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(8,47,73,0.82))] p-5 shadow-[0_20px_55px_rgba(16,185,129,0.12)]">
                <p className="text-xs uppercase tracking-[0.22em] text-emerald-300">Placement líder</p>
                <p className="mt-3 text-3xl font-bold text-white">{recoveryPlacementLeader?.placement_code || "N/D"}</p>
                <p className="mt-2 text-sm text-slate-300">{recoveryPlacementLeader ? `${currency(recoveryPlacementLeader.recoveredAmount)} recuperados` : "Sin datos aún."}</p>
                <p className="mt-1 text-xs text-slate-400">{recoveryPlacementLeader ? `${recoveryPlacementLeader.paymentRate.toFixed(1)}% de clientes con pago reciente · Saldo ${currency(recoveryPlacementLeader.total_balance || 0)}` : ""}</p>
              </div>
              <div className="rounded-[26px] border border-amber-400/20 bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(67,20,7,0.82))] p-5 shadow-[0_20px_55px_rgba(245,158,11,0.12)]">
                <p className="text-xs uppercase tracking-[0.22em] text-amber-300">Placement rezagado</p>
                <p className="mt-3 text-3xl font-bold text-white">{recoveryPlacementLaggard?.placement_code || "N/D"}</p>
                <p className="mt-2 text-sm text-slate-300">{recoveryPlacementLaggard ? `${currency(recoveryPlacementLaggard.recoveredAmount)} recuperados` : "Sin datos aún."}</p>
                <p className="mt-1 text-xs text-slate-400">{recoveryPlacementLaggard ? `${recoveryPlacementLaggard.paymentRate.toFixed(1)}% de clientes con pago reciente · Saldo ${currency(recoveryPlacementLaggard.total_balance || 0)}` : ""}</p>
              </div>
              <div className="rounded-[26px] border border-cyan-400/20 bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(14,116,144,0.78))] p-5 shadow-[0_20px_55px_rgba(34,211,238,0.12)]">
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-300">Mejor añada comparada</p>
                <p className="mt-3 text-3xl font-bold text-white">{recoveryBestVintage ? `Cosecha ${recoveryBestVintage.year}` : "N/D"}</p>
                <p className="mt-2 text-sm text-slate-300">{recoveryBestVintage ? `${recoveryBestVintage.paymentRate.toFixed(1)}% de conversión reciente` : "Corre el comparador para verla."}</p>
                <p className="mt-1 text-xs text-slate-400">{recoveryBestVintage ? `${recoveryBestVintage.active_payers_120d} clientes con pago reciente · Saldo ${currency(recoveryBestVintage.total_balance || 0)}` : ""}</p>
              </div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-[28px] border border-cyan-900/60 bg-[linear-gradient(180deg,rgba(10,18,31,0.98),rgba(8,20,34,0.95))] p-5 shadow-[0_24px_70px_rgba(2,8,23,0.4)]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/75">Gráfica de recuperación por placement</p>
                  <p className="mt-1 text-sm text-slate-300">Lectura visual del balance representado, recuperación visible y presión de saldo vencido por placement.</p>
                </div>
                <span className="rounded-full border border-cyan-400/20 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-200">Base: {recoveryVintage?.year || recoveryVintageYear}</span>
              </div>
              <div className="mt-5 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                <div className="rounded-[26px] border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">Saldo y recuperación por placement</p>
                      <p className="mt-1 text-xs text-slate-400">Barras dobles: balance visible vs recuperado.</p>
                    </div>
                    <div className="flex items-center gap-4 text-[11px] text-slate-400">
                      <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-slate-500" /> Balance</span>
                      <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-cyan-400" /> Recuperado</span>
                    </div>
                  </div>
                  {recoveryPlacementVisualData.length ? (
                    <div className="mt-6">
                      <div className="flex h-[260px] items-end gap-4 overflow-x-auto rounded-[22px] border border-white/5 bg-slate-950/35 px-4 pb-4 pt-6">
                        {recoveryPlacementVisualData.map((item) => (
                          <div key={`placement-visual-${item.placement_code}`} className="flex min-w-[96px] flex-1 flex-col items-center gap-3">
                            <div className="flex h-[200px] items-end gap-2">
                              <div className="flex w-6 items-end rounded-full bg-slate-800/90">
                                <div className="w-full rounded-full bg-gradient-to-t from-slate-500 to-slate-300 shadow-[0_0_18px_rgba(148,163,184,0.16)]" style={{ height: `${item.balanceHeight}px` }} />
                              </div>
                              <div className="flex w-6 items-end rounded-full bg-cyan-950/80">
                                <div className="w-full rounded-full bg-gradient-to-t from-cyan-500 via-sky-400 to-emerald-300 shadow-[0_0_22px_rgba(34,211,238,0.35)]" style={{ height: `${item.recoveredHeight}px` }} />
                              </div>
                            </div>
                            <div className="text-center">
                              <p className="text-sm font-semibold text-white">{item.placement_code}</p>
                              <p className="mt-1 text-[11px] text-slate-400">{currency(item.recoveredAmount)}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mt-6 rounded-2xl border border-dashed border-slate-700 bg-slate-950/50 px-4 py-4 text-sm text-slate-400">
                      No hay placements con recuperación para graficar en la cosecha seleccionada.
                    </div>
                  )}
                </div>
                <div className="space-y-4">
                  {recoveryPlacementVisualData.slice(0, 3).map((item) => (
                    <div key={`placement-insight-${item.placement_code}`} className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.01))] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.22em] text-cyan-300/75">{item.placement_code}</p>
                          <p className="mt-2 text-2xl font-bold text-white">{currency(item.total_balance || 0)}</p>
                          <p className="mt-1 text-xs text-slate-400">Balance visible</p>
                        </div>
                        <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                          {item.paymentRate.toFixed(1)}%
                        </div>
                      </div>
                      <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
                        <div className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-400" style={{ width: `${Math.max(8, Math.min(100, item.dueShare))}%` }} />
                      </div>
                      <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                        <span>Saldo vencido {currency(item.total_due || 0)}</span>
                        <span>{item.client_count} clientes</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-[28px] border border-cyan-900/60 bg-[linear-gradient(180deg,rgba(10,18,31,0.98),rgba(30,13,46,0.95))] p-5 shadow-[0_24px_70px_rgba(2,8,23,0.4)]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-fuchsia-300/75">Comparativo gráfico por añada</p>
                  <p className="mt-1 text-sm text-slate-300">Curva de recuperación reciente y huella de saldo para comparar cosechas con mirada ejecutiva.</p>
                </div>
              </div>
              <div className="mt-5">
                {recoveryCompareVisualData.enriched.length ? (
                  <div className="rounded-[26px] border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-white">Tendencia de conversión por añada</p>
                        <p className="mt-1 text-xs text-slate-400">La línea muestra % de pago reciente y las tarjetas resumen el peso financiero de cada cosecha.</p>
                      </div>
                      <div className="rounded-full border border-fuchsia-400/20 bg-fuchsia-500/10 px-3 py-1 text-xs font-semibold text-fuchsia-200">
                        {recoveryCompareVisualData.enriched.length} cosechas comparadas
                      </div>
                    </div>
                    <div className="mt-5 overflow-hidden rounded-[24px] border border-white/5 bg-slate-950/35 p-4">
                      <svg viewBox="0 0 620 220" className="h-[240px] w-full">
                        <defs>
                          <linearGradient id="recoveryCompareArea" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="#c026d3" stopOpacity="0.38" />
                            <stop offset="100%" stopColor="#0f172a" stopOpacity="0.02" />
                          </linearGradient>
                          <linearGradient id="recoveryCompareStroke" x1="0" x2="1" y1="0" y2="0">
                            <stop offset="0%" stopColor="#22d3ee" />
                            <stop offset="50%" stopColor="#818cf8" />
                            <stop offset="100%" stopColor="#f472b6" />
                          </linearGradient>
                        </defs>
                        {[0, 1, 2, 3].map((tick) => (
                          <line key={`grid-${tick}`} x1="0" x2="620" y1={20 + tick * 48} y2={20 + tick * 48} stroke="rgba(148,163,184,0.14)" strokeWidth="1" />
                        ))}
                        <polygon points={recoveryCompareVisualData.areaPoints} fill="url(#recoveryCompareArea)" />
                        <polyline points={recoveryCompareVisualData.points} fill="none" stroke="url(#recoveryCompareStroke)" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
                        {recoveryCompareVisualData.enriched.map((item) => (
                          <g key={`compare-point-${item.year}`}>
                            <circle cx={item.x} cy={item.y} r="6" fill="#0f172a" stroke="#67e8f9" strokeWidth="3" />
                            <text x={item.x} y="214" textAnchor="middle" fill="#cbd5e1" fontSize="12">{item.year}</text>
                          </g>
                        ))}
                      </svg>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      {recoveryCompareVisualData.enriched.map((item) => (
                        <div key={`compare-card-${item.year}`} className="rounded-2xl border border-white/8 bg-white/5 px-4 py-4">
                          <p className="text-xs uppercase tracking-[0.22em] text-fuchsia-300/75">Cosecha {item.year}</p>
                          <p className="mt-2 text-2xl font-bold text-white">{item.paymentRate.toFixed(1)}%</p>
                          <p className="mt-1 text-xs text-slate-400">{item.active_payers_120d} clientes con pago reciente</p>
                          <div className="mt-3 space-y-1 text-xs text-slate-400">
                            <p>Saldo total {currency(item.total_balance || 0)}</p>
                            <p>Saldo vencido {currency(item.total_due || 0)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/50 px-4 py-4 text-sm text-slate-400">
                    Ejecuta el comparador para visualizar varias cosechas en una sola gráfica.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="mt-5 rounded-[28px] border border-cyan-900/60 bg-[linear-gradient(180deg,rgba(10,18,31,0.96),rgba(11,27,45,0.92))] p-4 shadow-[0_20px_55px_rgba(2,8,23,0.32)]">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/75">Comparador de cosechas</p>
                <p className="mt-1 text-sm text-slate-300">Compara varias añadas al mismo tiempo por volumen, pago reciente y distribución por placement.</p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  value={recoveryCompareYears}
                  onChange={(event) => setRecoveryCompareYears(event.target.value)}
                  className="w-64 rounded-2xl border border-cyan-400/20 bg-slate-950/60 px-4 py-3 text-white"
                  placeholder="2025, 2024, 2023"
                />
                <button type="button" onClick={runRecoveryCompare} disabled={recoveryCompareLoading} className="rounded-2xl border border-cyan-400/25 bg-cyan-500/10 px-4 py-3 font-semibold text-cyan-200 disabled:opacity-70">
                  {recoveryCompareLoading ? "Comparando..." : "Comparar"}
                </button>
              </div>
            </div>
            {(recoveryVintageCompare?.items || []).length ? (
              <div className="mt-4 overflow-x-auto rounded-2xl border border-white/5 bg-slate-950/40">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-slate-400">
                      <th className="px-3 py-2 font-medium">Año</th>
                      <th className="px-3 py-2 font-medium">Clientes</th>
                      <th className="px-3 py-2 font-medium">Pago reciente</th>
                      <th className="px-3 py-2 font-medium">Placements</th>
                      <th className="px-3 py-2 font-medium">Distribución</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recoveryVintageCompare.items.map((item) => (
                      <tr key={`compare-${item.year}`} className="border-b border-white/5 align-top">
                        <td className="px-3 py-3 font-semibold text-white">{item.year}</td>
                        <td className="px-3 py-3 text-slate-300">{item.total_clients}</td>
                        <td className="px-3 py-3 text-slate-300">{item.active_payers_120d}</td>
                        <td className="px-3 py-3 text-slate-300">{item.placements_tracked}</td>
                        <td className="px-3 py-3 text-slate-300">
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(item.placement_distribution || {}).map(([placement, count]) => (
                              <span key={`${item.year}-${placement}`} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                                {placement}: {count}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.18fr)]">
            <div className="min-w-0 rounded-[28px] border border-cyan-900/60 bg-[linear-gradient(180deg,rgba(10,18,31,0.96),rgba(11,27,45,0.92))] p-4 shadow-[0_20px_55px_rgba(2,8,23,0.32)]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/75">Distribución por placement</p>
                  <p className="mt-1 text-sm text-slate-300">Cómo se ha movido la cosecha seleccionada dentro de Recovery.</p>
                </div>
                <span className="rounded-full border border-cyan-400/20 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-200">Umbral USD {Number(recoveryVintage?.payment_threshold || 10).toFixed(2)}</span>
              </div>
              <div className="mt-4 space-y-3">
                {(recoveryVintage?.placements || []).length ? (
                  recoveryVintage.placements.map((placement) => (
                    <div key={`recovery-vintage-${placement.placement_code}`} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 backdrop-blur-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-lg font-bold text-white">{placement.placement_code}</p>
                          <p className="mt-1 text-sm text-slate-300">{placement.client_count} clientes actualmente en este placement.</p>
                        </div>
                        <span className="rounded-full border border-white/10 bg-slate-950/50 px-3 py-1 text-sm font-semibold text-cyan-200">{currency(placement.total_paid_120d)}</span>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-3">
                        <div className="rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Con pago reciente</p>
                          <p className="mt-1 font-semibold text-white">{placement.paying_clients_120d}</p>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Elegibles V11</p>
                          <p className="mt-1 font-semibold text-white">{placement.v11_eligible_clients}</p>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Pago acumulado</p>
                          <p className="mt-1 font-semibold text-white">{currency(placement.total_paid_120d)}</p>
                        </div>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-3">
                          <p className="text-xs uppercase tracking-[0.18em] text-emerald-300">Agencia/lista con mejor desempeño</p>
                          <p className="mt-1 font-semibold text-white">{placement.best_group_id || "N/D"}</p>
                          <p className="mt-1 text-sm text-slate-300">{Number(placement.best_group_rate_120d || 0).toFixed(1)}% con pago reciente</p>
                        </div>
                        <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-3">
                          <p className="text-xs uppercase tracking-[0.18em] text-amber-300">Agencia/lista rezagada</p>
                          <p className="mt-1 font-semibold text-white">{placement.lagging_group_id || "N/D"}</p>
                          <p className="mt-1 text-sm text-slate-300">{Number(placement.lagging_group_rate_120d || 0).toFixed(1)}% con pago reciente</p>
                        </div>
                      </div>
                      {(placement.agencies || []).length ? (
                        <div className="mt-3 overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
                          <table className="min-w-full text-left text-xs">
                            <thead>
                              <tr className="border-b border-white/10 text-slate-400">
                                <th className="px-3 py-2 font-medium">Agencia / Lista</th>
                                <th className="px-3 py-2 font-medium">Scope</th>
                                <th className="px-3 py-2 font-medium">Clientes</th>
                                <th className="px-3 py-2 font-medium">Con pago</th>
                                <th className="px-3 py-2 font-medium">% pago</th>
                                <th className="px-3 py-2 font-medium">Pago acumulado</th>
                              </tr>
                            </thead>
                            <tbody>
                              {placement.agencies.map((agency) => (
                                <tr key={`${placement.placement_code}-${agency.group_id}`} className="border-b border-white/5 last:border-b-0">
                                  <td className="px-3 py-2 font-semibold text-white">{agency.group_id}</td>
                                  <td className="px-3 py-2 text-slate-300">{agency.channel_scope || "N/D"}</td>
                                  <td className="px-3 py-2 text-slate-300">{agency.client_count}</td>
                                  <td className="px-3 py-2 text-slate-300">{agency.paying_clients_120d}</td>
                                  <td className="px-3 py-2 text-slate-300">{Number(agency.payment_rate_120d || 0).toFixed(1)}%</td>
                                  <td className="px-3 py-2 text-slate-300">{currency(agency.total_paid_120d)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="rounded-2xl bg-slate-950/40 px-4 py-4 text-sm text-slate-400">No hay clientes Recovery con fecha de separación para el año seleccionado.</p>
                )}
              </div>
            </div>

            <div className="min-w-0 rounded-[28px] border border-cyan-900/60 bg-[linear-gradient(180deg,rgba(10,18,31,0.96),rgba(11,27,45,0.92))] p-4 shadow-[0_20px_55px_rgba(2,8,23,0.32)]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/75">Muestra ejecutiva de clientes</p>
                  <p className="mt-1 text-sm text-slate-300">Detalle rápido para explicar movimiento, placement actual y pagos recientes de la cosecha.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400">
                    Mostrando {recoveryVintageClients.length ? recoveryVintageStartIndex + 1 : 0}-{Math.min(recoveryVintageStartIndex + recoveryVintagePageSize, recoveryVintageClients.length)} de {recoveryVintageClients.length}
                  </span>
                  <select
                    value={recoveryVintagePageSize}
                    onChange={(event) => setRecoveryVintagePageSize(Number(event.target.value))}
                    className="rounded-xl border border-cyan-400/20 bg-slate-950/60 px-3 py-2 text-sm text-slate-100"
                  >
                    <option value={10}>10 por hoja</option>
                    <option value={20}>20 por hoja</option>
                  </select>
                </div>
              </div>
              <div className="mt-4 max-w-full overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-slate-400">
                      <th className="px-3 py-2 font-medium">Número Único</th>
                      <th className="px-3 py-2 font-medium">Cliente</th>
                      <th className="px-3 py-2 font-medium">Separación</th>
                      <th className="px-3 py-2 font-medium">Placement actual</th>
                      <th className="px-3 py-2 font-medium">Pago 120d</th>
                      <th className="px-3 py-2 font-medium">Ruta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recoveryVintageVisibleClients.length ? (
                      recoveryVintageVisibleClients.map((client) => (
                        <tr key={`recovery-vintage-client-${client.client_id}`} className="border-b border-white/5 align-top">
                          <td className="px-3 py-3 font-semibold text-white">{client.identity_code}</td>
                          <td className="px-3 py-3 text-slate-300">
                            <p>{client.client_name}</p>
                            <p className="mt-1 text-xs text-slate-400">{client.current_group_id || "Sin cartera"} · {client.current_status || "Sin estado"}</p>
                          </td>
                          <td className="px-3 py-3 text-slate-300">{client.separation_date}</td>
                          <td className="px-3 py-3 text-slate-300">{client.current_placement || "SIN_PLACEMENT"}</td>
                          <td className="px-3 py-3 text-slate-300">
                            <p>{currency(client.total_paid_120d)}</p>
                            <p className="mt-1 text-xs text-slate-400">{client.qualifying_payment_count_120d} pagos calificados</p>
                          </td>
                          <td className="px-3 py-3 text-slate-300">
                            <p>{client.movement_path}</p>
                            <p className="mt-1 text-xs text-slate-400">{client.qualifies_for_v11 ? "Con pago reciente >= umbral" : "Sin pago reciente >= umbral"}</p>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="6" className="px-3 py-6 text-center text-sm text-slate-400">No hay muestra disponible para esta cosecha.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {recoveryVintageClients.length ? (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-xs text-slate-400">Hoja {recoveryVintageSafePage} de {recoveryVintageTotalPages}</p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setRecoveryVintagePage((current) => Math.max(1, current - 1))}
                      disabled={recoveryVintageSafePage <= 1}
                      className="rounded-xl border border-cyan-400/20 bg-slate-950/60 px-3 py-2 text-sm font-semibold text-slate-100 disabled:opacity-50"
                    >
                      Anterior
                    </button>
                    <button
                      type="button"
                      onClick={() => setRecoveryVintagePage((current) => Math.min(recoveryVintageTotalPages, current + 1))}
                      disabled={recoveryVintageSafePage >= recoveryVintageTotalPages}
                      className="rounded-xl border border-cyan-400/20 bg-slate-950/60 px-3 py-2 text-sm font-semibold text-slate-100 disabled:opacity-50"
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <section className={`mt-6 glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("collector_preview") ? "" : "hidden"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-ink">Vista principal del gestor</h3>
              <p className="mt-2 text-sm text-slate-600">Como administrador puedes abrir el panel operativo del collector y revisar exactamente la experiencia principal de gestión.</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-right">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Collector visible</p>
              <p className="mt-1 text-sm font-bold text-ink">{collectorPreviewPortfolio?.collector?.nombre || "Selecciona un collector"}</p>
            </div>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-[1fr_auto]">
            <select
              value={selectedPreviewCollectorId}
              onChange={(event) => setSelectedPreviewCollectorId(event.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3"
            >
              {previewCollectors.map((collector) => (
                <option key={collector.id} value={collector.id}>
                  {collector.nombre} · {collector.username}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => selectedPreviewCollectorId && onOpenCollectorPreview(Number(selectedPreviewCollectorId))}
              disabled={!selectedPreviewCollectorId || collectorPreviewLoading}
              className="rounded-2xl bg-ink px-5 py-3 font-semibold text-white disabled:opacity-70"
            >
              {collectorPreviewLoading ? "Abriendo panel..." : "Abrir panel del gestor"}
            </button>
          </div>
          {collectorPreviewPortfolio ? (
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Asignados hoy</p>
                <p className="mt-2 text-2xl font-bold text-ink">{collectorPreviewPortfolio.metrics?.assigned_today || 0}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Recovery visible</p>
                <p className="mt-2 text-2xl font-bold text-ink">{collectorPreviewPortfolio.metrics?.strategy_summary?.VAGENCIASEXTERNASINTERNO || 0}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Preventivo visible</p>
                <p className="mt-2 text-2xl font-bold text-ink">{collectorPreviewPortfolio.metrics?.strategy_summary?.PREVENTIVO || 0}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Subgrupos Recovery</p>
                <p className="mt-2 text-2xl font-bold text-ink">
                  {new Set((collectorPreviewPortfolio.clients || []).filter((item) => item.estrategia_principal === "VAGENCIASEXTERNASINTERNO").map((item) => `${item.placement_code || "SIN"}-${item.group_id || item.sublista_trabajo || "GENERAL"}`)).size}
                </p>
              </div>
            </div>
          ) : null}
        </section>

        <section className={`mt-6 glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("omnichannel") ? "" : "hidden"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-ink">Centro omnicanal</h3>
              <p className="mt-2 text-sm text-slate-600">Controla la activación progresiva de WhatsApp bot, correo y callbot, y visualiza qué parte de la cartera ya puede entrar en journeys automatizados.</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-right">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Nivel de preparación</p>
              <p className="mt-1 text-2xl font-bold text-ink">{overview?.omnichannel?.readiness_score || 0}%</p>
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {(overview?.omnichannel?.channels || []).map((channel) => (
              <div key={channel.code} className={`rounded-2xl border p-4 transition-all ${channel.enabled ? "border-teal/30 bg-gradient-to-br from-teal/5 to-ocean/3" : "border-slate-200 bg-white"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-bold text-ink">{channel.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{channel.provider}</p>
                  </div>
                  <span className={`flex-shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${channel.enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                    {channel.enabled ? "✓ Activo" : "Pendiente"}
                  </span>
                </div>
                <p className="mt-3 text-2xl font-bold text-ink">{(channel.candidates || 0).toLocaleString()}</p>
                <p className="text-xs text-slate-500">clientes alcanzables</p>
                <p className="mt-2 text-xs text-slate-600 leading-4">{channel.status}</p>
                {channel.free_option && (
                  <div className="mt-3 rounded-lg bg-teal/8 border border-teal/15 px-2.5 py-2">
                    <p className="text-xs font-semibold text-teal">🆓 {channel.free_option}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Journeys sugeridos por estrategia</p>
              <div className="mt-3 space-y-2">
                {(overview?.omnichannel?.journeys || []).map((journey, index) => (
                  <div key={`journey-${index}`} className="rounded-xl bg-slate-50 px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-ink">{journey.strategy}</p>
                      <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700">{journey.primary_channel}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{journey.goal}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Configuración operativa</p>
              {omnichannelDraft ? (
                <div className="mt-3 space-y-3">
                  {[
                    ["whatsapp_bot_enabled", "WhatsApp bot"],
                    ["email_enabled", "Correo automatizado"],
                    ["callbot_enabled", "Callbot de cobranza"],
                    ["inbound_bot_enabled", "Atención entrante del bot"],
                    ["automation_enabled", "Orquestación automática"],
                    ["webhooks_configured", "Webhooks configurados"],
                    ["template_library_ready", "Biblioteca de plantillas lista"],
                  ].map(([key, label]) => (
                    <label key={key} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-700">
                      <span>{label}</span>
                      <input
                        type="checkbox"
                        checked={Boolean(omnichannelDraft[key])}
                        onChange={(event) => setOmnichannelDraft((current) => ({ ...current, [key]: event.target.checked }))}
                        className="h-4 w-4"
                      />
                    </label>
                  ))}
                  <textarea
                    value={omnichannelDraft.notes || ""}
                    onChange={(event) => setOmnichannelDraft((current) => ({ ...current, notes: event.target.value }))}
                    rows="4"
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                    placeholder="Notas del administrador: proveedor previsto, alcance del bot, reglas de derivación, restricciones o decisiones pendientes."
                  />
                  <div className="grid gap-3">
                    <input
                      value={omnichannelDraft.twilio_account_sid || ""}
                      onChange={(event) => setOmnichannelDraft((current) => ({ ...current, twilio_account_sid: event.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                      placeholder="Twilio Account SID"
                    />
                    <input
                      value={omnichannelDraft.twilio_auth_token || ""}
                      onChange={(event) => setOmnichannelDraft((current) => ({ ...current, twilio_auth_token: event.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                      placeholder="Twilio Auth Token"
                    />
                    <div className="grid gap-3 md:grid-cols-2">
                      <input
                        value={omnichannelDraft.twilio_whatsapp_from || ""}
                        onChange={(event) => setOmnichannelDraft((current) => ({ ...current, twilio_whatsapp_from: event.target.value }))}
                        className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                        placeholder="From WhatsApp (ej. whatsapp:+14155238886)"
                      />
                      <input
                        value={omnichannelDraft.twilio_demo_phone || ""}
                        onChange={(event) => {
                          const value = event.target.value;
                          setOmnichannelDraft((current) => ({ ...current, twilio_demo_phone: value }));
                          setWhatsAppDemoForm((current) => ({ ...current, to_phone: value }));
                        }}
                        className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                        placeholder="Número demo destino"
                      />
                    </div>
                  </div>
                  <div className="rounded-xl bg-sky-50 px-4 py-3 text-sm text-sky-700">
                    Siguiente paso recomendado: {overview?.omnichannel?.next_step || "Definir la primera fase omnicanal."}
                  </div>
                  <div className="rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-3 text-sm text-emerald-700">
                    <p className="font-semibold mb-1">📡 Webhooks configurados en el sistema:</p>
                    <p>• <code className="font-mono bg-emerald-100 px-1 rounded">POST /webhooks/twilio/whatsapp</code> — Bot entrante WhatsApp</p>
                    <p className="mt-1">• <code className="font-mono bg-emerald-100 px-1 rounded">POST /webhooks/twilio/voice</code> — IVR Callbot voz</p>
                    <p className="mt-1">• <code className="font-mono bg-emerald-100 px-1 rounded">POST /webhooks/twilio/voice/gather</code> — Respuesta IVR</p>
                  </div>
                  {channelDemoResult ? (
                    <div className={`rounded-xl border px-4 py-3 text-sm font-medium ${channelDemoResult.ok ? "bg-emerald-50 border-emerald-100 text-emerald-700" : "bg-red-50 border-red-100 text-red-700"}`}>
                      <span className="font-bold">{channelDemoResult.ch}: </span>{String(channelDemoResult.msg)}
                    </div>
                  ) : null}
                  {omnichannelPreview ? (
                    <div className="rounded-2xl border border-cyan-100 bg-cyan-50/70 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">Preview omnicanal</p>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700">{String(omnichannelPreview.channel || "").toUpperCase()}</span>
                      </div>
                      <p className="mt-2 text-sm text-slate-700">{omnichannelPreview.client_name || "Cliente"} · {omnichannelPreview.identity_code || "Sin número único"} · {omnichannelPreview.strategy_code}</p>
                      {omnichannelPreview.account_reference ? <p className="mt-1 text-xs text-slate-500">Cuenta: {omnichannelPreview.account_reference}</p> : null}
                      {omnichannelPreview.subject ? <p className="mt-3 text-sm font-semibold text-ink">Asunto: {omnichannelPreview.subject}</p> : null}
                      {omnichannelPreview.message ? <p className="mt-3 whitespace-pre-wrap rounded-xl bg-white px-3 py-3 text-sm text-slate-700">{omnichannelPreview.message}</p> : null}
                      {omnichannelPreview.html ? (
                        <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white">
                          <iframe title="preview-email" srcDoc={omnichannelPreview.html} className="h-72 w-full" />
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => onSaveOmnichannelConfig(omnichannelDraft)}
                    disabled={saving}
                    className="w-full rounded-xl bg-ink py-3 font-bold text-white disabled:opacity-70 hover:bg-brand-blue transition-colors"
                  >
                    {saving ? "Guardando..." : "💾 Guardar configuración omnicanal"}
                  </button>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Demo de WhatsApp</p>
                    <div className="mt-3 grid gap-3">
                      <input
                        value={whatsAppDemoForm.to_phone}
                        onChange={(event) => setWhatsAppDemoForm((current) => ({ ...current, to_phone: event.target.value }))}
                        className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3"
                        placeholder="Número destino (+503...)"
                      />
                      <div className="grid gap-3 md:grid-cols-2">
                        <select
                          value={whatsAppDemoForm.strategy_code}
                          onChange={(event) => setWhatsAppDemoForm((current) => ({ ...current, strategy_code: event.target.value }))}
                          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3"
                        >
                          {["PREVENTIVO", "FMORA1", "MMORA2", "HMORA3", "AMORA4", "BMORA5", "CMORA6", "DMORA7", "VAGENCIASEXTERNASINTERNO", "HMR"].map((code) => (
                            <option key={code} value={code}>{code}</option>
                          ))}
                        </select>
                        <select
                          value={whatsAppDemoForm.client_id}
                          onChange={(event) => setWhatsAppDemoForm((current) => ({ ...current, client_id: event.target.value }))}
                          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3"
                        >
                          <option value="">Sin cliente específico</option>
                          {(clients || []).slice(0, 50).map((client) => (
                            <option key={client.id} value={client.id}>{formatOmnichannelClientOption(client)}</option>
                          ))}
                        </select>
                      </div>
                      <textarea
                        value={whatsAppDemoForm.custom_message}
                        onChange={(event) => setWhatsAppDemoForm((current) => ({ ...current, custom_message: event.target.value }))}
                        rows="3"
                        className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3"
                        placeholder="Mensaje opcional. Si lo dejas vacío, el sistema arma uno según la estrategia."
                      />
                      <button
                        type="button"
                        onClick={() => previewChannelMessage("whatsapp", { ...whatsAppDemoForm, client_id: whatsAppDemoForm.client_id ? Number(whatsAppDemoForm.client_id) : null })}
                        disabled={omnichannelPreviewLoading}
                        className="w-full rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-semibold text-ink disabled:opacity-50"
                      >
                        {omnichannelPreviewLoading ? "Generando preview..." : "Previsualizar WhatsApp"}
                      </button>
                      <button
                        type="button"
                        onClick={() => onSendWhatsAppDemo({ ...whatsAppDemoForm, client_id: whatsAppDemoForm.client_id ? Number(whatsAppDemoForm.client_id) : null })}
                        disabled={saving || !whatsAppDemoForm.to_phone}
                        className="w-full rounded-xl bg-emerald-600 py-3 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                      >
                        {saving ? "Enviando..." : "📲 Enviar demo por WhatsApp →"}
                      </button>
                    </div>
                  </div>

                  {/* ── Email Demo ──────────────────────────────────────── */}
                  <div className="rounded-2xl border border-blue-100 bg-blue-50/50 p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-600 mb-3">📧 Email — Resend.com (100/día gratis)</p>
                    <div className="grid gap-3">
                      <input value={emailDemoForm.to_email}
                        onChange={e => setEmailDemoForm(f => ({...f, to_email: e.target.value}))}
                        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
                        placeholder="destinatario@email.com" type="email" />
                      <div className="grid grid-cols-2 gap-3">
                        <select value={emailDemoForm.strategy_code}
                          onChange={e => setEmailDemoForm(f => ({...f, strategy_code: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
                          {["PREVENTIVO","FMORA1","MMORA2","HMORA3","AMORA4","BMORA5","CMORA6","DMORA7"].map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                        <select value={emailDemoForm.client_id}
                          onChange={e => setEmailDemoForm(f => ({...f, client_id: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
                          <option value="">Sin cliente</option>
                          {(clients || []).slice(0, 30).map(c => (
                            <option key={c.id} value={c.id}>{formatOmnichannelClientOption(c)}</option>
                          ))}
                        </select>
                      </div>
                      <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                        <input type="checkbox" checked={emailDemoForm.use_smtp}
                          onChange={e => setEmailDemoForm(f => ({...f, use_smtp: e.target.checked}))} className="h-3.5 w-3.5" />
                        Usar SMTP (Gmail/Outlook) en vez de Resend
                      </label>
                      <button type="button" disabled={omnichannelPreviewLoading || !emailDemoForm.to_email}
                        onClick={() => previewChannelMessage("email", { ...emailDemoForm, client_id: emailDemoForm.client_id ? Number(emailDemoForm.client_id) : null })}
                        className="w-full rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-semibold text-ink disabled:opacity-50">
                        {omnichannelPreviewLoading ? "Generando preview..." : "Previsualizar email"}
                      </button>
                      <button type="button" disabled={saving || !emailDemoForm.to_email}
                        onClick={() => sendChannelDemo(
                          "Email",
                          "/admin/omnichannel/email/demo-send",
                          { ...emailDemoForm, client_id: emailDemoForm.client_id ? Number(emailDemoForm.client_id) : null },
                          (data) => `✓ Email enviado a ${data.to}`
                        )}
                        className="w-full rounded-xl bg-blue-600 py-2.5 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors">
                        {channelSending === "Email" ? "Enviando..." : "📧 Enviar email de prueba →"}
                      </button>
                    </div>
                  </div>

                  {/* ── SMS Demo ────────────────────────────────────────── */}
                  <div className="rounded-2xl border border-green-100 bg-green-50/50 p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-green-600 mb-3">📱 SMS — TextBelt (1/día sin cuenta)</p>
                    <div className="grid gap-3">
                      <input value={smsDemoForm.to_phone}
                        onChange={e => setSmsDemoForm(f => ({...f, to_phone: e.target.value}))}
                        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
                        placeholder="+50312345678" />
                      <div className="grid grid-cols-2 gap-3">
                        <select value={smsDemoForm.strategy_code}
                          onChange={e => setSmsDemoForm(f => ({...f, strategy_code: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
                          {["PREVENTIVO","FMORA1","MMORA2","HMORA3"].map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                        <select value={smsDemoForm.client_id}
                          onChange={e => setSmsDemoForm(f => ({...f, client_id: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
                          <option value="">Cliente automatico por estrategia</option>
                          {(clients || []).slice(0, 30).map(c => (
                            <option key={c.id} value={c.id}>{formatOmnichannelClientOption(c)}</option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-1 gap-3">
                        <select value={smsDemoForm.provider}
                          onChange={e => setSmsDemoForm(f => ({...f, provider: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
                          <option value="textbelt">TextBelt (gratis)</option>
                          <option value="twilio">Twilio SMS</option>
                        </select>
                      </div>
                      <button type="button" disabled={omnichannelPreviewLoading || !smsDemoForm.to_phone}
                        onClick={() => previewChannelMessage("sms", { ...smsDemoForm, client_id: smsDemoForm.client_id ? Number(smsDemoForm.client_id) : null })}
                        className="w-full rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-semibold text-ink disabled:opacity-50">
                        {omnichannelPreviewLoading ? "Generando preview..." : "Previsualizar SMS"}
                      </button>
                      <button type="button" disabled={saving || channelSending === "SMS" || !smsDemoForm.to_phone}
                        onClick={() => sendChannelDemo(
                          "SMS",
                          "/admin/omnichannel/sms/demo-send",
                          { ...smsDemoForm, client_id: smsDemoForm.client_id ? Number(smsDemoForm.client_id) : null },
                          (data) => `✓ SMS vía ${data.provider} enviado a ${data.to}. Cliente: ${data.client_name}. Cuenta ...${data.account_last4}. Monto vencido USD ${Number(data.total_due || 0).toFixed(0)}`
                        )}
                        className="w-full rounded-xl bg-green-600 py-2.5 text-sm font-bold text-white hover:bg-green-700 disabled:opacity-50 transition-colors">
                        {channelSending === "SMS" ? "Enviando..." : "📱 Enviar SMS de prueba →"}
                      </button>
                    </div>
                  </div>

                  {/* ── CallBot Demo ─────────────────────────────────────── */}
                  <div className="rounded-2xl border border-purple-100 bg-purple-50/50 p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-purple-600 mb-3">📞 CallBot IVR — Twilio Voice</p>
                    <div className="grid gap-3">
                      <input value={callbotDemoForm.to_phone}
                        onChange={e => setCallbotDemoForm(f => ({...f, to_phone: e.target.value}))}
                        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
                        placeholder="+50312345678 (número verificado en Twilio)" />
                      <div className="grid grid-cols-2 gap-3">
                        <input value={callbotDemoForm.client_id}
                          onChange={e => setCallbotDemoForm(f => ({...f, client_id: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
                          placeholder="ID cliente (opcional)" />
                        <select value={callbotDemoForm.strategy_code}
                          onChange={e => setCallbotDemoForm(f => ({...f, strategy_code: e.target.value}))}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
                          {["FMORA1","MMORA2","HMORA3","AMORA4","BMORA5","VAGENCIASEXTERNASINTERNO"].map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>
                      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
                        Requiere twilio_voice_from + callbot_webhook_url. Prueba local: <code className="font-mono">ngrok http 8000</code>
                      </p>
                      <button type="button" disabled={saving || channelSending === "CallBot" || !callbotDemoForm.to_phone}
                        onClick={() => sendChannelDemo(
                          "CallBot",
                          "/admin/omnichannel/callbot/demo-call",
                          { ...callbotDemoForm, client_id: callbotDemoForm.client_id ? Number(callbotDemoForm.client_id) : null },
                          (data) => `✓ Llamada iniciada · SID: ${data.sid}`
                        )}
                        className="w-full rounded-xl bg-purple-600 py-2.5 text-sm font-bold text-white hover:bg-purple-700 disabled:opacity-50 transition-colors">
                        {channelSending === "CallBot" ? "Iniciando..." : "📞 Iniciar llamada de prueba →"}
                      </button>
                    </div>
                  </div>

                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-500">Cargando configuración omnicanal...</p>
              )}
            </div>
          </div>
        </section>

        <section className={`mt-6 glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("daily_simulation") ? "" : "hidden"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-ink">Simular día operativo</h3>
              <p className="mt-2 text-sm text-slate-600">Avanza un día de mora, simula pagos para mover clientes entre estrategias o al día, agrega cartera nueva para `FMORA1`, `PREVENTIVO` y `Recovery`, y rota placements desde `V11` en adelante.</p>
            </div>
            <button
              type="button"
              onClick={() => onRunDailySimulation(simulationForm)}
              disabled={saving}
              className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70"
            >
              {saving ? "Procesando..." : "Simular dia operativo"}
            </button>
            <button
              type="button"
              onClick={runSimulationPreview}
              disabled={simulationPreviewLoading}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 font-semibold text-ink disabled:opacity-70"
            >
              {simulationPreviewLoading ? "Calculando..." : "Previsualizar simulación"}
            </button>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <input
              type="number"
              min="0"
              max="5000"
              value={simulationForm.fmora1_clients}
              onChange={(event) => setSimulationForm((current) => ({ ...current, fmora1_clients: Number(event.target.value || 0) }))}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              placeholder="Clientes nuevos FMORA1"
            />
            <input
              type="number"
              min="0"
              max="5000"
              value={simulationForm.preventivo_clients}
              onChange={(event) => setSimulationForm((current) => ({ ...current, preventivo_clients: Number(event.target.value || 0) }))}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              placeholder="Clientes nuevos PREVENTIVO"
            />
            <input
              type="number"
              min="0"
              max="5000"
              value={simulationForm.recovery_clients}
              onChange={(event) => setSimulationForm((current) => ({ ...current, recovery_clients: Number(event.target.value || 0) }))}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              placeholder="Clientes nuevos Recovery"
            />
          </div>
          {dailySimulationPreview ? (
            <div className="mt-4 rounded-2xl border border-cyan-200 bg-cyan-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700">Previsualización segura</p>
                  <p className="mt-1 text-sm text-slate-700">{dailySimulationPreview.message}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${dailySimulationPreview.already_applied_today ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                  {dailySimulationPreview.already_applied_today ? "Ya aplicada hoy" : "No modifica la base"}
                </span>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-cyan-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Envejecerían</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationPreview.aged_accounts}</p></div>
                <div className="rounded-2xl border border-cyan-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Pagos estimados</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationPreview.simulated_payments}</p></div>
                <div className="rounded-2xl border border-cyan-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cuentas que podrían curarse</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationPreview.fully_cured_accounts}</p></div>
                <div className="rounded-2xl border border-cyan-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rotaciones Recovery</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationPreview.recovery_rotations}</p></div>
              </div>
              {(dailySimulationPreview.warnings || []).length ? (
                <div className="mt-4 space-y-2">
                  {(dailySimulationPreview.warnings || []).map((warning, index) => (
                    <p key={`simulation-warning-${index}`} className="rounded-2xl bg-white px-4 py-3 text-sm text-amber-800">• {warning}</p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {dailySimulationSummary ? (
            <div className="mt-4 grid gap-4 md:grid-cols-4 xl:grid-cols-8">
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cuentas con mora +1</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.aged_accounts}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Nuevos FMORA1</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.inserted_fmora1_clients}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Nuevos PREVENTIVO</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.inserted_preventivo_clients}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Nuevos Recovery</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.inserted_recovery_clients}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Pagos simulados</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.simulated_payments}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cuentas al día</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.fully_cured_accounts}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rotaciones Recovery</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.recovery_rotations}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Total clientes</p><p className="mt-2 text-2xl font-bold text-ink">{dailySimulationSummary.total_clients}</p></div>
            </div>
          ) : null}
        </section>

        <section className={`mt-6 grid gap-6 xl:grid-cols-2 ${showAdminSection("documents", "user_import", "reports", "client_import", "strategies", "sql_query") ? "" : "hidden"}`}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              onAnalyzeDocument(documentFile, documentNotes);
            }}
            className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("documents") ? "" : "hidden"}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Cargar PDF de estrategia o manual</h3>
                <p className="mt-2 text-sm text-slate-600">El sistema analiza el documento, propone ajustes y los deja en revisión antes de aplicarlos.</p>
              </div>
              <button type="button" onClick={onDownloadTemplate} className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-ink">
                Descargar formato .docx
              </button>
            </div>
            <div className="mt-4 grid gap-4">
              <input type="file" accept=".pdf" onChange={(event) => setDocumentFile(event.target.files?.[0] || null)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" />
              <textarea value={documentNotes} onChange={(event) => setDocumentNotes(event.target.value)} rows="4" className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Notas del administrador: objetivo del documento, área impactada o ajustes esperados." />
              <button disabled={saving || !documentFile} className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70">{saving ? "Analizando..." : "Analizar documento"}</button>
            </div>
          </form>

          <section className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("documents") ? "" : "hidden"}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-ink">Propuesta de ajustes</h3>
                <p className="mt-2 text-sm text-slate-600">Revisa, ajusta conceptualmente y aplica solo cuando estés conforme.</p>
              </div>
              {proposal ? <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">{proposal.status}</span> : null}
            </div>
            {!proposalDraft ? (
              <p className="mt-4 text-sm text-slate-500">Aún no hay una propuesta generada desde PDF.</p>
            ) : (
              <div className="mt-4 space-y-4 text-sm text-slate-700">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Documento</p>
                  <p className="mt-2 font-semibold text-ink">{proposalDraft.file_name}</p>
                  <textarea value={proposalDraft.summary || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, summary: event.target.value }))} rows="3" className="mt-3 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" />
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Estrategias sugeridas</p>
                    <p className="mt-2 text-2xl font-bold text-ink">{proposalDraft.suggested_strategies?.length || 0}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Reglas de canal</p>
                    <p className="mt-2 text-2xl font-bold text-ink">{proposalDraft.suggested_channel_rules?.length || 0}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Sublistas detectadas</p>
                    <p className="mt-2 text-2xl font-bold text-ink">{proposalDraft.suggested_sublists?.length || 0}</p>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Contexto extraído</p>
                  <div className="mt-2 space-y-2">
                    {(proposalDraft.extracted_context || []).map((item, index) => <p key={`ctx-${index}`}>• {item}</p>)}
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Estrategias</p>
                    <div className="mt-2 space-y-3">
                      {(proposalDraft.suggested_strategies || []).map((item, index) => (
                        <div key={`${item.codigo}-${index}`} className="rounded-2xl bg-slate-50 p-3">
                          <input value={item.codigo || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_strategies: current.suggested_strategies.map((entry, entryIndex) => entryIndex === index ? { ...entry, codigo: event.target.value.toUpperCase() } : entry) }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 font-semibold text-ink" />
                          <input value={item.nombre || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_strategies: current.suggested_strategies.map((entry, entryIndex) => entryIndex === index ? { ...entry, nombre: event.target.value } : entry) }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
                          <textarea value={item.descripcion || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_strategies: current.suggested_strategies.map((entry, entryIndex) => entryIndex === index ? { ...entry, descripcion: event.target.value } : entry) }))} rows="2" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
                          <input value={item.action || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_strategies: current.suggested_strategies.map((entry, entryIndex) => entryIndex === index ? { ...entry, action: event.target.value } : entry) }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500" />
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Sublistas propuestas</p>
                    <div className="mt-2 space-y-3">
                      {(proposalDraft.suggested_sublists || []).map((item, index) => (
                        <div key={`${item.codigo}-${index}`} className="rounded-2xl bg-slate-50 p-3">
                          <input value={item.codigo || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_sublists: current.suggested_sublists.map((entry, entryIndex) => entryIndex === index ? { ...entry, codigo: event.target.value.toUpperCase() } : entry) }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 font-semibold text-ink" />
                          <textarea value={item.descripcion || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_sublists: current.suggested_sublists.map((entry, entryIndex) => entryIndex === index ? { ...entry, descripcion: event.target.value } : entry) }))} rows="2" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
                          <input value={item.strategy || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, suggested_sublists: current.suggested_sublists.map((entry, entryIndex) => entryIndex === index ? { ...entry, strategy: event.target.value } : entry) }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Notas de implementación</p>
                  <div className="mt-2 space-y-2">
                    {(proposalDraft.implementation_notes || []).map((item, index) => (
                      <textarea key={`note-${index}`} value={item || ""} onChange={(event) => setProposalDraft((current) => ({ ...current, implementation_notes: current.implementation_notes.map((entry, entryIndex) => entryIndex === index ? event.target.value : entry) }))} rows="2" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2" />
                    ))}
                  </div>
                </div>
                <button type="button" onClick={() => onAdjustProposal(proposalDraft)} disabled={saving || proposalDraft.status === "APLICADA"} className="w-full rounded-2xl bg-white px-4 py-3 font-semibold text-ink disabled:opacity-70">
                  {saving ? "Guardando ajuste..." : "Ajustar propuesta"}
                </button>
                <button onClick={() => onApplyProposal(proposalDraft.proposal_id)} disabled={saving || proposalDraft.status === "APLICADA"} className="w-full rounded-2xl bg-ocean px-4 py-3 font-semibold text-white disabled:opacity-70">
                  {saving ? "Aplicando..." : proposalDraft.status === "APLICADA" ? "Propuesta aplicada" : "Aprobar y aplicar propuesta"}
                </button>
                <button type="button" onClick={() => onDiscardProposal(proposalDraft.proposal_id)} disabled={saving || proposalDraft.status === "APLICADA"} className="w-full rounded-2xl bg-white px-4 py-3 font-semibold text-ink disabled:opacity-70">
                  Limpiar propuesta cargada
                </button>
              </div>
            )}
          </section>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              onAnalyzeUserImport(userImportFile);
            }}
            className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("user_import") ? "" : "hidden"}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Carga masiva de usuarios</h3>
                <p className="mt-2 text-sm text-slate-600">Importa usuarios operativos, supervisores y administradores desde un archivo estructurado.</p>
              </div>
              <button type="button" onClick={onDownloadUserImportTemplate} className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-ink">
                Descargar plantilla CSV
              </button>
            </div>
            <div className="mt-4 grid gap-4">
              <input type="file" accept=".csv,.xlsx,.xls" onChange={(event) => setUserImportFile(event.target.files?.[0] || null)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" />
              <button type="submit" disabled={saving || !userImportFile} className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70">
                {saving ? "Validando..." : "Validar archivo de usuarios"}
              </button>
            </div>
          </form>

          <section className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("user_import") ? "" : "hidden"}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-ink">Previsualización de usuarios</h3>
                <p className="mt-2 text-sm text-slate-600">Revisa nuevos usuarios, actualizaciones y errores antes de aplicar.</p>
              </div>
              {userImportProposal ? <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">{userImportProposal.status}</span> : null}
            </div>
            {!userImportProposal ? (
              <p className="mt-4 text-sm text-slate-500">Aún no hay una carga de usuarios validada.</p>
            ) : (
              <div className="mt-4 space-y-4 text-sm text-slate-700">
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Filas válidas</p><p className="mt-2 text-2xl font-bold text-ink">{userImportProposal.valid_rows}</p></div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Usuarios nuevos</p><p className="mt-2 text-2xl font-bold text-ink">{userImportProposal.new_clients}</p></div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Usuarios existentes</p><p className="mt-2 text-2xl font-bold text-ink">{userImportProposal.existing_clients}</p></div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mt-2 overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-500">
                          <th className="px-3 py-2 font-medium">Nombre</th>
                          <th className="px-3 py-2 font-medium">Email</th>
                          <th className="px-3 py-2 font-medium">Usuario</th>
                          <th className="px-3 py-2 font-medium">Rol</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(userImportProposal.preview_rows || []).map((row, index) => (
                          <tr key={`${row.username || row.email}-${index}`} className="border-b border-slate-100">
                            <td className="px-3 py-3 text-slate-700">{row.nombre}</td>
                            <td className="px-3 py-3 text-slate-700">{row.email}</td>
                            <td className="px-3 py-3 text-slate-700">{row.username}</td>
                            <td className="px-3 py-3 text-slate-700">{row.rol}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <button type="button" onClick={() => onApplyUserImport(userImportProposal.proposal_id)} disabled={saving || userImportProposal.status === "APLICADA"} className="w-full rounded-2xl bg-ocean px-4 py-3 font-semibold text-white disabled:opacity-70">
                  {saving ? "Aplicando usuarios..." : userImportProposal.status === "APLICADA" ? "Carga aplicada" : "Aplicar carga de usuarios"}
                </button>
                <button type="button" onClick={() => onDiscardUserImport(userImportProposal.proposal_id)} disabled={saving || userImportProposal.status === "APLICADA"} className="w-full rounded-2xl bg-white px-4 py-3 font-semibold text-ink disabled:opacity-70">
                  Limpiar carga validada
                </button>
              </div>
            )}
          </section>

          <section className={`glass rounded-3xl border border-white/60 p-6 shadow-panel xl:col-span-2 ${showAdminSection("reports") ? "" : "hidden"}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-ink">Generador de reportes gerenciales</h3>
                <p className="mt-2 text-sm text-slate-600">Escribe el reporte que necesitas y el sistema arma una vista ejecutiva con indicadores y dashboards listos para presentar.</p>
              </div>
            </div>
            <div className="mt-4 grid gap-4">
              <textarea value={reportPrompt} onChange={(event) => setReportPrompt(event.target.value)} rows="4" className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Ejemplo: Necesito un reporte ejecutivo de recuperación, promesas en riesgo, mora severa y distribución por estrategia para presentar a gerencia." />
              <button type="button" onClick={() => onGenerateReport(reportPrompt, setReportMessage)} disabled={saving || !reportPrompt.trim()} className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70">
                {saving ? "Generando..." : "Generar reporte analítico"}
              </button>
              <button
                type="button"
                onClick={() => onDownloadGeneratedReport(reportPrompt, setReportMessage)}
                disabled={saving || !reportPrompt.trim()}
                className="rounded-2xl bg-white px-4 py-3 font-semibold text-ink disabled:opacity-70"
              >
                Descargar reporte detallado
              </button>
            </div>
            {reportMessage ? <p className="mt-3 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">{reportMessage}</p> : null}
            {generatedReport ? (
              <div className="mt-6 space-y-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-lg font-semibold text-ink">{generatedReport.title}</h4>
                  <p className="mt-2 text-sm text-slate-600">{generatedReport.summary}</p>
                </div>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {(generatedReport.cards || []).map((card, index) => (
                    <div key={`report-card-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{card.title}</p>
                      <p className="mt-2 text-2xl font-bold text-ink">{card.value}</p>
                      <p className="mt-2 text-sm text-slate-600">{card.detail}</p>
                    </div>
                  ))}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  {(generatedReport.charts || []).map((chart, index) => (
                    <div key={`report-chart-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                      <p className="text-sm font-semibold text-ink">{chart.title}</p>
                      <div className="mt-3 space-y-2">
                        {(chart.items || []).map((item, itemIndex) => (
                          <div key={`chart-item-${itemIndex}`} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
                            <span className="text-sm text-slate-700">{item.label}</span>
                            <span className="text-sm font-semibold text-ink">{item.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Hallazgos clave</p>
                  <div className="mt-3 space-y-2">
                    {(generatedReport.insights || []).map((item, index) => <p key={`insight-${index}`}>• {item}</p>)}
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              onAnalyzeImport(importFile);
            }}
            className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("client_import") ? "" : "hidden"}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Carga masiva de clientes y cartera</h3>
                <p className="mt-2 text-sm text-slate-600">Importa clientes, cuentas y asignaciones desde un archivo estructurado. El sistema valida antes de aplicar.</p>
              </div>
              <button type="button" onClick={onDownloadImportTemplate} className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-ink">
                Descargar plantilla CSV
              </button>
            </div>
            <div className="mt-4 grid gap-4">
              <input type="file" accept=".csv,.xlsx,.xls" onChange={(event) => setImportFile(event.target.files?.[0] || null)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" />
              <button type="submit" disabled={saving || !importFile} className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70">
                {saving ? "Validando..." : "Validar archivo de carga"}
              </button>
            </div>
          </form>

          <section className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("client_import") ? "" : "hidden"}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-ink">Previsualización de carga</h3>
                <p className="mt-2 text-sm text-slate-600">Revisa conteos, errores y una muestra de registros antes de importar.</p>
              </div>
              {importProposal ? <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">{importProposal.status}</span> : null}
            </div>
            {!importProposal ? (
              <p className="mt-4 text-sm text-slate-500">Aún no hay una carga validada.</p>
            ) : (
              <div className="mt-4 space-y-4 text-sm text-slate-700">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Archivo</p>
                  <p className="mt-2 font-semibold text-ink">{importProposal.file_name}</p>
                  <p className="mt-2 text-sm text-slate-600">{importProposal.summary}</p>
                </div>
                <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Filas totales</p><p className="mt-2 text-2xl font-bold text-ink">{importProposal.total_rows}</p></div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Filas válidas</p><p className="mt-2 text-2xl font-bold text-ink">{importProposal.valid_rows}</p></div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Clientes nuevos</p><p className="mt-2 text-2xl font-bold text-ink">{importProposal.new_clients}</p></div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cuentas nuevas</p><p className="mt-2 text-2xl font-bold text-ink">{importProposal.new_accounts}</p></div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Errores detectados</p>
                    <div className="mt-2 space-y-2">
                      {(importProposal.sample_errors || []).length ? importProposal.sample_errors.map((item, index) => <p key={`import-error-${index}`}>• {item}</p>) : <p className="text-sm text-emerald-700">No se detectaron errores en la muestra validada.</p>}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Columnas esperadas</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(importProposal.expected_columns || []).map((item) => (
                        <span key={item} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{item}</span>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Muestra de registros válidos</p>
                  <div className="mt-3 overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-500">
                          <th className="px-3 py-2 font-medium">Cliente</th>
                          <th className="px-3 py-2 font-medium">Cuenta</th>
                          <th className="px-3 py-2 font-medium">Producto</th>
                          <th className="px-3 py-2 font-medium">Mora</th>
                          <th className="px-3 py-2 font-medium">Estrategia</th>
                          <th className="px-3 py-2 font-medium">Collector</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(importProposal.preview_rows || []).map((row, index) => (
                          <tr key={`${row.identity_code}-${row.numero_cuenta}-${index}`} className="border-b border-slate-100">
                            <td className="px-3 py-3 text-slate-700">{row.cliente}</td>
                            <td className="px-3 py-3 text-slate-700">{row.numero_cuenta}</td>
                            <td className="px-3 py-3 text-slate-700">{row.tipo_producto}</td>
                            <td className="px-3 py-3 text-slate-700">{row.dias_mora}</td>
                            <td className="px-3 py-3 text-slate-700">{row.estrategia_codigo}</td>
                            <td className="px-3 py-3 text-slate-700">{row.collector_username}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <button type="button" onClick={() => onApplyImport(importProposal.proposal_id)} disabled={saving || importProposal.status === "APLICADA"} className="w-full rounded-2xl bg-ocean px-4 py-3 font-semibold text-white disabled:opacity-70">
                  {saving ? "Aplicando carga..." : importProposal.status === "APLICADA" ? "Carga aplicada" : "Aplicar carga al sistema"}
                </button>
                <button type="button" onClick={() => onDiscardImport(importProposal.proposal_id)} disabled={saving || importProposal.status === "APLICADA"} className="w-full rounded-2xl bg-white px-4 py-3 font-semibold text-ink disabled:opacity-70">
                  Limpiar carga validada
                </button>
              </div>
            )}
          </section>

          <section className={`glass rounded-3xl border border-white/60 p-6 shadow-panel xl:col-span-2 ${showAdminSection("sql_query") ? "" : "hidden"}`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-ink">Consultas SQL seguras</h3>
                <p className="mt-2 text-sm text-slate-600">Solo para administradores. Este módulo usa una conexión de solo lectura, timeout corto y límite de filas para no afectar el trabajo operativo de usuarios conectados.</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                Permitido: <code className="font-mono">SELECT</code>, <code className="font-mono">WITH</code>, <code className="font-mono">EXPLAIN</code>
              </div>
            </div>
            <div className="mt-4 grid gap-4">
              <textarea
                value={sqlQueryText}
                onChange={(event) => setSqlQueryText(event.target.value)}
                rows={8}
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-sm"
                placeholder="select identity_code, nombres, apellidos from clientes limit 50"
              />
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="number"
                  min="1"
                  max="1000"
                  value={sqlQueryMaxRows}
                  onChange={(event) => setSqlQueryMaxRows(Number(event.target.value || 200))}
                  className="w-36 rounded-2xl border border-slate-200 bg-white px-4 py-3"
                  placeholder="Máx filas"
                />
                <button
                  type="button"
                  onClick={executeSqlQuery}
                  disabled={sqlQueryLoading || !sqlQueryText.trim()}
                  className="rounded-2xl bg-ink px-5 py-3 font-semibold text-white disabled:opacity-70"
                >
                  {sqlQueryLoading ? "Ejecutando..." : "Ejecutar consulta"}
                </button>
              </div>
              {sqlQueryResult ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm text-slate-600">
                      <span className="font-semibold text-ink">{sqlQueryResult.row_count}</span> filas
                      {sqlQueryResult.truncated ? <span> · resultado truncado</span> : null}
                      <span> · {sqlQueryResult.duration_ms} ms</span>
                    </div>
                    <code className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{sqlQueryResult.normalized_query}</code>
                  </div>
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-500">
                          {(sqlQueryResult.columns || []).map((column) => (
                            <th key={column} className="px-3 py-2 font-medium">{column}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(sqlQueryResult.rows || []).map((row, index) => (
                          <tr key={`sql-row-${index}`} className="border-b border-slate-100">
                            {(sqlQueryResult.columns || []).map((column) => (
                              <td key={`${index}-${column}`} className="px-3 py-2 text-slate-700">{row[column] == null ? "" : String(row[column])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
                  Aquí aparecerá el resultado de la consulta. Úsalo para extraer data sin entrar manualmente a pgAdmin.
                </div>
              )}
            </div>
          </section>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              onCreateStrategy(strategyForm, () => setStrategyForm({ codigo: "", nombre: "", descripcion: "", categoria: "COBRANZA", orden: 0 }));
            }}
            className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("strategies") ? "" : "hidden"}`}
          >
            <h3 className="text-xl font-semibold text-ink">Crear nueva estrategia</h3>
            <div className="mt-4 grid gap-4">
              <div className="grid gap-4 md:grid-cols-2">
                <input value={strategyForm.codigo} onChange={(event) => setStrategyForm((current) => ({ ...current, codigo: event.target.value.toUpperCase() }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Codigo" />
                <input value={strategyForm.nombre} onChange={(event) => setStrategyForm((current) => ({ ...current, nombre: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Nombre" />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <select value={strategyForm.categoria} onChange={(event) => setStrategyForm((current) => ({ ...current, categoria: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <option value="COBRANZA">Cobranza</option>
                  <option value="MITIGACION">Mitigacion</option>
                  <option value="REESTRUCTURA">Reestructura</option>
                </select>
                <input type="number" value={strategyForm.orden} onChange={(event) => setStrategyForm((current) => ({ ...current, orden: Number(event.target.value) }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Orden" />
              </div>
              <textarea value={strategyForm.descripcion} onChange={(event) => setStrategyForm((current) => ({ ...current, descripcion: event.target.value }))} rows="4" className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Descripcion y uso operativo de la estrategia." />
              <button disabled={saving} className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70">{saving ? "Guardando..." : "Crear estrategia"}</button>
            </div>
          </form>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              const ids = assignForm.client_ids
                .split(",")
                .map((item) => Number(item.trim()))
                .filter((item) => Number.isFinite(item) && item > 0);
              onAssignWorklist({ ...assignForm, user_id: Number(assignForm.user_id), client_ids: ids });
            }}
            className={`glass rounded-3xl border border-white/60 p-6 shadow-panel ${showAdminSection("strategies") ? "" : "hidden"}`}
          >
            <h3 className="text-xl font-semibold text-ink">Asignar lista de trabajo</h3>
            <div className="mt-4 grid gap-4">
              <select value={assignForm.user_id} onChange={(event) => setAssignForm((current) => ({ ...current, user_id: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                <option value="">Selecciona usuario</option>
                {(overview?.collectors || []).map((user) => <option key={user.id} value={user.id}>{user.nombre} · {user.rol}</option>)}
              </select>
              <select value={assignForm.strategy_code} onChange={(event) => setAssignForm((current) => ({ ...current, strategy_code: event.target.value }))} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                <option value="">Sin estrategia fija</option>
                {(overview?.strategies || []).map((strategy) => <option key={strategy.id} value={strategy.codigo}>{strategy.codigo} · {strategy.nombre}</option>)}
              </select>
              <textarea value={assignForm.client_ids} onChange={(event) => setAssignForm((current) => ({ ...current, client_ids: event.target.value }))} rows="4" className="rounded-2xl border border-slate-200 bg-white px-4 py-3" placeholder="Ids de clientes separados por coma. Ejemplo: 21,22,23,24" />
              <button disabled={saving} className="rounded-2xl bg-ocean px-4 py-3 font-semibold text-white disabled:opacity-70">{saving ? "Asignando..." : "Asignar cartera"}</button>
            </div>
          </form>
        </section>

        <section className={`mt-6 grid gap-6 xl:grid-cols-2 ${showAdminSection("assignments") ? "" : "hidden"}`}>
          <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Grupos asignados por usuario</h3>
                <p className="mt-2 text-sm text-slate-600">Consulta carteras exactas como `V13A082`, asigna nuevas listas completas y desasigna las que ya no corresponden.</p>
              </div>
              <button
                type="button"
                onClick={() => selectedManagedCollectorId && onLoadUserGroups(Number(selectedManagedCollectorId))}
                className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-ink"
              >
                Recargar grupos
              </button>
            </div>
            <div className="mt-4 grid gap-4">
              <select
                value={selectedManagedCollectorId}
                onChange={(event) => setSelectedManagedCollectorId(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              >
                <option value="">Selecciona collector</option>
                {previewCollectors.map((collector) => (
                  <option key={collector.id} value={collector.id}>
                    {collector.nombre} · {collector.username}
                  </option>
                ))}
              </select>
              <select
                value={selectedCatalogGroupKey}
                onChange={(event) => setSelectedCatalogGroupKey(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              >
                <option value="">Selecciona cartera/grupo para asignar</option>
                {groupCatalogOptions.map((group) => (
                  <option key={group.key} value={group.key}>
                    {group.display_name} · {group.client_count} clientes
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => {
                  const selectedGroup = groupCatalogOptions.find((group) => group.key === selectedCatalogGroupKey);
                  if (!selectedManagedCollectorId || !selectedGroup) return;
                  onAssignGroupToUser({
                    user_id: Number(selectedManagedCollectorId),
                    group_id: selectedGroup.group_id,
                    strategy_code: selectedGroup.strategy_code,
                    placement_code: selectedGroup.placement_code,
                    reassign_existing: true,
                  });
                }}
                disabled={!selectedManagedCollectorId || !selectedCatalogGroupKey || saving}
                className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70"
              >
                {saving ? "Procesando..." : "Asignar grupo completo"}
              </button>
            </div>
            <div className="mt-5 space-y-3">
              {(selectedUserGroups || []).length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
                  Este usuario aún no tiene grupos activos cargados o falta seleccionar un collector.
                </div>
              ) : (
                (selectedUserGroups || []).map((group) => (
                  <div key={`${group.strategy_code}-${group.placement_code}-${group.group_id}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-ink">{group.display_name}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          Estrategia: {group.strategy_code || "N/D"} · Placement: {group.placement_code || "N/D"} · Scope: {group.channel_scope || "N/D"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-ocean">{group.client_count} clientes</span>
                        <button
                          type="button"
                          onClick={() => onUnassignGroupFromUser({
                            user_id: Number(selectedManagedCollectorId),
                            group_id: group.group_id,
                            strategy_code: group.strategy_code,
                            placement_code: group.placement_code,
                          })}
                          className="rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700"
                        >
                          Desasignar
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-ink">Collectors por supervisor</h3>
                <p className="mt-2 text-sm text-slate-600">Asigna o retira collectors de cada supervisor para controlar exactamente qué equipo ve en su panel.</p>
              </div>
            </div>
            <div className="mt-4 grid gap-4">
              <select
                value={selectedSupervisorId}
                onChange={(event) => setSelectedSupervisorId(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              >
                <option value="">Selecciona supervisor</option>
                {availableSupervisors.map((supervisor) => (
                  <option key={supervisor.id} value={supervisor.id}>
                    {supervisor.nombre} · {supervisor.username}
                  </option>
                ))}
              </select>
              <select
                value={selectedSupervisorCollectorId}
                onChange={(event) => setSelectedSupervisorCollectorId(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
              >
                <option value="">Selecciona collector para asignar</option>
                {availableCollectorsForSupervisor.map((collector) => (
                  <option key={collector.id} value={collector.id}>
                    {collector.nombre} · {collector.username}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => selectedSupervisorId && selectedSupervisorCollectorId && onAssignCollectorToSupervisor({
                  supervisor_id: Number(selectedSupervisorId),
                  collector_id: Number(selectedSupervisorCollectorId),
                })}
                disabled={!selectedSupervisorId || !selectedSupervisorCollectorId || saving}
                className="rounded-2xl bg-ink px-4 py-3 font-semibold text-white disabled:opacity-70"
              >
                {saving ? "Procesando..." : "Asignar collector al supervisor"}
              </button>
            </div>
            <div className="mt-5 space-y-3">
              {!selectedSupervisorAssignment ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
                  Selecciona un supervisor para ver su equipo actual.
                </div>
              ) : (
                <>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-sm font-semibold text-ink">{selectedSupervisorAssignment.supervisor.nombre}</p>
                    <p className="mt-1 text-xs text-slate-500">Equipo visible: {(selectedSupervisorAssignment.collectors || []).length} collectors</p>
                  </div>
                  {(selectedSupervisorAssignment.collectors || []).map((collector) => (
                    <div key={`supervisor-collector-${collector.id}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-ink">{collector.nombre}</p>
                          <p className="mt-1 text-xs text-slate-500">{collector.username}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => onUnassignCollectorFromSupervisor({
                            supervisor_id: Number(selectedSupervisorId),
                            collector_id: collector.id,
                          })}
                          className="rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700"
                        >
                          Desasignar
                        </button>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
          </section>
        </section>

        <section className={`mt-6 ${showAdminSection("strategies") ? "" : "hidden"}`}>
          <DataTable
            title="Catalogo de estrategias"
            rows={overview?.strategies || []}
            emptyText="No hay estrategias registradas."
            columns={[
              { key: "codigo", label: "Codigo" },
              { key: "nombre", label: "Nombre" },
              { key: "categoria", label: "Categoria" },
              { key: "orden", label: "Orden" }
            ]}
          />
        </section>
          </div>
        </div>
      </div>
    </div>
  );
}

function GenericWorkspace({ auth, users, clients, accounts, payments, prediction, onLogout, onRequestPrediction }) {
  const roleWidgets = {
    Auditor: [
      { title: "Eventos revisados", value: "246", detail: "Ultima semana" },
      { title: "Alertas abiertas", value: "5", detail: "2 con prioridad alta" },
      { title: "Usuarios con cambios", value: "8", detail: "Validar permisos" }
    ],
    GestorUsuarios: [
      { title: "Usuarios activos", value: users.length, detail: "Base operativa disponible" },
      { title: "Roles auditados", value: "5", detail: "Sin brechas criticas" },
      { title: "Ultimos accesos", value: "17", detail: "Hoy antes de las 9am" }
    ]
  };

  const sections = auth.user.rol === "GestorUsuarios" ? ["Usuarios"] : auth.user.rol === "Auditor" ? ["Usuarios", "Pagos", "IA"] : ["Clientes", "Cuentas", "Pagos", "IA"];
  const accountOptions = accounts.slice(0, 8);

  return (
    <div className="min-h-screen px-4 py-5 md:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="rounded-2xl bg-brand-gradient px-6 py-5 shadow-card-lg md:flex md:items-center md:justify-between relative overflow-hidden">
          <div className="absolute inset-0 opacity-10" style={{background:"radial-gradient(circle at 80% 50%, rgba(0,180,166,0.6) 0%, transparent 60%)"}} />
          <div className="relative flex items-center gap-4">
            <BrandLogo size="header" className="flex-shrink-0" />
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-teal">
                <span className="h-1.5 w-1.5 rounded-full bg-teal pulse-dot" />{auth.user.rol}
              </span>
              <h1 className="mt-1.5 text-xl font-bold text-white">Panel de consulta</h1>
              <p className="mt-0.5 text-sm text-slate-300">Consulta · Auditoría · Gestión de usuarios</p>
            </div>
          </div>
          <div className="relative mt-4 flex items-center gap-3 md:mt-0">
            <div className="rounded-xl border border-white/10 bg-white/8 px-4 py-2.5 text-right">
              <p className="text-xs text-slate-400">Sesión activa</p>
              <p className="text-sm font-bold text-white">{auth.user.nombre}</p>
            </div>
            <div className="hidden items-center gap-2 lg:flex">
              <select
                value={selectedCollectorId}
                onChange={(event) => setSelectedCollectorId(event.target.value)}
                className="rounded-xl border border-white/15 bg-white/10 px-3 py-2.5 text-sm font-semibold text-white"
              >
                {supervisedCollectors.map((collector) => (
                  <option key={collector.id} value={collector.id} className="text-ink">
                    {collector.nombre}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => selectedCollectorId && onOpenCollectorPreview(Number(selectedCollectorId))}
                disabled={!selectedCollectorId || collectorPreviewLoading}
                className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20 disabled:opacity-60"
              >
                {collectorPreviewLoading ? "Abriendo..." : "Ver estrategias"}
              </button>
            </div>
            <button onClick={onLogout} className="rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white/20">Cerrar sesión</button>
          </div>
        </header>

        <section className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {(roleWidgets[auth.user.rol] || []).map((widget) => <StatCard key={widget.title} {...widget} />)}
        </section>

        <section className="mt-6 grid gap-3">
          {sections.includes("Usuarios") ? <DataTable title="Usuarios" rows={users} emptyText="No hay usuarios disponibles." columns={[{ key: "id", label: "#" }, { key: "nombre", label: "Nombre" }, { key: "username", label: "Usuario" }, { key: "rol", label: "Rol" }]} /> : null}
          {sections.includes("Clientes") ? <DataTable title="Clientes" rows={clients} emptyText="No hay clientes cargados." columns={[{ key: "identity_code", label: "Numero Unico" }, { key: "nombres", label: "Nombres" }, { key: "apellidos", label: "Apellidos" }, { key: "segmento", label: "Segmento" }, { key: "telefono", label: "Telefono" }]} /> : null}
          {sections.includes("Cuentas") ? <DataTable title="Cuentas" rows={accounts} emptyText="No hay cuentas visibles." columns={[{ key: "numero_cuenta", label: "Cuenta" }, { key: "tipo_producto", label: "Producto" }, { key: "bucket_actual", label: "Bucket" }, { key: "saldo_total", label: "Saldo", render: (value) => currency(value) }, { key: "dias_mora", label: "Dias Mora" }]} /> : null}
          {sections.includes("Pagos") ? <DataTable title="Pagos" rows={payments} emptyText="No hay pagos registrados." columns={[{ key: "cuenta_id", label: "Cuenta ID" }, { key: "monto", label: "Monto", render: (value) => currency(value) }, { key: "canal", label: "Canal" }, { key: "fecha_pago", label: "Fecha", render: (value) => new Date(value).toLocaleString("es-SV") }]} /> : null}
          {sections.includes("IA") ? (
            <section className="glass rounded-3xl border border-white/60 p-6 shadow-panel">
              <div className="flex flex-wrap gap-2">
                {accountOptions.map((account) => (
                  <button key={account.id} onClick={() => onRequestPrediction(account.id)} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
                    {account.numero_cuenta}
                  </button>
                ))}
              </div>
              {prediction ? (
                <div className="mt-5 grid gap-4 md:grid-cols-3">
                  <StatCard title="Cuenta" value={`#${prediction.cuenta_id}`} detail="Cuenta evaluada" />
                  <StatCard title="Probabilidad" value={`${(prediction.probabilidad_pago_30d * 100).toFixed(2)}%`} detail="Ventana de 30 dias" />
                  <StatCard title="Recomendacion" value={`${prediction.score_modelo.toFixed(2)} pts`} detail={prediction.recomendacion} />
                </div>
              ) : null}
            </section>
          ) : null}
        </section>
      </div>
    </div>
  );
}

export default function App() {
  const [auth, setAuth] = useState(() => {
    const saved = localStorage.getItem("collectplus-auth");
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [users, setUsers] = useState([]);
  const [clients, setClients] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [payments, setPayments] = useState([]);
  const [prediction, setPrediction] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [adminOverview, setAdminOverview] = useState(null);
  const [adminProposal, setAdminProposal] = useState(null);
  const [adminImportProposal, setAdminImportProposal] = useState(null);
  const [adminUserImportProposal, setAdminUserImportProposal] = useState(null);
  const [adminGeneratedReport, setAdminGeneratedReport] = useState(null);
  const [adminDailySimulationSummary, setAdminDailySimulationSummary] = useState(null);
  const [adminDailySimulationPreview, setAdminDailySimulationPreview] = useState(null);
  const [adminRecoveryVintage, setAdminRecoveryVintage] = useState(null);
  const [adminRecoveryVintageCompare, setAdminRecoveryVintageCompare] = useState(null);
  const [adminExecutiveLog, setAdminExecutiveLog] = useState([]);
  const [adminRecoveryVintageLoading, setAdminRecoveryVintageLoading] = useState(false);
  const [adminWorklistGroupCatalog, setAdminWorklistGroupCatalog] = useState([]);
  const [adminSelectedUserGroups, setAdminSelectedUserGroups] = useState([]);
  const [adminSelectedUserGroupsUserId, setAdminSelectedUserGroupsUserId] = useState(null);
  const [adminSupervisorAssignments, setAdminSupervisorAssignments] = useState([]);
  const [supervisorOverview, setSupervisorOverview] = useState(null);
  const [adminCollectorPreviewPortfolio, setAdminCollectorPreviewPortfolio] = useState(null);
  const [adminCollectorPreviewId, setAdminCollectorPreviewId] = useState(null);
  const [adminCollectorPreviewOpen, setAdminCollectorPreviewOpen] = useState(false);
  const [adminCollectorPreviewLoading, setAdminCollectorPreviewLoading] = useState(false);
  const [supervisorCollectorPreviewPortfolio, setSupervisorCollectorPreviewPortfolio] = useState(null);
  const [supervisorCollectorPreviewId, setSupervisorCollectorPreviewId] = useState(null);
  const [supervisorCollectorPreviewOpen, setSupervisorCollectorPreviewOpen] = useState(false);
  const [supervisorCollectorPreviewLoading, setSupervisorCollectorPreviewLoading] = useState(false);

  const normalizeErrorMessage = (raw) => {
    if (!raw) return "No se pudo completar la solicitud.";
    if (typeof raw === "string") return raw;
    if (Array.isArray(raw)) {
      const first = raw[0];
      if (typeof first === "string") return first;
      if (first?.msg) return first.msg;
      return "Hay datos pendientes o invalidos en el formulario.";
    }
    if (typeof raw === "object") {
      if (typeof raw.detail === "string") return raw.detail;
      if (Array.isArray(raw.detail)) {
        const first = raw.detail[0];
        if (typeof first === "string") return first;
        if (first?.msg) return first.msg;
      }
      if (raw.msg) return raw.msg;
    }
    return "No se pudo completar la solicitud.";
  };

  const apiFetch = async (path, token, options = {}) => {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      }
    });
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const data = isJson ? await response.json() : await response.text();
    if (!response.ok) {
      if (response.status === 401) {
        setAuth(null);
        throw new Error("La sesion expiro. Inicia sesion nuevamente.");
      }
      throw new Error(normalizeErrorMessage(data));
    }
    return data;
  };

  const loadData = async (token, role) => {
    setError("");
    try {
      if (role === "Collector") {
        const collectorPortfolio = await apiFetch("/collector/portfolio/me", token);
        setPortfolio(collectorPortfolio);
        setSupervisorOverview(null);
        setAdminOverview(null);
        setAdminProposal(null);
        setAdminImportProposal(null);
        setAdminUserImportProposal(null);
        setAdminGeneratedReport(null);
        setAdminDailySimulationSummary(null);
        setAdminDailySimulationPreview(null);
        setAdminRecoveryVintage(null);
        setAdminRecoveryVintageCompare(null);
        setAdminExecutiveLog([]);
        setAdminRecoveryVintageLoading(false);
        setAdminWorklistGroupCatalog([]);
        setAdminSelectedUserGroups([]);
        setAdminSelectedUserGroupsUserId(null);
        setAdminSupervisorAssignments([]);
        setAdminCollectorPreviewPortfolio(null);
        setAdminCollectorPreviewId(null);
        setAdminCollectorPreviewOpen(false);
        setSupervisorCollectorPreviewPortfolio(null);
        setSupervisorCollectorPreviewId(null);
        setSupervisorCollectorPreviewOpen(false);
        setUsers([]);
        setClients([]);
        setAccounts([]);
        setPayments([]);
        return;
      }

      if (role === "Supervisor") {
        const overview = await apiFetch("/supervisor/overview/me", token);
        setSupervisorOverview(overview);
        setClients([]);
        setPortfolio(null);
        setAdminOverview(null);
        setAdminProposal(null);
        setAdminImportProposal(null);
        setAdminUserImportProposal(null);
        setAdminGeneratedReport(null);
        setAdminDailySimulationSummary(null);
        setAdminDailySimulationPreview(null);
        setAdminRecoveryVintage(null);
        setAdminRecoveryVintageCompare(null);
        setAdminExecutiveLog([]);
        setAdminRecoveryVintageLoading(false);
        setAdminWorklistGroupCatalog([]);
        setAdminSelectedUserGroups([]);
        setAdminSelectedUserGroupsUserId(null);
        setAdminSupervisorAssignments([]);
        setAdminCollectorPreviewPortfolio(null);
        setAdminCollectorPreviewId(null);
        setAdminCollectorPreviewOpen(false);
        setSupervisorCollectorPreviewPortfolio(null);
        setSupervisorCollectorPreviewId(null);
        setSupervisorCollectorPreviewOpen(false);
        setUsers([]);
        setClients([]);
        setAccounts([]);
        setPayments([]);
        return;
      }

      const requests = [];
      setPortfolio(null);
      setSupervisorOverview(null);
      if (role === "Admin") {
        requests.push(apiFetch("/admin/overview", token).then(setAdminOverview));
        requests.push(apiFetch(`/admin/recovery-vintage?year=${new Date().getFullYear() - 1}&sample_limit=20000`, token).then(setAdminRecoveryVintage));
        requests.push(apiFetch(`/admin/recovery-vintage/compare?years=${new Date().getFullYear() - 1},${new Date().getFullYear() - 2}`, token).then(setAdminRecoveryVintageCompare));
        requests.push(apiFetch("/admin/executive-log?limit=80", token).then(setAdminExecutiveLog));
        requests.push(apiFetch("/admin/worklists/groups/catalog", token).then(setAdminWorklistGroupCatalog));
        requests.push(apiFetch("/admin/supervisor-assignments", token).then(setAdminSupervisorAssignments));
      } else {
        setAdminOverview(null);
        setAdminProposal(null);
        setAdminImportProposal(null);
        setAdminUserImportProposal(null);
        setAdminGeneratedReport(null);
        setAdminDailySimulationSummary(null);
        setAdminDailySimulationPreview(null);
        setAdminRecoveryVintage(null);
        setAdminRecoveryVintageCompare(null);
        setAdminExecutiveLog([]);
        setAdminRecoveryVintageLoading(false);
        setAdminWorklistGroupCatalog([]);
        setAdminSelectedUserGroups([]);
        setAdminSelectedUserGroupsUserId(null);
        setAdminSupervisorAssignments([]);
        setAdminCollectorPreviewPortfolio(null);
        setAdminCollectorPreviewId(null);
        setAdminCollectorPreviewOpen(false);
        setSupervisorCollectorPreviewPortfolio(null);
        setSupervisorCollectorPreviewId(null);
        setSupervisorCollectorPreviewOpen(false);
      }
      if (["Admin", "GestorUsuarios", "Auditor"].includes(role)) {
        requests.push(apiFetch("/users", token).then(setUsers));
      } else {
        setUsers([]);
      }
      if (["Admin", "Auditor"].includes(role)) {
        requests.push(apiFetch("/clients", token).then(setClients));
        requests.push(apiFetch("/accounts", token).then(setAccounts));
        requests.push(apiFetch("/payments", token).then(setPayments));
      } else {
        setClients([]);
        setAccounts([]);
        setPayments([]);
      }
      await Promise.all(requests);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  useEffect(() => {
    if (auth) {
      localStorage.setItem("collectplus-auth", JSON.stringify(auth));
      void loadData(auth.token, auth.user.rol);
    } else {
      localStorage.removeItem("collectplus-auth");
    }
  }, [auth]);

  const handleLogin = async ({ username, password }) => {
    setLoading(true);
    setError("");
    try {
      const body = new URLSearchParams();
      body.append("username", username);
      body.append("password", password);
      const data = await apiFetch("/auth/login", null, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body
      });
      setAuth({ token: data.access_token, user: data.user });
      setPrediction(null);
      setSuccess("");
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setAuth(null);
    setUsers([]);
    setClients([]);
    setAccounts([]);
    setPayments([]);
    setPortfolio(null);
    setAdminOverview(null);
    setAdminProposal(null);
    setAdminImportProposal(null);
    setAdminUserImportProposal(null);
    setAdminGeneratedReport(null);
    setAdminDailySimulationSummary(null);
    setAdminDailySimulationPreview(null);
    setAdminRecoveryVintage(null);
    setAdminRecoveryVintageCompare(null);
    setAdminExecutiveLog([]);
    setAdminRecoveryVintageLoading(false);
    setAdminWorklistGroupCatalog([]);
    setAdminSelectedUserGroups([]);
    setAdminSelectedUserGroupsUserId(null);
    setAdminSupervisorAssignments([]);
    setSupervisorOverview(null);
    setAdminCollectorPreviewPortfolio(null);
    setAdminCollectorPreviewId(null);
    setAdminCollectorPreviewOpen(false);
    setSupervisorCollectorPreviewPortfolio(null);
    setSupervisorCollectorPreviewId(null);
    setSupervisorCollectorPreviewOpen(false);
    setPrediction(null);
    setError("");
    setSuccess("");
  };

  const requestPrediction = async (accountId) => {
    try {
      const data = await apiFetch(`/ai/predictions/${accountId}`, auth.token);
      setPrediction(data);
    } catch (predictionError) {
      setError(predictionError.message);
    }
  };

  const searchSystemClients = async (search) => {
    if (!auth) return;
    setError("");
    try {
      const query = search ? `?search=${encodeURIComponent(search)}` : "";
      const data = await apiFetch(`/clients${query}`, auth.token);
      setClients(data);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const lookupClientForWorkspace = async (search, mode) => {
    if (!auth || !search?.trim()) return null;
    try {
      const query = `?search=${encodeURIComponent(search.trim())}&mode=${encodeURIComponent(mode || "all")}`;
      return await apiFetch(`/collector/client-lookup${query}`, auth.token);
    } catch (requestError) {
      setError(requestError.message);
      return null;
    }
  };

  const refreshCurrentRole = async () => {
    if (!auth) return;
    await loadData(auth.token, auth.user.rol);
  };

  const openAdminCollectorPreview = async (collectorId) => {
    if (!auth || !collectorId) return;
    setAdminCollectorPreviewLoading(true);
    setError("");
    try {
      const preview = await apiFetch(`/admin/collector-portfolio/${collectorId}`, auth.token);
      setAdminCollectorPreviewPortfolio(preview);
      setAdminCollectorPreviewId(collectorId);
      setAdminCollectorPreviewOpen(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setAdminCollectorPreviewLoading(false);
    }
  };

  const openSupervisorCollectorPreview = async (collectorId) => {
    if (!auth || !collectorId) return;
    setSupervisorCollectorPreviewLoading(true);
    setError("");
    try {
      const preview = await apiFetch(`/supervisor/collector-portfolio/${collectorId}`, auth.token);
      setSupervisorCollectorPreviewPortfolio(preview);
      setSupervisorCollectorPreviewId(collectorId);
      setSupervisorCollectorPreviewOpen(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSupervisorCollectorPreviewLoading(false);
    }
  };

  const loadAdminUserGroups = async (userId) => {
    if (!auth || !userId) return;
    try {
      const groups = await apiFetch(`/admin/worklists/users/${userId}/groups`, auth.token);
      setAdminSelectedUserGroups(groups);
      setAdminSelectedUserGroupsUserId(userId);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const loadAdminRecoveryVintage = async (year) => {
    if (!auth) return;
    setAdminRecoveryVintageLoading(true);
    setError("");
    try {
      const selectedYear = Number(year || new Date().getFullYear() - 1);
      const data = await apiFetch(`/admin/recovery-vintage?year=${selectedYear}&sample_limit=20000`, auth.token);
      setAdminRecoveryVintage(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setAdminRecoveryVintageLoading(false);
    }
  };

  const loadAdminRecoveryVintageCompare = async (years) => {
    if (!auth) return;
    setError("");
    const data = await apiFetch(`/admin/recovery-vintage/compare?years=${encodeURIComponent(years)}`, auth.token);
    setAdminRecoveryVintageCompare(data);
    return data;
  };

  const loadAdminExecutiveLog = async () => {
    if (!auth) return;
    const data = await apiFetch("/admin/executive-log?limit=80", auth.token);
    setAdminExecutiveLog(data);
    return data;
  };

  const downloadAdminRecoveryVintage = async (year) => {
    if (!auth) return;
    setError("");
    try {
      const selectedYear = Number(year || new Date().getFullYear() - 1);
      const response = await fetch(`${API_URL}/admin/recovery-vintage/export?year=${selectedYear}`, {
        headers: { Authorization: `Bearer ${auth.token}` },
      });
      if (!response.ok) {
        const isJson = response.headers.get("content-type")?.includes("application/json");
        const data = isJson ? await response.json() : await response.text();
        throw new Error(normalizeErrorMessage(data));
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `recovery_cosecha_${selectedYear}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const downloadAdminRecoveryExecutiveDashboard = async (year, compareYears) => {
    if (!auth) return;
    setError("");
    try {
      const selectedYear = Number(year || new Date().getFullYear() - 1);
      const response = await fetch(
        `${API_URL}/admin/recovery-vintage/executive-export?year=${selectedYear}&compare_years=${encodeURIComponent(compareYears || "")}`,
        {
          headers: { Authorization: `Bearer ${auth.token}` },
        }
      );
      if (!response.ok) {
        const isJson = response.headers.get("content-type")?.includes("application/json");
        const data = isJson ? await response.json() : await response.text();
        throw new Error(normalizeErrorMessage(data));
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `dashboard_recovery_cosecha_${selectedYear}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
      setSuccess("Dashboard ejecutivo descargado correctamente.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const sendAdminAssistantMessage = async (message, applyChange = false) => {
    if (!auth) return null;
    const response = await apiFetch("/admin/assistant/chat", auth.token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, apply_change: applyChange }),
    });
    if (response?.data?.recovery_vintage) {
      setAdminRecoveryVintage(response.data.recovery_vintage);
    }
    if (response?.executed && !response?.data?.recovery_vintage) {
      await loadData(auth.token, auth.user.rol);
    }
    return response;
  };

  const runAdminSqlQuery = async (payload) => {
    if (!auth) return null;
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch("/admin/sql/query", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSuccess(`Consulta SQL ejecutada en ${response.duration_ms} ms.`);
      return response;
    } catch (requestError) {
      setError(requestError.message);
      throw requestError;
    }
  };

  const assignAdminGroup = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch("/admin/worklists/groups/assign", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSuccess(response.message || "Cartera asignada correctamente.");
      await loadData(auth.token, auth.user.rol);
      await loadAdminUserGroups(payload.user_id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const unassignAdminGroup = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch("/admin/worklists/groups/unassign", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSuccess(response.message || "Cartera desasignada correctamente.");
      await loadData(auth.token, auth.user.rol);
      await loadAdminUserGroups(payload.user_id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const assignCollectorToSupervisor = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch("/admin/supervisor-assignments", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSuccess(response.message || "Collector asignado al supervisor.");
      await loadData(auth.token, auth.user.rol);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const unassignCollectorFromSupervisor = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch("/admin/supervisor-assignments/remove", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSuccess(response.message || "Collector desasignado del supervisor.");
      await loadData(auth.token, auth.user.rol);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const submitManagement = async (client, form, account, onDone) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      let reviewReason = "";
      if (form.promise_date && form.promise_amount && account?.pago_minimo && Number(form.promise_amount) < Number(account.pago_minimo)) {
        reviewReason = "Acuerdo de pago es menor al minimo sugerido.";
      }
      if (form.promise_date) {
        const promiseDate = new Date(form.promise_date);
        const today = new Date();
        let businessDays = 0;
        const cursor = new Date(today);
        while (businessDays < 5) {
          cursor.setDate(cursor.getDate() + 1);
          if (cursor.getDay() !== 0 && cursor.getDay() !== 6) businessDays += 1;
        }
        if (promiseDate > cursor) {
          reviewReason = reviewReason ? `${reviewReason} Acuerdo de pago excede los 5 dias habiles.` : "Acuerdo de pago excede los 5 dias habiles.";
        }
      }
      const response = await apiFetch("/collector/managements", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: client.id,
          account_id: Number(form.account_id),
          account_ids: (form.account_ids || []).map((id) => Number(id)),
          contact_channel: form.contact_channel,
          called_phone: form.called_phone || null,
          rdm: form.rdm || null,
          management_type: form.management_type,
          result: form.result,
          notes: form.notes,
          promise_date: form.promise_date || null,
          promise_amount: form.promise_amount ? Number(form.promise_amount) : null,
          callback_at: form.callback_at || null
        })
      });
      setSuccess(response.requires_supervisor_review ? `${reviewReason || "Gestion enviada a Revision Supervisor por politica de negocio."}` : "Gestion guardada correctamente.");
      onDone();
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const loadClientDemographics = async (client) => {
    return apiFetch(`/collector/clients/${client.id}/demographics`, auth.token);
  };

  const updateDemographics = async (client, form, refreshOverride = null, onDone = null) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch(`/collector/clients/${client.id}/demographics`, auth.token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form)
      });
      setSuccess("Datos demograficos actualizados.");
      if (onDone) onDone();
      if (refreshOverride) await refreshOverride();
      else await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const createStrategy = async (form, onDone) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/admin/strategies", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form)
      });
      setSuccess("Estrategia creada correctamente.");
      onDone();
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const assignWorklist = async (form) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/admin/worklists/assign", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form)
      });
      setSuccess("Lista de trabajo asignada correctamente.");
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const analyzeAdminDocument = async (file, notes) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("admin_notes", notes || "");
      const proposal = await apiFetch("/admin/documents/analyze", auth.token, {
        method: "POST",
        body: formData
      });
      setAdminProposal(proposal);
      setSuccess("Documento analizado. Ya puedes revisar la propuesta sugerida.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const applyAdminProposal = async (proposalId) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch(`/admin/documents/${proposalId}/apply`, auth.token, {
        method: "POST"
      });
      setAdminProposal((current) => (current ? { ...current, status: response.status } : current));
      setSuccess("La propuesta fue aprobada y aplicada al catalogo del sistema.");
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const adjustAdminProposal = async (proposalDraft) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const updated = await apiFetch(`/admin/documents/${proposalDraft.proposal_id}/update`, auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          summary: proposalDraft.summary,
          suggested_strategies: proposalDraft.suggested_strategies || [],
          suggested_channel_rules: proposalDraft.suggested_channel_rules || [],
          suggested_sublists: proposalDraft.suggested_sublists || [],
          implementation_notes: proposalDraft.implementation_notes || [],
        })
      });
      setAdminProposal(updated);
      setSuccess("La propuesta fue ajustada y quedó lista para revisión final.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const discardAdminProposal = async (proposalId) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch(`/admin/documents/${proposalId}/discard`, auth.token, {
        method: "POST"
      });
      setAdminProposal(null);
      setSuccess("La propuesta cargada fue descartada.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const downloadAdminTemplate = async () => {
    try {
      const response = await fetch(`${API_URL}/admin/documents/template`, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      if (!response.ok) {
        throw new Error("No se pudo descargar la plantilla.");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "plantilla-estrategia-ajustes-360collectplus.docx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const analyzeAdminImport = async (file) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const proposal = await apiFetch("/admin/imports/clients/analyze", auth.token, {
        method: "POST",
        body: formData
      });
      setAdminImportProposal(proposal);
      setSuccess("Archivo validado. Ya puedes revisar la previsualización antes de aplicarlo.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const applyAdminImport = async (proposalId) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch(`/admin/imports/clients/${proposalId}/apply`, auth.token, {
        method: "POST"
      });
      setAdminImportProposal((current) => (current ? { ...current, status: response.status } : current));
      setSuccess("La carga fue aplicada al sistema correctamente.");
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const discardAdminImport = async (proposalId) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch(`/admin/imports/clients/${proposalId}/discard`, auth.token, {
        method: "POST"
      });
      setAdminImportProposal(null);
      setSuccess("La carga validada fue descartada.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const downloadAdminImportTemplate = async () => {
    try {
      const response = await fetch(`${API_URL}/admin/imports/template`, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      if (!response.ok) {
        throw new Error("No se pudo descargar la plantilla de carga.");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "plantilla-carga-clientes-360collectplus.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const analyzeAdminUserImport = async (file) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const proposal = await apiFetch("/admin/imports/users/analyze", auth.token, {
        method: "POST",
        body: formData
      });
      setAdminUserImportProposal(proposal);
      setSuccess("Archivo de usuarios validado. Ya puedes revisar la carga antes de aplicarla.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const applyAdminUserImport = async (proposalId) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch(`/admin/imports/users/${proposalId}/apply`, auth.token, {
        method: "POST"
      });
      setAdminUserImportProposal((current) => (current ? { ...current, status: response.status } : current));
      setSuccess("La carga de usuarios fue aplicada correctamente.");
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const discardAdminUserImport = async (proposalId) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch(`/admin/imports/users/${proposalId}/discard`, auth.token, {
        method: "POST"
      });
      setAdminUserImportProposal(null);
      setSuccess("La carga validada de usuarios fue descartada.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const downloadAdminUserImportTemplate = async () => {
    try {
      const response = await fetch(`${API_URL}/admin/imports/users/template`, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      if (!response.ok) {
        throw new Error("No se pudo descargar la plantilla de usuarios.");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "plantilla-carga-usuarios-360collectplus.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const generateAdminReport = async (description, setLocalMessage) => {
    setSaving(true);
    setError("");
    setSuccess("");
    if (setLocalMessage) setLocalMessage("Generando reporte...");
    try {
      const report = await apiFetch("/admin/reports/generate", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description })
      });
      setAdminGeneratedReport(report);
      setSuccess("Reporte generado correctamente.");
      if (setLocalMessage) setLocalMessage("Reporte generado correctamente.");
    } catch (requestError) {
      setError(requestError.message);
      if (setLocalMessage) setLocalMessage(`No se pudo generar el reporte: ${requestError.message}`);
    } finally {
      setSaving(false);
    }
  };

  const downloadAdminGeneratedReport = async (description, setLocalMessage) => {
    setSaving(true);
    setError("");
    setSuccess("");
    if (setLocalMessage) setLocalMessage("Preparando archivo del reporte...");
    try {
      const response = await fetch(`${API_URL}/admin/reports/download?description=${encodeURIComponent(description)}`, {
        headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
      });
      if (!response.ok) {
        const isJson = response.headers.get("content-type")?.includes("application/json");
        const data = isJson ? await response.json() : await response.text();
        throw new Error(normalizeErrorMessage(data));
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "reporte-gerencial-detallado.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      setSuccess("Reporte detallado descargado correctamente.");
      if (setLocalMessage) setLocalMessage("Reporte detallado descargado correctamente.");
    } catch (requestError) {
      setError(requestError.message);
      if (setLocalMessage) setLocalMessage(`No se pudo descargar el reporte: ${requestError.message}`);
    } finally {
      setSaving(false);
    }
  };

  const runAdminDailySimulation = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const summary = await apiFetch("/admin/simulations/daily-rollover", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setAdminDailySimulationSummary(summary);
      setSuccess(summary.message);
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const previewAdminDailySimulation = async (payload) => {
    setError("");
    setSuccess("");
    const preview = await apiFetch("/admin/simulations/daily-rollover/preview", auth.token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    setAdminDailySimulationPreview(preview);
    setSuccess(preview.message);
    return preview;
  };

  const previewAdminOmnichannel = async (payload) => {
    setError("");
    const preview = await apiFetch("/admin/omnichannel/preview", auth.token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return preview;
  };

  const saveAdminOmnichannelConfig = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/admin/omnichannel/config", auth.token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setSuccess("Configuración omnicanal guardada correctamente.");
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const sendAdminWhatsAppDemo = async (payload) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await apiFetch("/admin/omnichannel/whatsapp/demo-send", auth.token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setSuccess(`${response.message} SID: ${response.sid}`);
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const approveSupervisorReview = async (promiseId, onDone) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch(`/supervisor/reviews/${promiseId}/approve`, auth.token, {
        method: "POST"
      });
      setSuccess("Caso revisado. La promesa quedo en estado PENDIENTE.");
      if (onDone) onDone();
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const approveSupervisorReviewBatch = async (promiseIds, onDone) => {
    const uniqueIds = Array.from(new Set((promiseIds || []).filter(Boolean)));
    if (!uniqueIds.length) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      for (const promiseId of uniqueIds) {
        await apiFetch(`/supervisor/reviews/${promiseId}/approve`, auth.token, {
          method: "POST"
        });
      }
      setSuccess(`${uniqueIds.length} casos revisados. Las promesas quedaron en estado PENDIENTE.`);
      if (onDone) onDone();
      await refreshCurrentRole();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  if (!auth) {
    return <LoginForm onLogin={handleLogin} loading={loading} error={error} />;
  }

  if (auth.user.rol === "Collector") {
    return (
      <CollectorWorkspace
        auth={auth}
        portfolio={portfolio}
        onLogout={handleLogout}
        onRefresh={refreshCurrentRole}
        onSubmitManagement={submitManagement}
        onLoadDemographics={loadClientDemographics}
        onUpdateDemographics={updateDemographics}
        onLookupClient={lookupClientForWorkspace}
        saving={saving}
        error={error}
        success={success}
      />
    );
  }

  if (auth.user.rol === "Supervisor") {
    if (supervisorCollectorPreviewOpen && supervisorCollectorPreviewPortfolio) {
      return (
        <CollectorWorkspace
          auth={auth}
          portfolio={supervisorCollectorPreviewPortfolio}
          onLogout={() => setSupervisorCollectorPreviewOpen(false)}
          onRefresh={() => openSupervisorCollectorPreview(supervisorCollectorPreviewId)}
          onSubmitManagement={submitManagement}
          onLoadDemographics={loadClientDemographics}
          onUpdateDemographics={updateDemographics}
          onLookupClient={lookupClientForWorkspace}
          saving={saving}
          error={error}
          success={success}
          exitLabel="Volver a supervisor"
        />
      );
    }
    return (
      <SupervisorWorkspace
        auth={auth}
        overview={supervisorOverview}
        systemClients={clients}
        onSearchSystemClients={searchSystemClients}
        onLogout={handleLogout}
        onRefresh={refreshCurrentRole}
        onApproveReview={approveSupervisorReview}
        onApproveReviewBatch={approveSupervisorReviewBatch}
        onOpenCollectorPreview={openSupervisorCollectorPreview}
        collectorPreviewLoading={supervisorCollectorPreviewLoading}
        saving={saving}
        error={error}
      />
    );
  }

  if (auth.user.rol === "Admin" && adminCollectorPreviewOpen && adminCollectorPreviewPortfolio) {
    return (
      <CollectorWorkspace
        auth={auth}
        portfolio={adminCollectorPreviewPortfolio}
        onLogout={() => setAdminCollectorPreviewOpen(false)}
        onRefresh={() => openAdminCollectorPreview(adminCollectorPreviewId)}
        onSubmitManagement={submitManagement}
        onLoadDemographics={loadClientDemographics}
        onUpdateDemographics={updateDemographics}
        onLookupClient={lookupClientForWorkspace}
        saving={saving}
        error={error}
        success={success}
        exitLabel="Volver a admin"
      />
    );
  }

  if (auth.user.rol === "Admin") {
    return (
      <AdminWorkspace
        auth={auth}
        overview={adminOverview}
        clients={clients}
        proposal={adminProposal}
        importProposal={adminImportProposal}
        userImportProposal={adminUserImportProposal}
        generatedReport={adminGeneratedReport}
        dailySimulationSummary={adminDailySimulationSummary}
        dailySimulationPreview={adminDailySimulationPreview}
        recoveryVintage={adminRecoveryVintage}
        recoveryVintageLoading={adminRecoveryVintageLoading}
        recoveryVintageCompare={adminRecoveryVintageCompare}
        executiveLog={adminExecutiveLog}
        collectorPreviewPortfolio={adminCollectorPreviewPortfolio}
        collectorPreviewId={adminCollectorPreviewId}
        collectorPreviewLoading={adminCollectorPreviewLoading}
        worklistGroupCatalog={adminWorklistGroupCatalog}
        selectedUserGroups={adminSelectedUserGroups}
        selectedUserGroupsUserId={adminSelectedUserGroupsUserId}
        supervisorAssignments={adminSupervisorAssignments}
        onOpenCollectorPreview={openAdminCollectorPreview}
        onLoadUserGroups={loadAdminUserGroups}
        onAssignGroupToUser={assignAdminGroup}
        onUnassignGroupFromUser={unassignAdminGroup}
        onAssignCollectorToSupervisor={assignCollectorToSupervisor}
        onUnassignCollectorFromSupervisor={unassignCollectorFromSupervisor}
        onLoadRecoveryVintage={loadAdminRecoveryVintage}
        onLoadRecoveryVintageCompare={loadAdminRecoveryVintageCompare}
        onLoadExecutiveLog={loadAdminExecutiveLog}
        onDownloadRecoveryVintage={downloadAdminRecoveryVintage}
        onDownloadRecoveryExecutiveDashboard={downloadAdminRecoveryExecutiveDashboard}
        onRunSqlQuery={runAdminSqlQuery}
        onAdminAssistantMessage={sendAdminAssistantMessage}
        onPreviewOmnichannel={previewAdminOmnichannel}
        onLogout={handleLogout}
        onCreateStrategy={createStrategy}
        onAssignWorklist={assignWorklist}
        onAnalyzeDocument={analyzeAdminDocument}
        onApplyProposal={applyAdminProposal}
        onAdjustProposal={adjustAdminProposal}
        onDiscardProposal={discardAdminProposal}
        onDownloadTemplate={downloadAdminTemplate}
        onAnalyzeImport={analyzeAdminImport}
        onApplyImport={applyAdminImport}
        onDiscardImport={discardAdminImport}
        onDownloadImportTemplate={downloadAdminImportTemplate}
        onAnalyzeUserImport={analyzeAdminUserImport}
        onApplyUserImport={applyAdminUserImport}
        onDiscardUserImport={discardAdminUserImport}
        onDownloadUserImportTemplate={downloadAdminUserImportTemplate}
        onGenerateReport={generateAdminReport}
        onDownloadGeneratedReport={downloadAdminGeneratedReport}
        onRunDailySimulation={runAdminDailySimulation}
        onPreviewDailySimulation={previewAdminDailySimulation}
        onSaveOmnichannelConfig={saveAdminOmnichannelConfig}
        onSendWhatsAppDemo={sendAdminWhatsAppDemo}
        saving={saving}
        error={error}
        success={success}
      />
    );
  }

  return (
    <GenericWorkspace
      auth={auth}
      users={users}
      clients={clients}
      accounts={accounts}
      payments={payments}
      prediction={prediction}
      onLogout={handleLogout}
      onRequestPrediction={requestPrediction}
    />
  );
}
