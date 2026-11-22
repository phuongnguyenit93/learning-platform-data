# Building Application Correctness Criteria Before and After Restore

With CRaC (Coordinated Restore at Checkpoint), an application can save process state at a checkpoint and resume from that state upon restore. A JVM restarting successfully is not enough to prove the application is correct. After a pause duration, the database may have changed, tokens may have expired, the broker may have redelivered messages, log files may have rotated, and leases may have been granted to another process.

Therefore, CRaC testing needs to answer a broader question than "does the application start back up?": **which business and operational guarantees must remain true after the process is recovered?** These guarantees must be written as observable and verifiable criteria before designing tests.

A good set of criteria defines:

- Which state must be preserved across checkpoints.
- Which work must complete, roll back, or be allowed to rerun.
- Which resources must be closed before checkpoint and recreated after restore.
- Which data or credentials must be refreshed because time has elapsed.
- When an instance is permitted to accept requests or messages.
- Which behavior is acceptable when checkpointing or restoration fails.
- Which evidence proves the application satisfies those guarantees.

This document explains how to establish correctness criteria for both sides of a checkpoint: the preparation phase prior to image creation and the recovery phase before the application resumes serving.

## 1. Defining Correctness of a Restore

A restore is considered correct when the application continues operating while upholding all invariants committed to users and dependent systems. An invariant is a condition that must always hold, regardless of whether the process ran continuously or went through checkpoint/restore.

Examples:

- An order committed before checkpoint is not lost after restore.
- A message not yet processed successfully is not acknowledged as if completed.
- A request that may be resent does not create two payments.
- A replica does not continue exercising leader authority after its old lease expired.
- Any connection used after restore must be a valid connection to the current peer.
- A token that expired while the JVM was stopped must not continue to be used.
- An instance accepts traffic only when required dependencies are ready.
- A log file after rotation must write to the current active target.

Correctness does not mean every state on the heap must remain unchanged. Some state must be preserved, some must be recomputed, and some must be discarded. The criteria must clearly specify which state belongs to which category.

### 1.1. Distinguishing Process Recovery from Application Recovery

| Level | Question | Evidence |
|---|---|---|
| Process recovery | Does the JVM restore and resume execution? | Runtime reports restore succeeded, process exists |
| Framework recovery | Do framework and lifecycle components work properly? | Beans/context, workers, schedulers, and callbacks are in expected states |
| Resource recovery | Are sockets, pools, files, clients, and native resources valid? | Fresh connections, read/write operations succeed, no stale handles used |
| Business recovery | Do data and side effects preserve invariants? | Database, broker, and business outcomes are consistent |
| Service recovery | Can the instance accept traffic safely? | Readiness opens only after required conditions complete |

A test that only verifies process recovery can pass while the application still fails on its very first request. Therefore, criteria must extend to business recovery and service recovery.

### 1.2. Defining the Scope of Criteria

Before writing tests, describe:

- Application type: HTTP service, batch worker, consumer, scheduler, CLI, or hybrid.
- Checkpoint type: JVM CRaC or container checkpoint.
- Engine and JDK/runtime used.
- Required dependencies: database, broker, cache, APIs, secret manager, filesystem.
- Deployment model: single instance, multiple replicas, autoscaling, or rolling deployment.
- Possible pause duration between checkpoint and restore.
- Business state that may exist at checkpoint time.
- Commitments regarding data loss, duplicate processing, and recovery time.

Criteria suitable for an HTTP service do not necessarily fit a message-processing consumer. A worker may need to preserve offsets and acknowledgments; an API may need to guarantee idempotency for retried requests.

## 2. Establishing the Invariant Set Before Writing Tests

Start from the existing invariants of the application. CRaC is a process lifecycle change; it must not alter the business semantics to which the application is committed.

### 2.1. Data Invariants

Identify:

- Which committed data must survive restore.
- Which uncommitted data must roll back or continue via a recoverable protocol.
- Which caches may become stale and need refreshing.
- Which counters or sequences must be monotonic and unique.
- Which data resides on the heap while its authoritative source is the database or an external service.

For example, an order committed in the database before checkpoint must still exist after restore. If the application has an in-heap cache, the cache may hold a stale copy; criteria must require cache invalidation or version verification before using it for business decisions.

### 2.2. Side-Effect Invariants

A side effect is an action that alters external state such as writing to a database, sending a message, charging a payment, sending an email, or calling a resource-creating API.

