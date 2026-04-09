from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, text

from database import SessionLocal
from main import next_cycle_cut_account_id, record_assignment_history
from models import Cliente, Cuenta, History, PrediccionIA, Usuario, WorklistAssignment


TARGET_NEW_CLIENTS = 240
TARGET_COLLECTOR = "collector1"


def main() -> None:
    db = SessionLocal()
    try:
        collector = (
            db.query(Usuario)
            .filter(Usuario.username == TARGET_COLLECTOR, Usuario.rol == "Collector", Usuario.activo.is_(True))
            .first()
        )
        if not collector:
            raise RuntimeError(f"No se encontró collector activo: {TARGET_COLLECTOR}")

        current_max_client = db.query(func.coalesce(func.max(Cliente.id), 0)).scalar() or 0
        current_max_account = db.query(func.coalesce(func.max(Cuenta.id), 0)).scalar() or 0
        today = date.today()
        now = datetime.now(timezone.utc)
        next_manual_account_id = current_max_account

        inserted = 0
        for index in range(1, TARGET_NEW_CLIENTS + 1):
            sequence_base = current_max_client + index
            client = Cliente(
                codigo_cliente=f"PRVH{str(sequence_base).zfill(6)}",
                nombres=["Karen Patricia", "Victor Manuel", "Gloria Beatriz", "Oscar David", "Roxana Isabel", "Francisco Javier"][index % 6],
                apellidos=["Arias Portillo", "Baires Mendoza", "Chavez Dubon", "Navarrete Rivas", "Calderon Ponce", "Serrano Mejia"][(index + 4) % 6],
                dui=f"4{str(sequence_base).zfill(7)}-{sequence_base % 10}",
                nit=f"0614-{str(sequence_base).zfill(6)}-{str(700 + index).zfill(3)}-{sequence_base % 10}",
                telefono=f"71{str(sequence_base % 1000000).zfill(6)}",
                email=f"preventivo.wave.{sequence_base}@demo360collectplus.com",
                direccion=f"San Salvador, Ola Preventivo, cliente {sequence_base}",
                score_riesgo=round(0.18 + ((index % 12) / 100.0), 2),
                segmento="Preventivo",
            )
            db.add(client)
            db.flush()

            # Today is considered Preventivo only when due_day <= today.day < cut_day.
            # With the current business rule, cut days 8..12 keep the account visible
            # in Preventivo on the 7th of the month.
            next_manual_account_id = next_cycle_cut_account_id(next_manual_account_id, {8, 9, 10, 11, 12})
            account = Cuenta(
                id=next_manual_account_id,
                cliente_id=client.id,
                numero_cuenta=f"PRH-{str(client.id).zfill(6)}",
                tipo_producto="Tarjeta" if index % 2 == 0 else "Prestamo",
                subtipo_producto="Clasica" if index % 2 == 0 else "Consumo",
                saldo_capital=round(520 + (index % 20) * 35, 2),
                saldo_mora=round(14 + (index % 5) * 3, 2),
                saldo_total=round(534 + (index % 20) * 36, 2),
                dias_mora=0,
                bucket_actual="0-30",
                estado="ACTIVA",
                fecha_apertura=today - timedelta(days=((index % 420) + 20)),
                fecha_vencimiento=today - timedelta(days=1),
                tasa_interes=round(13 + (index % 6) * 0.7, 2),
                es_estrafinanciamiento=False,
            )
            db.add(account)
            db.flush()

            assignment = WorklistAssignment(
                usuario_id=collector.id,
                cliente_id=client.id,
                estrategia_codigo="PREVENTIVO",
                activa=True,
            )
            db.add(assignment)
            db.flush()

            record_assignment_history(
                db,
                client,
                assignment,
                strategy_code="PREVENTIVO",
                notes="Carga manual de clientes Preventivo visibles para el collector.",
                user=collector,
            )
            db.add(
                PrediccionIA(
                    cuenta_id=account.id,
                    probabilidad_pago_30d=round(0.73 - ((index % 8) * 0.01), 4),
                    score_modelo=round((73 - ((index % 8) * 1.0)) * 10, 2),
                    modelo_version="xgb-v2-demo",
                    recomendacion="Seguimiento preventivo con recordatorio digital y chatbot antes de cualquier contacto humano.",
                )
            )
            db.add(
                History(
                    entidad="clientes",
                    entidad_id=client.id,
                    accion="CARGA_PREVENTIVO_MASIVA",
                    descripcion=f"Cliente Preventivo agregado manualmente. Cuenta {account.numero_cuenta} asignada a {TARGET_COLLECTOR}.",
                    usuario_id=collector.id,
                    created_at=now,
                )
            )
            inserted += 1

        db.flush()
        db.execute(text("SELECT setval(pg_get_serial_sequence('cuentas', 'id'), (SELECT MAX(id) FROM cuentas))"))
        db.commit()
        print(f"Preventivo seed completed. Inserted clients: {inserted}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
