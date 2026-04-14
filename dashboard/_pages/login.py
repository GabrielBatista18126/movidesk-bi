"""Página: Login com e-mail + senha; força troca no 1º acesso."""
import streamlit as st

from dashboard import auth


def _render_form_login():
    st.markdown("### Entrar")
    st.caption(f"Acesso restrito a e-mails {auth.EMAIL_DOMAIN}.")

    with st.form("form_login", clear_on_submit=False):
        email = st.text_input(
            "E-mail",
            value=st.session_state.get("login_email", ""),
            placeholder="seu.nome@rivio.com.br",
            autocomplete="email",
        )
        senha = st.text_input(
            "Senha",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Entrar", type="primary", width="stretch")

    if submitted:
        email_norm = email.strip().lower()
        ok, msg, user = auth.autenticar(email_norm, senha)
        if not ok:
            st.error(msg)
            return

        if user.get("must_change_password"):
            st.session_state["pending_user"] = user
            st.session_state["login_step"] = "change"
            st.rerun()

        st.session_state["user"] = user
        st.success("Autenticado! Carregando...")
        st.rerun()


def _render_form_troca_senha():
    user = st.session_state.get("pending_user")
    if not user:
        st.session_state["login_step"] = "login"
        st.rerun()

    st.markdown("### 🔒 Troque sua senha")
    st.caption(
        f"Primeiro acesso de **{user['email']}** — defina uma senha pessoal "
        f"antes de continuar."
    )

    with st.form("form_troca", clear_on_submit=False):
        nova = st.text_input(
            "Nova senha", type="password", autocomplete="new-password",
            help=f"Mínimo {auth.MIN_PASSWORD_LEN} caracteres, com letra e número.",
        )
        confirm = st.text_input(
            "Confirme a nova senha", type="password", autocomplete="new-password",
        )
        submitted = st.form_submit_button("Salvar e entrar", type="primary", width="stretch")

    if submitted:
        if nova != confirm:
            st.error("As senhas não coincidem.")
            return
        ok, msg = auth.alterar_senha(user["email"], nova)
        if not ok:
            st.error(msg)
            return

        fresh = auth.get_user(user["email"])
        st.session_state["user"] = fresh
        st.session_state.pop("pending_user", None)
        st.session_state.pop("login_step", None)
        st.success("Senha atualizada. Carregando...")
        st.rerun()


def _render_cancelar():
    if st.button("← Cancelar e voltar ao login"):
        for k in ("pending_user", "login_step"):
            st.session_state.pop(k, None)
        st.rerun()


def render():
    st.markdown(
        "<h1 style='text-align:center;margin-top:40px'>📊 Movidesk BI</h1>"
        "<p style='text-align:center;color:#888;margin-bottom:40px'>"
        "Acesso restrito · login com e-mail e senha</p>",
        unsafe_allow_html=True,
    )

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        with st.container(border=True):
            step = st.session_state.get("login_step", "login")
            if step == "change":
                _render_form_troca_senha()
                st.markdown("---")
                _render_cancelar()
            else:
                _render_form_login()

    st.markdown(
        "<p style='text-align:center;font-size:11px;color:#666;margin-top:40px'>"
        "Desenvolvido por Gabriel Furtado</p>",
        unsafe_allow_html=True,
    )