Identify:

- Which side effects completed before checkpoint.
- Which side effects may have been dispatched without receiving a response yet.
- Which side effects may be resent after restore.
- Which mechanisms prevent duplicate operations: transactions, idempotency keys, unique constraints, inbox/outbox, or deduplication.

You cannot rely solely on heap state to know whether an external request was already processed. If a client sent a request, the server performed the side effect, and the response was lost before checkpoint, the application may not know the outcome. Criteria must require querying state or retrying with a stable idempotency key.

### 2.3. Ownership and Concurrency Invariants

For distributed applications, identify:

- How many concurrent owners a resource can have.
- How long a lease remains valid.
- Who grants leadership authority.
- Whether there is a fencing token or generation preventing an old owner from writing.
- Whether a consumer member ID must be unique per instance.
- Which tasks multiple replicas restored from the same image may execute simultaneously.

A leader boolean on the heap does not prove leadership is still valid. After restore, the application must re-verify with the coordinator and execute side effects only when holding a currently valid lease/fencing token.

### 2.4. Security Invariants

Identify:

- Whether tokens, sessions, certificates, and key material expire or can be revoked.
- Whether credentials are bound to a specific replica or workload identity.
- Whether truststores or policies can rotate while the JVM is stopped.
- Whether the checkpoint image contains secrets.
- Whether restore must re-verify the identity of the current environment.

Security criteria must confirm that the application does not continue using expired, revoked, or another replica's credentials. Never print tokens or private keys to logs as test evidence.

### 2.5. Time Invariants

Time continues to advance while the JVM is stopped. Time-dependent states may change:

- Access tokens, refresh tokens, and sessions.
- TLS certificates and session tickets.
- Leases, distributed locks, and heartbeats.
- Cache TTLs and scheduler deadlines.
- DNS TTLs, connection max lifetimes, and idle timeouts.
- Business deadlines or request processing timeouts.

Criteria must state explicitly that the application uses the current time after restore to check validity. Never use a snapshotted flag or counter as proof that a time-bounded state is still valid.

## 3. Classifying State to Decide What to Keep, Refresh, or Discard

A useful technique is to catalog the state held by the application before checkpoint. For each item, record the authoritative source, lifecycle, and post-restore action.

| State Group | Examples | Post-Restore Policy |
|---|---|---|
| Immutable configuration | Service name, schema version, parser config | May be kept if version and environment are compatible |
| Durable data | Committed records, saved offsets | Read or verify from authoritative source |
| Rebuildable cache | Reference data, lookup cache | Keep if still fresh; otherwise refresh |
| OS resources | Sockets, file descriptors, native handles | Close before checkpoint or verify and recreate |
| Clients/pools | JDBC pool, HTTP client, broker client | Drain/close and reinitialize per library API |
| Time-bounded state | Tokens, leases, certificates, sessions | Re-check against current time; obtain fresh ones as needed |
| Per-instance identity | Instance ID, consumer member ID, temp path | Regenerate or re-query for the current instance |
| In-flight work | Requests, transactions, messages, scheduled jobs | Complete, roll back, save business checkpoint, or idempotent retry |
| Ownership state | Leader flags, locks, leases | Re-acquire and verify with coordinator |

This catalog turns general concepts into concrete actions. For instance, "the database must work after restore" is too broad. A concrete criterion might be "all connections belonging to the old pool are closed before checkpoint; the new pool opens readiness only after creating connections and executing a health query successfully."

## 4. Pre-Checkpoint Criteria

Checkpointing should occur only when the application has reached a safe point. This does not necessarily mean halting the entire process, but every piece of work in progress must have a well-defined state.

### 4.1. Stop Accepting New Work

When preparing for a checkpoint begins:

1. Transition the instance to a quiescing state.
2. Stop accepting new requests or route traffic to other instances.
3. Stop polling new messages from the broker.
4. Stop the scheduler from creating new tasks.
5. Prevent internal producers from enqueuing more work during drain.

Testable criteria:

- Once quiescing starts, no new requests are dispatched to workers preparing to shut down.
- Message consumers fetch no more messages beyond defined policy.
- Schedulers trigger no new executions during the checkpoint preparation window.
- Readiness or routing reflects that the instance is leaving service.

### 4.2. Drain In-Flight Work

An application must define what "drained" means:

