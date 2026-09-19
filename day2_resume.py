import os
from dotenv import load_dotenv
from openai import OpenAI, APIError, APIConnectionError, AuthenticationError, RateLimitError

load_dotenv()

SYSTEM_PROMPT = """你是一个大厂 HR，擅长把学生零散的经历改写成 STAR 结构的简历描述。
STAR 指 Situation（背景）、Task（任务）、Action（行动）、Result（结果）。
要求：结果尽量量化；每条控制在 80 字以内；
不要编造用户没有提供的信息，信息不足的地方用【待补充】标出。"""


def create_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件。")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )


def get_experience() -> str:
    print("=" * 50)
    print("简历经历改写助手")
    print("=" * 50)
    print("请输入一段实习或项目经历（可多行，输入空行结束）：\n")

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


def rewrite_experience(client: OpenAI, experience: str) -> str:
    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": experience},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("模型返回内容为空，请稍后重试。")
    return content.strip()


def main() -> None:
    try:
        client = create_client()
        experience = get_experience()
        if not experience:
            print("\n未输入有效经历，程序已退出。")
            return

        print("\n正在改写，请稍候...\n")
        result = rewrite_experience(client, experience)

        print("-" * 50)
        print("STAR 简历改写结果")
        print("-" * 50)
        print(result)
        print("-" * 50)

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
