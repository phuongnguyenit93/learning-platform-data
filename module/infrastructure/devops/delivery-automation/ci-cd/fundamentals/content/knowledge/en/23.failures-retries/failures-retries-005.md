# Avoiding Retrying Publish or Deploy Operations That Cause Duplicate Side Effects

Retries help pipelines recover from transient failures. However, many CI/CD operations create or mutate external state: publishing packages, pushing images, creating releases, sending notifications, running database migrations, creating deployments, shifting traffic, or triggering background jobs. If the pipeline does not know how far the previous call progressed, retrying can produce duplicate releases, overwrite artifacts, run migrations twice, send duplicate alerts, or repeat side effects.

The danger is that a request timeout or dropped connection does not prove the operation never happened. The server may have already committed the change while the response was lost in transit. The pipeline sees an error even though the target system completed the work. Blind retrying turns a communication glitch into duplicate impact.

The safe design is to understand operation semantics, use idempotency keys or deduplication wherever possible, persist durable operation state, bound retries, and inspect target system state before resending. Whenever you cannot prove the prior call caused no side effect, reconcile before retrying.

## 1. Why retrying publish or deploy operations can be dangerous

A publish/deploy command typically passes through several stages: authentication, sending the request, target ingestion, persisting state, executing side effects, and returning a response. Failure can strike at any point.

For example, a pipeline sends a request to publish version 3.2.0. The registry saves the package successfully, but the connection resets before the pipeline receives the HTTP response. The job exits as failed. If retried using a fresh creation call, the system might:

- Create duplicate release records or notifications.
- Overwrite a mutable tag now pointing to a different artifact.
- Create two deployments or two rollouts targeting the same service.
- Re-run migrations or hooks with side effects.
- Provision two cloud resources if the API lacks idempotency.
- Re-send emails, webhooks, or release events.
- Bump versions or create extra unintended packages.
- Cause pipeline state and target system state to drift apart.

### 1.1. A timeout does not mean the operation failed

Suppose a pipeline sends a request to a deployment API:

1. The pipeline requests deploying release R42.
2. The server receives the request and begins processing.
3. The server creates the deployment and updates state.
4. The response is lost due to a network timeout.
5. The pipeline observes only the timeout and marks the job failed.

At this point, the deployment may have started, be in progress, or have already succeeded. Sending a new deployment creation request risks creating a second operation.

This is an ambiguous outcome: the caller does not know whether the previous operation was committed. Query status by operation ID or reconcile actual state before resending.

~~~mermaid
sequenceDiagram
    participant P as CI Pipeline
    participant D as Deployment API
    participant C as Cluster
    P->>D: Create deployment R42
    D->>C: Apply desired state
    C-->>D: Accepted / progressing
    D--xP: Response lost / timeout
    Note over P: Pipeline does not know if operation was created
    P->>D: Query status by operation ID
    D-->>P: R42 is progressing or succeeded
    Note over P,D: Track existing operation; do not create a new one
~~~

### 1.2. Distinguishing pre-receipt failures from post-commit failures

| Scenario | What does the caller know? | Safe action |
|---|---|---|
| Validation rejects before processing | Request was clearly rejected | Fix input; do not retry the same invalid payload |
| DNS/connect fails before sending request | Reasonable basis that server never received request | May retry per policy |
| Timeout while sending or awaiting response | Uncertain whether server received/committed | Query operation or reconcile first |
| Server returns 5xx | Error may be pre- or post-commit depending on API | Rely on contract and idempotency; do not retry by default |
| Server returns 429 with `Retry-After` | Rate-limited as indicated | Wait per guidance; still need idempotency for mutating operations |
| Response succeeded but pipeline cancelled before saving state | Target system may have finished | Query target state and update release record |
| Client retries due to process restart | Prior attempt may have succeeded | Reuse the same operation/idempotency key |

You cannot classify every HTTP status code as safe or unsafe without knowing the API's semantics. An HTTP 500 can be returned after the server already committed; a timeout can happen before the request ever left the host. Rely on the target service's contract and observed evidence.

## 2. Classifying operations by retryability

Before adding retries, determine what class of operation you are performing.

