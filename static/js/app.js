(() => {
  const $ = (id) => document.getElementById(id);

  const screenHome = $("screenHome");
  const screenChat = $("screenChat");
  const chipRole = $("chipRole");
  const btnReset = $("btnReset");

  const sessionCodeInput = $("sessionCode");
  const btnNewSession = $("btnNewSession");
  const btnChooseA = $("btnChooseA");
  const btnChooseB = $("btnChooseB");

  const storyText = $("storyText");
  const systemNotice = $("systemNotice");
  const chatMeta = $("chatMeta");
  const presence = $("presence");
  const chatLog = $("chatLog");
  const composerInput = $("composerInput");
  const btnSend = $("btnSend");
  const composerSub = $("composerSub");

  const negotiateActions = $("negotiateActions");
  const btnAgree = $("btnAgree");
  const celebrationOverlay = $("celebrationOverlay");
  const finishModal = $("finishModal");
  const btnReviewChat = $("btnReviewChat");
  const btnPlayAgain = $("btnPlayAgain");
  const btnReturnHome = $("btnReturnHome");

  const modal = $("modal");
  const modalClose = $("modalClose");
  const modalCancel = $("modalCancel");
  const modalSubmit = $("modalSubmit");
  const modalTitle = $("modalTitle");
  const modalDesc = $("modalDesc");
  const modalFieldLabel = $("modalFieldLabel");
  const modalText = $("modalText");
  const modalHint = $("modalHint");

  const appState = {
    code: "",
    role: null,
    hasCelebrated: false
  };

  let syncInterval = null;
  let currentSessionData = null;
  let promptTimeout = null;

  function randomCode() {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let out = "";
    for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)];
    return out;
  }

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function setActiveScreen(which) {
    screenHome.classList.remove("screen--active");
    screenChat.classList.remove("screen--active");
    if (which === "home") screenHome.classList.add("screen--active");
    if (which === "chat") screenChat.classList.add("screen--active");
  }

  function setRoleChip(role) {
    if (!role) {
      chipRole.textContent = "未选择身份";
      chipRole.style.opacity = "0.9";
      return;
    }
    chipRole.textContent = `当前身份：${role}`;
    chipRole.style.opacity = "1";
  }

  function setPresence(ready, text) {
    presence.dataset.ready = ready ? "true" : "false";
    presence.querySelector(".presence__text").textContent = text;
    presence.querySelector(".presence__dot").style.background = ready ? "var(--good)" : "#94A3B8";
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function pushMsg({ from, text, meta = "", kind = "chat", extra = null }) {
    const isSelf = from === appState.role;
    const isJudge = from === "J";
    const row = document.createElement("div");
    row.className = "msg" + (isSelf && !isJudge ? " msg--right" : "");

    const avatar = document.createElement("div");
    avatar.className =
      "avatar " + (from === "A" ? "avatar--a" : from === "B" ? "avatar--b" : "avatar--j");
    avatar.textContent = from === "J" ? "法" : from;

    const bubble = document.createElement("div");
    bubble.className =
      "bubble " + (from === "A" ? "bubble--a" : from === "B" ? "bubble--b" : "bubble--j");

    if (kind === "judgeCard") {
      bubble.style.maxWidth = "100%";
      bubble.style.padding = "0";
      bubble.style.border = "0";
      bubble.style.background = "transparent";
      bubble.innerHTML = renderJudgeCard(extra);
    } else {
      bubble.innerHTML = `${escapeHtml(text)}`;
    }

    row.appendChild(avatar);
    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function renderJudgeCard(result) {
    if (!result) return `<div class="judgeCard">暂无裁判结果</div>`;
    const score = clamp(Math.round(result.misinterpretation * 100), 0, 100);
    const level = score >= 70 ? "高风险" : score >= 35 ? "中风险" : "低风险";
    const badgeClass = score >= 70 ? "badge--bad" : score >= 35 ? "badge--warn" : "badge--good";
    const guidance = escapeHtml(result.guidance || "");
    const truth = escapeHtml(result.truthForB || "");

    let contentHtml = "";

    const triggeredByMe = appState.role === result.triggeredBy;

    if (triggeredByMe && guidance) {
      contentHtml = `<div><strong>裁判分析：</strong>${guidance}</div>`;
    } else if (!triggeredByMe && truth) {
      contentHtml = `<div><strong>裁判分析：</strong>${truth}</div>`;
    } else if (!guidance && !truth) {
      contentHtml = `<div>意图匹配成功，建议进入下一步协作。</div>`;
    }

    return `
      <div class="judgeCard">
        <div class="judgeRow">
          <div class="judgeTitle">裁判结果打分</div>
          <div class="badge ${badgeClass}">意图误解度：${score}%（${level}）</div>
        </div>
        <div class="progress" aria-label="意图误解度进度条">
          <div class="progress__bar" style="width:${score}%"></div>
        </div>
        <div class="judgeBody">
          ${contentHtml}
        </div>
      </div>
    `;
  }

  function openModal(cfg) {
    modalTitle.textContent = cfg.title;
    modalDesc.textContent = cfg.desc || "";
    modalFieldLabel.textContent = cfg.fieldLabel || "请输入";
    modalText.value = cfg.defaultValue || "";
    modalText.placeholder = cfg.placeholder || "";
    modalHint.textContent = cfg.hint || "";
    modal.dataset.mode = cfg.mode || "";
    modal.setAttribute("aria-hidden", "false");
    setTimeout(() => modalText.focus(), 0);
  }

  function closeModal() {
    modal.setAttribute("aria-hidden", "true");
    modal.dataset.mode = "";
    modalText.value = "";
  }

  function triggerCelebration() {
    if (appState.hasCelebrated) return;
    appState.hasCelebrated = true;

    celebrationOverlay.classList.add("show");

    setTimeout(() => {
        celebrationOverlay.classList.remove("show");
        finishModal.setAttribute("aria-hidden", "false");
    }, 3500);
  }

  function renderSession(session) {
    // 【强制拦截旧缓存机制】如果后端没有下发动态 scenario，就不渲染，强制要求走新版
    if (!session || !session.scenario) return;

    const hasA = Boolean(session.participants.A);
    const hasB = Boolean(session.participants.B);
    const ready = hasA && hasB;

    setPresence(ready, ready ? "对方已加入" : "等待对方加入...");
    chatMeta.textContent = `会话码：${session.code} · 情境：${session.scenario.title}`;

    // 【强力占位符替换】防范大模型自作主张修改 {who} 为 {A}
    let ruleText = session.scenario.systemRule || "";

    if (appState.role === "A") {
      storyText.textContent = session.scenario.storyA;
      systemNotice.textContent = ruleText
        .replace("{arousal}", "高")
        .replace("{who}", "你（A）")
        .replace("{A}", "你（A）");
    } else {
      storyText.textContent = session.scenario.storyB;
      systemNotice.textContent = ruleText
        .replace("{arousal}", "低")
        .replace("{who}", "对方（A）")
        .replace("{A}", "对方（A）");
    }

    chatLog.innerHTML = "";
    for (const item of session.chat) {
      if (item.target && item.target !== appState.role) continue;

      if (item.kind === "judgeCard") {
        pushMsg({ from: "J", text: "", kind: "judgeCard", extra: item.extra });
      } else if (item.kind === "system") {
        if (item.meta === "celebrate") {
            pushMsg({ from: "J", text: item.text, meta: item.meta || "" });
            triggerCelebration();
        } else {
            pushMsg({ from: "J", text: item.text, meta: item.meta || "" });
        }
      } else {
        pushMsg({ from: item.from, text: item.text, meta: item.meta || "" });
      }
    }

    const frozen = session.freeze.active;
    const phase = session.freeze.phase;
    const aHasSpoken = session.chat.filter(m => m.from === "A").length > 0;

    const disabled = !ready || frozen || phase === "finished" || (appState.role === "B" && !aHasSpoken && phase === "idle");

    btnSend.disabled = disabled;
    composerInput.disabled = disabled;
    btnAgree.disabled = false;

    if (phase === "negotiate" && !session.agreed[appState.role]) {
        negotiateActions.style.display = "block";
    } else {
        negotiateActions.style.display = "none";
    }

    if (!ready) {
      composerSub.textContent = "等待另一端输入会话码加入后才能开始。";
    } else if (frozen) {
      composerSub.textContent = "对话已暂停，请先完成弹窗里的动机提交。";
    } else if (appState.role === "B" && !aHasSpoken && phase === "idle") {
      composerSub.textContent = "系统判定：由对方先发言。请等待对方消息。";
    } else if (phase === "rephrase") {
      const isSpeaker = session.freeze.triggeredBy === appState.role;
      if (isSpeaker) {
        composerSub.textContent = "请根据 AI 的引导重新组织语言再发送。";
        composerInput.placeholder = "例如：我有点着急，因为时间快到了…我可以帮你吗？";
        btnSend.disabled = false;
        composerInput.disabled = false;
      } else {
        composerSub.textContent = "系统正在引导对方重新组织语言，请等待对方重新发言…";
        btnSend.disabled = true;
        composerInput.disabled = true;
      }
    } else if (phase === "negotiate") {
      if (session.agreed[appState.role]) {
          composerSub.textContent = "您已确认达成一致，请等待对方确认...";
          btnSend.disabled = true;
          composerInput.disabled = true;
      } else {
          composerSub.textContent = "已进入规则制定阶段：沟通好后请点击上方“达成一致”按钮。";
          composerInput.placeholder = "例如：我画树，你画花；最后一起补色。";
      }
    } else if (phase === "finished") {
      composerSub.textContent = "本次调解训练已圆满结束！";
      composerInput.placeholder = "会话已结束";
    } else {
      composerSub.textContent = "";
      composerInput.placeholder = "在这里输入你想说的话…";
    }

    if (frozen && phase === "collecting") {
      maybePromptFreeze(session);
    } else {
      if (modal.getAttribute("aria-hidden") === "false") closeModal();
    }
  }

  function maybePromptFreeze(session) {
    const mode = modal.dataset.mode;
    if (mode || promptTimeout) return;

    const triggeredByMe = session.freeze.triggeredBy === appState.role;

    if (triggeredByMe && !session.freeze.aMotivation) {
      promptTimeout = setTimeout(() => {
        promptTimeout = null;
        if (appState.code !== session.code) return;
        openModal({
          mode: "aMotivation",
          title: "刚才发火真实的出发点是？",
          desc: "系统检测到刚才的话可能会引发争吵，已暂停对话。请你想想：你说那句话背后的真实需求是什么？",
          fieldLabel: "真实动机",
          placeholder: "例如：时间快到了，我特别想让我们这组拿到小红花…",
          hint: "写“我想要/我担心/我需要”会更清楚。"
        });
      }, 600);
      return;
    }

    if (!triggeredByMe && !session.freeze.bGuess) {
      promptTimeout = setTimeout(() => {
        promptTimeout = null;
        if (appState.code !== session.code) return;
        openModal({
          mode: "bGuess",
          title: "你觉得对方为什么这么凶？",
          desc: "（请结合对方刚才发出的消息）对话已暂停。在“双盲”状态下，请先写下你对对方意图的猜测（你觉得他刚才为什么要那么说）。",
          fieldLabel: "猜测动机",
          placeholder: "例如：他可能很着急、怕来不及…",
          hint: "写完点击提交。系统会和对方的“真实动机”对比。"
        });
      }, 2800);
    }
  }

  function ensureSessionCode() {
    let code = (sessionCodeInput.value || "").trim().toUpperCase();
    if (!code) {
      code = randomCode();
      sessionCodeInput.value = code;
    }
    return code;
  }

  function startSync() {
      if (syncInterval) clearInterval(syncInterval);
      syncInterval = setInterval(async () => {
          if (!appState.code) return;
          try {
              const res = await fetch('/api/sync', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({code: appState.code})
              });
              if (!res.ok) return;
              const data = await res.json();
              if (JSON.stringify(data) !== JSON.stringify(currentSessionData)) {
                  currentSessionData = data;
                  renderSession(data);
              }
          } catch(e) {}
      }, 1000);
  }

  async function join(role) {
    const code = ensureSessionCode();
    appState.code = code;
    appState.role = role;
    appState.hasCelebrated = false;
    setRoleChip(role);

    try {
        const res = await fetch('/api/join', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ code, role })
        });
        if (!res.ok) throw new Error("服务器返回状态异常: " + res.status);
    } catch (e) {
        console.error(e);
        alert("无法连接到后端服务器！请确保 PyCharm 中的 Flask 正在运行。");
        return;
    }

    setActiveScreen("chat");
    startSync();
  }

  function resetAll() {
    if (syncInterval) clearInterval(syncInterval);
    if (promptTimeout) { clearTimeout(promptTimeout); promptTimeout = null; }

    appState.code = "";
    appState.role = null;
    appState.hasCelebrated = false;
    currentSessionData = null;

    setRoleChip(null);
    sessionCodeInput.value = "";
    setActiveScreen("home");
    chatLog.innerHTML = "";
    closeModal();
    finishModal.setAttribute("aria-hidden", "true");
    celebrationOverlay.classList.remove("show");
  }

  async function sendMessage(text) {
    const t = String(text || "").trim();
    if (!t) return;
    const code = appState.code;
    const from = appState.role;

    btnSend.disabled = true;
    composerInput.disabled = true;

    try {
        const res = await fetch('/api/send_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, role: from, text: t })
        });
        if (!res.ok) throw new Error("消息发送异常");
    } catch (e) {
        console.error("发送失败", e);
        alert("网络请求失败，请检查后端是否断开连接。");
    } finally {
        btnSend.disabled = false;
        composerInput.disabled = false;
    }
  }

  async function submitFreeze(text) {
    const t = String(text || "").trim();
    if (!t) {
      alert("请输入内容再提交。");
      return;
    }

    const code = appState.code;
    const role = appState.role;
    const mode = modal.dataset.mode;

    try {
        const res = await fetch('/api/submit_freeze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, role, text: t, mode })
        });
        if (!res.ok) throw new Error("动机提交异常");
        closeModal();
    } catch (e) {
        console.error("提交动机失败", e);
        alert("提交失败，请检查网络连接。");
    }
  }

  async function submitAgree() {
    const code = appState.code;
    const role = appState.role;
    btnAgree.disabled = true;
    try {
        const res = await fetch('/api/agree', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, role })
        });
        if (!res.ok) throw new Error("一致确认异常");
    } catch (e) {
        console.error("确认失败", e);
        alert("网络请求失败，请检查网络。");
        btnAgree.disabled = false;
    }
  }

  btnNewSession.addEventListener("click", () => {
    sessionCodeInput.value = randomCode();
  });

  btnChooseA.addEventListener("click", () => join("A"));
  btnChooseB.addEventListener("click", () => join("B"));

  btnReset.addEventListener("click", () => {
      if(confirm("确定要退出当前会话吗？")) resetAll();
  });

  btnSend.addEventListener("click", () => {
    sendMessage(composerInput.value);
    composerInput.value = "";
    composerInput.focus();
  });

  composerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (!btnSend.disabled) btnSend.click();
    }
  });

  modalClose.addEventListener("click", closeModal);
  modalCancel.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    const t = e.target;
    if (t && t.dataset && t.dataset.close === "true") closeModal();
  });
  modalSubmit.addEventListener("click", () => {
    submitFreeze(modalText.value);
  });

  btnAgree.addEventListener("click", submitAgree);

  btnReviewChat.addEventListener("click", () => {
      finishModal.setAttribute("aria-hidden", "true");
  });

  btnPlayAgain.addEventListener("click", () => {
      resetAll();
      sessionCodeInput.value = randomCode();
  });

  btnReturnHome.addEventListener("click", () => {
      resetAll();
  });

  sessionCodeInput.value = randomCode();
})();