"""
alerts.py — Envia e-mail de alerta quando o ETL falha ou quando
            algum cliente está próximo de estourar o contrato.
"""
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config

logger = logging.getLogger(__name__)

# Cores por nível de alerta
_CORES = {
    "ESTOURADO": "#C00000",
    "CRITICO":   "#FF6B00",
    "ATENCAO":   "#FFC000",
    "NORMAL":    "#70AD47",
}


def _send_email(subject: str, body_html: str) -> None:
    placeholders = {"seu@email.com", "senha_do_email", "gestor@empresa.com", ""}
    if (not all([config.SMTP_USER, config.SMTP_PASS, config.ALERT_EMAIL])
            or config.SMTP_USER in placeholders
            or config.SMTP_PASS in placeholders):
        logger.debug("E-mail não configurado. Pulando envio de alerta.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.SMTP_FROM
    msg["To"]      = config.ALERT_EMAIL

    # Cópia para destinatários adicionais
    cc_list = [e.strip() for e in config.ALERT_EMAIL_CC.split(",") if e.strip()]
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg.attach(MIMEText(body_html, "html"))

    all_recipients = [config.ALERT_EMAIL] + cc_list

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.sendmail(config.SMTP_FROM, all_recipients, msg.as_string())
        logger.info("Alerta enviado para %s", ", ".join(all_recipients))
    except Exception as exc:
        logger.error("Falha ao enviar e-mail: %s", exc)


def alert_etl_failure(error: Exception, step: str) -> None:
    subject = f"[ALERTA] ETL Movidesk falhou — {step}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px">
      <h2 style="color:#C00000;border-bottom:2px solid #C00000;padding-bottom:8px">
        ❌ ETL Movidesk — Falha na etapa: {step}
      </h2>
      <p><strong>Data/Hora:</strong> {date.today().strftime('%d/%m/%Y')}</p>
      <p><strong>Erro:</strong></p>
      <pre style="background:#f5f5f5;padding:12px;border-left:4px solid #C00000;
                  font-size:13px;overflow:auto">{error}</pre>
      <p style="color:#666;font-size:12px">
        Verifique os logs em <code>scripts/logs/</code> e tome as ações necessárias.
      </p>
    </div>
    """
    _send_email(subject, body)


def alert_contract_overflow(overflows: list[dict]) -> None:
    """
    overflows: lista de dicts com keys:
        client_name, horas_consumidas, horas_contratadas, pct_consumo, status_consumo
    """
    if not overflows:
        return

    # Separa por nível
    estourados = [o for o in overflows if o["pct_consumo"] >= 100]
    criticos   = [o for o in overflows if 100 > o["pct_consumo"] >= config.OVERFLOW_THRESHOLD_CRITICAL]
    atencao    = [o for o in overflows if config.OVERFLOW_THRESHOLD_CRITICAL > o["pct_consumo"] >= config.OVERFLOW_THRESHOLD_WARNING]

    def _badge(pct: float) -> str:
        if pct >= 100:
            status, cor = "ESTOURADO", _CORES["ESTOURADO"]
        elif pct >= config.OVERFLOW_THRESHOLD_CRITICAL:
            status, cor = "CRÍTICO", _CORES["CRITICO"]
        else:
            status, cor = "ATENÇÃO", _CORES["ATENCAO"]
        return (
            f'<span style="background:{cor};color:#fff;padding:2px 8px;'
            f'border-radius:3px;font-size:11px;font-weight:bold">{status}</span>'
        )

    rows = "".join(
        f"""<tr style="background:{'#fff0f0' if o['pct_consumo'] >= 100 else '#fff8f0'}">
            <td style="padding:8px 12px">{o['client_name']}</td>
            <td style="padding:8px 12px;text-align:right"><strong>{o['horas_consumidas']:.1f}h</strong></td>
            <td style="padding:8px 12px;text-align:right">{o['horas_contratadas']:.1f}h</td>
            <td style="padding:8px 12px;text-align:right">
              <strong style="color:{_CORES['ESTOURADO'] if o['pct_consumo']>=100 else _CORES['CRITICO']}">
                {o['pct_consumo']:.0f}%
              </strong>
            </td>
            <td style="padding:8px 12px;text-align:center">{_badge(o['pct_consumo'])}</td>
        </tr>"""
        for o in overflows
    )

    mes_ref = date.today().strftime("%B/%Y")
    n_estourados = len(estourados)
    n_criticos   = len(criticos)

    if n_estourados:
        subject = f"[URGENTE] {n_estourados} cliente(s) ESTOUROU contrato — {mes_ref}"
    else:
        subject = f"[ALERTA] {n_criticos} cliente(s) crítico(s) no contrato — {mes_ref}"

    summary_parts = []
    if estourados:
        summary_parts.append(
            f'<span style="color:{_CORES["ESTOURADO"]};font-weight:bold">'
            f'{len(estourados)} estourado(s)</span>'
        )
    if criticos:
        summary_parts.append(
            f'<span style="color:{_CORES["CRITICO"]};font-weight:bold">'
            f'{len(criticos)} crítico(s)</span>'
        )
    if atencao:
        summary_parts.append(
            f'<span style="color:{_CORES["ATENCAO"]};font-weight:bold">'
            f'{len(atencao)} em atenção</span>'
        )

    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:700px">
      <h2 style="color:#C00000;border-bottom:2px solid #eee;padding-bottom:8px">
        ⚠️ Alerta de Consumo de Contrato — {mes_ref}
      </h2>
      <p>Resumo: {" | ".join(summary_parts)}</p>
      <table style="border-collapse:collapse;width:100%;font-size:13px">
        <thead>
          <tr style="background:#333;color:#fff">
            <th style="padding:8px 12px;text-align:left">Cliente</th>
            <th style="padding:8px 12px;text-align:right">Horas usadas</th>
            <th style="padding:8px 12px;text-align:right">Contratadas</th>
            <th style="padding:8px 12px;text-align:right">% Consumo</th>
            <th style="padding:8px 12px;text-align:center">Status</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:16px;font-size:12px;color:#888">
        Gerado automaticamente pelo ETL Movidesk BI em {date.today().strftime('%d/%m/%Y')}.
        Acesse o Power BI para detalhes completos.
      </p>
    </div>
    """
    _send_email(subject, body)