| Operation type | Examples | Default retryability |
|---|---|---|
| Read-only | GET release status, read digest, query deployment | Generally safe if request has no side effects |
| Idempotent write | Set desired replica count to 4, set config to a deterministic value | Safe to retry same payload if API genuinely guarantees idempotency |
| Create with deduplication | Create deployment with unique idempotency key/operation ID | Safe to retry with the same key and payload |
| Create without deduplication | Create new release, package, or resource per call | Do not retry blindly |
| Append/event publish | Send new message, webhook, or event | Requires event ID, deduplication, or transactional outbox |
| Non-idempotent business action | Charge payment, refund, send email, generate invoice | Retry only with an idempotency contract or verified non-execution |
| Irreversible action | Delete data, rotate key, issue external transaction | Requires dedicated recovery flow and state confirmation |

### 2.1. Idempotent vs. non-idempotent

An operation is idempotent if executing it multiple times with the same intent and inputs produces no change in final state beyond the first execution.

Example setting desired configuration:

~~~http
PUT /environments/staging/services/orders/config
Content-Type: application/json

{"replicas": 4, "featureFlag": "disabled"}
~~~

If the API replaces the configuration state with that exact payload, resending the same request yields the same desired state of four replicas and a disabled flag.

Conversely, a resource creation call:

~~~http
POST /deployments
Content-Type: application/json

{"service": "orders", "version": "3.2.0"}
~~~

may create a new deployment on every call. Sending it twice can create two deployment records or trigger two rollouts.

You cannot infer safety from the HTTP verb alone. `PUT` is conventionally designed to be idempotent, yet an implementation can still emit secondary side effects; `POST` can be idempotent if the API supports idempotency keys. Verify the actual contract.

### 2.2. State idempotency vs. side-effect idempotency

An API can bring a resource to the exact same final state while still triggering side effects repeatedly. For example, applying a manifest a second time leaves the Pod template unchanged, yet the deploy script still sends notifications, runs migration hooks, or fires webhooks.

Evaluate both:

- **State idempotency:** does the resource's final state stay identical across repeated calls?
- **Effect idempotency:** are external actions—publishing events, sending emails, charging payments, or running migrations—avoided on repeats?

A safe deployment controls both state and side effects.

## 3. Idempotency keys: identifying the same intent

An idempotency key uniquely identifies a single business intent or operation. The caller generates the key once, persists it durably, and reuses that exact key across every retry of the same operation.

Example:

~~~http
POST /releases
Idempotency-Key: release-orders-3.2.0-commit-a1b2c3d
Content-Type: application/json

{
  "service": "orders",
  "version": "3.2.0",
  "artifactDigest": "sha256:abc123..."
}
~~~

If the first request was processed but the response was lost, a repeated request carrying the same key can receive the stored result instead of creating a second release.

### 3.1. Key design rules

A key should:

- Represent one specific logical operation, not just one job execution attempt.
- Remain stable across retries of the same operation.
- Differ whenever a user genuinely initiates a new operation.
- Have clear scoping such as tenant, service, environment, or resource.
- Contain no secrets, passwords, tokens, or personal data.
- Be stored alongside release/deployment records for investigation.

A key can combine operation type, service, environment, artifact digest, and release request ID. Avoid using only the pipeline run ID if a rerun generates a new run ID for the same release request; doing so breaks deduplication across reruns.

### 3.2. The same key must accompany the same payload

The server should store a fingerprint/hash of the first payload bound to the key. If a caller sends the same key with a different payload, the server should reject it with a conflict rather than silently returning the old result or triggering a new side effect.

| Request | Key | Payload | Expected outcome |
|---|---|---|---|
| First attempt | K-42 | Deploy digest A to staging | Create operation K-42 |
| Retry after timeout | K-42 | Same digest A, same staging | Return status/result of K-42 |
| Mistaken different payload | K-42 | Digest B or production | Conflict; create no side effect |
| Intentional new release | K-43 | Digest B to staging | New operation |

### 3.3. Servers must persist idempotency records durably

A server-side implementation typically stores:

- The key and its scope.
- The payload fingerprint.
- Operation status.
- Created operation/resource ID.
- Cached response or returnable result.
- Creation, update, and expiration timestamps.
- Principal that initiated the operation.

Writing the idempotency record and applying the side effect require transactional boundaries or consistent recovery mechanisms. If the server creates the resource first and saves the key later, a mid-flight crash lets a retry create duplicates. If it marks the key completed before the side effect succeeds, callers can receive false-success responses.

## 4. State machines for operations with side effects

