# Safely Repeating Operations When a Process Is Interrupted or the Outcome Is Unclear

A deployment job sends a request to create a release in a target system. The system receives the request and creates the release, but the connection drops before CI receives the response. The job terminates with a timeout. Blindly re-running the entire operation could cause the pipeline to create a second release, send duplicate notifications, run migrations multiple times, or overwrite the state of an active deployment.

This is a common scenario in distributed systems: the caller does not know for certain whether the operation has already executed. A timeout only indicates that the caller did not receive a result within the wait window; it does not prove that the target system never processed the request.

For reliable deployment automation, operations must be designed to be safely repeatable, or the system must have a way to determine state before retrying. Two essential techniques are **idempotency** and **reconciliation** (reconciling observed state with desired state). Combining them with bounded retries, stable operation identifiers, durable state tracking, and side-effect controls lets pipelines recover from interruptions without creating duplicates or inconsistent state.

## 1. Understanding Idempotency in Automation

An operation is idempotent if executing it once or repeating it multiple times with the same inputs produces the same final state.

Conceptually, a function transforming state S via operation A is idempotent when:

~~~text
A(A(S)) = A(S)
~~~

For example, setting a service's replica count to 4 is safely repeatable:

- First call: service currently has 2 replicas, request sets it to 4.
- Second call: service already has 4 replicas, request sets it to 4 again.
- The final state remains 4 replicas.

By contrast, a command that increases replicas by 2 is not idempotent:

- First call: from 2 to 4.
- Second call: from 4 to 6.
- Third call: from 6 to 8.

If the caller does not know whether the previous attempt succeeded, repeating an incremental command can produce the wrong state.

### Setting Desired State vs. Issuing Relative Changes

| Operation Type | Example | Repeatability |
|---|---|---|
| Set absolute state | Set replicas = 4 | Usually idempotent under the same scope and conditions |
| Set desired configuration | Apply manifest version X | Can be idempotent if tool and resource identity are stable |
| Create resource with fixed name | Ensure bucket named release-assets exists | Can be idempotent if conflicts are checked and handled properly |
| Relative change | Increase replicas by 2 | Not idempotent |
| Create new without stable ID | Create a new release | Can create duplicate records on retry |
| Send notification | Send release email | Usually produces a new side effect each time |
| Conditional state transition | Transition deployment from pending to active | Requires state and contention control |

Good design generally describes the **desired target state** rather than a sequence of relative mutation commands. For example, instructing the system to ensure a specific version is running in production is clearer than commanding "run deploy one more time."

### Idempotency Does Not Mean Zero Side Effects

An API may update the same value multiple times while still sending an email, incrementing a counter, writing an audit event, or triggering a webhook on every call. When evaluating idempotency, consider all observable effects, not just the primary database column.

## 2. Why Can an Operation's Outcome Be Indeterminate?

Suppose CI sends a request to a deployment service. Failures can happen at many points:

1. Caller fails before sending the request.
2. Request is sent but never reaches the server.
3. Server receives the request but has not processed it yet.
4. Server commits the change, but the response is lost.
5. Server accepts an async task and returns an operation ID, but the caller loses the response.
6. Server finishes part of the work and then the worker dies.
7. Caller receives the response but crashes before persisting success to its own state store.

In cases 1–3, the operation may not have occurred. In cases 4–7, the operation may have completed wholly or partially. From the caller's viewpoint, a timeout or dropped connection cannot distinguish among these cases.

### Three Outcome States to Distinguish

- **Confirmed success:** the caller has reliable evidence that the operation completed.
- **Confirmed failure:** the target system returned a response showing the operation was not performed or was rejected.
- **Unknown outcome:** the caller does not know whether the operation was accepted, committed, or completed.

Do not automatically convert an unknown state into failed. If a deployment may already have finished, marking it failed and spawning a new operation can cause the pipeline to run twice in parallel.

### Timeout Is Not Proof That an Operation Failed

