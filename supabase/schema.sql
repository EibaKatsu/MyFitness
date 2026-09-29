-- MyFitness personal project schema
-- Supabase SQL Editor で全体を一度だけ実行してください。

create extension if not exists pgcrypto;

create table if not exists public.activities (
  id uuid primary key default gen_random_uuid(),
  garmin_activity_id bigint not null unique,
  start_time timestamptz not null,
  activity_type text not null,
  activity_type_label text not null,
  activity_name text,
  distance_m double precision check (distance_m is null or distance_m >= 0),
  duration_s double precision check (duration_s is null or duration_s >= 0),
  moving_duration_s double precision check (moving_duration_s is null or moving_duration_s >= 0),
  avg_hr integer check (avg_hr is null or avg_hr >= 0),
  max_hr integer check (max_hr is null or max_hr >= 0),
  avg_speed_mps double precision check (avg_speed_mps is null or avg_speed_mps >= 0),
  elevation_gain_m double precision,
  calories_kcal double precision check (calories_kcal is null or calories_kcal >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.weight_entries (
  id uuid primary key default gen_random_uuid(),
  recorded_at timestamptz not null,
  weight_kg numeric(6,2) not null check (weight_kg > 0 and weight_kg <= 500),
  note text check (note is null or char_length(note) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.meal_entries (
  id uuid primary key default gen_random_uuid(),
  recorded_at timestamptz not null,
  meal_type text not null check (meal_type in ('breakfast', 'lunch', 'dinner', 'snack', 'other')),
  description text not null check (char_length(description) between 1 and 5000),
  calories_kcal numeric(9,2) check (calories_kcal is null or calories_kcal >= 0),
  protein_g numeric(9,2) check (protein_g is null or protein_g >= 0),
  fat_g numeric(9,2) check (fat_g is null or fat_g >= 0),
  carbs_g numeric(9,2) check (carbs_g is null or carbs_g >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.sync_history (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  range_start date not null,
  range_end date not null,
  status text not null check (status in ('running', 'success', 'failed')),
  fetched_count integer not null default 0 check (fetched_count >= 0),
  added_count integer not null default 0 check (added_count >= 0),
  updated_count integer not null default 0 check (updated_count >= 0),
  skipped_count integer not null default 0 check (skipped_count >= 0),
  error_message text check (error_message is null or char_length(error_message) <= 1000),
  check (range_start <= range_end)
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists activities_set_updated_at on public.activities;
create trigger activities_set_updated_at before update on public.activities
for each row execute function public.set_updated_at();

drop trigger if exists weight_entries_set_updated_at on public.weight_entries;
create trigger weight_entries_set_updated_at before update on public.weight_entries
for each row execute function public.set_updated_at();

drop trigger if exists meal_entries_set_updated_at on public.meal_entries;
create trigger meal_entries_set_updated_at before update on public.meal_entries
for each row execute function public.set_updated_at();

create index if not exists activities_start_time_idx on public.activities (start_time desc);
create index if not exists weight_entries_recorded_at_idx on public.weight_entries (recorded_at desc);
create index if not exists meal_entries_recorded_at_idx on public.meal_entries (recorded_at desc);
create index if not exists sync_history_started_at_idx on public.sync_history (started_at desc);

alter table public.activities enable row level security;
alter table public.weight_entries enable row level security;
alter table public.meal_entries enable row level security;
alter table public.sync_history enable row level security;

-- 意図的にRLSポリシーを作成しません。anon/authenticatedロールは全行拒否になります。
-- ローカルPythonサーバーだけがsecret/service_role keyでRLSを迂回して操作します。
revoke all on table public.activities from anon, authenticated;
revoke all on table public.weight_entries from anon, authenticated;
revoke all on table public.meal_entries from anon, authenticated;
revoke all on table public.sync_history from anon, authenticated;
grant all on table public.activities to service_role;
grant all on table public.weight_entries to service_role;
grant all on table public.meal_entries to service_role;
grant all on table public.sync_history to service_role;
