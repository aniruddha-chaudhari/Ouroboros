import { AsciiEffect } from './AsciiEffect.jsx'

// The four steps of the agent's control loop. Rendered here as a self-advancing
// strip so the landing page *demonstrates* the loop instead of describing it —
// it previews the same DIAGNOSE→DECIDE→ACT→VERIFY ring the console runs live.
// The cycling is pure CSS (staggered negative animation-delays), deliberately:
// this page already pays for an animated canvas, so the loop must cost no
// re-renders and no extra main-thread work.
const PHASES = ['Diagnose', 'Decide', 'Act', 'Verify']

// The three-tier autonomy model — the thing that actually distinguishes this
// from a monitoring dashboard, so it belongs in the hero rather than the docs.
const TIERS = [
  { k: 'auto', label: 'Auto-heal', when: 'confident · low blast radius' },
  { k: 'ask', label: 'Ask first', when: 'unsure · or high-impact' },
  { k: 'noop', label: 'Do nothing', when: 'nothing is actually wrong' },
]

// Landing hero: a Greek marble bust rendered as flowing dithered ASCII (the
// classical "watcher" motif), with a plain-language explanation of what
// Ouroboros actually is. The CTA routes to the live console.
export default function Hero({ onEnter }) {
  return (
    <section className="hero">
      <div className="hero-art" aria-hidden="true">
        <AsciiEffect
          variant="flow"
          imageSrc="/statue.jpg"
          fontSize={7}
          characterSpacing={1}
          lineHeight={1}
          scale={1.05}
          fit="cover"
          contrast={1.25}
          brightnessBoost={2.0}
          dither="floyd-steinberg"
          flowStrength={7}
          flowSpeed={0.16}
          mouseRadius={170}
          mouseStrength={16}
          colors={['#0a0c10', '#33414d', '#7dd3fc', '#e8edf2']}
          backgroundColor="#0a0c10"
        />
        <div className="hero-fade" />
      </div>

      {/* CRT scanlines + grain: atmosphere that matches the dithered art */}
      <div className="hero-veil" aria-hidden="true" />

      <div className="hero-copy">
        <span className="hero-bracket tl" aria-hidden="true" />
        <span className="hero-bracket br" aria-hidden="true" />

        <div className="hero-eyebrow">
          <span className="hero-dot" aria-hidden="true" />
          Agents of SigNoz · Track 01 — AI &amp; Agent Observability
        </div>

        <h1 className="hero-title" data-echo="OUROBOROS">
          OURO<b>BOROS</b>
        </h1>

        <p className="hero-line">The AI SRE that watches your systems — and itself.</p>

        <p className="hero-tag">
          It watches your services around the clock and root-causes incidents from
          live <b>SigNoz</b> telemetry — traces, metrics, logs. Then it acts. And every
          decision it makes is <b>itself a trace in SigNoz</b>, so you can watch the
          watcher.
        </p>

        <div className="hero-loop" role="list" aria-label="The agent's control loop">
          {PHASES.map((p) => (
            <span className="hero-phase" role="listitem" key={p}>{p}</span>
          ))}
          <span className="hero-loop-back" aria-hidden="true">↻</span>
        </div>

        <ul className="hero-spec">
          {TIERS.map((t) => (
            <li className={'hero-tier ' + t.k} key={t.k}>
              <b>{t.label}</b>
              <span>{t.when}</span>
            </li>
          ))}
        </ul>

        <button className="hero-cta" onClick={onEnter}>
          <span>Open the live console</span>
          <i aria-hidden="true">→</i>
        </button>
      </div>
    </section>
  )
}
