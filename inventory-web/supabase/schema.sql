-- 올투게더나우 재고관리 — 데이터베이스(Supabase) 표 만들기
-- Supabase 화면 왼쪽 'SQL Editor'에 이 파일 내용을 통째로 붙여넣고 [Run]을 한 번 누르면 됩니다.
-- 지금 구글 시트의 탭 하나 = 여기 표(table) 하나입니다.

-- 1) 들어올 수 있는 사람 (대표님·직원 이메일). owner = 모든 권한, staff = 기록 가능, viewer = 보기만
create table if not exists allowed_users (
  email text primary key,
  role  text not null default 'staff' check (role in ('owner', 'staff', 'viewer')),
  added_at timestamptz not null default now()
);

-- 2) 상품(SKU)  ← 시트 'SKU' 탭
create table if not exists skus (
  code       text primary key check (code ~ '^[A-Z0-9][A-Z0-9_.-]{0,39}$'),
  name       text not null,
  part       text not null default '',
  option     text not null default '',
  safety     integer not null default 100,
  lead       integer not null default 50,
  active     boolean not null default true,
  retail     numeric not null default 0,
  wholesale  numeric not null default 0,
  cost       numeric not null default 0,      -- 화면에서는 숨김 (보관만)
  cost_usd   numeric not null default 0,
  updated_at timestamptz not null default now()
);

-- 3) 거래처  ← '거래처' 탭
create table if not exists partners (
  name  text primary key,
  basis text not null default '직접입력',
  memo  text not null default '',
  updated_at timestamptz not null default now()
);

-- 4) 입출고 기록  ← '기록' 탭 (재고 숫자는 모두 이 기록을 더해서 계산)
create table if not exists moves (
  id          text primary key default substr(md5(random()::text || clock_timestamp()::text), 1, 13),
  date        date not null,
  type        text not null,          -- inbound, order, ship, nsale, rocket, b2b, return, loss, adjust, fassto_out, fassto_in
  loc         text not null,          -- hq(본사창고), fassto(파스토), pending(입고예정)
  sku         text not null,
  qty         numeric not null,
  memo        text not null default '',
  batch       text not null default '',
  batch_label text not null default '',
  partner     text not null default '',
  price       numeric not null default 0,
  usd         numeric not null default 0,
  fx          numeric not null default 0,
  at          timestamptz not null default now(),
  by          text not null default ''
);
create index if not exists moves_sku_idx on moves (sku);
create index if not exists moves_date_idx on moves (date);
create index if not exists moves_batch_idx on moves (batch);

-- 5) 주문서 연결표 · 매칭 규칙  ← '연결표', '매칭규칙' 탭
create table if not exists maps (
  id   text primary key,
  key  text not null,
  sku  text not null,
  mult numeric not null default 1,
  updated_at timestamptz not null default now()
);
create table if not exists rules (
  id   text primary key,
  name text not null default '',
  opt  text not null default '',
  sku  text not null,
  mult numeric not null default 1,
  memo text not null default '',
  updated_at timestamptz not null default now()
);

-- 6) 상품 사진 (같은 상품 묶음마다 한 장)  ← '상품사진' 탭
create table if not exists photos (
  key  text primary key,
  name text not null default '',
  data text not null,
  updated_at timestamptz not null default now()
);

-- 7) 설정 (공급자 정보, 네이버 시트 주소, 자동 출고 기록 등)  ← '설정' 탭
create table if not exists conf (
  key   text primary key,
  value text not null default '',
  updated_at timestamptz not null default now()
);

-- 8) 견적서  ← '견적서' 탭
create table if not exists quotes (
  no      text primary key,
  date    date,
  to_name text not null default '',
  total   numeric not null default 0,
  supply  numeric not null default 0,
  vat     numeric not null default 0,
  body    jsonb not null default '{}'::jsonb,
  by      text not null default '',
  at      timestamptz not null default now()
);

-- 9) 이미 재고에서 뺀 주문 (두 번 빠지지 않게)  ← '처리주문' 탭
create table if not exists orders_done (
  order_key text primary key,
  day       date,
  file      text not null default '',
  at        timestamptz not null default now()
);
create index if not exists orders_done_day_idx on orders_done (day);

-- 10) 올린 엑셀 파일 기록  ← '업로드' 탭
create table if not exists uploads (
  sig   text primary key,
  file  text not null default '',
  units numeric not null default 0,
  at    timestamptz not null default now(),
  by    text not null default ''
);

-- 11) 홈 메모 (한 줄짜리)
create table if not exists memo (
  id   integer primary key default 1 check (id = 1),
  text text not null default '',
  at   timestamptz not null default now(),
  by   text not null default ''
);
insert into memo (id) values (1) on conflict do nothing;

-- ===== 권한: allowed_users 에 있는 이메일만 들어올 수 있음 =====
create or replace function my_role() returns text
language sql stable security definer set search_path = public as $$
  select role from allowed_users where lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''));
$$;

do $$
declare t text;
begin
  foreach t in array array['skus','partners','moves','maps','rules','photos','conf','quotes','orders_done','uploads','memo'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists read_%1$s on %1$I', t);
    execute format('drop policy if exists write_%1$s on %1$I', t);
    execute format('create policy read_%1$s on %1$I for select using (my_role() is not null)', t);
    execute format('create policy write_%1$s on %1$I for all using (my_role() in (''owner'',''staff'')) with check (my_role() in (''owner'',''staff''))', t);
  end loop;
end $$;
alter table allowed_users enable row level security;
drop policy if exists read_allowed on allowed_users;
create policy read_allowed on allowed_users for select using (my_role() = 'owner' or lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));

-- ===== 상품 코드 바꾸기: 기록·연결표·규칙의 코드도 한 번에 (중간에 실패하면 전부 취소) =====
create or replace function rename_sku(old_code text, new_code text) returns void
language plpgsql as $$
begin
  if my_role() not in ('owner', 'staff') then raise exception '권한이 없습니다'; end if;
  if exists (select 1 from skus where code = new_code) then raise exception '% 코드는 이미 다른 상품이 쓰고 있습니다', new_code; end if;
  update skus  set code = new_code, updated_at = now() where code = old_code;
  update moves set sku = new_code where sku = old_code;
  update maps  set sku = new_code where sku = old_code;
  update rules set sku = new_code where sku = old_code;
end $$;

-- 마지막: 대표님 이메일을 owner로 등록 (아래 이메일을 대표님 구글 계정으로 바꿔서 실행)
-- insert into allowed_users (email, role) values ('대표님이메일@gmail.com', 'owner') on conflict (email) do update set role = 'owner';
