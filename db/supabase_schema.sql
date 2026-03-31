-- Giridaga Marketer: GSheets -> Supabase(Postgres) migration schema
-- Run this in Supabase SQL editor first.

create extension if not exists "uuid-ossp";

-- 1) Marketing prompts (from worksheet: prompt/prompts)
create table if not exists prompts (
  category text primary key,
  prompt text not null default '',
  updated_at timestamptz not null default now()
);

-- 2) Marketing history (from worksheet: history)
create table if not exists marketing_history (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  date_text text not null default '',
  category text not null default '',
  instagram text not null default '',
  blog text not null default '',
  image_link text not null default ''
);

create index if not exists marketing_history_category_idx on marketing_history (category);

-- 3) Students (from worksheet: students)
create table if not exists students (
  student_id text primary key,
  name text not null default '',
  phone text not null default '',
  registered_date text not null default '',
  course text not null default '',
  total_sessions int not null default 0,
  remaining_sessions int not null default 0,
  status text not null default '',
  memo text not null default '',
  updated_at timestamptz not null default now()
);

-- 4) Attendance requests/log (worksheets: attendance_requests, attendance_log)
create table if not exists attendance_requests (
  request_id text primary key,
  time_text text not null default '',
  student_id text not null default '',
  student_name text not null default '',
  status text not null default '',
  approved_time text not null default '',
  updated_at timestamptz not null default now()
);

create index if not exists attendance_requests_status_idx on attendance_requests (status);
create index if not exists attendance_requests_student_idx on attendance_requests (student_id);

create table if not exists attendance_log (
  id bigserial primary key,
  time_text text not null default '',
  student_id text not null default '',
  student_name text not null default '',
  remain_count int not null default 0,
  event text not null default ''
);

create index if not exists attendance_log_student_idx on attendance_log (student_id);

-- 5) Schedule (worksheet: student_schedule)
create table if not exists student_schedule (
  id text primary key,
  student_id text not null default '',
  student_name text not null default '',
  weekday text not null default '',
  time_slot text not null default '',
  start_date text not null default '',
  end_date text not null default '',
  memo text not null default '',
  created_at text not null default ''
);

create index if not exists student_schedule_student_idx on student_schedule (student_id);

-- 6) Curriculum (worksheet: curriculum)
create table if not exists curriculum (
  course_id text primary key,
  course_name text not null default '',
  sessions int not null default 0,
  amount int not null default 0,
  description text not null default '',
  created_at text not null default '',
  sort_order int not null default 9999
);

-- 7) Finance (worksheets: finance_transactions, finance_expenses)
create table if not exists finance_transactions (
  tx_id text primary key,
  date text not null default '',
  year_month text not null default '',
  year_week text not null default '',
  student_id text not null default '',
  student_name text not null default '',
  course text not null default '',
  event_type text not null default '',
  amount int not null default 0,
  base_amount int not null default 0,
  discount_type text not null default '',
  discount_value int not null default 0,
  discount_amount int not null default 0,
  event_name text not null default '',
  note text not null default ''
);

create index if not exists finance_tx_year_month_idx on finance_transactions (year_month);
create index if not exists finance_tx_student_idx on finance_transactions (student_id);

create table if not exists finance_expenses (
  ex_id text primary key,
  date text not null default '',
  year_month text not null default '',
  category text not null default '',
  item text not null default '',
  amount int not null default 0,
  note text not null default ''
);

create index if not exists finance_expenses_year_month_idx on finance_expenses (year_month);

