import { motion, useReducedMotion } from 'framer-motion'

type Props = {
  onContinue: () => void
  onTryDemo?: () => void
  primaryCtaLabel?: string
}

function HeroTitle() {
  const reduceMotion = useReducedMotion()

  return (
    <div className="landing-hero">
      <motion.div
        className="landing-doodle landing-doodle-left"
        initial={reduceMotion ? { opacity: 1, rotate: -8 } : { opacity: 0, y: -8, rotate: -14 }}
        animate={{ opacity: 1, y: 0, rotate: -8 }}
        transition={{ delay: 0.2, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        ✦
      </motion.div>
      <motion.div
        className="landing-doodle landing-doodle-right"
        initial={reduceMotion ? { opacity: 1, rotate: 10 } : { opacity: 0, y: 8, rotate: 16 }}
        animate={{ opacity: 1, y: 0, rotate: 10 }}
        transition={{ delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        ☀
      </motion.div>
      <motion.div
        className="landing-breath-note"
        initial={reduceMotion ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.94, rotate: -5 }}
        animate={{ opacity: 1, scale: 1, rotate: -3 }}
        transition={{ delay: 1.05, duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
      >
        deep breath
      </motion.div>
      <h1 className="landing-headline warm-title text-[clamp(3rem,8vw,5.1rem)] font-semibold tracking-tight">
        <span className="landing-headline-prefix">Job search is</span>
        <span className="landing-word-row">
          <span className="landing-word-chaotic">
            chaotic
            <svg
              viewBox="0 0 460 96"
              aria-hidden="true"
              className="landing-strike-svg"
              preserveAspectRatio="none"
            >
              <motion.path
                className="landing-strike-underpaint"
                d="M12 58 C58 36, 106 79, 154 56 S250 41, 304 57 S386 69, 448 53"
                initial={reduceMotion ? { pathLength: 1, opacity: 0.65 } : { pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ delay: 0.5, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
              />
              <motion.path
                className="landing-strike-main"
                d="M10 51 C49 33, 98 73, 149 52 S247 38, 301 55 S390 65, 450 49"
                initial={reduceMotion ? { pathLength: 1, opacity: 1 } : { pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ delay: 0.58, duration: 0.84, ease: [0.22, 1, 0.36, 1] }}
              />
            </svg>
          </span>
          <motion.span
            className="landing-word-organized landing-word-organized-playful"
            initial={reduceMotion ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: 12, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 1.28, duration: 0.48, ease: [0.22, 1, 0.36, 1] }}
          >
            organized.
          </motion.span>
        </span>
      </h1>
    </div>
  )
}

export default function LandingPage({ onContinue, onTryDemo, primaryCtaLabel = 'Connect Inbox' }: Props) {
  return (
    <section className="landing-shell overflow-hidden rounded-[2rem] border border-[color:var(--border)] px-5 py-6 sm:px-8 sm:py-8 lg:px-10 lg:py-10">
      <div className="landing-brand mx-auto">
        <img src="/offertracker-icon-transparent.png" alt="" className="h-5 w-5" />
        <span>OfferTracker</span>
      </div>

      <div className="mx-auto mt-5 max-w-4xl text-center">
        <p className="landing-kicker warm-kicker text-[11px] font-medium uppercase tracking-[0.22em]">Job Search Clarity</p>
      </div>

      <div className="mx-auto mt-6 max-w-5xl space-y-5 text-center">
        <HeroTitle />
        <p className="warm-copy mx-auto max-w-2xl text-base leading-7 sm:text-lg sm:leading-8">
          Turn your inbox into a clear job search dashboard. OfferTracker organizes your pipeline and shows the next step for each application.
        </p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={onContinue}
            className="landing-cta warm-button inline-flex min-h-[56px] items-center justify-center rounded-full px-8 py-3 text-sm font-medium text-white transition"
          >
            {primaryCtaLabel}
          </button>
          {onTryDemo ? (
            <button
              type="button"
              onClick={onTryDemo}
              className="landing-secondary-cta inline-flex min-h-[56px] items-center justify-center rounded-full px-7 py-3 text-sm font-medium transition"
            >
              View Demo
            </button>
          ) : null}
        </div>
      </div>

      <section className="mx-auto mt-12 max-w-5xl">
        <div className="grid gap-4 md:grid-cols-[0.95fr_1.1fr_0.95fr]">
          <article className="landing-feature-card landing-feature-card-soft landing-feature-step">
            <div className="landing-feature-step-number">1</div>
            <div className="landing-feature-icon landing-feature-icon-soft mb-4">✉️</div>
            <p className="landing-feature-kicker warm-kicker text-[10px] font-medium uppercase tracking-[0.18em]">Read emails</p>
            <p className="warm-title mt-2 text-xl font-semibold tracking-tight">Find job emails automatically</p>
            <p className="warm-copy mt-3 text-sm leading-6">
              OfferTracker pulls job-related emails out of your inbox, so you do not have to search through every thread yourself.
            </p>
          </article>

          <article className="landing-feature-card landing-feature-card-strong landing-feature-step">
            <div className="landing-feature-step-number landing-feature-step-number-strong">2</div>
            <div className="landing-feature-icon landing-feature-icon-strong mb-4">📊</div>
            <p className="landing-feature-kicker text-[10px] font-medium uppercase tracking-[0.18em] text-white/72">See progress</p>
            <p className="mt-2 text-xl font-semibold tracking-tight text-white">See your pipeline clearly</p>
            <p className="mt-3 text-sm leading-6 text-white/88">
              The funnel shows how many applications are still waiting, in interviews, rejected, or turned into offers.
            </p>
          </article>

          <article className="landing-feature-card landing-feature-card-warm landing-feature-step">
            <div className="landing-feature-step-number landing-feature-step-number-warm">3</div>
            <div className="landing-feature-icon landing-feature-icon-warm mb-4">→</div>
            <p className="landing-feature-kicker warm-kicker text-[10px] font-medium uppercase tracking-[0.18em]">Take action</p>
            <p className="warm-title mt-2 text-xl font-semibold tracking-tight">Get the next step for each job</p>
            <p className="warm-copy mt-3 text-sm leading-6">
              Each application can show what to do next, like follow up, find a recruiter, or prepare for an interview.
            </p>
          </article>
        </div>
      </section>
    </section>
  )
}
