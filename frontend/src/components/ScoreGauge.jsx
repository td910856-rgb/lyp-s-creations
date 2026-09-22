import { levelOf } from './ScoreCard.jsx'

const COLOR = {
  good: 'var(--good)',
  mid: 'var(--mid)',
  low: 'var(--low)',
}

const VERDICT = {
  good: '匹配度较高',
  mid: '基本匹配',
  low: '差距明显',
}

// 总体匹配度：用圆环显示，一眼看出高低
export default function ScoreGauge({ score }) {
  const value = Math.max(0, Math.min(100, Math.round(Number(score) || 0)))
  const level = levelOf(value)

  return (
    <div className="gauge" style={{ '--pct': value, '--ring': COLOR[level] }}>
      <div className="gauge-inner">
        <div className="gauge-value">
          {value}
          <span className="gauge-unit">分</span>
        </div>
        <div className="gauge-label">{VERDICT[level]}</div>
      </div>
    </div>
  )
}

