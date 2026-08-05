"use strict";

const el = (id) => document.getElementById(id);
const token = new URLSearchParams(location.search).get("token") || "";

let finished = false;
let busy = false;

// ------------------------------------------------------------- geri sayım

let remaining = null;      // qalan saniyə
let tickHandle = null;
let syncHandle = null;     // serverlə vaxt sinxronizasiyası
let checkingTimeout = false;
let shownCount = 0;        // ekranda göstərilən mesaj sayı

// Vaxt Baş HR tərəfindən uzadıla bilər. Sayğac brauzerdə lokal işlədiyi üçün
// serverlə mütəmadi sinxronlaşdırılır — əks halda uzatma tətbiq olunmaz və
// müsahibə vaxtından əvvəl bağlanardı.
const SYNC_MS = 15000;

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function paintTimer() {
  const box = el("timer");
  if (remaining === null) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  el("timer-value").textContent = formatTime(Math.max(0, remaining));
  box.classList.toggle("warn", remaining <= 300 && remaining > 60);
  box.classList.toggle("danger", remaining <= 60);
}

function applyTiming(timing) {
  if (!timing) return;
  remaining = Math.max(0, timing.remaining_seconds);
  paintTimer();
  startTicking();
}

function startTicking() {
  if (tickHandle || finished || remaining === null) return;
  tickHandle = setInterval(() => {
    if (finished) { stopTicking(); return; }
    remaining = Math.max(0, remaining - 1);
    paintTimer();
    // Sıfıra çatanda müsahibəni DƏRHAL bağlamırıq — əvvəlcə serverdən
    // soruşuruq, çünki vaxt uzadılmış ola bilər.
    if (remaining === 0) syncTiming();
  }, 1000);
}

function stopTicking() {
  if (tickHandle) { clearInterval(tickHandle); tickHandle = null; }
  if (syncHandle) { clearInterval(syncHandle); syncHandle = null; }
}

/** Serverdən cari vəziyyəti alır: vaxt uzadılıbsa sayğacı yeniləyir,
 *  həqiqətən bitibsə müsahibəni bağlayır. AI çağırışı etmir. */
async function syncTiming() {
  if (finished || busy || checkingTimeout) return;
  checkingTimeout = true;
  try {
    const response = await fetch(`/api/interview/${encodeURIComponent(token)}`);
    if (!response.ok) return;
    const info = await response.json();

    // Serverdə yaranmış yeni mesajlar (məs. vaxtın bitməsi bildirişi)
    (info.messages || []).slice(shownCount).forEach((m) => addMessage(m.role, m.content));

    if (info.status === "completed") { markFinished(); return; }
    if (info.timing) applyTiming(info.timing);
  } catch (_) {
    // Şəbəkə qırılıbsa müsahibəni bağlamırıq — növbəti sinxronizasiyada yoxlanacaq
  } finally {
    checkingTimeout = false;
  }
}

function startSyncing() {
  if (syncHandle || finished) return;
  syncHandle = setInterval(syncTiming, SYNC_MS);
}

function fail(title, detail) {
  const state = el("state");
  state.className = "state error";
  state.innerHTML = `<h2>${title}</h2><p>${detail}</p>`;
  el("chat-view").classList.add("hidden");
  state.classList.remove("hidden");
}

function failLocked() {
  stopTicking();
  finished = true;
  fail("Bu link başqa cihazda açılıb",
       "Müsahibə linki yalnız onu ilk dəfə açan brauzerdə işləyir və " +
       "paylaşıla bilməz.<br><br>Müsahibəni başlatdığınız kompüterdə və " +
       "brauzerdə davam edin. Səhv olduğunu düşünürsünüzsə, linki sizə " +
       "göndərən HR mütəxəssisi ilə əlaqə saxlayın.");
}

function addMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + (role === "user" ? "me" : "ai");

  const who = document.createElement("div");
  who.className = "who";
  who.textContent = role === "user" ? "Siz" : "Müsahibəçi";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;          // textContent — XSS mümkün deyil

  wrap.append(who, bubble);
  el("log").append(wrap);
  shownCount += 1;
  scrollDown();
}

