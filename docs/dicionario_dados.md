# Dicionário de Dados — Movidesk BI

**Última atualização:** 2026-03-31  
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
Contratos de horas mensais por cliente — **mantida manualmente**.

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
