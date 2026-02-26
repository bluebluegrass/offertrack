import { useEffect } from 'react'
import LegalLayout from '../components/LegalLayout'

const LAST_UPDATED = 'February 26, 2026'

export default function PrivacyPage() {
  useEffect(() => {
    document.title = 'Privacy Policy | OfferTracker'
  }, [])

  return (
    <LegalLayout title="Privacy Policy" lastUpdated={LAST_UPDATED}>
      <section className="space-y-4">
        <p>
          OfferTracker helps you track your job search by connecting to Gmail or Outlook with read-only access. We only process the
          minimum data needed to detect job application events.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">What Data Is Accessed</h2>
        <p>
          If you connect Gmail or Outlook, OfferTracker can read relevant email metadata and content needed to classify job search
          activity, including sender, subject, timestamp, and message body.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">How Mail Access Is Used</h2>
        <p>
          Mail access is used only to identify and summarize job-search signals such as applications, interviews, rejections, and
          offers. Access scopes are read-only (`gmail.readonly` for Gmail and `Mail.Read` for Outlook).
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Data Storage and Retention</h2>
        <p>
          OfferTracker does not store raw email content or attachments. Email data is processed temporarily in memory during a scan and
          discarded after processing. We do not sell or share user data.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Security</h2>
        <p>
          We use HTTPS and standard access controls to protect app traffic and OAuth flow integrity. We also minimize logging and avoid
          logging raw email content.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Third-Party Services</h2>
        <p>
          OfferTracker uses Google OAuth/Gmail API and Microsoft OAuth/Graph API for mailbox access, and may use limited operational
          tooling for performance and debugging. These tools are not used to store email content.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">User Rights</h2>
        <p>
          You can revoke OfferTracker access at any time from your Google or Microsoft account permissions settings. You can also stop
          using the service at any time.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Contact</h2>
        <p>
          Questions about this policy can be sent to <a className="text-indigo-700 hover:underline" href="mailto:hey.simonalife@gmail.com">hey.simonalife@gmail.com</a>.
        </p>
      </section>
    </LegalLayout>
  )
}
