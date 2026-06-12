create table if not exists public.crypto_intel_items (
  item_hash text primary key,
  run_date date not null default current_date,
  title text not null,
  url text not null,
  source_name text not null,
  source_kind text not null,
  source_url text,
  published_at timestamptz,
  fetched_at timestamptz,
  relevance_score integer not null default 0,
  importance_score integer not null default 0,
  alert_score integer not null default 0,
  confidence numeric(5, 3),
  provider text not null default 'rules',
  categories text[] not null default '{}',
  projects text[] not null default '{}',
  asset_classes text[] not null default '{}',
  chains text[] not null default '{}',
  jurisdictions text[] not null default '{}',
  summary text,
  business_impact text,
  next_action text,
  reasons text[] not null default '{}',
  tags text[] not null default '{}',
  raw_summary text,
  raw_text text,
  status text not null default 'collected',
  owner text,
  notes text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  alert_sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint crypto_intel_items_status_check check (
    status in (
      'collected',
      'skipped_date',
      'skipped_rule',
      'analyzed',
      'selected',
      'sent',
      'noise',
      'archived'
    )
  )
);

alter table public.crypto_intel_items
  add column if not exists raw_text text;

alter table public.crypto_intel_items
  add column if not exists first_seen_at timestamptz not null default now();

alter table public.crypto_intel_items
  add column if not exists last_seen_at timestamptz not null default now();

alter table public.crypto_intel_items
  add column if not exists alert_sent_at timestamptz;

alter table public.crypto_intel_items
  alter column status set default 'collected';

update public.crypto_intel_items
set status = 'collected'
where status = 'inbox';

alter table public.crypto_intel_items
  drop constraint if exists crypto_intel_items_status_check;

alter table public.crypto_intel_items
  drop constraint if exists crypto_status_check;

alter table public.crypto_intel_items
  add constraint crypto_status_check check (
    status in (
      'collected',
      'skipped_date',
      'skipped_rule',
      'analyzed',
      'selected',
      'sent',
      'noise',
      'archived'
    )
  );

create index if not exists crypto_intel_items_run_date_idx
  on public.crypto_intel_items (run_date desc);

create index if not exists crypto_intel_items_alert_score_idx
  on public.crypto_intel_items (alert_score desc);

create index if not exists crypto_intel_items_source_idx
  on public.crypto_intel_items (source_name);

create index if not exists crypto_intel_items_status_idx
  on public.crypto_intel_items (status);

create index if not exists crypto_intel_items_asset_classes_idx
  on public.crypto_intel_items using gin (asset_classes);

create index if not exists crypto_intel_items_projects_idx
  on public.crypto_intel_items using gin (projects);

create or replace function public.set_crypto_intel_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_crypto_intel_items_updated_at on public.crypto_intel_items;
drop trigger if exists set_crypto_updated_at on public.crypto_intel_items;

create trigger set_crypto_intel_items_updated_at
before update on public.crypto_intel_items
for each row
execute function public.set_crypto_intel_updated_at();

create or replace view public.crypto_intel_today
with (security_invoker = true) as
select
  title as name,
  source_name as source,
  importance_score as importance,
  projects,
  asset_classes
from public.crypto_intel_items
where run_date = current_date
order by importance_score desc, confidence desc nulls last, published_at desc nulls last;

alter table public.crypto_intel_items enable row level security;

drop policy if exists "Authenticated users can read crypto intel items"
  on public.crypto_intel_items;
drop policy if exists "Authenticated users can read crypto"
  on public.crypto_intel_items;

create policy "Authenticated users can read crypto intel items"
  on public.crypto_intel_items
  for select
  to authenticated
  using (true);

grant select on table public.crypto_intel_items to authenticated;
grant select on table public.crypto_intel_today to authenticated;
grant select, insert, update, delete on table public.crypto_intel_items to service_role;
