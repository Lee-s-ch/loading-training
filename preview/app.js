// 출하 안전 교육: login, guided training, exam, admin. Talks to Supabase through RPC functions only.
import { QUESTIONS, EVENTS } from "./questions.js";

const API = "https://tjtbylpuvoqfzmfmsxvi.supabase.co/rest/v1/rpc/";
const KEY = "sb_publishable_7UniGhMJeSWPInc4EYsz8g_j8wZJc2j"; // publishable key: safe in the page, every function checks the session itself
const PASS = 70;
const ERR = {
  bad_login: "차량번호 또는 비밀번호가 맞지 않습니다. 비밀번호를 잊었으면 출하장 사무실(관리자)에 초기화를 요청하세요.", locked: "비밀번호를 5번 틀려 10분 동안 잠겼습니다. 잠시 뒤 다시 하세요.",
  plate_taken: "이미 가입된 차량번호입니다. 로그인하세요.", bad_plate: "차량번호를 정확히 입력하세요. (예: 12가3456)",
  bad_password: "비밀번호는 4자 이상으로 정하세요.", bad_name: "성명을 입력하세요.", bad_company: "소속 운송사를 입력하세요.",
  consent_required: "개인정보 수집에 동의해야 가입할 수 있습니다.", session_expired: "다시 로그인하세요.",
  not_approved: "관리자 승인 뒤에 이용할 수 있습니다.", forbidden: "관리자만 할 수 있습니다.", self: "자기 계정은 바꿀 수 없습니다.",
  network: "인터넷 연결을 확인하고 다시 누르세요.",
};
async function rpc(fn, args = {}) {
  let r;
  try { r = await fetch(API + fn, { method: "POST", headers: { apikey: KEY, "Content-Type": "application/json" }, body: JSON.stringify(args) }); }
  catch { throw new Error("network"); }
  const t = await r.text(); let j = null; try { j = t ? JSON.parse(t) : null; } catch {}
  if (!r.ok) throw new Error(j?.message || "network");
  return j;
}
const errText = (e) => ERR[e.message] || ERR.network;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const day = (iso) => (iso ? new Date(iso).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" }) : "");
const when = (iso) => (iso ? new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "short" }) : "");
const modeOf = (fuel) => (fuel === "휘발유" ? "bottom" : "top");
const modeName = (fuel) => (fuel === "휘발유" ? "하부 출하 (휘발유)" : `상부 출하 (${fuel})`);
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} } };
// the login lives only in this tab: on a shared PC or tablet, closing the tab logs out (sessionStorage)
const sess = { get(k) { try { return sessionStorage.getItem(k); } catch { return null; } }, set(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch {} } };

