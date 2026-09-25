<script>
  import { onDestroy } from 'svelte'

  let username = 'processor'
  let password = 'herb123456'
  let token = localStorage.getItem('herb_token') || ''
  let role = localStorage.getItem('herb_role') || ''
  let rows = []
  let herb = '白芍'
  let tempC = 110
  let minutes = 10
  let error = ''

  let view = 'records'
  let curfew = null
  let events = []
  let editStart = '22:00'
  let editEnd = '06:00'
  let curfewMsg = ''
  let curfewOk = ''
  let timer = null

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || '请求失败')
    return data
  }

  async function enter() {
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    token = data.access_token
    role = data.role
    localStorage.setItem('herb_token', token)
    localStorage.setItem('herb_role', role)
    await load()
  }

  async function load() {
    rows = await api('/api/batches')
  }

  async function loadCurfew() {
    curfew = await api('/api/curfew')
    events = await api('/api/curfew/events')
  }

  function show(next) {
    view = next
    curfewMsg = ''
    curfewOk = ''
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    if (next === 'curfew') {
      loadCurfew()
        .then(() => {
          editStart = curfew.start
          editEnd = curfew.end
        })
        .catch(() => {})
      timer = setInterval(() => loadCurfew().catch(() => {}), 15000)
    }
  }

  async function saveCurfew() {
    curfewMsg = ''
    curfewOk = ''
    try {
      curfew = await api('/api/curfew', {
        method: 'PUT',
        body: JSON.stringify({ start: editStart, end: editEnd }),
      })
      curfewOk = '禁写时段已保存，立即生效'
      await loadCurfew()
    } catch (err) {
      curfewMsg = err.message
    }
  }

  async function save() {
    error = ''
    try {
      await api('/api/batches', {
        method: 'POST',
        body: JSON.stringify({
          herb,
          steps: [{ name: '清炒', temp_c: Number(tempC), minutes: Number(minutes) }],
        }),
      })
      await load()
    } catch (err) {
      error = err.message
    }
  }

  function leave() {
    if (timer) clearInterval(timer)
    localStorage.clear()
    token = ''
    role = ''
  }

  function fmtTs(s) {
    return new Date(s).toLocaleString('zh-CN', { hour12: false })
  }

  onDestroy(() => {
    if (timer) clearInterval(timer)
  })

  if (token) load()
</script>

{#if !token}
  <main>
    <h1>饮片炮制记录台</h1>
    <p>炮制记录整包保存。清炒温度须在 80 到 150，时长须在 5 到 30 分钟。每日夜间禁写窗内禁止开炒写入。</p>
    <input bind:value={username} />
    <input type="password" bind:value={password} />
    <button on:click={enter}>登录</button>
    <p>processor / herb123456 可写；checker / check123456 只读</p>
  </main>
{:else}
  <header class="topbar">
    <span class="brand">饮片炮制记录台</span>
    <nav>
      <a href="/" class:on={view === 'records'} on:click|preventDefault={() => show('records')}>炮制记录</a>
      <a href="/curfew" class:on={view === 'curfew'} on:click|preventDefault={() => show('curfew')}>夜间禁写</a>
    </nav>
    <span class="who">{username} · {role === 'writer' ? '炮制员' : '质检员'} <button on:click={leave}>退出</button></span>
  </header>

  <main>
    {#if view === 'records'}
      <h1>炮制记录</h1>
      {#if role === 'writer'}
        <input bind:value={herb} placeholder="饮片" />
        <input type="number" bind:value={tempC} />
        <input type="number" bind:value={minutes} />
        <button on:click={save}>写入清炒记录</button>
        {#if error}
          <p class="err">{error}</p>
          {#if error.includes('禁写窗')}
            <p><a href="/curfew" on:click|preventDefault={() => show('curfew')}>前往「夜间禁写」查看时段与流水 →</a></p>
          {/if}
        {/if}
      {/if}
      <ul>
        {#each rows as row}
          <li>{row.herb} · {row.verdict} · {row.reason} · 温度 {row.doc.steps[0].temp_c}</li>
        {/each}
      </ul>
    {:else}
      <h1>夜间禁写窗</h1>
      {#if curfew}
        <section class="card">
          <h2>禁写时间段</h2>
          <p class="big">{curfew.start} ~ {curfew.end}{#if curfew.overnight}（跨夜）{/if}</p>
          <p>每日闭区间内禁止开炒写入 · 最近由 {curfew.updated_by} 调整于 {fmtTs(curfew.updated_at)}</p>
          {#if role === 'writer'}
            <label>起 <input type="time" bind:value={editStart} /></label>
            <label>止 <input type="time" bind:value={editEnd} /></label>
            <button on:click={saveCurfew}>保存时间段</button>
          {:else}
            <p class="muted">质检员仅可查看，不可调整禁写时段。</p>
          {/if}
          {#if curfewMsg}<p class="err">{curfewMsg}</p>{/if}
          {#if curfewOk}<p class="ok">{curfewOk}</p>{/if}
        </section>

        <section class="card">
          <h2>当前状态</h2>
          <p>服务器时间 {curfew.server_time}（{curfew.tz}）</p>
          {#if curfew.in_window}
            <p class="badge bad">禁写中 · 当前处于禁写窗，开炒写入将被拒绝</p>
          {:else}
            <p class="badge good">可写入 · 当前不在禁写窗内</p>
          {/if}
          <button on:click={loadCurfew}>刷新状态</button>
        </section>

        <section class="card">
          <h2>禁写流水</h2>
          {#if events.length === 0}
            <p class="muted">暂无禁写记录</p>
          {:else}
            <ul>
              {#each events as ev}
                <li>{fmtTs(ev.attempted_at)} · {ev.attempted_by} 试写「{ev.herb}」被拦 · 命中禁写窗 {ev.window_start}~{ev.window_end}</li>
              {/each}
            </ul>
          {/if}
        </section>
      {/if}
    {/if}
  </main>
{/if}

<style>
  main { font-family: sans-serif; max-width: 720px; margin: 24px auto; color: #3f2f1f; }
  h1 { color: #7c2d12; }
  h2 { color: #7c2d12; font-size: 18px; margin: 0 0 8px; }
  input { margin-right: 8px; padding: 6px; }
  .topbar {
    font-family: sans-serif;
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 10px 20px;
    background: #7c2d12;
    color: #fff7ed;
  }
  .topbar .brand { font-weight: bold; }
  .topbar nav { display: flex; gap: 16px; flex: 1; }
  .topbar a { color: #fed7aa; text-decoration: none; }
  .topbar a.on { color: #ffffff; font-weight: bold; border-bottom: 2px solid #ffffff; }
  .topbar .who { font-size: 13px; }
  .card { border: 1px solid #e7d8c9; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fffaf3; }
  .big { font-size: 22px; font-weight: bold; margin: 4px 0; }
  .muted { color: #8a7360; }
  .err { color: #b91c1c; }
  .ok { color: #15803d; }
  .badge { display: inline-block; padding: 6px 12px; border-radius: 6px; font-weight: bold; }
  .badge.bad { background: #fee2e2; color: #b91c1c; }
  .badge.good { background: #dcfce7; color: #15803d; }
</style>
