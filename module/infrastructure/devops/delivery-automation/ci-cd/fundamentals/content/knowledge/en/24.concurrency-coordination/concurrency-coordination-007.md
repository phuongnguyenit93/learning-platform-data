# Handling Redelivered Events Without Duplicate Deployments

## 1. Why Can One Event Trigger Multiple Deployments?

In CI/CD, a push, merged pull request, created tag, or release request can travel through webhooks, queues, schedulers, and multiple workers. Distributed systems typically deliver events using retryable mechanisms. If the receiver fails to respond in time, disconnects, or crashes after starting work, the sender can redeliver the same event.

Common scenarios:

- The Git provider redelivers a webhook because the endpoint responded slowly or returned an error code.
- A queue redelivers a message when the consumer fails to acknowledge completion before the visibility timeout.
- A worker finishes deploying but terminates before recording success status.
- An operator clicks retry while the previous run is still active.
- Two pipelines receive the same commit and target the same environment simultaneously.
- A scheduler re-runs a job because the previous attempt failed to report a heartbeat or completion.
- A new webhook arrives with a different ID yet represents the exact same release request.

If every received event creates a new deployment, the system can deploy duplicates, contend over environment authority, overwrite a newer version with an older one, or execute side effects multiple times. Consumers must handle receiving the same event multiple times and multiple workers picking up work almost simultaneously.

The goal is to turn repeated delivery into an operation with a stable outcome: the same deployment intent never produces unintended repeated mutations. Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, this preserves consistency across Git events, pipelines, artifacts, environments, and release records.

## 2. Distinguishing Redelivery from New Requests

Not every reception of a similar event is a duplicate. Distinguish among:

- **Delivery duplicate:** the exact same emission is resent, usually carrying the same event ID or delivery ID.
- **Semantic duplicate:** multiple events with different IDs representing the same business intent—for example, two webhooks both requesting deployment of the same commit to the same environment.
- **Concurrent execution:** two workers begin processing the same event or release almost simultaneously.
- **Intentional rerun:** an operator deliberately requests re-executing an operation, even though the commit and artifact have not changed.
- **Stale event:** a valid but outdated event; a newer release has already been deployed beforehand.

These cases require different handling. Event IDs work well for detecting delivery duplicates. A business-level idempotency key detects semantic duplicates. Locks or leases coordinate concurrent execution. Release sequences or revision checks prevent stale events from overwriting newer state. Intentional reruns require a new operation ID or an explicit rerun flag.

If you deduplicate solely by event ID, two webhooks with different IDs for the same commit can still trigger two pipelines. If you deduplicate solely by commit SHA, an intentional rollback to an older commit might be mistakenly blocked. Deduplication keys must accurately reflect the intent you want executed once.

## 3. Delivery Semantics: At-Most-Once, At-Least-Once, and Effectively-Once

Event delivery systems typically follow one of these models:

| Model | Characteristics | Risk |
|---|---|---|
| At-most-once | Event is delivered at most once | Events can be lost if an error occurs before processing |
| At-least-once | Event is redelivered until acknowledged | Consumers must handle duplicates |
| Exactly-once | System attempts to guarantee an effect occurs once within a bounded scope | Hard to guarantee across multiple independent systems |

In practice, webhooks and message queues usually use at-least-once delivery to avoid losing events. Therefore, consumers should assume an event may arrive multiple times.

The term "exactly-once" must be used carefully. A broker can support transactions or deduplication within its own scope, yet if the consumer calls cloud APIs, registries, external databases, or notification services, no single transaction spans everything. Practical designs usually aim for **effectively-once**: repeated deliveries are tolerated, yet through unique constraints, idempotency keys, state tracking, and reconciliation, the final business effect is never duplicated.

## 4. Idempotency Is the Foundation

An idempotent operation can be executed multiple times with the same inputs while producing the same final state as executing once.

Examples:

- Setting an environment's desired image to a specific digest is repeatable.
- Creating a release record keyed uniquely to the same release intent is repeatable.
- Setting a feature flag to `false` is idempotent if the API implements a set semantic.
- Incrementing replica count by one is not idempotent because calling twice increments twice.

Comparison:

~~~text
Non-idempotent:
  POST /deploy
  -> each call creates a new deployment

