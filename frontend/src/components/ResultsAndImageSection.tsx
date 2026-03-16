import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

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

type Props = {
  summary: Summary
  applicationRows: ApplicationRow[]
  messageRows: MessageRow[]
  hasResults: boolean
  sankeyImageSrc: string
  isDemoMode?: boolean
  onExitDemoMode?: () => void
}

type RowAction = {
  label: string
  tone: 'primary' | 'secondary' | 'muted'
}

type FollowUpDraft = {
  company: string
  position: string
  ageDays: number
  subject: string
  body: string
}

type ContactTask = {
  company: string
  position: string
  ageDays: number
  label: string
  hint: string
}

type SenderRoute = 'reply' | 'noreply' | 'ats' | 'unknown'

type ApplicationDetailData = {
  sender: string
  senderRoute: SenderRoute
  ageDays: number | null
  actions: RowAction[]
  followUpDraft: FollowUpDraft | null
  contactTask: ContactTask | null
  companyDomain: string
}

const statusPillClass: Record<Status, string> = {
  Applied: 'warm-pill-info',
  Interviewing: 'warm-pill',
  Rejected: 'warm-pill-error',
  Offer: 'warm-pill-success',
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="warm-panel rounded-xl border p-4 sm:p-5">
      <p className="warm-kicker text-xs font-medium uppercase tracking-wide">{label}</p>
      <p className="warm-title mt-2 text-2xl font-semibold tracking-tight sm:text-[1.75rem]">{value}</p>
    </div>
  )
}

function MobileMessageCard({ row }: { row: MessageRow }) {
  return (
    <article className="warm-panel rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Company</p>
          <p className="warm-title mt-1 break-words text-sm font-semibold">{row.company || '-'}</p>
        </div>
        <div className="warm-pill-neutral rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide">
          {row.eventType || 'other'}
        </div>
      </div>
      <div className="mt-4 space-y-3">
        <div>
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Date</p>
          <p className="warm-copy mt-1 break-words text-sm">{row.date || '-'}</p>
        </div>
        <div>
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Subject</p>
          <p className="warm-copy mt-1 break-words text-sm leading-6">{row.subject || '-'}</p>
        </div>
        <div>
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">From</p>
          <p className="warm-copy mt-1 break-all text-sm leading-6">{row.fromEmail || '-'}</p>
        </div>
      </div>
    </article>
  )
}

function MobileApplicationCard({
  row,
  actions,
  detail,
}: {
  row: ApplicationRow
  actions: RowAction[]
  detail: ApplicationDetailData
}) {
  const [open, setOpen] = useState(false)

  return (
    <article className="warm-panel rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Company</p>
          <p className="warm-title mt-1 break-words text-sm font-semibold">{row.company || '-'}</p>
          {row.position ? <p className="warm-copy mt-1 break-words text-sm">{row.position}</p> : null}
        </div>
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusPillClass[row.currentStatus]}`}>
          {row.currentStatus}
        </span>
      </div>
      <div className="mt-4 space-y-3">
        <div>
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Application Date</p>
          <p className="warm-copy mt-1 text-sm">{row.applicationDate || '-'}</p>
        </div>
        <div>
          <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Evidence Subject</p>
          <p className="warm-copy mt-1 break-words text-sm leading-6">{row.evidenceSubject || '-'}</p>
        </div>
        {actions.length > 0 ? (
          <div>
            <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Next Action</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {actions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    action.tone === 'primary'
                      ? 'warm-button text-white'
                      : action.tone === 'secondary'
                        ? 'warm-pill text-[color:var(--accent-strong)]'
                        : 'warm-pill-neutral'
                  }`}
                >
                  {action.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              className="warm-copy mt-3 inline-flex items-center gap-1 text-sm font-medium"
            >
              {open ? 'Hide details' : 'Show details'}
              {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        ) : null}
        {open ? (
          <div className="warm-divider border-t pt-3">
            <ApplicationDetailCard row={row} detail={detail} />
          </div>
        ) : null}
      </div>
    </article>
  )
}

