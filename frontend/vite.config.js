import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 关键配置：把 /api 开头的请求转发给后端（8000 端口）。
// 有了这个代理，前端代码里直接写 fetch('/api/health') 就行，
// 不用关心端口号，也不会遇到浏览器跨域拦截。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

