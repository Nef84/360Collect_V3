"""
omnichannel_channels.py
=======================
Implementaciones de canales adicionales para 360CollectPlus:

  • Email  — Resend.com (gratis: 100/día, 3 000/mes, sin tarjeta)
             Fallback: SMTP genérico (Gmail, Outlook, etc.)
  • SMS    — TextBelt (1 SMS gratis/día sin cuenta)
             Alternativa: Twilio SMS (mismo account que WhatsApp)
  • CallBot— Twilio Voice TwiML (cuenta trial existente)
             IVR conversacional de cobranza por estrategia

Todos los proveedores se configuran desde la consola de Admin
en /admin/omnichannel/config  y se usan desde los endpoints:
  POST /admin/omnichannel/email/demo-send
  POST /admin/omnichannel/sms/demo-send
  POST /admin/omnichannel/callbot/demo-call
  POST /webhooks/twilio/voice          ← TwiML inicial
  POST /webhooks/twilio/voice/gather   ← respuesta dígitos
"""

from __future__ import annotations

import base64
import json
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL  —  Resend.com (gratis) + SMTP fallback
# ─────────────────────────────────────────────────────────────────────────────

def build_collection_email_html(
    client_name: str,
    strategy_code: str,
    total_due: float,
    minimum_payment: float,
    account_last4: str,
    due_date_str: str,
    institution_name: str = "360CollectPlus",
) -> tuple[str, str]:
    """Devuelve (subject, html) adaptados a la estrategia de mora."""
    strategy_labels = {
        "AL_DIA":                 ("Recordatorio de pago", "#00B4A6"),
        "PREVENTIVO":             ("Aviso de vencimiento próximo", "#00B4A6"),
        "FMORA1":                 ("Atención requerida en su cuenta", "#F5A623"),
        "MMORA2":                 ("Seguimiento — cuenta en mora", "#F5A623"),
        "HMORA3":                 ("Acción urgente — regularice su cuenta", "#E67E22"),
        "AMORA4":                 ("Aviso prioritario de recuperación", "#E74C3C"),
        "BMORA5":                 ("Gestión intensiva — mora avanzada", "#C0392B"),
        "CMORA6":                 ("Última oportunidad de regularización", "#C0392B"),
        "DMORA7":                 ("Notificación final — referencia a gestión externa", "#8E44AD"),
        "VAGENCIASEXTERNASINTERNO":("Gestión de recuperación especial", "#8E44AD"),
    }
    subject_suffix, accent = strategy_labels.get(strategy_code, ("Aviso de cuenta", "#0B1F3A"))

    if strategy_code in {"AL_DIA", "PREVENTIVO"}:
        greeting = f"Estimado/a {client_name},"
        body_text = (
            f"Le recordamos que su cuenta con terminación <strong>{account_last4}</strong> "
            f"tiene una fecha de pago próxima el <strong>{due_date_str}</strong>.<br><br>"
            f"Mantenga su cuenta al día y evite cargos por mora. "
            f"El pago mínimo sugerido es de <strong>${minimum_payment:,.2f}</strong>."
        )
        cta = "Realizar mi pago ahora"
    elif strategy_code in {"FMORA1", "MMORA2"}:
        greeting = f"Estimado/a {client_name},"
        body_text = (
            f"Su cuenta terminación <strong>{account_last4}</strong> presenta un saldo vencido "
            f"de <strong>${total_due:,.2f}</strong>.<br><br>"
            f"Para regularizarla hoy, necesitamos un pago mínimo de "
            f"<strong>${minimum_payment:,.2f}</strong> a más tardar el <strong>{due_date_str}</strong>."
        )
        cta = "Regularizar mi cuenta"
    else:
        greeting = f"Estimado/a {client_name},"
        body_text = (
            f"Su cuenta terminación <strong>{account_last4}</strong> requiere atención inmediata. "
            f"Saldo vencido acumulado: <strong>${total_due:,.2f}</strong>.<br><br>"
            f"Contáctenos antes del <strong>{due_date_str}</strong> para acordar un plan de pago "
            f"y evitar el escalamiento de su caso. Pago mínimo: <strong>${minimum_payment:,.2f}</strong>."
        )
        cta = "Hablar con un asesor"

    subject = f"[{institution_name}] {subject_suffix} — Cuenta ...{account_last4}"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#F4F6F9;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F6F9;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">

  <!-- Header -->
  <tr><td style="background:#0B1F3A;padding:28px 36px;">
    <table width="100%"><tr>
      <td><span style="color:#00B4A6;font-size:22px;font-weight:bold;">360Collect</span>
          <span style="color:white;font-size:22px;font-weight:bold;">Plus</span></td>
      <td align="right"><span style="background:{accent};color:white;padding:4px 12px;
          border-radius:20px;font-size:12px;font-weight:bold;">{strategy_code}</span></td>
    </tr></table>
  </td></tr>

  <!-- Accent bar -->
  <tr><td style="background:{accent};height:4px;"></td></tr>

  <!-- Body -->
  <tr><td style="padding:36px;">
    <p style="color:#0B1F3A;font-size:16px;margin:0 0 16px;">{greeting}</p>
    <p style="color:#4A4A5A;font-size:15px;line-height:1.7;margin:0 0 24px;">{body_text}</p>

    <!-- Amount card -->
    <table width="100%" style="background:#F4F6F9;border-radius:8px;margin:0 0 28px;">
    <tr>
      <td style="padding:20px;text-align:center;">
        <p style="margin:0;color:#4A4A5A;font-size:13px;text-transform:uppercase;letter-spacing:.05em;">Saldo vencido</p>
        <p style="margin:6px 0 0;color:#E74C3C;font-size:32px;font-weight:bold;">${total_due:,.2f}</p>
      </td>
      <td style="width:1px;background:#D1D5E0;"></td>
      <td style="padding:20px;text-align:center;">
        <p style="margin:0;color:#4A4A5A;font-size:13px;text-transform:uppercase;letter-spacing:.05em;">Pago mínimo</p>
        <p style="margin:6px 0 0;color:#27AE60;font-size:32px;font-weight:bold;">${minimum_payment:,.2f}</p>
      </td>
      <td style="width:1px;background:#D1D5E0;"></td>
      <td style="padding:20px;text-align:center;">
        <p style="margin:0;color:#4A4A5A;font-size:13px;text-transform:uppercase;letter-spacing:.05em;">Fecha límite</p>
        <p style="margin:6px 0 0;color:#0B1F3A;font-size:20px;font-weight:bold;">{due_date_str}</p>
      </td>
    </tr></table>

    <!-- CTA button -->
    <table width="100%"><tr><td align="center">
      <a href="#" style="display:inline-block;background:{accent};color:white;
         padding:14px 40px;border-radius:8px;text-decoration:none;
         font-size:15px;font-weight:bold;">{cta}</a>
    </td></tr></table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#0B1F3A;padding:20px 36px;text-align:center;">
    <p style="color:#8AADC4;font-size:12px;margin:0;">
      Este mensaje fue enviado a {client_name} por {institution_name}.<br>
      Para más información contáctenos o responda este correo.
    </p>
    <p style="color:#4A6A8A;font-size:11px;margin:8px 0 0;">
      © {datetime.now().year} {institution_name} — Todos los derechos reservados
    </p>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""

    return subject, html


