import streamlit as st

st.title("我的第一个网页")

name = st.text_input("你叫什么名字？")

if name:
    st.write(f"你好，{name}！")