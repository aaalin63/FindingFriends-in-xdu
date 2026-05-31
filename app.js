const fieldSets = {
  meal: {
    title: "饭搭子",
    fields: [
      ["restaurant", "想去的饭店", "text", "例如：老碗会、秦镇米皮"],
      ["location", "饭店地点", "text", "例如：北校区东门外"],
      ["timeCost", "从学校出发时间", "select", ["10 分钟内", "10-20 分钟", "20-40 分钟", "40 分钟以上"]],
      ["dish", "特色菜", "text", "例如：油泼面、葫芦鸡"],
      ["budget", "人均消费", "select", ["20 元以内", "20-40 元", "40-70 元", "70 元以上"]],
      ["mealTime", "期望时间", "select", ["早餐", "午餐", "晚餐", "夜宵"]]
    ]
  },
  study: {
    title: "自习搭子",
    fields: [
      ["place", "自习地点", "text", "例如：图书馆三楼、B 楼教室"],
      ["subject", "学习内容", "text", "例如：高数、408、英语六级"],
      ["studyTime", "自习时段", "select", ["上午", "下午", "晚上", "全天"]],
      ["style", "自习方式", "select", ["安静自习", "互相提问", "定时休息", "考研监督"]],
      ["duration", "单次时长", "select", ["1-2 小时", "2-4 小时", "4 小时以上"]],
      ["frequency", "频率", "select", ["偶尔", "每周 2-3 次", "工作日", "每天"]]
    ]
  },
  run: {
    title: "跑步搭子",
    fields: [
      ["route", "跑步路线", "text", "例如：南校区操场、环校路"],
      ["pace", "配速", "select", ["轻松慢跑", "6-7 分钟/公里", "5-6 分钟/公里", "5 分钟内/公里"]],
      ["distance", "距离", "select", ["2-3 公里", "3-5 公里", "5-8 公里", "8 公里以上"]],
      ["runTime", "跑步时段", "select", ["清晨", "傍晚", "晚上", "周末"]],
      ["goal", "目标", "select", ["减脂", "体测", "马拉松训练", "保持习惯"]],
      ["intensity", "强度", "select", ["低强度", "中等强度", "高强度"]]
    ]
  },
  ball: {
    title: "打球搭子",
    fields: [
      ["sport", "球类项目", "select", ["篮球", "羽毛球", "乒乓球", "足球", "网球"]],
      ["court", "场地", "text", "例如：南校区篮球场、体育馆"],
      ["level", "水平", "select", ["新手", "普通爱好者", "院队水平", "只想娱乐"]],
      ["ballTime", "打球时段", "select", ["工作日晚上", "周末上午", "周末下午", "随时约"]],
      ["mode", "组局方式", "select", ["1v1", "2v2", "3v3", "多人局"]],
      ["equipment", "器材", "select", ["自带", "可借", "需要对方提供", "都可以"]]
    ]
  }
};

const typeButtons = document.querySelectorAll(".type-card");
const authTabs = document.querySelectorAll(".auth-tab");
const registerForm = document.querySelector("#registerForm");
const loginForm = document.querySelector("#loginForm");
const authHint = document.querySelector("#authHint");
const userSummary = document.querySelector("#userSummary");
const logoutBtn = document.querySelector("#logoutBtn");
const dynamicFields = document.querySelector("#dynamicFields");
const requestForm = document.querySelector("#requestForm");
const formHint = document.querySelector("#formHint");
const notice = document.querySelector("#notice");
const matchList = document.querySelector("#matchList");
let selectedType = "meal";
let currentPostId = null;
let currentUser = null;
let authToken = localStorage.getItem("xdu-partner-token") || "";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  const response = await fetch(path, {
    headers,
    ...options
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "请求失败，请稍后再试。");
  }

  return data;
}

function renderFields(type) {
  const html = fieldSets[type].fields.map(([id, label, kind, data]) => {
    if (kind === "select") {
      return `
        <label>
          ${label}
          <select id="${id}" data-field="${id}" required>
            <option value="">请选择</option>
            ${data.map(option => `<option>${escapeHtml(option)}</option>`).join("")}
          </select>
        </label>
      `;
    }

    return `
      <label>
        ${label}
        <input id="${id}" data-field="${id}" type="${kind}" placeholder="${escapeHtml(data)}" required>
      </label>
    `;
  }).join("");

  dynamicFields.innerHTML = `<div class="field-grid">${html}</div>`;
}

