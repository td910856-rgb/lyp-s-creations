import { useEffect, useState } from 'react'

import {
  createAnalysis,
  deleteAnalysis,
  deleteMyData,
  getAnalysis,
  getHealth,
  getLlmSettings,
  getMyData,
  listAnalyses,
  listResumes,
  saveLlmSettings,
  uploadResume,
} from './api.js'
import ResumeUploader from './components/ResumeUploader.jsx'
import ResultPanel from './components/ResultPanel.jsx'

const PRESET_JOBS = ['字节跳动 AI 算法实习生', '数据分析实习生', '后端开发实习生', '产品运营实习生']

export default function App() {
  const [health, setHealth] = useState(null)
  const [file, setFile] = useState(null)
  const [resume, setResume] = useState(null)
  const [jobTitle, setJobTitle] = useState('')
  const [useWeb, setUseWeb] = useState(true)
  const [jdText, setJdText] = useState('')
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [resumes, setResumes] = useState([])
  const [error, setError] = useState('')
  const [status, setStatus] = useState('idle') // idle | uploading | analyzing
  // 主题可以从 ?theme=dark 指定，方便分享链接；否则用上次的选择
  const [theme, setTheme] = useState(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('theme')
    return fromUrl === 'dark' || fromUrl === 'light'
      ? fromUrl
      : localStorage.getItem('resume-theme') || 'light'
  })
  const [llm, setLlm] = useState(() => getLlmSettings())
  const [myData, setMyData] = useState(null)

  const busy = status !== 'idle'
  // 粘贴了足够长的 JD，就以它为准，不再联网采集
  const hasJd = jdText.trim().length >= 30
  const canAnalyze = Boolean(resume) && jobTitle.trim().length >= 2 && !busy

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('resume-theme', theme)
  }, [theme])

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((err) => setError(err.message))
    refreshHistory()
    refreshResumes()

    // 支持用 ?analysis=8 直接打开某一次的分析结果（方便收藏和分享）
    const wanted = new URLSearchParams(window.location.search).get('analysis')
    if (wanted) {
      getAnalysis(Number(wanted))
        .then((data) => {
          setResult(data)
          setJobTitle(data.job_title)
        })
        .catch(() => {})
    }
  }, [])

  function refreshHistory() {
    listAnalyses()
      .then(setHistory)
      .catch(() => setHistory([]))
  }

  function refreshResumes() {
    listResumes()
      .then(setResumes)
      .catch(() => setResumes([]))
  }

  function scrollToResult() {
    requestAnimationFrame(() => {
      document.getElementById('result-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  // 选好文件就立刻上传并提取文字，不用再点一次按钮
  async function handleSelectFile(picked) {
    setFile(picked)
    setResume(null)
    setResult(null)
    setError('')
    setStatus('uploading')

    try {
      const data = await uploadResume(picked)
      setResume(data)
      refreshResumes()
    } catch (err) {
      setError(err.message)
      setFile(null)
    } finally {
      setStatus('idle')
    }
  }

  async function handleAnalyze() {
    if (!canAnalyze) return
    setStatus('analyzing')
    setError('')
    setResult(null)

    try {
      const data = await createAnalysis(resume.id, jobTitle.trim(), useWeb, jdText.trim())
      setResult(data)
      refreshHistory()
      scrollToResult()
    } catch (err) {
      setError(err.message)
    } finally {
      setStatus('idle')
    }
  }

  async function handleOpenHistory(id) {
    setError('')
    try {
      const data = await getAnalysis(id)
      setResult(data)
      setJobTitle(data.job_title)
      scrollToResult()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteHistory(id) {
    if (!window.confirm('删除这条分析记录？删除后无法恢复。')) return
    try {
      await deleteAnalysis(id)
      setHistory((prev) => prev.filter((item) => item.id !== id))
      if (result?.id === id) setResult(null)
    } catch (err) {
      setError(err.message)
    }
  }

  function handlePickResume(item) {
    setResume(item)
    setFile(null)
    setResult(null)
    setError('')
  }

  function handleLlmChange(field, value) {
    const next = { ...llm, [field]: value }
    setLlm(next)
    saveLlmSettings(next)
  }

  async function handleLoadMyData() {
    try {
      setMyData(await getMyData())
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteMyData() {
    if (!window.confirm('删除你在本站上传的简历和分析记录？删除后无法恢复。')) return
    try {
      await deleteMyData()
      setMyData({ resumes: [], analyses: [] })
      setResume(null)
      setFile(null)
      setResult(null)
      refreshHistory()
      refreshResumes()
    } catch (err) {
      setError(err.message)
    }
  }

  const connected = Boolean(health)
  const modelLabel = llm.apiKey
    ? '你自己的密钥'
    : health
      ? health.llm.mode === 'mock'
        ? '演示数据'
        : health.llm.model
      : '检查中…'

  return (
    <>
      <header className="appbar">
        <div className="appbar-inner">
          <span className="brand">
            <span className="brand-mark">AI</span>
            简历优化器
          </span>
          <span className="appbar-spacer" />

          <span className={`pill${connected ? '' : ' is-off'}`}>
            <span className="pill-dot" />
            {connected ? '已连接' : '未连接'}
          </span>
          <span className={`pill${health?.llm.mode === 'mock' ? ' is-warn' : ''}`}>
            模型：{modelLabel}
          </span>
          <span className="pill">联网采集：{health?.web?.enabled === false ? '关' : '开'}</span>
          {typeof health?.quota?.remaining === 'number' && (
            <span className="pill">今日剩余 {health.quota.remaining} 次</span>
          )}
          <button
            type="button"
            className="pill pill-btn"
            onClick={() => setTheme((value) => (value === 'dark' ? 'light' : 'dark'))}
          >
            {theme === 'dark' ? '☀️ 浅色' : '🌙 深色'}
          </button>
        </div>
      </header>

      <div className="page">
        <div className="hero">
          <h1>看看你的简历和目标岗位差在哪</h1>
          <p>上传简历 + 输入岗位，得到匹配度打分、关键词缺口和一份改写后的简历。</p>
        </div>

        <div className="layout">
          <aside className="sidebar">
            <section className="card">
              <h2 className="step-title">
                <span className="step-num">1</span>
                上传简历
              </h2>
              <ResumeUploader
                file={file}
                onSelect={handleSelectFile}
                disabled={busy}
                busy={status === 'uploading'}
              />

              {resume && (
                <div className="extract">
                  <p className="muted small">
                    当前简历：<strong>{resume.filename}</strong>（{resume.char_count} 字）
                  </p>
                  <p className="extract-text">{resume.preview}</p>
                </div>
              )}

              {resumes.length > 1 && (
                <details className="jd-holder" style={{ marginTop: 14, marginBottom: 0 }}>
                  <summary>换一份以前传过的简历（{resumes.length} 份）</summary>
                  <ul className="resume-list">
                    {resumes.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          className={`resume-pick${resume?.id === item.id ? ' is-active' : ''}`}
                          onClick={() => handlePickResume(item)}
                          disabled={busy}
                        >
                          <span className="history-title">{item.filename}</span>
                          <span className="muted small">{item.char_count} 字</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </section>

            <section className="card">
              <h2 className="step-title">
                <span className="step-num">2</span>
                填写目标岗位
              </h2>
              <input
                className="input"
                value={jobTitle}
                placeholder="例如：字节跳动 AI 算法实习生"
                onChange={(event) => setJobTitle(event.target.value)}
                disabled={busy}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleAnalyze()
                }}
              />

              <div className="chips">
                {PRESET_JOBS.map((job) => (
                  <button
                    key={job}
                    type="button"
                    className="chip chip-button"
                    onClick={() => setJobTitle(job)}
                    disabled={busy}
                  >
                    {job}
                  </button>
                ))}
              </div>

              <details className="jd-holder">
                <summary>有完整岗位 JD？粘贴进来更准</summary>
                <textarea
                  className="textarea"
                  rows={6}
                  value={jdText}
                  onChange={(event) => setJdText(event.target.value)}
                  disabled={busy}
                  placeholder="把招聘页面上的岗位描述整段复制到这里，例如「岗位职责…任职要求…」"
                />
                <p className="muted small">
                  填了就用你粘贴的内容分析，不会再联网采集（招聘网站大多抓不全，粘贴的最准）。
                </p>
              </details>

              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={useWeb && !hasJd}
                  onChange={(event) => setUseWeb(event.target.checked)}
                  disabled={busy || hasJd}
                />
                <span>
                  {hasJd
                    ? '已填 JD，将直接用你粘贴的内容分析'
                    : '联网采集该岗位的最新招聘要求，作为打分依据（更准，但慢一点）'}
                </span>
              </label>

              <button
                type="button"
                className="btn btn-primary"
                onClick={handleAnalyze}
                disabled={!canAnalyze}
              >
                {status === 'analyzing' ? '分析中…' : '开始分析'}
              </button>
            </section>

            {history.length > 0 && (
              <section className="card">
                <h2 className="step-title">最近的分析</h2>
                <ul className="history-list">
                  {history.map((item) => (
                    <li key={item.id} className="history-row">
                      <button
                        type="button"
                        className="history-item"
                        onClick={() => handleOpenHistory(item.id)}
                      >
                        <span className="history-title">{item.job_title}</span>
                        <span className="history-score">{item.overall_score}</span>
                      </button>
                      <button
                        type="button"
                        className="history-del"
                        title="删除这条记录"
                        onClick={() => handleDeleteHistory(item.id)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="card">
              <h2 className="step-title">设置与隐私</h2>

              <details className="jd-holder" style={{ marginBottom: 0 }}>
                <summary>模型设置（{llm.apiKey ? '正在用你自己的密钥' : '用本站默认模型'}）</summary>

                <div className="field">
                  <label htmlFor="llm-key">API Key</label>
                  <input
                    id="llm-key"
                    className="input"
                    type="password"
                    value={llm.apiKey}
                    placeholder="sk-...（留空则用本站的）"
                    onChange={(event) => handleLlmChange('apiKey', event.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="llm-base">接口地址</label>
                  <input
                    id="llm-base"
                    className="input"
                    value={llm.baseUrl}
                    placeholder="https://api.deepseek.com/v1"
                    onChange={(event) => handleLlmChange('baseUrl', event.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="llm-model">模型名</label>
                  <input
                    id="llm-model"
                    className="input"
                    value={llm.model}
                    placeholder="deepseek-flash"
                    onChange={(event) => handleLlmChange('model', event.target.value)}
                  />
                </div>

                <p className="muted small" style={{ paddingBottom: 10 }}>
                  密钥只存在你自己的浏览器里，每次请求临时带上，服务器不保存、也不写日志。
                  填了它就用你的额度，不占本站的每日次数。
                </p>
              </details>

              <details className="jd-holder" style={{ margin: '10px 0 0' }}>
                <summary>隐私与我的数据</summary>
                <p className="muted small" style={{ paddingTop: 4 }}>
                  上传的简历和分析记录会在{' '}
                  {health?.privacy?.retention_hours ?? 72} 小时后自动删除；每天免费额度{' '}
                  {health?.privacy?.rate_limit_per_day ?? 10} 次
                  {typeof health?.quota?.remaining === 'number'
                    ? `，今天还剩 ${health.quota.remaining} 次`
                    : ''}
                  。
                </p>
                <div className="row-btns">
                  <button type="button" className="btn btn-ghost" onClick={handleLoadMyData}>
                    查看我上传过什么
                  </button>
                  <button type="button" className="btn btn-ghost btn-danger" onClick={handleDeleteMyData}>
                    删除我的全部数据
                  </button>
                </div>
                {myData && (
                  <p className="muted small" style={{ paddingBottom: 10 }}>
                    这个浏览器上传过 {myData.resumes.length} 份简历、做过{' '}
                    {myData.analyses.length} 次分析。
                  </p>
                )}
              </details>
            </section>
          </aside>

          <main className="content" id="result-anchor">
            {health?.privacy?.require_own_key && !llm.apiKey && (
              <div className="banner banner-info">
                这个站点<strong>不提供模型密钥</strong>。开始分析前，请在左侧「设置与隐私 → 模型设置」
                里填上你自己的 API Key（DeepSeek、通义千问、OpenRouter 都可以，密钥只存在你浏览器里）。
              </div>
            )}

            {error && (
              <div className="banner banner-error">
                <strong>出错了：</strong>
                {error}
              </div>
            )}

            {status === 'analyzing' && (
              <section className="card">
                <div className="spinner" />
                <p style={{ textAlign: 'center', fontWeight: 550 }}>正在分析，请不要关闭页面</p>
                <p className="muted small" style={{ textAlign: 'center' }}>
                  联网采集 + 模型生成，本地模型通常要 30 秒到 2 分钟
                </p>
                <div style={{ marginTop: 26 }}>
                  <div className="skeleton skeleton-row" style={{ width: '38%' }} />
                  <div className="skeleton skeleton-row" style={{ width: '92%' }} />
                  <div className="skeleton skeleton-row" style={{ width: '76%' }} />
                  <div className="skeleton skeleton-row" style={{ width: '85%' }} />
                </div>
              </section>
            )}

            {!result && status !== 'analyzing' && (
              <section className="card placeholder">
                <div className="placeholder-icon">📄</div>
                <p className="placeholder-title">结果会显示在这里</p>
                <p className="muted small">左边上传简历、填好岗位，点「开始分析」。</p>
                <ul className="placeholder-steps">
                  <li>
                    <span className="dot">1</span>总体、技能、项目三个匹配度分数
                  </li>
                  <li>
                    <span className="dot">2</span>岗位关键词缺了哪些，重要程度如何
                  </li>
                  <li>
                    <span className="dot">3</span>每条怎么改，附可直接抄的示范句
                  </li>
                  <li>
                    <span className="dot">4</span>一份改写好的完整简历，可一键复制
                  </li>
                </ul>
              </section>
            )}

            {result && <ResultPanel result={result} />}
          </main>
        </div>

        <footer className="footer">
          本地运行 · 简历只保存在你自己的电脑上（backend/resume.db）
        </footer>
      </div>
    </>
  )
}
