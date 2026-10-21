-- Supabase 대시보드 → SQL Editor 에 통째로 붙여넣고 Run 하세요. (한 번만, 다시 실행해도 안전)

-- ───────────── 프로필 ─────────────
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 20),
  birth_year int not null check (birth_year between 1940 and 2015),
  gender text not null check (gender in ('M', 'F')),
  looking_for text not null check (looking_for in ('M', 'F', 'ALL')),
  region text not null check (char_length(region) <= 10),
  interests text[] not null default '{}' check (cardinality(interests) <= 5),
  bio text not null default '' check (char_length(bio) <= 300),
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
drop policy if exists "signed-in users read profiles" on public.profiles;
create policy "signed-in users read profiles" on public.profiles
  for select to authenticated using (true);
drop policy if exists "insert own profile" on public.profiles;
create policy "insert own profile" on public.profiles
  for insert to authenticated with check (id = auth.uid());
drop policy if exists "update own profile" on public.profiles;
create policy "update own profile" on public.profiles
  for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- ───────────── 좋아요 / 넘기기 ─────────────
-- 브라우저는 swipe() 함수로만 기록. 내가 남긴 기록만 볼 수 있음 (누가 나를 좋아했는지는 비공개)
create table if not exists public.likes (
  from_id uuid not null references public.profiles (id) on delete cascade,
  to_id uuid not null references public.profiles (id) on delete cascade,
  liked boolean not null,
  created_at timestamptz not null default now(),
  primary key (from_id, to_id)
);

alter table public.likes enable row level security;
drop policy if exists "read own swipes" on public.likes;
create policy "read own swipes" on public.likes
  for select to authenticated using (from_id = auth.uid());

-- ───────────── 매칭 (서로 좋아요) ─────────────
create table if not exists public.matches (
  id bigint generated always as identity primary key,
  user_a uuid not null references public.profiles (id) on delete cascade,
  user_b uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  check (user_a < user_b),
  unique (user_a, user_b)
);

alter table public.matches enable row level security;
drop policy if exists "members read match" on public.matches;
create policy "members read match" on public.matches
  for select to authenticated using (auth.uid() in (user_a, user_b));

-- ───────────── 채팅 메시지 ─────────────
create table if not exists public.messages (
  id bigint generated always as identity primary key,
  match_id bigint not null references public.matches (id) on delete cascade,
  sender_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  body text not null check (char_length(body) between 1 and 1000),
  created_at timestamptz not null default now()
);
create index if not exists messages_match_idx on public.messages (match_id, id);

alter table public.messages enable row level security;
drop policy if exists "members read messages" on public.messages;
create policy "members read messages" on public.messages
  for select to authenticated using (
    exists (select 1 from public.matches m
            where m.id = match_id and auth.uid() in (m.user_a, m.user_b))
  );
drop policy if exists "members send messages" on public.messages;
create policy "members send messages" on public.messages
  for insert to authenticated with check (
    sender_id = auth.uid()
    and exists (select 1 from public.matches m
                where m.id = match_id and auth.uid() in (m.user_a, m.user_b))
  );

-- ───────────── 함수 ─────────────

-- 스와이프 기록. 서로 좋아요면 매칭을 만들고 match id를 돌려줌 (아니면 null)
create or replace function public.swipe(target uuid, is_like boolean)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  me uuid := auth.uid();
  mid bigint;
begin
  if me is null then raise exception 'not signed in'; end if;
  if target = me then raise exception 'cannot swipe yourself'; end if;

  insert into likes (from_id, to_id, liked) values (me, target, is_like)
  on conflict (from_id, to_id) do update set liked = excluded.liked, created_at = now();

  if is_like and exists (
    select 1 from likes l where l.from_id = target and l.to_id = me and l.liked
  ) then
    insert into matches (user_a, user_b) values (least(me, target), greatest(me, target))
    on conflict (user_a, user_b) do update set user_a = excluded.user_a
    returning id into mid;
  end if;

  return mid;
end;
$$;
revoke execute on function public.swipe(uuid, boolean) from public, anon;
grant execute on function public.swipe(uuid, boolean) to authenticated;

-- 아직 안 본 상대 중 서로 성별 조건이 맞고 필터를 통과하는 사람 (무작위 30명)
create or replace function public.get_candidates(
  min_age int default 19,
  max_age int default 99,
  f_region text default null,
  f_interest text default null
)
returns setof public.profiles
language sql
stable
set search_path = public
as $$
  select p.*
  from profiles p
  join profiles me on me.id = auth.uid()
  where p.id <> me.id
    and (me.looking_for = 'ALL' or p.gender = me.looking_for)
    and (p.looking_for = 'ALL' or p.looking_for = me.gender)
    and extract(year from now())::int - p.birth_year between min_age and max_age
    and (f_region is null or p.region = f_region)
    and (f_interest is null or f_interest = any (p.interests))
    and not exists (select 1 from likes l where l.from_id = me.id and l.to_id = p.id)
  order by random()
  limit 30;
$$;
grant execute on function public.get_candidates(int, int, text, text) to authenticated;

-- 내 매칭 목록 + 상대 프로필 + 마지막 메시지 (최근 대화 순)
create or replace function public.my_matches()
returns table (
  match_id bigint,
  matched_at timestamptz,
  other_id uuid,
  other_name text,
  other_birth_year int,
  other_gender text,
  other_region text,
  other_interests text[],
  other_bio text,
  last_body text,
  last_at timestamptz
)
language sql
stable
set search_path = public
as $$
  select m.id, m.created_at,
         p.id, p.name, p.birth_year, p.gender, p.region, p.interests, p.bio,
         lm.body, lm.created_at
  from matches m
  join profiles p on p.id = case when m.user_a = auth.uid() then m.user_b else m.user_a end
  left join lateral (
    select x.body, x.created_at from messages x where x.match_id = m.id order by x.id desc limit 1
  ) lm on true
  where auth.uid() in (m.user_a, m.user_b)
  order by coalesce(lm.created_at, m.created_at) desc;
$$;
grant execute on function public.my_matches() to authenticated;

-- ───────────── 실시간(채팅/매칭 알림) ─────────────
do $$ begin
  alter publication supabase_realtime add table public.messages;
exception when duplicate_object then null; end $$;
do $$ begin
  alter publication supabase_realtime add table public.matches;
exception when duplicate_object then null; end $$;