A timeout is a caller-side event. It only reports that the wait budget expired. The target system may continue processing after the caller stops waiting.

On timeout, the safe action is usually to look up status by operation ID or idempotency key. Re-submit the request only after determining the appropriate retry rules.

## 3. Delivery Semantics: At-Most-Once, At-Least-Once, and Exactly-Once

In distributed systems, messages or requests can be lost, re-sent, or processed multiple times. Three common semantics:

| Semantics | Behavior | Trade-off |
|---|---|---|
| At-most-once | Do not resend when uncertain | Avoids duplicate processing, but operations may be lost |
| At-least-once | Resend until confirmation is received per policy | Increases completion probability, but may process multiple times |
| Exactly-once | Each operation takes effect strictly once within a defined scope | Difficult to guarantee across independent systems |

Exactly-once can typically only be guaranteed within a specific transaction or protocol boundary. When a pipeline calls APIs, writes to databases, publishes messages, and deploys to clusters, no single distributed transaction automatically spans all those systems.

In practice, many systems achieve **effectively-once** behavior by:

- Allowing requests to be re-sent (at-least-once).
- Assigning a stable identifier to a logical operation.
- Persisting processing state durably.
- Deduplicating where side effects are executed.
- Reconciling state when the caller misses a response.

The goal is for one logical operation to produce one business effect even if the request is transmitted multiple times.

## 4. Designing Operations to Be Safely Repeatable

### Prefer Desired-State APIs

Instead of APIs that increment or decrement a value, design APIs that accept target state wherever business logic permits.

Example:

~~~http
PUT /environments/production/services/order-api
Content-Type: application/json

{
  "version": "2.8.1",
  "replicas": 4
}
~~~

The caller can resend the same request. The server reads current state and converges the resource to version 2.8.1 with 4 replicas.

HTTP defines PUT with idempotent semantics, yet the implementation must still honor those semantics. If every PUT creates a new release record or emits a fresh business notification, the overall operation still produces duplicate side effects.

### Use Stable Resource Identifiers

Resources need stable identities so subsequent runs locate the exact object already created:

- Deployment name derived from service and environment.
- Release ID derived from repository, commit, or release version.
- Cloud resource name derived from system and purpose.
- Migration ID tied to schema version.
- Operation ID for one logical request.

Avoid generating a new random name on every retry if the goal is to continue the same operation.

### Use Idempotency Keys for Creation Operations

For APIs that create releases, provision resources, or process payments, send an idempotency key. The server stores the key and its associated result.

Example:

~~~http
POST /deployments
Idempotency-Key: order-api:production:release-2.8.1
Content-Type: application/json

{
  "service": "order-api",
  "environment": "production",
  "artifactDigest": "sha256:..."
}
~~~

If the same key is sent again, the server returns the recorded operation or result instead of creating a second deployment.

A good idempotency key should:

- Represent one specific business operation.
- Remain stable across retries of that same operation.
- Differ across distinct intentional deployments.
- Be retained server-side for a sufficient duration.
- Be clearly scoped, such as by tenant, endpoint, or operation type.
- Be bound to the payload to prevent reusing the same key for two different requests.

Never generate a new UUID on every retry. If every attempt uses a different key, the server cannot recognize that it is the same logical operation.

### Bind the Key to the Payload

If a key was already used with payload A, a subsequent request with the same key and payload B must be treated as a conflict or invalid request. Never silently return A's result for B or execute B as a new operation.

You can store a hash of the canonicalized payload alongside the key:

| Field | Purpose |
|---|---|
| idempotency_key | Identifies the logical operation |
| request_hash | Detects payloads differing from the first attempt |
| status | Processing state |
| operation_id | Reference to the actual work item |
| response/result | Cached result to return on retry |
| created_at / expires_at | Record lifecycle management |

Recording the key and creating the operation must happen atomically within the receiving service's database, typically via a unique constraint and transaction.

## 5. Persisting Operation State with a State Machine

