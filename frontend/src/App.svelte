<script>
  let username = localStorage.getItem('herb_username') || 'processor'
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
  let curfewHits = []
  let curfewStart = ''
  let curfewEnd = ''
  let curfewMsg = ''
  let curfewError = ''
  let curfewTimer = null

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
    localStorage.setItem('herb_username', username)
    await load()
  }

  async function load() {
    rows = await api('/api/batches')
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

  function show(next) {
    view = next
    error = ''
    if (next === 'curfew') {
      loadCurfew(true)
      startCurfewTimer()
    } else {
      stopCurfewTimer()
    }
  }

  function startCurfewTimer() {
    stopCurfewTimer()
    curfewTimer = setInterval(() => {
      if (token && view === 'curfew') loadCurfew(false)
    }, 10000)
  }

  function stopCurfewTimer() {
    if (curfewTimer) {
      clearInterval(curfewTimer)
      curfewTimer = null
    }
  }

  async function loadCurfew(syncInputs = false) {
    curfewError = ''
    try {
      const state = await api('/api/curfew')
      curfew = state
      if (syncInputs) {
        curfewStart = state.start
        curfewEnd = state.end
      }
      curfewHits = await api('/api/curfew/hits')
    } catch (err) {
      curfewError = err.message
    }
  }

  async function saveCurfew() {
    curfewMsg = ''
    curfewError = ''
    try {
      curfew = await api('/api/curfew', {
        method: 'PUT',
        body: JSON.stringify({ start: curfewStart, end: curfewEnd }),
      })
      curfewMsg = '已保存，禁写窗立即生效'
      curfewHits = await api('/api/curfew/hits')
    } catch (err) {
      curfewError = err.message
    }
  }

  function leave() {
    stopCurfewTimer()
    localStorage.clear()
    token = ''
    role = ''
  }

  const fmtTs = (iso) => (iso || '').replace('T', ' ').slice(0, 19)

  if (token) load()
</script>

<main>
  {#if !token}
    <h1>饮片炮制记录台</h1>
    <p>炮制记录整包保存。清炒温度须在 80 到 150，时长须在 5 到 30 分钟。夜间禁写窗内禁止开炒写入。</p>
    <input bind:value={username} />
    <input type="password" bind:value={password} />
    <button on:click={enter}>登录</button>
    <p>processor / herb123456 可写；checker / check123456 只读</p>
  {:else}
    <nav>
      <strong>饮片炮制记录台</strong>
      <a href="/" class:active={view === 'records'} on:click|preventDefault={() => show('records')}>炮制记录</a>
      <a href="/curfew" class:active={view === 'curfew'} on:click|preventDefault={() => show('curfew')}>夜间禁写</a>
      <span class="fill"></span>
      <span class="who">{username} · {role === 'writer' ? '炮制员' : '质检员'}</span>
      <button on:click={leave}>退出</button>
    </nav>

    {#if view === 'records'}
      <h1>炮制记录</h1>
      {#if role === 'writer'}
        <input bind:value={herb} placeholder="饮片" />
        <input type="number" bind:value={tempC} />
        <input type="number" bind:value={minutes} />
        <button on:click={save}>写入清炒记录</button>
        {#if error}<p class="err">{error}</p>{/if}
      {/if}
      <ul>
        {#each rows as row}
          <li>{row.herb} · {row.verdict} · {row.reason} · 温度 {row.doc.steps[0].temp_c}</li>
        {/each}
      </ul>
    {:else}
      <h1>夜间禁写窗</h1>

      <section class="card">
        <h2>当前状态</h2>
        {#if curfew}
          <p>服务器时间：{curfew.server_time}</p>
          {#if curfew.in_curfew}
            <p class="badge ban">禁写中 · 当前时刻落在禁写窗内，开炒写入一律拒绝</p>
          {:else}
            <p class="badge ok">可写入 · 当前时刻在禁写窗外</p>
          {/if}
        {:else}
          <p>状态加载中…</p>
        {/if}
        <button on:click={() => loadCurfew(false)}>刷新状态</button>
        {#if curfewError}<p class="err">{curfewError}</p>{/if}
      </section>

      <section class="card">
        <h2>禁写时间段（每日，闭区间）</h2>
        {#if curfew}
          {#if role === 'writer'}
            <p>
              <input type="time" bind:value={curfewStart} />
              至
              <input type="time" bind:value={curfewEnd} />
              <button on:click={saveCurfew}>保存并立即生效</button>
            </p>
            <p class="hint">开始晚于结束表示跨零点，如 22:00 至次日 06:00。当前配置：{curfew.start} 至 {curfew.end}（{curfew.updated_by} 更新）</p>
          {:else}
            <p>当前禁写窗：{curfew.start} 至 {curfew.end}（由 {curfew.updated_by} 更新）</p>
            <p class="hint">质检员仅可查看，不可修改配置。</p>
          {/if}
          {#if curfewMsg}<p class="oktext">{curfewMsg}</p>{/if}
        {/if}
      </section>

      <section class="card">
        <h2>禁写流水</h2>
        {#if curfewHits.length === 0}
          <p>暂无命中禁写窗的写入。</p>
        {:else}
          <table>
            <thead>
              <tr><th>#</th><th>时间（服务器）</th><th>操作人</th><th>饮片</th><th>命中禁写窗</th></tr>
            </thead>
            <tbody>
              {#each curfewHits as hit}
                <tr>
                  <td>{hit.id}</td>
                  <td>{fmtTs(hit.attempted_at)}</td>
                  <td>{hit.attempted_by}</td>
                  <td>{hit.herb}</td>
                  <td>{hit.window_start}–{hit.window_end}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    {/if}
  {/if}
</main>

<style>
  main { font-family: sans-serif; max-width: 720px; margin: 24px auto; color: #3f2f1f; }
  h1 { color: #7c2d12; }
  h2 { color: #7c2d12; font-size: 18px; margin: 0 0 10px; }
  input { margin-right: 8px; padding: 6px; }
  nav { display: flex; align-items: center; gap: 16px; padding: 10px 14px; background: #7c2d12; border-radius: 8px; color: #fff7ed; }
  nav strong { margin-right: 8px; }
  nav a { color: #fed7aa; text-decoration: none; padding: 4px 8px; border-radius: 6px; }
  nav a.active { background: #9a3412; color: #ffffff; font-weight: 600; }
  nav .fill { flex: 1; }
  nav .who { font-size: 13px; color: #ffedd5; }
  .card { border: 1px solid #e7d8c9; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; background: #fffaf4; }
  .badge { display: inline-block; padding: 6px 12px; border-radius: 6px; font-weight: 600; }
  .badge.ban { background: #fee2e2; color: #991b1b; }
  .badge.ok { background: #dcfce7; color: #166534; }
  .err { color: #b91c1c; }
  .oktext { color: #166534; }
  .hint { color: #8a6d4b; font-size: 13px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #e7d8c9; padding: 6px 10px; text-align: left; font-size: 14px; }
  th { background: #f5e9db; }
</style>