- In-flight requests have returned responses or been canceled according to contract.
- Queued tasks have finished or remain intact for reprocessing.
- Workers have no partially completed write operations.
- In-flight messages have committed results prior to acknowledgment, or been returned for broker redelivery.
- No transactions remain in an indeterminate state.

Set a deadline for draining. If completion cannot finish within the deadline, the application must have a clear policy: abort checkpointing, safely cancel work, roll back transactions, or persist durable business state to resume after restore.

Do not use a fixed sleep as proof that workers have stopped. Use latches, conditions, counters, queue state, or shutdown/awaitTermination APIs to verify actual state.

### 4.3. Transactions and Commit Boundaries

A transaction must not be checkpointed in an indeterminate state. Before checkpoint:

- Commit transactions that are business-complete.
- Roll back transactions that cannot complete.
- Never acknowledge messages before business results are persisted.
- If a commit outcome is ambiguous due to a network error, query the authoritative source before retrying.
- For distributed transactions or sagas, store completed step state durably.

Example criterion:

> For every order creation request accepted prior to quiescing, after restore there must exist exactly one order record or the request is returned in a safely retriable state. There must never be a case where a success response was sent yet the order record is lost.

### 4.4. Flush and Close Resources

Each resource needs its own criteria:

| Resource | Pre-Checkpoint Criteria |
|---|---|
| File writer/appender | Buffers flushed, writer closed, no threads still writing to handle |
| JDBC pool | No active transactions or checked-out connections; pool suspended/closed per API |
| HTTP client | In-flight requests drained; client/connection pool closed per supported lifecycle |
| Message consumer | Stopped receiving messages; acknowledgments/offsets reflect committed results |
| Scheduler | Stopped scheduling new tasks; running tasks completed or recorded for recomputation |
| Custom socket | I/O stream halted at protocol boundary; socket closed or handled per integration |
| Native resource | Released or has integration confirming checkpoint capability |
| Lease/lock | Released or guarded by fencing mechanism preventing stale owner writes |

Never directly close an underlying file descriptor or socket beneath a library if the library still holds a reference to it. Call the owner's official lifecycle API.

### 4.5. Callbacks Must Complete Within Deadline

A `beforeCheckpoint` callback can fail due to timeouts, unresponsive dependencies, or workers failing to drain. Criteria must specify:

- Maximum duration per resource and for the entire preparation phase.
- Which failures abort the checkpoint.
- Which failures are retriable.
- How partially closed resources are rolled back or brought to a safe state.
- Which logs and metrics are emitted when a callback fails.

Do not mark the application "checkpoint-ready" if any mandatory resource has not finished cleanup. An inconsistent checkpoint can be harder to detect than an explicit failure.

## 5. Post-Restore Criteria

Restoration is only the first step. Before opening traffic, the application must recreate environment-dependent state and verify invariants.

### 5.1. Recreate External Resources

Common criteria:

- All old sockets are discarded or never reused.
- Database pools establish fresh connections and run a health query.
- HTTP clients establish fresh connections and verify TLS/hostnames.
- Consumers rejoin groups and receive valid assignments.
- File writers open the current active path after any rotation.
- Schedulers are recreated with schedules computed from the current time.
- Native resources are initialized via supported integrations.

Do not treat a non-null Java object as proof that the underlying resource is still valid. Verify through actual protocol-appropriate operations.

### 5.2. Refresh Time-Bounded State

After restore, the application must verify:

- Tokens are unexpired and match the proper audience/scope.
- Certificates are still valid, with matching hostnames and trust chains.
- Whether session tickets or session caches may be used per policy.
- Leases remain valid and belong to the current instance.
- DNS and endpoints are resolved per current policy.
- Cache TTLs and business deadlines have not expired.

If a state has expired, the application must acquire fresh state or enter an unready state. Never continue using stale data merely because it still sits on the heap.

### 5.3. Recreate Instance Identity

If a checkpoint image may be used for multiple replicas, values on the heap may be identical. Criteria must distinguish:

- Service identity shared by design.
- Replica identity, which must be unique per replica.
- Process incarnation ID, which can change on each restore.
- Business IDs and idempotency keys, which must remain stable per business operation.
- Consumer member IDs, lease tokens, and local resource paths reissued within scope.

Test multiple replicas from the same image to detect duplicate IDs and cloned ownership state.

### 5.4. Recovery Order and Readiness

Interdependent resources must be recovered in the correct order. For example, the database pool must be ready before workers start processing messages that write to the database.