A long-running deployment operation should not have only two states, success/failed. It may be queued, running, or in an unknown state.

Example state machine:

~~~text
          +-----------+
          | REQUESTED |
          +-----+-----+
                |
                v
          +-----------+
          |  RUNNING  |
          +-----+-----+
                |
       +--------+---------+
       |                  |
       v                  v
 +-----------+       +-----------+
 | SUCCEEDED |       |  UNKNOWN  |
 +-----------+       +-----+-----+
                           |
                     Reconcile state
                           |
                 +---------+---------+
                 |                   |
                 v                   v
            SUCCEEDED          RETRYABLE
                                     |
                                     v
                                  RUNNING

Terminal failure: FAILED
~~~

Usable states:

| State | Meaning | Appropriate Action |
|---|---|---|
| REQUESTED | Request recorded | A worker may pick it up |
| RUNNING | Currently executing | Monitor lease/heartbeat |
| SUCCEEDED | Confirmed completion | Return cached result on retry |
| FAILED_RETRYABLE | Transient failure, known safe to retry | Retry per policy |
| FAILED_TERMINAL | Error unrecoverable via retry | Stop and require intervention |
| UNKNOWN | Caller or worker lost track of outcome | Query and reconcile |
| CANCELLED | Canceled per policy | Verify side effects before starting a new operation |

Not every system needs all these states. What matters is distinguishing known failures from unknown outcomes and defining valid state transitions.

### Use Conditional State Transitions

Multiple workers can claim the same operation after a lease expires or a job retries. Use transactions, compare-and-set, or optimistic locking so only one worker holds valid execution rights at a time.

For instance, transition REQUESTED to RUNNING only if the current state is still REQUESTED. If another worker already transitioned it to RUNNING or SUCCEEDED, the newcomer must re-read state instead of proceeding.

### Leases and Fencing Tokens

A lease grants a worker processing rights for a bounded period. If the worker crashes, the lease expires and another worker can take over.

However, an old worker might wake up after its lease expired and keep writing data. Fencing tokens solve this with a monotonically increasing version number; the target system accepts writes only from the worker holding the newest token. Leases without fencing or equivalent controls may fail to stop two workers from mutating concurrently.

## 6. Resolving Unknown Outcomes Through Reconciliation

When a caller times out after sending a request, do not default to creating a new operation. Look up the prior operation using its idempotency key, operation ID, or resource identity.

General procedure:

1. Record the request ID and idempotency key before sending.
2. Send the request to the target system.
3. If a success response arrives, save the operation ID and result.
4. If a timeout or connection drop occurs, mark status as UNKNOWN.
5. Query the target system by key or operation ID.
6. If the operation already completed, update status to SUCCEEDED.
7. If still running, continue polling at an appropriate interval.
8. If confirmed not received, resend with the same key.
9. If the system cannot determine state, halt automation and require manual reconciliation rather than creating extra side effects.

### Desired-State Reconciliation

In declarative deployments, the system can compare:

- Desired state: version 2.8.1, 4 replicas.
- Observed state: version 2.8.1, 3 replicas.
- Difference: missing 1 replica.
- Action: continue reconciling toward desired state.

If observed state already matches, the operation succeeded even though the earlier caller disconnected. If observed state is transitioning, wait or let the controller continue. If state is invalid, raise an alert and require intervention.

### Do Not Guess from the Final Log Line

Logs may be incomplete if a process died before flushing, and a "request sent" log line does not prove the server committed. Use durable state from the resource-owning system as the source of truth. Logs and traces assist investigation but do not replace operation records or actual state.

## 7. Retrying the Right Error Classes with Bounds

Not every error should be retried.

### Error Classification

