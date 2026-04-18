from openai import OpenAI

# 极简测试脚本
try:
    print("正在尝试连接智谱服务器...")
    client = OpenAI(
        api_key="b8a447348756415ca41e21d50dfd7984.HmPlU26ZFtipn5La",
        base_url="https://open.bigmodel.cn/api/paas/v4/"
    )
    response = client.chat.completions.create(
        model="glm-4-flash",
        messages=[{"role": "user", "content": "你好，请回复我收到。"}],
        timeout=10 # 设置10秒超时
    )
    print("✅ 连接成功！大模型回复：", response.choices[0].message.content)
except Exception as e:
    print("❌ 连接失败，具体错误信息是：", e)