import { useEffect, useRef } from "react"

// Image-to-ASCII renderer (Componentry "ascii-effect"), ported from the original
// TSX to plain JSX for this Vite app: TypeScript types stripped, the Next.js `cn`
// helper and Tailwind classes replaced with plain classNames (styled in styles.css).
// Renders a source image as flowing ASCII characters on a canvas.

const IMAGE_COLORS = ["#f4f4f5", "#a1a1aa"]
const FLOW_COLORS = ["#e2e8f0", "#67e8f9", "#818cf8"]

function clamp(value, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value))
}

function parseHex(color) {
  const m = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color)
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null
}

function gradientColor(colors, amount) {
  if (colors.length < 2) return colors[0] ?? "#ffffff"
  const position = clamp(amount) * (colors.length - 1)
  const index = Math.min(Math.floor(position), colors.length - 2)
  const mix = position - index
  const from = parseHex(colors[index])
  const to = parseHex(colors[index + 1])
  if (!from || !to) return colors[Math.round(position)] ?? colors[0]
  return `rgb(${from.map((c, i) => Math.round(c + (to[i] - c) * mix)).join(", ")})`
}

export function AsciiEffect({
  imageSrc,
  alt = "ASCII rendering",
  variant = "image",
  chars = " .:-=+*#%@",
  fontSize = 9,
  fontFamily = "monospace",
  fontWeight = 400,
  lineHeight = 1,
  characterSpacing = 1,
  brightnessBoost = 2.2,
  contrast = 1.1,
  threshold = 0.06,
  posterize = 32,
  dither = "floyd-steinberg",
  ditherStrength = 0.8,
  flowSpeed = 0.22,
  flowDirection = 0,
  flowStrength = 12,
  flowFrequency = 0.018,
  mouseRadius = 150,
  mouseStrength = 22,
  mouseWaveSpeed = 1.2,
  scale = 1.15,
  fit = "cover",
  colors = IMAGE_COLORS,
  colorMode = "gradient",
  backgroundColor = "#07090d",
  invert = false,
  className = "",
}) {
  const containerRef = useRef(null)
  const canvasRef = useRef(null)
  const pointer = useRef({ x: 0, y: 0, targetX: 0, targetY: 0, active: false })

  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas || chars.length === 0) return
    const context = canvas.getContext("2d")
    const sampleCanvas = document.createElement("canvas")
    const sampleContext = sampleCanvas.getContext("2d", { willReadFrequently: true })
    if (!context || !sampleContext) return

    const image = new Image()
    image.crossOrigin = "anonymous"
    let frame = 0
    let width = 0
    let height = 0
    let loaded = false
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches

    const resize = () => {
      const rect = container.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (loaded) draw(performance.now())
    }

    const draw = (now) => {
      if (!loaded || width === 0 || height === 0) return
      pointer.current.x += (pointer.current.targetX - pointer.current.x) * 0.08
      pointer.current.y += (pointer.current.targetY - pointer.current.y) * 0.08

      const cellHeight = Math.max(4, fontSize * Math.max(0.5, lineHeight))
      context.font = `${fontWeight} ${fontSize}px ${fontFamily}`
      const cellWidth = Math.max(2, context.measureText("M").width * Math.max(0.5, characterSpacing))
      const columns = Math.ceil(width / cellWidth) + 2
      const rows = Math.ceil(height / cellHeight) + 2
      const radians = (flowDirection * Math.PI) / 180
      const directionX = Math.cos(radians)
      const directionY = Math.sin(radians)
      sampleCanvas.width = columns
      sampleCanvas.height = rows

      const imageScale =
        fit === "stretch"
          ? 1
          : (fit === "contain"
              ? Math.min(width / image.naturalWidth, height / image.naturalHeight)
              : Math.max(width / image.naturalWidth, height / image.naturalHeight)) *
            Math.max(0.1, scale)
      const drawWidth = fit === "stretch" ? columns : (image.naturalWidth * imageScale) / cellWidth
      const drawHeight = fit === "stretch" ? rows : (image.naturalHeight * imageScale) / cellHeight
      sampleContext.clearRect(0, 0, columns, rows)
      sampleContext.drawImage(image, (columns - drawWidth) / 2, (rows - drawHeight) / 2, drawWidth, drawHeight)

      const pixels = sampleContext.getImageData(0, 0, columns, rows).data
      const steps = Math.max(2, Math.round(posterize))
      const lum = new Float32Array(columns * rows)
      for (let i = 0; i < lum.length; i++) {
        const p = i * 4
        const alpha = pixels[p + 3] / 255
        let l = (pixels[p] * 0.2126 + pixels[p + 1] * 0.7152 + pixels[p + 2] * 0.0722) / 255
        l = clamp((l - 0.5) * Math.max(0, contrast) + 0.5)
        l = clamp(l * brightnessBoost * alpha)
        lum[i] = l <= threshold ? 0 : (l - threshold) / Math.max(0.001, 1 - threshold)
      }

      if (dither === "floyd-steinberg") {
        for (let row = 0; row < rows; row++) {
          for (let col = 0; col < columns; col++) {
            const i = row * columns + col
            const oldV = clamp(lum[i])
            const quant = Math.round(oldV * (steps - 1)) / (steps - 1)
            const v = oldV + (quant - oldV) * clamp(ditherStrength)
            const err = oldV - v
            lum[i] = v
            if (col + 1 < columns) lum[i + 1] += (err * 7) / 16
            if (row + 1 < rows) {
              if (col > 0) lum[i + columns - 1] += (err * 3) / 16
              lum[i + columns] += (err * 5) / 16
              if (col + 1 < columns) lum[i + columns + 1] += err / 16
            }
          }
        }
      } else if (dither === "bayer") {
        const matrix = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]
        for (let row = 0; row < rows; row++)
          for (let col = 0; col < columns; col++) {
            const i = row * columns + col
            const off = (matrix[(row % 4) * 4 + (col % 4)] / 16 - 0.5) * clamp(ditherStrength) / 4
            lum[i] = clamp(lum[i] + off)
          }
      } else {
        for (let i = 0; i < lum.length; i++)
          lum[i] = Math.round(clamp(lum[i]) * (steps - 1)) / (steps - 1)
      }

      context.fillStyle = backgroundColor
      context.fillRect(0, 0, width, height)
      context.textBaseline = "top"

      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < columns; col++) {
          let sourceColumn = col
          let sourceRow = row
          let mouseInfluence = 0
          if (variant === "flow" && !reduceMotion) {
            const x = col * cellWidth
            const y = row * cellHeight
            const phase = (x * directionX + y * directionY) * flowFrequency + now * flowSpeed * Math.PI * 0.002
            const crossPhase = (-x * directionY + y * directionX) * flowFrequency * 0.65
            const drift = (Math.sin(phase) + Math.sin(phase * 0.61 + crossPhase) * 0.45) * flowStrength
            if (pointer.current.active && mouseRadius > 0) {
              const mx = x - pointer.current.x
              const my = y - pointer.current.y
              const dist = Math.hypot(mx, my)
              mouseInfluence = clamp(1 - dist / mouseRadius)
              if (dist > 0 && mouseInfluence > 0) {
                const ripple = Math.sin(dist * 0.055 - now * mouseWaveSpeed * Math.PI * 0.002)
                const disp = mouseInfluence ** 2 * mouseStrength * ripple
                sourceColumn -= (mx / dist) * disp / cellWidth
                sourceRow -= (my / dist) * disp / cellHeight
              }
            }
            sourceColumn -= (directionX * drift) / cellWidth
            sourceRow -= (directionY * drift) / cellHeight
          }

          const sc = Math.round(clamp(sourceColumn, 0, columns - 1))
          const sr = Math.round(clamp(sourceRow, 0, rows - 1))
          const si = sr * columns + sc
          const p = si * 4
          let l = clamp(lum[si] + mouseInfluence * 0.08)
          if (invert) l = 1 - l
          const ch = chars[Math.min(chars.length - 1, Math.floor(l * (chars.length - 1)))]
          if (!ch || !ch.trim()) continue
          context.fillStyle =
            colorMode === "source"
              ? `rgb(${pixels[p]}, ${pixels[p + 1]}, ${pixels[p + 2]})`
              : gradientColor(colors, l)
          context.fillText(ch, col * cellWidth - cellWidth, row * cellHeight - cellHeight)
        }
      }
    }

    const animate = (now) => {
      draw(now)
      if (!reduceMotion && variant !== "image") frame = requestAnimationFrame(animate)
    }
    const start = () => {
      if (loaded) return
      loaded = true
      resize()
      if (!reduceMotion && variant !== "image") frame = requestAnimationFrame(animate)
    }
    image.onload = start
    image.src = imageSrc
    if (image.complete) start()

    const observer = new ResizeObserver(resize)
    observer.observe(container)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      image.onload = null
    }
  }, [backgroundColor, brightnessBoost, characterSpacing, chars, colorMode, colors, contrast, dither, ditherStrength, fit, flowDirection, flowFrequency, flowSpeed, flowStrength, fontFamily, fontSize, fontWeight, imageSrc, invert, lineHeight, mouseRadius, mouseStrength, mouseWaveSpeed, posterize, scale, threshold, variant])

  const trackPointer = (event) => {
    if (variant !== "flow") return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    if (!pointer.current.active) {
      pointer.current.x = x
      pointer.current.y = y
    }
    pointer.current.active = true
    pointer.current.targetX = x
    pointer.current.targetY = y
  }
  const resetPointer = () => {
    pointer.current.active = false
  }

  return (
    <div
      ref={containerRef}
      className={("ascii-fx " + className).trim()}
      onPointerMove={trackPointer}
      onPointerLeave={resetPointer}
    >
      <canvas ref={canvasRef} role="img" aria-label={alt} className="ascii-fx-canvas" />
    </div>
  )
}

export { FLOW_COLORS, IMAGE_COLORS }
