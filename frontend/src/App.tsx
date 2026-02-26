import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CalendarDays, CheckCircle2, Github, Loader2 } from 'lucide-react'
import ResultsAndImageSection from './components/ResultsAndImageSection'

type Status = 'Applied' | 'Interviewing' | 'Rejected' | 'Offer'

type Summary = {
  applications: number
  interviews: number
  rejections: number
  offers: number
  noResponse: number
  timeToOfferDays: number | null
  timeSpentDays: number | null
}

type ApplicationRow = {
  company: string
  position: string
  applicationDate: string
  currentStatus: Status
  evidenceSubject: string
}

type MessageRow = {
  date: string
  company: string
  eventType: string
  subject: string
}

type CsvRow = Record<string, string>
type MailProvider = 'gmail' | 'outlook'
type ScanApiPayload = {
  base_path?: string
  detail?: string
  summary?: Record<string, unknown>
  application_rows?: CsvRow[]
  message_rows?: CsvRow[]
  sankey_image_data_url?: string
}

type AuthStatusPayload = {
  connected?: boolean
  provider?: string
}

const EMPTY_SUMMARY: Summary = {
  applications: 0,
  interviews: 0,
  rejections: 0,
  offers: 0,
  noResponse: 0,
  timeToOfferDays: null,
  timeSpentDays: null,
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function apiPath(path: string): string {
  if (!path.startsWith('/')) return `${API_BASE_URL}/${path}`
  return `${API_BASE_URL}${path}`
}

function normalizeProvider(value: string | null | undefined): MailProvider {
  return value?.toLowerCase() === 'outlook' ? 'outlook' : 'gmail'
}

function providerLabel(provider: MailProvider): string {
  return provider === 'outlook' ? 'Outlook' : 'Gmail'
}

function parseCsv(text: string): CsvRow[] {
  if (!text.trim()) return []

  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]
    const next = text[i + 1]

    if (char === '"') {
      if (inQuotes && next === '"') {
        field += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }

    if (!inQuotes && char === ',') {
      row.push(field)
      field = ''
      continue
    }

    if (!inQuotes && (char === '\n' || char === '\r')) {
      if (char === '\r' && next === '\n') i += 1
      row.push(field)
      rows.push(row)
      row = []
      field = ''
      continue
    }

    field += char
  }

  row.push(field)
  rows.push(row)

  const headers = rows[0]?.map((h) => h.trim()) ?? []
  const dataRows = rows.slice(1).filter((r) => r.some((v) => v.trim() !== ''))
  return dataRows.map((r) => {
    const out: CsvRow = {}
    headers.forEach((header, index) => {
      out[header] = r[index] ?? ''
    })
    return out
  })
}

function normalizeStatus(value: string): Status {
  const s = value.trim().toLowerCase()
  if (s === 'offer' || s === 'offered') return 'Offer'
  if (s === 'rejected' || s === 'rejection') return 'Rejected'
  if (s === 'interviewing' || s === 'interview') return 'Interviewing'
  return 'Applied'
}