function daysSince(dateLike: string): number | null {
  if (!dateLike) return null
  const date = new Date(dateLike)
  if (Number.isNaN(date.getTime())) return null
  return Math.max(Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60 * 24)), 0)
}

function classifySenderRoute(fromEmail: string): SenderRoute {
  const normalized = fromEmail.trim().toLowerCase()
  if (!normalized) return 'unknown'

  const localPart = normalized.split('@')[0] || ''
  const domain = normalized.split('@')[1] || ''

  if (
    /(^|[._-])(no ?reply|noreply|do ?not ?reply|donotreply|system|notifications?)($|[._-])/.test(localPart) ||
    localPart === 'system'
  ) {
    return 'noreply'
  }

  if (
    [
      'ashbyhq.com',
      'greenhouse.io',
      'lever.co',
      'smartrecruiters.com',
      'myworkday.com',
      'workday.com',
      'jobvite.com',
      'icims.com',
      'taleo.net',
      'successfactors.com',
    ].some((part) => domain === part || domain.endsWith(`.${part}`))
  ) {
    return 'ats'
  }

  return 'reply'
}

function buildLatestMessageByCompany(messageRows: MessageRow[]): Map<string, MessageRow> {
  const latestByCompany = new Map<string, MessageRow>()
  for (const row of messageRows) {
    if (!row.company || !row.date) continue
    const existing = latestByCompany.get(row.company)
    if (!existing || new Date(row.date).getTime() > new Date(existing.date).getTime()) {
      latestByCompany.set(row.company, row)
    }
  }
  return latestByCompany
}

function buildLastActivityByCompany(messageRows: MessageRow[]): Map<string, string> {
  const lastActivityByCompany = new Map<string, string>()
  for (const row of messageRows) {
    if (!row.company || !row.date) continue
    const existing = lastActivityByCompany.get(row.company)
    if (!existing || new Date(row.date).getTime() > new Date(existing).getTime()) {
      lastActivityByCompany.set(row.company, row.date)
    }
  }
  return lastActivityByCompany
}

function extractCompanyDomain(fromEmail: string): string {
  const normalized = fromEmail.trim().toLowerCase()
  const domain = normalized.split('@')[1] || ''
  if (!domain) return ''

  const blockedDomains = [
    'ashbyhq.com',
    'greenhouse.io',
    'lever.co',
    'smartrecruiters.com',
    'myworkday.com',
    'workday.com',
    'jobvite.com',
    'icims.com',
    'taleo.net',
    'successfactors.com',
  ]
  if (blockedDomains.some((part) => domain === part || domain.endsWith(`.${part}`))) {
    return ''
  }
  return domain
}