Do not record only job status as success/failed. A publish or deploy operation should maintain its own state on the target system.

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> InProgress: Valid request received
    InProgress --> Succeeded: Side effect completed
    InProgress --> Failed: Confirmed failed without commit
    InProgress --> Unknown: Connection lost / timeout, uncertain
    Unknown --> InProgress: Reconciliation confirms still running
    Unknown --> Succeeded: Query confirms completed
    Unknown --> Failed: Query confirms uncommitted or safely stopped
    Failed --> Requested: Create new operation after fixing conditions
    Succeeded --> [*]
~~~

The `Unknown` state is critical. Never convert `Unknown` directly to `Failed` solely because a client timed out. If the target system has no operation query API, reconcile created resources, artifact digests, release records, or audit logs before deciding to resend.

### 4.1. Avoiding "sent without a trace"

Pipelines should persist the operation ID immediately when returned by the server or supply a deterministic ID upfront. If the client loses the response before learning the ID, the idempotency key enables querying the operation. Persist the key and payload fingerprint before sending the request—not only after the job succeeds.

### 4.2. Handling concurrent requests

Two jobs might retry the same operation simultaneously due to reruns, duplicate webhooks, or worker recovery. The server needs an atomic claim or unique constraint on the idempotency key so only one request creates the operation; the other receives an in-progress status or the stored result.

Checking keys solely in one process's memory is insufficient if the server runs multiple replicas or restarts. Deduplication requires shared durable storage and atomic operations.

## 5. Exactly-once is hard; design for effectively-once outcomes

In distributed systems, a caller cannot tell whether the server committed when a response is lost. Networks can retransmit requests; consumers can redeliver messages; processes can crash between applying a side effect and recording completion. Consequently, end-to-end "exactly once" rarely comes from a single retry toggle.

Practical implementations typically combine:

- Delivery that may be at-least-once (a message or request can arrive multiple times).
- A stable ID on every event/operation.
- Consumer deduplication by ID backed by durable storage.
- Recording the business effect and processed status inside the same transaction where possible.
- When calling external systems, using the provider's idempotency contract or reconciliation flows.
- Bounded retries that never mint a new operation ID for the same intent.

The objective is a single business effect even though requests or messages may be delivered more than once.

## 6. Publishing artifacts: avoiding duplicate releases or overwritten tags

Artifact publishing involves varying semantics. Pushing an OCI image layer is content-addressed by digest; attaching or moving a tag is a separate state mutation. Publishing a package version may be rejected if the version already exists, or overwritten depending on registry policy.

### 6.1. Published versions should be immutable

For already-published package versions, enforce a no-overwrite rule. If version 3.2.0 already exists, a retry must verify whether the existing artifact has the same digest:

- If digests match, treat the operation as complete and proceed.
- If digests differ, stop and investigate; never overwrite to "fix" state.
- If the package does not exist and the registry confirms it was not published, proceed under safe mechanisms.

Avoid reusing a fixed overwritable version across builds. Use clear version/release identities and record digests.

### 6.2. Container images: tags and digests

Tags like `orders:3.2.0` or `orders:latest` can move depending on registry policy. Digests identify exact image content. When retrying a push:

1. Inspect the image manifest by existing tag/digest.
2. Compare the digest against the built artifact.
3. If digests match, do not create another release just to repeat the push.
4. If the tag points to a different digest, stop and resolve the conflict.
5. Deploy by digest rather than mutable tag.

Example inspecting an image digest with a registry tool:

~~~bash
docker build -t registry.example.com/orders:3.2.0 .
docker push registry.example.com/orders:3.2.0

# Capture the digest from push output or registry metadata.
# On retry, query tag/digest before pushing again.
docker buildx imagetools inspect registry.example.com/orders:3.2.0
~~~

The `inspect` command is only an illustrative query; how you retrieve digests depends on your tooling and registry. Never assume re-pushing a tag is safe if tags are overwritable.

### 6.3. Package registries

For npm, Maven, NuGet, or internal registries, understand the policy on published versions. Some registries forbid overwriting versions; some internal systems may permit it. Pipelines should:

- Use unique versions for releases.
- Check whether the package/version already exists.
- Compare checksums or metadata before treating it as a success.
- Never delete and republish the same version as a retry workaround.
- Store registry URL, package coordinates, version, and digest/checksum in the release record.

## 7. Deploying: declarative apply vs. imperative side effects

