import streamlit as st

print("脚本被运行了一次！")   # 注意：看终端，不是网页

count = 0

if st.button("点我"):
    count += 1

st.write(f"count = {count}")