Idempotent via desired state:
  PUT /environments/staging
  body: { "artifactDigest": "sha256:..." }
  -> setting the same digest multiple times converges to one target state
~~~

HTTP method names do not automatically guarantee idempotency. A `POST` API can still support an idempotency key; a `PUT` API can cause unsafe side effects if poorly designed. Understand the contract of the actual operation.

In CI/CD, prefer expressing desired state—such as "environment X must run artifact digest Y"—rather than issuing imperative "deploy one more time" commands.

## 5. Designing Idempotency Keys

An idempotency key is a stable identifier for a processing intent. Consumers use this key to recognize whether a request has already been accepted or completed.

A key can be composed from:

- Repository or project.
- Event type and action.
- Commit SHA or release ID.
- Artifact digest.
- Target environment.
- Service or component name.
- Operation ID if it is an intentional rerun.

Example key for a deployment intent:

~~~text
deploy:
  repository=payments-api
  environment=production
  artifact=sha256:abc...
  operation=release-2026-042
~~~

In real implementations, fields can be canonicalized and hashed into a compact string. Never use webhook reception timestamp as a primary component, because each retry can carry a different timestamp.

### 5.1. Choosing Key Scope

An overly broad key can block valid operations. For example, using only the commit SHA would block deploying the same commit to staging after it was deployed to dev.

An overly narrow key fails to catch semantic duplicates. For example, using only webhook delivery ID treats two deliveries of the same request as separate operations if the provider generates a new delivery ID.

Reference scopes:

| Intent | Suggested key components |
|---|---|
| Processing a webhook delivery | Provider + delivery ID |
| Building a commit for a pipeline | Repository + commit SHA + pipeline definition/version |
| Deploying an artifact to an environment | Service + environment + artifact digest + release operation |
| Running a migration once | Migration ID + database/tenant scope |
| Processing a business operation | Tenant + business operation ID |
| Intentional rerun | New operation ID + release target |

Clearly decide whether a rerun means resuming the old operation, retrying a failed operation, or creating a new release operation. Those three cases must never accidentally share the same key.

## 6. Deduplication Store and Unique Constraints

Consumers must persist a record of received events. You can use a relational database, key-value store, or broker deduplication mechanism. For deployment flows needing auditability, a stateful table is usually far more useful than a boolean cache.

PostgreSQL schema example:

~~~sql
CREATE TABLE processed_events (
    consumer_name   VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(300) NOT NULL,
    event_id        VARCHAR(200),
    payload_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    result_ref      VARCHAR(300),
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    owner_id        VARCHAR(120),
    lease_until     TIMESTAMPTZ,
    fencing_token  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (consumer_name, idempotency_key)
);
~~~

The unique primary key guarantees two workers cannot simultaneously insert two rows for the same consumer and key. The `consumer_name` column lets multiple independent consumers process the same event for their own purposes.

`payload_hash` detects cases where the same key arrives with different content. If a key is built from insufficient fields, two distinct requests could collide mistakenly. When a matching key arrives with a different payload hash, flag it as a conflict and investigate rather than silently ignoring it.

### 6.1. Accepting Events via Atomic Insert

Example:

~~~sql
INSERT INTO processed_events (
    consumer_name,
    idempotency_key,
    event_id,
    payload_hash,
    status
)
VALUES (
    :consumer,
    :key,
    :event_id,
    :payload_hash,
    'RECEIVED'
)
ON CONFLICT (consumer_name, idempotency_key) DO NOTHING
RETURNING idempotency_key;
~~~

If the statement returns one row, the worker successfully created the tracking record for the key. If no rows are returned, the key already exists and the worker must read existing state to decide whether to skip, wait, retry, or return the completed result.

Never use a "SELECT to check if absent, then INSERT" pattern without a unique constraint or proper lock. Two workers can both `SELECT` "not found" and both `INSERT`. That is a classic race condition.

## 7. Processing States and State Machine

A deduplication record should capture execution progress, not just `true`/`false`.

Common states:

- **RECEIVED:** event accepted.
- **PROCESSING:** a worker currently owns the active attempt.
- **SUCCEEDED:** required effects completed and verified.
- **RETRYABLE_FAILED:** transient failure; eligible for retry.
- **TERMINAL_FAILED:** non-retryable error; requires intervention.
- **CONFLICT:** same idempotency key with inconsistent payload or intent.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING
    PROCESSING --> SUCCEEDED
    PROCESSING --> RETRYABLE_FAILED
    PROCESSING --> TERMINAL_FAILED
    PROCESSING --> CONFLICT
    RETRYABLE_FAILED --> PROCESSING
    PROCESSING --> PROCESSING: lease expired and another worker claimed
    SUCCEEDED --> [*]
    TERMINAL_FAILED --> [*]
    CONFLICT --> [*]
~~~

When receiving a duplicate:

| Current state | Suggested action |
|---|---|
| `SUCCEEDED` | Return stored result; do not execute side effects again |
| `PROCESSING` with active lease | Do not start concurrently; return accepted/in-progress or retry later |
| `RETRYABLE_FAILED` | Re-claim per policy and increment attempt count |
| `TERMINAL_FAILED` | Do not auto-retry indefinitely; escalate for handling |
| `CONFLICT` | Quarantine and investigate key/payload mismatch |
| `PROCESSING` with expired lease | Re-claim only after verifying prior ownership expired |

Never mark `SUCCEEDED` immediately upon receiving an event. If the worker crashes before doing the work, the event appears complete even though no effect occurred. Similarly, never mark complete solely after calling an API returning HTTP 202 if the underlying async task has not actually reached the desired state; define completion semantics explicitly.

## 8. Avoiding Race Conditions When Multiple Workers Receive One Event

Two workers can receive the same message due to retries or queue redelivery. Checking state in application code alone is not enough to stop both from starting.

Common mechanisms:

- Unique constraint on the idempotency key.
- Atomic insert or compare-and-set.
- Row-level lock within a short transaction.
- Time-bounded lease for the owning worker.
- Distributed lock for shared resources.
- Fencing tokens to stop old workers from writing after losing ownership.

With a database, claim the record using a conditional `UPDATE`:

~~~sql
UPDATE processed_events
SET status = 'PROCESSING',
    attempt_count = attempt_count + 1,
    owner_id = :worker_id,
    lease_until = now() + INTERVAL '60 seconds',
    fencing_token = fencing_token + 1,
    updated_at = now()
WHERE consumer_name = :consumer
  AND idempotency_key = :key
  AND (
       status IN ('RECEIVED', 'RETRYABLE_FAILED')
       OR (status = 'PROCESSING' AND lease_until < now())
  )
RETURNING idempotency_key, owner_id, lease_until, fencing_token;
~~~

Only the worker receiving a row from `RETURNING` holds the claim. The worker must pass the returned `owner_id` and `fencing_token` on all subsequent lease renewals or status updates. This statement must run atomically in the database; actual lease duration must align with heartbeat intervals and processing time.

Never hold a database transaction open across a long-running deployment. Claim in a short transaction, execute work outside the transaction, and then update status conditionally by owner/token to prevent overwriting another worker's progress.

## 9. Leases, Heartbeats, and Fencing Tokens

A permanent lock can wedge the system if a worker dies. Leases solve this by letting ownership expire after a bounded duration.

A lease typically includes:

- Resource key, such as service + environment.
- Owner ID or worker ID.
- Expiration timestamp.
- Heartbeat to extend while still processing.
- Monotonically increasing fencing token or generation.

Example:

~~~text
resource: payments-api:production
owner: worker-17
lease_until: 2026-11-18T09:15:00Z
fencing_token: 1842
~~~

When a new worker claims after lease expiration, the system issues a higher fencing token, such as 1843. All subsequent write operations must validate the token. If the old worker wakes up after a long pause and tries writing with token 1842, the target rejects it as stale.

Leases alone do not stop stale workers. A worker can freeze, its lease expires, another worker takes over, and the old worker resumes execution. Fencing tokens only work when the receiving component validates and rejects stale tokens. If an external deployment API lacks fencing support, add generation or desired-revision checks in the orchestration layer.

Heartbeats also do not prove the worker is making business progress. Bound the maximum number of renewals and handle workers that stop advancing.

## 10. Distinguishing Event Deduplication from Deployment Locks

These two mechanisms solve different problems:

- **Event deduplication:** ensures one processing intent never spawns multiple independent jobs.
- **Deployment lock:** ensures only one process at a time mutates a conflicting environment or resource.

Two distinct releases, each with its own idempotency key, can still deploy to production simultaneously. Deduplication does not stop them from running concurrently. Conversely, a lock only serializes execution; once the first worker finishes, a second worker could still redeploy the exact same artifact unless deduplication or desired-state checks exist.

A complete design typically needs both:

1. Receive event and create an operation keyed by idempotency key.
2. Claim the operation so only one worker handles that key.
3. Acquire the service/environment lock before modifying the environment.
4. Inspect actual state and current release.
5. Apply changes toward desired state.
6. Verify artifact digest and environment health.
7. Record outcome and release the lock.

## 11. Coordinating Pipelines Targeting the Same Environment

An environment like staging or production should normally allow only one active mutating deployment at a time, unless the system supports isolated zones.

Lock keys should reflect the contention scope:

~~~text
deployment-lock:payments-api:production
deployment-lock:catalog-api:production
deployment-lock:payments-api:staging
~~~

In this example, deploying `payments-api` to production does not block `catalog-api` in production if the two services share no conflicting resources. However, two production deployments of `payments-api` must be serialized.

CI platforms often offer concurrency groups or environment deployment queues. Configure them per service and environment rather than lumping every pipeline into one global lock unnecessarily.

If using database locks or a distributed lock service, define:

- Lock key and TTL.
- Renewal/heartbeat mechanism.
- Behavior when a worker dies.
- Fencing token or generation.
- When the lock is released.
- How long-held locks are detected.
- Rules for handling manual out-of-band actions.

## 12. Preventing Older Releases from Overwriting Newer Releases

Another race condition occurs when an older pipeline runs slower than a newer pipeline.

For example:

1. Commit A creates Pipeline A.
2. Newer Commit B creates Pipeline B.
3. Pipeline B deploys first and production runs B.
4. Pipeline A finishes late and deploys A afterward.

Even though each pipeline ran only once, the final outcome is wrong because the older release overwrote the newer release.

Check release freshness right before mutating the environment. Options include:

- Commit ancestry or current branch head checks.
- Monotonically increasing release sequence/generation.
- Desired revision stored in the deployment controller.
- Compare-and-set on the current deployment revision.
- Policy permitting intentional rollbacks with a distinct operation ID.

Never rely solely on timestamps because machine clocks can drift. Sequence numbers or revisions issued by an authoritative source are much clearer.

An authorized rollback to an older artifact must still be permitted when approved. Therefore, "artifact has an older or earlier SHA" is not enough to reject; distinguish an accidental stale pipeline from an intentionally created rollback intent.

## 13. Handling Retries and Timely Acknowledgements

With message queues, consumers normally pull a message, process it, and then send an acknowledgement (`ack`). If `ack` occurs before effects finish, messages can be lost if the worker crashes. If `ack` occurs after effects finish yet the worker dies before `ack`, the queue redelivers and the consumer must deduplicate.

A common sequence:

1. Receive message.
2. Verify signature/origin and schema.
3. Create or read the idempotency record.
4. Claim processing ownership.
5. Execute work.
6. Verify result.
7. Record `SUCCEEDED` status.
8. Acknowledge (`ack`) message.

If recording `SUCCEEDED` and acknowledging do not share a single transaction with the broker, a failure window remains between the two operations. That is why deduplication state must persist across redeliveries.

For queues with visibility timeouts, set timeouts appropriately for processing duration or extend them via heartbeats. If the timeout is too short, the queue may deliver the message to a second worker while the first is still running. Even so, never rely on visibility timeouts to guarantee exclusivity; atomic claims and idempotency are still required.

## 14. Backoff, Retry Budgets, and Dead-Letter Queues

Infinite, immediate retries amplify load while a system is degraded. A retry policy should include:

- Exponential backoff.
- Jitter to prevent thundering-herd retries.
- Maximum retry count or retry budget.
- Separation of transient errors vs. permanent errors.
- Per-call timeouts.
- Dead-letter queue (DLQ) or quarantine queue.
- Controlled replay capability after fixing root causes.

Example retry schedule with jitter:

