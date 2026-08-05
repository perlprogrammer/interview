"use strict";

const el = (id) => document.getElementById(id);
const TOKEN_KEY = "musahibe_admin_token";

let token = localStorage.getItem(TOKEN_KEY) || "";
let draftSkills = [];   // yaradılmaqda olan namizədin bacarıqları
let myRole = "hr";      // cari istifadəçinin rolu (hr | bas_hr)
let editingId = null;   // düzəliş rejimindəki namizədin id-si (null = yeni)

// ------------------------------------------------------------------ köməkçi

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

let toastTimer = null;
function toast(message, isError = false) {
  const box = el("toast");
  box.textContent = message;
  box.className = "toast" + (isError ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.add("hidden"), 3500);
}

async function api(path, options = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers);
  if (token) headers["X-Admin-Token"] = token;

  const response = await fetch(path, Object.assign({}, options, { headers }));

  if (response.status === 401) {
    setToken("");
    showLogin();
    throw new Error("Sessiyanın vaxtı bitib, yenidən daxil olun");
  }

  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || `Xəta (${response.status})`);
  return data;
}

function setToken(value) {
  token = value;
  if (value) localStorage.setItem(TOKEN_KEY, value);
  else localStorage.removeItem(TOKEN_KEY);
}

// -------------------------------------------------------------------- giriş

function showLogin() {
  el("app-view").classList.add("hidden");
  el("login-view").classList.remove("hidden");
}

function showApp(session) {
  el("login-view").classList.add("hidden");
  el("app-view").classList.remove("hidden");
  el("who").textContent = session.full_name || session.username;
  myRole = session.role || "hr";
  const chip = el("who-role");
  chip.textContent = session.role_label || "";
  chip.className = "role-chip" + (myRole === "bas_hr" ? " role-chip-lead" : "");
  el("users-btn").classList.toggle("hidden", myRole !== "bas_hr");
  loadCandidates();
}

// ------------------------------------------------------------ istifadəçilər

const ROLE_LABELS = { hr: "HR mütəxəssis", bas_hr: "Baş HR mütəxəssis" };

async function loadUsers() {
  try {
    const data = await api("/api/admin/users");
    el("users-tbody").innerHTML = data.users.map((user) => {
      const isMe = user.id === data.me;
      const chip = `<span class="role-chip${user.role === "bas_hr" ? " role-chip-lead" : ""}">`
                 + `${esc(user.role_label || ROLE_LABELS[user.role] || user.role)}</span>`;
      const del = isMe
        ? '<span class="muted">siz</span>'
        : `<button class="btn btn-sm btn-delete" data-user-del="${user.id}">Sil</button>`;
      return `<tr>
        <td>${esc(user.full_name || "—")}</td>
        <td class="nowrap">${esc(user.username)}</td>
        <td>${chip}</td>
        <td class="nowrap muted">${esc(user.last_login || "—")}</td>
        <td class="right">${del}</td>
      </tr>`;
    }).join("");

    el("users-tbody").querySelectorAll("[data-user-del]").forEach((button) => {
      button.addEventListener("click", () => removeUser(button.dataset.userDel));
    });
  } catch (error) {
    toast(error.message, true);
  }
}

async function removeUser(id) {
  if (!confirm("Bu istifadəçi silinsin?")) return;
  try {
    await api(`/api/admin/users/${id}`, { method: "DELETE" });
    toast("İstifadəçi silindi");
    loadUsers();
  } catch (error) {
    toast(error.message, true);
  }
}

el("users-btn").addEventListener("click", () => {
  el("users-modal").classList.remove("hidden");
  loadUsers();
});
el("users-close").addEventListener("click", () => el("users-modal").classList.add("hidden"));
el("users-modal").addEventListener("click", (event) => {
  if (event.target === el("users-modal")) el("users-modal").classList.add("hidden");
});

el("user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = el("user-btn");
  el("user-error").textContent = "";
  button.disabled = true;
  try {
    const user = await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        full_name: el("u-name").value.trim(),
        username: el("u-username").value.trim().toLowerCase(),
        password: el("u-password").value,
        role: el("u-role").value,
      }),
    });
    el("user-form").reset();
    toast(`${user.full_name} yaradıldı (${user.role_label})`);
    loadUsers();
  } catch (error) {
    el("user-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

el("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = el("login-btn");
  el("login-error").textContent = "";
  button.disabled = true;
  button.textContent = "Yoxlanılır…";
  try {
    const session = await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({
        username: el("login-username").value.trim(),
        password: el("login-password").value,
      }),
    });
    setToken(session.token);
    el("login-password").value = "";
    showApp(session);
  } catch (error) {
    el("login-error").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Daxil ol";
  }
});

