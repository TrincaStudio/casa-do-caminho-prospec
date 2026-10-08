import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createClient, Session } from '@supabase/supabase-js';
import { AlertTriangle, Building2, CheckCircle2, ChevronDown, ChevronUp, Clock3, Database, ExternalLink, LogOut, Plus, Search, XCircle } from 'lucide-react';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
const supabase = SUPABASE_URL && SUPABASE_ANON_KEY ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

type Source = { id: string; url: string; normalized_url: string; title?: string; domain?: string; source_type: string; accessed_at?: string };
type Evidence = { id: string; excerpt: string; source?: Source };
type Result = { key?: string; question_key: string; question: string; status: string; answer: string; summary: string; evidences: Evidence[] };
type Section = { key: string; title: string; results: Result[] };
type Progress = { key: string; title: string; status: string; completed_items: number; total_items: number; message?: string };
type Usage = { brave_searches: number; urls_selected: number; firecrawl_calls: number; openai_calls: number; openai_input_tokens: number; openai_output_tokens: number; duration_ms: number; warnings: number };
type Research = { id: string; status: string; company: { name: string; cnpj?: string; website?: string }; sections?: Section[]; progress?: Progress[]; usage?: Usage; error_public?: string; completed_at?: string };

const resultLabels: Record<string, string> = {
  FOUND: 'ENCONTRADO',
  NOT_FOUND: 'NAO LOCALIZADO',
  INCONCLUSIVE: 'INCONCLUSIVO',
  REQUIRES_HUMAN_REVIEW: 'REQUER VALIDACAO HUMANA',
};

