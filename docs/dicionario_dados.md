# Dicionário de Dados — Movidesk BI

**Última atualização:** 2026-04-13
**Banco de dados:** PostgreSQL 15
**Schemas:** `raw` (dados brutos) | `analytics` (star schema + views)

---

## Schema `raw` — Dados brutos da API

### `raw.clientes`
Clientes importados da API Movidesk (persons do tipo organização).

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | VARCHAR(50) PK | ID interno do Movidesk |
| `business_name` | VARCHAR(255) | Razão social ou nome do cliente |
| `email` | VARCHAR(255) | E-mail principal |
| `cpf_cnpj` | VARCHAR(20) | CPF ou CNPJ sem formatação |
| `is_active` | BOOLEAN | Indica se o cliente está ativo |
| `created_date` | TIMESTAMPTZ | Data de cadastro no Movidesk |
| `profile_type` | VARCHAR(50) | `"Organization"` ou `"Person"` |
| `created_at` | TIMESTAMPTZ | Data de ingestão no banco |
| `updated_at` | TIMESTAMPTZ | Data da última atualização pelo ETL |

---

### `raw.agentes`
Técnicos e colaboradores internos (persons do tipo agente).

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | VARCHAR(50) PK | ID interno do Movidesk |
| `business_name` | VARCHAR(255) | Nome completo do agente |
| `email` | VARCHAR(255) | E-mail corporativo |
| `team` | VARCHAR(100) | Time/equipe ao qual pertence |
| `is_active` | BOOLEAN | Agente ativo no Movidesk |
| `created_at` | TIMESTAMPTZ | Data de ingestão |
| `updated_at` | TIMESTAMPTZ | Data da última atualização |

---

### `raw.tickets`
Tickets de suporte importados do Movidesk.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | VARCHAR(50) PK | ID do ticket no Movidesk |
| `subject` | VARCHAR(500) | Título/assunto do ticket |
| `status` | VARCHAR(50) | `New` \| `InAttendance` \| `Resolved` \| `Closed` |
| `ticket_type` | VARCHAR(50) | `Incident` \| `Request` \| `Problem` |
| `category` | VARCHAR(100) | Categoria do ticket |
| `urgency` | VARCHAR(50) | `Low` \| `Normal` \| `High` \| `Urgent` |
| `client_id` | VARCHAR(50) FK | Referência a `raw.clientes.id` |
| `owner_id` | VARCHAR(50) FK | Agente responsável → `raw.agentes.id` |
| `owner_team` | VARCHAR(100) | Time do agente responsável |
| `created_date` | TIMESTAMPTZ | Abertura do ticket |
| `resolved_date` | TIMESTAMPTZ | Data de resolução (NULL se não resolvido) |
| `closed_date` | TIMESTAMPTZ | Data de fechamento (NULL se não fechado) |
| `last_update` | TIMESTAMPTZ | Última modificação no Movidesk |
| `time_spent_total_hours` | NUMERIC(10,4) | Soma de todas as horas lançadas no ticket |
| `organization_id` | VARCHAR(50) | Organização do solicitante |
| `organization_name` | VARCHAR(255) | Nome da organização (denormalizado) |
| `requester_id` | VARCHAR(50) | ID do solicitante |
| `requester_name` | VARCHAR(255) | Nome do solicitante |
| `first_action_date` | TIMESTAMPTZ | **Primeira ação de agente** (origin ≠ 0). Base do TTFR |
| `sla_response_date` | TIMESTAMPTZ | Prazo SLA de primeira resposta (Movidesk) |
| `sla_solution_date` | TIMESTAMPTZ | Prazo SLA de solução (Movidesk) |
| `reopened_date` | TIMESTAMPTZ | Quando o ticket foi reaberto (NULL se nunca) |
| `created_at` | TIMESTAMPTZ | Data de ingestão |
| `updated_at` | TIMESTAMPTZ | Data da última atualização |

---

### `raw.time_entries`
Lançamentos de horas por ticket (grain: um lançamento por agente/ticket/dia).

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | VARCHAR(50) PK | ID do lançamento no Movidesk |
| `ticket_id` | VARCHAR(50) FK | Ticket relacionado → `raw.tickets.id` |
| `ticket_subject` | VARCHAR(500) | Título do ticket (denormalizado) |
| `agent_id` | VARCHAR(50) FK | Agente que lançou → `raw.agentes.id` |
| `agent_name` | VARCHAR(255) | Nome do agente (denormalizado) |
| `client_id` | VARCHAR(50) FK | Cliente do ticket → `raw.clientes.id` |
| `client_name` | VARCHAR(255) | Nome do cliente (denormalizado) |
| `hours_spent` | NUMERIC(10,4) | Horas gastas neste lançamento |
| `entry_date` | TIMESTAMPTZ | Data/hora do lançamento |
| `description` | TEXT | Descrição das atividades realizadas |
| `created_at` | TIMESTAMPTZ | Data de ingestão |
| `updated_at` | TIMESTAMPTZ | Data da última atualização |

