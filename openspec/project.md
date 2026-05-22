# OpenSpec Project: Chinese AI Publishing Review System

**Project Name:** Chinese AI Publishing Review System
**Version:** 1.0
**Language:** zh-CN
**Type:** Enterprise Content Governance Platform

## Conventions

- Change proposals live in `openspec/changes/{change-id}/`
- Source-of-truth specs live in `openspec/specs/`
- All specs use Markdown with YAML frontmatter where needed
- Architecture diagrams use Mermaid syntax
- API contracts follow OpenAPI 3.0 conventions
- Data models specify types explicitly

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| API Gateway | ASP.NET Core | Unified entry, auth, rate limiting |
| Workflow Engine | ASP.NET Core | State machine, approval flows |
| AI Services | Python / FastAPI | ML ecosystem, LLM integration |
| Message Queue | Kafka | Agent orchestration, event bus |
| Cache | Redis | Hot data, session, sensitive word cache |
| Object Storage | MinIO | Documents, PDFs, images |
| RDBMS | PostgreSQL | Metadata, workflow, permissions |
| Search | Elasticsearch | Full-text, OCR text |
| Vector DB | Milvus | Embeddings, semantic search |
| Audit DB | ClickHouse | Append-only audit logs |
| Container | Kubernetes | Orchestration, scaling |