el("logout-btn").addEventListener("click", async () => {
  try { await api("/api/admin/logout", { method: "POST" }); } catch (_) { /* susdur */ }
  setToken("");
  showLogin();
});

// -------------------------------------------------------------- bacarıqlar

function renderSkills() {
  const container = el("skill-list");
  if (!draftSkills.length) {
    container.innerHTML = '<p class="muted">Hələ bacarıq əlavə edilməyib.</p>';
    return;
  }
  container.innerHTML = draftSkills.map((skill, index) => `
    <div class="skill-item">
      <div class="skill-item-top">
        <span class="skill-name">${esc(skill.name)}</span>
        <span>
          <span class="skill-level" id="lvl-${index}">${skill.level}/10</span>
          <button type="button" class="skill-remove" data-remove="${index}"
                  aria-label="Sil">&times;</button>
        </span>
      </div>
      <input type="range" min="1" max="10" value="${skill.level}" data-level="${index}">
    </div>`).join("");

  container.querySelectorAll("[data-level]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const index = Number(event.target.dataset.level);
      draftSkills[index].level = Number(event.target.value);
      el(`lvl-${index}`).textContent = `${draftSkills[index].level}/10`;
    });
  });
  container.querySelectorAll("[data-remove]").forEach((button) => {
    button.addEventListener("click", (event) => {
      draftSkills.splice(Number(event.target.dataset.remove), 1);
      renderSkills();
    });
  });
}

function addSkill() {
  const input = el("skill-input");
  const name = input.value.trim();
  if (!name) return;
  if (draftSkills.some((s) => s.name.toLowerCase() === name.toLowerCase())) {
    toast("Bu bacarıq artıq əlavə edilib", true);
    return;
  }
  draftSkills.push({ name, level: 5 });
  input.value = "";
  input.focus();
  renderSkills();
}

el("skill-add-btn").addEventListener("click", addSkill);
el("skill-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") { event.preventDefault(); addSkill(); }
});

// -------------------------------------------------------- namizəd yaratmaq

function exitEditMode() {
  editingId = null;
  el("candidate-form").reset();
  el("duration").value = 15;        // reset() default dəyəri qaytarır, açıq yazırıq
  draftSkills = [];
  renderSkills();
  el("form-title").textContent = "Yeni namizəd";
  el("create-btn").textContent = "Namizədi yarat";
  el("cancel-edit").classList.add("hidden");
  el("edit-note").classList.add("hidden");
}

