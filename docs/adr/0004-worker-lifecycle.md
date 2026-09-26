# ADR 0004: PostgreSQL worker ownership and deterministic execution

Status: proposed for owner review (F1-04).

## Decision

Keep the queue beside runs in PostgreSQL. A short transaction selects one due
queued job or expired running job with `FOR UPDATE SKIP LOCKED`, ordered by
next_attempt_at/id, and locks its run. It increments attempt_count and
lease_generation exactly once, records an automatically generated process UUID,
claimed_at and lease_expires_at, and sets both records running. Existing queued
and running partial indexes cover the two eligibility predicates. The OR and
ordering may still require a bitmap scan/sort; no throughput claim is made.

Reuse the existing vocabulary: queued -> running -> completed/failed. `completed`
means success; do not introduce a synonymous succeeded state. Retry returns both
records to queued with a future next_attempt_at. Running jobs with expired leases
can be claimed directly; there is no separate reaper. Exhausted expired jobs become
failed without incrementing the count again. Terminal runs are never resurrected.
Run state_version increments on each worker transition. Other pre-existing run
statuses are reserved and not entered by this executor.

Each process generates its own UUID; this is operational identity, not authority
for API access. Defaults: poll every 1 second while idle, 60-second lease, three
attempts, retry base 2 seconds. Retries wait 2 then 4 seconds by default, bounded at
60 seconds with other allowed settings. All workers should use the same policy.
Changing max attempts affects existing jobs; it is configuration, not per-job data.

## Transaction and failure boundaries

Claim commits before fixture execution. The executor performs only a fixed small
packaged catalog lookup and deterministic transformations, without database access,
network calls, sleeps, or external effects. No lease heartbeat is needed for this
bounded workload. A suspended process may exceed the lease; it then loses the right
to publish. Extending to slow providers will require explicit deadlines/renewal.

A separate publication transaction locks the job, checks running status, owner,
generation and expiry against PostgreSQL clock_timestamp AFTER obtaining the lock,
then locks the run. It appends five completed steps and marks both records completed
atomically. The locked ownership check is the serialization point: recovery cannot
acquire the row while publication commits. A worker with an expired or replaced
lease cannot publish or fail that job. Job locks precede run locks everywhere.
Statement and connection timeouts remain bounded.

The final summary lives in the last completed RunStep, avoiding a duplicate result
column. Step numbers append under the job lock; attempt/generation are stored in
input metadata. These are observable action/results, not model reasoning. Steps
are published as one batch after execution; timestamps describe persistence, not
per-action durations. A crash before publication can repeat computation but cannot
publish duplicate successful steps. This is NOT exactly-once execution or a fence
for arbitrary external side effects. No external effects exist in this milestone.

Explicit RetryableExecutionError, connection failures, pool timeouts, serialization
failures and deadlocks are transient. Missing/mismatched fixtures are non-retryable.
Unexpected executor or persistence errors are internal failures, not blind retries.
Failure publication uses the same fencing check, atomically records a safe fixed
code in jobs and a failed execution_failure step, and queues a retry or fails both
records. No exception message, SQL or stack trace is persisted or logged. If failure
persistence itself is unavailable, retain the durable running claim for lease expiry;
crash recovery also consumes the bounded attempt budget. A non-transient claim/schema
error stops the worker with a nonzero exit instead of spinning forever.

## Storage and operations

0003 adds nullable claimed_at and last_error_code plus the partial running-lease
index. It rewrites no existing rows and needs no backfill. Existing queued jobs
remain processable. An old running row without any lease expiry is not automatically
repaired; pre-F1-04 code never creates such a state. Downgrade loses only the added
worker diagnostics/index; do it only on disposable databases with workers stopped.
0001 and 0002 remain unchanged. No process runs migrations on startup.

SIGINT and SIGTERM set a stop event: stop claiming, finish current short execution,
and dispose the engine. Ctrl+C is the normal Windows console path. Windows process
termination/Task Manager need not deliver a catchable signal; lease expiry provides
recovery. The subprocess smoke test terminates only its own handles after completion;
the separate stop-event test verifies finish-current/no-next-claim behavior.

JSON logs include timestamp/event/worker ID and, when available, run/job/attempt
and step kind. They contain no fixture bodies, API keys or connection diagnostics.
No telemetry stack is added. Database outage logs are rate-limited by idle polling.
The API remains synchronous, asynchronous creation stays HTTP 202, and public GET
exposes the same five fields. Public liveness remains independent of worker/database.

## Tradeoffs and scope

PostgreSQL keeps scheduling and run transitions atomic with a small operational
footprint, but polling costs queries and the application owns fairness and recovery.
Dedicated queues/workflow engines may become appropriate with demonstrated scale,
throughput or orchestration needs; PostgreSQL is not universally superior.

The three catalog entries are explicitly synthetic development fixtures, not real
incidents or held-out gold labels. Conclusions are fixed fixture interpretations,
not intelligence, causal proof, model reasoning or autonomous tool use. No LLM,
approval, UI or F1-05 workflow expansion is implemented.
