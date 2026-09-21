import json
import re
import time

from openai import APIError, APIConnectionError, AuthenticationError, RateLimitError

from day4_resume import create_client, format_call_error, get_api_key

MODEL = "deepseek-flash"
MAX_TOKENS = 2000
MAX_RETRIES = 2  # 首次 + 再试 2 次，共 3 次
LAST_SUCCESS_ATTEMPT: int | None = None
LAST_CALL_USAGE: dict = {"calls": 0, "tokens": 0, "seconds": 0.0}

SYSTEM_PROMPT_QUESTIONS = """你是资深面试官。请根据岗位 JD（若提供了简历则结合简历）出 5 道面试题：
2 道项目深挖、2 道技术基础、1 道行为面。
不要编造简历里没有的经历；没有简历时只根据 JD 出题。

你必须只输出一个合法 json 对象，不要输出 markdown，不要输出解释。
json 格式必须如下（字段名不可改）：
{"questions": [{"id": 1, "type": "项目深挖", "question": "请具体说明你如何推进用户调研？"}, {"id": 2, "type": "项目深挖", "question": "如果核心用户结论互相冲突，你怎么办？"}, {"id": 3, "type": "技术基础", "question": "如何用 SQL 统计周活跃用户？"}, {"id": 4, "type": "技术基础", "question": "Excel 透视表适合解决什么分析问题？"}, {"id": 5, "type": "行为面", "question": "讲一次你和同事意见不合，最后如何解决的。"}]}
type 只能是：项目深挖、技术基础、行为面。必须正好 5 道，类型数量为 2、2、1。"""

SYSTEM_PROMPT_EVALUATE = """你是面试评分官。请对候选人的回答打三维分，并给出反馈和最可能被追问的问题。
不要编造候选人没有说过的信息。

评分标准（各 1-5 分，必须是整数）：
- 完整度：1=只答一半，3=基本答完，5=有背景有结论
- 具体性：1=全是抽象词，3=说到方法，5=有具体做法和数字
- 量化程度：1=无数字，3=有1个数字，5=多个数字且有意义

你必须只输出一个合法 json 对象，不要输出 markdown，不要输出解释。
json 格式必须如下（字段名不可改）：
{"scores": {"完整度": 4, "具体性": 3, "量化程度": 2}, "feedback": "回答覆盖了背景和方法，但缺少可验证的结果数字。", "likely_followup": "这 3 条建议被采纳后，你们怎么衡量效果？"}"""


def parse_json_safely(text: str):
    """三层兜底解析 JSON：直接 loads → 剥离代码块 → 截取首尾大括号。"""
    if text is None or not str(text).strip():
        raise ValueError("空文本，无法解析 JSON。")

    raw = str(text).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法解析 JSON：{raw[:200]}")


def get_last_call_usage() -> dict:
    """返回最近一次 generate_questions / evaluate_answer 的调用次数、tokens、耗时。"""
    return dict(LAST_CALL_USAGE)


def _tokens_from_response(response) -> int:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    total = getattr(usage, "total_tokens", None)
    if total:
        return int(total)
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    return int(prompt) + int(completion)


def _record_attempt_usage(calls: int, tokens: int, seconds: float) -> None:
    global LAST_CALL_USAGE
    LAST_CALL_USAGE = {"calls": calls, "tokens": tokens, "seconds": seconds}


def _chat_json(system_prompt: str, user_content: str, action: str) -> dict:
    """JSON 模式调用：response_format + max_tokens=2000；空内容最多再试 2 次。"""
    global LAST_SUCCESS_ATTEMPT
    LAST_SUCCESS_ATTEMPT = None
    _record_attempt_usage(0, 0, 0.0)

    try:
        get_api_key()
        client = create_client()
    except Exception as e:
        raise RuntimeError(format_call_error(action, e)) from e

    last_error: Exception | None = None
    total_attempts = MAX_RETRIES + 1
    used_calls = 0
    used_tokens = 0
    used_seconds = 0.0

    for attempt in range(1, total_attempts + 1):
        try:
            started = time.perf_counter()
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=MAX_TOKENS,
            )
            used_seconds += time.perf_counter() - started
            used_calls += 1
            used_tokens += _tokens_from_response(response)
            _record_attempt_usage(used_calls, used_tokens, used_seconds)

            content = response.choices[0].message.content
            if not content or not str(content).strip():
                last_error = RuntimeError(f"第 {attempt} 次调用返回空内容")
                continue
            data = parse_json_safely(content)
            if not isinstance(data, dict):
                last_error = ValueError(f"第 {attempt} 次返回的 JSON 不是对象：{type(data).__name__}")
                continue
            LAST_SUCCESS_ATTEMPT = attempt
            return data
        except (AuthenticationError, RateLimitError, APIConnectionError, APIError) as e:
            _record_attempt_usage(used_calls, used_tokens, used_seconds)
            raise RuntimeError(format_call_error(action, e)) from e
        except ValueError as e:
            last_error = e
            continue
        except Exception as e:
            _record_attempt_usage(used_calls, used_tokens, used_seconds)
            raise RuntimeError(format_call_error(action, e)) from e

    _record_attempt_usage(used_calls, used_tokens, used_seconds)
    raise RuntimeError(
        f"{action}失败：JSON 模式连续 {total_attempts} 次无效（已重试 {MAX_RETRIES} 次）。最后错误：{last_error}"
    )