// ---------- shell ----------
const app = document.getElementById("app"); // in the page from the start, so the simulator never shows before the login screen
const coach = document.createElement("div"); coach.id = "coach"; coach.hidden = true;
const quitBtn = document.createElement("button"); quitBtn.id = "quit"; quitBtn.type = "button"; quitBtn.textContent = "그만하기"; quitBtn.hidden = true;
const voiceBtn = document.createElement("button"); voiceBtn.id = "voiceBtn"; voiceBtn.type = "button"; voiceBtn.hidden = true; // voice on/off, top right of the training / exam screen
const backBtn = document.createElement("button"); backBtn.id = "backAdmin"; backBtn.type = "button"; backBtn.textContent = "관리자 화면으로"; backBtn.hidden = true;
let me = null, token = sess.get("edu-token");
function screen(html) { app.hidden = false; app.innerHTML = `<div class="sheet">${html}</div>`; app.scrollTop = 0; return app; }
const $a = (sel) => app.querySelector(sel);
function msg(text, ok = false) { const m = $a(".msg"); if (m) { m.textContent = text; m.classList.toggle("ok", ok); } }
function busyBtn(btn, on) { if (btn) { btn.disabled = on; btn.dataset.label ??= btn.textContent; btn.textContent = on ? "잠시만요…" : btn.dataset.label; } }
const waitSim = () => new Promise((res) => { const t = () => (window.SIM ? res(window.SIM) : setTimeout(t, 50)); t(); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// voice guide (browser speech; quality depends on the device)
let voiceOn = store.get("edu-voice") !== "0";
function setVoice(on) { voiceOn = on; store.set("edu-voice", on ? "1" : "0"); if (!on) try { speechSynthesis.cancel(); } catch {} voiceBtn.textContent = on ? "🔊 음성 켜짐" : "🔇 음성 꺼짐"; voiceBtn.setAttribute("aria-pressed", String(on)); }
voiceBtn.onclick = () => setVoice(!voiceOn);
function say(text) {
  if (!voiceOn || !("speechSynthesis" in window)) return;
  try { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = "ko-KR"; u.rate = 0.92; speechSynthesis.speak(u); } catch {}
}

// ---------- login / signup ----------
function showLogin(note = "") {
  screen(`
    <h1>출하 안전 교육</h1>
    <p class="lead">차량번호와 비밀번호로 들어갑니다.</p>
    <form id="loginForm" class="form">
      <label for="lp">차량번호</label><input id="lp" autocomplete="username" placeholder="예: 12가3456" required>
      <label for="lw">비밀번호</label><input id="lw" type="password" autocomplete="current-password" required>
      <button class="big primary" type="submit">로그인</button>
    </form>
    <p class="msg" role="status">${esc(note)}</p>
    <button class="big ghost" id="toSignup" type="button">처음이신가요? 회원가입</button>`);
  $a("#toSignup").onclick = showSignup;
  $a("#loginForm").onsubmit = async (ev) => {
    ev.preventDefault(); const b = ev.submitter; busyBtn(b, true);
    try {
      const r = await rpc("login", { p_plate: $a("#lp").value, p_pw: $a("#lw").value });
      if (r.status === "bad_login" || r.status === "locked") return msg(ERR[r.status]);
      if (r.status !== "approved" && r.status !== "pending" && r.status !== "rejected") return msg(ERR.bad_login);
      if (r.status === "pending") return msg("가입 신청을 받았습니다. 관리자 승인을 기다려 주세요.");
      if (r.status === "rejected") return msg("가입이 반려되었습니다. 출하장 사무실에 문의하세요.");
      token = r.token; sess.set("edu-token", token); me = r; route();
    } catch (e) { msg(errText(e)); } finally { busyBtn(b, false); }
  };
}
function showSignup() {
  screen(`
    <h1>회원가입</h1>
    <p class="lead">가입 신청 뒤 관리자가 승인하면 교육을 받을 수 있습니다.</p>
    <form id="signForm" class="form">
      <label for="sp">차량번호</label><input id="sp" placeholder="예: 12가3456" required>
      <label for="sw">비밀번호 (4자 이상)</label><input id="sw" type="password" autocomplete="new-password" required>
      <label for="sw2">비밀번호 확인</label><input id="sw2" type="password" autocomplete="new-password" required>
      <label for="sn">성명</label><input id="sn" autocomplete="name" required>
      <label for="sc">소속 운송사</label><input id="sc" placeholder="운송사 이름" required>
      <label class="check"><input type="checkbox" id="solo"> 개인 사업자입니다</label>
      <fieldset class="fuel"><legend>주로 싣는 기름 (출하 유종)</legend>
        <label><input type="radio" name="fuel" value="등유" required><span>등유</span><small>상부 출하</small></label>
        <label><input type="radio" name="fuel" value="경유"><span>경유</span><small>상부 출하</small></label>
        <label><input type="radio" name="fuel" value="휘발유"><span>휘발유</span><small>하부 출하</small></label>
      </fieldset>
      <p class="note">유종은 가입 뒤 관리자만 바꿀 수 있습니다.</p>
      <div class="consent">
        <b>개인정보 수집·이용 동의</b>
        <p>수집 항목: 차량번호, 성명, 소속 운송사, 출하 유종, 교육·시험 기록<br>목적: 출하 안전 교육 이수 관리<br>보유 기간: 회원 탈퇴 또는 교육 관리 종료 시까지</p>
        <label class="check"><input type="checkbox" id="agree" required> 위 내용에 동의합니다</label>
      </div>
      <button class="big primary" type="submit">가입 신청</button>
    </form>
    <p class="msg" role="status"></p>
    <button class="big ghost" id="toLogin" type="button">로그인 화면으로</button>`);
  $a("#toLogin").onclick = () => showLogin();
  $a("#solo").onchange = (e) => { const c = $a("#sc"); c.value = e.target.checked ? "개인" : ""; c.readOnly = e.target.checked; };
  $a("#signForm").onsubmit = async (ev) => {
    ev.preventDefault();
    if ($a("#sw").value !== $a("#sw2").value) return msg("비밀번호 두 칸이 서로 다릅니다.");
    const b = ev.submitter; busyBtn(b, true);
    try {
      await rpc("signup", { p_plate: $a("#sp").value, p_pw: $a("#sw").value, p_name: $a("#sn").value, p_company: $a("#sc").value,
        p_fuel: app.querySelector('input[name="fuel"]:checked').value, p_consent: $a("#agree").checked });
      showLogin("가입 신청을 받았습니다. 관리자 승인 뒤 로그인하세요.");
    } catch (e) { msg(errText(e)); } finally { busyBtn(b, false); }
  };
}
async function logout() { document.body.classList.remove("admin-sim"); const t = token; token = null; me = null; sess.set("edu-token", null); showLogin(); try { if (t) await rpc("logout", { p_token: t }); } catch {} }

// ---------- driver home and records ----------
async function showHome() {
  const s = screen(`
    <p class="eyebrow">${esc(me.plate)} · ${esc(me.company)}</p>
    <h1>${esc(me.name)} 기사님</h1>
    <p class="lead">교육 과정: <b>${esc(modeName(me.fuel))}</b></p>
    <div class="state" id="passState">기록을 불러오는 중…</div>
    <div class="menu">
      <button class="big primary" id="goTrain" type="button">교육 받기<small>순서를 하나씩 배웁니다</small></button>
      <button class="big primary alt" id="goExam" type="button">시험 보기<small>${PASS}점 이상 합격</small></button>
      <button class="big ghost" id="goFree" type="button">자유 시뮬레이터<small>기록 없이 마음대로 조작해 봅니다</small></button>
      <button class="big ghost" id="goRec" type="button">내 기록 보기</button>
    </div>
    <div class="row-end"><label class="check"><input type="checkbox" id="voice" ${voiceOn ? "checked" : ""}> 음성 안내</label><button class="link" id="out" type="button">로그아웃</button></div>`);
  $a("#goTrain").onclick = () => runSession("training");
  $a("#goExam").onclick = () => runSession("exam");
  $a("#goRec").onclick = showMyRecords;
  $a("#goFree").onclick = openFree;
  $a("#out").onclick = logout;
  $a("#voice").onchange = (e) => setVoice(e.target.checked);
  try {
    const list = await rpc("my_attempts", { p_token: token });
    const ex = list.filter((a) => a.kind === "exam"), passed = ex.find((a) => a.passed);
    const st = s.querySelector("#passState");
    st.className = "state " + (passed ? "pass" : ex.length ? "fail" : "");
    st.textContent = passed ? `합격 (${passed.score}점 · ${day(passed.at)})` : ex.length ? `아직 합격 전 · 최고 ${Math.max(...ex.map((a) => a.score))}점` : `교육 ${list.length}회 · 시험 기록 없음`;
  } catch (e) { if (e.message === "session_expired" || e.message === "not_approved") return logout(); }
}
function recordRows(list) {
  if (!list.length) return `<p class="lead">아직 기록이 없습니다.</p>`;
  return `<div class="table-wrap"><table><thead><tr><th>날짜</th><th>구분</th><th>점수</th><th>결과</th><th>틀린 단계</th></tr></thead><tbody>${list.map((a) => `
    <tr><td>${esc(when(a.at))}</td><td>${a.kind === "exam" ? "시험" : "교육"}</td><td class="num">${a.score ?? "-"}</td>
    <td>${a.kind === "exam" ? (a.passed ? '<span class="pill pass">합격</span>' : '<span class="pill fail">불합격</span>') : "이수"}</td>
    <td>${esc((Array.isArray(a.mistakes) ? a.mistakes : []).join(", ")) || "-"}</td></tr>`).join("")}</tbody></table></div>`;
}
async function showMyRecords() {
  screen(`<h1>내 기록</h1><div id="rec">불러오는 중…</div><button class="big ghost" id="home" type="button">처음 화면으로</button>`);
  $a("#home").onclick = showHome;
  try { $a("#rec").innerHTML = recordRows(await rpc("my_attempts", { p_token: token })); } catch (e) { $a("#rec").textContent = errText(e); }
}

// ---------- training and exam in the simulator ----------
let session = null;
function enterSim() { document.body.classList.add("easy"); app.hidden = true; coach.hidden = false; quitBtn.hidden = false; setVoice(voiceOn); voiceBtn.hidden = false; window.SIM?.resetCam(); document.querySelector("#stage")?.append(coach, quitBtn, voiceBtn); window.dispatchEvent(new Event("resize")); }
function leaveSim() { document.body.classList.remove("easy"); coach.hidden = true; quitBtn.hidden = true; voiceBtn.hidden = true; try { speechSynthesis.cancel(); } catch {} window.dispatchEvent(new Event("resize")); }
quitBtn.onclick = () => {
  if (session?.kind === "exam" && quitBtn.dataset.sure !== "1") { quitBtn.dataset.sure = "1"; quitBtn.textContent = "중단하면 0점 기록 · 한 번 더 누르기"; setTimeout(() => { quitBtn.dataset.sure = ""; quitBtn.textContent = "그만하기"; }, 4000); return; }
  quitBtn.dataset.sure = ""; quitBtn.textContent = "그만하기";
  if (session) session.quit = true; session?.wake?.();
};
const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [a[i], a[j]] = [a[j], a[i]]; } return a; };
function card(html, slim = false) { coach.innerHTML = html; coach.classList.toggle("slim", slim); } // slim: a one-line strip while the driver works, so the scene stays visible
function choose(buttons) { // resolve with the pressed button's value, or "quit"
  return new Promise((res) => {
    session.wake = () => res("quit");
    coach.querySelectorAll("[data-v]").forEach((b) => (b.onclick = () => res(buttons[+b.dataset.v])));
  });
}
async function perform(SIM, i) { // let the driver act out step i, then wait until it is really done
  const st = SIM.STEPS[SIM.mode()][i], t0 = Date.now();
  while (!SIM.stepEnabled(i) && Date.now() - t0 < 5000) { if (session.quit) return; await sleep(100); }
  SIM.runStep(i);
  while (!(st.done() && !SIM.busy())) { if (session.quit) return; await sleep(150); if (Date.now() - t0 > 180000) break; }
}
async function askEvent(ev, head, kind) { // an abnormal situation: training shows the answer, the exam asks it. Resolves true (first try), false, or "quit"
  if (kind === "training") {
    card(`${head}<h2 class="bad">이런 일이 생기면</h2><p>${esc(ev.s)}</p><p><b>이렇게 합니다:</b> ${esc(ev.ok)}</p>
      <button class="big primary" data-v="0" type="button">알겠습니다</button>
      <details><summary>이렇게 하면 안 돼요</summary><ul>${ev.wrong.map((w) => `<li><b>${esc(w.t)}</b> ${esc(w.why)}</li>`).join("")}</ul></details>`);
    say(`이런 일이 생기면. ${ev.s} ${ev.ok}`);
    return (await choose([1])) === "quit" || session.quit ? "quit" : true;
  }
  let first = true;
  for (;;) {
    const opts = shuffle([{ ok: true, t: ev.ok }, ...ev.wrong]);
    card(`${head}<h2 class="bad">${esc(ev.s)}</h2><p>어떻게 할까요?</p><div class="opts">${opts.map((o, k) => `<button class="big opt" data-v="${k}" type="button">${esc(o.t)}</button>`).join("")}</div>`);
    say(`${ev.s} 어떻게 할까요?`);
    const pick = await choose(opts);
    if (pick === "quit" || session.quit) return "quit";
    if (pick.ok) return first;
    first = false;
    card(`${head}<h2 class="bad">다시 생각해 보세요</h2><p>${esc(pick.why)}</p><button class="big primary" data-v="0" type="button">다시 고르기</button>`);
    say(pick.why);
    if ((await choose([1])) === "quit") return "quit";
  }
}
async function runSession(kind) {
  const SIM = await waitSim(), m = modeOf(me.fuel), Q = QUESTIONS[m];
  session = { kind, quit: false };
  enterSim(); SIM.setAuto(false); SIM.resetScene(m); SIM.goView("follow");
  const steps = SIM.STEPS[m], mistakes = []; let firstTry = 0, doneSteps = 0;
  const evs = kind === "exam" ? [EVENTS[m][(Math.random() * EVENTS[m].length) | 0]] : EVENTS[m], total = steps.length + (kind === "exam" ? 1 : 0);
  for (let i = 0; i < steps.length && !session.quit; i++) {
    const head = `<p class="step-no">${i + 1} / ${steps.length} 단계 · ${kind === "exam" ? "시험" : "교육"}</p>`;
    for (const ev of evs.filter((e) => e.at === i)) {
      const r = await askEvent(ev, head, kind);
      if (r === "quit") break;
      if (r) firstTry++; else if (!mistakes.includes(ev.tag)) mistakes.push(ev.tag);
    }
    if (session.quit) break;
    let first = true;
    for (;;) {
      let pick;
      if (kind === "training") {
        card(`${head}<h2>${esc(steps[i].t)}</h2><p>${esc(Q[i].say)}</p>
          <button class="big primary" data-v="0" type="button">이 단계 하기</button>
          <details><summary>이렇게 하면 안 돼요</summary><ul>${Q[i].wrong.map((w) => `<li><b>${esc(w.t)}</b> ${esc(w.why)}</li>`).join("")}</ul></details>`);
        say(`${steps[i].t}. ${Q[i].say}`);
        pick = await choose([{ ok: true }]);
      } else {
        const opts = shuffle([{ ok: true, t: steps[i].t }, ...Q[i].wrong]);
        card(`${head}<h2>다음에 할 일은?</h2><div class="opts">${opts.map((o, k) => `<button class="big opt" data-v="${k}" type="button">${esc(o.t)}</button>`).join("")}</div>`);
        say("다음에 할 일을 고르세요.");
        pick = await choose(opts);
      }
      if (pick === "quit" || session.quit) break;
      if (pick.ok) break;
      first = false; if (!mistakes.includes(steps[i].t)) mistakes.push(steps[i].t);
      card(`${head}<h2 class="bad">다시 생각해 보세요</h2><p>${esc(pick.why)}</p><button class="big primary" data-v="0" type="button">다시 고르기</button>`);
      say(pick.why);
      if ((await choose([1])) === "quit") break;
    }
    if (session.quit) break;
    if (first) firstTry++;
    card(`<p class="working">작업 중 ${i + 1}/${steps.length} · ${esc(steps[i].t)}</p>`, true);
    await perform(SIM, i);
    if (!session.quit) doneSteps = i + 1;
  }
  const quit = session.quit; session = null; SIM.setAuto(false);
  if (quit) {
    if (kind === "exam") { try { await rpc("record_attempt", { p_token: token, p_kind: "exam", p_score: 0, p_mistakes: [...mistakes, `중단 (${doneSteps}/${steps.length}단계)`] }); } catch {} }
    leaveSim(); poke(); return showHome();
  }
  const score = Math.round((100 * firstTry) / total);
  let saved = null, err = "";
  try { saved = await rpc("record_attempt", { p_token: token, p_kind: kind, p_score: kind === "exam" ? score : null, p_mistakes: mistakes }); }
  catch (e) { err = errText(e); }
  leaveSim(); poke();
  const passed = kind === "exam" && score >= PASS;
  screen(kind === "exam" ? `
    <p class="eyebrow">시험 결과</p>
    <div class="result ${passed ? "pass" : "fail"}"><span class="score">${score}<small>점</small></span><b>${passed ? "합격" : "불합격"}</b></div>
    <p class="lead">${passed ? "수고하셨습니다. 합격 기록이 저장되었습니다." : `${PASS}점 이상이면 합격입니다. 교육을 한 번 더 받고 다시 도전하세요.`}</p>
    ${mistakes.length ? `<p>틀린 단계: ${esc(mistakes.join(", "))}</p>` : "<p>모든 단계를 한 번에 맞혔습니다.</p>"}
    ${err ? `<p class="msg">${esc(err)} 결과가 저장되지 않았습니다.</p>` : ""}
    <button class="big primary" id="home" type="button">처음 화면으로</button>` : `
    <p class="eyebrow">교육 완료</p><h1>수고하셨습니다</h1>
    <p class="lead">${esc(modeName(me.fuel))} 순서를 끝까지 마쳤습니다. 준비되면 시험을 보세요.</p>
    ${err ? `<p class="msg">${esc(err)} 기록이 저장되지 않았습니다.</p>` : ""}
    <button class="big primary" id="home" type="button">처음 화면으로</button>`);
  say(kind === "exam" ? `${score}점, ${passed ? "합격입니다" : "불합격입니다"}.` : "교육을 마쳤습니다.");
  $a("#home").onclick = showHome;
  if (saved == null && !err) return;
}

