# Conexão Power BI → PostgreSQL (Movidesk BI)

## Pré-requisitos

1. **Driver ODBC do PostgreSQL** instalado na máquina
   - Download: https://www.postgresql.org/ftp/odbc/versions/msi/
   - Instalar `psqlODBC_x64.msi` (versão 64-bit)

2. **Power BI Desktop** instalado

3. **Docker rodando** com o container do banco ativo:
   ```bash
   cd C:\Users\User\movidesk-bi
   docker-compose up -d
   ```

---

## Conectar o Power BI ao PostgreSQL

### Passo 1 — Obter dados

No Power BI Desktop:
1. Clique em **Página Inicial → Obter Dados**
2. Pesquise por **PostgreSQL** e selecione
3. Clique em **Conectar**

### Passo 2 — Configurar a conexão

| Campo    | Valor               |
|----------|---------------------|
| Servidor | `localhost`         |
| Banco de dados | `movidesk_bi` |

Modo de conectividade: **Importar** (recomendado para este projeto)

### Passo 3 — Credenciais

Quando solicitado:
- **Usuário:** `bi_user` (ou conforme `.env`)
- **Senha:** conforme variável `DB_PASSWORD` no `.env`

> Verifique os valores exatos no arquivo `.env` na raiz do projeto.

### Passo 4 — Selecionar as tabelas/views

No Navegador, expanda o schema **analytics** e selecione:

| View / Tabela | Para que serve |
|---|---|
| `analytics.v_consumo_mensal` | Dashboard de consumo por cliente |
| `analytics.v_produtividade_agentes` | Dashboard de produtividade |
| `analytics.v_tickets_abertos` | Painel de tickets em aberto |
| `analytics.v_resumo_mes_atual` | Cards KPI do mês atual |
| `analytics.v_etl_historico` | Monitor de saúde do ETL |

Clique em **Carregar** (ou **Transformar Dados** se quiser revisar antes).

---

## Dashboard Básico de Consumo

### Visuais recomendados (1ª página)

**Cards KPI (linha superior):**
- Total de horas consumidas no mês → `SUM(v_resumo_mes_atual[horas_mes_atual])`
- Qtd. de clientes ativos no mês → `DISTINCTCOUNT(v_resumo_mes_atual[client_id])`
- Qtd. de tickets abertos → `COUNTROWS(v_tickets_abertos)`

**Gráfico de barras:**
- Eixo X: `client_name`
- Valores: `horas_mes_atual`
- Fonte: `v_resumo_mes_atual`
- Ordenar por horas (decrescente)

**Tabela detalhada:**
- Colunas: `client_name`, `horas_mes_atual`, `tickets_mes_atual`, `ultimo_lancamento`
- Fonte: `v_resumo_mes_atual`

**Segmentação (filtro):**
- Filtro por `ano_mes` usando `v_consumo_mensal`

---

## Atualização dos dados

### Manual (enquanto não há agendamento)
1. No Power BI Desktop: **Página Inicial → Atualizar**
2. Isso rebusca os dados do PostgreSQL com os últimos valores

### Automática (após configurar o ETL agendado — Semana 3-4)
O ETL atualiza o banco automaticamente.  
No Power BI Desktop basta clicar em **Atualizar** após cada execução do ETL.

> Para atualização automática sem intervenção manual é necessário publicar no
> **Power BI Service** (planejado para Mês 3+).

---

## Resolução de problemas

| Problema | Solução |
|---|---|
| "Não foi possível conectar" | Verifique se o Docker está rodando: `docker ps` |
| "Driver não encontrado" | Reinstale o psqlODBC 64-bit |
| "Permissão negada" | Confirme usuário/senha no `.env` |
| Dados desatualizados | Execute o ETL: `python -m etl.main` e clique em Atualizar |
