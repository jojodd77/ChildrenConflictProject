import os
import urllib.request
import json
import time
import difflib
from flask import Flask, render_template, request, jsonify
from openai import OpenAI

# 强行清空代理，防止拦截
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

app = Flask(__name__)

# ========================================================
# 【双引擎架构】：Upstash 数据库 + 本地内存托底
# ========================================================
UPSTASH_URL = "https://thankful-basilisk-40393.upstash.io".rstrip('/')
UPSTASH_TOKEN = "AZ3JAAIncDFkZTI3YTc0N2VlZmM0ZGM2OTY2ZDYxNmRiNDUyNjAxNXAxNDAzOTM"

# 本地内存保底
sessions_db = {}

# 【核心修复】：默认超时时间从 7.0 秒提升到 20.0 秒，给大模型充足的生成时间！
def call_agent(system_prompt, user_message, agent_name="Agent", temperature=0.3, timeout=20.0):
    try:
        print(f"\n[{agent_name}] 正在思考中 (允许最长等待 {timeout} 秒)...")
        api_key = "b8a447348756415ca41e21d50dfd7984.HmPlU26ZFtipn5La"

        client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            timeout=timeout 
        )
        response = client.chat.completions.create(
            model="glm-4-flash",
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
            return None
    except Exception as e:
        # 如果你能在控制台看到这行红字，说明 API 报错了
        print(f"[{agent_name}] ❌ 调用失败，触发保底机制: {e}")
        return None

def get_session(code):
    url = f"{UPSTASH_URL}/"
    payload = json.dumps(["GET", code]).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {UPSTASH_TOKEN}",
        "Content-Type": "application/json"
    }, method='POST')
    
    try:
        with urllib.request.urlopen(req, timeout=5.0) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data and res_data.get("result"):
                session_data = json.loads(res_data["result"])
                sessions_db[code] = session_data
                return session_data
    except Exception:
        pass 

    if code in sessions_db:
        return sessions_db[code]

    new_session = {
        "code": code,
        "participants": {"A": False, "B": False},
        "scenario": None,
        "chat": [],
        "freeze": {
            "active": False,
            "phase": "idle",
            "triggeredBy": None,
            "triggerText": None,
            "aMotivation": None,
            "bGuess": None,
            "result": None,
            "finalReport": None
        },
        "agreed": {"A": False, "B": False}
    }
    sessions_db[code] = new_session
    return new_session