function toIsoDateLocal(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function toDayDiff(startIso: string, endIso: string): number | null {
  if (!startIso || !endIso) return null
  const start = new Date(startIso)
  const end = new Date(endIso)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
  const ms = end.getTime() - start.getTime()
  return Math.max(Math.floor(ms / (1000 * 60 * 60 * 24)), 0)
}

function computeTiming(messageRows: CsvRow[]): { timeToOfferDays: number | null; timeSpentDays: number | null } {
  const validDates = messageRows
    .map((r) => r.date)
    .filter(Boolean)
    .map((d) => new Date(d))
    .filter((d) => !Number.isNaN(d.getTime()))

  if (validDates.length === 0) {
    return { timeToOfferDays: null, timeSpentDays: null }
  }

  const sorted = [...validDates].sort((a, b) => a.getTime() - b.getTime())
  const firstEmail = sorted[0].toISOString()
  const lastEmail = sorted[sorted.length - 1].toISOString()

  const applicationDates = messageRows
    .filter((r) => (r.event_type || '').toLowerCase() === 'application')
    .map((r) => r.date)
    .filter(Boolean)
    .sort()

  const offerDates = messageRows
    .filter((r) => (r.event_type || '').toLowerCase() === 'offer')
    .map((r) => r.date)
    .filter(Boolean)
    .sort()

  const timeToOfferDays = applicationDates.length > 0 && offerDates.length > 0 ? toDayDiff(applicationDates[0], offerDates[0]) : null
  const timeSpentDays = toDayDiff(firstEmail, lastEmail)

  return { timeToOfferDays, timeSpentDays }
}

async function loadRunData(startDate: string, endDate: string, email: string, preferredBasePath?: string) {
  const emailKey = email
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  const rangeDir = `${startDate}_to_${endDate}`
  const baseCandidates = emailKey ? [`/output/${emailKey}/${rangeDir}`, `/output/${rangeDir}`] : [`/output/${rangeDir}`]
  const orderedCandidates = preferredBasePath
    ? [preferredBasePath, ...baseCandidates.filter((path) => path !== preferredBasePath)]
    : baseCandidates

  for (let i = 0; i < orderedCandidates.length; i += 1) {
    const basePath = orderedCandidates[i]
    const [summaryRes, appRes, messageRes] = await Promise.all([
      fetch(`${basePath}/ai_result_summary.json`, { cache: 'no-store' }),
      fetch(`${basePath}/ai_application_table.csv`, { cache: 'no-store' }),
      fetch(`${basePath}/ai_message_classification.csv`, { cache: 'no-store' }),
    ])

    if (!summaryRes.ok || !appRes.ok || !messageRes.ok) {
      continue
    }

    const [summaryRaw, appRaw, messageRaw] = await Promise.all([summaryRes.text(), appRes.text(), messageRes.text()])

    // Vite can return index.html for missing files; skip such candidates safely.
    if (summaryRaw.trim().startsWith('<!doctype') || summaryRaw.trim().startsWith('<html')) {
      continue
    }

    let summaryJson: Record<string, unknown>
    try {
      summaryJson = JSON.parse(summaryRaw) as Record<string, unknown>
    } catch {
      continue
    }

    const appRowsCsv = parseCsv(appRaw)
    const messageRowsCsv = parseCsv(messageRaw)

    const applicationRows: ApplicationRow[] = appRowsCsv.map((r) => ({
      company: r.company || r.application_id || '-',
      position: r.position || '',
      applicationDate: r.application_date || '',
      currentStatus: normalizeStatus(r.current_status || ''),
      evidenceSubject: r.evidence_subject || '',
    }))

    const messageRows: MessageRow[] = messageRowsCsv.map((r) => ({
      date: r.date || '',
      company: r.company || '',
      eventType: r.event_type || '',
      subject: r.subject || '',
    }))

    const { timeToOfferDays, timeSpentDays } = computeTiming(messageRowsCsv)
    const summary: Summary = {
      applications: Number(summaryJson.applications ?? applicationRows.length ?? 0),
      interviews: Number(summaryJson.interviews ?? 0),
      rejections: Number(summaryJson.rejections_total ?? 0),
      offers: Number(summaryJson.offers ?? 0),
      noResponse: Number(summaryJson.no_response ?? 0),
      timeToOfferDays,
      timeSpentDays,
    }

    return {
      summary,
      applicationRows,
      messageRows,
      sankeyImageSrc: `${basePath}/ai_sankey.png?v=${Date.now()}`,
      sourcePath: basePath,
      usedFallback: i > 0 && basePath !== preferredBasePath,
    }
  }

  throw new Error(
    `No valid output files found for ${email} in ${startDate} to ${endDate}. Run the pipeline first for this date range.`,
  )
}

export default function App() {
  const [mailConnected, setMailConnected] = useState(false)
  const [connectedProvider, setConnectedProvider] = useState<MailProvider | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<MailProvider>('gmail')
  const [connectedEmail, setConnectedEmail] = useState<string | null>(null)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [startDate, setStartDate] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 1)
    return toIsoDateLocal(d)
  })
  const [endDate, setEndDate] = useState(() => toIsoDateLocal(new Date()))
  const [isRunning, setIsRunning] = useState(false)
  const [connectionStatusText, setConnectionStatusText] = useState('Checking mailbox connection...')
  const [scanStatusText, setScanStatusText] = useState('Ready to scan.')
  const [scanStatusTone, setScanStatusTone] = useState<'idle' | 'running' | 'success' | 'error'>('idle')
  const [hasRunResults, setHasRunResults] = useState(false)

  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY)
  const [applicationRows, setApplicationRows] = useState<ApplicationRow[]>([])
  const [messageRows, setMessageRows] = useState<MessageRow[]>([])

  const envSankeyImageSrc = import.meta.env.VITE_SANKEY_IMAGE_SRC
  const [sankeyImageSrc, setSankeyImageSrc] = useState(envSankeyImageSrc ?? '')
  const todayIso = useMemo(() => toIsoDateLocal(new Date()), [])
  const isActiveConnection = mailConnected
  const activeProvider = connectedProvider ?? 'gmail'

  const canRun = isActiveConnection && !isCheckingAuth && !isConnecting && !isRunning && Boolean(startDate) && Boolean(endDate)

  const runButtonText = useMemo(() => {
    if (isRunning) return 'Running...'
    if (!hasRunResults) return 'Run Scan'
    return 'Rerun Scan'
  }, [isRunning, hasRunResults])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const auth = params.get('auth')
    const authMessage = params.get('message')
    let cancelled = false

    const loadAuthStatus = async () => {
      setIsCheckingAuth(true)
      try {
        const response = await fetch(apiPath('/api/auth/status'), {
          method: 'GET',
          credentials: 'include',
        })
        const payload = (await response.json().catch(() => ({}))) as AuthStatusPayload
        if (cancelled) return

        if (payload.connected) {
          const currentProvider = normalizeProvider(payload.provider)
          const currentProviderLabel = providerLabel(currentProvider)
          setMailConnected(true)
          setConnectedProvider(currentProvider)
          setSelectedProvider(currentProvider)
          setConnectedEmail(null)
          if (auth === 'success') {
            setConnectionStatusText(`${currentProviderLabel} connected.`)
          } else if (authMessage) {
            setConnectionStatusText(authMessage)
          } else {
            setConnectionStatusText(`${currentProviderLabel} connected.`)
          }
        } else {
          setMailConnected(false)
          setConnectedProvider(null)
          setConnectedEmail(null)
          if (auth === 'error' && authMessage) {
            setConnectionStatusText(authMessage)
          } else {
            setConnectionStatusText('Connect an email provider first.')
          }
        }
      } catch {
        if (cancelled) return
        setMailConnected(false)
        setConnectedProvider(null)
        setConnectedEmail(null)
        setConnectionStatusText('Unable to verify mailbox connection.')
      } finally {
        if (!cancelled) {
          setIsCheckingAuth(false)
        }
      }
    }

    void loadAuthStatus()

    if (auth || authMessage) {
      const cleanUrl = `${window.location.pathname}${window.location.hash || ''}`
      window.history.replaceState({}, document.title, cleanUrl)
    }

    return () => {
      cancelled = true
    }
  }, [])

  const onSelectProvider = (provider: MailProvider) => {
    setSelectedProvider(provider)
    if (!isActiveConnection && !isCheckingAuth && !isConnecting) {
      setConnectionStatusText(`Ready to connect ${providerLabel(provider)}.`)
    }
  }

  const onConnect = async () => {
    const label = providerLabel(selectedProvider)
    const endpoint = selectedProvider === 'outlook' ? '/api/auth/outlook/start' : '/api/auth/google/start'
    setIsConnecting(true)
    setConnectionStatusText(`Redirecting to ${label} OAuth...`)
    window.location.assign(apiPath(endpoint))
  }

  const onRun = async () => {
    if (!canRun) return

    setIsRunning(true)
    setScanStatusTone('running')
    setScanStatusText(`Step 1/4: Checking ${providerLabel(activeProvider)} connection...`)

    try {
      await new Promise((resolve) => setTimeout(resolve, 500))
      setScanStatusText('Step 2/4: Running scan and classification...')

      const scanResponse = await fetch(apiPath('/api/scan'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email: connectedEmail ?? '',
          start_date: startDate,
          end_date: endDate,
        }),
      })
      const scanRaw = await scanResponse.text()
      let scanPayload: ScanApiPayload = {}
      if (scanRaw.trim().startsWith('{')) {
        try {
          scanPayload = JSON.parse(scanRaw) as ScanApiPayload
        } catch {
          scanPayload = {}
        }
      }
      if (!scanResponse.ok) {
        throw new Error(scanPayload.detail || `Scan failed (${scanResponse.status})`)
      }

      setScanStatusText('Step 3/4: Reading scan output...')

      const appRowsRaw = Array.isArray(scanPayload.application_rows) ? scanPayload.application_rows : []
      const msgRowsRaw = Array.isArray(scanPayload.message_rows) ? scanPayload.message_rows : []

      const applicationRowsFromApi: ApplicationRow[] = appRowsRaw.map((r) => ({
        company: r.company || r.application_id || '-',
        position: r.position || '',
        applicationDate: r.application_date || '',
        currentStatus: normalizeStatus(r.current_status || ''),
        evidenceSubject: r.evidence_subject || '',
      }))
      const messageRowsFromApi: MessageRow[] = msgRowsRaw.map((r) => ({
        date: r.date || '',
        company: r.company || '',
        eventType: r.event_type || '',
        subject: r.subject || '',
      }))

      const { timeToOfferDays, timeSpentDays } = computeTiming(msgRowsRaw)
      const summaryJson = scanPayload.summary || {}
      const summaryFromApi: Summary = {
        applications: Number(summaryJson.applications ?? applicationRowsFromApi.length ?? 0),
        interviews: Number(summaryJson.interviews ?? 0),
        rejections: Number(summaryJson.rejections_total ?? 0),
        offers: Number(summaryJson.offers ?? 0),
        noResponse: Number(summaryJson.no_response ?? 0),
        timeToOfferDays,
        timeSpentDays,
      }

      setScanStatusText('Step 4/4: Preparing dashboard...')
      await new Promise((resolve) => setTimeout(resolve, 300))

      setSummary(summaryFromApi)
      setApplicationRows(applicationRowsFromApi)
      setMessageRows(messageRowsFromApi)
      setSankeyImageSrc(envSankeyImageSrc ?? scanPayload.sankey_image_data_url ?? '')
      setHasRunResults(true)
      setScanStatusTone('success')
      setScanStatusText(`Run complete (${startDate} to ${endDate}).`)
    } catch (error) {
      setHasRunResults(false)
      setSummary(EMPTY_SUMMARY)
      setApplicationRows([])
      setMessageRows([])
      setSankeyImageSrc(envSankeyImageSrc ?? '')
      setScanStatusTone('error')
      setScanStatusText(error instanceof Error ? error.message : 'Run failed while loading results.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-slate-50 px-4 py-10 font-sans sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8">
          <div className="mt-1 flex items-center gap-3">
            <img src="/offertracker-icon-transparent.png" alt="OfferTracker logo" className="h-9 w-9 object-contain" />
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">OfferTracker</h1>
          </div>
          <p className="mt-2 text-sm text-slate-500">Connect Gmail or Outlook, scan a date range, and review your job search results.</p>
        </header>

        <div className="space-y-6">
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">Connect Email Provider</h2>
            <p className="mt-1 text-sm text-slate-500">
              Mail access is read-only. OfferTracker does not store your raw email content.
            </p>

            <p className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-500">Step 1. Choose provider</p>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => onSelectProvider('gmail')}
                disabled={isConnecting}
                className={`rounded-lg border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                  selectedProvider === 'gmail'
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                    : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                <p className="text-sm font-semibold">Gmail</p>
                <p className="mt-1 text-xs">Use Google OAuth read-only access.</p>
              </button>
              <button
                type="button"
                onClick={() => onSelectProvider('outlook')}
                disabled={isConnecting}
                className={`rounded-lg border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                  selectedProvider === 'outlook'
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                    : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                <p className="text-sm font-semibold">Outlook</p>
                <p className="mt-1 text-xs">Use Microsoft OAuth read-only access.</p>
              </button>
            </div>
            <p className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-500">Step 2. Connect selected provider</p>
            <div className="mt-2">
              <button
                type="button"
                onClick={onConnect}
                disabled={isConnecting}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isConnecting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {isConnecting ? `Connecting ${providerLabel(selectedProvider)}...` : `Connect ${providerLabel(selectedProvider)}`}
              </button>
            </div>

            <div className="mt-4">
              <span
                className={`inline-flex max-w-full items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${
                  isActiveConnection ? 'bg-emerald-50 text-emerald-700' : 'bg-blue-50 text-blue-700'
                }`}
              >
                {isCheckingAuth || isConnecting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : isActiveConnection ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <AlertCircle className="h-3.5 w-3.5" />
                )}
                {connectionStatusText}
              </span>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">Scan and Rerun</h2>
            <p className="mt-1 text-sm text-slate-500">Select your timeframe and run the scan.</p>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block min-w-0 text-sm text-slate-600">
                Start Date
                <span className="relative mt-1 block">
                  <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type="date"
                    value={startDate}
                    onChange={(event) => setStartDate(event.target.value)}
                    max={todayIso}
                    className="min-w-0 w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-left text-sm text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                  />
                </span>
              </label>
              <label className="block min-w-0 text-sm text-slate-600">
                End Date
                <span className="relative mt-1 block">
                  <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type="date"
                    value={endDate}
                    onChange={(event) => setEndDate(event.target.value)}
                    max={todayIso}
                    className="min-w-0 w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-left text-sm text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                  />
                </span>
              </label>
            </div>

            <div className="mt-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={onRun}
                disabled={!canRun}
                className="inline-flex w-full items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {runButtonText}
              </button>
              <span
                className={`inline-flex max-w-full items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${
                  scanStatusTone === 'success'
                    ? 'bg-emerald-50 text-emerald-700'
                    : scanStatusTone === 'error'
                      ? 'bg-red-50 text-red-700'
                      : scanStatusTone === 'running'
                        ? 'bg-blue-50 text-blue-700'
                        : 'bg-slate-100 text-slate-700'
                }`}
              >
                {scanStatusTone === 'running' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : scanStatusTone === 'success' ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <AlertCircle className="h-3.5 w-3.5" />
                )}
                {scanStatusText}
              </span>
            </div>
          </section>

          <ResultsAndImageSection
            summary={summary}
            applicationRows={applicationRows}
            messageRows={messageRows}
            hasResults={hasRunResults}
            sankeyImageSrc={sankeyImageSrc}
          />
        </div>

        <footer className="mt-10 border-t border-slate-200 pt-5">
          <div className="flex flex-col gap-3 text-slate-600 sm:flex-row sm:items-center sm:justify-between">
            <div className="inline-flex items-center gap-2 text-sm">
              <img src="/offertracker-icon-transparent.png" alt="OfferTracker logo" className="h-5 w-5" />
              <span>© 2026 OfferTracker</span>
            </div>
            <div className="inline-flex flex-wrap items-center gap-4">
              <a
                href="https://github.com/bluebluegrass"
                target="_blank"
                rel="noreferrer"
                aria-label="GitHub"
                className="inline-flex items-center text-slate-600 transition-colors hover:text-slate-900"
              >
                <Github className="h-4 w-4" />
              </a>
              <a href="/privacy" className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900">
                Privacy
              </a>
              <a href="/terms" className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900">
                Terms
              </a>
              <a
                href="mailto:hey.simonalife@gmail.com"
                className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900"
              >
                Contact
              </a>
            </div>
          </div>
        </footer>
      </div>
    </main>
  )
}
