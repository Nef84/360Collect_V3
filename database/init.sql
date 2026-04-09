CREATE TABLE IF NOT EXISTS agencias (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    ciudad VARCHAR(80),
    region VARCHAR(80),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agentes (
    id SERIAL PRIMARY KEY,
    agencia_id INTEGER REFERENCES agencias(id),
    nombre VARCHAR(120) NOT NULL,
    codigo_agente VARCHAR(30) UNIQUE NOT NULL,
    rol_operativo VARCHAR(40) NOT NULL,
    telefono VARCHAR(30),
    email VARCHAR(180),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    email VARCHAR(180) UNIQUE NOT NULL,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(40) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_login TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    identity_code VARCHAR(30) UNIQUE NOT NULL,
    nombres VARCHAR(120) NOT NULL,
    apellidos VARCHAR(120) NOT NULL,
    dui VARCHAR(20) UNIQUE NOT NULL,
    nit VARCHAR(30),
    telefono VARCHAR(30),
    email VARCHAR(180),
    direccion TEXT,
    score_riesgo NUMERIC(5,2) NOT NULL DEFAULT 0.50,
    segmento VARCHAR(40),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cuentas (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    numero_cuenta VARCHAR(40) UNIQUE NOT NULL,
    tipo_producto VARCHAR(40) NOT NULL,
    subtipo_producto VARCHAR(60),
    saldo_capital NUMERIC(12,2) NOT NULL DEFAULT 0,
    saldo_mora NUMERIC(12,2) NOT NULL DEFAULT 0,
    saldo_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    dias_mora INTEGER NOT NULL DEFAULT 0,
    bucket_actual VARCHAR(30) NOT NULL DEFAULT '0-30',
    estado VARCHAR(30) NOT NULL DEFAULT 'ACTIVA',
    fecha_apertura DATE,
    fecha_vencimiento DATE,
    fecha_separacion DATE,
    tasa_interes NUMERIC(6,2) NOT NULL DEFAULT 0,
    es_estrafinanciamiento BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bucket_historial (
    id SERIAL PRIMARY KEY,
    cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
    bucket_anterior VARCHAR(30),
    bucket_nuevo VARCHAR(30) NOT NULL,
    fecha_cambio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    motivo VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS history (
    id SERIAL PRIMARY KEY,
    entidad VARCHAR(60) NOT NULL,
    entidad_id INTEGER NOT NULL,
    accion VARCHAR(60) NOT NULL,
    descripcion TEXT,
    usuario_id INTEGER REFERENCES usuarios(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pagos (
    id SERIAL PRIMARY KEY,
    cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
    monto NUMERIC(12,2) NOT NULL,
    fecha_pago TIMESTAMP NOT NULL,
    canal VARCHAR(50) NOT NULL,
    referencia VARCHAR(80),
    observacion TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS promesas (
    id SERIAL PRIMARY KEY,
    cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
    usuario_id INTEGER REFERENCES usuarios(id),
    fecha_promesa DATE NOT NULL,
    monto_prometido NUMERIC(12,2) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campanas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    estrategia VARCHAR(120),
    segmento_objetivo VARCHAR(80),
    fecha_inicio DATE,
    fecha_fin DATE,
    estado VARCHAR(30) NOT NULL DEFAULT 'ACTIVA',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS estrategias (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    descripcion TEXT,
    categoria VARCHAR(50),
    orden INTEGER NOT NULL DEFAULT 0,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asignaciones_cartera (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    estrategia_codigo VARCHAR(50),
    fecha_asignacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activa BOOLEAN NOT NULL DEFAULT TRUE
);

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

CREATE TABLE IF NOT EXISTS predicciones_ia (
    id SERIAL PRIMARY KEY,
    cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
    probabilidad_pago_30d NUMERIC(5,4) NOT NULL,
    score_modelo NUMERIC(8,2) NOT NULL,
    modelo_version VARCHAR(40) NOT NULL DEFAULT 'xgb-v1',
    fecha_prediccion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recomendacion TEXT
);

INSERT INTO estrategias (codigo, nombre, descripcion, categoria, orden, activa) VALUES
('PREVENTIVO', 'Preventivo', 'Clientes posteriores al vencimiento pero antes del corte.', 'COBRANZA', 1, TRUE),
('FMORA1', 'F Mora 1', 'Clientes entre 1 y 30 dias de mora.', 'COBRANZA', 2, TRUE),
('MMORA2', 'M Mora 2', 'Clientes entre 31 y 60 dias de mora.', 'COBRANZA', 3, TRUE),
('HMORA3', 'H Mora 3', 'Clientes entre 61 y 90 dias de mora.', 'COBRANZA', 4, TRUE),
('AMORA4', 'A Mora 4', 'Clientes entre 91 y 120 dias de mora.', 'COBRANZA', 5, TRUE),
('BMORA5', 'B Mora 5', 'Clientes entre 121 y 150 dias de mora.', 'COBRANZA', 6, TRUE),
('CMORA6', 'C Mora 6', 'Clientes entre 151 y 180 dias de mora.', 'COBRANZA', 7, TRUE),
('DMORA7', 'D Mora 7', 'Clientes con mas de 190 dias de mora y status vigente.', 'COBRANZA', 8, TRUE),
('VAGENCIASEXTERNASINTERNO', 'V Agencias Externas Interno', 'Clientes mayores a 180 dias con status liquidado o Z.', 'COBRANZA', 9, TRUE),
('HERRAMIENTAS', 'Herramientas de mitigacion HMR', 'Refinanciamiento integral, mega consolidacion y demas herramientas HMR.', 'MITIGACION', 10, TRUE);

INSERT INTO agencias (nombre, ciudad, region) VALUES
('Agencia Central', 'San Salvador', 'Centro'),
('Agencia Santa Ana', 'Santa Ana', 'Occidente'),
('Agencia San Miguel', 'San Miguel', 'Oriente');

INSERT INTO agentes (agencia_id, nombre, codigo_agente, rol_operativo, telefono, email) VALUES
(1, 'Marvin Rivas', 'AG001', 'Collector', '7000-0101', 'marvin.rivas@360collectplus.local'),
(1, 'Paola Amaya', 'AG002', 'Supervisor', '7000-0102', 'paola.amaya@360collectplus.local'),
(2, 'Elena Castillo', 'AG003', 'Collector', '7000-0103', 'elena.castillo@360collectplus.local'),
(2, 'Victor Pena', 'AG004', 'Auditor', '7000-0104', 'victor.pena@360collectplus.local'),
(3, 'Carla Salinas', 'AG005', 'Collector', '7000-0105', 'carla.salinas@360collectplus.local');

INSERT INTO usuarios (nombre, email, username, password_hash, rol, activo) VALUES
('Administrador General', 'admin@360collectplus.local', 'admin', 'Password123!', 'Admin', TRUE),
('Supervisor Uno', 'supervisor1@360collectplus.local', 'supervisor1', 'Password123!', 'Supervisor', TRUE),
('Supervisor Dos', 'supervisor2@360collectplus.local', 'supervisor2', 'Password123!', 'Supervisor', TRUE),
('Collector Uno', 'collector1@360collectplus.local', 'collector1', 'Password123!', 'Collector', TRUE),
('Collector Dos', 'collector2@360collectplus.local', 'collector2', 'Password123!', 'Collector', TRUE),
('Collector Tres', 'collector3@360collectplus.local', 'collector3', 'Password123!', 'Collector', TRUE),
('Collector Cuatro', 'collector4@360collectplus.local', 'collector4', 'Password123!', 'Collector', TRUE),
('Collector Cinco', 'collector5@360collectplus.local', 'collector5', 'Password123!', 'Collector', TRUE),
('Collector Seis', 'collector6@360collectplus.local', 'collector6', 'Password123!', 'Collector', TRUE),
('Auditor Uno', 'auditor1@360collectplus.local', 'auditor1', 'Password123!', 'Auditor', TRUE),
('Auditor Dos', 'auditor2@360collectplus.local', 'auditor2', 'Password123!', 'Auditor', TRUE),
('Gestor Usuarios Uno', 'gestor1@360collectplus.local', 'gestor1', 'Password123!', 'GestorUsuarios', TRUE),
('Gestor Usuarios Dos', 'gestor2@360collectplus.local', 'gestor2', 'Password123!', 'GestorUsuarios', TRUE),
('Admin Regional', 'admin2@360collectplus.local', 'admin2', 'Password123!', 'Admin', TRUE),
('Supervisor Tres', 'supervisor3@360collectplus.local', 'supervisor3', 'Password123!', 'Supervisor', TRUE),
('Collector Siete', 'collector7@360collectplus.local', 'collector7', 'Password123!', 'Collector', TRUE),
('Collector Ocho', 'collector8@360collectplus.local', 'collector8', 'Password123!', 'Collector', TRUE),
('Auditor Tres', 'auditor3@360collectplus.local', 'auditor3', 'Password123!', 'Auditor', TRUE),
('Gestor Usuarios Tres', 'gestor3@360collectplus.local', 'gestor3', 'Password123!', 'GestorUsuarios', TRUE),
('Collector Nueve', 'collector9@360collectplus.local', 'collector9', 'Password123!', 'Collector', TRUE);

INSERT INTO clientes (identity_code, nombres, apellidos, dui, nit, telefono, email, direccion, score_riesgo, segmento) VALUES
('00000000001', 'Ana Lucia', 'Martinez Cruz', '10000001-1', '0614-010101-101-1', '7000-1001', 'ana.martinez@mail.com', 'San Salvador, Colonia Escalon', 0.21, 'Preferente'),
('00000000002', 'Jose Manuel', 'Hernandez Flores', '10000002-2', '0614-010101-102-2', '7000-1002', 'jose.hernandez@mail.com', 'Santa Ana, Barrio San Rafael', 0.48, 'Masivo'),
('00000000003', 'Carla Sofia', 'Lopez Ayala', '10000003-3', '0614-010101-103-3', '7000-1003', 'carla.lopez@mail.com', 'Soyapango, Reparto Las Canas', 0.57, 'Masivo'),
('00000000004', 'Miguel Angel', 'Ramirez Ruiz', '10000004-4', '0614-010101-104-4', '7000-1004', 'miguel.ramirez@mail.com', 'Mejicanos, Colonia Zacamil', 0.69, 'Riesgo'),
('00000000005', 'Rosa Elena', 'Guardado Perez', '10000005-5', '0614-010101-105-5', '7000-1005', 'rosa.guardado@mail.com', 'San Miguel, Jardines del Rio', 0.34, 'Preferente'),
('00000000006', 'Luis Fernando', 'Pineda Torres', '10000006-6', '0614-010101-106-6', '7000-1006', 'luis.pineda@mail.com', 'Ilopango, Bosques del Matazano', 0.51, 'Masivo'),
('00000000007', 'Patricia', 'Castro Molina', '10000007-7', '0614-010101-107-7', '7000-1007', 'patricia.castro@mail.com', 'Apopa, Valle Verde', 0.77, 'Riesgo'),
('00000000008', 'Mauricio', 'Amaya Quintanilla', '10000008-8', '0614-010101-108-8', '7000-1008', 'mauricio.amaya@mail.com', 'Santa Tecla, Quezaltepec', 0.44, 'Masivo'),
('00000000009', 'Daniela', 'Mendez Sorto', '10000009-9', '0614-010101-109-9', '7000-1009', 'daniela.mendez@mail.com', 'La Libertad, Zaragoza', 0.28, 'Preferente'),
('00000000010', 'Oscar Rene', 'Vargas Alvarado', '10000010-0', '0614-010101-110-0', '7000-1010', 'oscar.vargas@mail.com', 'Sonsonate, Izalco', 0.61, 'Riesgo'),
('00000000011', 'Gabriela', 'Serrano Mejia', '10000011-1', '0614-010101-111-1', '7000-1011', 'gabriela.serrano@mail.com', 'San Vicente, Colonia Madrid', 0.36, 'Masivo'),
('00000000012', 'Ricardo', 'Calderon Ponce', '10000012-2', '0614-010101-112-2', '7000-1012', 'ricardo.calderon@mail.com', 'Usulutan, Puerto El Triunfo', 0.58, 'Masivo'),
('00000000013', 'Claudia', 'Reyes Diaz', '10000013-3', '0614-010101-113-3', '7000-1013', 'claudia.reyes@mail.com', 'San Salvador, Miralvalle', 0.19, 'Preferente'),
('00000000014', 'Nelson', 'Cruz Benitez', '10000014-4', '0614-010101-114-4', '7000-1014', 'nelson.cruz@mail.com', 'Santa Ana, Metapan', 0.73, 'Riesgo'),
('00000000015', 'Monica', 'Pena Solis', '10000015-5', '0614-010101-115-5', '7000-1015', 'monica.pena@mail.com', 'Cuscatancingo, San Luis Mariona', 0.53, 'Masivo'),
('00000000016', 'Ernesto', 'Melendez Castro', '10000016-6', '0614-010101-116-6', '7000-1016', 'ernesto.melendez@mail.com', 'Ahuachapan, Atiquizaya', 0.42, 'Masivo'),
('00000000017', 'Silvia', 'Arias Portillo', '10000017-7', '0614-010101-117-7', '7000-1017', 'silvia.arias@mail.com', 'La Paz, Olocuilta', 0.26, 'Preferente'),
('00000000018', 'Hector', 'Baires Mendoza', '10000018-8', '0614-010101-118-8', '7000-1018', 'hector.baires@mail.com', 'Morazan, San Francisco Gotera', 0.67, 'Riesgo'),
('00000000019', 'Andrea', 'Chavez Dubon', '10000019-9', '0614-010101-119-9', '7000-1019', 'andrea.chavez@mail.com', 'Chalatenango, Nueva Concepcion', 0.31, 'Preferente'),
('00000000020', 'Julio Cesar', 'Navarrete Rivas', '10000020-0', '0614-010101-120-0', '7000-1020', 'julio.navarrete@mail.com', 'Cabanas, Sensuntepeque', 0.64, 'Riesgo');

INSERT INTO cuentas (cliente_id, numero_cuenta, tipo_producto, subtipo_producto, saldo_capital, saldo_mora, saldo_total, dias_mora, bucket_actual, estado, fecha_apertura, fecha_vencimiento, tasa_interes, es_estrafinanciamiento) VALUES
(1, 'PRE-0001', 'Prestamo', 'Consumo', 1800.00, 125.00, 1925.00, 18, '0-30', 'ACTIVA', '2024-01-15', '2027-01-15', 14.50, FALSE),
(1, 'TAR-0001', 'Tarjeta', 'Clasica', 950.00, 80.00, 1030.00, 27, '0-30', 'ACTIVA', '2023-09-10', '2027-09-10', 29.90, FALSE),
(1, 'EST-0001', 'Tarjeta', 'Estrafinanciamiento', 600.00, 45.00, 645.00, 21, '0-30', 'ACTIVA', '2025-01-05', '2026-12-05', 24.00, TRUE),
(2, 'PRE-0002', 'Prestamo', 'Vehiculo', 7200.00, 540.00, 7740.00, 49, '31-60', 'ACTIVA', '2022-07-11', '2027-07-11', 11.75, FALSE),
(2, 'TAR-0002', 'Tarjeta', 'Oro', 2100.00, 260.00, 2360.00, 62, '61-90', 'ACTIVA', '2023-03-18', '2028-03-18', 31.20, FALSE),
(3, 'PRE-0003', 'Prestamo', 'Consumo', 1500.00, 75.00, 1575.00, 13, '0-30', 'ACTIVA', '2024-02-10', '2026-08-10', 16.40, FALSE),
(3, 'EST-0003', 'Tarjeta', 'Estrafinanciamiento', 450.00, 32.00, 482.00, 16, '0-30', 'ACTIVA', '2025-02-01', '2026-11-01', 23.50, TRUE),
(4, 'PRE-0004', 'Prestamo', 'Microcredito', 980.00, 190.00, 1170.00, 74, '61-90', 'ACTIVA', '2023-06-08', '2026-06-08', 18.60, FALSE),
(4, 'TAR-0004', 'Tarjeta', 'Clasica', 1300.00, 240.00, 1540.00, 88, '61-90', 'ACTIVA', '2022-11-25', '2027-11-25', 30.00, FALSE),
(5, 'PRE-0005', 'Prestamo', 'Hipotecario', 25500.00, 0.00, 25500.00, 0, '0-30', 'ACTIVA', '2021-04-20', '2041-04-20', 8.50, FALSE),
(5, 'TAR-0005', 'Tarjeta', 'Platinum', 3600.00, 120.00, 3720.00, 22, '0-30', 'ACTIVA', '2023-01-15', '2028-01-15', 27.50, FALSE),
(6, 'PRE-0006', 'Prestamo', 'Consumo', 4200.00, 390.00, 4590.00, 55, '31-60', 'ACTIVA', '2022-09-17', '2026-09-17', 15.40, FALSE),
(6, 'EST-0006', 'Tarjeta', 'Estrafinanciamiento', 980.00, 70.00, 1050.00, 37, '31-60', 'ACTIVA', '2024-11-11', '2026-10-11', 22.90, TRUE),
(7, 'PRE-0007', 'Prestamo', 'Microcredito', 650.00, 220.00, 870.00, 94, '91-120', 'ACTIVA', '2024-03-09', '2026-03-09', 19.75, FALSE),
(7, 'TAR-0007', 'Tarjeta', 'Clasica', 1450.00, 320.00, 1770.00, 110, '91-120', 'ACTIVA', '2023-02-12', '2027-02-12', 32.00, FALSE),
(8, 'PRE-0008', 'Prestamo', 'Consumo', 1950.00, 115.00, 2065.00, 24, '0-30', 'ACTIVA', '2024-06-01', '2027-06-01', 14.90, FALSE),
(8, 'EST-0008', 'Tarjeta', 'Estrafinanciamiento', 720.00, 58.00, 778.00, 29, '0-30', 'ACTIVA', '2025-01-23', '2026-12-23', 24.50, TRUE),
(9, 'PRE-0009', 'Prestamo', 'Vehiculo', 8300.00, 160.00, 8460.00, 18, '0-30', 'ACTIVA', '2021-10-05', '2028-10-05', 10.80, FALSE),
(9, 'TAR-0009', 'Tarjeta', 'Oro', 2750.00, 95.00, 2845.00, 15, '0-30', 'ACTIVA', '2022-12-19', '2027-12-19', 28.60, FALSE),
(10, 'PRE-0010', 'Prestamo', 'Consumo', 1180.00, 300.00, 1480.00, 72, '61-90', 'ACTIVA', '2023-07-02', '2026-07-02', 17.20, FALSE),
(10, 'EST-0010', 'Tarjeta', 'Estrafinanciamiento', 560.00, 90.00, 650.00, 67, '61-90', 'ACTIVA', '2025-02-14', '2026-11-14', 23.70, TRUE),
(11, 'PRE-0011', 'Prestamo', 'Consumo', 2050.00, 98.00, 2148.00, 19, '0-30', 'ACTIVA', '2024-01-09', '2027-01-09', 15.10, FALSE),
(11, 'TAR-0011', 'Tarjeta', 'Clasica', 980.00, 66.00, 1046.00, 17, '0-30', 'ACTIVA', '2023-06-20', '2028-06-20', 29.40, FALSE),
(12, 'PRE-0012', 'Prestamo', 'Vehiculo', 9100.00, 450.00, 9550.00, 43, '31-60', 'ACTIVA', '2022-04-04', '2029-04-04', 11.10, FALSE),
(12, 'TAR-0012', 'Tarjeta', 'Oro', 3200.00, 210.00, 3410.00, 39, '31-60', 'ACTIVA', '2023-08-08', '2028-08-08', 30.80, FALSE),
(13, 'PRE-0013', 'Prestamo', 'Consumo', 1350.00, 35.00, 1385.00, 7, '0-30', 'ACTIVA', '2024-10-10', '2027-10-10', 13.80, FALSE),
(13, 'EST-0013', 'Tarjeta', 'Estrafinanciamiento', 300.00, 12.00, 312.00, 5, '0-30', 'ACTIVA', '2025-01-30', '2026-10-30', 22.20, TRUE),
(14, 'PRE-0014', 'Prestamo', 'Microcredito', 760.00, 260.00, 1020.00, 101, '91-120', 'ACTIVA', '2023-09-27', '2026-09-27', 20.30, FALSE),
(14, 'TAR-0014', 'Tarjeta', 'Clasica', 1680.00, 355.00, 2035.00, 117, '121+', 'ACTIVA', '2022-05-13', '2027-05-13', 33.40, FALSE),
(15, 'PRE-0015', 'Prestamo', 'Consumo', 2600.00, 180.00, 2780.00, 29, '0-30', 'ACTIVA', '2024-03-01', '2027-03-01', 15.90, FALSE),
(15, 'TAR-0015', 'Tarjeta', 'Oro', 2280.00, 145.00, 2425.00, 26, '0-30', 'ACTIVA', '2023-07-14', '2028-07-14', 29.70, FALSE),
(16, 'PRE-0016', 'Prestamo', 'Consumo', 1740.00, 102.00, 1842.00, 21, '0-30', 'ACTIVA', '2024-04-16', '2027-04-16', 14.20, FALSE),
(16, 'EST-0016', 'Tarjeta', 'Estrafinanciamiento', 410.00, 22.00, 432.00, 11, '0-30', 'ACTIVA', '2025-03-01', '2026-12-01', 21.80, TRUE),
(17, 'PRE-0017', 'Prestamo', 'Hipotecario', 18500.00, 0.00, 18500.00, 0, '0-30', 'ACTIVA', '2020-12-12', '2040-12-12', 7.90, FALSE),
(17, 'TAR-0017', 'Tarjeta', 'Platinum', 4100.00, 80.00, 4180.00, 14, '0-30', 'ACTIVA', '2023-11-03', '2028-11-03', 26.90, FALSE),
(18, 'PRE-0018', 'Prestamo', 'Vehiculo', 6850.00, 910.00, 7760.00, 135, '121-150', 'ACTIVA', '2022-10-10', '2028-10-10', 12.40, FALSE),
(18, 'TAR-0018', 'Tarjeta', 'Clasica', 1580.00, 410.00, 1990.00, 168, '151-180', 'ACTIVA', '2023-09-09', '2028-09-09', 31.60, FALSE),
(19, 'PRE-0019', 'Prestamo', 'Consumo', 1120.00, 48.00, 1168.00, 10, '0-30', 'ACTIVA', '2024-08-22', '2026-08-22', 13.95, FALSE),
(19, 'EST-0019', 'Tarjeta', 'Estrafinanciamiento', 520.00, 18.00, 538.00, 9, '0-30', 'ACTIVA', '2025-02-05', '2026-11-05', 22.75, TRUE),
(20, 'PRE-0020', 'Prestamo', 'Microcredito', 890.00, 545.00, 1435.00, 205, '190+', 'VIGENTE', '2023-11-18', '2026-11-18', 18.90, FALSE),
(20, 'TAR-0020', 'Tarjeta', 'Oro', 2460.00, 520.00, 2980.00, 185, '181+', 'LIQUIDADO', '2022-06-26', '2027-06-26', 30.40, FALSE);

INSERT INTO bucket_historial (cuenta_id, bucket_anterior, bucket_nuevo, motivo) VALUES
(2, '0-30', '31-60', 'Aumento de mora mensual'),
(5, '31-60', '61-90', 'Incumplimiento de pago minimo'),
(15, '61-90', '91-120', 'Promesa incumplida'),
(28, '91-120', '121+', 'Escalada critica'),
(40, '31-60', '61-90', 'Persistencia de mora');

INSERT INTO pagos (cuenta_id, monto, fecha_pago, canal, referencia, observacion) VALUES
(1, 120.00, CURRENT_TIMESTAMP - INTERVAL '15 day', 'agencia', 'PAG-0001', 'Pago parcial'),
(2, 95.00, CURRENT_TIMESTAMP - INTERVAL '10 day', 'app', 'PAG-0002', 'Pago minimo'),
(3, 60.00, CURRENT_TIMESTAMP - INTERVAL '8 day', 'call center', 'PAG-0003', 'Abono estrafinanciamiento'),
(4, 300.00, CURRENT_TIMESTAMP - INTERVAL '28 day', 'agencia', 'PAG-0004', 'Regularizacion parcial'),
(6, 110.00, CURRENT_TIMESTAMP - INTERVAL '7 day', 'app', 'PAG-0005', 'Pago de consumo'),
(8, 75.00, CURRENT_TIMESTAMP - INTERVAL '13 day', 'digital', 'PAG-0006', 'Pago mixto'),
(10, 420.00, CURRENT_TIMESTAMP - INTERVAL '40 day', 'agencia', 'PAG-0007', 'Abono extraordinario'),
(12, 210.00, CURRENT_TIMESTAMP - INTERVAL '16 day', 'call center', 'PAG-0008', 'Pago programado'),
(16, 145.00, CURRENT_TIMESTAMP - INTERVAL '6 day', 'app', 'PAG-0009', 'Pago por enlace'),
(18, 180.00, CURRENT_TIMESTAMP - INTERVAL '9 day', 'agencia', 'PAG-0010', 'Pago de tarjeta'),
(21, 130.00, CURRENT_TIMESTAMP - INTERVAL '12 day', 'digital', 'PAG-0011', 'Abono normal'),
(24, 320.00, CURRENT_TIMESTAMP - INTERVAL '20 day', 'agencia', 'PAG-0012', 'Pago de vehiculo'),
(27, 85.00, CURRENT_TIMESTAMP - INTERVAL '5 day', 'app', 'PAG-0013', 'Pago reciente'),
(31, 140.00, CURRENT_TIMESTAMP - INTERVAL '11 day', 'app', 'PAG-0014', 'Pago recurrente'),
(34, 200.00, CURRENT_TIMESTAMP - INTERVAL '14 day', 'agencia', 'PAG-0015', 'Pago cliente preferente'),
(37, 155.00, CURRENT_TIMESTAMP - INTERVAL '18 day', 'call center', 'PAG-0016', 'Pago compromiso'),
(39, 90.00, CURRENT_TIMESTAMP - INTERVAL '4 day', 'digital', 'PAG-0017', 'Pago estrafinan'),
(40, 270.00, CURRENT_TIMESTAMP - INTERVAL '27 day', 'agencia', 'PAG-0018', 'Pago recuperacion');

INSERT INTO promesas (cuenta_id, usuario_id, fecha_promesa, monto_prometido, estado) VALUES
(4, 4, CURRENT_DATE + INTERVAL '5 day', 250.00, 'PENDIENTE'),
(8, 5, CURRENT_DATE + INTERVAL '2 day', 120.00, 'PENDIENTE'),
(15, 6, CURRENT_DATE + INTERVAL '1 day', 300.00, 'VENCIDA'),
(24, 7, CURRENT_DATE + INTERVAL '7 day', 500.00, 'PENDIENTE'),
(30, 16, CURRENT_DATE + INTERVAL '3 day', 180.00, 'PENDIENTE');

INSERT INTO campanas (nombre, estrategia, segmento_objetivo, fecha_inicio, fecha_fin, estado) VALUES
('Campana Reactivacion 0-30', 'SMS + WhatsApp', 'Preferente', CURRENT_DATE - INTERVAL '10 day', CURRENT_DATE + INTERVAL '20 day', 'ACTIVA'),
('Campana Mora Temprana', 'Llamada y autogestion', 'Masivo', CURRENT_DATE - INTERVAL '5 day', CURRENT_DATE + INTERVAL '25 day', 'ACTIVA'),
('Campana Recuperacion Intensiva', 'Supervisor + visita', 'Riesgo', CURRENT_DATE - INTERVAL '2 day', CURRENT_DATE + INTERVAL '30 day', 'ACTIVA');

INSERT INTO history (entidad, entidad_id, accion, descripcion, usuario_id) VALUES
('cuentas', 2, 'UPDATE_BUCKET', 'Cambio de bucket a 31-60', 2),
('pagos', 5, 'REGISTER_PAYMENT', 'Se registro pago digital', 4),
('promesas', 3, 'PROMISE_BROKEN', 'Promesa vencida sin pago', 6),
('campanas', 2, 'CAMPAIGN_START', 'Inicio de campana de mora temprana', 1),
('usuarios', 12, 'USER_CREATED', 'Alta de gestor de usuarios', 1);

INSERT INTO history (entidad, entidad_id, accion, descripcion, usuario_id, created_at)
SELECT
    'clientes',
    c.id,
    CASE seq.paso
        WHEN 1 THEN 'GESTION_REGISTRADA'
        WHEN 2 THEN 'SMS_ENVIADO'
        WHEN 3 THEN 'PROMESA_CREADA'
        WHEN 4 THEN 'GESTION_REGISTRADA'
        WHEN 5 THEN 'CLIENTE_ACTUALIZADO'
        ELSE 'WHATSAPP_ENVIADO'
    END,
    CASE seq.paso
        WHEN 1 THEN 'Llamada de bienvenida de mora. Cliente indica limitante temporal de flujo.'
        WHEN 2 THEN 'Se envio recordatorio preventivo con detalle de saldo y fecha sugerida de pago.'
        WHEN 3 THEN 'Cliente manifesto intencion de pago parcial y solicito seguimiento en su jornada laboral.'
        WHEN 4 THEN 'Gestion de seguimiento para validar fuente de pago y disponibilidad de fondos.'
        WHEN 5 THEN 'Se actualizaron telefono alterno, correo y referencia de direccion residencial.'
        ELSE 'Mensaje omnicanal enviado con ruta de autogestion y canales de contacto.'
    END,
    (
        SELECT u.id
        FROM usuarios u
        WHERE u.username = 'collector' || (((c.id - 1) % 9) + 1)::text
    ),
    CURRENT_TIMESTAMP - (((c.id + seq.paso) % 75) * INTERVAL '1 day') - (seq.paso * INTERVAL '2 hour')
FROM clientes c
CROSS JOIN generate_series(1, 6) AS seq(paso)
WHERE c.id BETWEEN 21 AND 50000;

INSERT INTO predicciones_ia (cuenta_id, probabilidad_pago_30d, score_modelo, modelo_version, recomendacion) VALUES
(1, 0.8120, 81.20, 'xgb-v1', 'Priorizar recordatorio digital.'),
(4, 0.3940, 39.40, 'xgb-v1', 'Escalar a llamada del supervisor.'),
(15, 0.2210, 22.10, 'xgb-v1', 'Aplicar gestion intensiva.'),
(21, 0.7740, 77.40, 'xgb-v1', 'Mantener seguimiento semanal.'),
(40, 0.3180, 31.80, 'xgb-v1', 'Coordinar plan de recuperacion.');

WITH fn AS (
    SELECT ARRAY['Carlos','Mariela','Sonia','Rene','Diego','Gabriela','Patricia','Oscar','Julio','Andrea','Mario','Karla','Fernanda','Ricardo','Silvia','Hector','Diana','Jorge','Melissa','Adriana'] AS arr
),
ln AS (
    SELECT ARRAY['Martinez','Hernandez','Lopez','Ramirez','Vargas','Mendez','Guardado','Pineda','Castro','Reyes','Arias','Torres','Portillo','Flores','Calderon','Benitez','Navarrete','Chavez','Salazar','Amaya'] AS arr
),
mn AS (
    SELECT ARRAY['Alberto','Lucia','Elena','Daniel','Sofia','Mauricio','Ernesto','Natalia','Samuel','Valeria','Manuel','Paola','Camila','Rafael','Cecilia','Nelson','Tatiana','Rolando','Claudia','Miguel'] AS arr
)
INSERT INTO clientes (identity_code, nombres, apellidos, dui, nit, telefono, email, direccion, score_riesgo, segmento)
SELECT
    LPAD(gs::text, 11, '0'),
    (SELECT arr[(gs % 20) + 1] FROM fn) || ' ' || (SELECT arr[((gs + 7) % 20) + 1] FROM mn),
    (SELECT arr[((gs + 3) % 20) + 1] FROM ln) || ' ' || (SELECT arr[((gs + 11) % 20) + 1] FROM ln),
    '2' || LPAD(gs::text, 7, '0') || '-' || (gs % 10),
    '0614-' || LPAD(gs::text, 6, '0') || '-' || LPAD((100 + gs)::text, 3, '0') || '-' || (gs % 10),
    '7' || LPAD((5000000 + gs)::text, 7, '0'),
    'cliente' || gs || '@demo360collectplus.com',
    CASE
        WHEN gs % 5 = 0 THEN 'San Salvador, Colonia Medica, Pasaje ' || gs
        WHEN gs % 5 = 1 THEN 'Santa Ana, Barrio San Rafael, Casa ' || gs
        WHEN gs % 5 = 2 THEN 'San Miguel, Residencial El Sitio, Poligono ' || gs
        WHEN gs % 5 = 3 THEN 'Soyapango, Colonia Guadalupe, Avenida ' || gs
        ELSE 'Santa Tecla, Urbanizacion Las Delicias, Calle ' || gs
    END,
    ROUND(((gs % 100) / 100.0)::numeric, 2),
    CASE
        WHEN gs % 4 = 0 THEN 'Preferente'
        WHEN gs % 4 = 1 THEN 'Masivo'
        WHEN gs % 4 = 2 THEN 'Riesgo'
        ELSE 'Recuperacion'
    END
FROM generate_series(21, 50000) AS gs
WHERE NOT EXISTS (SELECT 1 FROM clientes WHERE identity_code = LPAD(gs::text, 11, '0'));

INSERT INTO cuentas (cliente_id, numero_cuenta, tipo_producto, subtipo_producto, saldo_capital, saldo_mora, saldo_total, dias_mora, bucket_actual, estado, fecha_apertura, fecha_vencimiento, tasa_interes, es_estrafinanciamiento)
SELECT
    c.id,
    CASE WHEN idx = 1 THEN 'PRE-' ELSE 'TAR-' END || LPAD(c.id::text, 5, '0'),
    CASE WHEN idx = 1 THEN 'Prestamo' ELSE 'Tarjeta' END,
    CASE
        WHEN idx = 1 THEN CASE WHEN c.id % 3 = 0 THEN 'Consumo' WHEN c.id % 3 = 1 THEN 'Vehiculo' ELSE 'Microcredito' END
        ELSE CASE WHEN c.id % 4 = 0 THEN 'Clasica' WHEN c.id % 4 = 1 THEN 'Oro' WHEN c.id % 4 = 2 THEN 'Platinum' ELSE 'Estrafinanciamiento' END
    END,
    ROUND((600 + (c.id % 50) * 95 + idx * 75)::numeric, 2),
    ROUND(
        CASE (c.id % 10)
            WHEN 0 THEN 0
            WHEN 1 THEN 45
            WHEN 2 THEN 125
            WHEN 3 THEN 230
            WHEN 4 THEN 330
            WHEN 5 THEN 430
            WHEN 6 THEN 560
            WHEN 7 THEN 710
            WHEN 8 THEN 930
            ELSE 680
        END + idx * 12
    , 2),
    ROUND((600 + (c.id % 50) * 95 + idx * 75)::numeric +
        (
            CASE (c.id % 10)
                WHEN 0 THEN 0
                WHEN 1 THEN 45
                WHEN 2 THEN 125
                WHEN 3 THEN 230
                WHEN 4 THEN 330
                WHEN 5 THEN 430
                WHEN 6 THEN 560
                WHEN 7 THEN 710
                WHEN 8 THEN 930
                ELSE 680
            END + idx * 12
        ), 2),
    CASE (c.id % 10)
        WHEN 0 THEN 0
        WHEN 1 THEN 12
        WHEN 2 THEN 25
        WHEN 3 THEN 48
        WHEN 4 THEN 75
        WHEN 5 THEN 105
        WHEN 6 THEN 138
        WHEN 7 THEN 165
        WHEN 8 THEN 205
        ELSE 185
    END,
    CASE
        WHEN (c.id % 10) IN (0,1,2) THEN '0-30'
        WHEN (c.id % 10) = 3 THEN '31-60'
        WHEN (c.id % 10) = 4 THEN '61-90'
        WHEN (c.id % 10) = 5 THEN '91-120'
        WHEN (c.id % 10) = 6 THEN '121-150'
        WHEN (c.id % 10) = 7 THEN '151-180'
        ELSE '181+'
    END,
    CASE
        WHEN (c.id % 10) = 8 THEN 'VIGENTE'
        WHEN (c.id % 10) = 9 THEN 'LIQUIDADO'
        ELSE 'ACTIVA'
    END,
    CURRENT_DATE - ((c.id % 900) || ' days')::interval,
    CURRENT_DATE + (((c.id % 720) + 120) || ' days')::interval,
    CASE WHEN idx = 1 THEN 14.50 ELSE 29.90 END + ((c.id % 7) * 0.35),
    CASE WHEN idx = 2 AND (c.id % 4) = 3 THEN TRUE ELSE FALSE END
FROM clientes c
CROSS JOIN generate_series(1, 2) AS idx
WHERE c.id >= 21
AND NOT EXISTS (
    SELECT 1
    FROM cuentas existing
    WHERE existing.numero_cuenta = (CASE WHEN idx = 1 THEN 'PRE-' ELSE 'TAR-' END || LPAD(c.id::text, 5, '0'))
);

WITH client_profiles AS (
    SELECT
        c.id AS cliente_id,
        (c.id % 3) AS profile_group,
        CASE (c.id % 10)
            WHEN 0 THEN 0
            WHEN 1 THEN 14
            WHEN 2 THEN 27
            WHEN 3 THEN 46
            WHEN 4 THEN 74
            WHEN 5 THEN 103
            WHEN 6 THEN 136
            WHEN 7 THEN 168
            WHEN 8 THEN 205
            ELSE 186
        END AS head_days
    FROM clientes c
    WHERE c.id >= 21
),
account_targets AS (
    SELECT
        q.id,
        cp.cliente_id,
        cp.profile_group,
        cp.head_days,
        CASE
            WHEN cp.profile_group IN (0, 1) AND q.numero_cuenta LIKE 'PRE-%' THEN 'Prestamo'
            ELSE 'Tarjeta'
        END AS target_tipo,
        CASE
            WHEN cp.profile_group = 0 AND q.numero_cuenta LIKE 'PRE-%' THEN 'Hipotecario'
            WHEN cp.profile_group = 0 AND q.numero_cuenta LIKE 'TAR-%' THEN CASE WHEN cp.cliente_id % 4 = 0 THEN 'Platinum' ELSE 'Oro' END
            WHEN cp.profile_group = 1 AND q.numero_cuenta LIKE 'PRE-%' THEN 'PIL'
            WHEN cp.profile_group = 1 AND q.numero_cuenta LIKE 'TAR-%' THEN CASE WHEN cp.cliente_id % 2 = 0 THEN 'Gold' ELSE 'Clasica' END
            WHEN cp.profile_group = 2 AND q.numero_cuenta LIKE 'PRE-%' THEN 'Clasica'
            ELSE CASE
                WHEN cp.cliente_id % 4 = 0 THEN 'Platinum'
                WHEN cp.cliente_id % 4 = 1 THEN 'Oro'
                WHEN cp.cliente_id % 4 = 2 THEN 'Gold'
                ELSE 'Estrafinanciamiento'
            END
        END AS target_subtipo,
        CASE
            WHEN cp.profile_group IN (0, 1) AND q.numero_cuenta LIKE 'PRE-%' THEN cp.head_days
            WHEN cp.profile_group = 2 AND q.numero_cuenta LIKE 'TAR-%' THEN cp.head_days
            WHEN cp.profile_group = 0 AND q.numero_cuenta LIKE 'TAR-%' THEN GREATEST(cp.head_days - (12 + (cp.cliente_id % 11)), 0)
            WHEN cp.profile_group = 1 AND q.numero_cuenta LIKE 'TAR-%' THEN GREATEST(cp.head_days - (9 + (cp.cliente_id % 13)), 0)
            ELSE GREATEST(cp.head_days - (17 + (cp.cliente_id % 9)), 0)
        END AS target_days
    FROM cuentas q
    JOIN client_profiles cp ON cp.cliente_id = q.cliente_id
    WHERE q.cliente_id >= 21
)
UPDATE cuentas q
SET
    tipo_producto = account_targets.target_tipo,
    subtipo_producto = account_targets.target_subtipo,
    dias_mora = account_targets.target_days,
    bucket_actual = CASE
        WHEN account_targets.target_days <= 30 THEN '0-30'
        WHEN account_targets.target_days <= 60 THEN '31-60'
        WHEN account_targets.target_days <= 90 THEN '61-90'
        WHEN account_targets.target_days <= 120 THEN '91-120'
        WHEN account_targets.target_days <= 150 THEN '121-150'
        WHEN account_targets.target_days <= 180 THEN '151-180'
        ELSE '181+'
    END,
    estado = CASE
        WHEN account_targets.target_days > 180
            AND (
                (account_targets.profile_group IN (0, 1) AND q.numero_cuenta LIKE 'PRE-%')
                OR (account_targets.profile_group = 2 AND q.numero_cuenta LIKE 'TAR-%')
            )
            AND (account_targets.cliente_id % 10) = 9 THEN 'LIQUIDADO'
        WHEN account_targets.target_days > 190
            AND (
                (account_targets.profile_group IN (0, 1) AND q.numero_cuenta LIKE 'PRE-%')
                OR (account_targets.profile_group = 2 AND q.numero_cuenta LIKE 'TAR-%')
            )
            AND (account_targets.cliente_id % 10) = 8 THEN 'VIGENTE'
        ELSE 'ACTIVA'
    END,
    saldo_mora = ROUND(
        CASE
            WHEN account_targets.target_days <= 0 THEN 0
            ELSE ((account_targets.target_days + 1) * CASE WHEN account_targets.target_tipo = 'Tarjeta' THEN 4.20 ELSE 5.35 END) + ((q.id % 17) * 6)
        END
    , 2),
    saldo_total = ROUND(
        q.saldo_capital + CASE
            WHEN account_targets.target_days <= 0 THEN 0
            ELSE ((account_targets.target_days + 1) * CASE WHEN account_targets.target_tipo = 'Tarjeta' THEN 4.20 ELSE 5.35 END) + ((q.id % 17) * 6)
        END
    , 2),
    es_estrafinanciamiento = (account_targets.target_subtipo = 'Estrafinanciamiento')
FROM account_targets
WHERE q.id = account_targets.id;

WITH client_profiles AS (
    SELECT
        c.id AS cliente_id,
        (c.id % 3) AS profile_group,
        CASE (c.id % 10)
            WHEN 0 THEN 0
            WHEN 1 THEN 14
            WHEN 2 THEN 27
            WHEN 3 THEN 46
            WHEN 4 THEN 74
            WHEN 5 THEN 103
            WHEN 6 THEN 136
            WHEN 7 THEN 168
            WHEN 8 THEN 205
            ELSE 186
        END AS head_days
    FROM clientes c
    WHERE c.id >= 21
)
INSERT INTO cuentas (cliente_id, numero_cuenta, tipo_producto, subtipo_producto, saldo_capital, saldo_mora, saldo_total, dias_mora, bucket_actual, estado, fecha_apertura, fecha_vencimiento, tasa_interes, es_estrafinanciamiento)
SELECT
    cp.cliente_id,
    CASE
        WHEN cp.profile_group = 0 THEN 'PIL-' || LPAD(cp.cliente_id::text, 5, '0')
        WHEN cp.profile_group = 1 THEN 'TC2-' || LPAD(cp.cliente_id::text, 5, '0')
        ELSE 'TPL-' || LPAD(cp.cliente_id::text, 5, '0')
    END,
    CASE WHEN cp.profile_group = 0 THEN 'Prestamo' ELSE 'Tarjeta' END,
    CASE
        WHEN cp.profile_group = 0 THEN 'PIL'
        WHEN cp.profile_group = 1 THEN 'Clasica'
        WHEN cp.cliente_id % 2 = 0 THEN 'Platinum'
        ELSE 'Estrafinanciamiento'
    END,
    ROUND((850 + (cp.cliente_id % 45) * 52)::numeric, 2),
    ROUND(
        CASE
            WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 0 THEN 0
            ELSE ((GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) + 1) * CASE WHEN cp.profile_group = 0 THEN 5.10 ELSE 4.05 END) + ((cp.cliente_id % 13) * 5)
        END
    , 2),
    ROUND(
        (850 + (cp.cliente_id % 45) * 52)::numeric +
        CASE
            WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 0 THEN 0
            ELSE ((GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) + 1) * CASE WHEN cp.profile_group = 0 THEN 5.10 ELSE 4.05 END) + ((cp.cliente_id % 13) * 5)
        END
    , 2),
    GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0),
    CASE
        WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 30 THEN '0-30'
        WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 60 THEN '31-60'
        WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 90 THEN '61-90'
        WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 120 THEN '91-120'
        WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 150 THEN '121-150'
        WHEN GREATEST(cp.head_days - (22 + (cp.cliente_id % 9)), 0) <= 180 THEN '151-180'
        ELSE '181+'
    END,
    'ACTIVA',
    CURRENT_DATE - ((cp.cliente_id % 740) || ' days')::interval,
    CURRENT_DATE + (((cp.cliente_id % 680) + 180) || ' days')::interval,
    CASE WHEN cp.profile_group = 0 THEN 15.75 ELSE 28.40 END + ((cp.cliente_id % 6) * 0.45),
    CASE WHEN cp.profile_group = 2 AND cp.cliente_id % 2 = 1 THEN TRUE ELSE FALSE END
FROM client_profiles cp
WHERE NOT EXISTS (
    SELECT 1
    FROM cuentas existing
    WHERE existing.numero_cuenta = CASE
        WHEN cp.profile_group = 0 THEN 'PIL-' || LPAD(cp.cliente_id::text, 5, '0')
        WHEN cp.profile_group = 1 THEN 'TC2-' || LPAD(cp.cliente_id::text, 5, '0')
        ELSE 'TPL-' || LPAD(cp.cliente_id::text, 5, '0')
    END
);

INSERT INTO asignaciones_cartera (usuario_id, cliente_id, estrategia_codigo, activa)
SELECT
    collector.id,
    c.id,
    NULL,
    TRUE
FROM clientes c
JOIN LATERAL (
    SELECT u.id
    FROM usuarios u
    WHERE u.rol = 'Collector'
    ORDER BY u.id
    OFFSET ((c.id - 1) % GREATEST((SELECT COUNT(*) FROM usuarios WHERE rol = 'Collector'), 1))
    LIMIT 1
) AS collector ON TRUE
WHERE NOT EXISTS (
    SELECT 1
    FROM asignaciones_cartera ac
    WHERE ac.cliente_id = c.id AND ac.activa = TRUE
);

UPDATE asignaciones_cartera ac
SET estrategia_codigo = derived.strategy_code
FROM (
    SELECT
        ac_inner.id AS assignment_id,
        CASE
            WHEN MAX(CASE WHEN q.estado IN ('LIQUIDADO', 'Z') AND q.dias_mora > 180 THEN 1 ELSE 0 END) = 1 THEN 'VAGENCIASEXTERNASINTERNO'
            WHEN MAX(q.dias_mora) > 190 AND MAX(CASE WHEN q.estado IN ('VIGENTE', 'ACTIVA') THEN 1 ELSE 0 END) = 1 THEN 'DMORA7'
            WHEN MAX(q.dias_mora) BETWEEN 151 AND 180 THEN 'CMORA6'
            WHEN MAX(q.dias_mora) BETWEEN 121 AND 150 THEN 'BMORA5'
            WHEN MAX(q.dias_mora) BETWEEN 91 AND 120 THEN 'AMORA4'
            WHEN MAX(q.dias_mora) BETWEEN 61 AND 90 THEN 'HMORA3'
            WHEN MAX(q.dias_mora) BETWEEN 31 AND 60 THEN 'MMORA2'
            WHEN MAX(q.dias_mora) BETWEEN 1 AND 30 THEN 'FMORA1'
            ELSE 'AL_DIA'
        END AS strategy_code
    FROM asignaciones_cartera ac_inner
    JOIN cuentas q ON q.cliente_id = ac_inner.cliente_id
    WHERE ac_inner.activa = TRUE
    GROUP BY ac_inner.id
) AS derived
WHERE ac.id = derived.assignment_id;

INSERT INTO assignment_history (
    cliente_id, usuario_id, assignment_id, strategy_code, placement_code, channel_scope, group_id,
    sublista_codigo, assigned_share_pct, efficiency_pct, tenure_days, minimum_payment_to_progress,
    segment_snapshot, account_status_snapshot, max_days_past_due_snapshot, total_due_snapshot,
    notes, start_at, is_current
)
SELECT
    ac.cliente_id,
    ac.usuario_id,
    ac.id,
    COALESCE(ac.estrategia_codigo,
        CASE
            WHEN MAX(CASE WHEN q.estado IN ('LIQUIDADO', 'Z') AND q.dias_mora > 180 THEN 1 ELSE 0 END) = 1 THEN 'VAGENCIASEXTERNASINTERNO'
            WHEN MAX(q.dias_mora) > 190 AND MAX(CASE WHEN q.estado IN ('VIGENTE', 'ACTIVA') THEN 1 ELSE 0 END) = 1 THEN 'DMORA7'
            WHEN MAX(q.dias_mora) BETWEEN 151 AND 180 THEN 'CMORA6'
            WHEN MAX(q.dias_mora) BETWEEN 121 AND 150 THEN 'BMORA5'
            WHEN MAX(q.dias_mora) BETWEEN 91 AND 120 THEN 'AMORA4'
            WHEN MAX(q.dias_mora) BETWEEN 61 AND 90 THEN 'HMORA3'
            WHEN MAX(q.dias_mora) BETWEEN 31 AND 60 THEN 'MMORA2'
            WHEN MAX(q.dias_mora) BETWEEN 1 AND 30 THEN 'FMORA1'
            ELSE 'AL_DIA'
        END
    ),
    CASE
        WHEN MAX(CASE WHEN q.estado IN ('LIQUIDADO', 'Z') AND q.dias_mora > 180 THEN 1 ELSE 0 END) = 1 THEN 'V11'
        ELSE NULL
    END,
    CASE
        WHEN MAX(CASE WHEN q.estado IN ('LIQUIDADO', 'Z') AND q.dias_mora > 180 THEN 1 ELSE 0 END) = 1 THEN 'INTERNO'
        ELSE NULL
    END,
    CASE
        WHEN MAX(CASE WHEN q.estado IN ('LIQUIDADO', 'Z') AND q.dias_mora > 180 THEN 1 ELSE 0 END) = 1 THEN 'V11INT01'
        ELSE UPPER(u.username)
    END,
    CASE
        WHEN SUM(q.saldo_mora) <= 175 THEN 'F02SALDOSBAJOS'
        WHEN MAX(q.dias_mora) >= 151 THEN 'ALTOIMP'
        ELSE 'QALDIA'
    END,
    CASE
        WHEN MAX(CASE WHEN q.estado IN ('LIQUIDADO', 'Z') AND q.dias_mora > 180 THEN 1 ELSE 0 END) = 1 THEN 20
        ELSE NULL
    END,
    NULL,
    120,
    10,
    c.segmento,
    MAX(q.estado),
    MAX(q.dias_mora),
    SUM(q.saldo_mora),
    'Carga inicial de asignación para trazabilidad histórica.',
    CURRENT_TIMESTAMP - ((c.id % 45) || ' days')::interval,
    TRUE
FROM asignaciones_cartera ac
JOIN clientes c ON c.id = ac.cliente_id
JOIN usuarios u ON u.id = ac.usuario_id
JOIN cuentas q ON q.cliente_id = c.id
WHERE NOT EXISTS (
    SELECT 1 FROM assignment_history ah WHERE ah.assignment_id = ac.id
)
GROUP BY ac.id, ac.cliente_id, ac.usuario_id, ac.estrategia_codigo, c.id, c.segmento, u.username;

INSERT INTO history (entidad, entidad_id, accion, descripcion, usuario_id, created_at)
SELECT
    'clientes',
    c.id,
    CASE seq.paso
        WHEN 1 THEN 'GESTION_REGISTRADA'
        WHEN 2 THEN 'SMS_ENVIADO'
        WHEN 3 THEN 'PROMESA_CREADA'
        WHEN 4 THEN 'GESTION_REGISTRADA'
        WHEN 5 THEN 'CLIENTE_ACTUALIZADO'
        ELSE 'WHATSAPP_ENVIADO'
    END,
    CASE seq.paso
        WHEN 1 THEN 'Llamada de bienvenida de mora. Cliente indica limitante temporal de flujo.'
        WHEN 2 THEN 'Se envio recordatorio preventivo con detalle de saldo y fecha sugerida de pago.'
        WHEN 3 THEN 'Cliente manifesto intencion de pago parcial y solicito seguimiento en su jornada laboral.'
        WHEN 4 THEN 'Gestion de seguimiento para validar fuente de pago y disponibilidad de fondos.'
        WHEN 5 THEN 'Se actualizaron telefono alterno, correo y referencia de direccion residencial.'
        ELSE 'Mensaje omnicanal enviado con ruta de autogestion y canales de contacto.'
    END,
    collector.id,
    CURRENT_TIMESTAMP - (((c.id + seq.paso) % 75) * INTERVAL '1 day') - (seq.paso * INTERVAL '2 hour')
FROM clientes c
JOIN LATERAL (
    SELECT u.id
    FROM usuarios u
    WHERE u.rol = 'Collector'
    ORDER BY u.id
    OFFSET ((c.id - 1) % GREATEST((SELECT COUNT(*) FROM usuarios WHERE rol = 'Collector'), 1))
    LIMIT 1
) AS collector ON TRUE
CROSS JOIN generate_series(1, 6) AS seq(paso)
WHERE NOT EXISTS (
    SELECT 1
    FROM history h
    WHERE h.entidad = 'clientes'
      AND h.entidad_id = c.id
);

INSERT INTO bucket_historial (cuenta_id, bucket_anterior, bucket_nuevo, fecha_cambio, motivo)
SELECT
    q.id,
    CASE
        WHEN q.dias_mora <= 30 THEN 'PREVENTIVO'
        WHEN q.dias_mora <= 60 THEN 'FMORA1'
        WHEN q.dias_mora <= 90 THEN 'MMORA2'
        WHEN q.dias_mora <= 120 THEN 'HMORA3'
        WHEN q.dias_mora <= 150 THEN 'AMORA4'
        WHEN q.dias_mora <= 180 THEN 'BMORA5'
        ELSE 'CMORA6'
    END,
    CASE
        WHEN q.dias_mora <= 30 THEN 'FMORA1'
        WHEN q.dias_mora <= 60 THEN 'MMORA2'
        WHEN q.dias_mora <= 90 THEN 'HMORA3'
        WHEN q.dias_mora <= 120 THEN 'AMORA4'
        WHEN q.dias_mora <= 150 THEN 'BMORA5'
        WHEN q.dias_mora <= 180 THEN 'CMORA6'
        ELSE 'DMORA7'
    END,
    CURRENT_TIMESTAMP - (((q.id % 180) + 8) || ' days')::interval,
    'Migracion automatica por incremento de mora'
FROM cuentas q
WHERE q.id > 40
AND NOT EXISTS (
    SELECT 1
    FROM bucket_historial bh
    WHERE bh.cuenta_id = q.id
);

INSERT INTO pagos (cuenta_id, monto, fecha_pago, canal, referencia, observacion)
SELECT
    q.id,
    ROUND(GREATEST(35.00, LEAST(q.saldo_total, q.saldo_mora * (0.45 + ((q.id % 4) * 0.08))))::numeric, 2),
    CURRENT_TIMESTAMP - (((q.id % 75) + 1) || ' days')::interval,
    CASE (q.id % 4)
        WHEN 0 THEN 'Caja'
        WHEN 1 THEN 'Transferencia'
        WHEN 2 THEN 'App movil'
        ELSE 'Banca web'
    END,
    'PAY-' || q.id || '-' || LPAD((2000 + (q.id % 7000))::text, 6, '0'),
    'Pago parcial de demo para recuperar cartera y alimentar indicadores.'
FROM cuentas q
WHERE q.id > 40
AND q.id % 3 = 0
AND NOT EXISTS (
    SELECT 1
    FROM pagos p
    WHERE p.cuenta_id = q.id
);

INSERT INTO promesas (cuenta_id, usuario_id, fecha_promesa, monto_prometido, estado)
SELECT
    q.id,
    (
        SELECT u.id
        FROM usuarios u
        WHERE u.rol = 'Collector'
        ORDER BY u.id
        OFFSET ((q.cliente_id - 1) % GREATEST((SELECT COUNT(*) FROM usuarios WHERE rol = 'Collector'), 1))
        LIMIT 1
    ),
    CURRENT_DATE + ((q.id % 9) + 1),
    ROUND(GREATEST(40.00, q.saldo_mora * (0.50 + ((q.id % 3) * 0.10)))::numeric, 2),
    CASE
        WHEN q.id % 10 = 0 THEN 'REVISION_SUPERVISOR'
        WHEN q.id % 7 = 0 THEN 'VENCIDA'
        ELSE 'PENDIENTE'
    END
FROM cuentas q
WHERE q.id > 40
AND q.dias_mora > 0
AND q.id % 2 = 0
AND NOT EXISTS (
    SELECT 1
    FROM promesas p
    WHERE p.cuenta_id = q.id
);

INSERT INTO predicciones_ia (cuenta_id, probabilidad_pago_30d, score_modelo, modelo_version, recomendacion)
SELECT
    q.id,
    ROUND(
        GREATEST(
            0.09,
            LEAST(
                0.96,
                0.88
                - (q.dias_mora / 320.0)
                + CASE WHEN q.estado IN ('ACTIVA', 'VIGENTE') THEN 0.04 ELSE -0.06 END
                + CASE WHEN q.es_estrafinanciamiento THEN -0.05 ELSE 0.01 END
            )
        )::numeric,
        4
    ),
    ROUND(
        (
            GREATEST(
                0.09,
                LEAST(
                    0.96,
                    0.88
                    - (q.dias_mora / 320.0)
                    + CASE WHEN q.estado IN ('ACTIVA', 'VIGENTE') THEN 0.04 ELSE -0.06 END
                    + CASE WHEN q.es_estrafinanciamiento THEN -0.05 ELSE 0.01 END
                )
            ) * 100
        )::numeric,
        2
    ),
    'xgb-v2-demo',
    CASE
        WHEN q.dias_mora <= 30 THEN 'Priorizar preventivo, recordatorio digital y llamada corta.'
        WHEN q.dias_mora <= 90 THEN 'Gestion telefonica con control de promesa y seguimiento 48h.'
        WHEN q.dias_mora <= 180 THEN 'Escalar estrategia intensiva y evaluar HMR.'
        ELSE 'Mantener recuperacion intensiva con supervisor y canal externo.'
    END
FROM cuentas q
WHERE q.id > 40
AND NOT EXISTS (
    SELECT 1
    FROM predicciones_ia pi
    WHERE pi.cuenta_id = q.id
);
