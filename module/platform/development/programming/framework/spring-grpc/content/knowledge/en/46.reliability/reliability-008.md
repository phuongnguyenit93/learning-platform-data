# Persisting request state for long-running tasks

An RPC may launch work that lasts minutes or hours: exporting reports, batch data processing, inventory synchronization, or creating backups. Keeping a single RPC open for that entire duration risks client deadline expiration, dropped connections, or restarts; the server itself may also restart mid-flight. In Spring gRPC, the more reliable approach is **persisting operation state durably**, returning an operation identifier early, and letting clients query progress/results via separate RPCs.

State must reside in durable storage such as a database, not merely in a `Map`, singleton field, or worker memory. When a process stops, another worker must be able to continue or recover the operation from saved data.

## 1. Decoupling RPC lifecycle from operation lifecycle

The `StartExport` RPC only accepts the request and creates the operation. It should complete quickly once the operation and dispatch record have committed. The actual work runs in a background worker:

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant S as Spring gRPC Service
    participant DB as Operation DB
    participant O as Outbox Publisher
    participant W as Worker
    C->>S: StartExport(request, idempotency_key)
    S->>DB: INSERT operation + outbox in one transaction
    DB-->>S: operation_id, state=QUEUED
    S-->>C: Operation(QUEUED)
    O->>DB: Read unpublished outbox
    O->>W: Dispatch operation_id
    W->>DB: Claim operation, lease + fencing token
    W->>W: Execute and persist progress
    W->>DB: Persist SUCCEEDED / FAILED
    C->>S: GetOperation(operation_id)
    S->>DB: Read latest state
    DB-->>S: Operation snapshot
    S-->>C: Operation(state, progress, result)
~~~

The submission RPC uses a short deadline appropriate for recording the operation. That RPC's deadline is not the background job's deadline. If the client disconnects after the server commits the operation, the job continues according to published policy; the client looks it up using the operation ID or idempotency key.

## 2. Designing the operation contract

A minimal API can provide `StartExport`, `GetOperation`, `WatchOperation`, and `CancelOperation`:

~~~proto
syntax = "proto3";

package acme.export.v1;

option java_multiple_files = true;
option java_package = "com.acme.export.v1";

import "google/protobuf/timestamp.proto";
import "google/rpc/status.proto";

service ExportService {
  rpc StartExport(StartExportRequest) returns (Operation);
  rpc GetOperation(GetOperationRequest) returns (Operation);
  rpc WatchOperation(WatchOperationRequest) returns (stream Operation);
  rpc CancelOperation(CancelOperationRequest) returns (Operation);
}

enum OperationState {
  OPERATION_STATE_UNSPECIFIED = 0;
  OPERATION_STATE_QUEUED = 1;
  OPERATION_STATE_RUNNING = 2;
  OPERATION_STATE_CANCEL_REQUESTED = 3;
  OPERATION_STATE_SUCCEEDED = 4;
  OPERATION_STATE_FAILED = 5;
  OPERATION_STATE_CANCELLED = 6;
}

message StartExportRequest {
  string idempotency_key = 1;
  string source_id = 2;
  string format = 3;
}

message Operation {
  string name = 1;
  OperationState state = 2;
  int32 progress_percent = 3;
  string result_uri = 4;
  google.rpc.Status error = 5;
  google.protobuf.Timestamp created_at = 6;
  google.protobuf.Timestamp updated_at = 7;
  int64 version = 8;
}

message GetOperationRequest {
  string name = 1;
}

message WatchOperationRequest {
  string name = 1;
  int64 after_version = 2;
}

message CancelOperationRequest {
  string name = 1;
}
~~~

`name` is a stable operation identifier, e.g., `operations/01J...`; clients should not choose their own tenant or owner via this field. The server derives the tenant from the authenticated principal and verifies the operation belongs to that tenant. `result_uri` should point to a durably stored artifact; never embed large files in status messages.

`WatchOperation` is a convenient change-notification stream, whereas `GetOperation` is the re-queryable snapshot source. Streams can break and do not inherently guarantee replay; `after_version` lets clients request updates after the last received version, or the server can return the current snapshot if event history is no longer retained.