function collectRequest() {
  const data = { type: selectedType };
  document.querySelectorAll("[data-field]").forEach(field => {
    data[field.dataset.field] = field.value.trim();
  });
  data.note = document.querySelector("#note").value.trim();
  return data;
}

function validate(request) {
  const missingRequest = Object.entries(request).filter(([key, value]) => key !== "note" && !value);

  if (!currentUser) {
    formHint.textContent = "请先完成注册或登录，再发布搭子招募。";
    return false;
  }

  if (missingRequest.length) {
    formHint.textContent = "请先补全当前需求的必填项。";
    return false;
  }

  formHint.textContent = "";
  return true;
}

function getDetailTags(match) {
  const keys = fieldSets[match.type].fields.map(([id]) => id);
  return keys.slice(0, 4).map(key => match.details[key]).filter(Boolean);
}

function renderMatches(post, matches) {
  currentPostId = post.id;

  if (!matches.length) {
    notice.innerHTML = `<strong>已发布</strong><span>数据库中暂无可匹配的真实同学。等同类型招募发布后，再拒绝或重新发布即可继续匹配。</span>`;
    matchList.innerHTML = "";
    return;
  }

  notice.innerHTML = `<strong>已通知双方</strong><span>${escapeHtml(post.nickname)} 的${fieldSets[post.type].title}招募已写入数据库，并推送给 ${matches.map(item => escapeHtml(item.nickname)).join("、")}。</span>`;
  matchList.innerHTML = matches.map(match => `
    <article class="match-card">
      <div class="match-top">
        <div class="avatar">${escapeHtml(match.nickname.slice(0, 1))}</div>
        <div>
          <strong>${escapeHtml(match.nickname)}</strong>
          <p>${escapeHtml(match.department)} · ${escapeHtml(match.grade)} · ${escapeHtml(match.gender)}</p>
        </div>
        <div class="score">${match.score}%</div>
      </div>
      <p>${escapeHtml(match.note || "对方暂未填写补充说明。")}</p>
      <div class="tag-row">
        ${getDetailTags(match).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="match-actions">
        <button class="match-action accept" type="button" data-accept="${match.id}">接受</button>
        <button class="match-action reject" type="button" data-reject="${match.id}">拒绝并继续</button>
      </div>
    </article>
  `).join("");
}

function persistLatest(request, postId) {
  localStorage.setItem("xdu-partner-request", JSON.stringify(request));
  localStorage.setItem("xdu-partner-post-id", String(postId));
}

