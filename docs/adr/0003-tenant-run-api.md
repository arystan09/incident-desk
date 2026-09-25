# ADR 0003: Tenant keys and transactional run idempotency

Status: proposed for owner review.

## Identity and HTTP boundary

Provision tenants locally with `uv run --locked python -m incident_desk.provision
--name NAME`. The CLI commits the tenant and first key before displaying the raw
key once. Keys are generated with `secrets.token_urlsafe(32)` (256 random bits);
only a SHA-256 digest of the complete key is stored. These are random bearer
credentials, not human passwords. There is no provisioning HTTP endpoint. Send
keys only over trusted local connections or HTTPS; do not log Authorization headers.
Rotation, a revocation CLI, and reviewer roles are outside F1-03. A non-null
revoked_at prevents subsequent authentication; revocation does not cancel requests
that already authenticated.

Synchronous dependencies authenticate the stored digest and return its tenant UUID.
Run access always includes that UUID in database predicates. Caller-supplied tenant
headers and query parameters cannot select a tenant; unknown body fields are rejected.
This is application-enforced tenant isolation, not PostgreSQL row-level security.
The database credentials are trusted administrative access and must stay private.

POST and GET use explicit response models. Invalid authentication returns 401 with
WWW-Authenticate: Bearer; invalid input is 422; conflicting idempotency input is
409; absent and other-tenant runs share the same 404. Validation responses omit
raw input/context so secrets in invalid bodies are not reflected. Connection-class
OperationalError and pool timeouts become a generic 503. Constraint, SQL programming,
and unrelated errors are not classified as unavailable or idempotency collisions.

## Ownership and concurrency

The API lifespan owns one lazy engine, with disposal off the event loop. Construction
never connects or migrates. Synchronous dependencies/endpoints run in FastAPI's
thread pool and each owns a separate short-lived session/transaction. Authentication
finishes before the run transaction; no session crosses concurrent requests.
Liveness never requests a database connection.

Canonical request identity is SHA-256 of sorted compact ASCII-escaped JSON containing
schema_version=1, service_id, and incident_id after validated whitespace stripping.
Idempotency keys are case-sensitive 1-128 characters in ASCII 0x21 through 0x7e.
A database UNIQUE(tenant_id, idempotency_key) constraint is authoritative.

At explicit READ COMMITTED isolation, INSERT ... ON CONFLICT DO NOTHING targets
only uq_runs_tenant_idempotency and returns the newly inserted run. The winner
inserts its queued job in that same transaction. A competing insert waits for the
winner's transaction. After a conflict, a separate SELECT gets a fresh committed
snapshot and compares request_hash: identical returns the existing run, different
raises a conflict. If the winner rolls back, a contender can insert instead. No
broad IntegrityError catch is used. The response is returned only after commit.
Deletion of runs is not exposed; this algorithm assumes no concurrent administrative
run deletion. POST and replay both return 202 and Location; replay reports the current
persisted run state, which can change after future execution. No fixture is looked
up and no investigation has run.

Concurrency tests synchronize two independent PostgreSQL connections immediately
before the insert, verify distinct backend PIDs, and assert one run/job pair for
both identical and conflicting requests. A real job constraint failure proves rollback.

## Migration and legacy records

0001 remains unchanged. 0002 creates tenants and api_keys, then backfills one tenant
per distinct existing runs.tenant_id, named legacy:<tenant UUID>. No API key is
created for these tenants, so historical records do not acquire a new access path.
Existing runs retain IDs, statuses, counters, timestamps, jobs, and steps. Newly
required fields receive service_id=legacy-unassigned, incident_id and idempotency_key
of legacy:<run UUID>, and SHA-256 of legacy-v0:<run UUID> as request_hash. These
internal placeholders do not claim a real service/incident and cannot match a v1
request hash. The migration then makes fields non-null and installs the foreign key
and unique constraint. New requests supply real validated identifiers; there are no
legacy defaults for new rows. Development inspection found zero runs before upgrade;
a disposable test verifies migration of representative 0001 history.

Downgrading 0002 loses tenant/key records and request metadata while preserving
original run/job/step records. Downgrade testing is for disposable databases only.
Hosted CI execution and an independent source/security audit are separate from
local test evidence; neither is implied by owner acceptance of F1-02.