Desired-state deployments are usually safer to repeat than imperative commands that create new objects on every invocation.

Example desired-state declaration:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 4
  template:
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders@sha256:abc123...
~~~

Applying the same manifest declaratively converges the cluster to the same desired state. However, hooks, migrations, notifications, one-off Jobs, or helper scripts can still cause repeated side effects. Declarative apply does not automatically make every part of a release idempotent.

### 7.1. Desired-state reconciliation

With GitOps or controllers, the pipeline updates a versioned desired state and a controller continuously reconciles actual state toward desired state. Retrying an update to the same desired state is typically less risky than creating a brand-new deployment operation each time.

Even so, watch out for:

- Pre/post-deploy hooks that may run again.
- Kubernetes Jobs that may spawn new executions depending on naming, TTL, and controller logic.
- Helm hooks that execute migration commands or external calls.
- Imperative scripts that create new resources per run.
- Controllers that guarantee resource state convergence without guaranteeing application-level side effects execute only once.

### 7.2. Separating deployment state from release side effects

Split these stages cleanly:

1. Identify artifact digest and release ID.
2. Update deployment desired state.
3. Wait for rollout by deployment ID/revision.
4. Run post-deployment validation with its own operation ID.
5. Send notifications or publish release announcements only after confirming final state.
6. If notifications fail, retry notifications by event ID; never re-run the entire deployment.

## 8. Database migrations and deployment hooks

Database migrations carry clear side effects. A script may add columns, backfill data, build indexes, or alter constraints. If a client times out after the database commits, re-running the migration can fail or mutate data a second time.

Safeguards:

- Use unique migration versions/IDs and a migration ledger.
- Record migration completion in the same transaction as DDL/DML where the database supports it.
- Design idempotent migrations where appropriate, such as checking schema state before adding objects.
- Do not rely solely on "object already exists"; verify the existing object matches the intended definition.
- Run backfills in batches with checkpoints and resume criteria.
- Enforce unique constraints or idempotency keys to block duplicate writes.
- Separate expand migrations from contract migrations.
- Never run migrations from every replica at application startup; use a coordinated job/migration runner with locking.

Example migration ledger table:

~~~sql
CREATE TABLE schema_migrations (
    migration_id VARCHAR(200) PRIMARY KEY,
    checksum VARCHAR(128) NOT NULL,
    applied_at TIMESTAMP NOT NULL
);
~~~

Before executing a migration, the runner checks migration ID and checksum. If already applied with the same checksum, treat it as complete. If the same ID has a different checksum, halt and require investigation; never re-run modified logic under an already-applied identifier.

## 9. Messages, webhooks, and notifications: event IDs and outbox

Message and webhook delivery is typically at-least-once. If a producer succeeds in sending but misses the acknowledgment, it may resend. Consumers must deduplicate by event ID or business key.

A consumer can maintain a processed-events table:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside the event-processing transaction, the consumer records the event ID and updates business state. If the event ID already exists, skip executing the business effect again.

### 9.1. Transactional outbox

When an application must both update a database and publish an event, write the business change and an outbox record inside the same transaction. A publisher reads the outbox and dispatches the event; if redelivered, consumers deduplicate by event ID.

An outbox does not turn the message broker into an exactly-once system. It prevents losing the link between database commit and publish intent; consumers still need idempotency/deduplication.

### 9.2. Webhooks and notifications

When sending release webhooks or emails:

- Generate a stable event ID.
- Track state as queued/sent/failed/unknown.
- Use the provider's idempotency contract if available.
- If the provider lacks deduplication, query delivery state or accept that non-duplication cannot be proven after a timeout.
- Decouple notifications from deploy jobs so an email failure does not re-trigger deployment.

## 10. Retry policies: retry only when safety is known

A policy should classify errors into at least four categories:

| Error group | Examples | Action |
|---|---|---|
| Permanent failure | Invalid payload, version conflict, permission denied, policy rejection | Stop; fix root cause, do not auto-retry |
| Transient failure | Rate limit, service unavailable, connection reset confirmed pre-send | Bounded retry with backoff if operation is safe |
| Ambiguous outcome | Timeout after sending request, lost response after possible commit | Query operation/reconcile; retry only with same idempotency key if supported |
| Partial completion | Some resources created, subsequent step failed | Inspect per-resource state and resume from checkpoint; do not rerun full chain |

### 10.1. Exponential backoff and jitter

