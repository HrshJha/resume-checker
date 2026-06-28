"""Small browser UI for local resume matching."""

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Resume Matcher</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #5f6b7a;
      --line: #dfe3e8;
      --accent: #0b6bcb;
      --good: #137333;
      --warn: #b06000;
      --bad: #b3261e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0; font-size: 22px; font-weight: 700; }
    h2 { margin: 0 0 14px; font-size: 16px; }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 20px auto 40px;
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 16px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      font-size: 13px;
      color: var(--muted);
      font-weight: 600;
    }
    input, textarea, button {
      width: 100%;
      font: inherit;
      border-radius: 6px;
    }
    input, textarea {
      border: 1px solid var(--line);
      padding: 10px 11px;
      background: white;
      color: var(--text);
    }
    textarea { min-height: 220px; resize: vertical; line-height: 1.4; }
    button {
      border: 0;
      background: var(--accent);
      color: white;
      padding: 11px 12px;
      margin-top: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary {
      background: #eef4fb;
      color: var(--accent);
      border: 1px solid #c9ddf3;
    }
    button:disabled { opacity: 0.55; cursor: not-allowed; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .status {
      margin-top: 12px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      background: #fbfcfd;
      min-height: 42px;
      white-space: pre-wrap;
    }
    .score {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }
    .metric strong { display: block; font-size: 22px; margin-bottom: 4px; }
    .metric span { color: var(--muted); font-size: 12px; }
    ul { margin: 8px 0 0; padding-left: 18px; }
    li { margin: 4px 0; }
    .pill {
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 8px;
      margin: 3px;
      font-size: 12px;
      background: #fbfcfd;
    }
    .good { color: var(--good); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    @media (max-width: 900px) {
      main, .grid { grid-template-columns: 1fr; }
      .score { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Resume Matcher</h1>
  </header>
  <main>
    <section>
      <h2>Credentials</h2>
      <label for="username">Username</label>
      <input id="username" value="testuser" autocomplete="username" />
      <label for="password">Password</label>
      <input id="password" value="testpassword123" type="password" autocomplete="current-password" />
      <button id="loginBtn">Register or Login</button>
      <div id="authStatus" class="status">Not logged in.</div>

      <h2 style="margin-top:18px">Resume</h2>
      <label for="resumeFile">PDF or DOCX resume</label>
      <input id="resumeFile" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" />
      <button id="uploadBtn" disabled>Upload Resume</button>
      <div id="uploadStatus" class="status">Upload a resume after login.</div>
    </section>

    <section>
      <h2>Job Description</h2>
      <label for="jdText">Paste the job description to match against</label>
      <textarea id="jdText">Senior Backend Engineer

Requirements:
- 5+ years of experience in backend development
- Strong proficiency in Python, Go, or Java
- Experience with PostgreSQL, Redis, and Kafka
- Familiarity with Docker, Kubernetes, and CI/CD pipelines
- Experience with REST APIs and GraphQL

Preferred:
- Experience with AWS or GCP
- Contributions to open source projects</textarea>
      <button id="matchBtn" disabled>Check Match</button>
      <div id="matchStatus" class="status">Login, upload a resume, then check match.</div>

      <div id="results" style="display:none; margin-top:16px">
        <div class="score">
          <div class="metric"><strong id="overallScore">0%</strong><span>Final Match Score</span></div>
          <div class="metric"><strong id="skillScore">0%</strong><span>Skills (40%)</span></div>
          <div class="metric"><strong id="expScore">0%</strong><span>Experience (20%)</span></div>
          <div class="metric"><strong id="semanticScore">0%</strong><span>Semantic Match (10%)</span></div>
        </div>
        <div class="grid">
          <section>
            <h2>Matched Skills</h2>
            <div id="matchedSkills"></div>
          </section>
          <section>
            <h2>Missing Skills</h2>
            <div id="missingSkills"></div>
          </section>
        </div>
        <section style="margin-top:16px">
          <h2>Details</h2>
          <div id="details"></div>
        </section>
      </div>
    </section>
  </main>

  <script>
    const state = { token: "", candidateId: "", jdId: "", candidate: null, jd: null, rank: null };
    const $ = (id) => document.getElementById(id);

    function setStatus(id, text) { $(id).textContent = text; }
    function authHeaders() { return { Authorization: `Bearer ${state.token}` }; }
    function pct(n) { return `${Math.round((Number(n) || 0) * 100)}%`; }
    function escapeHtml(text) {
      return String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function pills(items, klass = "") {
      if (!items.length) return '<span class="pill">None</span>';
      return items.map(x => `<span class="pill ${klass}">${escapeHtml(x)}</span>`).join("");
    }
    async function readJson(response) {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    }

    async function registerOrLogin() {
      const username = $("username").value.trim();
      const password = $("password").value;
      if (!username || !password) {
        setStatus("authStatus", "Enter username and password.");
        return;
      }
      $("loginBtn").disabled = true;
      setStatus("authStatus", "Registering or logging in...");
      try {
        const register = await fetch("/api/v1/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password, role: "recruiter" })
        });
        if (!register.ok && register.status !== 400) await readJson(register);

        const form = new URLSearchParams();
        form.set("username", username);
        form.set("password", password);
        const login = await fetch("/api/v1/auth/token", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: form
        });
        const data = await readJson(login);
        state.token = data.access_token;
        $("uploadBtn").disabled = false;
        $("matchBtn").disabled = false;
        setStatus("authStatus", "Logged in. Now upload a resume.");
      } catch (err) {
        setStatus("authStatus", `Login failed: ${err.message}`);
      } finally {
        $("loginBtn").disabled = false;
      }
    }

    async function uploadResume() {
      const file = $("resumeFile").files[0];
      if (!file) {
        setStatus("uploadStatus", "Choose a PDF or DOCX file first.");
        return;
      }
      $("uploadBtn").disabled = true;
      setStatus("uploadStatus", "Uploading resume...");
      try {
        const form = new FormData();
        form.append("file", file);
        const upload = await fetch("/api/v1/candidates/upload", {
          method: "POST",
          headers: authHeaders(),
          body: form
        });
        const data = await readJson(upload);
        state.candidateId = data.candidate_id;
        setStatus("uploadStatus", `Uploaded. Candidate ID: ${state.candidateId}\\nProcessing...`);
        await pollCandidate();
      } catch (err) {
        setStatus("uploadStatus", `Upload failed: ${err.message}`);
      } finally {
        $("uploadBtn").disabled = false;
      }
    }

    async function pollCandidate() {
      for (let i = 0; i < 20; i++) {
        await new Promise(resolve => setTimeout(resolve, i === 0 ? 500 : 1500));
        const statusResponse = await fetch(`/api/v1/candidates/${state.candidateId}/status`, {
          headers: authHeaders()
        });
        const status = await readJson(statusResponse);
        setStatus("uploadStatus", `Candidate ID: ${state.candidateId}\\nStatus: ${status.status}`);
        if (status.status === "indexed") {
          const detailResponse = await fetch(`/api/v1/candidates/${state.candidateId}`, {
            headers: authHeaders()
          });
          state.candidate = await readJson(detailResponse);
          setStatus("uploadStatus", `Resume ready. Parsed ${state.candidate.skills.length} skills.`);
          return;
        }
        if (status.status === "failed") {
          throw new Error("Resume parsing failed. Check server logs.");
        }
      }
      throw new Error("Still processing. Try Check Match again in a few seconds.");
    }

    function computeSkillBreakdown(required, candidateSkills) {
      const requiredLower = required.map(s => String(s).toLowerCase());
      const candidateLower = new Map(candidateSkills.map(s => [String(s).toLowerCase(), s]));
      const matched = [];
      const missing = [];
      required.forEach((skill, i) => {
        const exact = candidateLower.get(requiredLower[i]);
        if (exact) matched.push(exact);
        else missing.push(skill);
      });
      return {
        matched,
        missing,
        ratio: required.length ? matched.length / required.length : 0
      };
    }

    async function checkMatch() {
      if (!state.token) {
        setStatus("matchStatus", "Login first.");
        return;
      }
      if (!state.candidateId) {
        setStatus("matchStatus", "Upload a resume first.");
        return;
      }
      $("matchBtn").disabled = true;
      setStatus("matchStatus", "Checking match...");
      try {
        if (!state.candidate) await pollCandidate();
        const jdText = $("jdText").value.trim();
        if (jdText.length < 50) throw new Error("Job description must be at least 50 characters.");

        const jdResponse = await fetch("/api/v1/jobs/", {
          method: "POST",
          headers: { ...authHeaders(), "Content-Type": "application/json" },
          body: JSON.stringify({ jd_text: jdText })
        });
        state.jd = await readJson(jdResponse);
        state.jdId = state.jd.jd_id;

        const rankResponse = await fetch("/api/v1/search/rank", {
          method: "POST",
          headers: { ...authHeaders(), "Content-Type": "application/json" },
          body: JSON.stringify({ jd_id: state.jdId, top_k: 100 })
        });
        const rankData = await readJson(rankResponse);
        state.rank = rankData.results.find(r => r.candidate_id === state.candidateId) || null;

        const required = state.jd.required_skills || [];
        const candidateSkills = state.candidate.skills || [];
        const skillBreakdown = computeSkillBreakdown(required, candidateSkills);
        // Fetch Explanation
        const explainResponse = await fetch(`/api/v1/search/rank/${state.jdId}/${state.candidateId}/explain`, {
          headers: authHeaders()
        });
        const explainData = await readJson(explainResponse);

        const rankScore = state.rank ? state.rank.final_score : 0;
        
        $("results").style.display = "block";
        $("overallScore").textContent = pct(rankScore);
        $("skillScore").textContent = state.rank ? pct(state.rank.semantic_score) : "0%";
        $("expScore").textContent = state.rank ? pct(state.rank.career_score) : "0%";
        $("semanticScore").textContent = state.rank ? pct(state.rank.behavior_score) : "0%";
        
        $("matchedSkills").innerHTML = pills(skillBreakdown.matched, "good");
        $("missingSkills").innerHTML = pills(skillBreakdown.missing, skillBreakdown.missing.length ? "bad" : "good");
        $("details").innerHTML = `
          <ul>
            <li><strong>JD role:</strong> ${escapeHtml(state.jd.role || "Unknown")}</li>
            <li><strong>JD domain:</strong> ${escapeHtml(state.jd.industry || "Unknown")}</li>
            <li><strong>Candidate Rank:</strong> ${state.rank ? "#" + state.rank.rank : "Not in ranked list"}</li>
            <li><strong>Formula:</strong> 40% Skills, 20% Experience, 15% Projects, 10% Education, 10% Semantic (BM25+CE), 5% Preferred</li>
          </ul>
          <div class="status" style="margin-top:16px">
            <strong>Detailed Explanation:</strong><br><br>
            ${escapeHtml(explainData.natural_language_explanation || state.rank.explanation_summary).replace(/\\n/g, '<br>')}
          </div>
          <div style="margin-top:16px">
            <strong>All Parsed Candidate Skills:</strong><br>${pills(candidateSkills)}
          </div>
        `;
        setStatus("matchStatus", "Match complete.");
      } catch (err) {
        setStatus("matchStatus", `Match failed: ${err.message}`);
      } finally {
        $("matchBtn").disabled = false;
      }
    }

    $("loginBtn").addEventListener("click", registerOrLogin);
    $("uploadBtn").addEventListener("click", uploadResume);
    $("matchBtn").addEventListener("click", checkMatch);
  </script>
</body>
</html>
"""