async function startEdit(id) {
  try {
    const candidate = await api(`/api/admin/candidates/${id}`);
    if (candidate.status !== "pending") {
      toast("Müsahibə artıq başlayıb — düzəliş etmək olmaz", true);
      loadCandidates();
      return;
    }
    editingId = candidate.id;
    el("first-name").value = candidate.first_name;
    el("last-name").value = candidate.last_name;
    el("role").value = candidate.role;
    el("duration").value = candidate.duration_minutes;
    draftSkills = candidate.skills.map((s) => ({ name: s.name, level: s.level }));
    renderSkills();

    el("form-title").textContent = "Namizədi düzəlt";
    el("create-btn").textContent = "Yadda saxla";
    el("cancel-edit").classList.remove("hidden");
    el("edit-note").classList.remove("hidden");
    el("first-name").focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (error) {
    toast(error.message, true);
  }
}

el("cancel-edit").addEventListener("click", exitEditMode);

el("candidate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!draftSkills.length) { toast("Ən azı bir bacarıq əlavə edin", true); return; }

  const button = el("create-btn");
  button.disabled = true;
  const payload = JSON.stringify({
    first_name: el("first-name").value.trim(),
    last_name: el("last-name").value.trim(),
    role: el("role").value.trim(),
    duration_minutes: Number(el("duration").value) || 15,
    skills: draftSkills,
  });

  try {
    if (editingId) {
      await api(`/api/admin/candidates/${editingId}`, { method: "POST", body: payload });
      toast("Dəyişikliklər yadda saxlanıldı");
    } else {
      await api("/api/admin/candidates", { method: "POST", body: payload });
      toast("Namizəd yaradıldı");
    }
    exitEditMode();
    loadCandidates();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

// ------------------------------------------------------------------ siyahı

const STATUS_LABELS = {
  pending: ["Gözləyir", "badge-pending"],
  active: ["Davam edir", "badge-active"],
  completed: ["Tamamlanıb", "badge-completed"],
};
const RECOMMENDATION_LABELS = {
  hire: ["Tövsiyə olunur", "badge-hire"],
  consider: ["Nəzərdən keçirilsin", "badge-consider"],
  reject: ["Tövsiyə olunmur", "badge-reject"],
};

async function loadCandidates() {
  try {
    renderCandidates(await api("/api/admin/candidates"));
  } catch (error) {
    toast(error.message, true);
  }
}

function renderCandidates(candidates) {
  const tbody = el("candidates-tbody");
  el("empty-state").classList.toggle("hidden", candidates.length > 0);
  tbody.innerHTML = candidates.map((candidate) => {
    const [statusText, statusClass] = STATUS_LABELS[candidate.status] || ["—", ""];
    const skills = candidate.skills
      .map((s) => `<span class="tag">${esc(s.name)} · ${s.level}</span>`).join("");
    const score = candidate.report && candidate.report.overall_score != null
      ? `<span class="score">${candidate.report.overall_score.toFixed(1)}</span>`
      : '<span class="muted">—</span>';

    const reportButton = candidate.status === "completed"
      ? `<button class="btn btn-sm btn-report" data-report="${candidate.id}">Hesabat</button>`
      : "";

    // Düzəliş yalnız müsahibə hələ başlamayıbsa
    const editButton = candidate.status === "pending"
      ? `<button class="btn btn-sm btn-edit" data-edit="${candidate.id}">Düzəliş</button>`
      : "";

    // Canlı izləmə yalnız Baş HR mütəxəssis üçün və bitməmiş müsahibələrdə
    const watchButton = myRole === "bas_hr" && candidate.status !== "completed"
      ? `<button class="btn btn-sm btn-watch" data-watch="${esc(candidate.access_token)}"
                 title="Müdaxilə etmədən canlı izlə">İzlə</button>`
      : "";

    const lockIcon = candidate.locked
      ? ' <span class="lock" title="Link bir cihaza bağlanıb">&#128274;</span>' : "";

    return `<tr>
      <td>${esc(candidate.first_name)} ${esc(candidate.last_name)}</td>
      <td>${esc(candidate.role)}</td>
      <td>${skills}</td>
      <td class="nowrap">${candidate.duration_minutes} dəq</td>
      <td><span class="badge ${statusClass}">${statusText}</span>${lockIcon}</td>
      <td>${score}</td>
      <td class="right"><div class="actions">
        <button class="btn btn-sm btn-link" data-link="${esc(candidate.access_token)}">Link</button>
        ${editButton}
        ${watchButton}
        ${reportButton}
        <button class="btn btn-sm btn-delete" data-delete="${candidate.id}">Sil</button>
      </div></td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll("[data-link]").forEach((button) => {
    button.addEventListener("click", () => copyLink(button.dataset.link));
  });
  tbody.querySelectorAll("[data-report]").forEach((button) => {
    button.addEventListener("click", () => openReport(button.dataset.report));
  });
  tbody.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", () => removeCandidate(button.dataset.delete));
  });
  tbody.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => startEdit(button.dataset.edit));
  });
  tbody.querySelectorAll("[data-watch]").forEach((button) => {
    button.addEventListener("click", () => {
      window.open(`/watch/?token=${button.dataset.watch}`, "_blank", "noopener");
    });
  });
}

/**
 * Mətni panoya kopyalayır.
 *
 * `navigator.clipboard` yalnız təhlükəsiz kontekstdə (HTTPS və ya localhost)
 * mövcuddur. Panel `http://` üzərindən açıldığı üçün orada işləmir — həmin hal
 * üçün gizli textarea + execCommand ehtiyat yolu var.
 */
async function copyText(text) {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) { /* ehtiyat yola keçirik */ }
  }

  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-9999px";
  document.body.appendChild(area);
  area.select();
  area.setSelectionRange(0, area.value.length);

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (_) {
    copied = false;
  }
  document.body.removeChild(area);
  return copied;
}

async function copyLink(accessToken) {
  const link = `${location.origin}/candidate/?token=${accessToken}`;
  if (await copyText(link)) {
    toast("Link kopyalandı");
  } else {
    toast("Kopyalamaq alınmadı — brauzer icazə vermir", true);
  }
}

async function removeCandidate(id) {
  if (!confirm("Namizəd və bütün müsahibə tarixçəsi silinsin?")) return;
  try {
    await api(`/api/admin/candidates/${id}`, { method: "DELETE" });
    toast("Silindi");
    loadCandidates();
  } catch (error) {
    toast(error.message, true);
  }
}

el("refresh-btn").addEventListener("click", loadCandidates);

// ----------------------------------------------------------------- hesabat

async function openReport(id) {
  try {
    renderReport(await api(`/api/admin/candidates/${id}`));
  } catch (error) {
    toast(error.message, true);
  }
}

function renderReport(candidate) {
  const report = candidate.report;
  const targets = {};
  candidate.skills.forEach((s) => { targets[s.name] = s.level; });

  const printedAt = new Date().toLocaleString("az-AZ");
  let body = `<div class="print-only rep-print-head">
      Müsahibə hesabatı · çap tarixi: ${esc(printedAt)}
    </div>
    <div class="rep-head">
      <div>
        <div class="rep-name">${esc(candidate.first_name)} ${esc(candidate.last_name)}</div>
        <div class="muted">${esc(candidate.role)}</div>
        <div class="muted">Müsahibə müddəti: ${candidate.duration_minutes} dəqiqə${
          candidate.started_at ? ` · başladı ${esc(candidate.started_at)}` : ""}</div>
      </div>`;

  if (report && report.overall_score != null) {
    const [recText, recClass] = RECOMMENDATION_LABELS[report.recommendation] || ["—", ""];
    body += `<div style="text-align:right">
        <div class="rep-score">${report.overall_score.toFixed(1)}</div>
        <div class="muted">ümumi bal / 10</div>
        <div style="margin-top:6px"><span class="badge ${recClass}">${recText}</span></div>
      </div>`;
  }
  body += "</div>";

  if (!report) {
    body += '<div class="rep-section"><p class="note">Hesabat hələ hazırlanmayıb.</p></div>';
  } else if (report.error) {
    body += `<div class="rep-section"><p class="note">${esc(report.error)}
             <br>Müsahibə yazışması aşağıda tam saxlanılıb — əl ilə qiymətləndirə bilərsiniz.</p></div>`;
  } else {
    body += `<div class="rep-section"><h3>Xülasə</h3><p>${esc(report.summary || "—")}</p></div>`;

    const bars = Object.entries(report.skill_scores || {}).map(([name, score]) => {
      const target = targets[name];
      const targetText = target ? ` (hədəf ${target})` : "";
      return `<div class="bar-row">
          <div class="bar-label"><span>${esc(name)}</span>
            <span>${Number(score).toFixed(1)}/10${targetText}</span></div>
          <div class="bar"><span style="width:${Math.max(0, Math.min(100, score * 10))}%"></span></div>
        </div>`;
    }).join("");
    if (bars) body += `<div class="rep-section"><h3>Bacarıq balları</h3>${bars}</div>`;

    const list = (items) => (items || []).map((i) => `<li>${esc(i)}</li>`).join("")
      || "<li class='muted'>—</li>";
    body += `<div class="rep-section"><h3>Güclü / zəif tərəflər</h3>
      <div class="sw-grid">
        <div class="sw-card sw-good"><h4>Güclü tərəflər</h4><ul>${list(report.strengths)}</ul></div>
        <div class="sw-card sw-bad"><h4>Təkmilləşdirilməli</h4><ul>${list(report.weaknesses)}</ul></div>
      </div></div>`;
  }

  const chat = (candidate.messages || []).map((message) => `
    <div class="chat-msg ${message.role}">
      <div class="chat-role">${message.role === "user" ? "Namizəd" : "Müsahibəçi"}</div>
      ${esc(message.content)}
    </div>`).join("") || '<p class="muted">Yazışma yoxdur.</p>';
  body += `<div class="rep-section"><h3>Müsahibə yazışması</h3>
           <div class="chat-log">${chat}</div></div>`;

  el("modal-body").innerHTML = body;
  el("modal").classList.remove("hidden");
}

function closeModal() { el("modal").classList.add("hidden"); }
el("modal-close").addEventListener("click", closeModal);
el("modal-print").addEventListener("click", () => window.print());
el("modal").addEventListener("click", (event) => {
  if (event.target === el("modal")) closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});

// --------------------------------------------------------------- başlanğıc

(async function init() {
  renderSkills();
  if (!token) { showLogin(); return; }
  try {
    showApp(await api("/api/admin/me"));
  } catch (_) {
    showLogin();
  }
})();
