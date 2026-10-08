create extension if not exists "pgcrypto";

create table if not exists companies (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  cnpj text,
  website text,
  dedupe_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_user_id, dedupe_key)
);

create table if not exists researches (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  company_id uuid not null references companies(id) on delete cascade,
  company_snapshot jsonb not null,
  status text not null default 'PENDING' check (status in ('PENDING','PROCESSING','COMPLETED','COMPLETED_WITH_WARNINGS','FAILED','CANCELLED')),
  checklist_version text not null,
  idempotency_key text,
  usage jsonb not null default '{}'::jsonb,
  error_public text,
  error_internal text,
  locked_by text,
  locked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  unique(owner_user_id, idempotency_key)
);

create table if not exists research_progress (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references researches(id) on delete cascade,
  step_key text not null,
  title text not null,
  status text not null default 'WAITING' check (status in ('WAITING','PROCESSING','COMPLETED','FAILED','SKIPPED')),
  completed_items integer not null default 0,
  total_items integer not null default 0,
  message text,
  updated_at timestamptz not null default now(),
  unique(research_id, step_key)
);

create table if not exists research_questions (
  id uuid primary key default gen_random_uuid(),
  checklist_version text not null,
  section_key text not null,
  question_key text not null,
  question text not null,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  unique(checklist_version, question_key)
);

create table if not exists research_sections (
  id uuid primary key default gen_random_uuid(),
  checklist_version text not null,
  section_key text not null,
  title text not null,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  unique(checklist_version, section_key)
);

create table if not exists search_executions (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references researches(id) on delete cascade,
  group_key text not null,
  query text not null,
  query_hash text not null,
  results jsonb not null default '[]'::jsonb,
  status text not null check (status in ('COMPLETED','FAILED')),
  error text,
  created_at timestamptz not null default now()
);

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references researches(id) on delete cascade,
  url text not null,
  normalized_url text not null,
  title text,
  domain text,
  source_type text not null default 'OTHER' check (source_type in ('OFFICIAL_GOVERNMENT','REGULATORY','OFFICIAL_COMPANY','INSTITUTIONAL','JOURNALISTIC','OTHER')),
  description text,
  accessed_at timestamptz not null default now(),
  published_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  unique(research_id, normalized_url)
);

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references researches(id) on delete cascade,
  source_id uuid not null references sources(id) on delete cascade,
  url text not null,
  normalized_url text not null,
  content text,
  content_hash text,
  metadata jsonb not null default '{}'::jsonb,
  accessed_at timestamptz not null default now()
);

create table if not exists evidences (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references researches(id) on delete cascade,
  source_id uuid not null references sources(id) on delete cascade,
  document_id uuid references documents(id) on delete set null,
  excerpt text not null,
  fingerprint text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(research_id, fingerprint)
);

create table if not exists research_results (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references researches(id) on delete cascade,
  section_key text not null,
  question_key text not null,
  question text not null,
  status text not null check (status in ('FOUND','NOT_FOUND','INCONCLUSIVE','REQUIRES_HUMAN_REVIEW')),
  answer text not null,
  summary text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(research_id, question_key)
);

create table if not exists result_evidences (
  result_id uuid not null references research_results(id) on delete cascade,
  evidence_id uuid not null references evidences(id) on delete cascade,
  primary key(result_id, evidence_id)
);

create index if not exists companies_owner_idx on companies(owner_user_id);
create index if not exists researches_owner_status_idx on researches(owner_user_id, status);
create index if not exists researches_company_idx on researches(company_id);
create index if not exists search_query_hash_idx on search_executions(query_hash, created_at);
create index if not exists sources_research_idx on sources(research_id);
create index if not exists documents_url_idx on documents(normalized_url, accessed_at);
create index if not exists evidences_research_idx on evidences(research_id);
create index if not exists results_research_idx on research_results(research_id);

alter table companies enable row level security;
alter table researches enable row level security;
alter table research_progress enable row level security;
alter table research_questions enable row level security;
alter table research_sections enable row level security;
alter table search_executions enable row level security;
alter table sources enable row level security;
alter table documents enable row level security;
alter table evidences enable row level security;
alter table research_results enable row level security;
alter table result_evidences enable row level security;

create policy "companies_owner_select" on companies for select using (auth.uid() = owner_user_id);
create policy "researches_owner_select" on researches for select using (auth.uid() = owner_user_id);
create policy "progress_owner_select" on research_progress for select using (exists (select 1 from researches r where r.id = research_id and r.owner_user_id = auth.uid()));
create policy "questions_authenticated_select" on research_questions for select using (auth.role() = 'authenticated');
create policy "sections_authenticated_select" on research_sections for select using (auth.role() = 'authenticated');
create policy "search_owner_select" on search_executions for select using (exists (select 1 from researches r where r.id = research_id and r.owner_user_id = auth.uid()));
create policy "sources_owner_select" on sources for select using (exists (select 1 from researches r where r.id = research_id and r.owner_user_id = auth.uid()));
create policy "documents_owner_select" on documents for select using (exists (select 1 from researches r where r.id = research_id and r.owner_user_id = auth.uid()));
create policy "evidences_owner_select" on evidences for select using (exists (select 1 from researches r where r.id = research_id and r.owner_user_id = auth.uid()));
create policy "results_owner_select" on research_results for select using (exists (select 1 from researches r where r.id = research_id and r.owner_user_id = auth.uid()));
create policy "result_evidences_owner_select" on result_evidences for select using (
  exists (
    select 1
    from research_results rr
    join researches r on r.id = rr.research_id
    where rr.id = result_id and r.owner_user_id = auth.uid()
  )
);
