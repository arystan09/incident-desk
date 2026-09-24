# ADR 0001: Initial architecture

Status: proposed for owner review

## Context

Incident Desk is a personal portfolio project investigating resumable incident
workflows in a synthetic environment. It needs understandable failure semantics,
typed boundaries, and exact human approval of proposed local effects. F1-01 only
implements the HTTP and tooling foundation; this decision guides later milestones.

## Decision

Use one modular Python application with separate API and worker process roles.
They share domain contracts and a PostgreSQL source of truth, while scaling and
restarting independently. Keeping one package avoids service-to-service contracts
and deployment machinery before the project needs them.

Initially store jobs alongside runs, steps, proposals, and audit records in
PostgreSQL. Transactions can couple state transitions and local effects. Claims,
leases, fencing, bounded retries, and recovery must be implemented explicitly and
verified against real PostgreSQL. Durable storage alone does not guarantee correct
recovery or exactly-once execution of external effects.

Do not introduce Redis, a broker, a vector database, Kubernetes, or an agent
framework. Four typed evidence tools and bounded fixtures do not yet require
semantic retrieval or a separate queue. These components would add operational
and consistency boundaries without a demonstrated workload requirement.

## Consequences and reconsideration

This keeps local development and review small, but the application owns scheduling,
lease renewal, retry policy, and safe resume semantics. Never hold a transaction
open across a model call. Keep provider and persistence code behind typed boundaries.

Consider a dedicated workflow engine when demonstrated needs include long-running
multi-stage orchestration, many independent services, complex timers or compensation,
workflow version migration, or operational recovery burden that exceeds the value
of a PostgreSQL job implementation. Record measurements and a new ADR before adopting
one. An engine would not replace tenant authorization, exact approval binding, or
atomic local effects. Introduce a broker or vector index only for a concrete,
measured requirement, with failure and consistency semantics documented.
