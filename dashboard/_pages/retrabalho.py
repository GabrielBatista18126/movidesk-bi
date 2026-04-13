"""Página: Análise de Retrabalho e Recorrência."""
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import db


@st.cache_data(ttl=600)
def _clusters_descricoes(min_cluster_size: int = 2):
    """Agrupa descrições de ações por similaridade TF-IDF + KMeans simples.

    Retorna DataFrame com: cluster, top_termos, qtd, exemplos.
    """
    df = db.descricoes_para_cluster()
    if df.empty or len(df) < 5:
        return pd.DataFrame()

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
        import numpy as np
    except ImportError:
        return pd.DataFrame()

    textos = df["description"].astype(str).tolist()
    n = len(textos)
    k = max(3, min(10, n // 6))   # 3-10 clusters

    vec = TfidfVectorizer(
        max_features=500, ngram_range=(1, 2),
        stop_words=["de", "para", "com", "do", "da", "em", "que", "no", "na",
                    "dos", "das", "ao", "as", "os", "um", "uma", "se", "por"],
        min_df=2,
    )
    try:
        X = vec.fit_transform(textos)
    except ValueError:
        return pd.DataFrame()

    if X.shape[1] < 3:
        return pd.DataFrame()

    km = KMeans(n_clusters=k, n_init=5, random_state=42)
    labels = km.fit_predict(X)
    df = df.copy()
    df["cluster"] = labels

    terms = vec.get_feature_names_out()
    centros = km.cluster_centers_

    rows = []
    for c in range(k):
        top_idx = np.argsort(centros[c])[::-1][:5]
        top_terms = ", ".join(terms[i] for i in top_idx if centros[c][i] > 0)
        sub = df[df["cluster"] == c]
        if len(sub) < min_cluster_size:
            continue
        exemplo = sub["description"].iloc[0][:200]
        rows.append({
            "cluster":   c,
            "top_termos": top_terms,
            "qtd":       len(sub),
            "clientes":  sub["cliente"].nunique(),
            "exemplo":   exemplo,
        })
    return pd.DataFrame(rows).sort_values("qtd", ascending=False)


def render():
    st.title("🔁 Retrabalho e Recorrência")
    st.caption("Tickets reabertos, problemas recorrentes e clusters de demandas")

    # ── KPIs ──────────────────────────────────────────────────────
    reabertos = db.tickets_reabertos()
    recorrentes = db.problemas_recorrentes()

    k1, k2, k3 = st.columns(3)
    k1.metric("🔁 Tickets reabertos", len(reabertos))
    k2.metric("🔄 Problemas recorrentes (90d)", len(recorrentes))
    if not recorrentes.empty:
        k3.metric("⏱️ Horas em recorrentes",
                  f"{recorrentes['horas_totais'].sum():.1f}h")
    else:
        k3.metric("⏱️ Horas em recorrentes", "0h")

    st.markdown("---")

    # ── Tickets reabertos ─────────────────────────────────────────
    st.subheader("🔁 Tickets reabertos")
    if reabertos.empty:
        st.success("Nenhum ticket reaberto detectado.")
    else:
        df = reabertos.copy()
        df["Ticket"] = "#" + df["ticket_id"].astype(str)
        df["Reaberto em"] = pd.to_datetime(df["reopened_date"]).dt.strftime("%Y-%m-%d %H:%M")
        df["Dias após resolver"] = df["dias_apos_resolucao"].apply(
            lambda v: f"{v:.1f}d" if pd.notna(v) else "—"
        )
        st.dataframe(
            df.rename(columns={
                "subject": "Assunto", "cliente": "Cliente",
                "category": "Categoria", "urgency": "Urgência",
                "horas_gastas": "Horas",
            })[["Ticket", "Assunto", "Cliente", "Categoria",
                "Urgência", "Horas", "Dias após resolver", "Reaberto em"]],
            width="stretch", hide_index=True,
            height=min(500, 40 + len(df) * 35),
        )

    st.markdown("---")

    # ── Top problemas recorrentes ─────────────────────────────────
    st.subheader("🔄 Top problemas recorrentes (cliente × categoria)")
    if recorrentes.empty:
        st.info("Sem dados de recorrência nos últimos 90 dias.")
    else:
        df = recorrentes.copy()
        df["h/ticket"] = df["horas_por_ticket"].apply(
            lambda v: f"{v:.2f}h" if pd.notna(v) else "—"
        )
        st.dataframe(
            df.rename(columns={
                "cliente": "Cliente", "categoria": "Categoria",
                "qtd_tickets": "Tickets",
                "horas_totais": "Horas totais",
                "ultimo_ocorrido": "Último",
            })[["Cliente", "Categoria", "Tickets",
                "Horas totais", "h/ticket", "Último"]],
            width="stretch", hide_index=True,
            height=min(500, 40 + len(df) * 35),
        )

        # Barra: top 15 por horas
        st.markdown("### 📊 Onde estão sendo gastas as horas (top 15)")
        df_plot = df.head(15).copy()
        df_plot["Cliente · Categoria"] = (
            df_plot["cliente"].str[:25] + " · " + df_plot["categoria"].str[:25]
        )
        fig = px.bar(
            df_plot.sort_values("horas_totais"),
            x="horas_totais", y="Cliente · Categoria", orientation="h",
            text="horas_totais",
            labels={"horas_totais": "Horas", "Cliente · Categoria": ""},
            color="horas_totais", color_continuous_scale="Reds",
        )
        fig.update_traces(texttemplate="%{text:.1f}h", textposition="outside")
        fig.update_layout(
            showlegend=False, coloraxis_showscale=False,
            height=max(400, len(df_plot) * 32),
            margin=dict(l=0, r=40, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ── Clusters de descrições (TF-IDF + KMeans) ──────────────────
    st.subheader("🧩 Clusters de demandas (descrições do mês)")
    st.caption("Agrupa lançamentos similares para identificar temas recorrentes")
    clusters = _clusters_descricoes()
    if clusters.empty:
        st.info("Dados insuficientes para gerar clusters (mínimo 5 lançamentos com descrição).")
    else:
        st.dataframe(
            clusters.rename(columns={
                "cluster":     "#",
                "top_termos":  "Termos principais",
                "qtd":         "Lançamentos",
                "clientes":    "Clientes",
                "exemplo":     "Exemplo",
            })[["#", "Termos principais", "Lançamentos", "Clientes", "Exemplo"]],
            width="stretch", hide_index=True,
            height=min(500, 40 + len(clusters) * 60),
        )

    # ── Subjects mais frequentes ──────────────────────────────────
    st.markdown("---")
    st.subheader("🏷️ Assuntos mais repetidos (90d)")
    subj = db.subjects_frequentes()
    if subj.empty:
        st.caption("Sem assuntos repetidos.")
    else:
        st.dataframe(
            subj.rename(columns={
                "subject_norm":      "Assunto",
                "qtd":               "Vezes",
                "clientes_distintos": "Clientes",
                "horas_totais":      "Horas",
            }),
            width="stretch", hide_index=True,
            height=min(500, 40 + len(subj) * 35),
        )
