# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅        |

## Reporting a Vulnerability

**Do NOT report security vulnerabilities through public GitHub issues.**

Email: **1254406948@qq.com**  
Subject: `[Security] Read Everything v3 — Vulnerability Report`

Response time: within 72 hours.

## API Key Security

This tool reads API keys from `~/.read_everything_config.json` (outside the repository).
**Never commit API keys to the repository.**
The `.gitignore` file explicitly blocks credential files.

## Input Sanitization

This tool performs file I/O with the privileges of the current process.
Do NOT pass untrusted file paths or URIs.
Call `read_everything()` only on files you trust.