async function publishRequest(request) {
  formHint.textContent = "正在发布到本地数据库并计算真实匹配...";
  const payload = { request };
  const data = await api("/api/posts", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  persistLatest(request, data.post.id);
  renderMatches(data.post, data.matches);
  formHint.textContent = "";
  document.querySelector("#matches").scrollIntoView({ behavior: "smooth", block: "start" });
}

function setAuthTab(name) {
  authTabs.forEach(tab => tab.classList.toggle("is-active", tab.dataset.authTab === name));
  registerForm.hidden = name !== "register";
  loginForm.hidden = name !== "login";
  authHint.textContent = "";
}

function renderUser() {
  const loggedIn = Boolean(currentUser);
  userSummary.hidden = !loggedIn;
  logoutBtn.hidden = !loggedIn;
  registerForm.hidden = loggedIn || !document.querySelector('[data-auth-tab="register"]').classList.contains("is-active");
  loginForm.hidden = loggedIn || !document.querySelector('[data-auth-tab="login"]').classList.contains("is-active");

  if (!loggedIn) {
    userSummary.innerHTML = "";
    return;
  }

  userSummary.innerHTML = `
    <strong>${escapeHtml(currentUser.nickname)}</strong>
    <span>${escapeHtml(currentUser.department)} · ${escapeHtml(currentUser.grade)} · ${escapeHtml(currentUser.gender)}</span>
    <span>学号：${escapeHtml(currentUser.studentId)}</span>
    <span>联系方式：${escapeHtml(currentUser.contact)}</span>
  `;
}

function saveSession(data) {
  authToken = data.token;
  currentUser = data.user;
  localStorage.setItem("xdu-partner-token", authToken);
  renderUser();
}

async function loadMe() {
  if (!authToken) {
    renderUser();
    return;
  }

  try {
    const data = await api("/api/me");
    currentUser = data.user;
  } catch {
    authToken = "";
    currentUser = null;
    localStorage.removeItem("xdu-partner-token");
  }

  renderUser();
}

function readRegisterPayload() {
  return {
    studentId: document.querySelector("#regStudentId").value.trim(),
    password: document.querySelector("#regPassword").value,
    nickname: document.querySelector("#regNickname").value.trim(),
    department: document.querySelector("#regDepartment").value,
    grade: document.querySelector("#regGrade").value,
    gender: document.querySelector("#regGender").value,
    contact: document.querySelector("#regContact").value.trim()
  };
}

function readLoginPayload() {
  return {
    studentId: document.querySelector("#loginStudentId").value.trim(),
    password: document.querySelector("#loginPassword").value
  };
}

async function decide(candidateId, decision) {
  if (!currentPostId) return;

  const data = await api("/api/decisions", {
    method: "POST",
    body: JSON.stringify({
      postId: currentPostId,
      candidateId: Number(candidateId),
      decision
    })
  });

  if (decision === "accept") {
    const status = data.matchStatus === "confirmed" ? "双方已接受" : "已通知对方确认";
    notice.innerHTML = `<strong>${status}</strong><span>你的选择已记录到数据库。对方登录并接受后，状态会变为双方确认。</span>`;
    matchList.querySelectorAll(".match-card").forEach(card => {
      if (!card.querySelector(`[data-accept="${candidateId}"]`)) card.remove();
    });
    return;
  }

  renderMatches(data.post, data.matches);
}

typeButtons.forEach(button => {
  button.addEventListener("click", () => {
    selectedType = button.dataset.type;
    typeButtons.forEach(item => {
      item.classList.toggle("is-active", item === button);
      item.setAttribute("aria-pressed", String(item === button));
    });
    renderFields(selectedType);
  });
});

requestForm.addEventListener("submit", async event => {
  event.preventDefault();
  const request = collectRequest();

  if (!validate(request)) return;

  try {
    await publishRequest(request);
  } catch (error) {
    formHint.textContent = error.message;
  }
});

authTabs.forEach(tab => {
  tab.addEventListener("click", () => setAuthTab(tab.dataset.authTab));
});

registerForm.addEventListener("submit", async event => {
  event.preventDefault();
  authHint.textContent = "正在注册...";

  try {
    const data = await api("/api/register", {
      method: "POST",
      body: JSON.stringify(readRegisterPayload())
    });
    saveSession(data);
    authHint.textContent = "注册成功，已经登录。";
  } catch (error) {
    authHint.textContent = error.message;
  }
});

loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  authHint.textContent = "正在登录...";

  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify(readLoginPayload())
    });
    saveSession(data);
    authHint.textContent = "登录成功。";
  } catch (error) {
    authHint.textContent = error.message;
  }
});

logoutBtn.addEventListener("click", () => {
  authToken = "";
  currentUser = null;
  localStorage.removeItem("xdu-partner-token");
  setAuthTab("login");
  renderUser();
  authHint.textContent = "已退出登录。";
});

matchList.addEventListener("click", async event => {
  const acceptId = event.target.dataset.accept;
  const rejectId = event.target.dataset.reject;

  try {
    if (acceptId) await decide(acceptId, "accept");
    if (rejectId) await decide(rejectId, "reject");
  } catch (error) {
    notice.innerHTML = `<strong>操作失败</strong><span>${escapeHtml(error.message)}</span>`;
  }
});

function restore() {
  const request = JSON.parse(localStorage.getItem("xdu-partner-request") || "{}");
  currentPostId = Number(localStorage.getItem("xdu-partner-post-id")) || null;

  if (request.type && fieldSets[request.type]) {
    selectedType = request.type;
    typeButtons.forEach(item => {
      const active = item.dataset.type === selectedType;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-pressed", String(active));
    });
  }

  renderFields(selectedType);

  Object.entries(request).forEach(([key, value]) => {
    const input = document.querySelector(`#${key}`);
    if (input && value) input.value = value;
  });
}

restore();
loadMe();
