import os
import re
from dotenv import load_dotenv
from openai import OpenAI, APIError, APIConnectionError, AuthenticationError, RateLimitError

load_dotenv()

MODEL = "deepseek-flash"

SYSTEM_PROMPT_ANALYZE = """你是一个大厂 HR，擅长把学生零散的经历改写成 STAR 结构的简历描述。
STAR 指 Situation（背景）、Task（任务）、Action（行动）、Result（结果）。
要求：结果尽量量化；每条控制在 80 字以内；
不要编造用户没有提供的信息，信息不足的地方用【待补充】标出。

请严格按下面格式输出，不要输出其他内容：

【待补充清单】
只列出缺失的关键信息，每条用一句问句表述，一条一行，用 1. 2. 3. 编号。
例如：你访谈了20人，最后有多少条建议被采纳？
如果信息已经足够，写「无」。

【初步改写】
基于现有信息写出 STAR 简历描述，缺失处保留【待补充】。"""

SYSTEM_PROMPT_FINAL = """你是一个大厂 HR，擅长把学生零散的经历改写成可直接使用的简历描述和面试口述稿。
不要编造用户没有提供的信息。用户未提供的细节不要编造数字、成果或职责。

请根据原始经历和用户补充，严格按下面格式输出，不要输出其他内容。

【第一部分：简历版】
写一段紧凑描述，2-3 行，可直接粘贴进简历。
硬性要求：
- 用强动词开头（如主导、搭建、推动、落地、优化、设计、上线），禁用「负责」「参与」「协助」这类弱动词
- 必须包含至少 1 个量化数字；如果原始信息和补充里都没有可量化的数字，不要编造，在段落后单独标注：【缺少量化数据，需要补充】
- 不要用 S/T/A/R 标签，不要分行列举
- 同一件事不能重复出现两次

【第二部分：面试版】
1. STAR 四步拆解，每步 1-2 句，四步之间不要重复同一事实：
Situation：……
Task：……
Action：……
Result：……
2. 再输出一栏【面试官可能追问】，列出 3 个追问问题，每个问题附回答要点。
信息里没有的内容，回答要点里标注「需要你自己补充」，不要编造。

格式如下：
【面试官可能追问】
1. 问题
   回答要点：……
2. 问题
   回答要点：……
3. 问题
   回答要点：……"""


def get_api_key() -> str:
    """本地从 .env 读；Streamlit Cloud 从 st.secrets 读。"""
    # 线上优先
    try:
        import streamlit as st
        if "DEEPSEEK_API_KEY" in st.secrets:
            return st.secrets["DEEPSEEK_API_KEY"]
    except Exception:
        # 本地环境没有 secrets.toml，会走到这里，属于正常情况
        pass

    # 本地回退
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key

    raise RuntimeError(
        "未找到 DEEPSEEK_API_KEY：本地请检查 .env，线上请检查 Streamlit Cloud 的 Secrets。"
    )


def create_client() -> OpenAI:
    return OpenAI(
        api_key=get_api_key(),
        base_url="https://api.deepseek.com",
    )


def chat(client: OpenAI, system_prompt: str, user_content: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("模型返回内容为空，请稍后重试。")
    return content.strip()


def read_multiline(prompt: str) -> str:
    print(prompt)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            if lines:
                break
            print("内容不能为空，请重新输入：")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_analyze_result(text: str) -> tuple[list[str], str]:
    checklist_match = re.search(r"【待补充清单】", text)
    draft_match = re.search(r"【初步改写】", text)

    if checklist_match and draft_match:
        checklist_block = text[checklist_match.end():draft_match.start()]
        draft = text[draft_match.end():].strip()
    elif checklist_match:
        checklist_block = text[checklist_match.end():]
        draft = ""
    else:
        checklist_block = ""
        draft = text.strip()

    questions = extract_questions(checklist_block)
    return questions, draft


def extract_questions(block: str) -> list[str]:
    questions = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"(无|暂无|没有|无。)[。！]?", line):
            return []
        numbered = re.match(r"^(?:\d+[\.．、\)]\s*|[-*•]\s*)(.+)$", line)
        text = numbered.group(1).strip() if numbered else line
        if text:
            questions.append(text)
    return questions


def collect_answers(questions: list[str]) -> list[tuple[str, str]]:
    answers = []
    total = len(questions)
    for i, question in enumerate(questions, start=1):
        print(f"\n[{i}/{total}] {question}")
        try:
            reply = input("你的回答（直接回车表示跳过）：").strip()
        except EOFError:
            reply = ""
        if not reply:
            reply = "（未提供）"
            print("  → 已跳过")
        answers.append((question, reply))
    return answers


def build_final_user_content(experience: str, answers: list[tuple[str, str]]) -> str:
    parts = ["【原始经历】", experience, ""]
    if answers:
        parts.append("【用户补充】")
        for question, reply in answers:
            parts.append(f"问：{question}")
            parts.append(f"答：{reply}")
            parts.append("")
    else:
        parts.append("【用户补充】无")
    return "\n".join(parts).strip()