---

### `raw.etl_watermark`
Controla a última execução bem-sucedida do ETL por tabela.

| Coluna | Tipo | Descrição |
|---|---|---|
| `table_name` | VARCHAR(100) PK | Nome da tabela (`clientes`, `tickets`, etc.) |
| `last_run` | TIMESTAMPTZ | Timestamp da última ingestão bem-sucedida |

---

### `raw.etl_log`
Histórico de execuções do pipeline ETL.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL PK | ID sequencial |
| `started_at` | TIMESTAMPTZ | Início da execução |
| `finished_at` | TIMESTAMPTZ | Fim da execução (NULL se ainda rodando) |
| `status` | VARCHAR(20) | `RUNNING` \| `SUCCESS` \| `FAILURE` |
| `records_in` | INTEGER | Total de registros processados |
| `error_msg` | TEXT | Mensagem de erro (apenas se FAILURE) |
| `full_load` | BOOLEAN | `true` se foi uma carga completa |

---

## Schema `analytics` — Camada analítica

### Dimensões (star schema)

#### `analytics.dim_tempo`
Calendário pré-gerado de 2020 a 2030. Chave de join: `TO_CHAR(data, 'YYYYMMDD')::INT`.

| Coluna | Tipo | Descrição |
|---|---|---|
| `tempo_key` | INTEGER PK | Data no formato YYYYMMDD |
| `data` | DATE | Data completa |
| `ano` | SMALLINT | Ano (ex: 2025) |
| `semestre` | SMALLINT | 1 ou 2 |
| `trimestre` | SMALLINT | 1 a 4 |
| `mes` | SMALLINT | 1 a 12 |
| `mes_nome` | VARCHAR(20) | "Janeiro", "Fevereiro"... |
| `mes_abrev` | CHAR(3) | "Jan", "Fev"... |
| `semana_ano` | SMALLINT | Semana ISO (1–53) |
| `dia_mes` | SMALLINT | Dia do mês (1–31) |
| `dia_semana` | SMALLINT | 1=Dom, 2=Seg, ..., 7=Sáb |
| `dia_semana_nome` | VARCHAR(15) | "Segunda-feira"... |
| `e_fim_semana` | BOOLEAN | `true` se sábado ou domingo |
| `ano_mes` | CHAR(7) | "2025-03" — para filtros mensais |

#### `analytics.dim_clientes`
Dimensão de clientes com dados de contrato denormalizados (SCD Tipo 1).

| Coluna | Tipo | Descrição |
|---|---|---|
| `cliente_key` | SERIAL PK | Chave surrogate |
| `client_id` | VARCHAR(50) NK | ID original do Movidesk |
| `business_name` | VARCHAR(255) | Razão social |
| `email` | VARCHAR(255) | E-mail |
| `cpf_cnpj` | VARCHAR(20) | CPF/CNPJ |
| `profile_type` | VARCHAR(50) | Tipo de perfil |
| `is_active` | BOOLEAN | Ativo? |
| `plano_nome` | VARCHAR(100) | Nome do plano contratado |
| `horas_contratadas` | NUMERIC(8,2) | Horas mensais do contrato vigente |
| `vigencia_inicio` | DATE | Início do contrato |
| `vigencia_fim` | DATE | Fim do contrato (NULL = sem prazo) |

#### `analytics.dim_agentes`
Dimensão de agentes/técnicos (SCD Tipo 1).

| Coluna | Tipo | Descrição |
|---|---|---|
| `agente_key` | SERIAL PK | Chave surrogate |
| `agent_id` | VARCHAR(50) NK | ID original do Movidesk |
| `business_name` | VARCHAR(255) | Nome do agente |
| `email` | VARCHAR(255) | E-mail |
| `team` | VARCHAR(100) | Time/equipe |
| `is_active` | BOOLEAN | Ativo? |

---

### Fatos (star schema)

#### `analytics.fact_consumo`
Um registro por lançamento de hora. Grain: time entry.

