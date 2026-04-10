# Guia Power BI — Movidesk BI
**Para o time de operações e gestores**

---

## O que é este sistema?

O Movidesk BI conecta os dados de suporte (tickets e horas lançadas) ao Power BI,
permitindo visualizar em tempo real:

- Quanto cada cliente consumiu do contrato de horas no mês
- Quais clientes estão em risco de estourar o contrato
- Produtividade de cada técnico
- Tickets abertos e tempo de espera

Os dados são atualizados automaticamente **3 vezes ao dia** (07h, 12h e 18h).

---

## Dashboard 1 — Consumo de Contrato

### O que mostra
Comparativo entre horas consumidas e horas contratadas por cliente no mês selecionado.

### Como interpretar o semáforo

| Cor | Status | Significado |
|---|---|---|
| 🟢 Verde | NORMAL | Até 60% consumido — tranquilo |
| 🟡 Amarelo | ATENÇÃO | Entre 60% e 80% — monitorar |
| 🟠 Laranja | CRÍTICO | Entre 80% e 100% — acionar cliente |
| 🔴 Vermelho | ESTOURADO | Acima de 100% — horas extrapoladas |

### Filtros disponíveis
- **Mês de referência** — selecione o mês desejado
- **Cliente** — filtre por um cliente específico
- **Status** — filtre apenas CRÍTICO ou ESTOURADO

### Principais métricas
- **Horas consumidas** — soma dos lançamentos no período
- **Horas contratadas** — conforme contrato vigente
- **% Consumo** — horas consumidas ÷ horas contratadas × 100
- **Horas disponíveis** — saldo restante do contrato

---

## Dashboard 2 — Alertas

### O que mostra
Lista de clientes que atingiram o limiar de alerta no mês atual,
ordenados pelo percentual de consumo (maior primeiro).

### Quando agir

**Status CRÍTICO (≥ 80%)**
- Avisar o cliente que está próximo do limite
- Verificar se há horas represadas não lançadas
- Avaliar necessidade de upgrade de plano

**Status ESTOURADO (≥ 100%)**
- Comunicar o cliente imediatamente
- Registrar as horas excedentes para cobrança ou desconto futuro
- Acionar o gestor comercial

### Alertas por e-mail
O sistema envia automaticamente um e-mail quando clientes atingem o limiar crítico.
Configure os destinatários nas variáveis `ALERT_EMAIL` e `ALERT_EMAIL_CC` no arquivo `.env`.

---

## Dashboard 3 — Produtividade

### O que mostra
Horas lançadas por técnico no mês, distribuição por cliente e ranking de tickets.

### Principais visuais
- **Ranking de agentes** — quem mais lançou horas no período
- **% de contribuição no time** — participação de cada técnico no total
- **Clientes atendidos** — diversidade de atendimentos
- **Top tickets** — tickets que mais consumiram horas

### Como usar
- Filtre por **time/equipe** para ver a produtividade de um grupo específico
- Compare meses para identificar variações de carga
- Identifique técnicos sobrecarregados ou ociosos

---

## Dashboard 4 — Tickets em Aberto

### O que mostra
Todos os tickets que ainda não foram resolvidos ou fechados.

### Colunas importantes
- **Dias aberto** — quantos dias desde a abertura do ticket
- **Urgência** — Low / Normal / High / Urgent
- **Responsável** — técnico designado
- **Horas lançadas** — esforço já investido

### Filtros sugeridos
- Urgência = **Urgent** ou **High** → tickets que precisam de atenção imediata
- Dias aberto > **7** → tickets potencialmente parados
- Cliente específico → visão do atendimento a um cliente

---

## Atualizando os dados manualmente

Caso precise dos dados mais recentes antes da próxima atualização automática:

1. Abra o **Power BI Desktop**
2. Clique em **Página Inicial → Atualizar**
3. Aguarde a atualização completar (normalmente menos de 1 minuto)

Para forçar uma nova coleta da API do Movidesk:
```
cd C:\Users\User\movidesk-bi
.venv\Scripts\python.exe -m etl.main
```

---

## Adicionando ou editando contratos

Os contratos de horas **não vêm do Movidesk** — são mantidos manualmente no banco.

Para adicionar um novo contrato:
1. Conecte ao banco PostgreSQL (use DBeaver, pgAdmin ou similar)
2. Execute o INSERT abaixo, substituindo os valores:

```sql
INSERT INTO analytics.contratos
    (client_id, client_name, plano_nome, horas_contratadas, vigencia_inicio)
VALUES
    ('ID_DO_CLIENTE', 'Nome do Cliente', 'Plano 20h', 20.0, '2025-04-01');
```

Para encontrar o `client_id`:
```sql
SELECT id, business_name FROM raw.clientes WHERE business_name ILIKE '%nome%';
```

Para encerrar um contrato (definir data fim):
```sql
UPDATE analytics.contratos
SET vigencia_fim = '2025-12-31'
WHERE client_id = 'ID_DO_CLIENTE' AND vigencia_fim IS NULL;
```

---

## Perguntas frequentes

**Por que o consumo de um cliente não aparece?**  
O cliente pode não ter contrato cadastrado em `analytics.contratos`.
Verifique com a query de busca acima e insira se necessário.

**Os dados estão desatualizados, o que fazer?**  
Verifique se o Docker está rodando (`docker ps`) e se o agendamento está ativo
(`Get-ScheduledTask -TaskName MovideskBI_ETL`). Então clique em Atualizar no Power BI.

**Como ver o histórico de execuções do ETL?**  
Use a view `analytics.v_etl_historico` ou o dashboard de ETL no Power BI:
```sql
SELECT * FROM analytics.v_etl_historico LIMIT 20;
```

**Um cliente quer saber quantas horas usou em meses anteriores — como ver?**  
Use o filtro de **Mês de referência** no Dashboard 1 ou consulte diretamente:
```sql
SELECT ano_mes, horas_consumidas, qtd_tickets
FROM analytics.v_consumo_mensal
WHERE client_name ILIKE '%nome do cliente%'
ORDER BY ano_mes DESC;
```