function authHeader(session: Session | null): Record<string, string> {
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

function Badge({ status }: { status: string }) {
  const icon = status === 'FOUND' ? <CheckCircle2 size={14} /> : status === 'REQUIRES_HUMAN_REVIEW' ? <AlertTriangle size={14} /> : <Clock3 size={14} />;
  return <span className={`badge ${status.toLowerCase()}`}>{icon} {resultLabels[status] || status}</span>;
}

function Login({ onSession }: { onSession: (session: Session) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!supabase) {
      setError('Configure VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY.');
      return;
    }
    setLoading(true);
    setError('');
    const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (authError || !data.session) {
      setError(authError?.message || 'Nao foi possivel autenticar.');
      return;
    }
    onSession(data.session);
  }

  return <main><Header session={null} onLogout={() => {}} /><section className="login"><form onSubmit={submit}><p className="eyebrow">Acesso interno</p><h1>Casa do Caminho</h1><label>Email<input required type="email" value={email} onChange={e => setEmail(e.target.value)} /></label><label>Senha<input required type="password" value={password} onChange={e => setPassword(e.target.value)} /></label>{error && <p className="error">{error}</p>}<button className="primary full" disabled={loading}>{loading ? 'Entrando...' : 'Entrar'}</button></form></section></main>;
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [items, setItems] = useState<Research[]>([]);
  const [active, setActive] = useState<Research | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', cnpj: '', website: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession));
    return () => subscription.subscription.unsubscribe();
  }, []);

  async function api(path: string, options: RequestInit = {}) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...authHeader(session), ...(options.headers as Record<string, string> | undefined) };
    const response = await fetch(`${API}${path}`, { ...options, headers });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  async function load() {
    if (!session) return;
    try {
      setItems(await api('/api/research'));
    } catch {
      setError('Nao foi possivel carregar o historico.');
    }
  }

  useEffect(() => { load(); const timer = setInterval(load, 4000); return () => clearInterval(timer); }, [session?.access_token]);
  useEffect(() => {
    if (!active || !['PENDING', 'PROCESSING'].includes(active.status)) return;
    const timer = setInterval(async () => setActive(await api(`/api/research/${active.id}`)), 2500);
    return () => clearInterval(timer);
  }, [active?.id, active?.status, session?.access_token]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const research = await api('/api/research', { method: 'POST', body: JSON.stringify({ ...form, idempotency_key: crypto.randomUUID() }) });
      setCreating(false);
      setForm({ name: '', cnpj: '', website: '' });
      setActive(await api(`/api/research/${research.id}`));
      await load();
    } catch {
      setError('Nao foi possivel criar a pesquisa.');
    } finally {
      setLoading(false);
    }
  }

  async function cancel(id: string) {
    await api(`/api/research/${id}/cancel`, { method: 'POST' });
    setActive(await api(`/api/research/${id}`));
    await load();
  }

  async function logout() {
    await supabase?.auth.signOut();
    setSession(null);
  }

  if (!session) return <Login onSession={setSession} />;

  if (active) return <main><Header session={session} onLogout={logout} /><button className="back" onClick={() => setActive(null)}>Voltar as pesquisas</button><section className="hero"><div><p className="eyebrow">Dossie empresarial</p><h1>{active.company.name}</h1><p>{active.company.cnpj || 'CNPJ nao informado'} {active.company.website && <> · <a href={active.company.website} target="_blank" rel="noopener noreferrer">site <ExternalLink size={12} /></a></>}</p></div><span className={`state ${active.status.toLowerCase()}`}>{active.status}</span></section><ProgressList progress={active.progress || []} usage={active.usage} />{['PENDING', 'PROCESSING'].includes(active.status) && <div className="processing"><div className="spinner" /><h2>Pesquisa em andamento</h2><p>O progresso vem do backend e permanece salvo ao atualizar a pagina.</p><button className="secondary" onClick={() => cancel(active.id)}><XCircle size={16} /> Cancelar</button></div>}{active.status === 'FAILED' && <div className="processing"><h2>Nao foi possivel concluir</h2><p>{active.error_public}</p></div>}{active.sections && active.sections.length > 0 && <div className="sections">{active.sections.map(section => <section className="section" key={section.key}><button className="sectionHead" onClick={() => setOpen({ ...open, [section.key]: !open[section.key] })}><div><p>{section.results.length} itens analisados</p><h2>{section.title}</h2></div>{open[section.key] === false ? <ChevronDown /> : <ChevronUp />}</button>{open[section.key] !== false && <div>{section.results.map(result => <article className="result" key={result.question_key}><div className="resultTop"><h3>{result.question}</h3><Badge status={result.status} /></div><p className="answer">{result.answer}</p><p className="summary">{result.summary}</p>{result.evidences?.length > 0 && <div className="evidence"><strong>Evidencias ({result.evidences.length})</strong>{result.evidences.map(evidence => <a key={evidence.id} href={evidence.source?.url || '#'} target="_blank" rel="noopener noreferrer"><span>{evidence.source?.title || evidence.source?.domain || evidence.source?.url}</span><small>{evidence.excerpt}</small><ExternalLink size={14} /></a>)}</div>}{result.status === 'REQUIRES_HUMAN_REVIEW' && <p className="legal">Este item exige validacao humana. A existencia de registro nao comprova culpa, irregularidade ou condenacao.</p>}</article>)}</div>}</section>)}</div>}</main>;

  return <main><Header session={session} onLogout={logout} /><section className="hero"><div><p className="eyebrow">Inteligencia para parcerias</p><h1>Pesquisa de empresas</h1><p>Centralize informacoes publicas, evidencias e fontes para apoiar a analise de potenciais parceiros.</p></div><button className="primary" onClick={() => setCreating(true)}><Plus size={18} /> Nova pesquisa</button></section>{error && <p className="error">{error}</p>}{creating && <div className="modal"><form onSubmit={submit}><div className="modalTop"><div><p className="eyebrow">Nova pesquisa</p><h2>Qual empresa vamos pesquisar?</h2></div><button type="button" className="close" onClick={() => setCreating(false)}>x</button></div><label>Nome da empresa *<input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Ex.: Empresa S.A." /></label><label>CNPJ <input value={form.cnpj} onChange={e => setForm({ ...form, cnpj: e.target.value })} placeholder="00.000.000/0001-00" /></label><label>Site <input value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} placeholder="https://..." /></label><button className="primary full" disabled={loading}>{loading ? 'Criando...' : <><Search size={17} /> Iniciar pesquisa</>}</button></form></div>}<section className="list"><div className="listTitle"><div><p className="eyebrow">Historico</p><h2>Pesquisas recentes</h2></div><span>{items.length} pesquisas</span></div>{items.length === 0 ? <div className="empty"><Database /><h3>Nenhuma pesquisa ainda</h3><p>Crie a primeira pesquisa para montar o dossie de uma empresa.</p></div> : items.map(item => <button className="card" key={item.id} onClick={async () => setActive(await api(`/api/research/${item.id}`))}><div className="companyIcon"><Building2 /></div><div className="company"><strong>{item.company.name}</strong><span>{item.company.cnpj || 'CNPJ nao informado'}</span></div><span className={`state ${item.status.toLowerCase()}`}>{item.status}</span><span className="arrow">→</span></button>)}</section></main>;
}

function ProgressList({ progress, usage }: { progress: Progress[]; usage?: Usage }) {
  return <section className="progressGrid">{progress.map(item => <div className="progressItem" key={item.key}><span className={`dot ${item.status.toLowerCase()}`} /><strong>{item.title}</strong><small>{item.status} · {item.completed_items}/{item.total_items}</small></div>)}{usage && <div className="progressItem usage"><strong>Consumo</strong><small>Brave {usage.brave_searches} · URLs {usage.urls_selected} · Firecrawl {usage.firecrawl_calls} · OpenAI {usage.openai_calls}</small></div>}</section>;
}

function Header({ session, onLogout }: { session: Session | null; onLogout: () => void }) {
  return <header><div className="brand"><div className="mark">CC</div><div><strong>Casa do Caminho</strong><span>Pesquisa de Parcerias</span></div></div><div className="headerActions"><span className="secure">Fontes publicas · Evidencias rastreaveis</span>{session && <button className="logout" onClick={onLogout}><LogOut size={16} /> Sair</button>}</div></header>;
}

createRoot(document.getElementById('root')!).render(<App />);