def send_email_resend(
    api_key: str,
    from_email: str,
    to_email: str,
    subject: str,
    html: str,
    reply_to: Optional[str] = None,
) -> dict:
    """
    Envía email vía Resend.com.
    Gratis: 100 emails/día · 3 000/mes · sin tarjeta de crédito.
    Registro: https://resend.com/signup  (solo email)
    API key: https://resend.com/api-keys
    """
    payload = json.dumps({
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
        **({"reply_to": reply_to} if reply_to else {}),
    }).encode("utf-8")

    req = urllib_request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=400, detail=f"Resend rechazó el envío: {detail or e.reason}")
    except URLError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con Resend: {e.reason}")


def send_email_smtp(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
    to_email: str,
    subject: str,
    html: str,
) -> dict:
    """
    Fallback SMTP. Funciona con Gmail (smtp.gmail.com:587),
    Outlook (smtp-mail.outlook.com:587), etc.
    Para Gmail necesitas una 'contraseña de aplicación':
    https://myaccount.google.com/apppasswords
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
        return {"status": "sent", "provider": "smtp", "to": to_email}
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=401, detail="Credenciales SMTP incorrectas.")
    except smtplib.SMTPException as e:
        raise HTTPException(status_code=502, detail=f"Error SMTP: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con el servidor SMTP: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SMS  —  TextBelt (gratis) + Twilio SMS
# ─────────────────────────────────────────────────────────────────────────────

def build_collection_sms(
    client_name: str,
    strategy_code: str,
    total_due: float,
    minimum_payment: float,
    account_last4: str,
    due_date_str: str,
    institution: str = "360CollectPlus",
) -> str:
    """Construye un SMS de máximo ~160 caracteres adaptado a la estrategia."""
    first_name = client_name.split()[0] if client_name else "Cliente"
    total_due_label = f"USD {total_due:,.0f}"
    minimum_label = f"USD {minimum_payment:,.0f}"
    safe_last4 = account_last4 or "0000"

    templates = {
        "AL_DIA": (
            f"{institution}: Hola {first_name}, su pago próximo es el {due_date_str}. "
            f"Minimo {minimum_label}. Cuenta ...{safe_last4}. Responda AYUDA."
        ),
        "PREVENTIVO": (
            f"{institution}: {first_name}, su cuenta ...{safe_last4} vence el {due_date_str}. "
            f"Pague {minimum_label} hoy y evite mora. Responda ASESOR si necesita apoyo."
        ),
        "FMORA1": (
            f"{institution}: {first_name}, mora de {total_due_label} en cuenta ...{safe_last4}. "
            f"Regularice con {minimum_label} antes del {due_date_str}. Responda PAGAR."
        ),
        "MMORA2": (
            f"{institution}: {first_name}, su saldo vencido de {total_due_label} requiere accion. "
            f"Min {minimum_label} hasta {due_date_str}. Responda ACUERDO o llame al *360."
        ),
        "HMORA3": (
            f"{institution} URGENTE: {first_name}, cuenta ...{safe_last4} con {total_due_label} "
            f"en mora. Contactenos HOY. Min {minimum_label}. Responda 1 para asesor."
        ),
    }
    default = (
        f"{institution}: {first_name}, gestione urgente su cuenta ...{safe_last4}. "
        f"Saldo vencido: {total_due_label}. Llame al *360 o responda ASESOR."
    )
    msg = templates.get(strategy_code, default)
    return msg[:320]  # SMS long message safe limit


def send_sms_textbelt(
    phone_number: str,
    message: str,
    api_key: str = "textbelt",
) -> dict:
    """
    Envía SMS via TextBelt.
    GRATIS: use api_key='textbelt' → 1 SMS gratuito/día por IP (para demo/pruebas).
    Sin registro, sin tarjeta. Perfecto para validar el flujo.
    Paid: compra créditos en https://textbelt.com  (~$0.01/SMS)

    El número debe incluir código de país: +50312345678
    """
    digits = re.sub(r"\D", "", phone_number)
    if not digits.startswith("+"):
        normalized = f"+{digits}"
    else:
        normalized = phone_number

    payload = urllib_parse.urlencode({
        "phone": normalized,
        "message": message,
        "key": api_key,
    }).encode("utf-8")

    req = urllib_request.Request(
        "https://textbelt.com/text",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"TextBelt error: {result.get('error', 'Unknown')}. "
                       f"Cuota restante: {result.get('quotaRemaining', '?')}",
            )
        return {
            "status": "sent",
            "provider": "textbelt",
            "to": normalized,
            "quota_remaining": result.get("quotaRemaining"),
            "text_id": result.get("textId"),
        }
    except HTTPError as e:
        raise HTTPException(status_code=502, detail=f"TextBelt HTTP error: {e.reason}")
    except URLError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con TextBelt: {e.reason}")


def send_sms_twilio(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    message: str,
) -> dict:
    """
    Envía SMS via Twilio (misma cuenta que WhatsApp).
    El from_number debe ser un número Twilio con capacidad SMS (no whatsapp:+...).
    Con cuenta trial puedes enviar a números verificados.
    """
    digits_to = re.sub(r"\D", "", to_number)
    to_e164 = f"+{digits_to}" if not to_number.startswith("+") else to_number
    digits_from = re.sub(r"\D", "", from_number.replace("whatsapp:", ""))
    from_e164 = f"+{digits_from}" if not from_number.startswith("+") else from_number.replace("whatsapp:", "")

    pair = f"{account_sid}:{auth_token}"
    basic_auth = base64.b64encode(pair.encode("ascii")).decode("ascii")
    payload = urllib_parse.urlencode({
        "To": to_e164,
        "From": from_e164,
        "Body": message,
    }).encode("utf-8")

    req = urllib_request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=400, detail=f"Twilio SMS error: {detail or e.reason}")
    except URLError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con Twilio: {e.reason}")


# ─────────────────────────────────────────────────────────────────────────────
# CALLBOT  —  Twilio Voice TwiML  (misma cuenta trial)
# ─────────────────────────────────────────────────────────────────────────────

def build_twiml_initial_call(
    client_name: str,
    strategy_code: str,
    total_due: float,
    minimum_payment: float,
    account_last4: str,
    due_date_str: str,
    gather_webhook_url: str,
    institution: str = "360CollectPlus",
) -> str:
    """
    Genera el TwiML para la llamada inicial de cobranza.
    El IVR saluda, expone el saldo y pide una acción por teclado:
      1 → registrar promesa de pago
      2 → solicitar llamada humana
      3 → repetir opciones
      0 → colgar
    """
    first_name = client_name.split()[0] if client_name else "cliente"

    if strategy_code in {"AL_DIA", "PREVENTIVO"}:
        urgency = "le recordamos que tiene un pago próximo"
        tone = "amistoso"
    elif strategy_code in {"FMORA1", "MMORA2"}:
        urgency = "su cuenta presenta un saldo vencido que requiere atención"
        tone = "cordial"
    elif strategy_code in {"HMORA3", "AMORA4"}:
        urgency = "su cuenta requiere acción inmediata para evitar mayor escalamiento"
        tone = "firme"
    else:
        urgency = "su caso ha sido derivado a gestión de recuperación prioritaria"
        tone = "formal"

    _ = tone  # usado para contexto interno
    greeting = (
        f"Buenas tardes. Le llama el sistema automatizado de cobranza de {institution}. "
        f"Solicitamos hablar con {first_name}. "
        f"{urgency.capitalize()}. "
        f"Su saldo vencido en la cuenta terminación {' '.join(account_last4)} "
        f"es de {total_due:.0f} dólares con {int((total_due % 1) * 100):02d} centavos. "
        f"El pago mínimo para regularizar es de {minimum_payment:.0f} dólares. "
        f"Fecha límite: {due_date_str}. "
    )
    menu = (
        "Para registrar un acuerdo de pago presione 1. "
        "Para hablar con un asesor presione 2. "
        "Para escuchar nuevamente estas opciones presione 3. "
        "Para finalizar la llamada presione 0."
    )

    safe_url = gather_webhook_url.rstrip("/")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Pause length="1"/>
  <Say voice="Polly.Lupe" language="es-US">{_xml_escape(greeting)}</Say>
  <Gather numDigits="1" action="{safe_url}/webhooks/twilio/voice/gather" method="POST" timeout="8">
    <Say voice="Polly.Lupe" language="es-US">{_xml_escape(menu)}</Say>
  </Gather>
  <Say voice="Polly.Lupe" language="es-US">
    No recibimos respuesta. Un asesor se comunicará con usted. Que tenga buen día.
  </Say>
</Response>"""


