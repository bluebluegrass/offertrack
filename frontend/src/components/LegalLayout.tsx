import { ReactNode } from 'react'

type LegalLayoutProps = {
  title: string
  lastUpdated: string
  children: ReactNode
}

export default function LegalLayout({ title, lastUpdated, children }: LegalLayoutProps) {
  return (
    <main className="min-h-screen px-4 py-6 font-sans sm:px-6 sm:py-10 lg:px-8">
      <div className="warm-panel mx-auto max-w-3xl rounded-2xl border p-5 sm:p-8">
        <header className="warm-divider border-b pb-4">
          <p className="warm-kicker text-sm font-medium">OfferTracker</p>
          <h1 className="warm-title mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          <p className="warm-muted mt-2 text-sm leading-6">Last updated: {lastUpdated}</p>
        </header>

        <article className="warm-copy mt-6 break-words text-[15px] leading-7 sm:text-base">{children}</article>

        <footer className="warm-divider mt-8 border-t pt-4">
          <div className="flex flex-col gap-3 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
            <a href="/" className="warm-link font-medium transition-colors">
              Home
            </a>
            <a href="/privacy" className="warm-link font-medium transition-colors">
              Privacy
            </a>
            <a href="/terms" className="warm-link font-medium transition-colors">
              Terms
            </a>
            <a href="mailto:hey.simonalife@gmail.com" className="warm-link font-medium transition-colors">
              Contact
            </a>
          </div>
        </footer>
      </div>
    </main>
  )
}