~~~text
attempt 1: near immediate
attempt 2: a few seconds
attempt 3: tens of seconds
attempt 4: a few minutes
after retry budget: route to dead-letter
~~~

Do not retry validation errors, invalid webhook signatures, or unsupported payloads as if they were network errors. Those belong in quarantine for investigation. Conversely, timeouts or HTTP 503 responses can be retried when operations are idempotent.

When replaying a message from a dead-letter queue, preserve the event identity so deduplication recognizes the replay—unless an operator intentionally creates a new operation. Log the operator replaying, the reason, and a link to the incident or change request.

## 15. Transactional Inbox and Outbox

When a service receives an event and updates its own database, the **transactional inbox** pattern persists event receipt and business updates within a single transaction.

Example:

~~~sql
BEGIN;

INSERT INTO event_inbox (
    consumer_name,
    idempotency_key,
    received_at
)
VALUES (
    :consumer,
    :key,
    now()
)
ON CONFLICT DO NOTHING;

-- Apply business updates only if INSERT actually inserted one row.
-- Update business state and mark inbox within the same transaction.

COMMIT;
~~~

This SQL is pseudocode for the sequence. In real implementations, check the inserted row count and perform business updates only if the worker owns the key. Keeping the inbox insert and business update in the same transaction ensures a rollback leaves no false receipt record.

**Transactional outbox** solves the publishing side: write business changes and an outbox row in the same transaction, then a publisher emits events from the outbox. The publisher may redeliver if it crashes after sending but before marking sent, so downstream consumers must still be idempotent.

Inbox/outbox narrows the loss or duplication window between a database and broker, yet does not turn a chain of independent systems into a global exactly-once transaction.

## 16. Handling External Side Effects

A deployment often calls multiple external services:

- Container registries or artifact repositories.
- Cloud provider APIs.
- Kubernetes APIs.
- DNS or load balancers.
- Feature flag services.
- Notification or chat services.
- Release record stores.

Not every API supports idempotency keys. Design around actual capabilities:

- Prefer desired-state APIs wherever available.
- Pass idempotency keys when providers support them.
- Attach operation IDs in metadata or annotations.
- Read state before creating new resources.
- After a timeout, query whether the previous call succeeded before calling again.
- Record external resource IDs for resumption or reconciliation.
- Use bounded retries and handle indeterminate outcomes.

For example, if a deploy request times out, you cannot assume the cloud provider never received the command. Immediately calling again could create a second deployment. Query the deployment first by operation ID, release ID, or desired digest to determine its actual state.

## 17. Git Webhooks and CI/CD Events

Webhooks typically carry a delivery ID, event type, repository, ref, commit SHA, and metadata. Consumers should:

1. Verify the webhook signature per the provider's specification.
2. Check timestamps or anti-replay controls if supported by the provider.
3. Record delivery ID to detect identical redeliveries.
4. Build a semantic idempotency key from repository, event/action, commit or release intent, and environment.
5. Check whether the branch/ref remains a valid target.
6. Enqueue the operation.
7. Return a fast response to the webhook once durably persisted; never keep the HTTP request open across the entire deployment.

Example build key:

~~~text
build:repository=payments-api:commit=4f8c2a1:pipeline=v3
~~~

Example deploy key:

~~~text
deploy:service=payments-api:environment=staging:artifact=sha256:abc123:operation=release-42
~~~

If the same commit needs to be intentionally deployed again, create a new operation ID and record the reason. Never alter keys arbitrarily just to bypass deduplication, as that hides unintended retries or duplicates.

## 18. Checking Desired State Before Deploying

A good consumer asks not only "was this event processed?" but also "is the environment already in the state this event requests?"

For example, the release record states production already runs digest D. A duplicate webhook requests deploying D to production. The consumer reads actual state, confirms the environment already runs D, and marks the operation complete without redeploying.

Conversely, if the environment is running a different digest, the consumer must verify whether the operation remains the latest authorized request.

Reconciliation flow:

~~~mermaid
flowchart TD
    A["Receive event"] --> B["Verify and derive idempotency key"]
    B --> C{"Key already SUCCEEDED?"}
    C -- "Yes" --> D["Return stored result"]
    C -- "No" --> E["Claim operation"]
    E --> F["Acquire service/environment lock"]
    F --> G["Read desired and actual revision"]
    G --> H{"Environment already has digest?"}
    H -- "Yes" --> I["Mark SUCCEEDED, skip redeploy"]
    H -- "No" --> J{"Operation valid and latest?"}
    J -- "No" --> K["Skip stale event"]
    J -- "Yes" --> L["Apply desired state"]
    L --> M["Verify digest and health"]
    M --> N["Record outcome and release lock"]
~~~

Reconciliation is valuable because it also handles cases where a worker had no idea how far the previous attempt progressed. Instead of blindly repeating side effects, it observes actual state and converges toward desired state.

## 19. Distinguishing Retry, Replay, and Manual Rerun

These three actions must be tracked separately:

| Action | Meaning | Idempotency |
|---|---|---|
| Retry | Retrying the same operation after a transient failure | Keep the exact same key |
| Replay | Re-emitting a stored event for consumer reprocessing | Usually preserves event identity; may increment replay attempt |
| Rerun | Operator intentionally creates a new execution request | Generate a new operation ID and log reason |

If a retry generates a new key, the consumer treats it as brand-new work and can duplicate side effects. If an intentional rerun reuses a key already marked `SUCCEEDED`, the consumer skips it even though the operator wants a new release operation executed.

A good operational UI should display event ID, idempotency key, status, attempt count, and operation ID. Selecting rerun should require explicitly recording a new intent.

## 20. Retention of Deduplication Records

Deleting deduplication records too early allows an old replayed message to look brand new and re-execute side effects.

Record retention should be greater than or equal to:

- Maximum webhook/queue retry window.
- Maximum backlog dwell time.
- Dead-letter retention before replay.
- Operational replay lookback window.
- Release or business audit retention requirements.

For operations with lasting impact like production deployments or migrations, persist durable release/operation history rather than relying on short-TTL caches.

When pruning records, archive older data to audit storage or retain tombstones containing key, outcome, and timestamp. Never delete `PROCESSING` records with active leases or records tied to open incidents.

## 21. Security and Event Integrity

Idempotency does not replace authentication. Attackers can send forged payloads with valid keys or deliberately flood the deduplication store.

Controls needed:

- Verify webhook signatures and sender origins.
- Validate schema, payload size, and required fields.
- Bind events to authorized repositories/projects.
- Enforce branch, tag, and environment policies.
- Never execute arbitrary artifacts or commands pulled from untrusted payloads.
- Scope worker permissions and credentials per environment.
- Write audit logs without storing secrets in payload logs.
- Apply rate limits and anomaly detection on incoming events.
- Enforce authorization on replay/rerun actions.

Payload hashes detect same-key collisions with differing content. On conflict, never overwrite the original record or blindly pick the later payload without verification rules.

## 22. Observability and Troubleshooting

To operate deduplication effectively, measure both duplicates and job execution state.

Useful metrics:

- Total events received by type and source.
- Delivery duplicate and semantic duplicate counts.
- Operations newly created, skipped, or returning cached outcomes.
- Worker claim successes/failures.
- Expired leases and fencing rejections.
- Retry counts, retry ages, and dead-letter counts.
- Time spent in `PROCESSING` state.
- Deployment operations blocked by locks.
- Stale events skipped.
- Rate at which the environment already matched desired digest when events arrived.

Logs should include event ID, masked or hashed idempotency key, operation ID, repository, commit SHA, artifact digest, environment, worker ID, and attempt. Avoid logging raw payloads if they contain sensitive data.

Alert when operations remain `PROCESSING` too long, leases repeatedly expire, duplicates spike abnormally, events land in dead-letter queues, or two pipelines continually contend for the same environment lock.

## 23. Example Safe Deployment Handling Flow

Suppose the Git provider sends a webhook for a new commit on the `checkout` service. The endpoint receives the webhook twice because the first response was slow.

Desired flow:

1. Both requests pass signature verification.
2. Delivery ID and semantic key are derived from repository, commit, service, environment, and release operation.
3. The first request creates the operation; the second hits the unique constraint and reads the existing operation's status.
4. Only one worker claims the operation.
5. The worker acquires the lock for `checkout`/`production`.
6. The worker verifies branch head and desired artifact digest.
7. If the environment already runs that digest, the worker records completion without calling deploy again.
8. Otherwise, the worker instructs the controller to set desired state to the approved digest.
9. The worker waits for rollout and verifies image digest, health checks, and policy.
10. The worker records `SUCCEEDED`, releases the lock, and acknowledges the message.
11. The duplicate request receives the status/result of the existing operation.

If the worker dies after the controller receives desired state but before recording `SUCCEEDED`, the message can be redelivered. A new worker re-claims after lease expiry, reads actual state, sees the digest already matches, and finalizes the record without creating a second deployment.

## 24. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Checking only event ID | Misses semantic duplicates with different delivery IDs | Add a business-intent idempotency key |
| `SELECT` then `INSERT` without unique constraint | Two workers process simultaneously | Use atomic insert/claim and unique keys |
| Marking complete before side effects | Worker crashes lose the work | Mark `SUCCEEDED` only after verifying effects |
| Acking queue before durable persistence | Messages lost on worker errors | Ack only after state is durably saved |
| Holding DB transactions across deployments | Long locks and connection exhaustion | Claim briefly, work outside transactions, update conditionally |
| Leases without fencing | Old workers write after losing lease | Use generations/fencing validated at the target |
| Deployment locks without deduplication | Same release still deploys repeatedly sequentially | Pair locks with idempotency/digest checks |
| Deduplication without deployment locks | Two distinct releases still deploy concurrently | Lock by service/environment |
| Generating new idempotency keys on retries | Side effects duplicate | Keep key for retries; create new keys only for intentional reruns |
| Pruning dedupe records too early | Old replays re-execute effects | Size retention to retry, backlog, replay, and audit windows |
| Letting old pipelines overwrite newer releases | Environment reverts to stale revision | Check generation or desired revision |
| Treating timeouts as definite failures | Retries create a second operation | Query external operation state before retrying |

## 25. Checklist for Handling Redelivered Events

**Identification and Ingestion**

- [ ] Event source and signature are verified.
- [ ] Appropriate event ID and idempotency keys exist.
- [ ] Keys distinguish service, environment, and operation scope.
- [ ] Payload hashes catch same-key requests with differing content.
- [ ] Retry, replay, and rerun are distinguished.

**Deduplication and Concurrency**

- [ ] Unique constraints or atomic claim mechanisms exist.
- [ ] Clear state machine and failure states exist.
- [ ] Workers execute only after claiming succeeds.
- [ ] Long tasks use leases/heartbeats.
- [ ] Fencing tokens or generation checks are used where needed.
- [ ] Deployment locks are scoped by service/environment.
- [ ] Stale events cannot overwrite newer revisions.

**Side Effects and Recovery**

- [ ] Operations prefer desired-state/idempotent APIs.
- [ ] Timeouts query actual state before retrying.
- [ ] DB effects and inbox records share appropriate transactions.
- [ ] Outbox/consumers tolerate duplicates and retries.
- [ ] Acknowledgements happen only after durable state persistence.
- [ ] Retries use backoff, budgets, and dead-letter queues.
- [ ] Deduplication records are retained long enough.
- [ ] Replays/reruns have audit logs and proper permissions.

**Observability**

- [ ] Metrics track duplicates, retries, lock contention, and lease expirations.
- [ ] Logs include event/operation/release identities.
- [ ] Alerts exist for stuck operations or stale events.
- [ ] Actual digests can be reconciled against desired digests.
- [ ] Runbooks cover conflict and replay handling.

## 26. Conclusion

Redelivered events are normal in webhook, queue, and distributed pipeline systems. Consumers must assume deliveries can repeat, workers can race, and timeouts do not prove external operations never occurred.

Idempotency keys and deduplication records identify identical intent; unique constraints and atomic claims stop race conditions; leases and fencing coordinate workers; deployment locks serialize environment mutations; and desired-state reconciliation enables safe recovery after mid-flight interruptions. Retries preserve operation identity, while intentional reruns create new operations with audit trails.

No single lock replaces every safeguard. By combining properly scoped identifiers, processing state tracking, release revision checks, and actual-state verification, pipelines can receive the same event repeatedly while preserving a single, traceable, recoverable deployment outcome.
