create extension if not exists pgcrypto;

create table if not exists public.proyecto_d_inbound_messages (
  id uuid primary key default gen_random_uuid(),
  project_key text not null default 'proyecto_d',
  source_channel text not null default 'whatsapp',
  sender text not null,
  message_id text not null unique,
  raw_body text not null,
  normalized_body text,
  has_trigger_emoji boolean not null default false,
  visible_output text not null default 'NO_REPLY',
  project_guess text,
  result_status text,
  clickup_action text,
  clickup_task_id text,
  clickup_task_name text,
  clickup_target_status text,
  result_payload jsonb,
  error_text text,
  received_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists proyecto_d_inbound_messages_sender_received_idx
  on public.proyecto_d_inbound_messages (sender, received_at desc);
create index if not exists proyecto_d_inbound_messages_result_status_idx
  on public.proyecto_d_inbound_messages (result_status);

create table if not exists public.proyecto_d_clickup_sync_events (
  id bigint generated always as identity primary key,
  message_id text not null references public.proyecto_d_inbound_messages(message_id) on delete cascade,
  event_type text not null,
  clickup_task_id text,
  clickup_task_name text,
  clickup_status text,
  payload jsonb,
  created_at timestamptz not null default now()
);

create index if not exists proyecto_d_clickup_sync_events_message_idx
  on public.proyecto_d_clickup_sync_events (message_id, created_at desc);

create table if not exists public.proyecto_d_processing_errors (
  id bigint generated always as identity primary key,
  message_id text,
  sender text,
  stage text not null,
  error_text text not null,
  payload jsonb,
  created_at timestamptz not null default now()
);

alter table public.proyecto_d_inbound_messages enable row level security;
alter table public.proyecto_d_clickup_sync_events enable row level security;
alter table public.proyecto_d_processing_errors enable row level security;
