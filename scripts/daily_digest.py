"""
daily_digest.py — Envia digest diário (HTML) ao gestor com:
  - horas lançadas ontem
  - tickets novos/resolvidos ontem
  - top 5 tickets em risco de SLA
  - alertas ativos / clientes próximos do estouro
  - anomalias detectadas

Uso:
  python scripts/daily_digest.py
"""
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from etl.alerts import _send_email
from dashboard.db import _engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("digest")


def _q(sql: str):
    with _engine().connect() as conn:
        return list(conn.execute(text(sql)).mappings())


def _kpis_ontem():
    rows = _q("""
        SELECT
            COALESCE(SUM(te.hours_spent), 0) AS horas_ontem,
            COUNT(DISTINCT te.ticket_id)     AS tickets_atendidos,
            COUNT(DISTINCT te.agent_id)      AS analistas_ativos
        FROM raw.time_entries te
        WHERE te.entry_date = CURRENT_DATE - INTERVAL '1 day'
    """)
    return rows[0] if rows else {}


def _tickets_dia():
    rows = _q("""
        SELECT
            COUNT(*) FILTER (WHERE DATE(t.created_date) = CURRENT_DATE - INTERVAL '1 day') AS novos,
            COUNT(*) FILTER (WHERE DATE(t.resolved_date) = CURRENT_DATE - INTERVAL '1 day') AS resolvidos
        FROM raw.tickets t
    """)
    return rows[0] if rows else {}


def _top_risco_sla():
    return _q("""
        SELECT ticket_id, subject, cliente, urgency,
               (minutos_ate_estourar_sla / 60.0) AS horas_para_sla
        FROM analytics.v_tickets_risco_sla
        WHERE minutos_ate_estourar_sla IS NOT NULL
          AND minutos_ate_estourar_sla < 24 * 60
        ORDER BY minutos_ate_estourar_sla ASC
        LIMIT 5
    """)


def _previsao_estouro():
    return _q("""
        SELECT client_name, pct_previsto, dias_ate_fim_mes
        FROM analytics.previsoes_consumo
        WHERE mes_referencia = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          AND vai_estourar = TRUE
        ORDER BY pct_previsto DESC
        LIMIT 5
    """)


def _anomalias():
    return _q("""
        SELECT client_name, severidade, z_score, horas_periodo
        FROM analytics.anomalias_consumo
        WHERE data_detectada >= CURRENT_DATE - INTERVAL '2 days'
        ORDER BY z_score DESC
        LIMIT 5
    """)


def _previsao_tickets_hoje():
    rows = _q("""
        SELECT tickets_previstos
        FROM analytics.previsoes_tickets_7d
        WHERE data_prevista = CURRENT_DATE
    """)
    return float(rows[0]["tickets_previstos"]) if rows else 0.0