def build_twiml_gather_response(digit: str, context: dict) -> str:
    """
    TwiML de respuesta según el dígito presionado en el IVR.
    context: {client_name, minimum_payment, due_date_str, account_last4}
    """
    first_name = context.get("client_name", "cliente").split()[0]
    minimum_payment = context.get("minimum_payment", 0.0)
    due_date_str = context.get("due_date_str", "próximamente")
    account_last4 = context.get("account_last4", "****")

    if digit == "1":
        msg = (
            f"Gracias {first_name}. Se ha registrado su acuerdo de pago "
            f"por {minimum_payment:.0f} dólares con fecha límite {due_date_str} "
            f"para la cuenta terminación {' '.join(account_last4)}. "
            "Un asesor confirmará el acuerdo por mensaje. Gracias por su tiempo. Que tenga buen día."
        )
    elif digit == "2":
        msg = (
            f"Entendido {first_name}. Un asesor de cobranza se comunicará con usted "
            "a la brevedad posible. Gracias por atendernos. Que tenga buen día."
        )
    elif digit == "3":
        # repeat — handled by redirect in TwiML
        return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Redirect method="POST">/webhooks/twilio/voice</Redirect>
</Response>"""
    elif digit == "0":
        msg = f"Gracias por su tiempo {first_name}. Hasta pronto."
    else:
        msg = "Opción no reconocida. Un asesor se comunicará con usted. Que tenga buen día."

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Lupe" language="es-US">{_xml_escape(msg)}</Say>
  <Hangup/>
</Response>"""