function showTyping(on) {
  const existing = el("typing");
  if (!on) { if (existing) existing.remove(); return; }
  if (existing) return;
  const wrap = document.createElement("div");
  wrap.id = "typing";
  wrap.className = "msg ai";
  wrap.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
  el("log").append(wrap);
  scrollDown();
}

function scrollDown() {
  const log = el("log");
  log.scrollTop = log.scrollHeight;
}

function markFinished() {
  finished = true;
  stopTicking();          // taymer + sinxronizasiya
  remaining = null;
  el("timer").classList.add("hidden");
  el("input-row").classList.add("hidden");
  el("done-note").classList.remove("hidden");
}

// ------------------------------------------------------------------- şəbəkə

async function send(message) {
  if (busy || finished) return;
  busy = true;
  el("send").disabled = true;
  showTyping(true);

  try {
    const response = await fetch(`/api/interview/${encodeURIComponent(token)}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await response.json();
    showTyping(false);

    if (response.status === 403 && data.locked) {
      failLocked();
      return;
    }
    if (!response.ok) {
      addMessage("assistant", data.error || "Xəta baş verdi. Yenidən cəhd edin.");
      return;
    }

    addMessage("assistant", data.reply);
    applyTiming(data.timing);
    if (data.finished) markFinished();
  } catch (_) {
    showTyping(false);
    addMessage("assistant", "Şəbəkə xətası. Zəhmət olmasa yenidən cəhd edin.");
  } finally {
    busy = false;
    el("send").disabled = finished;
    if (!finished) el("input").focus();
  }
}

function submit() {
  const input = el("input");
  const text = input.value.trim();
  if (!text || busy || finished) return;
  addMessage("user", text);
  input.value = "";
  input.style.height = "auto";
  send(text);
}

el("send").addEventListener("click", submit);
el("input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submit();
  }
});
el("input").addEventListener("input", (event) => {
  event.target.style.height = "auto";
  event.target.style.height = Math.min(event.target.scrollHeight, 180) + "px";
});

// --------------------------------------------------------------- başlanğıc

(async function init() {
  if (!token) {
    fail("Link etibarsızdır", "Müsahibə linkini tam şəkildə açdığınızdan əmin olun.");
    return;
  }

  let info;
  try {
    const response = await fetch(`/api/interview/${encodeURIComponent(token)}`);
    if (response.status === 404) {
      fail("Link tapılmadı", "Bu müsahibə linki mövcud deyil və ya silinib.");
      return;
    }
    if (response.status === 403) {
      failLocked();
      return;
    }
    info = await response.json();
  } catch (_) {
    fail("Bağlantı xətası", "Serverə qoşulmaq mümkün olmadı. Yenidən cəhd edin.");
    return;
  }

  el("subtitle").textContent =
    `${info.first_name} ${info.last_name} · ${info.role}`;
  el("skills").innerHTML = (info.skills || [])
    .map((s) => `<span class="skill-tag"></span>`).join("");
  el("skills").querySelectorAll(".skill-tag").forEach((tag, index) => {
    const skill = info.skills[index];
    tag.textContent = `${skill.name} · ${skill.level}/10`;
  });

  el("state").classList.add("hidden");
  el("chat-view").classList.remove("hidden");

  (info.messages || []).forEach((message) => addMessage(message.role, message.content));

  if (info.status === "completed") {
    markFinished();
    return;
  }

  if (info.timing) {
    applyTiming(info.timing);              // müsahibə davam edir
  } else if (info.duration_minutes) {
    remaining = info.duration_minutes * 60; // hələ başlamayıb — limiti göstər
    paintTimer();
  }
  startSyncing();          // vaxt uzadılarsa dərhal tutulsun

  // Yazışma boşdursa AI-dan salamlama + ilk sualı istəyirik
  if (!(info.messages || []).length) {
    send("");
  } else {
    el("input").focus();
  }
})();