A good readiness criterion includes:

1. Current identity has been verified.
2. Required credentials have been refreshed or confirmed valid.
3. Required clients and pools have opened new connections.
4. Consumers/schedulers have registered valid state.
5. Leases and ownership have been confirmed.
6. Minimum business health checks succeed.

Liveness only confirms the process is alive. Readiness decides whether the instance can accept traffic. Do not open readiness simply because `afterRestore` callbacks started or the JVM restored successfully.

## 6. Writing Measurable Acceptance Criteria

A good criterion includes input conditions, actions, expected results, and evidence. Avoid vague statements such as "restore succeeds," "no data loss," or "stable connections" without defining how to measure them.

### 6.1. Criteria Template

~~~text
ID:
Criterion name:
Scope:
Preconditions:
Checkpoint operation:
Conditions during pause:
Restore operation:
Expected result:
Time limit:
Evidence:
Failure behavior:
~~~

### 6.2. Concrete Criterion Examples

**AC-01 — Committed Data**

- Preconditions: create a record and confirm the transaction committed.
- Operation: checkpoint, stop the JVM, restore.
- Outcome: record still exists with unchanged content.
- Evidence: query database with a fresh connection and compare key/value.
- Failure: instance does not open readiness if database cannot be verified.

**AC-02 — In-Flight Message**

- Preconditions: consumer receives a message with a known ID and begins processing.
- Operation: request checkpoint during processing.
- Outcome: message is either committed once in business state, or redelivered by broker and processed idempotently; never acknowledged prior to durable persistence.
- Evidence: message ID, business record, offset/ack, and side-effect count.

**AC-03 — Database Connections**

- Preconditions: application has an active pool.
- Operation: close pool before checkpoint, restart database during pause, restore.
- Outcome: new pool connects once database is ready; no old connections used.
- Evidence: connection creation metrics, health query, and pool lifecycle logs.
- Time limit: readiness opens only within configured deadline; if exceeded, instance stays unready.

**AC-04 — Expired Token**

- Preconditions: short-lived token issued before checkpoint.
- Operation: pause longer than token lifetime, then restore.
- Outcome: old token is not sent; application obtains a new token before calling protected APIs.
- Evidence: non-sensitive token issuer/audience/expiry metadata and service-side request audit.

**AC-05 — Expired Lease**

- Preconditions: replica A holds a lease with fencing token N.
- Operation: checkpoint A; during pause, lease expires and replica B receives a higher token.
- Outcome: after restore, A does not write with token N; A must acquire a new lease or remain in follower state.
- Evidence: coordinator lease record and storage rejecting writes carrying old tokens.

**AC-06 — Multiple Replicas**

- Preconditions: one checkpoint image can launch at least two replicas.
- Operation: restore two copies concurrently.
- Outcome: service identity matches by config; replica/incarnation IDs differ; no duplicate member IDs or local paths.
- Evidence: per-replica metadata, registry records, and logs/metrics.

**AC-07 — File Rotation**

- Preconditions: application is writing to a log file.
- Operation: close writer before checkpoint; rename file and create a new file while JVM is stopped; restore.
- Outcome: post-restore logs write to the active path.
- Evidence: old/new file contents, inode or file identity, and post-restore log markers.

### 6.3. Quantifying Thresholds

Thresholds must align with system SLOs:

- Maximum duration for `beforeCheckpoint`.
- Maximum duration for `afterRestore`.
- Time from restore to readiness.
- Maximum retry count and backoff.
- Number of requests or messages allowed to retry.
- Acceptable data loss window (RPO), if any.
- Maximum recovery time (RTO).
- Restore success rate across a batch of runs.

Do not pick arbitrary numbers. Use startup baselines, SLOs, dependency latencies, and actual checkpoint/restore timings to set thresholds.

## 7. Designing a Pre- and Post-Restore Test Matrix

A test matrix ensures testing covers more than the happy path.