def build_twiml_no_answer() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Lupe" language="es-US">
    No recibimos respuesta. Un asesor se comunicará con usted. Gracias. Que tenga buen día.
  </Say>
  <Hangup/>
</Response>"""


def initiate_callbot_twilio(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    twiml_webhook_url: str,
    status_callback_url: Optional[str] = None,
) -> dict:
    """
    Inicia una llamada de voz saliente via Twilio Voice.
    from_number: número Twilio con capacidad de voz (ej: +15551234567)
    to_number:   número del cliente (ej: +50312345678)
    twiml_webhook_url: URL pública que devuelve TwiML (ej: https://tudominio.com/webhooks/twilio/voice)

    Con cuenta TRIAL: solo puedes llamar a números VERIFICADOS en la consola Twilio.
    Para producción: actualiza la cuenta y llama a cualquier número.
    """
    digits_to = re.sub(r"\D", "", to_number)
    to_e164 = f"+{digits_to}" if not to_number.startswith("+") else to_number
    digits_from = re.sub(r"\D", "", from_number.replace("whatsapp:", ""))
    from_e164 = f"+{digits_from}"

    pair = f"{account_sid}:{auth_token}"
    basic_auth = base64.b64encode(pair.encode("ascii")).decode("ascii")

    params = {
        "To": to_e164,
        "From": from_e164,
        "Url": twiml_webhook_url,
        "Method": "POST",
    }
    if status_callback_url:
        params["StatusCallback"] = status_callback_url
        params["StatusCallbackMethod"] = "POST"

    payload = urllib_parse.urlencode(params).encode("utf-8")
    req = urllib_request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=400, detail=f"Twilio Voice error: {detail or e.reason}")
    except URLError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con Twilio Voice: {e.reason}")


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )
