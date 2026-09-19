import streamlit as st

if "n" not in st.session_state:
    st.session_state.n = 0

x = 0

if st.button("+1"):
    x += 1
    st.session_state.n += 1

st.write(f"x = {x}   n = {st.session_state.n}")