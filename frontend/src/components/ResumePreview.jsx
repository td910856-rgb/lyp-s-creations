import { useState } from 'react'

// 极简 Markdown 渲染：只支持 # ## ###、- 列表、> 引用和 **加粗**。
// 不引第三方库，够用就行。

function renderInline(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${keyPrefix}-${index}`}>{part}</span>
  })
}

function parseBlocks(text) {
  const blocks = []
  let list = null

  for (const raw of (text || '').split('\n')) {
    const line = raw.trim()

    if (!line) {
      list = null
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.*)$/)
    if (heading) {
      blocks.push({ type: `h${heading[1].length}`, text: heading[2] })
      list = null
      continue
    }

    const bullet = line.match(/^[-*]\s+(.*)$/)
    if (bullet) {
      if (!list) {
        list = { type: 'ul', items: [] }
        blocks.push(list)
      }
      list.items.push(bullet[1])
      continue
    }

    const quote = line.match(/^>\s*(.*)$/)
    if (quote) {
      blocks.push({ type: 'quote', text: quote[1] })
      list = null
      continue
    }

    blocks.push({ type: 'p', text: line })
    list = null
  }

  return blocks
}

export default function ResumePreview({ markdown, analysisId }) {
  const [copied, setCopied] = useState(false)
  const [a4, setA4] = useState(false)
  const blocks = parseBlocks(markdown)

  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
      window.alert('复制失败，请手动选中文本复制。')
    }
  }

  return (
    <div className="preview">
      <div className="preview-toolbar">
        <span className="preview-tip">可直接复制到 Word 再微调排版</span>
        <div className="preview-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setA4((value) => !value)}>
            {a4 ? '适应窗口' : 'A4 预览'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => window.print()}>
            打印 / 存 PDF
          </button>
          {analysisId ? (
            <a className="btn btn-ghost" href={`/api/analyses/${analysisId}/export.docx`}>
              下载 Word
            </a>
          ) : null}
          <button type="button" className="btn btn-ghost" onClick={copy}>
            {copied ? '已复制 ✓' : '复制全文'}
          </button>
        </div>
      </div>

      <article className={`preview-body${a4 ? ' is-a4' : ''}`}>
        {blocks.length === 0 && <p className="muted">模型没有返回优化后的简历文本。</p>}
        {blocks.map((block, index) => {
          const key = `block-${index}`
          if (block.type === 'ul') {
            return (
              <ul key={key}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </ul>
            )
          }
          if (block.type === 'h1') return <h3 key={key}>{renderInline(block.text, key)}</h3>
          if (block.type === 'h2') return <h4 key={key}>{renderInline(block.text, key)}</h4>
          if (block.type === 'h3') return <h5 key={key}>{renderInline(block.text, key)}</h5>
          if (block.type === 'quote') return <blockquote key={key}>{renderInline(block.text, key)}</blockquote>
          return <p key={key}>{renderInline(block.text, key)}</p>
        })}
      </article>
    </div>
  )
}
