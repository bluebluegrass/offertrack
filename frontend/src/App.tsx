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
  fromEmail: string
}

type CsvRow = Record<string, string>
type MailProvider = 'gmail' | 'outlook'
type DashboardMode = 'empty' | 'demo' | 'real'
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

const DEMO_APPLICATION_ROWS: ApplicationRow[] = [
  {
    company: 'Catawiki',
    position: 'Software Engineer - Data Engineering',
    applicationDate: '2026-02-16',
    currentStatus: 'Applied',
    evidenceSubject: 'Application received for Software Engineer - Data Engineering',
  },
  {
    company: 'Datadog',
    position: 'Senior Data Engineer',
    applicationDate: '2026-03-02',
    currentStatus: 'Applied',
    evidenceSubject: 'Thanks for applying to Datadog',
  },
  {
    company: 'Miro',
    position: 'Analytics Engineer',
    applicationDate: '2026-02-28',
    currentStatus: 'Rejected',
    evidenceSubject: 'Update on your application at Miro',
  },
  {
    company: 'Stripe',
    position: 'Data Platform Engineer',
    applicationDate: '2026-03-05',
    currentStatus: 'Applied',
    evidenceSubject: 'Application received for Data Platform Engineer',
  },
  {
    company: 'Notion',
    position: 'Business Intelligence Engineer',
    applicationDate: '2026-03-01',
    currentStatus: 'Applied',
    evidenceSubject: 'Thank you for applying to Notion',
  },
  {
    company: 'Teal',
    position: 'Data Analyst',
    applicationDate: '2026-02-20',
    currentStatus: 'Rejected',
    evidenceSubject: 'Update regarding your application',
  },
]

const DEMO_MESSAGE_ROWS: MessageRow[] = [
  {
    date: '2026-02-16',
    company: 'Catawiki',
    eventType: 'application',
    subject: 'Application received for Software Engineer - Data Engineering',
    fromEmail: 'noreply@catawiki.com',
  },
  {
    date: '2026-03-02',
    company: 'Datadog',
    eventType: 'application',
    subject: 'Thanks for applying to Datadog',
    fromEmail: 'candidate@datadoghq.com',
  },
  {
    date: '2026-02-28',
    company: 'Miro',
    eventType: 'application',
    subject: 'Application received',
    fromEmail: 'noreply@miro.com',
  },
  {
    date: '2026-03-04',
    company: 'Miro',
    eventType: 'rejection',
    subject: 'Update on your application at Miro',
    fromEmail: 'noreply@miro.com',
  },
  {
    date: '2026-03-05',
    company: 'Stripe',
    eventType: 'application',
    subject: 'Application received for Data Platform Engineer',
    fromEmail: 'no-reply@jobs.lever.co',
  },
  {
    date: '2026-03-01',
    company: 'Notion',
    eventType: 'application',
    subject: 'Thank you for applying to Notion',
    fromEmail: 'notifications@ashbyhq.com',
  },
  {
    date: '2026-02-20',
    company: 'Teal',
    eventType: 'application',
    subject: 'Application received',
    fromEmail: 'hello@tealhq.com',
  },
  {
    date: '2026-02-25',
    company: 'Teal',
    eventType: 'rejection',
    subject: 'Update regarding your application',
    fromEmail: 'hello@tealhq.com',
  },
]

const DEMO_SUMMARY: Summary = {
  applications: 6,
  interviews: 0,
  rejections: 2,
  offers: 0,
  noResponse: 4,
  timeToOfferDays: null,
  timeSpentDays: 25,
}
const DEMO_SANKEY_IMAGE_SRC = '/demo-sankey.png'

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

function compareApplicationRows(a: ApplicationRow, b: ApplicationRow): number {
  const statusRank: Record<Status, number> = {
    Offer: 0,
    Interviewing: 1,
    Applied: 2,
    Rejected: 3,
  }

  const rankDiff = statusRank[a.currentStatus] - statusRank[b.currentStatus]
  if (rankDiff !== 0) return rankDiff

  const aDate = a.applicationDate ? new Date(a.applicationDate).getTime() : 0
  const bDate = b.applicationDate ? new Date(b.applicationDate).getTime() : 0
  if (aDate !== bDate) return bDate - aDate

  return a.company.localeCompare(b.company)
}

