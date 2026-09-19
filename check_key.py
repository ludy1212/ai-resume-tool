import os
from dotenv import load_dotenv

load_dotenv()
k = os.getenv("DEEPSEEK_API_KEY")

print("读到内容了吗:", k is not None)
print("长度:", len(k) if k else 0)
print("以 sk- 开头吗:", k.startswith("sk-") if k else False)
print("前后有多余空格吗:", k != k.strip() if k else None)
print("里面有换行吗:", "\n" in k if k else None)