| Error Class | Examples | Policy |
|---|---|---|
| Transient error | Network reset, timeout, service unavailable | Retry with backoff if the operation is safe |
| Rate limit | HTTP 429 | Honor Retry-After or server-supplied limits |
| Transient server error | HTTP 502, 503, 504 | Bounded retries keeping the same idempotency key |
| Authentication error | HTTP 401 | Do not loop retries; fix identity/credentials |
| Authorization error | HTTP 403 | Stop and resolve policy |
| Invalid input | HTTP 400, schema validation failure | Do not retry the same payload |
| State conflict | HTTP 409 or version conflict | Read fresh state and reconcile |
| Not found | HTTP 404 | Depends on operation; may be terminal or propagation lag |
| Unknown outcome | Timeout after sending request | Query status before creating a new operation |

HTTP codes are only one signal; custom APIs may use other status conventions. Rely on the service contract and classify errors explicitly.

### Exponential Backoff and Jitter

If many jobs retry immediately at once, they can trigger a fresh load spike against a struggling system. Exponential backoff widens the wait between attempts; jitter adds randomness to keep callers from retrying in lockstep.

Example:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait = random(0, delay)
~~~

You might configure a 1-second base delay, 30-second max delay, and a retry cap. Numbers must fit SLAs, deploy windows, and guidance from the target service.

### Bounding Total Duration and Attempt Count

A retry policy should define:

- Maximum attempt count.
- Overall deadline for the operation.
- Per-request timeout.
- Maximum backoff and jitter.
- Retry-After handling.
- Abort rules for terminal errors.
- How unknown outcomes are recorded when time expires.

Never retry forever. Pipelines must reach a clear terminal state and provide enough data for operators to investigate.

### Avoid Nested Retries That Amplify Load

If the HTTP client retries 3 times, the SDK retries 3 times, and the CI job retries 3 times, a single logical operation can generate up to 27 requests. Align retry budgets across layers. One layer should own retries, or layers must coordinate via a shared deadline and idempotency key.

## 8. Designing CI/CD to Resume the Same Operation

A job can be canceled, a runner can disconnect, or a pipeline can be manually re-run. If every run generates a new deployment ID, the system cannot tell whether it is resuming an existing operation or launching a new release.

### Create Stable Operation Identities

An operation identifier can be derived from:

- Service.
- Environment.
- Release or deployment version.
- Artifact digest.
- Source commit.
- Operation type.

Example:

~~~text
operation_key =
  service + environment + release_version + artifact_digest
~~~

If the same release is retried, the key stays identical. If the artifact digest or release version changes, it is a different operation and gets a new key.

Do not rely solely on CI run IDs if every rerun generates a new run ID. Store the run ID for traceability, but use the operation key to identify the same release intent across multiple runs.

### Decouple Requests from Execution Workers

A well-designed deployment API can return an operation ID immediately upon accepting a request:

~~~http
POST /deployments
Idempotency-Key: order-api:production:2.8.1:sha256-abc123

HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operationId": "op-4821",
  "status": "RUNNING"
}
~~~

The caller saves the operation ID. If the job is interrupted, the next run looks up that operation instead of issuing a new creation request.

If the server receives the same key again, it returns the active operation or completed result. The caller can simply resume polling.

### Pseudo-Code Example for a Deploy Client

~~~python
def deploy_release(service, environment, release, digest):
    key = f"{service}:{environment}:{release}:{digest}"

    operation = deployment_api.find_by_idempotency_key(key)

    if operation is None:
        try:
            operation = deployment_api.create(
                service=service,
                environment=environment,
                release=release,
                artifact_digest=digest,
                idempotency_key=key,
            )
        except TimeoutError:
            operation = deployment_api.find_by_idempotency_key(key)
            if operation is None:
                raise UnknownOutcome(key)

    return wait_until_terminal(operation.id)
~~~

This example assumes the API supports key lookup and persists keys durably. If the API lacks that capability, the client needs another reconciliation mechanism; never treat an immediate "not found" lookup as proof the request never reached the server, because replication or indexing may still be in flight.

## 9. Declarative Deployments and Reconciling Desired State

