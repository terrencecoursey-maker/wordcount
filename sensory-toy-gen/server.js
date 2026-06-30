require('dotenv').config()
const express = require('express')
const Anthropic = require('@anthropic-ai/sdk')

const app = express()
app.use(express.json())

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })

const SYSTEM_PROMPT = `You are an expert sensory toy designer specializing in educational toys for children with diverse sensory needs. You create detailed, safe, and engaging sensory toy designs.

For each request, provide:
## 🧸 Toy Name
A creative, descriptive name.

## 📝 Description
A 2-3 sentence overview of the toy and its purpose.

## 🎯 Sensory Benefits
Bullet list of which senses are engaged and how.

## 🛒 Materials Needed
A complete list with quantities and where to find them.

## 🔨 How to Make It
Numbered step-by-step instructions.

## 👶 Age Range & Skills
Age suitability and developmental skills it supports.

## ⚠️ Safety Notes
Any important safety considerations.`

app.post('/api/generate', async (req, res) => {
  const { prompt } = req.body

  if (!prompt || !prompt.trim()) {
    return res.status(400).json({ error: 'Prompt is required' })
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return res.status(500).json({ error: 'ANTHROPIC_API_KEY is not set' })
  }

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')

  try {
    const stream = client.messages.stream({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1500,
      system: SYSTEM_PROMPT,
      messages: [{ role: 'user', content: prompt }]
    })

    for await (const event of stream) {
      if (
        event.type === 'content_block_delta' &&
        event.delta.type === 'text_delta'
      ) {
        res.write(`data: ${JSON.stringify({ text: event.delta.text })}\n\n`)
      }
    }

    res.write('data: [DONE]\n\n')
    res.end()
  } catch (err) {
    if (!res.headersSent) {
      res.status(500).json({ error: err.message })
    } else {
      res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`)
      res.end()
    }
  }
})

const PORT = process.env.PORT || 3001
app.listen(PORT, () => {
  console.log(`API server running on http://localhost:${PORT}`)
})