function sortApplicationRows(rows: ApplicationRow[]): ApplicationRow[] {
  return [...rows].sort(compareApplicationRows)
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

    const applicationRows = sortApplicationRows(appRowsCsv.map((r) => ({
      company: r.company || r.application_id || '-',
      position: r.position || '',
      applicationDate: r.application_date || '',
      currentStatus: normalizeStatus(r.current_status || ''),
      evidenceSubject: r.evidence_subject || '',
    })))

    const messageRows: MessageRow[] = messageRowsCsv.map((r) => ({
      date: r.date || '',
      company: r.company || '',
      eventType: r.event_type || '',
      subject: r.subject || '',
      fromEmail: r.from_email || r.from_email_address || '',
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
  const [dashboardMode, setDashboardMode] = useState<DashboardMode>('empty')
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
  const [scanStatusText, setScanStatusText] = useState('Connect an inbox or view demo data to get started.')
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

  const enterDemoMode = () => {
    setDashboardMode('demo')
    setSummary(DEMO_SUMMARY)
    setApplicationRows(sortApplicationRows(DEMO_APPLICATION_ROWS))
    setMessageRows(DEMO_MESSAGE_ROWS)
    setSankeyImageSrc(envSankeyImageSrc ?? DEMO_SANKEY_IMAGE_SRC)
    setHasRunResults(true)
    setScanStatusTone('idle')
    setScanStatusText('Showing sample data. Connect an inbox and run a scan to replace it.')
  }

  const exitDemoMode = () => {
    setDashboardMode('empty')
    setSummary(EMPTY_SUMMARY)
    setApplicationRows([])
    setMessageRows([])
    setSankeyImageSrc(envSankeyImageSrc ?? '')
    setHasRunResults(false)
    setScanStatusTone('idle')
    setScanStatusText('Connect an inbox or view demo data to get started.')
  }

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

      const applicationRowsFromApi = sortApplicationRows(appRowsRaw.map((r) => ({
        company: r.company || r.application_id || '-',
        position: r.position || '',
        applicationDate: r.application_date || '',
        currentStatus: normalizeStatus(r.current_status || ''),
        evidenceSubject: r.evidence_subject || '',
      })))
      const messageRowsFromApi: MessageRow[] = msgRowsRaw.map((r) => ({
        date: r.date || '',
        company: r.company || '',
        eventType: r.event_type || '',
        subject: r.subject || '',
        fromEmail: r.from_email || r.from_email_address || '',
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
      setDashboardMode('real')
      setScanStatusTone('success')
      setScanStatusText(`Run complete (${startDate} to ${endDate}).`)
    } catch (error) {
      setDashboardMode('empty')
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
    <main className="min-h-screen overflow-x-hidden px-4 py-6 font-sans sm:px-6 sm:py-10 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 sm:mb-8">
          <div className="mt-1 flex items-center gap-3">
            <img src="/offertracker-icon-transparent.png" alt="OfferTracker logo" className="h-9 w-9 flex-none object-contain sm:h-10 sm:w-10" />
            <h1 className="warm-title text-2xl font-semibold tracking-tight sm:text-3xl">
              Offer<span className="warm-brand">Tracker</span>
            </h1>
          </div>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="warm-copy max-w-2xl text-sm leading-6 sm:text-base">
              Connect Gmail or Outlook, scan a date range, and review your job search results.
            </p>
            <button
              type="button"
              onClick={enterDemoMode}
              className="warm-pill inline-flex rounded-full px-3 py-1.5 text-xs font-medium text-[color:var(--accent-strong)]"
            >
              View Demo
            </button>
          </div>
        </header>

        <div className="space-y-6">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <section className="warm-panel rounded-xl border p-4 sm:p-5">
            <h2 className="warm-title text-lg font-semibold tracking-tight">Connect Email Provider</h2>
            <p className="warm-copy mt-1 text-sm">
              Mail access is read-only. OfferTracker does not store your raw email content.
            </p>

            <p className="warm-kicker mt-4 text-xs font-medium uppercase tracking-wide">Step 1. Choose provider</p>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => onSelectProvider('gmail')}
                disabled={isConnecting}
                className={`min-h-[92px] rounded-xl border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                  selectedProvider === 'gmail'
                    ? 'warm-panel-soft border-[color:var(--border-strong)] text-[color:var(--accent-strong)]'
                    : 'border-[color:var(--border)] bg-white/80 text-[color:var(--text-body)] hover:bg-[color:var(--accent-soft)]/40'
                }`}
              >
                <p className="text-sm font-semibold">Gmail</p>
                <p className="mt-1 text-xs">Use Google OAuth read-only access.</p>
              </button>
              <button
                type="button"
                onClick={() => onSelectProvider('outlook')}
                disabled={isConnecting}
                className={`min-h-[92px] rounded-xl border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                  selectedProvider === 'outlook'
                    ? 'warm-panel-soft border-[color:var(--border-strong)] text-[color:var(--accent-strong)]'
                    : 'border-[color:var(--border)] bg-white/80 text-[color:var(--text-body)] hover:bg-[color:var(--accent-soft)]/40'
                }`}
              >
                <p className="text-sm font-semibold">Outlook</p>
                <p className="mt-1 text-xs">Use Microsoft OAuth read-only access.</p>
              </button>
            </div>
            <p className="warm-kicker mt-4 text-xs font-medium uppercase tracking-wide">Step 2. Connect selected provider</p>
            <div className="mt-2">
              <button
                type="button"
                onClick={onConnect}
                disabled={isConnecting}
                className="warm-button inline-flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                {isConnecting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {isConnecting ? `Connecting ${providerLabel(selectedProvider)}...` : `Connect ${providerLabel(selectedProvider)}`}
              </button>
            </div>

            <div className="mt-4">
              <span
                className={`inline-flex max-w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium leading-5 ${
                  isActiveConnection ? 'warm-pill-success' : 'warm-pill-info'
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

          <section className="warm-panel rounded-xl border p-4 sm:p-5">
            <h2 className="warm-title text-lg font-semibold tracking-tight">Scan and Rerun</h2>
            <p className="warm-copy mt-1 text-sm">Select your timeframe and run the scan.</p>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="warm-copy block min-w-0 text-sm">
                Start Date
                <span className="relative mt-1 block">
                  <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--text-muted)]" />
                  <input
                    type="date"
                    value={startDate}
                    onChange={(event) => setStartDate(event.target.value)}
                    max={todayIso}
                    className="date-input-mobile warm-input min-w-0 w-full max-w-full rounded-xl border py-3 pl-9 pr-3 text-left text-base outline-none transition sm:text-sm"
                  />
                </span>
              </label>
              <label className="warm-copy block min-w-0 text-sm">
                End Date
                <span className="relative mt-1 block">
                  <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--text-muted)]" />
                  <input
                    type="date"
                    value={endDate}
                    onChange={(event) => setEndDate(event.target.value)}
                    max={todayIso}
                    className="date-input-mobile warm-input min-w-0 w-full max-w-full rounded-xl border py-3 pl-9 pr-3 text-left text-base outline-none transition sm:text-sm"
                  />
                </span>
              </label>
            </div>

            <div className="mt-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={onRun}
                disabled={!canRun}
                className="warm-button inline-flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {runButtonText}
              </button>
              <span
                className={`inline-flex max-w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium leading-5 ${
                  scanStatusTone === 'success'
                    ? 'warm-pill-success'
                    : scanStatusTone === 'error'
                      ? 'warm-pill-error'
                      : scanStatusTone === 'running'
                        ? 'warm-pill'
                        : 'warm-pill-neutral'
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
          </div>

          {!hasRunResults ? (
            <section className="warm-empty rounded-xl border-2 border-dashed p-8 text-center sm:p-10">
              <p className="warm-title text-xl font-semibold tracking-tight sm:text-2xl">
                Connect your inbox to see your real job search pipeline.
              </p>
              <p className="warm-copy mx-auto mt-3 max-w-2xl text-sm leading-7 sm:text-base">
                OfferTracker scans job-related emails, builds your funnel, and shows the next step for each application.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-3">
                <button
                  type="button"
                  onClick={onConnect}
                  disabled={isConnecting}
                  className="warm-button inline-flex min-h-[48px] items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isConnecting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {isConnecting ? `Connecting ${providerLabel(selectedProvider)}...` : `Connect ${providerLabel(selectedProvider)}`}
                </button>
                <button
                  type="button"
                  onClick={enterDemoMode}
                  className="warm-pill inline-flex min-h-[48px] items-center justify-center rounded-xl px-4 py-3 text-sm font-medium text-[color:var(--accent-strong)]"
                >
                  View Demo
                </button>
              </div>
            </section>
          ) : (
            <ResultsAndImageSection
              summary={summary}
              applicationRows={applicationRows}
              messageRows={messageRows}
              hasResults={hasRunResults}
              sankeyImageSrc={sankeyImageSrc}
              isDemoMode={dashboardMode === 'demo'}
              onExitDemoMode={dashboardMode === 'demo' ? exitDemoMode : undefined}
            />
          )}
        </div>

        <footer className="warm-divider mt-10 border-t pt-5">
          <div className="warm-copy flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
                className="warm-link inline-flex items-center transition-colors"
              >
                <Github className="h-4 w-4" />
              </a>
              <a href="/privacy" className="warm-link text-sm font-medium transition-colors">
                Privacy
              </a>
              <a href="/terms" className="warm-link text-sm font-medium transition-colors">
                Terms
              </a>
              <a
                href="mailto:hey.simonalife@gmail.com"
                className="warm-link text-sm font-medium transition-colors"
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
