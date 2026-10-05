-- ============================================================
-- CREACIÓN DE BASE DE DATOS COMPLETA - MEDCONTROL PRO / HDAC
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'HDAC_Hospital_DB')
BEGIN
    CREATE DATABASE HDAC_Hospital_DB;
END
GO

USE HDAC_Hospital_DB;
GO

-- ============================================================
-- 1. ROLES Y USUARIOS DEL SISTEMA
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Roles')
CREATE TABLE Roles (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Usuarios')
CREATE TABLE Usuarios (
    id INT IDENTITY(1,1) PRIMARY KEY,
    usuario VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(120) NOT NULL,
    email VARCHAR(100) UNIQUE,
    rol_id INT FOREIGN KEY REFERENCES Roles(id),
    activo BIT DEFAULT 1,
    fecha_creacion DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- 2. MÓDULO: PACIENTES
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Pacientes')
CREATE TABLE Pacientes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    dni VARCHAR(15) UNIQUE NOT NULL,
    nombre VARCHAR(80) NOT NULL,
    apellido VARCHAR(80) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    genero VARCHAR(15),
    telefono VARCHAR(20),
    email VARCHAR(100),
    direccion VARCHAR(200),
    latitud DECIMAL(10,7) NULL,
    longitud DECIMAL(10,7) NULL,
    grupo_sanguineo VARCHAR(5),
    alergias VARCHAR(MAX),
    fecha_registro DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- 3. MÓDULO: PERSONAL MÉDICO
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Especialidades')
CREATE TABLE Especialidades (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PersonalMedico')
CREATE TABLE PersonalMedico (
    id INT IDENTITY(1,1) PRIMARY KEY,
    usuario_id INT NULL FOREIGN KEY REFERENCES Usuarios(id),
    dni VARCHAR(15) UNIQUE NOT NULL,
    nombre VARCHAR(80) NOT NULL,
    apellido VARCHAR(80) NOT NULL,
    colegiatura_cmp VARCHAR(20) UNIQUE NOT NULL,
    especialidad_id INT FOREIGN KEY REFERENCES Especialidades(id),
    telefono VARCHAR(20),
    email VARCHAR(100),
    horario_atencion VARCHAR(100)
);
GO

-- ============================================================
-- 4. MÓDULO: CITAS MÉDICAS
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CitasMedicas')
CREATE TABLE CitasMedicas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    medico_id INT NOT NULL FOREIGN KEY REFERENCES PersonalMedico(id),
    fecha_cita DATE NOT NULL,
    hora_cita TIME NOT NULL,
    motivo VARCHAR(255),
    estado VARCHAR(20) DEFAULT 'Programada', -- 'Programada','En Triaje','Atendido','Completada','Cancelada'
    fecha_creacion DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- 5. MÓDULO: TRIAJE / VITALES
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Triaje')
CREATE TABLE Triaje (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cita_id INT UNIQUE FOREIGN KEY REFERENCES CitasMedicas(id),
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    presion_arterial VARCHAR(15),
    temperatura DECIMAL(4,2),
    frecuencia_cardiaca INT,
    frecuencia_respiratoria INT,
    saturacion_oxigeno INT,
    peso_kg DECIMAL(5,2),
    talla_cm INT,
    imc DECIMAL(4,2),
    enfermero_id INT FOREIGN KEY REFERENCES Usuarios(id) NULL,
    fecha_registro DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- 6. MÓDULO: HISTORIAL CLÍNICO
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'HistorialClinico')
CREATE TABLE HistorialClinico (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cita_id INT UNIQUE FOREIGN KEY REFERENCES CitasMedicas(id),
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    medico_id INT NOT NULL FOREIGN KEY REFERENCES PersonalMedico(id),
    motivo_consulta VARCHAR(MAX),
    sintomas VARCHAR(MAX),
    diagnostico VARCHAR(MAX),
    codigo_cie10 VARCHAR(10),
    tratamiento VARCHAR(MAX),
    observaciones VARCHAR(MAX),
    fecha_atencion DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- 7. MÓDULO: FARMACIA E INSUMOS
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'FarmaciaInsumos')
CREATE TABLE FarmaciaInsumos (
    id INT IDENTITY(1,1) PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255),
    tipo VARCHAR(30) DEFAULT 'Medicamento',
    stock INT DEFAULT 0,
    precio_unitario DECIMAL(10,2) NOT NULL,
    fecha_vencimiento DATE,
    ubicacion VARCHAR(50)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Recetas')
CREATE TABLE Recetas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    historial_id INT NOT NULL FOREIGN KEY REFERENCES HistorialClinico(id),
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    fecha_emision DATETIME DEFAULT GETDATE()
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DetalleReceta')
CREATE TABLE DetalleReceta (
    id INT IDENTITY(1,1) PRIMARY KEY,
    receta_id INT NOT NULL FOREIGN KEY REFERENCES Recetas(id),
    insumo_id INT NOT NULL FOREIGN KEY REFERENCES FarmaciaInsumos(id),
    cantidad INT NOT NULL,
    indicaciones VARCHAR(255)
);
GO

-- ============================================================
-- 8. MÓDULO: LABORATORIO
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ExamenesLaboratorio')
CREATE TABLE ExamenesLaboratorio (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    medico_id INT NOT NULL FOREIGN KEY REFERENCES PersonalMedico(id),
    nombre_examen VARCHAR(100) NOT NULL,
    resultado VARCHAR(MAX),
    observaciones VARCHAR(255),
    estado VARCHAR(20) DEFAULT 'Pendiente',
    fecha_solicitud DATETIME DEFAULT GETDATE(),
    fecha_resultado DATETIME NULL
);
GO

-- ============================================================
-- 9. MÓDULO: HOSPITALIZACIÓN
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Habitaciones')
CREATE TABLE Habitaciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    numero_habitacion VARCHAR(10) UNIQUE NOT NULL,
    piso INT NOT NULL,
    tipo VARCHAR(30) DEFAULT 'Individual'
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Camas')
CREATE TABLE Camas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    habitacion_id INT NOT NULL FOREIGN KEY REFERENCES Habitaciones(id),
    numero_cama VARCHAR(10) NOT NULL,
    estado VARCHAR(20) DEFAULT 'Disponible' -- 'Disponible','Ocupada','Mantenimiento'
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Hospitalizacion')
CREATE TABLE Hospitalizacion (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    cama_id INT NOT NULL FOREIGN KEY REFERENCES Camas(id),
    medico_tratante_id INT NOT NULL FOREIGN KEY REFERENCES PersonalMedico(id),
    fecha_ingreso DATETIME DEFAULT GETDATE(),
    fecha_alta DATETIME NULL,
    diagnostico_ingreso VARCHAR(MAX),
    estado VARCHAR(20) DEFAULT 'Activo' -- 'Activo','Alta'
);
GO

-- ============================================================
-- 10. MÓDULO: CAJA Y FACTURACIÓN
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ComprobantesFacturacion')
CREATE TABLE ComprobantesFacturacion (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NOT NULL FOREIGN KEY REFERENCES Pacientes(id),
    cita_id INT NULL FOREIGN KEY REFERENCES CitasMedicas(id),
    tipo_comprobante VARCHAR(20) NOT NULL,
    numero_serie VARCHAR(10) NOT NULL,
    numero_correlativo VARCHAR(20) NOT NULL,
    monto_subtotal DECIMAL(10,2) NOT NULL,
    monto_igv DECIMAL(10,2) NOT NULL,
    monto_total DECIMAL(10,2) NOT NULL,
    metodo_pago VARCHAR(30) DEFAULT 'Efectivo',
    estado VARCHAR(20) DEFAULT 'Pagado',
    fecha_emision DATETIME DEFAULT GETDATE()
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DetalleComprobante')
CREATE TABLE DetalleComprobante (
    id INT IDENTITY(1,1) PRIMARY KEY,
    comprobante_id INT NOT NULL FOREIGN KEY REFERENCES ComprobantesFacturacion(id),
    descripcion VARCHAR(200) NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL
);
GO

-- ============================================================
-- 11. MÓDULO: NOTIFICACIONES
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Notificaciones')
CREATE TABLE Notificaciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NULL FOREIGN KEY REFERENCES Pacientes(id),
    usuario_id INT NULL FOREIGN KEY REFERENCES Usuarios(id),
    destinatario_email VARCHAR(150) NULL, -- correo libre, no siempre ligado a un paciente/usuario registrado
    asunto VARCHAR(150) NOT NULL,
    mensaje VARCHAR(MAX) NOT NULL,
    tipo VARCHAR(20) DEFAULT 'Email',
    enviado BIT DEFAULT 0,
    fecha_envio DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- INSERCIÓN DE DATOS INICIALES DE PRUEBA (solo si no existen)
-- ============================================================
IF NOT EXISTS (SELECT * FROM Roles)
INSERT INTO Roles (nombre) VALUES
('Administrador'), ('Médico'), ('Enfermero'), ('Farmacéutico'), ('Cajero');

IF NOT EXISTS (SELECT * FROM Usuarios)
INSERT INTO Usuarios (usuario, password_hash, nombre_completo, email, rol_id) VALUES
('admin', 'admin123', 'Administrador General', 'admin@hdac.com', 1);

IF NOT EXISTS (SELECT * FROM Especialidades)
INSERT INTO Especialidades (nombre, descripcion) VALUES
('Medicina General', 'Atención médica integral primaria'),
('Pediatría', 'Atención de niños y adolescentes'),
('Cardiología', 'Diagnóstico y tratamiento del corazón'),
('Ginecología', 'Salud del sistema reproductor femenino'),
('Traumatología', 'Lesiones del sistema musculoesquelético'),
('Dermatología', 'Enfermedades de la piel'),
('Neurología', 'Sistema nervioso');

IF NOT EXISTS (SELECT * FROM Habitaciones)
INSERT INTO Habitaciones (numero_habitacion, piso, tipo) VALUES
('101', 1, 'Individual'), ('102', 1, 'Compartida'), ('201', 2, 'UCI');

IF NOT EXISTS (SELECT * FROM Camas)
INSERT INTO Camas (habitacion_id, numero_cama, estado) VALUES
(1, 'Cama 1', 'Disponible'),
(2, 'Cama A', 'Disponible'),
(2, 'Cama B', 'Disponible'),
(3, 'UCI 1', 'Disponible');
GO

-- ============================================================
-- 12. MÓDULO: MACHINE LEARNING EN VIVO (NUEVO)
--     Cada predicción se guarda aquí; cuando se conoce el resultado real
--     (reingresó / no reingresó) la matriz de confusión se calcula desde esta tabla.
--     (La aplicación también la crea sola si no existe.)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ML_Predicciones')
CREATE TABLE dbo.ML_Predicciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NULL,
    paciente_nombre VARCHAR(160) NULL,
    fecha_prediccion DATETIME NOT NULL DEFAULT GETDATE(),
    edad INT NOT NULL,
    presion_sistolica INT NOT NULL,
    presion_diastolica INT NOT NULL,
    frecuencia_cardiaca INT NOT NULL,
    glucosa INT NOT NULL,
    temperatura DECIMAL(4,1) NOT NULL,
    nivel_triaje INT NOT NULL,
    comorbilidades INT NOT NULL,
    probabilidad DECIMAL(5,4) NOT NULL,
    riesgo_predicho BIT NOT NULL,          -- 0 = bajo riesgo, 1 = alto riesgo
    resultado_real BIT NULL,               -- NULL = pendiente de confirmar; 1 = reingresó
    fecha_resultado DATETIME NULL,
    origen_resultado VARCHAR(20) NULL,     -- manual / hospitalizacion / ventana_30d / simulacion
    origen VARCHAR(12) NOT NULL DEFAULT 'sistema',   -- sistema / simulacion
    usuario VARCHAR(50) NOT NULL DEFAULT 'admin',
    CONSTRAINT FK_ML_Predicciones_Pacientes FOREIGN KEY (paciente_id)
        REFERENCES dbo.Pacientes(id) ON DELETE SET NULL
);
GO
