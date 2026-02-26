import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import PrivacyPage from './pages/PrivacyPage'
import TermsPage from './pages/TermsPage'
import './index.css'

function resolvePage(pathname: string) {
  const normalizedPath = pathname.replace(/\/+$/, '') || '/'
  if (normalizedPath === '/privacy') return <PrivacyPage />
  if (normalizedPath === '/terms') return <TermsPage />
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {resolvePage(window.location.pathname)}
  </React.StrictMode>,
)
