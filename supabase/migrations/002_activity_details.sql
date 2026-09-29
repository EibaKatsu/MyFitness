-- MyFitness v0.2: running detail data, annotations, and growth analytics
-- Existing project: run this file once in Supabase SQL Editor.

alter table public.activities
  add column if not exists elapsed_duration_s double precision,
  add column if not exists max_speed_mps double precision,
  add column if not exists avg_moving_speed_mps double precision,
  add column if not exists avg_grade_adjusted_speed_mps double precision,
  add column if not exists min_hr integer,
  add column if not exists recovery_hr integer,
  add column if not exists elevation_loss_m double precision,
  add column if not exists min_elevation_m double precision,
  add column if not exists avg_elevation_m double precision,
  add column if not exists max_elevation_m double precision,
  add column if not exists avg_run_cadence_spm double precision,
  add column if not exists max_run_cadence_spm double precision,
  add column if not exists avg_power_w double precision,
  add column if not exists max_power_w double precision,
  add column if not exists normalized_power_w double precision,
  add column if not exists total_work_j double precision,
  add column if not exists steps integer,
  add column if not exists stride_length_cm double precision,
  add column if not exists vertical_oscillation_cm double precision,
  add column if not exists vertical_ratio_pct double precision,
  add column if not exists ground_contact_time_ms double precision,
  add column if not exists training_effect double precision,
  add column if not exists anaerobic_training_effect double precision,
  add column if not exists activity_training_load double precision,
  add column if not exists training_effect_label text,
  add column if not exists difference_body_battery integer,
  add column if not exists workout_rpe integer,
  add column if not exists workout_feel integer,
  add column if not exists moderate_intensity_minutes integer,
  add column if not exists vigorous_intensity_minutes integer,
  add column if not exists water_estimated_ml double precision,
  add column if not exists lap_count integer,
  add column if not exists device_manufacturer text,
  add column if not exists device_id text,
  add column if not exists aerobic_decoupling_pct double precision,
  add column if not exists details_synced_at timestamptz,
  add column if not exists detail_sync_error text;

alter table public.sync_history
  add column if not exists detail_synced_count integer not null default 0,
  add column if not exists detail_failed_count integer not null default 0;

create table if not exists public.activity_laps (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references public.activities(id) on delete cascade,
  lap_index integer not null,
  start_time timestamptz,
  distance_m double precision,
  duration_s double precision,
  moving_duration_s double precision,
  elapsed_duration_s double precision,
  avg_speed_mps double precision,
  max_speed_mps double precision,
  avg_grade_adjusted_speed_mps double precision,
  avg_hr integer,
  max_hr integer,
  avg_run_cadence_spm double precision,
  max_run_cadence_spm double precision,
  avg_power_w double precision,
  max_power_w double precision,
  normalized_power_w double precision,
  elevation_gain_m double precision,
  elevation_loss_m double precision,
  stride_length_cm double precision,
  vertical_oscillation_cm double precision,
  vertical_ratio_pct double precision,
  ground_contact_time_ms double precision,
  intensity_type text,
  unique (activity_id, lap_index)
);

create table if not exists public.activity_hr_zones (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references public.activities(id) on delete cascade,
  zone_number integer not null,
  low_boundary_bpm integer,
  seconds_in_zone double precision,
  unique (activity_id, zone_number)
);

create table if not exists public.activity_samples (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references public.activities(id) on delete cascade,
  sample_index integer not null,
  recorded_at timestamptz,
  distance_m double precision,
  duration_s double precision,
  moving_duration_s double precision,
  elapsed_duration_s double precision,
  heart_rate_bpm integer,
  speed_mps double precision,
  grade_adjusted_speed_mps double precision,
  elevation_m double precision,
  vertical_speed_mps double precision,
  cadence_spm double precision,
  power_w double precision,
  body_battery integer,
  stride_length_cm double precision,
  vertical_oscillation_cm double precision,
  vertical_ratio_pct double precision,
  ground_contact_time_ms double precision,
  performance_condition double precision,
  unique (activity_id, sample_index)
);

create table if not exists public.activity_weather (
  activity_id uuid primary key references public.activities(id) on delete cascade,
  temperature_raw double precision,
  apparent_temperature_raw double precision,
  dew_point_raw double precision,
  relative_humidity_pct double precision,
  wind_speed_raw double precision,
  wind_gust_raw double precision,
  wind_direction_deg double precision,
  wind_direction_compass text,
  weather_description text,
  station_name text,
  observed_at timestamptz
);

create table if not exists public.activity_gear (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references public.activities(id) on delete cascade,
  gear_uuid text not null,
  display_name text,
  gear_type text,
  manufacturer text,
  model text,
  unique (activity_id, gear_uuid)
);

create table if not exists public.activity_annotations (
  activity_id uuid primary key references public.activities(id) on delete cascade,
  training_category text check (
    training_category is null or training_category in (
      'easy', 'long', 'tempo', 'threshold', 'interval', 'race', 'recovery', 'other'
    )
  ),
  session_rpe integer check (session_rpe is null or session_rpe between 0 and 10),
  fatigue_score integer check (fatigue_score is null or fatigue_score between 1 and 5),
  pain_score integer check (pain_score is null or pain_score between 0 and 5),
  surface text check (
    surface is null or surface in ('road', 'track', 'trail', 'treadmill', 'mixed', 'other')
  ),
  completion_status text check (
    completion_status is null or completion_status in ('completed', 'modified', 'stopped')
  ),
  is_race boolean not null default false,
  training_goal text check (training_goal is null or char_length(training_goal) <= 1000),
  notes text check (notes is null or char_length(notes) <= 3000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists activity_annotations_set_updated_at on public.activity_annotations;
create trigger activity_annotations_set_updated_at before update on public.activity_annotations
for each row execute function public.set_updated_at();

create index if not exists activity_laps_activity_idx
  on public.activity_laps (activity_id, lap_index);
create index if not exists activity_samples_activity_idx
  on public.activity_samples (activity_id, sample_index);
create index if not exists activity_samples_recorded_at_idx
  on public.activity_samples (recorded_at);
create index if not exists activity_hr_zones_activity_idx
  on public.activity_hr_zones (activity_id, zone_number);

alter table public.activity_laps enable row level security;
alter table public.activity_hr_zones enable row level security;
alter table public.activity_samples enable row level security;
alter table public.activity_weather enable row level security;
alter table public.activity_gear enable row level security;
alter table public.activity_annotations enable row level security;

revoke all on table public.activity_laps from anon, authenticated;
revoke all on table public.activity_hr_zones from anon, authenticated;
revoke all on table public.activity_samples from anon, authenticated;
revoke all on table public.activity_weather from anon, authenticated;
revoke all on table public.activity_gear from anon, authenticated;
revoke all on table public.activity_annotations from anon, authenticated;

grant all on table public.activity_laps to service_role;
grant all on table public.activity_hr_zones to service_role;
grant all on table public.activity_samples to service_role;
grant all on table public.activity_weather to service_role;
grant all on table public.activity_gear to service_role;
grant all on table public.activity_annotations to service_role;
