# Power BI Service — Refresh Automático

## Por que usar o Power BI Service?

Com o Power BI Desktop, os dados só atualizam quando você clica em **Atualizar** manualmente.  
O **Power BI Service** (cloud) permite que os relatórios se atualizem automaticamente,
sem ninguém precisar abrir o arquivo — inclusive fora do horário comercial.

---

## Arquitetura do refresh automático

```
ETL (Task Scheduler, 3x/dia)
       │
       ▼
PostgreSQL (Docker local)
       │
       ▼ On-premises Data Gateway
Power BI Service (nuvem)
       │
       ▼
Refresh agendado (Power BI Service)
       │
       ▼
Relatórios sempre atualizados para todos os usuários
```

---

## Pré-requisitos

1. Licença **Power BI Pro** ou **Premium Per User** (necessária para agendar refresh)
2. Conta Microsoft organizacional (não pessoal)
3. **Power BI Desktop** instalado localmente
4. **On-premises Data Gateway** instalado no mesmo computador que roda o Docker

---

## Passo 1 — Instalar o On-premises Data Gateway

O gateway é o "ponte" entre o PostgreSQL local e o Power BI Service na nuvem.

1. Acesse: [https://powerbi.microsoft.com/pt-br/gateway/](https://powerbi.microsoft.com/pt-br/gateway/)
2. Baixe e instale o **On-premises data gateway (modo padrão)**
3. Durante a instalação, faça login com sua conta organizacional Microsoft
4. Anote o nome do gateway criado (ex: `MAQUINA-BI`)

### Adicionar fonte de dados PostgreSQL ao gateway

No Power BI Service (app.powerbi.com):
1. Acesse **Configurações (⚙️) → Gerenciar conexões e gateways**
2. Clique no seu gateway → **Adicionar conexão**
3. Preencha:

| Campo | Valor |
|---|---|
| Tipo de conexão | PostgreSQL |
| Nome da conexão | `movidesk-bi-local` |
| Servidor | `localhost` |
| Banco de dados | `movidesk_bi` |
| Método de autenticação | Básico |
| Nome de usuário | conforme `.env` |
| Senha | conforme `.env` |

4. Clique em **Criar**

---

## Passo 2 — Publicar o relatório no Power BI Service

No Power BI Desktop:
1. Abra o arquivo `.pbix` do projeto
2. Clique em **Página Inicial → Publicar**
3. Selecione o workspace de destino (ex: `Movidesk BI`)
4. Aguarde a publicação completar

---

## Passo 3 — Configurar o refresh agendado

No Power BI Service (app.powerbi.com):
1. Acesse o workspace **Movidesk BI**
2. Clique nos **três pontos (...)** ao lado do dataset → **Configurações**
3. Expanda **Credenciais da fonte de dados**
   - Clique em **Editar credenciais** e insira usuário/senha do PostgreSQL
4. Expanda **Atualização agendada**
   - Ative **Manter seus dados atualizados**
   - Fuso horário: `(UTC-03:00) Brasília`
   - Adicione os horários: `07:30` | `12:30` | `18:30`
     *(30 min após o ETL rodar, para garantir que os dados estão no banco)*
5. Clique em **Aplicar**

---

## Passo 4 — Compartilhar com o time

No workspace **Movidesk BI**:
1. Clique em **Compartilhar** no relatório desejado
2. Adicione os e-mails dos membros do time
3. Defina permissões:
   - **Visualizador** — apenas leitura (para a maioria do time)
   - **Colaborador** — pode editar (para analistas)
   - **Administrador** — acesso total (para o responsável técnico)

---

## Monitoramento do refresh

### Ver histórico de atualizações
No Power BI Service, dataset → **Histórico de atualização**:
- ✅ Verde = atualização bem-sucedida
- ❌ Vermelho = falha (clique para ver o erro)

### Alertas de falha no refresh
1. No dataset → **Configurações → Notificação de falha de atualização**
2. Ative e informe seu e-mail
3. Você receberá um e-mail sempre que o refresh falhar

### Verificar se o ETL rodou antes do refresh
Consulte a view no banco antes de investigar o Power BI:
```sql
SELECT started_at, finished_at, status, records_in
FROM analytics.v_etl_historico
LIMIT 5;
```

---

## Solução de problemas comuns

| Problema | Causa provável | Solução |
|---|---|---|
| Refresh falha com "Gateway offline" | Docker ou máquina desligada | Verificar se a máquina está ligada e o gateway ativo |
| "Credenciais inválidas" | Senha mudou no `.env` | Atualizar credenciais no Power BI Service |
| Dados desatualizados mesmo após refresh | ETL não rodou | Verificar logs em `scripts/logs/` |
| Gateway não aparece na lista | Gateway não registrado | Reinstalar o On-premises Data Gateway |
| Refresh falha às vezes | ETL ainda está rodando | Adiar o horário do refresh em +1h |

---

## Estrutura final do projeto com Power BI Service

```
Agendamento (Windows Task Scheduler)
  ├─ 07:00 → run_etl.bat → ETL → PostgreSQL atualizado
  ├─ 12:00 → run_etl.bat → ETL → PostgreSQL atualizado
  └─ 18:00 → run_etl.bat → ETL → PostgreSQL atualizado

Power BI Service (agendamento independente)
  ├─ 07:30 → Refresh → Relatórios atualizados
  ├─ 12:30 → Refresh → Relatórios atualizados
  └─ 18:30 → Refresh → Relatórios atualizados
```