def _table(rows, headers, render_row):
    if not rows:
        return '<p style="color:#888;font-size:13px"><em>Nenhum item.</em></p>'
    th = "".join(
        f'<th style="padding:6px 10px;text-align:left;background:#333;color:#fff">{h}</th>'
        for h in headers
    )
    body = "".join(render_row(r) for r in rows)
    return f"""
    <table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:18px">
      <thead><tr>{th}</tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def build_html() -> str:
    ontem = date.today() - timedelta(days=1)
    k = _kpis_ontem()
    td = _tickets_dia()
    risco = _top_risco_sla()
    estouro = _previsao_estouro()
    anomalias = _anomalias()
    prev_hoje = _previsao_tickets_hoje()

    horas_ontem = float(k.get("horas_ontem") or 0)
    tickets_atendidos = int(k.get("tickets_atendidos") or 0)
    analistas = int(k.get("analistas_ativos") or 0)
    novos = int(td.get("novos") or 0)
    resolvidos = int(td.get("resolvidos") or 0)

    risco_html = _table(
        risco, ["Ticket", "Assunto", "Cliente", "Urgência", "Horas p/ SLA"],
        lambda r: f"""<tr>
            <td style="padding:6px 10px">#{r['ticket_id']}</td>
            <td style="padding:6px 10px">{(r['subject'] or '')[:55]}</td>
            <td style="padding:6px 10px">{r['cliente'] or '-'}</td>
            <td style="padding:6px 10px">{r['urgency'] or '-'}</td>
            <td style="padding:6px 10px;color:#C00000;font-weight:bold">
                {float(r['horas_para_sla']):.1f}h
            </td>
        </tr>""",
    )

    estouro_html = _table(
        estouro, ["Cliente", "% Previsto", "Dias restantes"],
        lambda r: f"""<tr>
            <td style="padding:6px 10px">{r['client_name']}</td>
            <td style="padding:6px 10px;color:#FF6B00;font-weight:bold">
                {float(r['pct_previsto']):.0f}%
            </td>
            <td style="padding:6px 10px">{int(r['dias_ate_fim_mes'])}d</td>
        </tr>""",
    )

    anomalias_html = _table(
        anomalias, ["Cliente", "Severidade", "Z-score", "Horas no período"],
        lambda r: f"""<tr>
            <td style="padding:6px 10px">{r['client_name']}</td>
            <td style="padding:6px 10px"><strong>{r['severidade']}</strong></td>
            <td style="padding:6px 10px">{float(r['z_score']):.2f}σ</td>
            <td style="padding:6px 10px">{float(r['horas_periodo']):.1f}h</td>
        </tr>""",
    )

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:780px;margin:0 auto">
      <h2 style="color:#7c3aed;border-bottom:2px solid #eee;padding-bottom:8px">
        📊 Movidesk BI — Digest diário · {ontem.strftime('%d/%m/%Y')}
      </h2>

      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px">
        <div style="flex:1;min-width:140px;background:#1e1e2e;color:#fff;padding:14px;border-radius:8px">
          <div style="font-size:11px;opacity:0.7">HORAS ONTEM</div>
          <div style="font-size:24px;font-weight:bold">{horas_ontem:.1f}h</div>
          <div style="font-size:11px;opacity:0.6">{analistas} analistas ativos</div>
        </div>
        <div style="flex:1;min-width:140px;background:#1e1e2e;color:#fff;padding:14px;border-radius:8px">
          <div style="font-size:11px;opacity:0.7">TICKETS NOVOS</div>
          <div style="font-size:24px;font-weight:bold">{novos}</div>
          <div style="font-size:11px;opacity:0.6">{resolvidos} resolvidos</div>
        </div>
        <div style="flex:1;min-width:140px;background:#1e1e2e;color:#fff;padding:14px;border-radius:8px">
          <div style="font-size:11px;opacity:0.7">PREVISÃO HOJE</div>
          <div style="font-size:24px;font-weight:bold">{prev_hoje:.0f}</div>
          <div style="font-size:11px;opacity:0.6">tickets esperados</div>
        </div>
        <div style="flex:1;min-width:140px;background:#1e1e2e;color:#fff;padding:14px;border-radius:8px">
          <div style="font-size:11px;opacity:0.7">ATENDIDOS</div>
          <div style="font-size:24px;font-weight:bold">{tickets_atendidos}</div>
          <div style="font-size:11px;opacity:0.6">tickets com lançamento</div>
        </div>
      </div>

      <h3 style="color:#C00000">🚨 Top 5 tickets em risco de SLA (&lt;24h)</h3>
      {risco_html}

      <h3 style="color:#FF6B00">📈 Clientes com previsão de estouro</h3>
      {estouro_html}

      <h3 style="color:#FFC000">🔍 Anomalias de consumo recentes</h3>
      {anomalias_html}

      <p style="font-size:11px;color:#999;margin-top:24px;border-top:1px solid #eee;padding-top:10px">
        Gerado automaticamente pelo Movidesk BI · Desenvolvido por Gabriel Furtado
      </p>
    </div>
    """


def main():
    logger.info("Gerando digest diário...")
    html = build_html()
    subject = f"[Movidesk BI] Digest diário — {date.today().strftime('%d/%m/%Y')}"
    _send_email(subject, html)
    logger.info("Digest enviado.")


if __name__ == "__main__":
    main()