| Coluna | Tipo | Descrição |
|---|---|---|
| `consumo_key` | BIGSERIAL PK | Chave surrogate |
| `time_entry_id` | VARCHAR(50) NK | ID original do lançamento |
| `tempo_key` | INTEGER FK | Data do lançamento → `dim_tempo` |
| `cliente_key` | INTEGER FK | Cliente → `dim_clientes` |
| `agente_key` | INTEGER FK | Agente → `dim_agentes` |
| `ticket_id` | VARCHAR(50) | Ticket relacionado |
| `ticket_subject` | VARCHAR(500) | Título do ticket |
| `horas_gastas` | NUMERIC(10,4) | Horas deste lançamento |
| `mes_referencia` | CHAR(7) | "YYYY-MM" — partição lógica |

#### `analytics.fact_tickets`
Um registro por ticket. Grain: ticket.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ticket_key` | BIGSERIAL PK | Chave surrogate |
| `ticket_id` | VARCHAR(50) NK | ID original do ticket |
| `tempo_abertura_key` | INTEGER FK | Data de abertura → `dim_tempo` |
| `tempo_resolucao_key` | INTEGER FK | Data de resolução (NULL se aberto) |
| `tempo_fechamento_key` | INTEGER FK | Data de fechamento (NULL se aberto) |
| `cliente_key` | INTEGER FK | Cliente → `dim_clientes` |
| `agente_key` | INTEGER FK | Agente responsável → `dim_agentes` |
| `status` | VARCHAR(50) | Status atual do ticket |
| `ticket_type` | VARCHAR(50) | Tipo: Incident, Request, Problem |
| `category` | VARCHAR(100) | Categoria |
| `urgency` | VARCHAR(50) | Urgência: Low, Normal, High, Urgent |
| `owner_team` | VARCHAR(100) | Time responsável |
| `time_spent_total_hours` | NUMERIC(10,4) | Total de horas lançadas |
| `dias_para_resolver` | INTEGER | SLA: dias até resolução (NULL se aberto) |
| `dias_para_fechar` | INTEGER | Dias até fechamento (NULL se aberto) |
| `esta_aberto` | BOOLEAN | `true` se não Resolved/Closed |

---

### Tabelas de referência

#### `analytics.contratos`
Contratos de horas mensais por cliente — gerenciado pela página `📄 Contratos` do dashboard.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL PK | ID sequencial |
| `client_id` | VARCHAR(50) FK | Cliente → `raw.clientes.id` |
| `client_name` | VARCHAR(255) | Nome do cliente (denormalizado) |
| `plano_nome` | VARCHAR(100) | Nome comercial do plano |
| `horas_contratadas` | NUMERIC(8,2) | Horas mensais contratadas |
| `vigencia_inicio` | DATE | Início da vigência |
| `vigencia_fim` | DATE | Fim da vigência (NULL = sem prazo) |
| `valor_mensal` | NUMERIC(10,2) | Valor do contrato (opcional) |
| `observacoes` | TEXT | Notas adicionais |
| `tipo_contrato` | VARCHAR(30) | `mensal_fixo` \| `banco_horas_mensal` \| `banco_horas_trimestral` |
| `rollover_horas` | BOOLEAN | Se `true`, horas não usadas acumulam pro próximo ciclo |
| `hora_extra_valor` | NUMERIC(10,2) | Valor cobrado por hora excedente |
| `dia_corte` | SMALLINT | Dia do mês em que o ciclo reinicia (1–28) |
| `ativo` | BOOLEAN | Contrato ativo (false = encerrado) |

---

#### `analytics.previsoes_consumo`
Previsão de horas até o fim do mês por cliente (gerada pelo `etl/ml.py`).

| Coluna | Tipo | Descrição |
|---|---|---|
| `client_id` | VARCHAR(50) PK | Cliente |
| `client_name` | VARCHAR(255) | Nome (denormalizado) |
| `mes_referencia` | CHAR(7) PK | "YYYY-MM" |
| `horas_ate_agora` | NUMERIC(8,2) | Consumo real até hoje |
| `horas_previstas_fim` | NUMERIC(8,2) | Projeção até o último dia do mês |
| `horas_contratadas` | NUMERIC(8,2) | Limite do contrato |
| `pct_previsto` | NUMERIC(6,2) | % em relação ao contrato |
| `vai_estourar` | BOOLEAN | Projeção ultrapassa o contrato |
| `dias_ate_fim_mes` | INTEGER | Dias restantes |
| `metodo` | VARCHAR(30) | Método (atualmente `linear`) |
| `gerado_em` | TIMESTAMPTZ | Quando foi calculado |

---

#### `analytics.score_clientes`
Score de risco 0–100 por cliente (gerado pelo `etl/ml.py`).

| Coluna | Tipo | Descrição |
|---|---|---|
| `client_id` | VARCHAR(50) PK | Cliente |
| `client_name` | VARCHAR(255) | Nome |
| `score_total` | NUMERIC(5,1) | Score 0–100 |
| `classificacao` | VARCHAR(10) | `BAIXO` \| `MEDIO` \| `ALTO` \| `CRITICO` |
| `score_historico_estouro` | NUMERIC(5,1) | Componente: meses estourados / total (peso 40%) |
| `score_tendencia` | NUMERIC(5,1) | Componente: regressão linear sobre consumo (peso 30%) |
| `score_volatilidade` | NUMERIC(5,1) | Componente: desvio padrão do consumo (peso 20%) |
| `score_urgencia_tickets` | NUMERIC(5,1) | Componente: % tickets High/Urgent (peso 10%) |
| `meses_analisados` | INTEGER | Quantos meses entraram no cálculo |
| `meses_estourados` | INTEGER | Quantos desses estouraram |
| `media_consumo_pct` | NUMERIC(6,1) | Média % de consumo no período |
| `tendencia_pct_mes` | NUMERIC(6,2) | Inclinação (%/mês) |
| `gerado_em` | TIMESTAMPTZ | Quando foi calculado |

---

#### `analytics.anomalias_consumo`
Clientes com consumo acima da média histórica (Z-score). Atualizado pelo `etl/ml.py`.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL PK | — |
| `client_id` | VARCHAR(50) | Cliente |
| `client_name` | VARCHAR(255) | Nome |
| `data_detectada` | DATE | Quando a anomalia foi detectada |
| `horas_periodo` | NUMERIC(8,2) | Horas na janela analisada (default 7 dias) |
| `media_historica` | NUMERIC(8,2) | Média das janelas anteriores (até 90 dias atrás) |
| `desvio_padrao` | NUMERIC(8,2) | Desvio padrão do histórico |
| `z_score` | NUMERIC(6,2) | (atual - média) / desvio |
| `severidade` | VARCHAR(20) | `MEDIO` (z≥1.8) \| `ALTO` (z≥2.5) \| `CRITICO` (z≥3.5) |
| `gerado_em` | TIMESTAMPTZ | — |

UNIQUE (`client_id`, `data_detectada`).

---

#### `analytics.previsoes_tickets_7d`
Previsão de volume de tickets para os próximos 7 dias (sazonalidade semanal + tendência).

| Coluna | Tipo | Descrição |
|---|---|---|
| `data_prevista` | DATE PK | Dia no futuro |
| `tickets_previstos` | NUMERIC(8,2) | Volume previsto |
| `media_30d` | NUMERIC(8,2) | Média diária dos últimos 30 dias |
| `tendencia_pct` | NUMERIC(6,2) | Tendência % calculada por regressão linear |
| `gerado_em` | TIMESTAMPTZ | — |

---

### Views analíticas

| View | Descrição | Atualização |
|---|---|---|
| `analytics.v_contrato_vigente` | Contrato ativo mais recente por cliente | Automática |
| `analytics.v_consumo_mensal` | Horas consumidas por cliente por mês | Automática |
| `analytics.v_produtividade_agentes` | Horas lançadas por agente por mês | Automática |
| `analytics.v_tickets_abertos` | Tickets em aberto com tempo decorrido | Automática |
| `analytics.v_resumo_mes_atual` | KPIs do mês corrente por cliente | Automática |
| `analytics.v_etl_historico` | Histórico de execuções do ETL | Automática |
| `analytics.v_alerta_consumo` | Consumo vs. contrato com semáforo | Automática |
| `analytics.v_historico_consumo` | Série histórica consumo vs. contrato | Automática |
| `analytics.v_produtividade_detalhada` | Produtividade por agente com % do time | Automática |
| `analytics.v_top_tickets_mes` | Tickets que mais consumiram horas | Automática |
| `analytics.v_sla_tickets` | TTFR/TTR + flags `dentro_sla_response/solution` por ticket | Automática |
| `analytics.v_sla_kpis_mes` | % SLA OK, TTFR médio, TTR médio do mês | Automática |
| `analytics.v_sla_por_cliente` | Cumprimento de SLA agregado por cliente | Automática |
| `analytics.v_sla_por_categoria` | Cumprimento de SLA agregado por categoria | Automática |
| `analytics.v_tickets_risco_sla` | Tickets em aberto a < 24h de estourar SLA | Automática |
| `analytics.v_saldo_contrato` | Saldo do ciclo atual considerando rollover e dia de corte | Automática |
| `analytics.v_tickets_reabertos` | Tickets com `reopened_date` preenchido + dias após resolução | Automática |
| `analytics.v_problemas_recorrentes` | Cliente × categoria com ≥3 ocorrências em 90d | Automática |
| `analytics.v_subjects_frequentes` | Top 50 assuntos normalizados que se repetem | Automática |