def save_session(session):
    code = session["code"]
    sessions_db[code] = session
    url = f"{UPSTASH_URL}/"
    val_str = json.dumps(session, ensure_ascii=False)
    payload = json.dumps(["SET", code, val_str]).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {UPSTASH_TOKEN}",
        "Content-Type": "application/json"
    }, method='POST')
    try:
        urllib.request.urlopen(req, timeout=5.0)
    except Exception:
        pass

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

    if session["scenario"] is None:
        agent1_prompt = """
        你是一个【场控Agent】，负责为7-11岁儿童生成具有丰富背景细节的社交冲突剧本。

        【核心结构：敌意归因偏误】
        1. 丰富的前情提要：交代清楚时间、地点、他们在干什么。
        2. 突发意外：发生了一件让A受损失的倒霉事。
        3. B的真实意图：B其实是好意或无意。
        4. 造成误会的动作：B在现场做了一个动作，让A恰好抓到了“把柄”。
        5. A的误解与情绪：A认定B是故意的，心里非常生气。

        【绝对禁令】
        - storyA 必须完全代入A的视角！只能用“我”代表自己，用“B”代表对方。
        - storyB 必须完全代入B的视角！只能用“我”代表自己，用“A”代表对方。
        - 绝不能写出双方吵架的对话！在生气和委屈这一刻戛然而止。

        严格只返回JSON格式：
        {
          "title": "场景标题",
          "objective_fact": "客观事实",
          "storyA": "今天...（A的视角）",
          "storyB": "今天...（B的视角）",
          "systemRule": "你现在心里有点着急哦，请由{who}先发言吧。"
        }
        """
        # 放宽超时时间到 25 秒，保证长剧本能生成完
        scenario_res = call_agent(agent1_prompt, "请随机生成一个全新的儿童冲突剧本。", agent_name="场控 Agent", temperature=0.8, timeout=25.0)

        if scenario_res:
            for key in ["storyA", "storyB", "title", "systemRule", "objective_fact"]:
                if isinstance(scenario_res.get(key), dict):
                    vals = list(scenario_res[key].values())
                    scenario_res[key] = str(vals[0]) if vals else ""
                elif isinstance(scenario_res.get(key), list):
                    scenario_res[key] = str(scenario_res[key][0]) if scenario_res[key] else ""
                else:
                    scenario_res[key] = str(scenario_res.get(key, ""))
            
            session["scenario"] = scenario_res
        else:
            session["scenario"] = {
                "title": "自然课上的植物标本（网络超时保底剧本）",
                "objective_fact": "B看到一阵风快把A的标本吹跑了，想帮忙按住，却不小心压碎了。",
                "storyA": "今天下午的自然课上，老师让我们在操场收集树叶做标本。我刚拼出一只漂亮的树叶蝴蝶放在椅子上晾干。回头就看到B一巴掌拍在我的树叶蝴蝶上，标本瞬间全碎了！我快气哭了，B绝对是故意的，就是嫉妒我！",
                "storyB": "今天下午的自然课上，我抬头发现突然刮起一阵风，A放在长椅上的树叶蝴蝶马上要被吹跑了。我急忙冲过去想用手帮A按住。结果跑得太急没控制好力气，一巴掌把树叶压碎了。我真的是想帮忙的，但A现在红着眼睛瞪着我，我好委屈。",
                "systemRule": "你现在心里有点着急哦，请由A先发言吧。"
            }

    if not any(m.get("meta") == "welcome" for m in session["chat"]):
        session["chat"].append({
            "id": f"sys_{time.time()}",
            "kind": "system",
            "text": "法官精灵：欢迎来到魔法调解屋！请先看看上面的故事，再开始聊天吧。",
            "meta": "welcome"
        })

    save_session(session)
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
        session["chat"].append({"id": f"m_{time.time()}", "kind": "chat", "from": role, "text": text})
        session["chat"].append({"id": f"sys_{time.time()}_neg_start", "kind": "system", "text": "精灵小提示：这次的表达有了很大的进步，听起来舒服多了！现在请你们就事论事，一起商量个解决办法吧。商量好后点击上方的【我们商量好了】哦。", "meta": "negotiate"})
    elif session["freeze"]["phase"] not in ["rephrase", "finished"] and not session["freeze"]["active"]:
        
        history_str = format_chat_history(session["chat"])
        scenario_title = session["scenario"]["title"]

        agent2_prompt = f"""
        你是一个专业的儿童心理学监听专家。情境：【{scenario_title}】。对话历史：{history_str}

        【任务】：判断最新发言（[{text}]）是否应该被“强制冻结”进入调解阶段。
        【触发红线】（只要满足以下任意一条，必须绝对判定为 true！不要犹豫！）：
        1. 贴负面标签、起外号（如：讨厌鬼、神经病、笨蛋、有病、坏人）。
        2. 恶意揣测对方动机（如：你就是故意的、你嫉妒我、你成心的）。
        3. 带有攻击性的辱骂或极度不耐烦（如：闭嘴、滚、烦死人）。
        
        【宽容原则】：如果只是单纯表达难过（“我好伤心”）、陈述事实、解释原因（“我不是故意的”），判断为 false。

        严格返回纯 JSON：{{"is_hostile": true/false}}
        """
        detect_res = call_agent(agent2_prompt, f"最新发言：[{text}]", agent_name="监听 Agent", temperature=0.1, timeout=12.0)

        is_hostile = False
        if detect_res and "is_hostile" in detect_res:
            val = detect_res["is_hostile"]
            is_hostile = (val.lower() == "true") if isinstance(val, str) else bool(val)
        else:
            is_hostile = any(kw in text for kw in ['白痴', '去死', '有病', '恶心', '讨厌', '烦', '笨', '故意', '神经病', '讨厌鬼', '闭嘴', '滚'])

        session["chat"].append({"id": f"m_{time.time()}", "kind": "chat", "from": role, "text": text})

        if is_hostile:
            session["freeze"]["active"] = True
            session["freeze"]["phase"] = "collecting"
            session["freeze"]["triggeredBy"] = role
            session["freeze"]["triggerText"] = text 
            session["freeze"]["aMotivation"] = None
            session["freeze"]["bGuess"] = None
            session["freeze"]["result"] = None
            session["agreed"] = {"A": False, "B": False}

            session["chat"].append({
                "id": f"sys_{time.time()}_freeze",
                "kind": "system",
                "text": "法官精灵发现火药味有点重哦！为了不让小火苗变成大火灾，我们先暂停一下，深呼吸~ 请在弹窗里告诉精灵你的想法。",
                "meta": "freeze"
            })
    else:
        session["chat"].append({"id": f"m_{time.time()}", "kind": "chat", "from": role, "text": text})

    save_session(session)
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
        
        scenario_title = session["scenario"].get("title", "")
        objective_fact = session["scenario"].get("objective_fact", "")

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
            你同时扮演【裁判Agent】和【引导Agent】，是一只极具共情能力、充满智慧的儿童心理专家“法官精灵”。
            当前情境：{scenario_title}
            【核心客观事实真相】：{objective_fact}  <- 请务必参考这个事实来化解误会！
            发火方填写的真实动机："{a_motivation_str}"
            被骂方猜测的动机："{b_guess_str}"

            【计算误解分数(misinterpretation)】：
            - 0.0到0.3：猜测准确。
            - 0.4到0.6：猜对部分。
            - 0.7到1.0：完全猜错，恶意揣测。

            【确定流程(route)】：分数 > 0.3 为 "rephrase"，否则 "negotiate"。

            【话术规范：详细引导，就事论事】：
            语气必须温柔、童趣。必须结合【核心客观事实真相】，详细地进行分析，每段字数在60-80字左右！不能只说套话！
            
            - `guidance` (给发火方的悄悄话)：
              1. 共情：肯定TA因为遭受损失而生气的合理性。
              2. 揭示真相（就事论事）：结合【客观事实真相】，告诉TA对方其实是出于好意。
              3. 引导：鼓励TA用“我希望/我需要”重新表达感受，不要贴标签。
              
            - `comfort` (给被指责方的安抚)：
              1. 共情：肯定TA被误会后的委屈。
              2. 解释（就事论事）：解释发火方只是因为损失太着急了，没看到你的本来目的。
              3. 安抚：耐心等待对方重新表达。

            严格返回JSON格式：
            {{
                "reasoning": "分析...",
                "misinterpretation": <计算出的0.0到1.0之间的真实浮点数>, 
                "route": "rephrase" 或 "negotiate",
                "guidance": "引导文案...",
                "comfort": "安抚文案..."
            }}
            """

            judge_res = call_agent(agent34_prompt, "请结合客观事实详细打分并生成引导！", agent_name="裁判&引导 Agent", temperature=0.3, timeout=25.0)

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
                    if "发火方" in guidance or "的建议" in guidance or len(guidance) < 15:
                        guidance = f"发生这样的事你肯定很生气，我都理解。但如果直接用伤人的词语，原本出于好意的朋友也会难过的。试着用“我希望...”重新告诉对方你的想法吧！"
                    if "被骂方" in comfort or "的安抚" in comfort or len(comfort) < 15:
                        comfort = "抱抱你，好心办坏事还被指责，心里一定很委屈。他只是太着急了没发现你的善意，我们耐心等他冷静下来换个说法吧。"

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
                    "guidance": "发生这样的事你肯定很生气，我都理解。但如果直接用伤人的词语，原本出于好意的朋友也会难过的。试着用“我希望...”重新告诉对方你的想法吧！",
                    "comfort": "抱抱你，好心办坏事还被指责，心里一定很委屈。他只是太着急了没发现你的善意，我们耐心等他冷静下来换个说法吧。",
                    "route": "rephrase" if mis_score > 0.3 else "negotiate",
                    "triggeredBy": triggered_by
                }

        session["freeze"]["result"] = result
        session["freeze"]["active"] = False
        session["freeze"]["phase"] = "rephrase" if result["route"] == "rephrase" else "negotiate"
        session["chat"].append({"id": f"judge_{time.time()}", "kind": "judgeCard", "extra": result})

        if result["route"] == "rephrase":
            session["chat"].append({"id": f"sys_{time.time()}_guide", "kind": "system", "text": "精灵小提示：请看看上面卡片里的悄悄话，试着换一种温柔的方式重新说一句话吧。", "meta": "rephrase", "target": triggered_by})
            session["chat"].append({"id": f"sys_{time.time()}_comfort", "kind": "system", "text": "精灵悄悄话：对方正在整理语言，请耐心等待哦。", "meta": "rephrase", "target": receiver})
        else:
            session["chat"].append({"id": f"sys_{time.time()}_neg", "kind": "system", "text": "精灵小提示：你们的心电波对齐啦！现在一起商量个好办法吧。", "meta": "negotiate"})
    else:
        msg_text = "你已经说出真实想法啦，法官精灵正在等另一位小朋友说完..."
        if not any(m.get("text") == msg_text for m in session["chat"]):
            session["chat"].append({"id": f"sys_{time.time()}_wait", "kind": "system", "text": msg_text, "meta": "waiting"})

    save_session(session)
    return jsonify(session)

@app.route('/api/agree', methods=['POST'])
def agree():
    data = request.json
    code = data.get('code')
    role = data.get('role')

    session = get_session(code)
    session["agreed"][role] = True

    if session["freeze"]["phase"] != "finished":
        session["freeze"]["phase"] = "finished"
        
        scenario_title = session["scenario"]["title"] if session.get("scenario") else "刚才的小插曲"
        
        session["freeze"]["finalReport"] = {
            "praise": "你们都太棒啦！在遇到矛盾时没有一直发脾气，而是愿意停下来听对方说话，这就是超级厉害的【共情能力】！",
            "growth": f"在解决【{scenario_title}】的误会时，你们勇敢地说出了自己的感受。你们学会了用沟通代替争吵，这就是最大的成长！",
            "tip": "法官精灵的交友秘籍：下次再遇到让你着急的事情，记得在心里数三秒，然后用“我希望/我需要...”来表达，好朋友会更懂你哦！"
        }

        session["chat"].append({"id": f"sys_{time.time()}_celeb", "kind": "system", "text": "太棒了！因为你们成功合作，误会解开啦，每人奖励一朵小红花！", "meta": "celebrate"})
        session["chat"].append({"id": f"sys_{time.time()}_feel_A", "kind": "system", "text": "法官精灵：回想一下最开始生气的时刻，再看看现在，心里感觉怎么样呀？", "meta": "finished", "target": "A"})
        session["chat"].append({"id": f"sys_{time.time()}_enc_A", "kind": "system", "text": "精灵小广播：你今天做得很棒！学会了用沟通解开误会！", "meta": "finished", "target": "A"})
        session["chat"].append({"id": f"sys_{time.time()}_enc_B", "kind": "system", "text": "精灵小广播：你是个善解人意的好搭档！没有陷入争吵，做得很棒！", "meta": "finished", "target": "B"})

    save_session(session)
    return jsonify(session)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
