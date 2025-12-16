<!--
Sync Impact Report:
- Version change: [INITIAL] → 1.0.0
- Modified principles: N/A (initial creation)
- Added sections: All sections (initial constitution from template)
- Removed sections: None
- Templates requiring updates:
  ✅ constitution.md (this file) - created
  ✅ plan-template.md - updated Constitution Check section with all 5 principles
  ✅ spec-template.md - validated, no updates needed (already emphasizes testing)
  ✅ tasks-template.md - validated, no updates needed (generic task structure)
  ✅ command files - validated, agent-specific references are appropriate (script detection)
- Follow-up TODOs: None
-->

# OMD-MCP Constitution

## Core Principles

### I. Service Separation

The project MUST maintain clear separation between Chatbot Service (web UI + LLM integration)
and Thruk MCP Service (MCP server + Thruk API integration). Each service MUST be independently
deployable, testable, and documented. Services communicate ONLY via HTTP/Streamable HTTP using
Model Context Protocol standards.

**Rationale**: Service separation enables independent scaling, testing, and deployment. It
allows the Thruk MCP service to be reused by other MCP clients beyond the chatbot.

### II. MCP Protocol Compliance

All tool implementations, resource handlers, and prompt definitions MUST follow the Model
Context Protocol specification. The Thruk MCP service MUST correctly implement MCP server
capabilities (tools list, tool execution, error responses). Protocol versioning and capability
negotiation are mandatory.

**Rationale**: MCP compliance ensures interoperability with Claude Code, Claude Desktop, and
other MCP-enabled clients, not just the bundled chatbot.

### III. Configuration-Driven Integration

All external integrations (Thruk API endpoints, LLM providers, authentication credentials)
MUST be configured via environment variables. No hardcoded URLs, API keys, or deployment
assumptions in source code. The .env.example file MUST document all required and optional
configuration.

**Rationale**: Configuration externalization enables deployment flexibility (development,
staging, production), secure credential management, and easy adaptation to different Thruk
installations.

### IV. Containerization Standards

Each service MUST have a Dockerfile following best practices (minimal base images, non-root
users, health checks, multi-stage builds where applicable). Services MUST be deployable via
Docker Compose for local development and Kubernetes for production. Resource limits (CPU,
memory) MUST be configurable.

**Rationale**: Consistent containerization ensures reproducible deployments across development
and production environments, simplifies scaling, and enforces resource governance.

### V. Error Resilience & Observability

All inter-service communication MUST handle network failures gracefully. Thruk API errors
MUST be translated to actionable MCP error responses. Structured logging (JSON format) is
REQUIRED for all services. Sensitive data (API keys, credentials) MUST be redacted from
logs and error messages.

**Rationale**: Monitoring systems are mission-critical; the MCP chatbot must degrade gracefully
and provide clear diagnostics without compromising security or exposing sensitive data.

## Integration Requirements

### Thruk API Integration

- API requests MUST validate inputs before constructing Thruk API calls
- SSL/TLS certificate verification MUST be configurable (THRUK_VERIFY_SSL)
- Authentication MUST support API keys and optional user credentials
- Response parsing MUST handle malformed or unexpected API responses gracefully
- API rate limiting considerations MUST be documented

### LLM Integration

- LLM provider MUST be configurable via OPENAI_BASE_URL and OPENAI_MODEL
- Support for OpenAI-compatible APIs (OpenAI, Anthropic, local models) is REQUIRED
- LLM API errors MUST not crash the chatbot service
- Conversation context MUST be managed to prevent token limit exhaustion

## Development Workflow

### Testing Requirements

- Unit tests MUST cover Thruk API request construction and response parsing
- Contract tests MUST verify MCP tool schemas match implementation
- Integration tests MUST validate chatbot ↔ Thruk MCP communication
- End-to-end tests SHOULD use mock Thruk API responses for reproducibility

### Code Review Standards

- All PRs MUST verify MCP protocol compliance
- Security-sensitive changes (authentication, credential handling) require additional review
- Breaking changes to MCP tools require version increment and migration notes
- Dockerfile changes MUST maintain security best practices (non-root users, minimal attack surface)

### Deployment Gates

- Docker images MUST build successfully for both services
- Health check endpoints MUST respond correctly
- Environment variable documentation (.env.example) MUST be synchronized with code
- Kubernetes manifests MUST include resource limits and readiness probes

## Governance

### Amendment Process

Constitution amendments MUST be documented with clear rationale and approved before
implementation. Changes to core principles (I-V) require MAJOR version bump. Changes
to integration requirements or workflow sections require MINOR version bump. Wording
clarifications and formatting fixes require PATCH version bump.

### Compliance Verification

All PRs MUST verify compliance with applicable principles. Violations of service separation
(Principle I) or security requirements are blocking and MUST be resolved before merge.
Complexity that cannot be justified against simplicity goals MUST be refactored.

### Versioning Policy

This constitution follows semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR: Backward-incompatible principle changes, removals, or fundamental redefinitions
- MINOR: New principles, expanded guidance, new governance sections, or requirement additions
- PATCH: Clarifications, wording improvements, typo fixes, formatting adjustments

**Version**: 1.0.0 | **Ratified**: 2025-12-16 | **Last Amended**: 2025-12-16
