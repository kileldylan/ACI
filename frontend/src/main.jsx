import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function useApiCredentials() {
  const [credentials, setCredentials] = useState(null);
  const [form, setForm] = useState({ username: "", password: "" });

  function signIn(event) {
    event.preventDefault();
    if (!form.username || !form.password) return;
    setCredentials({ ...form });
  }

  return { credentials, form, setForm, signIn, signOut: () => setCredentials(null) };
}

async function request(path, credentials, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Basic ${btoa(`${credentials.username}:${credentials.password}`)}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function Login({ auth }) {
  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="brand-mark">ACI<span>/</span></div>
        <p className="kicker">Delivery intelligence</p>
        <h1>Evidence before conclusions.</h1>
        <p className="login-copy">Connect a repository, choose a pull request, and see what the evidence can actually prove.</p>
        <form onSubmit={auth.signIn} className="login-form">
          <label>Username<input autoComplete="username" value={auth.form.username} onChange={(event) => auth.setForm({ ...auth.form, username: event.target.value })} /></label>
          <label>Password<input type="password" autoComplete="current-password" value={auth.form.password} onChange={(event) => auth.setForm({ ...auth.form, password: event.target.value })} /></label>
          <button className="primary-button" type="submit">Open workspace <span>↗</span></button>
        </form>
        <p className="security-note">Credentials stay in memory for this session.</p>
      </section>
      <aside className="login-aside"><div className="signal-line" /><p>REQUIREMENT → PR → COMMITS → EVIDENCE → DECISION</p><strong>Make delivery<br />auditable.</strong></aside>
    </main>
  );
}

function StatusPill({ status }) {
  const label = status || "unknown";
  return <span className={`status-pill status-${label}`}>{label}</span>;
}

function App() {
  const auth = useApiCredentials();
  if (!auth.credentials) return <Login auth={auth} />;
  return <Workspace credentials={auth.credentials} signOut={auth.signOut} />;
}