Infrastructure and orchestration tools often follow a declarative model: users declare desired state, and a controller compares it against current state and reconciles the difference.

Example Kubernetes manifest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: production
spec:
  replicas: 4
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: app
          image: registry.example.com/order-api@sha256:...
~~~

Applying the same manifest repeatedly generally converges the resource to the same desired state. However:

- Images should reference immutable digests.
- Do not generate random resource names on each run.
- Admission webhooks or controllers may produce side effects of their own.
- Migration jobs, hooks, or notifications need their own idempotency.
- Monitor rollout status rather than relying solely on apply returning success.

### Apply and Wait Are Two Separate Steps

An apply command may have updated desired state while Pods are not yet ready. If the job is interrupted while waiting, the next run should read the existing resource and resume waiting for rollout. There is no need to create a brand-new Deployment.

A resume flow:

1. Apply manifest with fixed resource identity.
2. Record generation or revision.
3. Watch rollout status.
4. If interrupted, re-read the Deployment and ReplicaSet.
5. Compare observed generation against desired generation.
6. Resume waiting or reconciling.
7. Mark success only after readiness and post-deploy criteria pass.

Never treat API server acceptance of a manifest as proof that the application is safely serving traffic.

## 10. Provisioning Cloud Resources Safely Under Retries

Creating buckets, databases, queues, load balancers, or service accounts can hit the exact case where the request succeeded but the caller timed out.

### Use Stable Resource Names and Client Tokens

If the cloud API supports an idempotency token or client request token, supply a stable token for the same logical operation. Otherwise:

- Create resources with deterministic names.
- Look up resources by system-managed names or tags.
- Validate attributes before reusing.
- If the resource already exists with the exact expected configuration, treat the step as satisfied.
- If the resource exists with different configuration, handle the conflict rather than blindly overwriting.

### Verify Ownership

A deterministic name could already be used by another system. Never see an existing resource and automatically assume the current deployment created it.

Attach ownership metadata such as:

- Owner service.
- Environment.
- Managed-by.
- Release or stack ID.
- Resource schema version.

Before updating, verify ownership and configuration. If they do not match, halt and require investigation.

### Terraform and State

Terraform uses state to map configured resources to real resources. If an apply is interrupted, state or provider actions may not fully reflect reality.

Safe workflow:

- Use remote state with locking.
- Never run two concurrent applies against the same state.
- After an interruption, refresh and inspect state against cloud reality.
- Run plan to inspect drift.
- Apply again only after understanding which resources were created or modified.
- Never delete the state file to "start from scratch."
- If a resource exists outside management, use import or an appropriate recovery flow.

Never use a fresh creation operation to replace an apply whose outcome is unknown.

## 11. Database Migrations and Data Require Special Care

Migrations often carry hard-to-reverse side effects. Adding a column can be safe to rerun if written conditionally, whereas crediting balances or transforming data can corrupt values if executed twice.

### Distinguishing Schema Migrations from Data Migrations

| Type | Example | Retry Risk |
|---|---|---|
| Schema migration | Create table or add column | May conflict if object already exists |
| Data migration | Convert data from old format to new | May double-process or mis-update rows |
| Backfill | Populate missing data in batches | Needs checkpoints and conditional updates |
| Index migration | Create large index | May take a long time or conflict if already exists |
| Destructive migration | Drop old column or data | Hard to roll back and risks data loss |

### Use Migration History and Unique Versions

Migration tools typically track executed versions or migration IDs. Before running, check migration history inside a transaction or using the tool's lock mechanism. A migration already marked successful must never rerun as a new migration.

Never edit the contents of a migration already applied to real environments. Express changes as a new migration so schema history stays traceable.

### Write Resumable Migrations

For large data backfills:

- Split into bounded batches.
- Use stable keys or cursors.
- Update conditionally so only unfinished records are touched.
- Persist durable checkpoints.
- Scope each batch in an appropriate transaction.
- After interruption, read the checkpoint and resume.
- Ensure the latest batch can rerun without duplicate side effects.