def _validate_questions(data: dict) -> list[dict]:
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("JSON 缺少 questions 列表。")
    if len(questions) != 5:
        raise ValueError(f"面试题数量应为 5 道，实际为 {len(questions)} 道。")

    cleaned = []
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("questions 中存在非对象项。")
        try:
            qid = int(item["id"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError("每道题必须包含整数 id。") from e
        qtype = str(item.get("type", "")).strip()
        question = str(item.get("question", "")).strip()
        if qtype not in {"项目深挖", "技术基础", "行为面"}:
            raise ValueError(f"题目类型不合法：{qtype}")
        if not question:
            raise ValueError(f"第 {qid} 题缺少 question 文本。")
        cleaned.append({"id": qid, "type": qtype, "question": question})

    type_counts = {
        "项目深挖": sum(1 for q in cleaned if q["type"] == "项目深挖"),
        "技术基础": sum(1 for q in cleaned if q["type"] == "技术基础"),
        "行为面": sum(1 for q in cleaned if q["type"] == "行为面"),
    }
    if type_counts != {"项目深挖": 2, "技术基础": 2, "行为面": 1}:
        raise ValueError(f"题目类型数量应为 2 道项目深挖、2 道技术基础、1 道行为面，实际为 {type_counts}。")
    return cleaned


def _validate_evaluation(data: dict) -> dict:
    scores = data.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("JSON 缺少 scores 对象。")

    cleaned_scores = {}
    for key in ("完整度", "具体性", "量化程度"):
        if key not in scores:
            raise ValueError(f"scores 缺少「{key}」。")
        try:
            value = int(scores[key])
        except (TypeError, ValueError) as e:
            raise ValueError(f"「{key}」必须是 1-5 的整数。") from e
        if value < 1 or value > 5:
            raise ValueError(f"「{key}」必须在 1-5 之间，实际为 {value}。")
        cleaned_scores[key] = value

    feedback = str(data.get("feedback", "")).strip()
    followup = str(data.get("likely_followup", "")).strip()
    if not feedback:
        raise ValueError("JSON 缺少 feedback。")
    if not followup:
        raise ValueError("JSON 缺少 likely_followup。")

    return {
        "scores": cleaned_scores,
        "feedback": feedback,
        "likely_followup": followup,
    }


def generate_questions(jd: str, resume: str = "") -> list[dict]:
    """根据岗位 JD（可选简历）生成 5 道面试题。"""
    if not jd or not str(jd).strip():
        raise ValueError("岗位 JD 不能为空。")

    user_content = f"岗位 JD：\n{str(jd).strip()}"
    if resume and str(resume).strip():
        user_content += (
            "\n\n候选人简历（请结合简历项目出题，不要编造简历中没有的信息）：\n"
            f"{str(resume).strip()}"
        )
    else:
        user_content += "\n\n候选人未提供简历，请只根据 JD 出题。"

    try:
        data = _chat_json(SYSTEM_PROMPT_QUESTIONS, user_content, "生成面试题")
        return _validate_questions(data)
    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        raise RuntimeError(f"生成面试题失败：{e}") from e


def evaluate_answer(jd: str, question: str, answer: str) -> dict:
    """对面试回答打三维分，并给出反馈和最可能的追问。"""
    if not jd or not str(jd).strip():
        raise ValueError("岗位 JD 不能为空。")
    if not question or not str(question).strip():
        raise ValueError("面试题不能为空。")
    if not answer or not str(answer).strip():
        raise ValueError("回答不能为空。")

    user_content = (
        f"岗位 JD：\n{str(jd).strip()}\n\n"
        f"面试题：\n{str(question).strip()}\n\n"
        f"候选人回答：\n{str(answer).strip()}"
    )

    try:
        data = _chat_json(SYSTEM_PROMPT_EVALUATE, user_content, "评估回答")
        return _validate_evaluation(data)
    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        raise RuntimeError(f"评估回答失败：{e}") from e


if __name__ == "__main__":
    print("=" * 50)
    print("手动测试 1：parse_json_safely")
    print("=" * 50)
    samples = {
        "直接 json.loads": '{"questions": [{"id": 1, "type": "项目深挖", "question": "Q1"}]}',
        "剥离代码块": '```json\n{"scores": {"完整度": 3, "具体性": 3, "量化程度": 1}, "feedback": "ok", "likely_followup": "为什么？"}\n```',
        "截取大括号": '模型说明如下 {"feedback": "ok", "likely_followup": "下一步？", "scores": {"完整度": 2, "具体性": 2, "量化程度": 1}} 结束',
    }
    for name, sample in samples.items():
        parsed = parse_json_safely(sample)
        print(f"  {name} -> {parsed}")
    try:
        parse_json_safely("这不是 json")
        raise SystemExit("空失败用例未触发 ValueError")
    except ValueError as e:
        print(f"  非法文本 -> ValueError: {e}")

    sample_jd = (
        "岗位：产品经理实习生\n"
        "要求：用户调研、需求分析、数据分析；熟悉 SQL 或 Excel；有互联网实习优先。"
    )
    sample_resume = (
        "某互联网公司产品部实习 3 个月。访谈 20 个核心用户，整理 8 条问题，其中 3 条被采纳。"
    )

    print("\n" + "=" * 50)
    print("手动测试 2：generate_questions")
    print("=" * 50)
    questions = generate_questions(sample_jd, sample_resume)
    print(f"  成功于第 {LAST_SUCCESS_ATTEMPT} 次调用")
    for item in questions:
        print(f"  [{item['id']}][{item['type']}] {item['question']}")

    print("\n" + "=" * 50)
    print("手动测试 3：evaluate_answer")
    print("=" * 50)
    result = evaluate_answer(
        sample_jd,
        questions[0]["question"],
        "我访谈了一些用户，整理了问题，部分被采纳，感觉还不错。",
    )
    print(f"  成功于第 {LAST_SUCCESS_ATTEMPT} 次调用")
    print(f"  scores: {result['scores']}")
    print(f"  feedback: {result['feedback']}")
    print(f"  likely_followup: {result['likely_followup']}")
    print("\n全部手动测试完成。")