## 3. Durable data model

An operations table can store the following fields:

~~~sql
CREATE TABLE operations (
    id               VARCHAR(64) PRIMARY KEY,
    tenant_id        VARCHAR(128) NOT NULL,
    idempotency_key  VARCHAR(128) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    state            VARCHAR(32) NOT NULL,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    result_uri       TEXT,
    error_code       VARCHAR(64),
    error_message    TEXT,
    error_details    BYTEA,
    attempt          INTEGER NOT NULL DEFAULT 0,
    available_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_owner      VARCHAR(128),
    lease_until      TIMESTAMP WITH TIME ZONE,
    fencing_token    BIGINT NOT NULL DEFAULT 0,
    version          BIGINT NOT NULL DEFAULT 0,
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (tenant_id, idempotency_key)
);
~~~

Outbox and event logs can be stored separately:

~~~sql
CREATE TABLE outbox_events (
    event_id      VARCHAR(64) PRIMARY KEY,
    operation_id  VARCHAR(64) NOT NULL,
    event_type    VARCHAR(64) NOT NULL,
    payload       BYTEA NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at  TIMESTAMP WITH TIME ZONE
);

CREATE TABLE operation_events (
    operation_id      VARCHAR(64) NOT NULL,
    version           BIGINT NOT NULL,
    state             VARCHAR(32) NOT NULL,
    progress_percent  INTEGER NOT NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (operation_id, version)
);
~~~

`error_details` can store sanitized rich errors as serialized Protobuf; if rich details are unnecessary, store only normalized error codes and messages. `available_at` determines when an operation becomes eligible for retry after backoff. `operation_events` serves as the replay log for `WatchOperation` if the product needs version-by-version replay; without an event log, the endpoint can only return the latest snapshot.

Key columns:

- `tenant_id` enforces authorization and data isolation.
- `idempotency_key` prevents clients from creating duplicate operations when retrying submission requests.
- `request_hash` detects callers reusing a key with a different payload.
- `state`, `progress_percent`, `result_uri`, `error_*` form the public status snapshot.
- `attempt`, `lease_owner`, `lease_until` support worker claiming and recovery.
- `fencing_token` prevents an old worker from overwriting a newer worker's results.
- `version` supports optimistic concurrency and client watch resumption.

You do not need to store large inputs or outputs inside this table. Normalized requests can live in object storage or a separate table with an immutable reference stored on the operation. Ensure enough data is persisted for a worker to recover without relying on the memory of the process that created the request.

## 4. Creating operation and outbox in the same transaction

A common bug is writing the operation to the database and then sending a message to the broker separately. If the process stops between those two steps, the operation sits in `QUEUED` and is never dispatched. A transactional outbox closes that gap: persist the operation and dispatch event in the same transaction; a publisher reads the outbox and retries sending until it succeeds.

Service-layer example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExportSubmissionService {

    private final OperationRepository operations;
    private final OutboxRepository outbox;
    private final RequestHasher requestHasher;
    private final OperationIdGenerator idGenerator;

    public ExportSubmissionService(
            OperationRepository operations,
            OutboxRepository outbox,
            RequestHasher requestHasher,
            OperationIdGenerator idGenerator) {
        this.operations = operations;
        this.outbox = outbox;
        this.requestHasher = requestHasher;
        this.idGenerator = idGenerator;
    }

    @Transactional
    public OperationRecord submit(String tenantId, StartExportRequest request) {
        String hash = requestHasher.hashCanonicalRequest(request);

        var inserted = operations.insertIfAbsent(
            idGenerator.newId(),
            tenantId,
            request.getIdempotencyKey(),
            hash,
            "QUEUED");

        if (inserted.isPresent()) {
            OperationRecord created = inserted.get();
            outbox.append("EXPORT_REQUESTED", created.getId());
            return created;
        }

        OperationRecord existing = operations
            .findByTenantAndIdempotencyKey(
                tenantId, request.getIdempotencyKey())
            .orElseThrow();

        if (!existing.getRequestHash().equals(hash)) {
            throw new IdempotencyKeyConflictException();
        }

        return existing;
    }
}
~~~