function Workspace({ credentials, signOut }) {
  const [repositories, setRepositories] = useState([]);
  const [repository, setRepository] = useState(null);
  const [pullRequests, setPullRequests] = useState([]);
  const [requirements, setRequirements] = useState([]);
  const [selectedPr, setSelectedPr] = useState(null);
  const [selectedRequirement, setSelectedRequirement] = useState(null);
  const [verification, setVerification] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [decision, setDecision] = useState(null);
  const [notice, setNotice] = useState({ type: "", text: "" });
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  async function loadRepositories() {
    setLoading(true);
    try {
      const data = await request("/repositories/", credentials);
      setRepositories(data);
      if (!repository && data[0]) setRepository(data[0]);
      setNotice({ type: "", text: "" });
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally { setLoading(false); }
  }

  async function loadRepositoryData(repo) {
    if (!repo) return;
    try {
      const [prs, reqs] = await Promise.all([
        request(`/repositories/${repo.id}/pull-requests/`, credentials),
        request(`/repositories/${repo.id}/requirements/`, credentials),
      ]);
      setPullRequests(prs);
      setRequirements(reqs);
      setSelectedPr(prs[0] || null);
      setSelectedRequirement(reqs[0] || null);
    } catch (error) { setNotice({ type: "error", text: error.message }); }
  }

  async function loadResult() {
    if (!repository || !selectedPr || !selectedRequirement) return;
    try {
      const [verifications, evidenceItems, decisions] = await Promise.all([
        request(`/verifications/?repository=${repository.id}`, credentials),
        request(`/evidence/?repository=${repository.id}`, credentials),
        request(`/delivery-decisions/?repository=${repository.id}&current=true`, credentials),
      ]);
      const current = verifications.find((item) => item.pull_request === selectedPr.id && item.requirement === selectedRequirement.id);
      setVerification(current || null);
      setEvidence(evidenceItems.filter((item) => item.pull_request === selectedPr.id && item.requirement === selectedRequirement.id));
      const currentDecision = decisions.find((item) => item.verification === current?.id);
      setDecision(currentDecision || null);
    } catch (error) { setNotice({ type: "error", text: error.message }); }
  }

  async function startVerification() {
    if (!repository || !selectedPr || !selectedRequirement) return;
    setStarting(true);
    try {
      await request(`/repositories/${repository.id}/start-verification/`, credentials, {
        method: "POST",
        body: JSON.stringify({ pull_request_id: selectedPr.id, requirement_id: selectedRequirement.id }),
      });
      setNotice({ type: "success", text: "Verification queued. Run the worker, then refresh this view." });
      await loadResult();
    } catch (error) { setNotice({ type: "error", text: error.message }); }
    finally { setStarting(false); }
  }

  useEffect(() => { loadRepositories(); }, []);
  useEffect(() => { loadRepositoryData(repository); }, [repository]);
  useEffect(() => { loadResult(); }, [selectedPr, selectedRequirement, repository]);

  const stats = [
    ["Repositories", repositories.length, "connected"],
    ["Open pull requests", pullRequests.filter((item) => item.state === "open").length, "in selected repo"],
    ["Evidence items", evidence.length, "for selected delivery"],
    ["Decision", decision?.status || "—", decision ? "current" : "awaiting run"],
  ];

  return <div className="app-shell">
    <header className="topbar"><div className="brand-mark">ACI<span>/</span></div><div className="topbar-title"><span>Workspace</span><strong>Delivery intelligence</strong></div><div className="topbar-actions"><button className="icon-button" onClick={loadResult} title="Refresh results">↻</button><button className="user-button" onClick={signOut}><span className="avatar">{credentials.username[0]?.toUpperCase()}</span>{credentials.username}<span>⌄</span></button></div></header>
    <main className="workspace">
      <section className="intro"><div><p className="kicker">Verification workspace / 01</p><h1>See what shipped.<br /><em>Prove what holds.</em></h1></div><div className="intro-note"><span className="live-dot" /> Live evidence graph<br /><small>Webhook-connected repositories</small></div></section>
      {notice.text && <div className={`notice ${notice.type}`}>{notice.text}</div>}
      <section className="stats-grid">{stats.map(([label, value, detail]) => <div className="stat" key={label}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>)}</section>
      <section className="control-grid">
        <div className="control-block"><label>Repository</label><select value={repository?.id || ""} onChange={(event) => setRepository(repositories.find((item) => item.id === Number(event.target.value)))}><option value="">{loading ? "Loading repositories..." : "Select repository"}</option>{repositories.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></div>
        <div className="control-block"><label>Pull request</label><select value={selectedPr?.id || ""} onChange={(event) => setSelectedPr(pullRequests.find((item) => item.id === Number(event.target.value)))}><option value="">Select pull request</option>{pullRequests.map((item) => <option value={item.id} key={item.id}>#{item.number} · {item.title}</option>)}</select></div>
        <div className="control-block"><label>Requirement</label><select value={selectedRequirement?.id || ""} onChange={(event) => setSelectedRequirement(requirements.find((item) => item.id === Number(event.target.value)))}><option value="">Select requirement</option>{requirements.map((item) => <option value={item.id} key={item.id}>{item.external_id} · {item.title}</option>)}</select></div>
        <button className="primary-button start-button" disabled={!selectedPr || !selectedRequirement || starting} onClick={startVerification}>{starting ? "Queueing..." : "Start verification"}<span>→</span></button>
      </section>
      <section className="analysis-layout">
        <article className="analysis-card"><div className="card-heading"><div><p className="kicker">Current delivery</p><h2>{selectedPr ? `PR #${selectedPr.number} / ${selectedPr.title}` : "Choose a pull request"}</h2></div>{verification && <StatusPill status={verification.status} />}</div>{selectedPr && <div className="pr-meta"><span>{selectedPr.author}</span><span>{selectedPr.source_branch} → {selectedPr.target_branch}</span><span>{selectedPr.head_sha.slice(0, 8)}</span></div>}<div className="decision-panel"><div className="decision-label">Delivery decision</div><strong>{decision?.status || verification?.status || "Not evaluated"}</strong><p>{decision?.summary || verification?.summary || "Select a PR and start a verification run to generate an auditable conclusion."}</p>{decision?.rationale && <div className="rationale">{decision.rationale.required_criteria_count ?? 0} required criteria · {decision.rationale.missing_required_criteria?.length ?? 0} missing</div>}</div></article>
        <article className="evidence-card"><div className="card-heading"><div><p className="kicker">Evidence ledger</p><h2>{evidence.length} signals collected</h2></div><span className="ledger-icon">◎</span></div><div className="evidence-list">{evidence.length ? evidence.map((item) => <div className="evidence-row" key={item.id}><span className={`evidence-icon ${item.status}`}>{item.evidence_type === "code" ? "⌘" : item.evidence_type === "test" ? "✓" : "◌"}</span><div><strong>{item.evidence_type} evidence</strong><p>{item.description}</p></div><StatusPill status={item.status} /></div>) : <div className="empty-state">No evidence yet.<br /><small>Run the worker after the verification is queued.</small></div>}</div></article>
      </section>
    </main>
    <footer className="footer"><span>ACI / Evidence before conclusions</span><span>API {API_BASE}</span></footer>
  </div>;
}

createRoot(document.getElementById("root")).render(<StrictMode><App /></StrictMode>);