When a failure is transient and the operation is retryable, exponential backoff eases pressure on the service:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
actual_delay = random(0, delay)
~~~

Random jitter prevents multiple pipelines from retrying simultaneously. If the server returns `Retry-After`, honor it per policy. Cap maximum retries and total wait time.

Backoff does not make a non-idempotent operation safe. It only spaces out attempts.

### 10.2. Retry budgets and time caps

Bound the following:

- Maximum retry attempts.
- Total operation duration.
- Wait interval between attempts.
- Concurrent in-flight operations.
- Retry budget per service or pipeline.
- Nested retries across client, SDK, job, and workflow layers.

If each layer independently retries three times, three stacked layers can multiply a single operation into 27 requests. Designate a single retry owner or coordinate a shared budget explicitly.

### 10.3. Never retry validation and authorization errors

Requests failing schema validation, lacking permissions, hitting artifact conflicts, or violating policies rarely heal on resend. Repeated retries generate noisy logs and wasted load. Stop, surface the error, and require fixing inputs or permissions.

## 11. Reconciling before retrying

When an outcome is uncertain, a safe sequence typically follows:

1. Preserve the original idempotency key/operation ID and payload.
2. Query the status API by key/operation ID.
3. If the operation is running, continue polling with backoff; do not create a new operation.
4. If it succeeded, verify the resource/digest and mark the pipeline step complete.
5. If it definitely failed before commit, fix conditions or retry per policy.
6. If status remains unknown, inspect the registry, deployment controller, audit logs, or resource state.
7. Create a new operation only after proving the prior operation cannot still cause side effects and making an explicit decision.

### 11.1. Polling status differs from retrying creation

Creation request:

~~~http
POST /deployments
Idempotency-Key: deploy-orders-prod-release-42
~~~

Status query request:

~~~http
GET /operations/deploy-orders-prod-release-42
~~~

When `POST` times out, issue `GET` for the operation status first. Never send a `POST` with a new key just to see if the system responds.

### 11.2. When the target API lacks idempotency keys or operation status

You may have to reconcile directly against target resources:

- Registry: does the package version/tag/digest already exist?
- Kubernetes: what are the Deployment revision, image digest, and rollout status?
- Cloud API: what resource ID, client token, or operation record was created?
- Release platform: does the release ID/version already exist?
- Database: what are the current migration ledger, schema, and checkpoint?
- Message broker: was the event ID/offset or consumer ledger recorded?

If no reliable verification path exists, stop automatic retries and escalate for human investigation. Never assume a timeout means non-execution.

## 12. Example: publishing packages with pre-retry checks

Suppose a pipeline publishes predetermined package coordinates and version. A script can follow this logic:

~~~text
operation_key = release_request_id
expected_digest = digest_of_built_artifact

status = registry.lookup(package, version)

if status == NOT_FOUND:
    publish_once(package, version, artifact, operation_key)
    verify_registry_digest(package, version, expected_digest)

else if status.digest == expected_digest:
    mark_publish_complete()

else:
    stop_with_conflict()
~~~

This is pseudocode, not a specific API. If the registry supports idempotency keys, pass the same key on retries. If not, check version/digest before publishing and treat digest mismatches as conflicts requiring investigation.

Never delete an existing package version and republish the same version as a recovery shortcut. That breaks immutability and can serve different content to consumers under identical coordinates.

## 13. Example: deploying via operation ID and reconciliation

A deployment client should separate operation creation from status polling:

~~~python
def ensure_deployment(api, operation_key, desired):
    operation = api.get_operation(operation_key)

    if operation is None:
        try:
            operation = api.create_deployment(
                desired_state=desired,
                idempotency_key=operation_key,
            )
        except TimeoutError:
            # Request may have already been committed by the server.
            operation = api.get_operation(operation_key)
            if operation is None:
                raise RuntimeError(
                    "Deployment outcome unknown; reconcile before retry"
                )

    while operation.status in {"queued", "running"}:
        wait_with_backoff()
        operation = api.get_operation(operation_key)

    if operation.status == "succeeded":
        verify_runtime_digest(desired["artifact_digest"])
        return operation

    if operation.status == "failed":
        raise RuntimeError(operation.error)

    raise RuntimeError("Deployment requires manual reconciliation")
~~~

