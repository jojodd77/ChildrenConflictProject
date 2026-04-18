import os

# 强行清空可能存在的环境变量代理，防止 PyCharm 拦截
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import time
import json
import re
import difflib

app = Flask(__name__)

sessions_db = {}


def call_agent(system_prompt, user_message, agent_name="Agent", temperature=0.3):
    try:
        print(f"\n[{agent_name}] 正在思考中...")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("缺少环境变量 OPENAI_API_KEY，请在部署平台中配置。")

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "glm-4-flash"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=temperature
        )
        content = response.choices[0].message.content
        print(f"[{agent_name}] 大模型原始回复:\n{content}\n")

        start_idx = content.find('{')
        end_idx = content.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_str = content[start_idx:end_idx + 1]
            return json.loads(json_str)
        else:
            print(f"[{agent_name}] 警告：未找到有效 JSON 格式数据！")
            return None
    except Exception as e:
        print(f"[{agent_name}] 调用或解析失败: {e}")
        return None


def get_session(code):
    if code not in sessions_db:
        sessions_db[code] = {
            "code": code,
            "participants": {"A": False, "B": False},
            "scenario": None,
            "chat": [],
            "freeze": {
                "active": False,
                "phase": "idle",
                "triggeredBy": None,
                "aMotivation": None,
                "bGuess": None,
                "result": None
            },
            "agreed": {"A": False, "B": False}
        }
    return sessions_db[code]


def format_chat_history(chat_list):
    history = []
    for msg in chat_list:
        if msg["kind"] == "chat":
            history.append(f"{msg['from']}说: {msg['text']}")
    return "\n".join(history[-8:])


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/join', methods=['POST'])
def join():
    data = request.json
    code = data.get('code')
    role = data.get('role')

    session = get_session(code)
    session["participants"][role] = True

    # ========================================================
    # 【完美修复】：要求极其生动的背景描写，且戛然而止留给孩子
    # ========================================================
    if session["scenario"] is None:
        agent1_prompt = """
        你是一个【场控Agent】，负责为7-11岁儿童生成具有丰富背景细节的社交冲突剧本。

        【核心结构：敌意归因偏误（必须遵守！）】
        故事必须具备以下完整逻辑链，缺一不可：
        1. 丰富的前情提要：交代清楚时间、地点、他们在干什么（比如：美术课上大家都在画画，或者下雨天在走廊等家长）。
        2. 突发意外：发生了一件让A受损失的倒霉事（作品被毁、东西掉落、被撞到等）。
        3. B的真实意图：B其实是好意（想帮忙）或者无意（躲避、没站稳、没看清）。
        4. 造成误会的动作：B在现场做了一个动作，让A恰好抓到了“把柄”。
        5. A的误解与情绪：A看到结果和B的动作，立刻认定B是故意的，心里非常生气。

        【绝对禁令：人称与演绎（极其重要）】
        - storyA 必须完全代入A的视角！只能用“我”代表自己，用“B”代表对方。
        - storyB 必须完全代入B的视角！只能用“我”代表自己，用“A”代表对方。
        - 绝不能把双方吵架的对话写出来！剧本必须在“A刚刚发现并感到生气，B刚刚做完动作感到委屈”这一刻戛然而止！把说话的机会留给用户去演绎。

        【内容要求】
        视角描述控制在 100-150 字左右。前因（背景）要生动具体，后果（误会）要清晰，让儿童有充足的情境代入感！

        【标准范例参考】：
        "objective_fact": "B看到A的书包快掉进水坑，想帮忙拉住，但手滑没抓住，书包掉进去了。",
        "storyA": "今天下雨了，放学后我们在学校走廊等家长。我把最喜欢的新书包放在长椅上，转头去拿水杯。突然，我看到B伸手推了我的书包一下，书包“吧嗒”一声掉进了旁边的泥水坑里，全都弄脏了！我简直气坏了，B肯定是嫉妒我的新书包，故意搞破坏！",
        "storyB": "今天下雨了，放学后我们在学校走廊等家长。我看到A的新书包放在长椅边缘，马上就要滑进旁边的泥水坑了。我赶紧跑过去想帮A拉住，但是书包太重了，我手一滑没抓住，它还是掉进去了。我真的是想帮忙的，但A转过头来狠狠地瞪着我，我心里觉得好委屈。"

        严格只返回以下JSON格式（绝不输出多余文字）：
        {
          "title": "场景标题",
          "objective_fact": "客观事实",
          "storyA": "今天...（A的视角：丰富背景 + 看到B做了什么 + 误解生气）",
          "storyB": "今天...（B的视角：丰富背景 + 真实意图 + 造成误会的动作 + 委屈）",
          "systemRule": "系统判定：你处于{arousal}唤醒状态，由{who}先发言。"
        }
        """
        # 温度调为 0.75，兼顾逻辑严密与场景丰富度
        scenario_res = call_agent(agent1_prompt, "请按模板生成一个背景生动、字数在100字左右的儿童冲突剧本。",
                                  agent_name="场控 Agent", temperature=0.75)

        if scenario_res:
            session["scenario"] = scenario_res
        else:
            session["scenario"] = {
                "title": "自然课上的植物标本",
                "objective_fact": "B看到一阵风快把A的植物标本吹跑了，想用手帮忙按住，却不小心把标本压碎了。",
                "storyA": "今天下午的自然课上，老师让我们在操场上收集树叶做标本。我找了好久，终于拼出了一只非常漂亮的树叶蝴蝶，放在长椅上晾干。我刚转过身去拿胶水，回头就看到B一巴掌拍在了我的树叶蝴蝶上，标本瞬间全碎了！我真的快气哭了，B绝对是故意的，就是见不得我做得比他好！",
                "storyB": "今天下午的自然课上，大家都在操场做树叶标本。我刚弄完自己的，一抬头发现突然刮起了一阵大风，A放在长椅上的树叶蝴蝶马上就要被风吹跑了。我急忙冲过去，想用手帮A把标本按住。结果因为跑得太急没控制好力气，一巴掌把脆弱的树叶给压碎了。我真的是想帮忙的，但是A现在红着眼睛瞪着我，我心里好难受也很委屈。",
                "systemRule": "系统判定：你处于{arousal}唤醒状态，由{who}先发言。"
            }

    if not any(m.get("meta") == "welcome" for m in session["chat"]):
        session["chat"].append({
            "id": f"sys_{time.time()}",
            "kind": "system",
            "text": "欢迎进入调解场域。请先阅读情境，再开始对话。",
            "meta": "welcome"
        })

    return jsonify(session)