| Category | Pre-Checkpoint Condition | Change During Pause | Post-Restore Criteria |
|---|---|---|---|
| Data | Committed record present | Unchanged or updated by another replica | Reads latest data per consistency contract |
| Transaction | Open transaction | JVM stopped | Deterministic commit/rollback; no orphaned transactions |
| HTTP request | In-flight request | Client times out or retries | No duplicate side effects created |
| Message | Consumer holds message | Broker session expires | Rejoins group, reprocesses safely, or confirms outcome |
| Database | Pool active | Database restarts/credentials rotate | New pool and health query succeed |
| TLS | Active TLS connection | Certificate/CA rotates | New handshake verifies valid certificate and hostname |
| File | Writer open | Rename/create or copytruncate | Writer reopens active path properly |
| Scheduler | Periodic schedule | Deadline passes | Runs/skips missed run per policy |
| Lease | Instance holds lease | Lease expires, another owner acquires lease | Old owner cannot write with stale token |
| Token | Valid access token | Token expires or is revoked | Refreshes/re-authenticates before calling services |
| Cache | Warmed-up cache | Source data changes | Cache refreshes or validates version |
| Identity | Instance ID on heap | Restored into multiple replicas | Each replica has distinct identity |
| Native resource | Library holds handle | Runtime checkpoint/restore | Resource recreated or checkpoint explicitly rejected |
| Filesystem | Volumes and temp files present | Mounts/permissions change | Paths and permissions are verified |
| Security | Process holds current policy | Secrets/certificates/policies rotate | Restore does not use stale credentials or security context |
| Resilience | Healthy application | Callback or dependency fails | Keeps readiness closed; errors observed and retried per policy |

### 7.1. Testing Short and Long Pauses

Do not restore only immediately after checkpointing. Run multiple pause durations:

- Nearly immediate.
- Longer than connection idle timeout.
- Longer than token or session lifetime.
- Longer than lease duration.
- Across certificate or configuration rotation boundaries.
- Long enough for cache TTLs and scheduler deadlines to change.

Pause durations should be chosen from actual dependency timeouts. A 1-second pause test cannot prove system safety when production pauses can last minutes or hours.

### 7.2. Testing Repeated Checkpointing

An application may be checkpointed multiple times in its lifecycle. Check:

- Callbacks do not accumulate duplicate listeners or resources.
- Executors are not shut down and then reused in an invalid state.
- Old clients are not retained after each restore.
- Each incarnation generates identity according to policy.
- Caches and tokens are refreshed per lifecycle.
- No monotonic growth in threads, sockets, file descriptors, or connections.

Repeated testing uncovers resource leaks and non-idempotent callbacks.

### 7.3. Testing Multiple Replicas from One Checkpoint

If the environment scales out, restore at least two instances from the same image. Confirm:

- Replica identities differ.
- Service identity remains identical if that is the contract.
- Leases or leader states are not shared.
- Consumer groups have distinct members.
- Temporary files, socket paths, and metric labels do not collide.
- Credentials are issued per policy.
- Two replicas do not cause duplicate side effects when receiving the same request/message.

## 8. Testing Failure Paths

Correctness testing must include scenarios where checkpointing or restoring cannot complete.

### 8.1. `beforeCheckpoint` Failure

Possible failures:

- Worker fails to drain within deadline.
- Database fails to roll back transaction.
- File writer fails to flush or close.
- Client cannot close connections.
- Dependent resource not ready.

Criteria:

- Failure is reported clearly.
- Checkpoint is not considered successful if mandatory resources failed to finish preparing.
- Application does not continue serving traffic in an indeterminate quiescing state.
- Partially modified resources are recovered or application enters a controlled shutdown.

### 8.2. `afterRestore` Failure

Possible failures:

- Secret manager unavailable.
- Database or broker restarting.
- New certificate untrusted.
- Lease already held by another replica.
- Volume unmounted or switched to read-only.

Criteria:

- Instance keeps readiness closed.
- Bounded retries with backoff and jitter.
- Error carries appropriate code or diagnostic details.
- Never fall back to stale credentials or sockets to bypass errors.
- Upon timeout, instance enters an observable failed state handled by the orchestrator.

### 8.3. Mid-Restore Failure

Some resources may have been recreated while another fails. Determine:

- Can callbacks or bootstrap retry without creating duplicate resources?
- Are already-created resources closed when a subsequent step fails?
- Which resources can recover independently?
- Should the instance be destroyed and recreated from checkpoint?
- Does readiness stay closed until every mandatory dependency is ready?

Idempotent bootstrap design allows retrying without creating duplicate clients, threads, or subscriptions.

### 8.4. Incompatible Checkpoint Images

Checkpoints can be bound to specific JDK builds, native libraries, kernels, filesystems, and runtimes. Test these scenarios:

- Restoring with a different JDK version.
- Changed native libraries or agents.
- Changed CPU features or node architecture.
- Changed mounts, volumes, or network namespaces.
- Changed container runtime or checkpoint engine.

