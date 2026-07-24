import { AsciiEffect } from './AsciiEffect.jsx'

// Landing hero: a Greek marble bust rendered as flowing dithered ASCII (the
// classical "watcher" motif), with a plain-language explanation of what
// Ouroboros actually is. Scroll / click drops into the live console below.
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

      <div className="hero-copy">
        <div className="hero-eyebrow">Agents of SigNoz · Track 01 — AI &amp; Agent Observability</div>
        <h1 className="hero-title">OURO<b>BOROS</b></h1>
        <p className="hero-line">The AI SRE that watches your systems — and itself.</p>
        <p className="hero-tag">
          It watches your services around the clock, diagnoses incidents from live
          SigNoz telemetry, and fixes them — <b>auto-healing</b> when it's confident,
          <b> asking you first</b> for high-impact actions. And every decision it makes
          is itself a trace in SigNoz, so you can watch the watcher.
        </p>
        <div className="hero-facts">
          <span>Diagnoses from real traces &amp; metrics</span>
          <span>Auto-heals or requests approval</span>
          <span>Fully self-observable</span>
        </div>
        <button className="hero-cta" onClick={onEnter}>Open the live console ↓</button>
      </div>
    </section>
  )
}