For example, instead of incrementing a counter on every row each time a job runs, update only rows lacking the migration marker. For financial operations, enforce unique constraints or ledgers to prevent double-recording transactions.

### Expand-Contract for Multi-Version Deployments

During rolling deployments, old and new versions may access the database concurrently. A safe strategy:

1. Expand: add new structures while the old version stays compatible.
2. Deploy code capable of reading/writing during the transition.
3. Backfill data using checkpoints.
4. Switch reads to the new structure and verify.
5. Contract: remove old structures only when no dependent version remains.

Never bundle destructive schema drops into the initial deploy step if application rollback still relies on old structures.

## 12. External Side Effects: Messages, Email, Payments, and Webhooks

Not every operation can be expressed as desired state. Sending email, charging payments, or publishing messages normally creates a new event on every call.

### Inbox/Deduplication at the Consumer

A consumer may receive the same message multiple times. Use the message ID or business event ID as a unique key. Before processing, check whether the message has already been recorded; recording completion and updating business data should share the same transaction whenever possible.

Example:

~~~text
Receive message with event_id
          |
          v
Insert event_id into inbox table
          |
     unique constraint
       /       \
    new       duplicate
     |            |
     v            v
Apply effect   Return prior result
     |
     v
Commit inbox + business update
~~~

If the consumer marks a message done before updating business state, a crash between steps loses the effect. If it updates business state first and crashes before marking done, redelivery repeats the effect. Sharing a transaction or using an appropriate pattern closes this gap.

### Transactional Outbox

If a transaction both updates the database and needs to publish an event, two independent operations can fall out of sync. A transactional outbox writes the event into an outbox table in the same transaction as business data. A worker publishes the event and marks it sent.

The worker may still publish the same event multiple times if it crashes after sending but before marking sent. Consumers still need deduplication. Outbox prevents losing events between database commit and message publish, though it does not by itself create end-to-end exactly-once across broker and consumer.

### Payment APIs and Irreversible Operations

For payments, refunds, or provisioning valuable resources, use business-managed idempotency keys and persist transaction outcomes. Never retry a transaction creation request with a new key solely due to a client timeout.

If a provider lacks idempotency support, look up the transaction by merchant reference or business reference before resending. When state cannot be determined, halt automation and route to reconciliation.

## 13. Rollback, Retry, and Compensation Are Not the Same

These three concepts solve different problems:

- **Retry:** re-attempt the exact same operation after a transient error or when it can be proven the previous attempt did not complete.
- **Rollback:** return the system to a prior version or state, when reverting remains feasible.
- **Compensation:** perform a new business operation to offset an effect that already occurred.

Examples:

| Scenario | Retry | Rollback | Compensation |
|---|---|---|---|
| Deploying new version not yet rolled out | Continue applying the same digest | Revert to previous digest | Usually not needed |
| Migration adding a compatible column | Continue migration | Column can remain; no immediate drop needed | Usually not needed |
| Email already sent | Do not resend if already recorded | Cannot unsend email | Send correction notice if needed |
| Payment already captured | Do not create a new charge when outcome is unclear | Cannot simply delete transaction | Issue refund against business reference |
| Cloud resource already created | Look up and finish configuring | Delete resource if safe | Transfer or release resource per process |

Compensation does not always restore the original state. A refund creates a brand-new transaction with its own audit trail. Therefore, avoid calling every corrective action a rollback.

### Rollback Designs Must Also Be Idempotent

A rollback job can time out after shifting traffic back to the old version. Re-running it must inspect current state and continue converging to the target digest without creating extra releases or repeating destructive reversal sequences.

Assign a dedicated operation key to rollbacks and store the target version to restore.

## 14. Locks and Handling Two Concurrent Deployments

Idempotency handles repeating the same operation; it does not by itself resolve two different operations running concurrently.

Example:

