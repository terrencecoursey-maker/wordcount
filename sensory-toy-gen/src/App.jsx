import { useState } from 'react'

const AGE_RANGES = ['0-2', '2-4', '4-6', '6-8', '8-12', '12+']
const SENSORY_OPTIONS = [
  { id: 'tactile', label: 'Tactile', emoji: '✋' },
  { id: 'visual', label: 'Visual', emoji: '👁️' },
  { id: 'auditory', label: 'Auditory', emoji: '👂' },
  { id: 'vestibular', label: 'Vestibular', emoji: '🌀' },
  { id: 'proprioceptive', label: 'Proprioceptive', emoji: '💪' },
  { id: 'oral', label: 'Oral', emoji: '👄' },
]
const MATERIAL_PREFS = ['Household items', 'Craft supplies', 'Sensory beads/fillers', 'Fabric', 'Foam/sponge', 'Natural materials']

export default function App() {
  const [description, setDescription] = useState('')
  const [ageRange, setAgeRange] = useState('2-4')
  const [sensoryFoci, setSensoryFoci] = useState([])
  const [materials, setMaterials] = useState([])
  const [output, setOutput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const toggleItem = (value, list, setList) => {
    setList(prev =>
      prev.includes(value) ? prev.filter(v => v !== value) : [...prev, value]
    )
  }

  const buildPrompt = () => {
    const parts = [`Create a sensory toy for children ages ${ageRange}.`]
    if (sensoryFoci.length > 0) {
      parts.push(`Sensory focus areas: ${sensoryFoci.join(', ')}.`)
    }
    if (materials.length > 0) {
      parts.push(`Preferred materials: ${materials.join(', ')}.`)
    }
    if (description.trim()) {
      parts.push(`Additional details: ${description.trim()}`)
    }
    return parts.join(' ')
  }

  const generate = async () => {
    const prompt = buildPrompt()
    setLoading(true)
    setOutput('')
    setError('')

    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.error || 'Request failed')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') break
          try {
            const parsed = JSON.parse(data)
            if (parsed.error) throw new Error(parsed.error)
            if (parsed.text) setOutput(prev => prev + parsed.text)
          } catch (e) {
            if (e.message !== 'Unexpected end of JSON input') throw e
          }
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setOutput('')
    setError('')
  }

  return (
    <div className="app">
      <header>
        <h1>🧸 Sensory Toy Generator</h1>
        <p>Design custom sensory toys powered by AI</p>
      </header>

      <main>
        <div className="form-card">
          <section>
            <label className="section-label">Age Range</label>
            <div className="pill-group">
              {AGE_RANGES.map(age => (
                <button
                  key={age}
                  className={`pill ${ageRange === age ? 'active' : ''}`}
                  onClick={() => setAgeRange(age)}
                >
                  {age}
                </button>
              ))}
            </div>
          </section>

          <section>
            <label className="section-label">Sensory Focus <span className="optional">(optional)</span></label>
            <div className="pill-group">
              {SENSORY_OPTIONS.map(({ id, label, emoji }) => (
                <button
                  key={id}
                  className={`pill ${sensoryFoci.includes(id) ? 'active' : ''}`}
                  onClick={() => toggleItem(id, sensoryFoci, setSensoryFoci)}
                >
                  {emoji} {label}
                </button>
              ))}
            </div>
          </section>

          <section>
            <label className="section-label">Preferred Materials <span className="optional">(optional)</span></label>
            <div className="pill-group">
              {MATERIAL_PREFS.map(mat => (
                <button
                  key={mat}
                  className={`pill ${materials.includes(mat) ? 'active' : ''}`}
                  onClick={() => toggleItem(mat, materials, setMaterials)}
                >
                  {mat}
                </button>
              ))}
            </div>
          </section>

          <section>
            <label className="section-label" htmlFor="description">
              Description <span className="optional">(optional)</span>
            </label>
            <textarea
              id="description"
              placeholder="e.g. A calming toy for a child who loves water and bright colors..."
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
            />
          </section>

          <button
            className="generate-btn"
            onClick={generate}
            disabled={loading}
          >
            {loading ? (
              <><span className="spinner" /> Generating...</>
            ) : (
              '✨ Generate Toy Idea'
            )}
          </button>
        </div>

        {error && (
          <div className="error-card">
            <strong>Error:</strong> {error}
          </div>
        )}

        {output && (
          <div className="output-card">
            <div className="output-header">
              <h2>Your Sensory Toy Design</h2>
              <button className="reset-btn" onClick={reset}>New Design</button>
            </div>
            <div className="output-body">
              <MarkdownOutput text={output} />
              {loading && <span className="cursor" />}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function MarkdownOutput({ text }) {
  const lines = text.split('\n')
  const elements = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('## ')) {
      elements.push(<h2 key={i}>{line.slice(3)}</h2>)
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={i}>{line.slice(2)}</h1>)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      const items = []
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('* '))) {
        items.push(<li key={i}>{lines[i].slice(2)}</li>)
        i++
      }
      elements.push(<ul key={`ul-${i}`}>{items}</ul>)
      continue
    } else if (/^\d+\. /.test(line)) {
      const items = []
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(<li key={i}>{lines[i].replace(/^\d+\. /, '')}</li>)
        i++
      }
      elements.push(<ol key={`ol-${i}`}>{items}</ol>)
      continue
    } else if (line.trim()) {
      elements.push(<p key={i}>{line}</p>)
    }
    i++
  }

  return <div className="markdown">{elements}</div>
}
