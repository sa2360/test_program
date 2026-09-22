const state = { experiments: [], selected: null, dataset: null, lastAnswer: "", datasetLoad: 0 };

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "请求失败，请稍后重试。");
  return payload;
}

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function setStatus(id, text, kind = "") {
  const target = document.getElementById(id);
  target.textContent = text;
  target.className = `status ${kind}`;
}

function studentName() {
  return document.getElementById("student-name").value.trim();
}

function selectedExperiment() {
  return state.selected;
}

function renderExperiment() {
  const experiment = selectedExperiment();
  if (!experiment) return;
  document.getElementById("experiment-summary").textContent = experiment.summary;
  const steps = document.getElementById("steps");
  steps.replaceChildren();
  experiment.steps.forEach((step, index) => {
    const card = node("article", undefined, "step");
    card.append(node("strong", `${index + 1}. ${step.title}`));
    card.append(node("span", step.detail));
    steps.append(card);
  });
  document.getElementById("safety").textContent = `安全提示：${experiment.safety}`;
  document.getElementById("dataset-title").value = `${experiment.name}原始记录`;
  state.dataset = null;
  document.getElementById("dataset-area").textContent = "尚未创建数据表。";
  loadStudentDatasets();
}

async function loadExperiments() {
  const data = await api("/api/v1/experiments");
  state.experiments = data.experiments;
  const selector = document.getElementById("experiment");
  selector.replaceChildren();
  data.experiments.forEach((experiment) => {
    const option = node("option", experiment.name);
    option.value = experiment.id;
    selector.append(option);
  });
  state.selected = data.experiments[0];
  selector.addEventListener("change", () => {
    state.selected = state.experiments.find((item) => item.id === selector.value);
    renderExperiment();
  });
  renderExperiment();
}

function setupVoice() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const status = document.getElementById("voice-status");
  const start = document.getElementById("start-voice");
  if (!Recognition) {
    status.textContent = "当前浏览器不支持语音识别；你仍可直接输入问题。";
    start.disabled = true;
    return;
  }
  status.textContent = "可使用浏览器语音识别。首次使用时请允许麦克风权限。";
  start.addEventListener("click", () => {
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      document.getElementById("assistant-question").value = event.results[0][0].transcript;
      status.textContent = "已转写语音，请确认文字后发送。";
    };
    recognition.onerror = () => { status.textContent = "未能识别语音；请检查麦克风权限或改用文字输入。"; };
    recognition.start();
    status.textContent = "正在聆听。";
  });
}

async function askAssistant() {
  const question = document.getElementById("assistant-question").value.trim();
  if (!question) return setStatus("assistant-answer", "请先输入问题。", "warning");
  const answerArea = document.getElementById("assistant-answer");
  answerArea.className = "answer";
  answerArea.textContent = "正在生成回答。";
  try {
    const result = await api("/api/v1/qa", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ experiment: selectedExperiment().id, question }),
    });
    state.lastAnswer = result.answer;
    const source = result.source === "agnes" ? "大模型" : result.source === "local_knowledge" ? "本地知识库" : "安全回退";
    answerArea.textContent = `${result.answer}\n\n来源：${source}${result.error ? "（模型暂不可用）" : ""}`;
  } catch (error) {
    answerArea.textContent = error.message;
    answerArea.className = "answer status danger";
  }
}

function speakAnswer() {
  if (!state.lastAnswer) return setStatus("assistant-answer", "请先获得一条回答。", "warning");
  if (!("speechSynthesis" in window)) return setStatus("assistant-answer", "当前浏览器不支持朗读；请直接阅读回答。", "warning");
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(state.lastAnswer);
  utterance.lang = "zh-CN";
  window.speechSynthesis.speak(utterance);
}

async function sendTeacherQuestion() {
  const name = studentName();
  const question = document.getElementById("teacher-question").value.trim();
  if (!name) return setStatus("teacher-status", "请先填写姓名或编号，便于查看回复。", "warning");
  if (!question) return setStatus("teacher-status", "请填写要发送的问题。", "warning");
  try {
    const result = await api("/api/v1/teacher/questions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_name: name, experiment: selectedExperiment().id, question }),
    });
    document.getElementById("teacher-question").value = "";
    setStatus("teacher-status", `已发送，问题编号：${result.question_id}。`, "ok");
    loadMyQuestions();
  } catch (error) {
    setStatus("teacher-status", error.message, "danger");
  }
}

async function loadMyQuestions() {
  const name = studentName();
  const area = document.getElementById("my-questions");
  area.replaceChildren();
  if (!name) return;
  try {
    const questions = await api(`/api/v1/student/questions?${new URLSearchParams({ student_name: name })}`);
    questions.forEach((question) => {
      const card = node("article", undefined, "question");
      card.append(node("div", `${question.experiment} · ${question.created_at}`, "meta"));
      card.append(node("p", question.question));
      card.append(node("div", question.reply ? `教师回复：${question.reply}` : "等待教师回复。", question.reply ? "reply" : "muted"));
      area.append(card);
    });
  } catch (error) {
    area.append(node("p", error.message, "muted"));
  }
}