`insertIfAbsent` must be implemented with a unique constraint on `(tenant_id, idempotency_key)` and an atomic operation, such as `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL. Append to the outbox only when a new operation is created. For the same key and same request hash, return the existing operation; for the same key with a different payload, fail with a clear conflict error instead of silently altering the accepted request.

The publisher may emit the event multiple times if it crashes after publishing but before marking the outbox processed. Workers must therefore be idempotent by operation ID; never assume the message broker delivers strictly once.

The gRPC adapter simply resolves the tenant from the authenticated principal, calls the application service, and returns the snapshot. Condensed example:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class ExportGrpcService
        extends ExportServiceGrpc.ExportServiceImplBase {

    private final ExportSubmissionService submissions;
    private final AuthenticatedTenantResolver tenantResolver;
    private final OperationMapper operationMapper;

    public ExportGrpcService(
            ExportSubmissionService submissions,
            AuthenticatedTenantResolver tenantResolver,
            OperationMapper operationMapper) {
        this.submissions = submissions;
        this.tenantResolver = tenantResolver;
        this.operationMapper = operationMapper;
    }

    @Override
    public void startExport(
            StartExportRequest request,
            StreamObserver<Operation> observer) {
        try {
            String tenantId = tenantResolver.currentTenantId();
            OperationRecord record = submissions.submit(tenantId, request);
            observer.onNext(operationMapper.toProto(record));
            observer.onCompleted();
        } catch (IdempotencyKeyConflictException conflict) {
            observer.onError(Status.ALREADY_EXISTS
                .withDescription("idempotency key was used with another request")
                .asRuntimeException());
        }
    }
}
~~~

The adapter does not send events directly to the broker; the application service already wrote the outbox record alongside the operation inside the transaction. `tenantResolver` must read identity from the authentication context/interceptor, never from a field in the request body.

## 5. State machine and transition conditions

A state machine clarifies which transitions are legal:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: worker claim
    QUEUED --> CANCELLED: cancel before running
    RUNNING --> SUCCEEDED: result committed
    RUNNING --> FAILED: non-retryable error
    RUNNING --> CANCEL_REQUESTED: caller requests cancel
    CANCEL_REQUESTED --> CANCELLED: worker stops safely
    CANCEL_REQUESTED --> SUCCEEDED: finishes before cancel takes effect
    RUNNING --> QUEUED: transient error, attempts left
~~~

Terminal states are typically `SUCCEEDED`, `FAILED`, and `CANCELLED`. A terminal operation must never transition back to `RUNNING`; if a rerun is needed after failure, create a new operation or define an explicit attempt/retry lifecycle.

Every transition must be guarded in the database, not just checked in Java followed by an unconditional update. For instance, transition `RUNNING` to `SUCCEEDED` only if the operation is still `RUNNING` and the worker's fencing token matches. `version` can be incremented on each update to detect concurrent overwrites.

## 6. Worker claiming via leases and fencing tokens

Workers should not hold a database transaction open across long-running work. Instead, claim the operation in a short transaction, record a time-bounded lease, and execute outside the transaction. PostgreSQL example using `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH candidate AS (
    SELECT id
    FROM operations
    WHERE (state = 'QUEUED' AND available_at <= CURRENT_TIMESTAMP)
       OR (state IN ('RUNNING', 'CANCEL_REQUESTED')
           AND lease_until < CURRENT_TIMESTAMP)
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE operations AS op
SET state = CASE
        WHEN op.state = 'CANCEL_REQUESTED' THEN 'CANCEL_REQUESTED'
        ELSE 'RUNNING'
    END,
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    fencing_token = fencing_token + 1,
    attempt = attempt + 1,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE op.id = candidate.id
RETURNING op.*;
~~~

Leases let another worker take over if the current worker dies and its lease expires. `fencing_token` increments on every claim; a stale worker holding a lower token cannot write progress or terminal states after a newer worker takes over. If the claimed row is in `CANCEL_REQUESTED`, the new worker only runs cleanup/cancellation and finalizes the operation rather than restarting the task.

On heartbeat, the worker renews its lease conditionally:

~~~sql
UPDATE operations
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    updated_at = CURRENT_TIMESTAMP
WHERE id = :operation_id
  AND state = 'RUNNING'
  AND lease_owner = :worker_id
  AND fencing_token = :fencing_token;
~~~

If zero rows are updated, the worker has lost ownership of the operation and must stop writing results. Lease duration must exceed the expected heartbeat interval with safety headroom for pauses/GC; heartbeats must not keep the main processing transaction open indefinitely.

Database fencing tokens only protect conditional updates inside the database. If the worker writes to an external system, that sink also needs an idempotency key, version/fencing token, or conditional write; otherwise, a stale worker can still cause external side effects after losing its lease.

## 7. Controlled progress and result updates

Progress should reflect meaningful milestones rather than updating the database on every single record. Guard updates with the fencing token:

~~~sql
UPDATE operations
SET progress_percent = GREATEST(progress_percent, :progress),
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :operation_id
  AND state = 'RUNNING'
  AND lease_owner = :worker_id
  AND fencing_token = :fencing_token;
~~~

Progress should increase monotonically between 0 and 100 and must never report 100 before the artifact is durably saved. On completion:

1. Write the artifact to storage under a stable operation/attempt key or via an atomic publish step.
2. Verify the artifact exists with required metadata/checksums.
3. Transition the operation to `SUCCEEDED`, store `result_uri`, increment `version`, and clear the lease in the same transaction.
4. Only then expose the succeeded state.

If a worker crashes after writing the artifact but before updating the operation, the rerun must recognize the completed artifact or overwrite safely by idempotency key. Never report `SUCCEEDED` while the result exists only in memory or an unpublished temporary file.

## 8. Recovery after process or worker restarts

After a restart, the service does not recover operations from old memory. It reads the database to serve current state. The worker scheduler scans for `QUEUED` operations and `RUNNING` operations with expired leases to take over.

A recovery flow needs to:

- Scan expired-lease operations and claim them with a new fencing token.
- Retry transient errors up to a max attempt limit using `available_at`/backoff.
- Mark `FAILED` on permanent errors or exhausted retry budgets.
- Use checkpoints to resume from committed progress instead of redoing expensive work from scratch.
- Make worker side effects idempotent or deduplicated by operation ID.
- Run a reconciliation job for operations stuck too long in `QUEUED`, `RUNNING`, or `CANCEL_REQUESTED`.

If using a broker, the outbox publisher keeps sending unacknowledged events. Workers must tolerate duplicate events, late events, and out-of-order events; database operation state is the authority for claim and transition rights.

## 9. Cancellation independent of client disconnects

A client disconnect only terminates the open RPC. It does not automatically mean the caller wants to cancel an accepted, durably persisted operation. Automatically wiring gRPC Context cancellation to background workers would allow flaky networks to kill jobs the caller still expects to finish.

Design the two actions distinctly:

- **Disconnect:** stops sending responses on the current RPC; the operation continues per policy.
- **CancelOperation:** caller invokes a dedicated RPC to request operation cancellation.

If the operation is still `QUEUED`, the server can transition it directly to `CANCELLED`. If `RUNNING`, transition to `CANCEL_REQUESTED`; the worker checks the cancel flag at checkpoints and stops safely. If work already committed its result before the cancellation took effect, the operation can still end `SUCCEEDED`; transitions must use compare-and-set to resolve the race.

Cancellation cannot always undo already-committed side effects. The contract must state whether cancel is best-effort or guaranteed to stop before a specific milestone.

## 10. GetOperation and WatchOperation

`GetOperation` returns the latest snapshot after verifying the tenant owns the operation. If it does not belong to the tenant, return a status per your security policy; avoid letting callers probe IDs belonging to other tenants.

`WatchOperation` can stream the initial snapshot and subsequent updates. Since gRPC streams can drop:

- Each update should carry a monotonically increasing `version`.
- The client records the last processed version.
- On reconnect, the client sends `after_version` to receive later updates or the latest snapshot.
- If event history has aged past retention, the server returns the current snapshot so the client resynchronizes.
- Clients can always fall back to `GetOperation` to recover state if the stream drops.

Do not treat the Watch stream as durable history storage. If full auditing is required, store operation events separately with explicit retention/access policies.

## 11. Security, tenant isolation, and retention

An operation ID is not a credential. Every `GetOperation`, `WatchOperation`, and `CancelOperation` RPC must authenticate the caller and authorize access to the tenant/resource. Never rely solely on UUID unpredictability.

Guidelines:

- Derive `tenant_id` from the authenticated principal; never trust a client-supplied field.
- Bound request sizes and validate formats/options before creating operations.
- Encrypt or restrict access to sensitive inputs/outputs.
- `result_uri` should grant time-limited access or route through an authorized endpoint.
- Stored error details must never contain tokens, secrets, or stack traces.
- Apply retention to terminal operations, outboxes, and artifacts; never delete active running operations.
- Audit submissions, cancellations, result reads, and key state transitions.

## 12. Testing contracts and operation durability

Tests must verify behavior across restarts and mid-step failures, not just check that the service returns a response:

| Scenario | Assertion |
| --- | --- |
| Successful submit | Operation and outbox commit in the same transaction |
| Retry with same idempotency key/request | Returns same operation ID, creates no second job |
| Reuse key with different payload | Returns conflict without modifying original operation |
| Process stops after commit before publish | Outbox publisher still dispatches after restart |
| Worker dies while RUNNING | Lease expires, another worker claims with a new fencing token |
| Stale worker writes after losing lease | Update rejected due to mismatched token |
| Client disconnects after submit | Operation continues and remains queryable |
| Cancel running operation | Transitions to CANCEL_REQUESTED then stops at checkpoint |
| Artifact saved, worker crashes before SUCCEEDED | Retry recognizes/publishes artifact safely |
| Another tenant reads operation | Rejected per authorization policy |
| Watch stream reconnect | Client resumes from version or receives snapshot |

Include integration tests with a real database and real broker/outbox relay or fault-injecting test doubles. Transaction tests must prove there is no case where an operation commits while event dispatch is permanently lost.

## 13. Observability and operations

Monitor:

- Operation counts by state and age of the oldest active operation.
- Time from `QUEUED` to `RUNNING`, processing duration, and total completion time.
- Expired leases, worker takeovers, and fencing rejections.
- Retry counts, failure reasons, and terminal operation rates.
- Outbox backlog, publish latency, and redelivered event counts.
- Cancellation rate and time from cancel request to `CANCELLED`.
- Watch stream disconnects/reconnects and snapshot resync counts.

Logs/traces should carry operation ID, safe tenant ID, worker ID, attempt, and fencing token. Never use unbounded operation IDs or tenant IDs as metric labels if cardinality is high; use histograms/counters grouped by operation type and state.

## 14. Key takeaways and self-check

**Persisting request state for long-running tasks** means turning background work into a durable operation with an ID, state machine, and persisted state. The submit RPC creates the operation and outbox record in one transaction and returns early; workers claim via leases/fencing tokens, update progress, and store results before marking terminal state. Clients use dedicated Get/Watch/Cancel RPCs, and an RPC disconnect does not automatically cancel the operation.

Self-check:

1. Why should a single RPC not stay open for the duration of a long-running task?
2. Which scenario does the transactional outbox protect against losing dispatch?
3. How do idempotency keys solve submission retries?
4. How do leases and fencing tokens prevent stale workers from overwriting results?
5. Why does a client disconnect differ from `CancelOperation`?
6. How does a Watch stream use versions/cursors to recover after reconnect?
7. When is an operation allowed to transition to `SUCCEEDED`?

Proper state persistence lets Spring gRPC survive process restarts, client timeouts/disconnects, and worker crashes while giving callers a stable contract to track or cancel long-running work.