@app.route('/api/sync', methods=['POST'])
def sync():
    code = request.json.get('code')
    return jsonify(get_session(code) if code else {})


@app.route('/api/send_message', methods=['POST'])
def send_message():
    data = request.json
    code = data.get('code')
    role = data.get('role')
    text = data.get('text', '').strip()

    session = get_session(code)

    if session["freeze"]["phase"] == "rephrase":
        session["freeze"]["phase"] = "negotiate"
        session["chat"].append({
            "id": f"m_{time.time()}",
            "kind": "chat",
            "from": role,
            "text": text
        })
        session["chat"].append({
            "id": f"sys_{time.time()}_neg_start",
            "kind": "system",
            "text": "系统提示：已进入妥协与规则制定阶段。请一起讨论一个可执行的方案，沟通好后点击上方的【达成一致】按钮。",
            "meta": "negotiate"
        })
    elif session["freeze"]["phase"] not in ["rephrase", "finished"] and not session["freeze"]["active"]:

        history_str = format_chat_history(session["chat"])
        scenario_title = session["scenario"]["title"]

        agent2_prompt = f"""
        你是一个专业的儿童心理学监听专家。情境是：【{scenario_title}】。对话历史：{history_str}

        【任务】：判断最新发言（[{text}]）是否应该被“强制冻结”。
        【宽容原则】：儿童在商量解决问题时，表达委屈、轻微抱怨、提出要求（如道歉赔偿），都属于正常协商，判断为 false！
        【触发红线】：只有包含严重辱骂（笨、恶心）、恶意揣测（故意害我）、或者完全拒绝沟通再次发火时，才判断为 true。

        严格返回纯 JSON：{{"is_hostile": false}}
        """
        detect_res = call_agent(agent2_prompt, f"最新发言：[{text}]", agent_name="监听 Agent", temperature=0.1)

        is_hostile = False
        if detect_res and "is_hostile" in detect_res:
            val = detect_res["is_hostile"]
            is_hostile = (val.lower() == "true") if isinstance(val, str) else bool(val)
        else:
            hostile_patterns = ['白痴', '去死', '有病', '恶心', '讨厌', '烦', '笨', '故意']
            is_hostile = any(kw in text for kw in hostile_patterns)

        session["chat"].append({
            "id": f"m_{time.time()}",
            "kind": "chat",
            "from": role,
            "text": text
        })

        if is_hostile:
            session["freeze"]["active"] = True
            session["freeze"]["phase"] = "collecting"
            session["freeze"]["triggeredBy"] = role
            session["freeze"]["aMotivation"] = None
            session["freeze"]["bGuess"] = None
            session["freeze"]["result"] = None
            session["agreed"] = {"A": False, "B": False}

            session["chat"].append({
                "id": f"sys_{time.time()}_freeze",
                "kind": "system",
                "text": "检测到对话情绪张力过高，场控Agent已强制冻结对话，阻断情绪互激。请完成弹窗双盲采集。",
                "meta": "freeze"
            })
    else:
        session["chat"].append({
            "id": f"m_{time.time()}",
            "kind": "chat",
            "from": role,
            "text": text
        })

    return jsonify(session)