This example assumes the API supports querying by operation key and creating with an idempotency key. Against real APIs, follow the provider's exact contract, authentication, timeouts, polling intervals, and error model. If the operation status is unknown, never generate a new key automatically.

## 14. Pipeline example: not re-running the entire deploy just because notifications failed

Split publish, deploy, verify, and notify into separate steps with independent state. Example structure:

~~~yaml
jobs:
  publish:
    steps:
      - name: Publish immutable artifact
        run: ./scripts/publish-with-idempotency.sh

  deploy:
    needs: publish
    steps:
      - name: Reconcile deployment operation
        run: ./scripts/ensure-deployment.sh

  verify:
    needs: deploy
    steps:
      - name: Verify runtime digest and smoke checks
        run: ./scripts/verify-release.sh

  notify:
    needs: verify
    steps:
      - name: Send release notification using event ID
        run: ./scripts/send-notification-once.sh
~~~

This structure is illustrative. Each script must persist its operation/event ID and provide matching reconciliation logic. If notifications fail, retry only notification handling by event ID; never rerun the `deploy` job. If `deploy` times out, the `deploy` job queries the existing operation rather than creating a new deployment.

In GitHub Actions or similar platforms, re-running a failed job can repeat side effects if the script is not idempotent. Re-running a job does not automatically cause target platforms to recognize it as the same operation.

## 15. Preventing multi-layer retry amplification

An operation can be retried at multiple layers:

- Workflow rerun or job retry.
- Shell script internal retry loop.
- SDK/HTTP client retry.
- Reverse proxy/service mesh request retry.
- Server queue message retry.
- Deployment controller desired-state reconciliation.
- Manual operator rerun.

Without coordination, a single operation can suffer multiplied invocations. Document explicitly which layer owns retries and which layers only observe state.

| Layer | Appropriate role |
|---|---|
| CI workflow | Orchestrate operations, persist IDs, decide continue vs. stop |
| Client/SDK | Retry transient failures only when API semantics permit |
| API server | Deduplicate by key, persist operation state, return stable results |
| Queue/consumer | Delivery may repeat; consumer deduplicates by event ID |
| Controller | Reconcile desired state rather than spawning new operations repeatedly |
| Operator | Investigate Unknown/Conflict states and approve manual actions |

Do not let a workflow retry the entire chain when only a secondary step fails. Checkpoints and clean job boundaries allow resuming at the exact incomplete step.

## 16. Concurrency control and operation locks

Two pipelines may simultaneously try to publish the same version or deploy to the same service/environment. Idempotency keys prevent repeating the same operation, yet do not automatically stop two distinct operations from colliding.

Add concurrency controls:

- Unique constraints on package coordinates/version or release ID.
- Per-service/environment locks when deployments cannot run concurrently.
- Compare-and-swap or resource versioning to avoid overwriting newer state.
- Deployment queues/leases with TTL and recovery when a worker dies.
- Desired-state checks before applying changes.
- Clear conflict responses when another operation owns the resource.

Locks do not replace idempotency. Locks prevent competing operations; idempotency handles repeated requests for the same intent. Systems need both when multiple pipelines and retries coexist.

## 17. Timeouts, cancellations, and Unknown state

A timeout usually stops only the caller from waiting for a response. It does not necessarily cancel the operation on the server. Likewise, cancelling a pipeline does not guarantee a deployment or publish actually stopped.

On cancellation or timeout:

1. Record the operation ID and timestamp.
2. Query server state.
3. If the operation is running, call the official cancel API if allowed and semantics are clear.
4. Query again to verify cancellation completed.
5. Inspect actual resources and any side effects already applied.
6. Release locks or start a new operation only once state is certain.

Never delete a lock/lease just because the client process exited; the server-side operation may still be running. Leases need TTLs, fencing tokens, or ownership checks so stale workers cannot keep writing after ownership transfers.

## 18. Observability for retries and side effects

Every invocation needs enough metadata to correlate attempts back to the same operation:

- Operation ID and idempotency key (masked/hashed if needed in display).
- Pipeline run ID, job ID, workflow revision, and commit SHA.
- Artifact version/digest or deployment target.
- Attempt number, retry reason, and backoff delay.
- Request ID, response code, and server operation ID.
- Before/after states and timestamps.
- Confirmed side effects: resource created, package published, event emitted, deployment completed.
- Reconciliation outcomes and evidence sources.

Useful metrics:

