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
  Applied: 'bg-blue-50 text-blue-600',
  Interviewing: 'bg-amber-50 text-amber-600',
  Rejected: 'bg-red-50 text-red-600',
  Offer: 'bg-emerald-50 text-emerald-600',
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
    </div>
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
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-slate-900">Your Journey</h2>
        <div className="transition-all duration-200">
          {!hasResults ? (
            <div className="flex min-h-56 flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-200 bg-white p-10 text-center">
              <p className="text-2xl leading-none">💪</p>
              <p className="mt-3 text-base font-medium text-slate-600">Hang in there</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard label="Applications" value={summary.applications} />
                <StatCard label="Interviews" value={summary.interviews} />
                <StatCard label="Rejections" value={summary.rejections} />
                <StatCard label="Offers" value={summary.offers} />
                <StatCard label="No Response" value={summary.noResponse} />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <StatCard
                  label="Time to Offer"
                  value={summary.timeToOfferDays === null ? 'No offer yet' : `${summary.timeToOfferDays} days`}
                />
                <StatCard
                  label="Time Spent"
                  value={summary.timeSpentDays === null ? '-' : `${summary.timeSpentDays} days`}
                />
              </div>

              <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                <div className="border-b border-slate-200 px-4 py-3">
                  <h3 className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <img src="/offertracker-icon-transparent.png" alt="" className="h-4 w-4" />
                    OfferTracker Image
                  </h3>
                </div>
                <div className="p-4">
                  {!imageMissing ? (
                    <img
                      src={sankeyImageSrc}
                      alt="OfferTracker Sankey"
                      className="w-full rounded-md border border-slate-100"
                      loading="lazy"
                      onError={() => setImageMissing(true)}
                    />
                  ) : (
                    <p className="text-sm text-slate-500">
                      Image not found at <code className="rounded bg-slate-100 px-1 py-0.5">{sankeyImageSrc}</code>
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
          className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          <span>Message Classifications</span>
          {open ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
        </button>
        {open ? (
          <div className="mt-2 overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Event Type</th>
                  <th className="px-4 py-3 font-medium">Subject</th>
                </tr>
              </thead>
              <tbody>
                {messageRows.map((row, idx) => (
                  <tr key={`${row.date}-${idx}`} className="border-t border-slate-100 transition-colors hover:bg-slate-50">
                    <td className="px-4 py-3 text-slate-600">{row.date}</td>
                    <td className="px-4 py-3 text-slate-700">{row.company}</td>
                    <td className="px-4 py-3 text-slate-600">{row.eventType}</td>
                    <td className="max-w-[420px] truncate px-4 py-3 text-slate-500">{row.subject}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {hasResults ? (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium text-slate-700">Private: Application Details</h3>
            <span className="text-xs text-slate-400">Place this lower on page for safer screenshots</span>
          </div>
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-500">
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
                    <tr key={`${row.company}-${index}`} className="border-t border-slate-100 transition-colors hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-700">{row.company}</td>
                      <td className="px-4 py-3 text-slate-600">{row.position}</td>
                      <td className="px-4 py-3 text-slate-600">{row.applicationDate}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusPillClass[row.currentStatus]}`}>
                          {row.currentStatus}
                        </span>
                      </td>
                      <td className="max-w-[320px] truncate px-4 py-3 text-slate-500">{row.evidenceSubject}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}
