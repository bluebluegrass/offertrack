import { useEffect } from 'react'
import LegalLayout from '../components/LegalLayout'

const LAST_UPDATED = 'February 26, 2026'

export default function TermsPage() {
  useEffect(() => {
    document.title = 'Terms of Service | OfferTracker'
  }, [])

  return (
    <LegalLayout title="Terms of Service" lastUpdated={LAST_UPDATED}>
      <section className="space-y-4">
        <p>
          These Terms govern your use of OfferTracker at <a className="text-indigo-700 hover:underline" href="https://offertracker.simona.life">offertracker.simona.life</a>.
          By using the service, you agree to these Terms.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Description of Service</h2>
        <p>
          OfferTracker helps users track job applications by reading relevant Gmail or Outlook messages with your permission and
          generating a structured summary.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Acceptable Use</h2>
        <p>
          You agree not to misuse the service, attempt unauthorized access, disrupt operations, or use OfferTracker for unlawful
          activities.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">No Guarantees</h2>
        <p>
          OfferTracker is provided on an &quot;as is&quot; and &quot;as available&quot; basis. We do not guarantee uninterrupted
          operation, absolute accuracy, or suitability for any specific purpose.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Limitation of Liability</h2>
        <p>
          To the maximum extent allowed by law, OfferTracker and its operators are not liable for indirect, incidental, special, or
          consequential damages resulting from use of the service.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Termination</h2>
        <p>
          We may suspend or terminate access if these Terms are violated or if continued operation is not feasible. You may stop using
          the service at any time.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Changes to Terms</h2>
        <p>
          We may update these Terms over time. Continued use after updates means you accept the revised Terms. The date above reflects
          the latest version.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Contact</h2>
        <p>
          Questions can be sent to <a className="text-indigo-700 hover:underline" href="mailto:hey.simonalife@gmail.com">hey.simonalife@gmail.com</a>.
        </p>
      </section>
    </LegalLayout>
  )
}