function buildSearchUrl(query: string): string {
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`
}

function buildLinkedInPeopleSearchQuery(company: string, titleHint: string): string {
  return `site:linkedin.com/in ${titleHint} "${company}"`
}

function getRowActions(row: ApplicationRow, latestMessageByCompany: Map<string, MessageRow>): RowAction[] {
  const senderRoute = classifySenderRoute(latestMessageByCompany.get(row.company)?.fromEmail || '')

  if (row.currentStatus === 'Interviewing') {
    return [
      { label: 'Build Prep', tone: 'primary' },
      { label: senderRoute === 'reply' ? 'Check In' : 'Find Recruiter', tone: 'secondary' },
    ]
  }
  if (row.currentStatus === 'Applied') {
    if (senderRoute === 'reply') {
      return [
        { label: 'Draft Follow-Up', tone: 'primary' },
        { label: 'Mark Cold', tone: 'muted' },
      ]
    }
    if (senderRoute === 'ats') {
      return [
        { label: 'Check ATS', tone: 'secondary' },
        { label: 'Find Recruiter', tone: 'muted' },
      ]
    }
    return [
      { label: 'Find Contact', tone: 'secondary' },
      { label: 'Mark Cold', tone: 'muted' },
    ]
  }
  if (row.currentStatus === 'Rejected') {
    return [{ label: 'Archive', tone: 'muted' }]
  }
  if (row.currentStatus === 'Offer') {
    return [{ label: 'View Notes', tone: 'secondary' }]
  }
  return []
}

function buildFollowUpDrafts(applicationRows: ApplicationRow[], messageRows: MessageRow[]): FollowUpDraft[] {
  const lastActivityByCompany = buildLastActivityByCompany(messageRows)
  const latestMessageByCompany = buildLatestMessageByCompany(messageRows)

  return applicationRows
    .filter((row) => row.currentStatus === 'Applied')
    .filter((row) => classifySenderRoute(latestMessageByCompany.get(row.company)?.fromEmail || '') === 'reply')
    .map((row) => {
      const referenceDate = lastActivityByCompany.get(row.company) || row.applicationDate
      const ageDays = daysSince(referenceDate) ?? 0
      return {
        company: row.company,
        position: row.position,
        ageDays,
        subject: `Follow-up on ${row.position || 'my application'} at ${row.company}`,
        body: [
          `Hi ${row.company} team,`,
          '',
          `I wanted to follow up on my application for the ${row.position || 'role'} position.`,
          'I remain very interested in the opportunity and would be glad to share any additional information if helpful.',
          '',
          'Please let me know if there is any update on the process.',
          '',
          'Best,',
          '[Your Name]',
        ].join('\n'),
      }
    })
    .filter((draft) => draft.ageDays >= 7)
    .sort((a, b) => b.ageDays - a.ageDays)
}

function buildContactTasks(applicationRows: ApplicationRow[], messageRows: MessageRow[]): ContactTask[] {
  const lastActivityByCompany = buildLastActivityByCompany(messageRows)
  const latestMessageByCompany = buildLatestMessageByCompany(messageRows)

  return applicationRows
    .filter((row) => row.currentStatus === 'Applied')
    .map((row) => {
      const referenceDate = lastActivityByCompany.get(row.company) || row.applicationDate
      const ageDays = daysSince(referenceDate) ?? 0
      const senderRoute = classifySenderRoute(latestMessageByCompany.get(row.company)?.fromEmail || '')
      if (ageDays < 7 || senderRoute === 'reply') return null

      return {
        company: row.company,
        position: row.position,
        ageDays,
        label: senderRoute === 'ats' ? 'Check ATS or find recruiter' : 'Find a better contact',
        hint:
          senderRoute === 'ats'
            ? 'This email came from an applicant tracking system. Check the portal first, then look for a recruiter or hiring manager.'
            : 'This email came from a no-reply or system mailbox. Replying is unlikely to reach a person.',
      }
    })
    .filter((task): task is ContactTask => task !== null)
    .sort((a, b) => b.ageDays - a.ageDays)
}

function buildApplicationDetailData(
  row: ApplicationRow,
  latestMessageByCompany: Map<string, MessageRow>,
  lastActivityByCompany: Map<string, string>,
  followUpDrafts: FollowUpDraft[],
  contactTasks: ContactTask[],
): ApplicationDetailData {
  const sender = latestMessageByCompany.get(row.company)?.fromEmail || ''
  const senderRoute = classifySenderRoute(sender)
  const referenceDate = lastActivityByCompany.get(row.company) || row.applicationDate
  const ageDays = daysSince(referenceDate)

  return {
    sender,
    senderRoute,
    ageDays,
    actions: getRowActions(row, latestMessageByCompany),
    followUpDraft: followUpDrafts.find((draft) => draft.company === row.company) ?? null,
    contactTask: contactTasks.find((task) => task.company === row.company) ?? null,
    companyDomain: extractCompanyDomain(sender),
  }
}

function ApplicationDetailCard({ row, detail }: { row: ApplicationRow; detail: ApplicationDetailData }) {
  const searchLinks = [
    {
      label: 'Recruiters',
      href: buildSearchUrl(buildLinkedInPeopleSearchQuery(row.company, 'recruiter OR "talent acquisition"')),
    },
    {
      label: 'Hiring Managers',
      href: buildSearchUrl(buildLinkedInPeopleSearchQuery(row.company, `"${row.position}" OR "hiring manager"`)),
    },
    {
      label: 'LinkedIn',
      href: buildSearchUrl(`site:linkedin.com "${row.company}" "${row.position}" recruiter`),
    },
    {
      label: 'Careers Page',
      href: buildSearchUrl(`${row.company} careers ${detail.companyDomain || ''}`.trim()),
    },
  ]

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-soft)]/80 p-4">
        <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Action Lane</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {detail.actions.map((action) => (
            <button
              key={action.label}
              type="button"
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                action.tone === 'primary'
                  ? 'warm-button text-white'
                  : action.tone === 'secondary'
                    ? 'warm-pill text-[color:var(--accent-strong)]'
                    : 'warm-pill-neutral'
              }`}
            >
              {action.label}
            </button>
          ))}
        </div>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="warm-kicker text-xs font-medium uppercase tracking-wide">Latest Sender</dt>
            <dd className="warm-copy mt-1 break-all">{detail.sender || 'No sender captured'}</dd>
          </div>
          <div>
            <dt className="warm-kicker text-xs font-medium uppercase tracking-wide">Contact Route</dt>
            <dd className="warm-copy mt-1">
              {detail.senderRoute === 'reply'
                ? 'Direct reply is possible'
                : detail.senderRoute === 'ats'
                  ? 'Use portal or recruiter search'
                  : detail.senderRoute === 'noreply'
                    ? 'Find a real person instead'
                    : 'Contact path unclear'}
            </dd>
          </div>
          <div>
            <dt className="warm-kicker text-xs font-medium uppercase tracking-wide">Quiet Period</dt>
            <dd className="warm-copy mt-1">{detail.ageDays === null ? 'Unknown' : `${detail.ageDays} days since last visible activity`}</dd>
          </div>
          <div>
            <dt className="warm-kicker text-xs font-medium uppercase tracking-wide">Search Shortcuts</dt>
            <dd className="mt-2 flex flex-wrap gap-2">
              {searchLinks.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="warm-pill inline-flex rounded-full px-3 py-1.5 text-xs font-medium text-[color:var(--accent-strong)]"
                >
                  {link.label}
                </a>
              ))}
            </dd>
          </div>
        </dl>
      </div>

      <div className="rounded-2xl border border-[color:var(--border)] bg-white/70 p-4">
        {detail.followUpDraft ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Email Draft</p>
              <span className="warm-pill-info rounded-full px-2.5 py-1 text-xs font-medium">Ready to copy</span>
            </div>
            <p className="warm-copy mt-3 text-sm font-medium">{detail.followUpDraft.subject}</p>
            <pre className="warm-copy mt-3 whitespace-pre-wrap rounded-xl bg-[color:var(--surface-soft)]/75 p-4 text-sm leading-6">
              {detail.followUpDraft.body}
            </pre>
          </>
        ) : detail.contactTask ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Manual Route</p>
              <span className="warm-pill-neutral rounded-full px-2.5 py-1 text-xs font-medium">No direct reply</span>
            </div>
            <p className="warm-title mt-3 text-base font-semibold">{detail.contactTask.label}</p>
            <p className="warm-copy mt-2 text-sm leading-6">{detail.contactTask.hint}</p>
          </>
        ) : (
          <>
            <p className="warm-kicker text-xs font-medium uppercase tracking-wide">Next Step</p>
            <p className="warm-copy mt-3 text-sm leading-6">
              {row.currentStatus === 'Rejected'
                ? 'This application is closed. Archive it or keep it for pattern review.'
                : row.currentStatus === 'Interviewing'
                  ? 'Use this space for interview prep, thank-you notes, or recruiter check-ins.'
                  : row.currentStatus === 'Offer'
                    ? 'Use this space to compare terms, notes, and negotiation follow-up.'
                    : 'No draft is available yet, but the sender and status signals are captured here.'}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export default function ResultsAndImageSection({
  summary,
  applicationRows,
  messageRows,
  hasResults,
  sankeyImageSrc,
  isDemoMode = false,
  onExitDemoMode,
}: Props) {
  const [open, setOpen] = useState(false)
  const [imageMissing, setImageMissing] = useState(false)
  const [expandedApplicationKey, setExpandedApplicationKey] = useState<string | null>(null)
  const followUpDrafts = buildFollowUpDrafts(applicationRows, messageRows)
  const contactTasks = buildContactTasks(applicationRows, messageRows)
  const latestMessageByCompany = buildLatestMessageByCompany(messageRows)
  const lastActivityByCompany = buildLastActivityByCompany(messageRows)

  useEffect(() => {
    setImageMissing(false)
  }, [sankeyImageSrc])

  return (
    <div className="space-y-6">
      <section>
        <h2 className="warm-title mb-3 text-lg font-semibold tracking-tight sm:text-xl">Your Journey</h2>
        <div className="transition-all duration-200">
          {!hasResults ? (
            <div className="warm-empty flex min-h-56 flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center sm:p-10">
              <p className="text-2xl leading-none">💪</p>
              <p className="warm-copy mt-3 text-base font-medium">Hang in there</p>
            </div>
          ) : (
            <div className="space-y-4">
              {isDemoMode ? (
                <div className="warm-panel-soft rounded-xl border px-4 py-3 sm:px-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="warm-kicker text-[11px] font-medium uppercase tracking-[0.18em]">Demo Mode</p>
                      <p className="warm-copy mt-1 text-sm">
                        Showing sample data until you connect an inbox and run your first scan.
                      </p>
                    </div>
                    {onExitDemoMode ? (
                      <button
                        type="button"
                        onClick={onExitDemoMode}
                        className="warm-pill inline-flex rounded-full px-3 py-1.5 text-xs font-medium text-[color:var(--accent-strong)]"
                      >
                        Connect Inbox
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <StatCard label="Applications" value={summary.applications} />
                <StatCard label="Interviews" value={summary.interviews} />
                <StatCard label="Rejections" value={summary.rejections} />
                <StatCard label="Offers" value={summary.offers} />
                <StatCard label="No Response" value={summary.noResponse} />
              </div>

              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <StatCard
                  label="Time to Offer"
                  value={summary.timeToOfferDays === null ? 'No offer yet' : `${summary.timeToOfferDays} days`}
                />
                <StatCard
                  label="Time Spent"
                  value={summary.timeSpentDays === null ? '-' : `${summary.timeSpentDays} days`}
                />
              </div>

              {sankeyImageSrc ? (
                <div className="warm-panel overflow-hidden rounded-xl border">
                  <div className="warm-divider border-b px-4 py-3 sm:px-5">
                    <h3 className="warm-copy flex items-center gap-2 text-sm font-medium">
                      <img src="/offertracker-icon-transparent.png" alt="" className="h-4 w-4" />
                      OfferTracker Image
                    </h3>
                  </div>
                  <div className="p-3 sm:p-4">
                    {!imageMissing ? (
                      <img
                        src={sankeyImageSrc}
                        alt="OfferTracker Sankey"
                        className="w-full rounded-md border border-slate-100"
                        loading="lazy"
                        onError={() => setImageMissing(true)}
                      />
                    ) : (
                      <p className="warm-copy text-sm">
                        Image not found at <code className="warm-pill-neutral rounded px-1 py-0.5">{sankeyImageSrc}</code>
                      </p>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>

      <section>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="warm-panel warm-copy flex min-h-[48px] w-full items-center justify-between rounded-xl border px-4 py-3 text-left text-sm font-medium transition hover:bg-[color:var(--accent-soft)]/35"
        >
          <span>Message Classifications</span>
          {open ? <ChevronUp className="warm-muted h-4 w-4" /> : <ChevronDown className="warm-muted h-4 w-4" />}
        </button>
        {open ? (
          <div className="mt-2 space-y-3">
            <div className="space-y-3 md:hidden">
              {messageRows.map((row, idx) => (
                <MobileMessageCard key={`${row.date}-${idx}`} row={row} />
              ))}
            </div>
            <div className="warm-panel hidden overflow-hidden rounded-xl border md:block">
              <table className="w-full table-fixed text-left text-sm">
              <thead className="warm-table-head">
                <tr>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Event Type</th>
                  <th className="px-4 py-3 font-medium">From</th>
                  <th className="px-4 py-3 font-medium">Subject</th>
                </tr>
              </thead>
              <tbody>
                {messageRows.map((row, idx) => (
                  <tr key={`${row.date}-${idx}`} className="warm-divider border-t transition-colors hover:bg-[color:var(--accent-soft)]/18">
                    <td className="warm-copy px-4 py-3 align-top">{row.date}</td>
                    <td className="warm-title px-4 py-3 align-top">{row.company}</td>
                    <td className="warm-copy px-4 py-3 align-top">{row.eventType}</td>
                    <td className="warm-copy max-w-[240px] truncate px-4 py-3 align-top">{row.fromEmail || '-'}</td>
                    <td className="warm-muted max-w-[420px] truncate px-4 py-3 align-top">{row.subject}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        ) : null}
      </section>

      {hasResults ? (
        <section>
          <div className="mb-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="warm-copy text-sm font-medium">Private: Application Details</h3>
            <span className="warm-muted text-xs">Place this lower on page for safer screenshots</span>
          </div>
          <div className="space-y-3">
            <div className="space-y-3 md:hidden">
              {applicationRows.map((row, index) => {
                const detail = buildApplicationDetailData(
                  row,
                  latestMessageByCompany,
                  lastActivityByCompany,
                  followUpDrafts,
                  contactTasks,
                )

                return (
                <MobileApplicationCard
                  key={`${row.company}-${index}`}
                  row={row}
                  actions={detail.actions}
                  detail={detail}
                />
                )
              })}
            </div>
            <div className="warm-panel hidden overflow-hidden rounded-xl border md:block">
              <div className="overflow-x-auto">
                <table className="w-full table-fixed text-left text-sm">
                <thead className="warm-table-head">
                  <tr>
                    <th className="px-4 py-3 font-medium">Company</th>
                    <th className="px-4 py-3 font-medium">Position</th>
                    <th className="px-4 py-3 font-medium">Date</th>
                    <th className="px-4 py-3 font-medium">Current Status</th>
                    <th className="px-4 py-3 font-medium">Details</th>
                    <th className="px-4 py-3 font-medium">Evidence Subject</th>
                  </tr>
                </thead>
                <tbody>
                  {applicationRows.map((row, index) => {
                    const rowKey = `${row.company}-${index}`
                    const detail = buildApplicationDetailData(
                      row,
                      latestMessageByCompany,
                      lastActivityByCompany,
                      followUpDrafts,
                      contactTasks,
                    )
                    const isExpanded = expandedApplicationKey === rowKey

                    return (
                      <Fragment key={rowKey}>
                        <tr key={rowKey} className="warm-divider border-t transition-colors hover:bg-[color:var(--accent-soft)]/18">
                          <td className="warm-title px-4 py-3 align-top">{row.company}</td>
                          <td className="warm-copy px-4 py-3 align-top">{row.position}</td>
                          <td className="warm-copy px-4 py-3 align-top">{row.applicationDate}</td>
                          <td className="px-4 py-3 align-top">
                            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusPillClass[row.currentStatus]}`}>
                              {row.currentStatus}
                            </span>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <button
                              type="button"
                              onClick={() => setExpandedApplicationKey((current) => (current === rowKey ? null : rowKey))}
                              className="warm-pill inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-[color:var(--accent-strong)]"
                            >
                              {isExpanded ? 'Hide card' : 'Open card'}
                              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            </button>
                          </td>
                          <td className="warm-muted max-w-[320px] truncate px-4 py-3 align-top">{row.evidenceSubject}</td>
                        </tr>
                        {isExpanded ? (
                          <tr className="warm-divider border-t bg-[color:var(--accent-soft)]/12">
                            <td colSpan={6} className="px-4 py-4">
                              <ApplicationDetailCard row={row} detail={detail} />
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}
