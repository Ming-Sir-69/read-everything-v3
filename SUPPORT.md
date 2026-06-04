# Support

## How to get help

- **GitHub Issues**: [Report bugs or request features](https://github.com/Ming-Sir-69/read-everything-v3/issues)
- **Discussions**: [Community Q&A](https://github.com/Ming-Sir-69/read-everything-v3/discussions)

## Common issues

### "ollama not running"
```bash
ollama serve
```

### "API key not configured"
Edit `~/.read_everything_config.json` and add the required keys.
See [README.md](README.md) for step-by-step instructions.

### "MarkItDown conversion failed"
```bash
pip install "markitdown[all]"
```

### "PDF classification timed out"
The first call to `qwen2.5vl:7b` on Ollama may take 30+ seconds to warm up.
Subsequent calls are faster (~10s).
