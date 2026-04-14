"""Página: Administração de usuários (apenas admin)."""
import pandas as pd
import streamlit as st

from dashboard import auth


def render():
    st.title("👤 Usuários")
    st.caption("Quem pode acessar o dashboard. Apenas admins veem esta página.")

    current_email = st.session_state["user"]["email"]

    df = auth.listar_usuarios()

    # ── KPIs ──────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("👥 Total", len(df))
    c2.metric("👑 Admins", int(df["is_admin"].sum()) if not df.empty else 0)
    c3.metric("🟢 Ativos", int(df["is_ativo"].sum()) if not df.empty else 0)

    st.markdown("---")

    # ── Tabela ────────────────────────────────────────────────────
    st.subheader("📋 Lista de usuários")
    if df.empty:
        st.info("Nenhum usuário cadastrado ainda.")
    else:
        tbl = df.copy()
        tbl["criado_em"] = pd.to_datetime(tbl["criado_em"]).dt.strftime("%Y-%m-%d %H:%M")
        tbl["ultimo_login"] = pd.to_datetime(tbl["ultimo_login"]).dt.strftime("%Y-%m-%d %H:%M")
        tbl["ultimo_login"] = tbl["ultimo_login"].fillna("—")
        tbl["is_admin"] = tbl["is_admin"].map({True: "👑 SIM", False: "—"})
        tbl["is_ativo"] = tbl["is_ativo"].map({True: "🟢 Ativo", False: "🔴 Desativado"})
        st.dataframe(
            tbl.rename(columns={
                "email": "E-mail", "nome": "Nome",
                "is_admin": "Admin", "is_ativo": "Status",
                "criado_em": "Criado em", "ultimo_login": "Último login",
            }),
            width="stretch", hide_index=True,
        )

    st.markdown("---")

    # ── Ações ─────────────────────────────────────────────────────
    st.subheader("⚙️ Gerenciar usuário")

    if df.empty:
        st.caption("Nenhum usuário para gerenciar.")
        return

    emails = df["email"].tolist()
    alvo = st.selectbox("Selecione o usuário", options=emails, key="admin_alvo")
    user = auth.get_user(alvo)
    if not user:
        st.error("Usuário não encontrado.")
        return

    is_self = alvo == current_email

    c1, c2, c3 = st.columns(3)

    with c1:
        novo_admin = st.toggle(
            "👑 Admin",
            value=bool(user["is_admin"]),
            disabled=is_self,
            help="Promove/remove privilégios de admin. Você não pode alterar isso em si mesmo.",
            key=f"admin_toggle_{alvo}",
        )
        if novo_admin != bool(user["is_admin"]):
            auth.set_admin(alvo, novo_admin)
            st.success(f"{'Promovido' if novo_admin else 'Removido'} de admin.")
            st.rerun()

    with c2:
        novo_ativo = st.toggle(
            "🟢 Ativo",
            value=bool(user["is_ativo"]),
            disabled=is_self,
            help="Se desativado, o usuário é deslogado imediatamente.",
            key=f"ativo_toggle_{alvo}",
        )
        if novo_ativo != bool(user["is_ativo"]):
            auth.set_ativo(alvo, novo_ativo)
            st.success(f"Usuário {'ativado' if novo_ativo else 'desativado'}.")
            st.rerun()

    with c3:
        if st.button("🗑️ Remover usuário", disabled=is_self, width="stretch",
                     type="secondary", key=f"del_{alvo}"):
            st.session_state[f"confirm_del_{alvo}"] = True

    if st.session_state.get(f"confirm_del_{alvo}"):
        st.warning(f"Tem certeza que deseja remover **{alvo}**? Esta ação é irreversível.")
        cc1, cc2 = st.columns(2)
        if cc1.button("✔️ Sim, remover", key=f"confirm_yes_{alvo}"):
            auth.remover_usuario(alvo)
            st.session_state.pop(f"confirm_del_{alvo}", None)
            st.success(f"Usuário {alvo} removido.")
            st.rerun()
        if cc2.button("✖️ Cancelar", key=f"confirm_no_{alvo}"):
            st.session_state.pop(f"confirm_del_{alvo}", None)
            st.rerun()