If the environment is incompatible, the system must explicitly reject restore or fall back to the normal startup path. Never mark an instance ready when the runtime has not verified state.

## 9. Evidence and Observability

Criteria are useful only if compliance can be proven. Design logs, metrics, and traces from the start.

### 9.1. Lifecycle Logs

Record milestones:

- Checkpoint preparation started.
- Quiescing started and completed.
- Count of active requests/tasks/messages.
- Each resource starting and ending callbacks.
- Checkpoint requested, succeeded, or failed.
- Restore started and finished.
- Each resource recovering successfully or failing.
- Dependency health checks.
- Readiness closing and opening.

Every log must carry service identity, replica identity, process incarnation ID, and appropriate correlation IDs. Never log access tokens, refresh tokens, passwords, or private keys.

### 9.2. Suggested Metrics

| Metric | Meaning |
|---|---|
| checkpoint_prepare_duration_seconds | Time spent preparing before checkpoint |
| checkpoint_resource_callback_duration_seconds | Callback duration per resource |
| checkpoint_failure_total | Total checkpoint failures |
| restore_duration_seconds | Runtime restore duration |
| restore_resource_failure_total | Count of resource recovery failures |
| restore_to_ready_seconds | Time from restore to readiness |
| active_requests_at_checkpoint | Active requests when checkpoint begins |
| pending_messages_at_checkpoint | Incomplete messages |
| recreated_connections_total | Total connections recreated |
| stale_credential_rejection_total | Count of stale credentials rejected |
| lease_reacquire_failure_total | Count of failed lease reacquisitions |
| duplicate_operation_detected_total | Duplicate side effects detected/blocked |

Metric names are suggestions; follow the conventions and cardinality policies of your observability system. Do not put request IDs, user IDs, or instance UUIDs into high-cardinality metric labels. Those values belong in logs or traces.

### 9.3. Tracing and Correlation

A request may start before checkpoint and be retried after restore. Traces should preserve correlation or idempotency keys per business operation, while the process incarnation ID changes with the new process. That makes it possible to distinguish a single business operation spanning multiple incarnations from two separate operations.

Do not use process ID or thread ID as a stable business correlation ID. Those IDs may change or be reused after restore.

## 10. Test Stratification

No single test type suffices to validate an entire CRaC application.

### 10.1. Unit Tests for Resource Logic

Test each resource individually:

- `beforeCheckpoint` invokes pause, drain, flush, and close in the right sequence.
- `afterRestore` recreates resources and does not reuse old objects.
- Failures during initialization do not publish ready state.
- Retries do not create duplicate resources.
- Callbacks can be invoked multiple times per supported lifecycle without leaks.

Mock external dependencies to test ordering and error policies. Do not mock CRaC and conclude that kernel checkpointing works.

### 10.2. Integration Tests with a Real CRaC Runtime

Run on a CRaC-enabled JDK/runtime:

1. Start the application with production-like configuration.
2. Warm up according to procedure.
3. Send requests/messages and generate test data.
4. Request a checkpoint.
5. Change dependency state during the pause window.
6. Restore from the image.
7. Send new requests/messages and verify invariants.
8. Collect logs, metrics, database/broker state, and readiness time.

Integration tests require the same kind of filesystem, network, runtime, and critical dependencies as the target environment.

### 10.3. End-to-End Tests

Test the full flow from client to database, broker, and external services. Especially critical for:

- Payments and operations with side effects.
- Sagas or multi-step workflows.
- Consumer groups and offsets.
- APIs with retries/idempotency.
- Schedulers and batch jobs.
- Systems with multiple replicas restoring concurrently.

### 10.4. Chaos and Fault Injection

In a controlled test environment, proactively:

- Restart the database or broker while the JVM is stopped.
- Block DNS or networking during restore.
- Rotate certificates and tokens.
- Expire leases or change leadership.
- Switch volumes to read-only.
- Cause callback timeouts.
- Reject one credential issuance attempt.
- Deliver the same message/request multiple times.

The goal is to prove the application preserves invariants under failure conditions, not just on the happy path.

## 11. Example End-to-End Test Scenario

Suppose the Orders application handles order creation requests, saves to a database, and sends events to a broker. It has an HTTP client to a pricing service and a reference cache.

### 11.1. Initial Conditions