- Pipeline A wants to deploy version 2.8.1.
- Pipeline B wants to deploy version 2.8.2.
- Both read current state as 2.8.0.
- A and B sequentially overwrite the resource, leaving the final state out of intended release order.

Control concurrency per service/environment:

- One active deployment per service and environment, if policy requires serialization.
- Use locks with leases or queues.
- Attach sequence/version or generation numbers to operations.
- Reject stale operations if a newer version was already accepted.
- Use optimistic concurrency such as If-Match or resource versions.
- Never hold locks forever if a worker dies; require leases and recovery.

### Do Not Rely Only on CI Concurrency Groups

CI may offer concurrency groups to prevent two workflows from deploying simultaneously. However, operations can be triggered from another tool, or an old workflow may still be executing after a job was canceled. The target system should enforce its own concurrency or version checks rather than relying solely on CI-side locks.

## 15. Testing Retry and Recovery Capabilities

Idempotency cannot be verified solely by reading code. Test behavior when failures happen at different points.

### Failure injection

Try simulating:

- Caller crashes before sending the request.
- Server commits, then the response is dropped.
- Worker dies between two side-effect steps.
- Lease expires while the old worker is still running.
- Two requests with the same idempotency key arrive concurrently.
- Same key with a different payload.
- Job is rerun while the operation is RUNNING.
- Job is rerun after the operation has SUCCEEDED.
- Database temporarily loses connectivity while saving state.
- Cloud API returns 429 or 503.

### Test expectations

| Scenario | Expected Outcome |
|---|---|
| Same key, same payload, concurrent calls | Only one logical operation is created |
| Same key, different payload | Rejected as conflict |
| Timeout after commit | Lookup finds existing operation; no second operation created |
| Retry while running | Returns current state or existing operation ID |
| Retry after success | Returns prior result |
| Old worker returns after lease expiry | Fencing token blocks stale state write |
| Validation error | Stops; does not retry |
| Transient error | Retries within budget and backoff |
| Migration interrupted between batches | Resumes from checkpoint without duplicate application |
| Two competing releases | Lock/version policy enforces clear ordering |

Verify both the final data state and the actual count of side effects executed. Checking only that the API returned HTTP 200 is insufficient.

## 16. Observability, Auditing, and Operations After Interruption

When a job is interrupted, operators must know whether to resume, retry, reconcile, or stop. This requires logs and metadata sufficient to recognize the same operation.

Each operation should include:

- Operation ID and idempotency key.
- Service and environment.
- Release version, commit SHA, and artifact digest.
- Pipeline run ID and job attempt.
- Start, update, and completion timestamps.
- Current state and state-transition history.
- Retry count, error types, and backoff durations.
- External resource ID or deployment revision.
- Initiating user or identity.
- Health check results and any rollback/compensation details.

Never write secrets or tokens to logs. Record non-sensitive fingerprints or identifiers for traceability.

### Useful metrics

- Operation retry rate.
- Count of operations stuck in UNKNOWN past deadline.
- Count of deduplicated requests.
- Retry success rate.
- Duration from REQUESTED to SUCCEEDED.
- Count of operations requiring manual intervention.
- Conflict count from concurrent deployments.
- Count of migrations resumed from checkpoints.
- Rollback and compensation rates.

If retry rates spike suddenly, the target system may be overloaded or configured timeouts may be too low. If UNKNOWN counts climb, lookup or reconciliation mechanisms may be unreliable.

## 17. Procedure When a Pipeline Is Interrupted

When a deploy job is interrupted or yields an unclear outcome, operators can follow this sequence:

1. Identify the operation key, release version, and artifact digest of the run.
2. Check pipeline status and the timestamp when the job lost connectivity.
3. Look up the operation in the deployment system by operation ID or idempotency key.
4. Inspect the observed state of real resources rather than relying solely on caller logs.
5. If the operation is running, resume polling or wait for the active worker.
6. If already succeeded, update the pipeline record and run post-deploy verification if missing.
7. If terminally failed, stop and address the root cause.
8. If confirmed not received, retry with the exact same operation key.
9. If outcome remains unknown, keep the indeterminate status, alert, and require reconciliation.
10. Generate a new operation key only when it is genuinely a new release or deployment intent.

