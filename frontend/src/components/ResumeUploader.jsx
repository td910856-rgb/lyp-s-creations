import { useRef, useState } from 'react'

const ACCEPT = '.pdf,.docx,.txt,.md'

// 简历上传框：支持点击选择，也支持把文件拖进来。
// 选中文件后立刻交给父组件上传，用户不用再点一次「上传」。
export default function ResumeUploader({ file, onSelect, disabled, busy }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) onSelect(dropped)
  }

  function handleChange(event) {
    const picked = event.target.files?.[0]
    if (picked) onSelect(picked)
    event.target.value = '' // 允许重复选择同一个文件
  }

  return (
    <div
      className={`uploader${dragging ? ' is-dragging' : ''}${disabled ? ' is-disabled' : ''}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(event) => {
        event.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
      }}
    >
      <input ref={inputRef} type="file" accept={ACCEPT} onChange={handleChange} hidden />

      {file ? (
        <div className="uploader-file">
          <span className="uploader-icon">📄</span>
          <div>
            <p className="uploader-filename">{file.name}</p>
            <p className="uploader-hint">
              {(file.size / 1024).toFixed(0)} KB{busy ? ' · 正在读取文字…' : ' · 点击可更换文件'}
            </p>
          </div>
        </div>
      ) : (
        <div className="uploader-empty">
          <span className="uploader-icon">⬆️</span>
          <p className="uploader-title">点击选择简历，或把文件拖到这里</p>
          <p className="uploader-hint">支持 PDF、DOCX、TXT，单个文件不超过 10 MB</p>
        </div>
      )}
    </div>
  )
}