@app.route('/api/submit_freeze', methods=['POST'])
def submit_freeze():
    data = request.json
    code = data.get('code')
    mode = data.get('mode')
    text = data.get('text', '').strip()

    session = get_session(code)
    if mode == 'aMotivation':
        session["freeze"]["aMotivation"] = text
    elif mode == 'bGuess':
        session["freeze"]["bGuess"] = text

    done_a = bool(session["freeze"]["aMotivation"])
    done_b = bool(session["freeze"]["bGuess"])

    if done_a and done_b:
        a_motivation_str = session["freeze"]["aMotivation"]
        b_guess_str = session["freeze"]["bGuess"]
        triggered_by = session["freeze"]["triggeredBy"]
        receiver = "B" if triggered_by == "A" else "A"

        similarity = difflib.SequenceMatcher(None, a_motivation_str, b_guess_str).ratio()
        if similarity > 0.85:
            result = {
                "misinterpretation": 0.05,
                "route": "negotiate",
                "guidance": "",
                "comfort": "",
                "triggeredBy": triggered_by
            }
        else:
            agent34_prompt = f"""
            你现在同时扮演【裁判Agent】和【引导Agent】。

            发火方填写的真实动机："{a_motivation_str}"
            被骂方猜测的动机："{b_guess_str}"

            【计算分数】：
            - 0.0 到 0.3：猜测准确（低风险）。
            - 0.4 到 0.6：猜对一半，有偏差（中风险）。
            - 0.7 到 1.0：完全猜错，充满恶意（高风险）。

            【确定流程】：
            - 如果分数 > 0.3：route 为 "rephrase"。撰写 guidance 和 comfort。
            - 如果分数 <= 0.3：route 为 "negotiate"。"guidance"和"comfort"留空。

            【话术规范 (绝对禁令)】：绝不能出现“发火方”、“被骂方”这样的词！必须像老师一样直接对他们说话（如：我知道你现在很着急...）。

            第一步："reasoning"中写推理。
            第二步：输出JSON：
            {{
                "reasoning": "推理...",
                "misinterpretation": 0.55, 
                "route": "rephrase",
                "guidance": "引导发火方...",
                "comfort": "安抚被骂方..."
            }}
            """

            judge_res = call_agent(agent34_prompt, "请分析动机，打分并提供老师口吻的安抚！", agent_name="裁判&引导 Agent",
                                   temperature=0.1)

            if judge_res:
                try:
                    mis_score = float(judge_res.get("misinterpretation", 0.5))
                except ValueError:
                    mis_score = 0.5

                route = "rephrase" if mis_score > 0.3 else "negotiate"
                guidance = judge_res.get("guidance", "")
                comfort = judge_res.get("comfort", "")

                if route == "negotiate":
                    guidance = ""
                    comfort = ""
                else:
                    if "发火方" in guidance or "的建议" in guidance or len(guidance) < 5:
                        guidance = "你的感受很正常，但发脾气会让人害怕。试着用‘我希望/我需要’来重新表达你的想法吧。"
                    if "被骂方" in comfort or "的安抚" in comfort or len(comfort) < 5:
                        comfort = "抱抱你，莫名其妙被指责肯定委屈。对方现在太着急了产生误会，我们等他冷静下来好好说。"

                result = {
                    "misinterpretation": mis_score,
                    "guidance": guidance,
                    "comfort": comfort,
                    "route": route,
                    "triggeredBy": triggered_by
                }
            else:
                mis_score = 0.92 if any(kw in b_guess_str for kw in ["霸道", "嫉妒", "故意", "坏", "抢"]) else 0.45
                result = {
                    "misinterpretation": mis_score,
                    "guidance": "你的感受很正常，但指责没用。试着用‘我希望/我需要’重新表达。",
                    "comfort": "抱抱你，他现在可能有点误会，我们等他冷静下来重新说。",
                    "route": "rephrase" if mis_score > 0.3 else "negotiate",
                    "triggeredBy": triggered_by
                }

        session["freeze"]["result"] = result
        session["freeze"]["active"] = False
        session["freeze"]["phase"] = "rephrase" if result["route"] == "rephrase" else "negotiate"

        session["chat"].append({
            "id": f"judge_{time.time()}",
            "kind": "judgeCard",
            "extra": result
        })

        if result["route"] == "rephrase":
            session["chat"].append({
                "id": f"sys_{time.time()}_guide",
                "kind": "system",
                "text": f"引导Agent：{result.get('guidance', '请换一种更温和的方式表达吧。')}",
                "meta": "rephrase",
                "target": triggered_by
            })
            session["chat"].append({
                "id": f"sys_{time.time()}_comfort",
                "kind": "system",
                "text": f"引导Agent：{result.get('comfort', '抱抱你，可能中间有些误会，我们等对方重新说。')}",
                "meta": "rephrase",
                "target": receiver
            })
        else:
            session["chat"].append({
                "id": f"sys_{time.time()}_neg",
                "kind": "system",
                "text": "系统提示：你们的心电波对齐啦！对方准确理解了你的意图。已进入规则制定阶段，请讨论一个可执行的方案。",
                "meta": "negotiate"
            })
    else:
        msg_text = "一方已提交动机，等待另一方提交…"
        if not any(m.get("text") == msg_text for m in session["chat"]):
            session["chat"].append({
                "id": f"sys_{time.time()}_wait",
                "kind": "system",
                "text": msg_text,
                "meta": "waiting"
            })

    return jsonify(session)


