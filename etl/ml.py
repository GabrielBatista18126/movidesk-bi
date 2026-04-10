"""
ml.py — Inteligência analítica: previsão de estouro, score de risco
        e base para sugestão de upgrade de plano.

Executa APÓS o pipeline DW (etl/dw.py) completar.

Módulos:
  calcular_previsoes()   → projeta consumo até fim do mês
  calcular_scores()      → calcula score de risco 0–100 por cliente
  run_ml()               → orquestra tudo
"""
import logging
from calendar import monthrange
from datetime import date, datetime, timezone

import numpy as np
import psycopg2
from psycopg2.extras import execute_values

from . import config

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(**config.DB_CONFIG)


# ─── Previsão de consumo ──────────────────────────────────────────

def _projetar_horas(dias_passados: int, horas_ate_agora: float, total_dias_mes: int) -> float:
    """
    Projeção linear simples: taxa_diária × total_dias_mes.
    Se dias_passados == 0, retorna horas_ate_agora (sem divisão por zero).
    """
    if dias_passados <= 0:
        return horas_ate_agora
    taxa_diaria = horas_ate_agora / dias_passados
    return round(taxa_diaria * total_dias_mes, 2)


def calcular_previsoes() -> int:
    """
    Para cada cliente com contrato vigente, projeta o consumo total
    até o fim do mês atual usando taxa diária linear.

    Grava/atualiza a tabela analytics.previsoes_consumo.
    Retorna número de previsões calculadas.
    """
    hoje = date.today()
    mes_ref = hoje.strftime("%Y-%m")
    total_dias_mes = monthrange(hoje.year, hoje.month)[1]
    dias_passados = hoje.day  # dias decorridos no mês (inclui hoje)
    dias_ate_fim = total_dias_mes - hoje.day

    sql_consumo = """
        SELECT
            cv.client_id,
            cv.client_name,
            cv.horas_contratadas,
            COALESCE(SUM(te.hours_spent), 0) AS horas_ate_agora
        FROM analytics.v_contrato_vigente cv
        LEFT JOIN raw.time_entries te
            ON  te.client_id = cv.client_id
            AND DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
        GROUP BY cv.client_id, cv.client_name, cv.horas_contratadas
    """

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_consumo)
            clientes = cur.fetchall()

    if not clientes:
        logger.info("Previsões: nenhum cliente com contrato vigente encontrado.")
        return 0

    rows = []
    for client_id, client_name, horas_contratadas, horas_ate_agora in clientes:
        horas_ate_agora = float(horas_ate_agora or 0)
        horas_contratadas = float(horas_contratadas or 0)

        horas_previstas = _projetar_horas(dias_passados, horas_ate_agora, total_dias_mes)

        pct_previsto = round(
            (horas_previstas / horas_contratadas * 100) if horas_contratadas > 0 else 0, 1
        )
        vai_estourar = horas_previstas > horas_contratadas

        rows.append((
            client_id, client_name, mes_ref,
            round(horas_ate_agora, 2), horas_previstas,
            horas_contratadas, pct_previsto,
            vai_estourar, dias_ate_fim, "linear",
            datetime.now(timezone.utc),
        ))

    sql_upsert = """
        INSERT INTO analytics.previsoes_consumo (
            client_id, client_name, mes_referencia,
            horas_ate_agora, horas_previstas_fim,
            horas_contratadas, pct_previsto,
            vai_estourar, dias_ate_fim_mes, metodo, gerado_em
        ) VALUES %s
        ON CONFLICT (client_id, mes_referencia) DO UPDATE SET
            horas_ate_agora     = EXCLUDED.horas_ate_agora,
            horas_previstas_fim = EXCLUDED.horas_previstas_fim,
            pct_previsto        = EXCLUDED.pct_previsto,
            vai_estourar        = EXCLUDED.vai_estourar,
            dias_ate_fim_mes    = EXCLUDED.dias_ate_fim_mes,
            gerado_em           = EXCLUDED.gerado_em
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql_upsert, rows)
        conn.commit()

    n_estouros = sum(1 for r in rows if r[7])
    logger.info(
        "Previsões: %d clientes calculados | %d vão estourar este mês",
        len(rows), n_estouros,
    )
    return len(rows)


# ─── Score de risco ───────────────────────────────────────────────

def _normalizar(valor: float, minimo: float, maximo: float) -> float:
    """Mapeia valor para 0–100. Retorna 0 se maximo == minimo."""
    if maximo <= minimo:
        return 0.0
    return min(100.0, max(0.0, (valor - minimo) / (maximo - minimo) * 100))


def calcular_scores(meses_historico: int = 6) -> int:
    """
    Calcula score de risco 0–100 para cada cliente com contrato.

    Componentes (pesos):
      40% — histórico de estouros   (meses estourados / total analisado)
      30% — tendência de crescimento (regressão linear sobre pct_consumo)
      20% — volatilidade            (desvio padrão do consumo%)
      10% — urgência em tickets     (% tickets High/Urgent no período)

    Classificação final:
      0–24  → BAIXO
      25–49 → MEDIO
      50–74 → ALTO
      75–100 → CRITICO
    """
    sql_historico = f"""
        SELECT
            hc.client_id,
            hc.client_name,
            hc.ano_mes,
            hc.pct_consumo
        FROM analytics.v_historico_consumo hc
        WHERE hc.ano_mes >= TO_CHAR((CURRENT_DATE - INTERVAL '{meses_historico} months'), 'YYYY-MM')
        ORDER BY hc.client_id, hc.ano_mes
    """

    sql_urgencia = f"""
        SELECT
            t.client_id,
            COUNT(*) FILTER (WHERE t.urgency IN ('High', 'Urgent'))::FLOAT
                / NULLIF(COUNT(*), 0) * 100  AS pct_urgente
        FROM raw.tickets t
        WHERE t.created_date >= CURRENT_DATE - INTERVAL '{meses_historico} months'
          AND t.client_id IS NOT NULL
        GROUP BY t.client_id
    """

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_historico)
            historico_rows = cur.fetchall()
            cur.execute(sql_urgencia)
            urgencia_map = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    if not historico_rows:
        logger.info("Scores: sem histórico suficiente para calcular.")
        return 0

    # Agrupa por cliente
    from collections import defaultdict
    dados: dict[str, dict] = defaultdict(lambda: {"client_name": "", "pcts": []})
    for client_id, client_name, ano_mes, pct in historico_rows:
        dados[client_id]["client_name"] = client_name
        dados[client_id]["pcts"].append(float(pct or 0))

    scores = []
    for client_id, info in dados.items():
        pcts = info["pcts"]
        n = len(pcts)
        if n < 1:
            continue

        # ── Componente 1: histórico de estouros (0–100)
        meses_estourados = sum(1 for p in pcts if p >= 100)
        s_estouro = (meses_estourados / n) * 100

        # ── Componente 2: tendência via regressão linear (0–100)
        if n >= 2:
            x = np.arange(n, dtype=float)
            coef = float(np.polyfit(x, pcts, 1)[0])   # inclinação (% por mês)
            # normaliza: -10%/mês (queda) = 0 pts | +10%/mês (crescimento) = 100 pts
            s_tendencia = _normalizar(coef, -10, 10)
        else:
            s_tendencia = 0.0

        # ── Componente 3: volatilidade — desvio padrão (0–100)
        if n >= 2:
            std = float(np.std(pcts))
            s_volatilidade = _normalizar(std, 0, 40)
        else:
            s_volatilidade = 0.0

        # ── Componente 4: urgência de tickets (0–100)
        s_urgencia = min(100.0, urgencia_map.get(client_id, 0.0))

        # ── Score total ponderado
        score_total = round(
            s_estouro    * 0.40 +
            s_tendencia  * 0.30 +
            s_volatilidade * 0.20 +
            s_urgencia   * 0.10,
            1,
        )

        # ── Classificação
        if score_total < 25:
            classificacao = "BAIXO"
        elif score_total < 50:
            classificacao = "MEDIO"
        elif score_total < 75:
            classificacao = "ALTO"
        else:
            classificacao = "CRITICO"

        # ── Tendência em %/mês (para exibição)
        tendencia_pct_mes = round(
            float(np.polyfit(np.arange(n, dtype=float), pcts, 1)[0]) if n >= 2 else 0.0, 2
        )

        scores.append((
            client_id, info["client_name"],
            score_total, classificacao,
            round(s_estouro, 1), round(s_tendencia, 1),
            round(s_volatilidade, 1), round(s_urgencia, 1),
            n, meses_estourados,
            round(float(np.mean(pcts)), 1),
            tendencia_pct_mes,
            datetime.now(timezone.utc),
        ))

    sql_upsert = """
        INSERT INTO analytics.score_clientes (
            client_id, client_name,
            score_total, classificacao,
            score_historico_estouro, score_tendencia,
            score_volatilidade, score_urgencia_tickets,
            meses_analisados, meses_estourados,
            media_consumo_pct, tendencia_pct_mes, gerado_em
        ) VALUES %s
        ON CONFLICT (client_id) DO UPDATE SET
            client_name              = EXCLUDED.client_name,
            score_total              = EXCLUDED.score_total,
            classificacao            = EXCLUDED.classificacao,
            score_historico_estouro  = EXCLUDED.score_historico_estouro,
            score_tendencia          = EXCLUDED.score_tendencia,
            score_volatilidade       = EXCLUDED.score_volatilidade,
            score_urgencia_tickets   = EXCLUDED.score_urgencia_tickets,
            meses_analisados         = EXCLUDED.meses_analisados,
            meses_estourados         = EXCLUDED.meses_estourados,
            media_consumo_pct        = EXCLUDED.media_consumo_pct,
            tendencia_pct_mes        = EXCLUDED.tendencia_pct_mes,
            gerado_em                = EXCLUDED.gerado_em
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql_upsert, scores)
        conn.commit()

    criticos = sum(1 for s in scores if s[3] == "CRITICO")
    logger.info(
        "Scores: %d clientes calculados | %d CRITICO | %d ALTO",
        len(scores), criticos,
        sum(1 for s in scores if s[3] == "ALTO"),
    )
    return len(scores)