function renderDataset() {
  const area = document.getElementById("dataset-area");
  area.replaceChildren();
  const dataset = state.dataset;
  if (!dataset) {
    area.textContent = "尚未创建数据表。";
    return;
  }
  area.append(node("p", `${dataset.title} · ${dataset.rows.length} 条原始记录`, "muted"));
  const wrap = node("div", undefined, "table-wrap");
  const table = node("table");
  const header = node("tr");
  dataset.columns.forEach((column) => header.append(node("th", column)));
  table.append(header);
  dataset.rows.forEach((row) => {
    const tr = node("tr");
    row.values.forEach((value) => tr.append(node("td", value)));
    table.append(tr);
  });
  const inputRow = node("tr");
  const inputs = dataset.columns.map((column) => {
    const cell = node("td");
    const input = document.createElement("input");
    input.placeholder = column;
    cell.append(input);
    inputRow.append(cell);
    return input;
  });
  table.append(inputRow);
  wrap.append(table);
  area.append(wrap);
  const add = node("button", "保存本行");
  add.type = "button";
  add.addEventListener("click", async () => {
    const values = inputs.map((input) => input.value.trim());
    if (values.some((value) => !value)) return setStatus("capture-status", "请完整填写本行数据。", "warning");
    try {
      const row = await api(`/api/v1/datasets/${encodeURIComponent(dataset.dataset_id)}/rows`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ values }),
      });
      dataset.rows.push(row);
      renderDataset();
    } catch (error) {
      setStatus("capture-status", error.message, "danger");
    }
  });
  area.append(add);
}

async function createDataset() {
  const name = studentName();
  if (!name) return setStatus("capture-status", "请先填写姓名或编号再创建数据表。", "warning");
  const generation = ++state.datasetLoad;
  try {
    const dataset = await api("/api/v1/datasets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_name: name, experiment: selectedExperiment().id,
        title: document.getElementById("dataset-title").value.trim(),
        columns: selectedExperiment().data_columns,
      }),
    });
    if (generation !== state.datasetLoad) return;
    state.dataset = dataset;
    renderDataset();
  } catch (error) {
    setStatus("capture-status", error.message, "danger");
  }
}

async function loadStudentDatasets() {
  const generation = ++state.datasetLoad;
  const name = studentName();
  const experiment = selectedExperiment()?.id;
  state.dataset = null;
  renderDataset();
  if (!name || !experiment) return;
  try {
    const datasets = await api(`/api/v1/datasets?${new URLSearchParams({ student_name: name })}`);
    if (generation !== state.datasetLoad) return;
    const match = datasets.find((item) => item.experiment === experiment);
    if (match) {
      const dataset = await api(`/api/v1/datasets/${encodeURIComponent(match.dataset_id)}`);
      if (generation !== state.datasetLoad) return;
      state.dataset = dataset;
      renderDataset();
    }
  } catch (_) {
    if (generation !== state.datasetLoad) return;
    state.dataset = null;
    renderDataset();
  }
}

function csvCell(value) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

function downloadCsv() {
  const dataset = state.dataset;
  if (!dataset) return setStatus("capture-status", "请先创建或载入数据表。", "warning");
  const csv = [dataset.columns, ...dataset.rows.map((row) => row.values)].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
  link.download = `${dataset.title}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function renderCapture(capture) {
  const area = document.getElementById("capture-result");
  area.replaceChildren();
  if (!capture.image) return;
  const image = capture.image;
  const picture = document.createElement("img");
  picture.src = `/api/v1/images/${encodeURIComponent(image.image_id)}/file`;
  picture.alt = "实验相机拍摄的照片";
  picture.style.maxWidth = "320px";
  picture.style.marginTop = "12px";
  area.append(picture);
  const vision = image.vision;
  const card = node("div", undefined, "answer");
  if (vision.result === "unknown" || vision.source === "unconfigured") {
    card.textContent = "图片已收到，但视觉模型尚未配置，系统未对器材或接线作出判断。请由教师或实验者人工检查。";
  } else {
    card.textContent = `视觉结果：${vision.result}\n${vision.suggestion}`;
  }
  area.append(card);
}

function sleep(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function requestCapture() {
  setStatus("capture-status", "正在向相机节点发送拍照请求。", "");
  document.getElementById("capture-result").replaceChildren();
  try {
    const capture = await api("/api/v1/captures", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ experiment: selectedExperiment().id }),
    });
    for (let attempt = 0; attempt < 14; attempt += 1) {
      const status = await api(`/api/v1/captures/${encodeURIComponent(capture.request_id)}`);
      if (status.status === "received") {
        setStatus("capture-status", "相机图片已收到。", "ok");
        renderCapture(status);
        return;
      }
      setStatus("capture-status", `等待相机上传图片（${attempt + 1}/14）。`, "warning");
      await sleep(1500);
    }
    setStatus("capture-status", "未在等待时间内收到图片；请检查相机、热点和 MQTT 服务状态。", "warning");
  } catch (error) {
    setStatus("capture-status", error.message, "danger");
  }
}

document.getElementById("ask-assistant").addEventListener("click", askAssistant);
document.getElementById("speak-answer").addEventListener("click", speakAnswer);
document.getElementById("send-teacher-question").addEventListener("click", sendTeacherQuestion);
document.getElementById("create-dataset").addEventListener("click", createDataset);
document.getElementById("download-csv").addEventListener("click", downloadCsv);
document.getElementById("request-capture").addEventListener("click", requestCapture);
document.getElementById("student-name").addEventListener("input", () => { loadMyQuestions(); loadStudentDatasets(); });
setupVoice();
loadExperiments().catch((error) => setStatus("capture-status", error.message, "danger"));
