import streamlit as st

from day4_resume import analyze_experience, generate_final


def init_state() -> None:
    defaults = {
        "step": 1,
        "text": "",
        "questions": None,
        "draft": "",
        "answers": [],
        "resume": "",
        "interview": "",
        "final_ready": False,
        "analyze_error": "",
        "final_error": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()


def collect_answers_from_inputs(questions: list[str]) -> list[tuple[str, str]]:
    answers = []
    for i, question in enumerate(questions):
        reply = st.session_state.get(f"answer_{i}", "").strip()
        answers.append((question, reply or "（未提供）"))
    return answers


init_state()

st.title("简历经历改写助手")

# ---- 第 1 步：输入 ----
if st.session_state.step == 1:
    st.header("第 1 步：输入经历")

    text = st.text_area("粘贴一段经历", height=200)

    if st.button("开始分析"):
        if not text.strip():
            st.warning("请先输入内容")
        else:
            st.session_state.text = text
            st.session_state.questions = None
            st.session_state.draft = ""
            st.session_state.answers = []
            st.session_state.resume = ""
            st.session_state.interview = ""
            st.session_state.final_ready = False
            st.session_state.analyze_error = ""
            st.session_state.final_error = ""
            st.session_state.step = 2
            st.rerun()

# ---- 第 2 步：分析并补充 ----
elif st.session_state.step == 2:
    st.header("第 2 步：分析结果")

    if st.session_state.questions is None and not st.session_state.analyze_error:
        try:
            with st.spinner("AI 正在分析..."):
                questions, draft = analyze_experience(st.session_state.text)
            st.session_state.questions = questions
            st.session_state.draft = draft
            st.session_state.analyze_error = ""
        except Exception as e:
            st.session_state.analyze_error = str(e)

    if st.session_state.analyze_error:
        st.error(st.session_state.analyze_error)
        if st.button("返回修改"):
            st.session_state.step = 1
            st.session_state.questions = None
            st.session_state.analyze_error = ""
            st.rerun()
    else:
        st.subheader("【待补充清单】")
        questions = st.session_state.questions or []
        if questions:
            st.caption("请逐条补充，留空表示跳过。")
            for i, question in enumerate(questions):
                st.text_input(f"{i + 1}. {question}", key=f"answer_{i}")
        else:
            st.info("暂无需要补充的关键信息。")

        st.subheader("【初步改写】")
        st.write(st.session_state.draft)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("下一步"):
                st.session_state.answers = collect_answers_from_inputs(questions)
                st.session_state.final_ready = False
                st.session_state.final_error = ""
                st.session_state.step = 3
                st.rerun()
        with col2:
            if st.button("返回修改"):
                st.session_state.step = 1
                st.session_state.questions = None
                st.rerun()

# ---- 第 3 步：最终输出 ----
elif st.session_state.step == 3:
    st.header("完成")

    if not st.session_state.final_ready and not st.session_state.final_error:
        try:
            with st.spinner("正在生成简历版和面试版..."):
                resume, interview = generate_final(
                    st.session_state.text,
                    st.session_state.answers,
                )
            st.session_state.resume = resume
            st.session_state.interview = interview
            st.session_state.final_ready = True
            st.session_state.final_error = ""
        except Exception as e:
            st.session_state.final_error = str(e)

    if st.session_state.final_error:
        st.error(st.session_state.final_error)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("重试生成"):
                st.session_state.final_error = ""
                st.session_state.final_ready = False
                st.rerun()
        with col2:
            if st.button("返回上一步"):
                st.session_state.step = 2
                st.session_state.final_error = ""
                st.session_state.final_ready = False
                st.rerun()
    else:
        st.subheader("【第一部分：简历版】")
        st.text_area(
            "可直接复制到简历",
            value=st.session_state.resume,
            height=160,
            label_visibility="collapsed",
        )

        st.subheader("【第二部分：面试版】")
        st.markdown(st.session_state.interview)

        if st.button("重新开始"):
            reset_state()
            st.rerun()
