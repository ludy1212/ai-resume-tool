import streamlit as st

from day4_resume import get_api_key
from interview_ai import evaluate_answer, generate_questions, get_last_call_usage

st.set_page_config(page_title="模拟面试助手", layout="centered")


def init_state() -> None:
    defaults = {
        "step": 1,
        "jd": "",
        "resume": "",
        "questions": None,
        "current_q": 0,
        "answers": [],
        "error": "",
        "usage": {"calls": 0, "tokens": 0, "seconds": 0.0},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()


def record_usage() -> None:
    last = get_last_call_usage()
    usage = st.session_state.usage
    usage["calls"] += int(last.get("calls", 0) or 0)
    usage["tokens"] += int(last.get("tokens", 0) or 0)
    usage["seconds"] += float(last.get("seconds", 0.0) or 0.0)


def current_question() -> dict:
    return st.session_state.questions[st.session_state.current_q]


def current_record() -> dict | None:
    answers = st.session_state.answers
    idx = st.session_state.current_q
    if not answers or idx >= len(answers):
        return None
    return answers[idx]


init_state()

try:
    get_api_key()
except Exception as e:
    st.error(str(e))
    st.stop()

st.title("模拟面试助手")
st.caption(f"第 {st.session_state.step} / 4 屏")

# ---- 第 1 屏：输入 JD + 简历 ----
if st.session_state.step == 1:
    st.header("第 1 屏：填写岗位信息")

    with st.form("input_form"):
        jd = st.text_area("岗位 JD（必填）", height=200, key="jd_input")
        resume = st.text_area("简历（选填）", height=160, key="resume_input")
        submitted = st.form_submit_button("生成面试题")

    if submitted:
        if not jd.strip():
            st.warning("请先填写岗位 JD")
        else:
            st.session_state.jd = jd.strip()
            st.session_state.resume = resume.strip()
            st.session_state.questions = None
            st.session_state.current_q = 0
            st.session_state.answers = []
            st.session_state.error = ""
            st.session_state.usage = {"calls": 0, "tokens": 0, "seconds": 0.0}
            st.session_state.step = 2
            st.rerun()

# ---- 第 2 屏：显示 5 道题 ----
elif st.session_state.step == 2:
    st.header("第 2 屏：本次面试题")

    if st.session_state.questions is None and not st.session_state.error:
        try:
            with st.spinner("正在根据 JD 生成面试题..."):
                questions = generate_questions(st.session_state.jd, st.session_state.resume)
            st.session_state.questions = questions
            st.session_state.answers = [None] * len(questions)
            st.session_state.error = ""
        except Exception as e:
            st.session_state.error = str(e)
        finally:
            record_usage()

    if st.session_state.error:
        st.error(st.session_state.error)
        retry, back = st.columns(2)
        with retry:
            if st.button("重新生成"):
                st.session_state.questions = None
                st.session_state.error = ""
                st.rerun()
        with back:
            if st.button("返回修改"):
                st.session_state.step = 1
                st.session_state.questions = None
                st.session_state.error = ""
                st.rerun()
    else:
        for item in st.session_state.questions:
            with st.container(border=True):
                st.caption(f"第 {item['id']} 题 · {item['type']}")
                st.write(item["question"])

        start, back = st.columns(2)
        with start:
            if st.button("开始作答"):
                st.session_state.current_q = 0
                st.session_state.step = 3
                st.rerun()
        with back:
            if st.button("返回修改"):
                st.session_state.step = 1
                st.session_state.questions = None
                st.session_state.error = ""
                st.rerun()

# ---- 第 3 屏：按 current_q 逐题循环 ----
elif st.session_state.step == 3:
    questions = st.session_state.questions or []
    total = len(questions)
    if not questions:
        st.header("第 3 屏：逐题作答")
        st.error("没有面试题，请返回重新生成。")
        if st.button("返回第 1 屏"):
            st.session_state.step = 1
            st.rerun()
    else:
        idx = st.session_state.current_q
        st.header("第 3 屏：逐题作答")
        st.progress((idx + 1) / total)
        st.caption(f"第 {idx + 1} / {total} 题")

        q = current_question()
        record = current_record()

        with st.container(border=True):
            st.caption(q["type"])
            st.subheader(q["question"])

        if record is None:
            st.text_area("你的回答", height=180, key=f"answer_input_{idx}")
            if st.button("提交回答"):
                answer = str(st.session_state.get(f"answer_input_{idx}", "")).strip()
                if not answer:
                    st.warning("请先作答")
                else:
                    result = None
                    try:
                        with st.spinner("正在评估回答..."):
                            result = evaluate_answer(
                                st.session_state.jd,
                                q["question"],
                                answer,
                            )
                    except Exception as e:
                        st.error(str(e))
                    finally:
                        record_usage()

                    if result is not None:
                        st.session_state.answers[idx] = {
                            "id": q["id"],
                            "type": q["type"],
                            "question": q["question"],
                            "answer": answer,
                            "scores": result["scores"],
                            "feedback": result["feedback"],
                            "likely_followup": result["likely_followup"],
                        }
                        st.session_state.error = ""
                        st.rerun()
        else:
            st.markdown("**你的回答**")
            st.write(record["answer"])

            score_cols = st.columns(3)
            for col, name in zip(score_cols, ("完整度", "具体性", "量化程度")):
                col.metric(name, f"{record['scores'][name]} / 5")

            st.markdown("**反馈**")
            st.write(record["feedback"])
            st.markdown("**最可能被追问**")
            st.write(record["likely_followup"])

            if idx + 1 < total:
                if st.button("下一题"):
                    st.session_state.current_q = idx + 1
                    st.rerun()
            else:
                if st.button("查看面试报告"):
                    st.session_state.step = 4
                    st.rerun()

# ---- 第 4 屏：面试报告 ----
elif st.session_state.step == 4:
    st.header("第 4 屏：面试报告")

    records = [item for item in st.session_state.answers if item]
    if records:
        avg_cols = st.columns(3)
        for col, name in zip(avg_cols, ("完整度", "具体性", "量化程度")):
            avg = sum(item["scores"][name] for item in records) / len(records)
            col.metric(f"平均{name}", f"{avg:.1f} / 5")

        for item in records:
            with st.expander(f"第 {item['id']} 题 · {item['type']}", expanded=False):
                st.markdown("**题目**")
                st.write(item["question"])
                st.markdown("**回答**")
                st.write(item["answer"])
                score_cols = st.columns(3)
                for col, name in zip(score_cols, ("完整度", "具体性", "量化程度")):
                    col.metric(name, f"{item['scores'][name]} / 5")
                st.markdown("**反馈**")
                st.write(item["feedback"])
                st.markdown("**最可能被追问**")
                st.write(item["likely_followup"])
    else:
        st.info("还没有作答记录。")

    usage = st.session_state.usage
    calls = int(usage.get("calls", 0) or 0)
    tokens = int(usage.get("tokens", 0) or 0)
    avg_seconds = (usage["seconds"] / calls) if calls else 0.0
    st.divider()
    st.caption(f"本次共调用 {calls} 次，累计 {tokens} tokens，平均响应 {avg_seconds:.1f} 秒")

    if st.button("重新开始"):
        reset_state()
        st.rerun()