- Retry rate by operation type.
- Retry success rate vs. retries resulting in duplicates/conflicts.
- Operations stuck in `Unknown` state beyond threshold.
- Time from initial request to terminal state.
- Duplicate publish/deploy calls deduplicated.
- Pipeline reruns where the operation had already succeeded.
- Share of operations requiring manual reconciliation.
- Retry budget consumption and extra request volume generated by retries.

Never log raw idempotency secrets, tokens, passwords, or sensitive payloads. Keys are usually not credentials, yet they can still be internal identifiers requiring restricted access.

## 19. Common anti-patterns

| Anti-pattern | Risk | Better practice |
|---|---|---|
| Retrying every 5xx/timeout | Prior request may have already committed side effects | Query operation and reconcile |
| Minting a new idempotency key per retry | Server treats each retry as a new operation | Persist and reuse the key for the same intent |
| Reusing the same key for a different payload | Old result may be returned erroneously | Compare payload fingerprints and return conflict |
| Re-running full workflow when notifications fail | Repeats publish/deploy | Split jobs and retry notifications independently |
| Using mutable versions/tags for releases | Artifacts get overwritten under the same name | Immutable versions, digests, and registry policies |
| Retrying migrations without ledgers/checkpoints | Repeats DDL/DML or backfills | Migration IDs, checksums, transactions, and checkpoints |
| Treating timeout as cancellation | Server continues executing side effects | Query/cancel operation and confirm state |
| Storing only job success/failed | Cannot distinguish Unknown or Partial completion | Operation-level state machine |
| Nested retries across multiple layers | Multiplies requests, causing overload and duplicates | Single retry owner and shared retry budget |
| Using locks without fencing | Stale worker keeps writing after lease expiry | Leases/fencing tokens and compare-and-swap |
| Assuming declarative apply has no side effects | Hooks and scripts can still run repeatedly | Separate state reconciliation from side-effect steps |
| Skipping target state reconciliation | Pipeline and target system drift out of sync | Reconciliation and release records |

## 20. Checklist for designing safe publish/deploy retries

### Before enabling retries

- [ ] Classified operation as read-only, idempotent write, or non-idempotent side effect.
- [ ] Read API contracts covering timeouts, retries, idempotency, and error responses.
- [ ] Distinguished confirmed pre-commit failures from ambiguous outcomes.
- [ ] Defined a stable idempotency key/operation ID per logical intent.
- [ ] Enforced matching payload fingerprints for identical keys.
- [ ] Verified server performs atomic deduplication and persists operation state durably.
- [ ] Confirmed a status query API or reliable reconciliation mechanism exists.
- [ ] Backed external side effects with event IDs, idempotency contracts, or compensation plans.

### When publishing artifacts

- [ ] Versions/coordinates cannot be overwritten once published.
- [ ] Retries check existing package/version and digest.
- [ ] Digest mismatch against expected artifact triggers conflict and halts pipeline.
- [ ] Published packages/tags are never deleted to retry the same version.
- [ ] Release records capture artifact digest and operation ID.

### When deploying

- [ ] Desired state is reconcilable and versioned.
- [ ] Deploy operations carry stable IDs; timeouts query prior state.
- [ ] Migrations, hooks, notifications, and side effects are decoupled from state apply.
- [ ] Concurrency control per service/environment is in place where needed.
- [ ] Cancellations/timeouts are verified on the target system.
- [ ] Post-deploy verification confirms runtime digest and actual behavior.

### Retry policies and operations

- [ ] Retries apply strictly to transient errors and safe operations.
- [ ] Permanent failures are never auto-retried.
- [ ] Ambiguous outcomes route to reconciliation rather than creating new operations.
- [ ] Exponential backoff, jitter, max attempts, deadlines, and retry budgets are configured.
- [ ] No stacked multi-layer retries amplify request volume.
- [ ] Logs/metrics link attempts to operation IDs and resources.
- [ ] Manual reconciliation procedures exist for `Unknown` or `Conflict` states.
- [ ] Runbooks document how to verify side effects before clicking rerun.

Retries help pipelines survive brief glitches, but they do not automatically make side-effecting operations safe. Publishing and deploying require stable operation identities, target-side idempotency/deduplication, durable state, and reconciliation after timeouts. Whenever it is unclear whether the prior request committed, query state and inspect resources before resending. That allows pipelines to recover from network or runner faults without producing unintended releases, deployments, migrations, or transactions.
