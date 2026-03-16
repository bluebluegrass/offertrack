import { useEffect, useState } from 'react'
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
}

type Props = {
  summary: Summary
  applicationRows: ApplicationRow[]
  messageRows: MessageRow[]
  hasResults: boolean
  sankeyImageSrc: string
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
      </div>
    </article>
  )
}

function MobileApplicationCard({ row }: { row: ApplicationRow }) {
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
      </div>
    </article>
  )
}

export default function ResultsAndImageSection({
  summary,
  applicationRows,
  messageRows,
  hasResults,
  sankeyImageSrc,
}: Props) {
  const [open, setOpen] = useState(false)
  const [imageMissing, setImageMissing] = useState(false)

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
                  <th className="px-4 py-3 font-medium">Subject</th>
                </tr>
              </thead>
              <tbody>
                {messageRows.map((row, idx) => (
                  <tr key={`${row.date}-${idx}`} className="warm-divider border-t transition-colors hover:bg-[color:var(--accent-soft)]/18">
                    <td className="warm-copy px-4 py-3 align-top">{row.date}</td>
                    <td className="warm-title px-4 py-3 align-top">{row.company}</td>
                    <td className="warm-copy px-4 py-3 align-top">{row.eventType}</td>
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
              {applicationRows.map((row, index) => (
                <MobileApplicationCard key={`${row.company}-${index}`} row={row} />
              ))}
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
                    <th className="px-4 py-3 font-medium">Evidence Subject</th>
                  </tr>
                </thead>
                <tbody>
                  {applicationRows.map((row, index) => (
                    <tr key={`${row.company}-${index}`} className="warm-divider border-t transition-colors hover:bg-[color:var(--accent-soft)]/18">
                      <td className="warm-title px-4 py-3 align-top">{row.company}</td>
                      <td className="warm-copy px-4 py-3 align-top">{row.position}</td>
                      <td className="warm-copy px-4 py-3 align-top">{row.applicationDate}</td>
                      <td className="px-4 py-3 align-top">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusPillClass[row.currentStatus]}`}>
                          {row.currentStatus}
                        </span>
                      </td>
                      <td className="warm-muted max-w-[320px] truncate px-4 py-3 align-top">{row.evidenceSubject}</td>
                    </tr>
                  ))}
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
