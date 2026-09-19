import streamlit as st

# 第一次运行时初始化
if "count" not in st.session_state:
    st.session_state.count = 0

if st.button("点我"):
    st.session_state.count += 1

st.write(f"count = {st.session_state.count}")