def parse_final_result(text: str) -> tuple[str, str]:
    resume_match = re.search(r"【第一部分：简历版】", text)
    interview_match = re.search(r"【第二部分：面试版】", text)

    if resume_match and interview_match:
        resume = text[resume_match.end():interview_match.start()].strip()
        interview = text[interview_match.end():].strip()
    elif interview_match:
        resume = text[:interview_match.start()].strip()
        interview = text[interview_match.end():].strip()
    elif resume_match:
        resume = text[resume_match.end():].strip()
        interview = ""
    else:
        resume = text.strip()
        interview = ""
    return resume, interview


def normalize_answers(answers) -> list[tuple[str, str]]:
    if not answers:
        return []
    if isinstance(answers, dict):
        items = answers.items()
    else:
        items = answers

    pairs = []
    for item in items:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            question, reply = item[0], item[1]
        else:
            continue
        reply_text = str(reply).strip() or "（未提供）"
        pairs.append((str(question).strip(), reply_text))
    return pairs


def format_call_error(action: str, exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        return "API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY。"
    if isinstance(exc, RateLimitError):
        return "请求过于频繁，请稍后再试。"
    if isinstance(exc, APIConnectionError):
        return "网络连接失败，请检查网络后重试。"
    if isinstance(exc, APIError):
        return f"调用 DeepSeek API 失败：{exc}"
    return f"{action}失败：{exc}"


def analyze_experience(text: str) -> tuple[list[str], str]:
    """分析经历，返回 (待补充问题列表, 初步改写文本)。不含 input/print。"""
    if not text or not str(text).strip():
        raise ValueError("经历内容不能为空。")
    try:
        client = create_client()
        result = chat(client, SYSTEM_PROMPT_ANALYZE, str(text).strip())
        questions, draft = parse_analyze_result(result)
        return questions, draft or result
    except Exception as e:
        raise RuntimeError(format_call_error("分析经历", e)) from e


def generate_final(text: str, answers) -> tuple[str, str]:
    """合并原始经历和补充信息，返回 (简历版, 面试版)。不含 input/print。"""
    if not text or not str(text).strip():
        raise ValueError("经历内容不能为空。")
    try:
        client = create_client()
        user_content = build_final_user_content(str(text).strip(), normalize_answers(answers))
        result = chat(client, SYSTEM_PROMPT_FINAL, user_content)
        resume, interview = parse_final_result(result)
        if not resume and not interview:
            raise RuntimeError("模型返回内容为空，请稍后重试。")
        return resume, interview
    except Exception as e:
        raise RuntimeError(format_call_error("生成最终版", e)) from e


def print_step(step: int, total: int, title: str) -> None:
    print()
    print("=" * 50)
    print(f"第 {step} 步 / 共 {total} 步：{title}")
    print("=" * 50)


def print_final_result(resume: str, interview: str) -> None:
    print("\n" + "=" * 50)
    print("最终输出")
    print("=" * 50)
    print("【第一部分：简历版】")
    print(resume)
    print()
    print("【第二部分：面试版】")
    print(interview)
    print("=" * 50)


def main() -> None:
    try:
        print("=" * 50)
        print("简历经历改写助手（简历版 + 面试版）")
        print("=" * 50)

        print_step(1, 3, "分析经历，找出待补充信息")
        experience = read_multiline("请输入一段实习或项目经历（可多行，输入空行结束）：\n")
        if not experience:
            print("\n未输入有效经历，程序已退出。")
            return

        print("\n正在调用 DeepSeek 分析缺失信息并生成初步改写，请稍候...")
        questions, draft = analyze_experience(experience)

        print("\n" + "-" * 50)
        print("【待补充清单】")
        print("-" * 50)
        if questions:
            for i, q in enumerate(questions, start=1):
                print(f"{i}. {q}")
        else:
            print("暂无需要补充的关键信息。")

        print("\n" + "-" * 50)
        print("【初步改写】")
        print("-" * 50)
        print(draft)

        print_step(2, 3, "逐条补充缺失信息")
        if questions:
            print(f"共 {len(questions)} 条待补充，请一条一条回答。")
            answers = collect_answers(questions)
            print("\n补充完成。")
        else:
            print("没有需要补充的问题，跳过本步。")
            answers = []

        print_step(3, 3, "生成简历版和面试版")
        print("正在把原始经历和补充信息合并后再次调用 DeepSeek，请稍候...")
        resume, interview = generate_final(experience, answers)
        print_final_result(resume, interview)
        print("\n全部完成。第一部分可直接粘贴进简历，第二部分用于面试准备。")

    except KeyboardInterrupt:
        print("\n\n已取消。")
    except Exception as e:
        print(f"错误：{e}")


if __name__ == "__main__":
    main()
