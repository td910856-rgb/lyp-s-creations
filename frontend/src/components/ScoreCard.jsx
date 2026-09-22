// 小指标条：标签 + 分数 + 进度条
function clamp(score) {
  return Math.max(0, Math.min(100, Math.round(Number(score) || 0)))
}

export function levelOf(value) {
  if (value >= 75) return 'good'
  if (value >= 55) return 'mid'
  return 'low'
}

export default function ScoreCard({ label, score, caption }) {
  const value = clamp(score)
  const level = levelOf(value)

  return (
    <div className="metric">
      <div className="metric-head">
        <span>
          {label}
          {caption ? ` · ${caption}` : ''}
        </span>
        <span className="metric-value">{value}</span>
      </div>
      <div className="metric-bar">
        <div className={`metric-fill lv-${level}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

