"""
Movidesk BI — Dashboard Streamlit
Rode com: streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

# Garante que a raiz do projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Movidesk BI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS global
st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 4px solid #7c3aed;
    }
    .badge-estourado { background:#C00000;color:#fff;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:bold }
    .badge-critico   { background:#FF6B00;color:#fff;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:bold }
    .badge-atencao   { background:#FFC000;color:#000;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:bold }
    .badge-normal    { background:#70AD47;color:#fff;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:bold }
    [data-testid="stSidebar"] { background-color: #0f0f1a; }
</style>
""", unsafe_allow_html=True)

# ── Gate de autenticação ──────────────────────────────────────────
from dashboard import auth

if "user" not in st.session_state or st.session_state["user"] is None:
    from dashboard._pages import login
    login.render()
    st.stop()

# Revalida usuário a cada execução (pega desativação em tempo real)
_current_user = auth.get_user(st.session_state["user"]["email"])
if not _current_user or not _current_user.get("is_ativo"):
    st.session_state.pop("user", None)
    st.warning("Sua sessão foi encerrada. Faça login novamente.")
    st.stop()
st.session_state["user"] = _current_user

# ── Navegação ──────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://i.imgur.com/placeholder.png", width=40) if False else None
    st.markdown("## 📊 Movidesk BI")

    # Bloco do usuário logado
    _u = st.session_state["user"]
    _nome = _u.get("nome") or _u["email"].split("@")[0]
    _badge = "👑 admin" if _u.get("is_admin") else "usuário"
    st.markdown(
        f"<div style='background:#1e1e2e;padding:10px 12px;border-radius:8px;"
        f"margin-bottom:8px;font-size:13px'>"
        f"<strong>{_nome}</strong><br>"
        f"<span style='color:#888;font-size:11px'>{_u['email']}</span><br>"
        f"<span style='color:#7c3aed;font-size:11px'>{_badge}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button("🚪 Sair", width="stretch"):
        st.session_state.pop("user", None)
        st.cache_data.clear()
        st.rerun()

    persona = st.radio(
        "Persona",
        options=["👔 Gestor", "🧑‍💻 Analista"],
        horizontal=True,
        key="persona_atual",
        label_visibility="collapsed",
    )
    st.markdown("---")

    if persona == "🧑‍💻 Analista":
        opcoes = ["🧑‍💻 Minha fila"]
    else:
        opcoes = [
            "🏠 Visão Geral",
            "📏 SLA",
            "📋 Consumo de Contrato",
            "📄 Contratos",
            "🚨 Alertas",
            "👥 Produtividade",
            "🔁 Retrabalho",
            "🎫 Tickets em Aberto",
            "🤖 Inteligência",
            "⚙️ Monitor ETL",
        ]
        if _u.get("is_admin"):
            opcoes.append("👤 Usuários")

    pagina = st.radio(
        "Navegação",
        options=opcoes,
        label_visibility="collapsed",
    )
    st.markdown("---")
    if st.button("🔄 Atualizar dados"):
        with st.spinner("Buscando dados do Movidesk..."):
            try:
                from etl.main import run
                run(full_load=False)
            except SystemExit:
                pass
            except Exception as exc:
                st.error(f"ETL falhou: {exc}")
        st.cache_data.clear()
        st.rerun()
    st.caption("Auto-refresh a cada 5 min · Cache: 2 min")
    st.markdown("<br>" * 3, unsafe_allow_html=True)
    st.markdown(
        "<div style='position:fixed;bottom:10px;left:16px;font-size:11px;"
        "color:#666;'>Desenvolvido por Gabriel Furtado</div>",
        unsafe_allow_html=True,
    )

# Auto-refresh a cada 5 minutos (300_000 ms)
st_autorefresh(interval=300_000, limit=None, key="auto_refresh")

# ── Páginas ───────────────────────────────────────────────────────
if pagina == "🏠 Visão Geral":
    from dashboard._pages import visao_geral
    visao_geral.render()

elif pagina == "📏 SLA":
    from dashboard._pages import sla
    sla.render()

elif pagina == "📋 Consumo de Contrato":
    from dashboard._pages import consumo
    consumo.render()

elif pagina == "📄 Contratos":
    from dashboard._pages import contratos
    contratos.render()

elif pagina == "🚨 Alertas":
    from dashboard._pages import alertas
    alertas.render()

elif pagina == "👥 Produtividade":
    from dashboard._pages import produtividade
    produtividade.render()

elif pagina == "🔁 Retrabalho":
    from dashboard._pages import retrabalho
    retrabalho.render()

elif pagina == "🎫 Tickets em Aberto":
    from dashboard._pages import tickets
    tickets.render()

elif pagina == "🤖 Inteligência":
    from dashboard._pages import inteligencia
    inteligencia.render()

elif pagina == "⚙️ Monitor ETL":
    from dashboard._pages import etl_monitor
    etl_monitor.render()

elif pagina == "🧑‍💻 Minha fila":
    from dashboard._pages import minha_fila
    minha_fila.render()

elif pagina == "👤 Usuários":
    if not st.session_state["user"].get("is_admin"):
        st.error("Acesso restrito a administradores.")
        st.stop()
    from dashboard._pages import usuarios
    usuarios.render()
