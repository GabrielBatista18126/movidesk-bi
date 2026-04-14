"""Página: Login / Cadastro por código enviado ao e-mail."""
import streamlit as st

from dashboard import auth


def _render_step_email():
    st.markdown("### 1. Digite seu e-mail corporativo")
    st.caption(f"Aceitamos apenas e-mails {auth.EMAIL_DOMAIN}")

    with st.form("form_email", clear_on_submit=False):
        email = st.text_input(
            "E-mail",
            value=st.session_state.get("login_email", ""),
            placeholder="seu.nome@rivio.com.br",
            autocomplete="email",
        )
        nome = st.text_input(
            "Nome (apenas no primeiro acesso)",
            value=st.session_state.get("login_nome", ""),
            placeholder="Seu nome completo — opcional",
        )
        submitted = st.form_submit_button("Enviar código", type="primary", width="stretch")

    if submitted:
        email_norm = email.strip().lower()
        if not auth.email_permitido(email_norm):
            st.error(f"Somente e-mails {auth.EMAIL_DOMAIN} são aceitos.")
            return

        ok, msg = auth.enviar_codigo(email_norm)
        if not ok:
            st.error(msg)
            return

        st.session_state["login_email"] = email_norm
        st.session_state["login_nome"] = nome.strip() or None
        st.session_state["login_step"] = "code"
        st.success(msg)
        st.rerun()


def _render_step_code():
    email = st.session_state.get("login_email", "")
    st.markdown("### 2. Digite o código de 6 dígitos")
    st.caption(f"Enviamos um código para **{email}** — ele expira em {auth.CODE_TTL_MIN} min.")

    with st.form("form_code", clear_on_submit=False):
        code = st.text_input(
            "Código", max_chars=6,
            placeholder="000000",
            help="6 dígitos. Sem espaços.",
        )
        c1, c2 = st.columns([1, 1])
        submitted = c1.form_submit_button("Entrar", type="primary", width="stretch")
        reenviar = c2.form_submit_button("Reenviar código", width="stretch")

    if reenviar:
        ok, msg = auth.enviar_codigo(email)
        (st.success if ok else st.error)(msg)
        return

    if submitted:
        ok, msg = auth.validar_codigo(
            email, code, nome=st.session_state.get("login_nome"),
        )
        if not ok:
            st.error(msg)
            return

        user = auth.get_user(email)
        if user and not user.get("is_ativo"):
            st.error("Seu acesso foi desativado. Fale com o administrador.")
            return

        st.session_state["user"] = user
        # Limpa estado do fluxo de login
        for k in ("login_email", "login_nome", "login_step"):
            st.session_state.pop(k, None)
        st.success("Autenticado! Carregando...")
        st.rerun()


def _render_voltar():
    if st.button("← Usar outro e-mail"):
        for k in ("login_email", "login_nome", "login_step"):
            st.session_state.pop(k, None)
        st.rerun()


def render():
    st.markdown(
        "<h1 style='text-align:center;margin-top:40px'>📊 Movidesk BI</h1>"
        "<p style='text-align:center;color:#888;margin-bottom:40px'>"
        "Acesso restrito · login por código enviado ao e-mail</p>",
        unsafe_allow_html=True,
    )

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        with st.container(border=True):
            step = st.session_state.get("login_step", "email")
            if step == "code":
                _render_step_code()
                st.markdown("---")
                _render_voltar()
            else:
                _render_step_email()

    st.markdown(
        "<p style='text-align:center;font-size:11px;color:#666;margin-top:40px'>"
        "Desenvolvido por Gabriel Furtado</p>",
        unsafe_allow_html=True,
    )
