async function api(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "请求失败，请稍后重试。");
  return payload;
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function appendList(parent, title, items, formatter) {
  const block = node("div", undefined, "insight");
  block.append(node("h3", title));
  if (!items.length) {
    block.append(node("p", "暂无记录。", "muted"));
  } else {
    const list = document.createElement("ul");
    items.forEach((item) => list.append(node("li", formatter(item))));
    block.append(list);
  }
  parent.append(block);
}

async function loadInsights() {
  const area = document.getElementById("insights");
  area.replaceChildren();
  try {
    const data = await api("/api/v1/teacher/insights");
    const cards = node("div", undefined, "cards");
    [["学生问题", data.question_count], ["已复核图片", data.reviewed_image_count], ["数据范围", data.window.from ? "已有记录" : "暂无记录"]].forEach(([label, value]) => {
      const card = node("div", undefined, "metric");
      card.append(node("span", label));
      card.append(node("strong", String(value)));
      cards.append(card);
    });
    area.append(cards);
    area.append(node("p", `统计时间范围：${data.window.from || "暂无"} 至 ${data.window.to || "暂无"}`, "muted"));
    appendList(area, "问题分类", data.categories, (item) => `${item.category}：${item.count} 条`);
    appendList(area, "常问问题", data.frequent_questions, (item) => `${item.question}（${item.count} 次）`);
    appendList(area, "人工或模型视觉告警", data.warning_codes, (item) => `${item.code}：${item.count} 次`);
    appendList(area, "设备告警", data.alarms, (item) => `${item.code}：${item.count} 次`);
    const suggestions = node("section", undefined, "insight");
    suggestions.append(node("h3", "授课建议"));
    data.suggestions.forEach((item) => {
      const article = node("article");
      article.append(node("strong", item.text));
      article.append(node("div", item.basis, "muted"));
      suggestions.append(article);
    });
    area.append(suggestions);
  } catch (error) {
    area.append(node("p", error.message, "status danger"));
  }
}

async function submitReply(questionId, input, button) {
  const reply = input.value.trim();
  if (!reply) return;
  button.disabled = true;
  try {
    await api(`/api/v1/teacher/questions/${encodeURIComponent(questionId)}/reply`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reply }),
    });
    await Promise.all([loadQuestions(), loadInsights()]);
  } catch (error) {
    button.disabled = false;
    input.value = error.message;
  }
}

async function loadQuestions() {
  const area = document.getElementById("questions");
  area.replaceChildren();
  try {
    const questions = await api("/api/v1/teacher/questions");
    if (!questions.length) {
      area.append(node("p", "暂无学生问题。", "muted"));
      return;
    }
    questions.forEach((question) => {
      const card = node("article", undefined, "question");
      card.append(node("div", `${question.student_name} · ${question.experiment} · ${question.category} · ${question.created_at}`, "meta"));
      card.append(node("p", question.question));
      if (question.reply) {
        card.append(node("div", `已回复：${question.reply}`, "reply"));
      } else {
        const input = document.createElement("textarea");
        input.maxLength = 800;
        input.placeholder = "输入给学生的回复。";
        const button = node("button", "发送回复");
        button.type = "button";
        button.addEventListener("click", () => submitReply(question.question_id, input, button));
        card.append(input, button);
      }
      area.append(card);
    });
  } catch (error) {
    area.append(node("p", error.message, "status danger"));
  }
}

function reviewPayload(image, outcome, note) {
  const message = note || (outcome === "danger" ? "人工复核发现安全风险，请停止实验并检查。" : outcome === "warning" ? "人工复核发现需检查的项目。" : "人工复核未发现异常。");
  const warnings = outcome === "ok" ? [] : [{
    level: outcome === "danger" ? "danger" : "warning",
    code: outcome === "danger" ? "MANUAL_DANGER" : "MANUAL_WARNING",
    message,
  }];
  return {
    schema: "physlab.vision.result.v1", device_id: "camera01", request_id: image.request_id,
    image_id: image.image_id, scene: image.scene, result: outcome, objects: [], warnings,
    suggestion: message, source: "manual", processing_ms: 0,
  };
}

async function reviewImage(image, select, note, button) {
  button.disabled = true;
  try {
    await api(`/api/v1/images/${encodeURIComponent(image.image_id)}/result`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reviewPayload(image, select.value, note.value.trim())),
    });
    await Promise.all([loadImages(), loadInsights()]);
  } catch (error) {
    button.disabled = false;
    note.value = error.message;
  }
}

function visionDescription(vision) {
  if (vision.result === "unknown" || vision.source === "unconfigured") return "未配置视觉模型：图片已保存，尚未对器材或接线作出判断。";
  return `结果：${vision.result}；来源：${vision.source || "未标注"}；建议：${vision.suggestion}`;
}

async function loadImages() {
  const area = document.getElementById("images");
  area.replaceChildren();
  try {
    const images = await api("/api/v1/images");
    if (!images.length) {
      area.append(node("p", "暂无相机图片。", "muted"));
      return;
    }
    images.forEach((image) => {
      const card = node("article", undefined, "image-card");
      const picture = document.createElement("img");
      picture.src = `/api/v1/images/${encodeURIComponent(image.image_id)}/file`;
      picture.alt = "实验相机照片";
      card.append(picture);
      card.append(node("div", `${image.scene} · ${image.received_at}`, "meta"));
      card.append(node("p", visionDescription(image.vision)));
      const select = document.createElement("select");
      [["ok", "人工确认正常"], ["warning", "人工确认需检查"], ["danger", "人工确认危险"]].forEach(([value, label]) => {
        const option = node("option", label);
        option.value = value;
        select.append(option);
      });
      const note = document.createElement("input");
      note.maxLength = 300;
      note.placeholder = "人工复核说明（可选）";
      const button = node("button", "提交人工复核");
      button.type = "button";
      button.addEventListener("click", () => reviewImage(image, select, note, button));
      card.append(select, note, button);
      area.append(card);
    });
  } catch (error) {
    area.append(node("p", error.message, "status danger"));
  }
}

document.getElementById("refresh-insights").addEventListener("click", loadInsights);
document.getElementById("refresh-questions").addEventListener("click", loadQuestions);
document.getElementById("refresh-images").addEventListener("click", loadImages);
Promise.all([loadInsights(), loadQuestions(), loadImages()]);