- Database holds reference data version 10.
- Broker has consumer group `orders-events`.
- Instance holds a pricing token valid for 30 seconds.
- In-heap cache is warmed up with version 10.
- An order creation request with idempotency key `K-100` is in progress.

### 11.2. Checkpoint Preparation

1. Transition instance to quiescing and close readiness.
2. Stop accepting new requests.
3. Request `K-100` completes its transaction and writes an outbox record, or rolls back per policy.
4. Consumer stops receiving new messages; acknowledgment happens only after commit.
5. HTTP client and database pool are closed per API.
6. Cache is marked to verify version after restore.
7. Resource callbacks complete and checkpoint is created.

### 11.3. Changes During Pause

- Database is updated to reference data version 11.
- Pricing token expires.
- Broker closes old sessions and rebalances partitions.
- Instance lease expires.

### 11.4. Recovery

1. Generate a new process incarnation ID.
2. Fetch a fresh pricing token.
3. Create new HTTP client and database pool.
4. Read reference data version from database; refresh cache from version 10 to 11.
5. Rejoin consumer group and receive new assignment.
6. Acquire a new lease; if not granted, do not execute leader tasks.
7. Verify health checks.
8. Open readiness.

### 11.5. Assertions

- Result for `K-100` exists exactly once.
- Outbox event is emitted according to the transaction contract.
- No message is acknowledged before durable persistence of results.
- New requests use the new token.
- Cache never serves version 10 once the application confirmed version 11 is required.
- Consumer carries a new member identity.
- Instance never writes with the old lease token.
- Readiness opens only after required steps finish.
- Logs/traces distinguish process incarnations before and after restore.

This scenario tests a chain of invariants across multiple systems. It is far more valuable than merely checking that an endpoint returns HTTP 200 after restore.

## 12. Handling Results and Pass/Fail Criteria

Before running tests, define how to evaluate outcomes:

### Pass

- All mandatory invariants hold.
- Resources are closed and recreated following proper lifecycle.
- No duplicate side effects or data loss outside contract.
- Credentials and ownership are re-verified.
- Readiness opens only when conditions are met.
- Recovery duration falls within SLO thresholds.
- Logs/metrics suffice to prove the outcome.

### Fail

- Committed data is lost.
- Side effects execute twice or messages are lost due to out-of-order acknowledgment.
- Instance uses expired sockets, tokens, leases, or identities.
- Mandatory callback failed yet checkpoint/restore is still treated as successful.
- Readiness opens before mandatory dependencies are ready.
- Restore creates duplicate resources or workers.
- Recovery duration exceeds threshold with no defined fallback behavior.

### Inconclusive

- Test failed to collect sufficient evidence.
- Test dependencies do not reflect the target environment.
- Checkpoint/restore did not actually occur via the intended engine.
- Outcomes of side effects or transactions cannot be determined.

Never turn an inconclusive test into a pass just because the process stayed alive. If evidence is lacking, add instrumentation or redesign the test.

## 13. Organizing Criteria Within a Project

A criteria set can be maintained as documentation or numbered test cases. Each criterion should link to:

- The business invariant it protects.
- The responsible resource or component.
- The unit/integration/e2e test verifying it.
- Metrics or logs used as evidence.
- SLO or time limit.
- Owner responsible when the test fails.

Example mapping:

| Criterion | Invariant | Component | Test | Evidence |
|---|---|---|---|---|
| AC-01 committed data | No loss of committed data | Repository/transaction manager | DB integration | Record and transaction state |
| AC-02 message | No ack before commit | Consumer/outbox | Broker integration | Offset, ack, business record |
| AC-03 connection | No reuse of old connections | DataSource/HTTP client | Resource + integration | Connection ID, health query |
| AC-04 credential | No use of expired tokens | Token provider | Expiry fault test | Issuer/audience/expiry metadata |
| AC-05 lease | Old owner cannot write | Coordinator/storage | Lease expiry test | Fencing token and rejected write |
| AC-06 replica | Non-duplicate instance IDs | Bootstrap/identity provider | Multi-replica test | Replica metadata |
| AC-07 readiness | Accepts traffic only when ready | Health/readiness endpoint | E2E | Readiness transition |

Whenever code alters resource lifecycles, rerun related tests. Whenever upgrading the JDK, framework, drivers, pools, or container runtime, rerun CRaC integration tests because resource behavior can vary across versions.

## 14. Mistakes When Defining Criteria