# ─── Alerta preditivo ─────────────────────────────────────────────

def alert_previsoes_estouro(previsoes_rows: list) -> None:
    """
    Dispara alerta por e-mail para clientes com previsão de estouro
    que ainda não estouraram (aviso antecipado).
    """
    from .alerts import _send_email
    from datetime import date

    if not previsoes_rows:
        return

    mes_ref = date.today().strftime("%B/%Y")
    rows_html = "".join(
        f"""<tr>
            <td style="padding:8px 12px">{r['client_name']}</td>
            <td style="padding:8px 12px;text-align:right">{r['horas_ate_agora']:.1f}h</td>
            <td style="padding:8px 12px;text-align:right">{r['horas_previstas_fim']:.1f}h</td>
            <td style="padding:8px 12px;text-align:right">{r['horas_contratadas']:.1f}h</td>
            <td style="padding:8px 12px;text-align:right;color:#FF6B00">
                <strong>{r['pct_previsto']:.0f}%</strong>
            </td>
            <td style="padding:8px 12px;text-align:center">{r['dias_ate_fim_mes']}d</td>
        </tr>"""
        for r in previsoes_rows
    )

    subject = f"[PREVISÃO] {len(previsoes_rows)} cliente(s) devem estourar — {mes_ref}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:750px">
      <h2 style="color:#FF6B00;border-bottom:2px solid #eee;padding-bottom:8px">
        📈 Previsão de Estouro de Contrato — {mes_ref}
      </h2>
      <p>Os clientes abaixo <strong>ainda não estouraram</strong> o contrato,
         mas a projeção indica que ultrapassarão o limite antes do fim do mês.</p>
      <table style="border-collapse:collapse;width:100%;font-size:13px">
        <thead>
          <tr style="background:#333;color:#fff">
            <th style="padding:8px 12px;text-align:left">Cliente</th>
            <th style="padding:8px 12px;text-align:right">Horas atuais</th>
            <th style="padding:8px 12px;text-align:right">Previsão fim</th>
            <th style="padding:8px 12px;text-align:right">Contratadas</th>
            <th style="padding:8px 12px;text-align:right">% Previsto</th>
            <th style="padding:8px 12px;text-align:center">Dias restantes</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="margin-top:16px;color:#555;font-size:13px">
        <strong>Ação recomendada:</strong> entrar em contato com os clientes para
        alinhar sobre as horas restantes ou discutir upgrade de plano.
      </p>
      <p style="font-size:11px;color:#999">
        Previsão baseada na taxa diária de consumo do mês atual.
        Gerado automaticamente pelo Movidesk BI em {date.today().strftime('%d/%m/%Y')}.
      </p>
    </div>
    """
    _send_email(subject, body)


# ─── Orquestrador ─────────────────────────────────────────────────

def run_ml() -> int:
    """
    Executa o pipeline de inteligência completo.
    Retorna total de registros gerados.
    """
    logger.info("── ML: iniciando previsões e scores ──")

    n_prev  = calcular_previsoes()
    n_score = calcular_scores()

    # Dispara alerta preditivo para clientes que vão estourar mas ainda não estouraram
    sql_alerta = """
        SELECT
            p.client_id, p.client_name,
            p.horas_ate_agora, p.horas_previstas_fim,
            p.horas_contratadas, p.pct_previsto, p.dias_ate_fim_mes
        FROM analytics.previsoes_consumo p
        LEFT JOIN analytics.v_resumo_mes_atual rm ON rm.client_id = p.client_id
        WHERE p.mes_referencia = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          AND p.vai_estourar = TRUE
          -- Ainda não estourou (consumo atual abaixo do contrato)
          AND COALESCE(rm.horas_mes_atual, 0) < p.horas_contratadas
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_alerta)
            cols = [d[0] for d in cur.description]
            previsoes_alerta = [dict(zip(cols, row)) for row in cur.fetchall()]

    if previsoes_alerta:
        logger.info(
            "ML: %d cliente(s) com previsão de estouro — enviando alerta preventivo",
            len(previsoes_alerta),
        )
        alert_previsoes_estouro(previsoes_alerta)

    total = n_prev + n_score
    logger.info("── ML: concluído | previsões=%d | scores=%d ──", n_prev, n_score)
    return total