@app.route('/api/agree', methods=['POST'])
def agree():
    data = request.json
    code = data.get('code')
    role = data.get('role')

    session = get_session(code)
    session["agreed"][role] = True

    if session["agreed"]["A"] and session["agreed"]["B"]:
        session["freeze"]["phase"] = "finished"
        session["chat"].append({
            "id": f"sys_{time.time()}_celeb",
            "kind": "system",
            "text": "太棒了！因为你们成功合作，调解训练顺利结束，你们都拿到了 🌸 小红花！",
            "meta": "celebrate"
        })
        session["chat"].append({
            "id": f"sys_{time.time()}_feel_A",
            "kind": "system",
            "text": "场控Agent：回想一下最开始生气的时刻，再看看现在，你心里的感觉怎么样？沟通是不是比吵架更有用呢😊",
            "meta": "finished",
            "target": "A"
        })
        session["chat"].append({
            "id": f"sys_{time.time()}_enc_A",
            "kind": "system",
            "text": "引导Agent：你今天做得很棒！你学会了说出‘我需要’而不是发脾气，你用沟通解开了误会！",
            "meta": "finished",
            "target": "A"
        })
        session["chat"].append({
            "id": f"sys_{time.time()}_enc_B",
            "kind": "system",
            "text": "引导Agent：你是个善解人意的好搭档！你愿意倾听和剥离情绪，没有陷入争吵，你做得很好！",
            "meta": "finished",
            "target": "B"
        })
    else:
        session["chat"].append({
            "id": f"sys_{time.time()}_wait_agree",
            "kind": "system",
            "text": f"身份 {role} 已点击达成一致，等待另一方确认...",
            "meta": "waiting"
        })

    return jsonify(session)


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')