| Mistake | Why It Is Insufficient | Fix |
|---|---|---|
| Checking only that JVM restore succeeds | Does not prove dependencies or business logic work | Test through readiness and side effects |
| Checking only HTTP 200 | Simple requests may not touch database/broker | Test business flows with real dependencies |
| Not simulating pause duration | Misses token, lease, TTL, or connection timeouts | Pause longer than actual timeouts |
| Testing only a single replica | Misses duplicated IDs, leases, or member identities | Restore multiple replicas from the same image |
| Testing callbacks with mocks only | Misses kernel, sockets, file descriptors, and native resources | Add real checkpoint/restore runs |
| Not testing callback failures | Leaves partial-state handling unknown | Inject faults into each resource |
| Using sleep for drain | Does not prove tasks stopped | Use synchronization primitives and observable state |
| Not testing idempotency | Post-restore retries may repeat side effects | Use idempotency keys and check storage |
| Opening readiness immediately after restore | Dependencies may not be ready yet | Gate readiness on mandatory health checks |
| Not checking checkpoint image provenance | May restore an artifact from wrong environment or untrusted source | Verify digest, version, origin, and policy |
| Not setting time thresholds | Cannot measure RTO or detect hung callbacks | Define timeouts and SLOs |
| Not tagging logs by incarnation | Hard to separate pre- and post-restore errors | Attach process incarnation ID to logs/traces |

## 15. Correctness Criteria Checklist

### Before Writing Tests

- [ ] Identify application type and checkpoint engine.
- [ ] List dependencies and application-owned resources.
- [ ] Document invariants for data, side effects, concurrency, and security.
- [ ] Classify state to retain, refresh, or discard.
- [ ] Determine maximum pause window and timeouts that may expire.
- [ ] Define handling for in-flight requests, transactions, messages, and schedulers.

### Before Checkpoint

- [ ] Stop accepting new work.
- [ ] Drain requests, workers, and queues.
- [ ] Commit/roll back transactions per contract.
- [ ] Flush/close files and clients per official API.
- [ ] Verify leases/locks and ownership.
- [ ] Have callback deadlines and failure behavior.

### After Restore

- [ ] Recreate sockets, pools, clients, and native resources.
- [ ] Refresh tokens, certificates, sessions, and secrets as needed.
- [ ] Verify identity and leases.
- [ ] Refresh or validate caches.
- [ ] Rejoin broker groups and schedulers.
- [ ] Health-check mandatory dependencies.
- [ ] Open readiness only after all required conditions pass.

### Testing and Evidence

- [ ] Unit tests exist for each Resource.
- [ ] Integration tests exist using a real CRaC runtime.
- [ ] Short and long pause duration tests exist.
- [ ] Callback failure and unavailable dependency tests exist.
- [ ] Repeated checkpoint/restore tests exist.
- [ ] Multi-replica tests from the same image exist if scaling out is needed.
- [ ] Side-effect/idempotency and message acknowledgment tests exist.
- [ ] Logs/metrics/traces distinguish incarnations.
- [ ] Clear RTO, timeout, and retry thresholds exist.
- [ ] Explicit pass, fail, and inconclusive criteria exist.

## 16. Key Principles to Remember

- Post-restore correctness is defined by business and operational invariants, not merely by the JVM remaining alive.
- Distinguish process recovery, resource recovery, business recovery, and service readiness.
- Every state must have a clear policy: preserve, verify, refresh, recreate, or discard.
- Before checkpointing, stop accepting new work, drain in-flight work, and bring transactions to deterministic boundaries.
- Resource callbacks must have deadlines, explicit errors, and policies for partial cleanup states.
- After restore, recreate connections, refresh credentials, and verify ownership before serving traffic.
- Use idempotency and authoritative data sources to handle side effects or messages that may be redelivered.
- Test pauses long enough for tokens, leases, caches, and connection timeouts to change.
- Restore multiple replicas from the same image to detect duplicated identities and ownership state.
- Unit testing callbacks does not replace integration testing with a real CRaC runtime.
- Readiness must reflect business serving capability; do not open it solely because JVM restore succeeded.
- Every criterion needs expected outcomes, measurable bounds, and evidence.

Establishing pre- and post-restore correctness criteria gives development teams clarity on what must be preserved, what must be recreated, and when an instance is permitted to resume operations. When invariants are written as measurable acceptance criteria, CRaC testing catches data, side-effect, resource, identity, and security bugs before checkpoint images reach production.