// ---------- admin ----------
async function renderStats(body) { // which steps drivers get wrong most often in exams: where to focus training
  body.innerHTML = "불러오는 중…";
  let list; try { list = await rpc("admin_all_attempts", { p_token: token }); } catch (e) { body.textContent = errText(e); return; }
  const SIM = await waitSim(), out = [];
  for (const m of ["bottom", "top"]) {
    const ex = list.filter((a) => a.kind === "exam" && a.mode === m), n = ex.length;
    const names = [...SIM.STEPS[m].map((s) => s.t), ...EVENTS[m].map((e) => e.tag).filter((t, i, all) => all.indexOf(t) === i)];
    const rows = names.map((t) => ({ t, c: ex.filter((a) => Array.isArray(a.mistakes) && a.mistakes.includes(t)).length })).sort((x, y) => y.c - x.c);
    const quit = ex.filter((a) => (a.mistakes || []).some((x) => String(x).startsWith("중단"))).length;
    out.push(`<h2>${m === "bottom" ? "하부 출하 (휘발유)" : "상부 출하 (등유·경유)"} · 시험 ${n}회${quit ? ` (중단 ${quit}회)` : ""}</h2>` + (n ? `<div class="table-wrap"><table class="stats"><thead><tr><th>단계·상황</th><th>틀린 시험</th><th>비율</th></tr></thead><tbody>${rows.map((r) => {
      const pct = Math.round((100 * r.c) / n);
      return `<tr><td>${esc(r.t)}</td><td class="num">${r.c}회</td><td><span class="meter"><i style="width:${pct}%"></i></span> <span class="num">${pct}%</span></td></tr>`; }).join("")}</tbody></table></div>` : '<p class="lead">아직 시험 기록이 없습니다.</p>'));
  }
  body.innerHTML = `<p class="note">시험에서 처음 고른 답이 틀린 횟수입니다. 많이 틀리는 단계를 교육 때 더 설명하세요.</p>${out.join("")}`;
}
let drivers = [], tab = "pending";
const lib = (src, glob) => new Promise((res, rej) => { if (window[glob]) return res(window[glob]); const s = document.createElement("script"); s.src = src; s.onload = () => res(window[glob]); s.onerror = rej; document.head.append(s); });
const QR_LIB = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js", XLSX_LIB = "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js", PDF_LIB = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
const siteUrl = () => location.origin + location.pathname;
async function showAdmin() {
  screen(`
    <div class="admin-head"><div><p class="eyebrow">관리자 · ${esc(me.name)}</p><h1>출하 안전 교육 관리</h1></div>
      <div class="admin-actions"><button class="btn" id="qrBtn" type="button">접속 QR 코드</button><button class="btn" id="allXls" type="button">전체 기록 엑셀</button><button class="btn" id="simBtn" type="button">시뮬레이터 상세 화면</button><button class="link" id="out" type="button">로그아웃</button></div></div>
    <div class="tabs" role="tablist">
      <button role="tab" data-tab="pending" type="button">승인 대기</button><button role="tab" data-tab="all" type="button">전체 기사</button><button role="tab" data-tab="passed" type="button">합격자 명단</button><button role="tab" data-tab="stats" type="button">오답 통계</button>
    </div>
    <div id="tabBody">불러오는 중…</div><p class="msg" role="status"></p>`);
  app.classList.add("wide");
  $a("#out").onclick = () => { app.classList.remove("wide"); logout(); };
  $a("#qrBtn").onclick = showQR;
  $a("#allXls").onclick = exportAll;
<<<<<<< HEAD
  $a("#simBtn").onclick = () => { app.hidden = true; document.body.classList.add("admin-sim"); window.SIM?.resetCam(); window.SIM?.render(); backBtn.textContent = "관리자 화면으로"; backBtn.hidden = false; backBtn.classList.remove("inflow"); document.querySelector("#stage")?.append(backBtn); window.dispatchEvent(new Event("resize")); };
  app.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; renderTab(); }));
  await loadDrivers();
}
backBtn.onclick = () => { backBtn.hidden = true; app.hidden = false; document.body.classList.remove("admin-sim"); window.SIM?.render(); free = false; document.body.classList.remove("free"); poke(); window.dispatchEvent(new Event("resize")); };
=======
  $a("#simBtn").onclick = () => { app.hidden = true; document.body.classList.add("admin-sim"); backBtn.textContent = "관리자 화면으로"; backBtn.hidden = false; backBtn.classList.remove("inflow"); document.querySelector("#stage")?.append(backBtn); window.dispatchEvent(new Event("resize")); };
  app.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; renderTab(); }));
  await loadDrivers();
}
backBtn.onclick = () => { backBtn.hidden = true; app.hidden = false; document.body.classList.remove("admin-sim"); free = false; document.body.classList.remove("free"); poke(); window.dispatchEvent(new Event("resize")); };
>>>>>>> c4aa52bab63a2c5e789f9e779fa50f496946e91e
let free = false;
async function openFree() {
  const SIM = await waitSim(); free = true;
  SIM.setAuto(false); SIM.resetScene(modeOf(me.fuel)); SIM.resetCam(); SIM.goView("follow"); SIM.render();
  app.hidden = true; backBtn.textContent = "처음 화면으로"; backBtn.hidden = false; document.body.classList.add("free");
  const inflow = matchMedia("(max-width: 600px), (pointer: coarse)").matches; // phones and tablets: the button sits under the 3D view, never on it
  backBtn.classList.toggle("inflow", inflow);
  if (inflow) document.querySelector(".dock")?.before(backBtn); else document.querySelector("#stage")?.append(backBtn);
  window.dispatchEvent(new Event("resize"));
}
let adminTimer = 0;
async function loadDrivers() {
  clearInterval(adminTimer);
  adminTimer = setInterval(() => { if (!app.hidden && app.classList.contains("wide") && tab !== "history" && tab !== "stats" && !document.querySelector("#tabBody form")) loadDrivers(); }, 15000);
  try { drivers = (await rpc("admin_drivers", { p_token: token })).filter((d) => d.role !== "admin"); renderTab(); }
  catch (e) { if (e.message === "session_expired") return logout(); msg(errText(e)); }
}
function renderTab() {
  app.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  const pend = drivers.filter((d) => d.status === "pending");
  app.querySelector('[data-tab="pending"]').textContent = `승인 대기 ${pend.length}`;
  const body = $a("#tabBody");
  if (tab === "stats") return renderStats(body);
  if (tab === "passed") {
    const list = drivers.filter((d) => d.passed_at).sort((a, b) => a.passed_at.localeCompare(b.passed_at));
    body.innerHTML = `<div class="bar"><span>합격자 ${list.length}명</span><span class="grow"></span>
      <button class="btn" id="xls" type="button" ${list.length ? "" : "disabled"}>엑셀로 받기</button><button class="btn" id="pdf" type="button" ${list.length ? "" : "disabled"}>PDF로 받기</button></div>
      ${list.length ? table(list, ["plate", "name", "company", "fuel", "best", "passed_at"]) : '<p class="lead">아직 합격자가 없습니다.</p>'}`;
    body.querySelector("#xls").onclick = () => exportXlsx(list);
    body.querySelector("#pdf").onclick = () => exportPdf(list);
    return;
  }
  const list = tab === "pending" ? pend : drivers;
  body.innerHTML = list.length ? table(list, ["plate", "name", "company", "fuel", "status", "trainings", "best", "passed_at", "actions"]) : `<p class="lead">${tab === "pending" ? "승인을 기다리는 가입 신청이 없습니다." : "가입한 기사가 없습니다."}</p>`;
  body.querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => act(b.dataset.act, b.dataset.id, b)));
  body.querySelectorAll("select[data-fuel]").forEach((s) => (s.onchange = async () => {
    try { await rpc("admin_set_fuel", { p_token: token, p_driver: s.dataset.fuel, p_fuel: s.value }); msg("유종을 바꿨습니다. 다음 교육부터 바뀐 과정으로 들어갑니다.", true); await loadDrivers(); } catch (e) { msg(errText(e)); }
  }));
}
const COLS = { plate: "차량번호", name: "성명", company: "소속", fuel: "유종", status: "상태", trainings: "교육", best: "최고점", passed_at: "합격일", actions: "" };
const STATUS = { pending: '<span class="pill">대기</span>', approved: '<span class="pill pass">승인</span>', rejected: '<span class="pill fail">반려</span>' };
function cell(d, c) {
  if (c === "fuel") return `<select data-fuel="${d.id}" aria-label="${esc(d.plate)} 유종">${["등유", "경유", "휘발유"].map((f) => `<option ${f === d.fuel ? "selected" : ""}>${f}</option>`).join("")}</select>`;
  if (c === "status") return STATUS[d.status] || esc(d.status);
  if (c === "best") return d.best == null ? "-" : `<span class="num">${d.best}</span>`;
  if (c === "passed_at") return d.passed_at ? esc(day(d.passed_at)) : "-";
  if (c === "trainings") return `<span class="num">${d.trainings}</span>`;
  if (c === "actions") return `<div class="acts">${d.status !== "approved" ? `<button class="btn ok" data-act="approve" data-id="${d.id}" type="button">승인</button>` : ""}${d.status === "pending" ? `<button class="btn" data-act="reject" data-id="${d.id}" type="button">반려</button>` : ""}
    <button class="btn" data-act="history" data-id="${d.id}" type="button">기록</button><button class="btn" data-act="pw" data-id="${d.id}" type="button">비밀번호 초기화</button><button class="btn danger" data-act="del" data-id="${d.id}" type="button">삭제</button></div>`;
  return esc(d[c]);
}
const table = (list, cols) => `<div class="table-wrap"><table><thead><tr>${cols.map((c) => `<th>${COLS[c]}</th>`).join("")}</tr></thead><tbody>${list.map((d) => `<tr>${cols.map((c) => `<td>${cell(d, c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
async function act(kind, id, btn) {
  const d = drivers.find((x) => x.id === id);
  try {
    if (kind === "approve" || kind === "reject") { await rpc("admin_set_status", { p_token: token, p_driver: id, p_status: kind === "approve" ? "approved" : "rejected" }); msg(`${d.plate} ${kind === "approve" ? "승인" : "반려"}했습니다.`, true); return loadDrivers(); }
    if (kind === "history") {
      const list = await rpc("admin_attempts", { p_token: token, p_driver: id });
      $a("#tabBody").innerHTML = `<div class="bar"><b>${esc(d.plate)} · ${esc(d.name)} (${esc(d.company)})</b><span class="grow"></span><button class="btn" id="backList" type="button">목록으로</button></div>${recordRows(list)}`;
      tab = "history"; $a("#backList").onclick = () => { tab = "all"; renderTab(); }; return;
    }
    if (kind === "pw") {
      const row = btn.closest("td");
      row.innerHTML = `<form class="inline"><input type="password" aria-label="새 비밀번호" placeholder="새 비밀번호 4자 이상" required minlength="4"><button class="btn ok" type="submit">저장</button><button class="btn" type="button">취소</button></form>`;
      const f = row.querySelector("form"); f.querySelector('button[type="button"]').onclick = renderTab;
      f.onsubmit = async (ev) => { ev.preventDefault(); try { await rpc("admin_reset_password", { p_token: token, p_driver: id, p_pw: f.querySelector("input").value }); msg(`${d.plate} 비밀번호를 바꿨습니다. 기사님께 새 비밀번호를 알려 주세요.`, true); renderTab(); } catch (e) { msg(errText(e)); } };
      return;
    }
    if (kind === "del") {
      if (btn.dataset.sure !== "1") { btn.dataset.sure = "1"; btn.textContent = "정말 삭제"; setTimeout(() => { btn.dataset.sure = ""; btn.textContent = "삭제"; }, 4000); return; }
      await rpc("admin_delete", { p_token: token, p_driver: id }); msg(`${d.plate} 계정과 기록을 삭제했습니다.`, true); return loadDrivers();
    }
  } catch (e) { msg(errText(e)); }
}
const stamp = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" }).replaceAll("-", "");
const passRows = (list) => list.map((d, i) => ({ 번호: i + 1, 차량번호: d.plate, 성명: d.name, 소속: d.company, 유종: d.fuel, 최고점: d.best, 합격일: day(d.passed_at) }));
async function exportXlsx(list) {
  try {
    const X = await lib(XLSX_LIB, "XLSX"); const ws = X.utils.json_to_sheet(passRows(list));
    ws["!cols"] = [6, 12, 10, 16, 8, 8, 12].map((w) => ({ wch: w })); const wb = X.utils.book_new(); X.utils.book_append_sheet(wb, ws, "합격자");
    X.writeFile(wb, `합격자명단_${stamp()}.xlsx`);
  } catch { msg("엑셀 파일을 만들지 못했습니다. 인터넷 연결을 확인하세요."); }
}
async function exportPdf(list) { // Korean text is drawn on a canvas (system fonts), then each page goes into the PDF as an image
  try {
    const { jsPDF } = await lib(PDF_LIB, "jspdf"); await document.fonts?.load?.('700 20px "Noto Sans KR"');
    const rows = passRows(list), per = 28, W = 1240, H = 1754, doc = new jsPDF({ unit: "mm", format: "a4" });
    const cols = [["번호", 70], ["차량번호", 190], ["성명", 150], ["소속", 300], ["유종", 110], ["최고점", 110], ["합격일", 190]];
    for (let p = 0; p * per < rows.length; p++) {
      const c = document.createElement("canvas"); c.width = W; c.height = H; const g = c.getContext("2d");
      g.fillStyle = "#fff"; g.fillRect(0, 0, W, H); g.fillStyle = "#14201b"; g.textBaseline = "middle";
      g.font = '700 40px "Noto Sans KR", sans-serif'; g.fillText("출하 안전 교육 합격자 명단", 90, 120);
      g.font = '400 22px "Noto Sans KR", sans-serif'; g.fillText(`합격 기준 ${PASS}점 이상 · 출력일 ${day(new Date().toISOString())} · ${p + 1} / ${Math.ceil(rows.length / per)}쪽`, 90, 175);
      let y = 240; g.fillStyle = "#e3ece7"; g.fillRect(80, y - 26, W - 160, 52); g.fillStyle = "#14201b"; g.font = '700 22px "Noto Sans KR", sans-serif';
      let x = 90; for (const [h, w] of cols) { g.fillText(h, x, y); x += w; }
      g.font = '400 22px "Noto Sans KR", sans-serif';
      rows.slice(p * per, p * per + per).forEach((r) => { y += 48; g.strokeStyle = "#cfd8d3"; g.beginPath(); g.moveTo(80, y + 24); g.lineTo(W - 80, y + 24); g.stroke(); x = 90; for (const [h, w] of cols) { g.fillText(String(r[h] ?? ""), x, y, w - 14); x += w; } });
      if (p) doc.addPage(); doc.addImage(c.toDataURL("image/jpeg", 0.92), "JPEG", 0, 0, 210, 297);
    }
    doc.save(`합격자명단_${stamp()}.pdf`);
  } catch { msg("PDF 파일을 만들지 못했습니다. 인터넷 연결을 확인하세요."); }
}
async function exportAll() { // backup of every training and exam record
  try {
    const list = await rpc("admin_all_attempts", { p_token: token }), X = await lib(XLSX_LIB, "XLSX");
    const rows = list.map((a) => ({ 일시: when(a.at), 차량번호: a.plate, 성명: a.name, 소속: a.company, 유종: a.fuel, 구분: a.kind === "exam" ? "시험" : "교육",
      점수: a.score ?? "", 결과: a.kind === "exam" ? (a.passed ? "합격" : "불합격") : "이수", "틀린 단계": (Array.isArray(a.mistakes) ? a.mistakes : []).join(", ") }));
    const ws = X.utils.json_to_sheet(rows); ws["!cols"] = [18, 12, 10, 16, 8, 6, 6, 8, 40].map((w) => ({ wch: w }));
    const wb = X.utils.book_new(); X.utils.book_append_sheet(wb, ws, "전체 기록"); X.writeFile(wb, `교육기록_전체_${stamp()}.xlsx`);
    msg(`기록 ${rows.length}건을 받았습니다.`, true);
  } catch (e) { msg(e.message === "session_expired" ? ERR.session_expired : "엑셀 파일을 만들지 못했습니다. 인터넷 연결을 확인하세요."); }
}
async function showQR() {
  const ov = document.createElement("div"); ov.className = "qr-full";
  ov.innerHTML = `<div class="qr-card"><h2>출하 안전 교육</h2><p>휴대폰 카메라로 찍으면 교육 화면이 열립니다</p><div id="qrBox"></div><p class="url">${esc(siteUrl())}</p>
    <div class="acts"><button class="btn ok" id="qrSave" type="button">QR 이미지 받기</button><button class="btn" id="qrClose" type="button">닫기</button></div></div>`;
  document.body.append(ov);
  ov.querySelector("#qrClose").onclick = () => ov.remove();
  try {
    const QR = await lib(QR_LIB, "QRCode"); new QR(ov.querySelector("#qrBox"), { text: siteUrl(), width: 320, height: 320, correctLevel: QR.CorrectLevel.M });
    ov.querySelector("#qrSave").onclick = () => { const c = ov.querySelector("#qrBox canvas"); const a = document.createElement("a"); a.href = c.toDataURL("image/png"); a.download = "출하안전교육_QR.png"; a.click(); };
  } catch { ov.querySelector("#qrBox").textContent = "QR 코드를 만들지 못했습니다. 인터넷 연결을 확인하세요."; }
}

// shared devices: nobody touching the screen for a while logs the account out (never during training or an exam)
let idleT = 0;
function poke() {
  clearTimeout(idleT);
  if (token && !session) idleT = setTimeout(() => { if (token && !session && !free) { app.classList.remove("wide"); logout().then(() => msg("한동안 사용이 없어 로그아웃했습니다.")); } }, (me?.role === "admin" ? 30 : 5) * 60000);
}
for (const ev of ["pointerdown", "keydown"]) addEventListener(ev, poke, { passive: true });

// ---------- start ----------
async function route() {
  leaveSim(); app.classList.remove("wide");
  if (!token) return showLogin();
  try { me = { ...(me || {}), ...(await rpc("me", { p_token: token })) }; }
  catch (e) { token = null; sess.set("edu-token", null); return showLogin(e.message === "network" ? ERR.network : ""); }
  poke();
  return me.role === "admin" ? showAdmin() : showHome();
}
route();