This procedure separates "resuming an existing deployment" from "starting a different deployment."

## 18. Common Anti-Patterns

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| Re-running the entire script on timeout | May create duplicate side effects | Look up operation and reconcile first |
| Generating a new idempotency key per retry | Server cannot recognize duplicate requests | Keep key stable for the same logical operation |
| Using relative increment/decrement commands | Retries drift state further | Specify absolute desired state |
| Storing state only in job memory | Runner crash loses track of operation | Persist durable operation records |
| Marking failed when no response arrives | May spawn a new operation while old one already ran | Use UNKNOWN status |
| Retrying every error | Repeats validation/auth errors and adds load | Classify errors and bound retries |
| Retrying immediately | Causes retry storms | Exponential backoff and jitter |
| Nested retries across layers | Amplifies request counts | Align a unified retry budget |
| Treating API 202 Accepted as deployment complete | Async task may still be running | Poll operation and verify observed state |
| Running data migrations without checkpoints | Risks double-processing or skipped rows | Batches, markers, transactions, and history |
| Using unlocked cache/state files | Concurrent pipelines corrupt state | Locks, versioning, and proper state backends |
| Using a new artifact when retrying the same release | One logical operation swaps inputs mid-flight | Bind operation to immutable digest |
| Treating compensation as complete rollback | May overlook effects already committed | Track compensation as its own transaction |

## 19. Checklist for Designing Recoverable Deploy Operations

### Identity and State

- [ ] Every logical operation has a stable operation ID or idempotency key.
- [ ] Retrying the same operation preserves both key and payload.
- [ ] Keys are bound to a payload hash.
- [ ] Operation records are stored durably.
- [ ] UNKNOWN state is distinguished from FAILED.
- [ ] Transition rules and concurrent-worker protections exist.
- [ ] Leases, fencing, or equivalent prevent stale workers from overwriting.

### Retries and Reconciliation

- [ ] Errors are classified into transient, terminal, and unknown.
- [ ] Retries occur only when operations are safe or server-side deduplicated.
- [ ] Exponential backoff, jitter, max attempts, and deadlines are configured.
- [ ] Retry-After headers or target service guidance are respected.
- [ ] No unbounded retries or nested retry amplification.
- [ ] APIs or mechanisms exist to query current operation/resource state.
- [ ] After a timeout, reconcile before creating a new operation.

### Deployment and Side Effects

- [ ] Artifacts are bound to immutable digests.
- [ ] Desired state uses stable resource identities.
- [ ] Database migrations maintain history and support resume.
- [ ] Message consumers implement deduplication.
- [ ] Emails, payments, and webhooks carry business references or idempotency keys.
- [ ] Rollbacks and compensations carry their own operation identities.
- [ ] Concurrency control protects each service/environment.

### Operations

- [ ] Logs and traces include operation ID, release, and artifact digest.
- [ ] Metrics track retries, unknown outcomes, and deduplication.
- [ ] Failure-injection tests cover commit/response/worker failure points.
- [ ] Manual procedures exist for outcomes that cannot be resolved automatically.
- [ ] Success is never marked merely because an API accepted a request.
- [ ] Deployments finish only after health checks and post-deploy criteria pass.

## Conclusion

An interrupted process does not mean the operation in the target system never occurred. When outcomes are unclear, pipelines must query state and reconcile before introducing more side effects. Design operations around desired state, use stable identifiers and idempotency keys, persist durable state machines, classify errors, and apply bounded retries. For migrations, messages, payments, and cloud resources, add checkpoints, deduplication, locking, or compensation as appropriate. This ensures the same deployment intent can resume safely after timeouts, runner failures, or job reruns without producing duplicate releases, transactions, or resource mutations.
