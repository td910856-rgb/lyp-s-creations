import { useState } from 'react'

import ResumePreview from './ResumePreview.jsx'
import ScoreCard from './ScoreCard.jsx'
import ScoreGauge from './ScoreGauge.jsx'

const IMPORTANCE_ORDER = { 高: 0, 中: 1, 低: 2 }

function importanceClass(importance) {
  if (importance === '高') return 'tag tag-high'
  if (importance === '低') return 'tag tag-low'
  return 'tag tag-mid'
}

// 分析结果展示区：总览 → 技能 → 项目 → 建议 → 来源 → 优化后的简历
export default function ResultPanel({ result }) {
  const [linkCopied, setLinkCopied] = useState(false)
  const details = result.details || {}
  const missing = [...(details.missing_keywords || [])].sort(
    (a, b) => (IMPORTANCE_ORDER[a.importance] ?? 1) - (IMPORTANCE_ORDER[b.importance] ?? 1),
  )
  const sources = details.web_sources || []
  const questions = details.interview_questions || []
  const delta = details.score_delta

  async function copyLink() {
    const url = `${window.location.origin}${window.location.pathname}?analysis=${result.id}`
    try {
      await navigator.clipboard.writeText(url)
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2000)
    } catch {
      window.prompt('复制这个链接：', url)
    }
  }

  return (
    <div className="result">
      {result.is_mock && (
        <div className="banner banner-warn">
          当前是<strong>演示模式</strong>，分数和建议是系统生成的示例数据，没有调用真实模型。
          在 <code>backend/.env</code> 里把 <code>LLM_MOCK</code> 改成 0 就能得到真实分析。
        </div>
      )}

      <section className="card">
        <header className="card-head">
          <h2 className="section-title">匹配度总览</h2>
          <div className="head-right">
            {typeof delta === 'number' && (
              <span className={`delta${delta > 0 ? ' is-up' : delta < 0 ? ' is-down' : ''}`}>
                {delta > 0 ? `比上次 +${delta}` : delta < 0 ? `比上次 ${delta}` : '和上次持平'} 分
              </span>
            )}
            <span className="muted small">
              {result.resume_filename} · {result.job_title}
            </span>
            <button type="button" className="btn btn-ghost" onClick={copyLink}>
              {linkCopied ? '链接已复制 ✓' : '复制链接'}
            </button>
          </div>
        </header>

        <div className="score-hero">
          <ScoreGauge score={result.overall_score} />
          <div className="score-side">
            <ScoreCard label="技能匹配度" score={result.skill_score} caption="硬技能覆盖" />
            <ScoreCard label="项目匹配度" score={result.project_score} caption="项目相关度" />
          </div>
        </div>

        {details.overall_summary && <p className="summary">{details.overall_summary}</p>}
      </section>

      <section className="card">
        <h2 className="section-title">技能与关键词</h2>

        <h3 className="sub">已具备的技能</h3>
        {(details.matched_skills || []).length > 0 ? (
          <div className="chips">
            {details.matched_skills.map((skill) => (
              <span key={skill} className="chip chip-ok">
                {skill}
              </span>
            ))}
          </div>
        ) : (
          <p className="muted small">没有识别到和岗位匹配的技能，建议在技能栏明确写出。</p>
        )}

        <h3 className="sub">岗位关键词缺失（{missing.length} 项）</h3>
        {missing.length > 0 ? (
          <ul className="keyword-list">
            {missing.map((item, index) => (
              <li key={`${item.keyword}-${index}`}>
                <div className="keyword-head">
                  <strong>{item.keyword}</strong>
                  <span className={importanceClass(item.importance)}>{item.importance}</span>
                  <span className="muted small">{item.category}</span>
                </div>
                {item.note && <p className="muted small">{item.note}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">没有发现明显缺失的关键词。</p>
        )}
      </section>

      {(details.project_comments || []).length > 0 && (
        <section className="card">
          <h2 className="section-title">项目经历点评</h2>
          <ul className="project-list" style={{ marginTop: 14 }}>
            {details.project_comments.map((project, index) => (
              <li key={`${project.title}-${index}`}>
                <p className="project-title">{project.title}</p>
                {project.comment && <p className="suggest">{project.comment}</p>}
                {project.suggestion && (
                  <p className="suggest suggest-example">
                    <strong>怎么改：</strong>
                    {project.suggestion}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(details.suggestions || []).length > 0 && (
        <section className="card">
          <h2 className="section-title">简历修改建议</h2>
          <ol className="suggestion-list" style={{ marginTop: 14 }}>
            {details.suggestions.map((item, index) => (
              <li key={`${item.area}-${index}`}>
                <div className="suggestion-head">
                  <span className="tag tag-area">{item.area}</span>
                </div>
                {item.problem && (
                  <p className="suggest">
                    <strong>问题：</strong>
                    {item.problem}
                  </p>
                )}
                {item.advice && (
                  <p className="suggest">
                    <strong>建议：</strong>
                    {item.advice}
                  </p>
                )}
                {item.example && (
                  <p className="suggest suggest-example">
                    <strong>示范：</strong>
                    {item.example}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {(details.web_note || sources.length > 0) && (
        <section className="card">
          <header className="card-head">
            <h2 className="section-title">岗位信息来源</h2>
            <span className={details.web_status === 'ok' || details.web_status === 'manual' ? 'ok small' : 'warn small'}>
              {details.web_status === 'ok'
                ? '联网采集成功'
                : details.web_status === 'manual'
                  ? '使用你粘贴的 JD'
                  : '本次未采集到'}
            </span>
          </header>

          {details.web_note && <p className="muted small">{details.web_note}</p>}

          {sources.length > 0 && (
            <ul className="source-list" style={{ marginTop: 10 }}>
              {sources.map((source, index) => (
                <li key={`${source.url}-${index}`}>
                  <span className="muted small">#{index + 1}</span>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title || source.url}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {questions.length > 0 && (
        <section className="card">
          <header className="card-head">
            <h2 className="section-title">面试可能会问这些</h2>
            <span className="muted small">{questions.length} 个问题</span>
          </header>
          <ol className="question-list">
            {questions.map((item, index) => (
              <li key={`${item.question}-${index}`}>
                <p className="question-text">
                  <span className="q-index">Q{index + 1}</span>
                  {item.question}
                </p>
                {item.why && (
                  <p className="suggest">
                    <strong>为什么问：</strong>
                    {item.why}
                  </p>
                )}
                {item.hint && (
                  <p className="suggest suggest-example">
                    <strong>答题思路：</strong>
                    {item.hint}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="card card-resume">
        <h2 className="section-title" style={{ marginBottom: 14 }}>
          优化后的简历
        </h2>
        <ResumePreview markdown={details.optimized_resume} analysisId={result.id} />
      </section>
    </div>
  )
}
