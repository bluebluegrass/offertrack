import { ReactNode } from 'react'

type LegalLayoutProps = {
  title: string
  lastUpdated: string
  children: ReactNode
}

export default function LegalLayout({ title, lastUpdated, children }: LegalLayoutProps) {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 font-sans sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl rounded-xl border border-slate-200 bg-white p-6 sm:p-8">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-sm font-medium text-indigo-600">OfferTracker</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
          <p className="mt-2 text-sm text-slate-500">Last updated: {lastUpdated}</p>
        </header>

        <article className="mt-6 text-base leading-7 text-slate-700">{children}</article>

        <footer className="mt-8 border-t border-slate-200 pt-4">
          <div className="inline-flex flex-wrap items-center gap-4 text-sm">
            <a href="/" className="font-medium text-slate-600 transition-colors hover:text-slate-900">
              Home
            </a>
            <a href="/privacy" className="font-medium text-slate-600 transition-colors hover:text-slate-900">
              Privacy
            </a>
            <a href="/terms" className="font-medium text-slate-600 transition-colors hover:text-slate-900">
              Terms
            </a>
            <a href="mailto:hey.simonalife@gmail.com" className="font-medium text-slate-600 transition-colors hover:text-slate-900">
              Contact
            </a>
          </div>
        </footer>
      </div>
    </main>
  )
}
