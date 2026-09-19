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

SYSTEM_PROMPT_FINAL = """你是一个大厂 HR，擅长把学生零散的经历改写成 STAR 结构的简历描述。
STAR 指 Situation（背景）、Task（任务）、Action（行动）、Result（结果）。
要求：结果尽量量化；每条控制在 80 字以内；
不要编造用户没有提供的信息。

请根据原始经历和用户补充，输出最终版 STAR 描述。
不允许再出现【待补充】。用户未提供的细节不要编造，直接省略该细节，用已确认信息写完整句子。
只输出最终 STAR 描述，不要输出其他说明。"""


def create_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件。")
    return OpenAI(
        api_key=api_key,
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


def print_step(step: int, total: int, title: str) -> None:
    print()
    print("=" * 50)
    print(f"第 {step} 步 / 共 {total} 步：{title}")
    print("=" * 50)


def main() -> None:
    try:
        client = create_client()

        print("=" * 50)
        print("简历经历改写助手（三段式）")
        print("=" * 50)

        print_step(1, 3, "分析经历，找出待补充信息")
        experience = read_multiline("请输入一段实习或项目经历（可多行，输入空行结束）：\n")
        if not experience:
            print("\n未输入有效经历，程序已退出。")
            return

        print("\n正在调用 DeepSeek 分析缺失信息并生成初步改写，请稍候...")
        first_result = chat(client, SYSTEM_PROMPT_ANALYZE, experience)
        questions, draft = parse_analyze_result(first_result)

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
        print(draft or first_result)

        print_step(2, 3, "逐条补充缺失信息")
        if questions:
            print(f"共 {len(questions)} 条待补充，请一条一条回答。")
            answers = collect_answers(questions)
            print("\n补充完成。")
        else:
            print("没有需要补充的问题，跳过本步。")
            answers = []

        print_step(3, 3, "生成最终版 STAR 描述")
        print("正在把原始经历和补充信息合并后再次调用 DeepSeek，请稍候...")
        final_result = chat(
            client,
            SYSTEM_PROMPT_FINAL,
            build_final_user_content(experience, answers),
        )

        print("\n" + "-" * 50)
        print("最终版 STAR 描述")
        print("-" * 50)
        print(final_result)
        print("-" * 50)
        print("\n全部完成。")

    except KeyboardInterrupt:
        print("\n\n已取消。")
    except AuthenticationError:
        print("错误：API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY。")
    except RateLimitError:
        print("错误：请求过于频繁，请稍后再试。")
    except APIConnectionError:
        print("错误：网络连接失败，请检查网络后重试。")
    except APIError as e:
        print(f"错误：调用 DeepSeek API 失败：{e}")
    except RuntimeError as e:
        print(f"错误：{e}")
    except Exception as e:
        print(f"发生未知错误：{e}")


if __name__ == "__main__":
    main()
