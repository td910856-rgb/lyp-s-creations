// 所有和后端打交道的代码都集中在这一个文件里。
// 以后要改接口地址、加请求头，只改这里。

const BASE = '/api'

const CLIENT_ID_KEY = 'resume-client-id'
const LLM_KEY = 'resume-llm-key'
const LLM_BASE = 'resume-llm-base'
const LLM_MODEL = 'resume-llm-model'

// 每个浏览器一个随机 ID，用来识别"我自己上传的数据"（没有账号系统）
export function getClientId() {
  let id = localStorage.getItem(CLIENT_ID_KEY)
  if (!id) {
    id =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `c-${Date.now()}-${Math.random().toString(16).slice(2)}`
    localStorage.setItem(CLIENT_ID_KEY, id)
  }
  return id
}

// 访客自己的模型配置：只存在浏览器里，每次请求临时带上，服务端不保存
export function getLlmSettings() {
  return {
    apiKey: localStorage.getItem(LLM_KEY) || '',
    baseUrl: localStorage.getItem(LLM_BASE) || '',
    model: localStorage.getItem(LLM_MODEL) || '',
  }
}

export function saveLlmSettings(settings) {
  localStorage.setItem(LLM_KEY, settings.apiKey || '')
  localStorage.setItem(LLM_BASE, settings.baseUrl || '')
  localStorage.setItem(LLM_MODEL, settings.model || '')
}

function extraHeaders() {
  const headers = { 'X-Client-Id': getClientId() }
  const llm = getLlmSettings()
  if (llm.apiKey) {
    headers['X-LLM-Key'] = llm.apiKey
    if (llm.baseUrl) headers['X-LLM-Base-URL'] = llm.baseUrl
    if (llm.model) headers['X-LLM-Model'] = llm.model
  }
  return headers
}

// 把 FastAPI 的错误信息翻译成一句人话。
function toMessage(data, status) {
  const detail = data?.detail

  if (typeof detail === 'string') return detail

  // 字段校验失败时，FastAPI 返回的是一个数组
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item.msg || '参数不正确').replace(/^Value error,\s*/, ''))
      .join('；')
  }

  if (status >= 500) return '后端出错了，请查看后端窗口里的报错信息。'
  return `请求失败（状态码 ${status}）`
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(BASE + path, {
      ...options,
      headers: { ...extraHeaders(), ...(options.headers || {}) },
    })
  } catch {
    throw new Error('连不上后端服务，请确认后端已经启动（默认 8000 端口）。')
  }

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }

  if (!response.ok) {
    throw new Error(toMessage(data, response.status))
  }
  return data
}

// 检查后端与模型配置状态
export function getHealth() {
  return request('/health')
}

// 上传简历文件，返回 { id, filename, char_count, preview, ... }
export function uploadResume(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/resumes/upload', { method: 'POST', body: form })
}

// 发起一次分析
// useWeb        = 是否联网采集最新岗位信息
// jobDescription = 用户自己粘贴的岗位 JD（填了就优先用它）
export function createAnalysis(resumeId, jobTitle, useWeb = true, jobDescription = '') {
  return request('/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      resume_id: resumeId,
      job_title: jobTitle,
      use_web: useWeb,
      job_description: jobDescription,
    }),
  })
}

// 最近的分析记录
export function listAnalyses(limit = 8) {
  return request(`/analyses?limit=${limit}`)
}

// 已上传的简历列表（用于切换）
export function listResumes(limit = 20) {
  return request(`/resumes?limit=${limit}`)
}

// 删除一条分析记录
export function deleteAnalysis(id) {
  return request(`/analyses/${id}`, { method: 'DELETE' })
}

// 读取某条历史分析结果
export function getAnalysis(id) {
  return request(`/analyses/${id}`)
}

// 这个浏览器上传过什么
export function getMyData() {
  return request('/my-data')
}

// 删除这个浏览器产生的全部数据
export function deleteMyData() {
  return request('/my-data', { method: 'DELETE' })
}
