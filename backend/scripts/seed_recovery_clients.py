from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from database import SessionLocal
from main import record_assignment_history
from models import Cliente, Cuenta, History, Pago, PrediccionIA, Usuario, WorklistAssignment


TARGET_NEW_CLIENTS = 1000


def main() -> None:
    db = SessionLocal()
    try:
        active_collectors = (
            db.query(Usuario)
            .filter(Usuario.rol == "Collector", Usuario.activo.is_(True))
            .order_by(Usuario.id)
            .all()
        )
        if not active_collectors:
            raise RuntimeError("No hay collectors activos para asignar cartera Recovery.")

        current_max_client = db.query(func.coalesce(func.max(Cliente.id), 0)).scalar() or 0
        today = date.today()
        now = datetime.now(timezone.utc)

        inserted = 0
        for index in range(1, TARGET_NEW_CLIENTS + 1):
            sequence_base = current_max_client + index
            client = Cliente(
                codigo_cliente=f"RCVW{str(sequence_base).zfill(6)}",
                nombres=["Samuel Antonio", "Gabriela Elena", "Mauricio Jose", "Patricia Lorena", "Edwin Rafael", "Marisela Beatriz"][index % 6],
                apellidos=["Rivera Diaz", "Mejia Paredes", "Portillo Castillo", "Linares Castro", "Rivas Sandoval", "Bonilla Flores"][(index + 2) % 6],
                dui=f"5{str(sequence_base).zfill(7)}-{sequence_base % 10}",
                nit=f"0614-{str(sequence_base).zfill(6)}-{str(500 + index).zfill(3)}-{sequence_base % 10}",
                telefono=f"72{str(sequence_base % 1000000).zfill(6)}",
                email=f"recovery.wave.{sequence_base}@demo360collectplus.com",
                direccion=f"San Salvador, Ola Recovery, placement {index}, cliente {sequence_base}",
                score_riesgo=round(0.74 + ((index % 14) / 100.0), 2),
                segmento="Recovery",
            )
            db.add(client)
            db.flush()

            account = Cuenta(
                cliente_id=client.id,
                numero_cuenta=f"RCW-{str(client.id).zfill(6)}",
                tipo_producto="Tarjeta" if index % 2 == 0 else "Prestamo",
                subtipo_producto="Recuperacion",
                saldo_capital=round(900 + (index % 55) * 42, 2),
                saldo_mora=round(450 + (index % 28) * 26, 2),
                saldo_total=round(1350 + (index % 55) * 66, 2),
                dias_mora=185 + (index % 50),
                bucket_actual="181+",
                estado="LIQUIDADO" if index % 2 == 0 else "Z",
                fecha_apertura=today - timedelta(days=((index % 1800) + 450)),
                fecha_vencimiento=today - timedelta(days=185 + (index % 50)),
                tasa_interes=round(18 + (index % 6) * 0.8, 2),
                es_estrafinanciamiento=False,
            )
            db.add(account)
            db.flush()

            collector = active_collectors[(index - 1) % len(active_collectors)]
            assignment = WorklistAssignment(
                usuario_id=collector.id,
                cliente_id=client.id,
                estrategia_codigo="VAGENCIASEXTERNASINTERNO",
                activa=True,
            )
            db.add(assignment)
            db.flush()

            record_assignment_history(
                db,
                client,
                assignment,
                strategy_code="VAGENCIASEXTERNASINTERNO",
                notes="Carga manual de 1000 clientes Recovery para placements V11+ y agencias.",
                user=collector,
            )
            db.add(
                PrediccionIA(
                    cuenta_id=account.id,
                    probabilidad_pago_30d=round(0.34 - ((index % 9) * 0.012), 4),
                    score_modelo=round((34 - ((index % 9) * 1.2)) * 10, 2),
                    modelo_version="xgb-v2-demo",
                    recomendacion="Recovery de alta severidad. Priorizar callbot, llamada humana y refuerzo por WhatsApp.",
                )
            )
            db.add(
                History(
                    entidad="clientes",
                    entidad_id=client.id,
                    accion="CARGA_RECOVERY_MASIVA",
                    descripcion=f"Cliente Recovery agregado manualmente. Cuenta {account.numero_cuenta} enviada a placement inicial.",
                    usuario_id=collector.id,
                    created_at=now,
                )
            )
            inserted += 1

        db.commit()
        print(f"Recovery seed completed. Inserted clients: {inserted}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
