# Simulating Permission Errors, Timeouts, Duplicate Messages, and Recovery

## 1. Objectives of the Lab

This lab builds and tests a Spring Boot workflow integrating object storage, a queue, and a relational database. During execution, we intentionally inject three common failure categories:

1. **Permission errors (AccessDenied):** the workload lacks permission to read objects or publish/consume messages.
2. **Timeouts:** calls to storage/database/queue exceed client timeouts or message processing deadlines.
3. **Duplicate delivery:** the same event is delivered multiple times and could cause business logic to run repeatedly.

After each failure, we inspect logs/metrics, identify the exact identity and transaction boundary, fix the root cause, and recover the work. The goal is to prove the system can resume after failures without losing confirmed work or producing duplicate business side effects.

This lesson belongs to the **Spring Cloud Provider Integration** module: hands-on practice integrating Spring Boot with managed services across AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries. Examples share a common workflow and then contrast permission, timeout, and message settlement mechanisms across providers.

Desired outcomes:

- Identify which caller identity, worker identity, or service identity is causing an error.
- Distinguish authorization errors from network, timeout, or resource-not-found errors.
- Set per-layer timeouts and align them with queue visibility/lock/ack deadlines.
- Handle duplicates using event IDs, unique constraints, and idempotent side effects.
- Know when to retry, when to dead-letter, and when operator intervention is needed.
- Replay a message after fixing an error while preserving correlation/event IDs.
- Use automated tests to reproduce and verify recovery.

## 2. Lab Scenario and Architecture

### 2.1. Document processing scenario

An API receives documents, stores files in object storage, persists metadata, and emits a `document.stored` event. A worker receives the event, downloads the exact object version, computes a checksum, processes the file, saves outputs, and updates the database.

~~~mermaid
flowchart LR
    C["Client"] --> API["Spring Boot Upload API"]
    API --> S[("Object Storage")]
    API --> DB[("Metadata DB")]
    DB --> O["Outbox"]
    O --> R["Outbox Relay"]
    R --> Q[["Queue"]]
    Q --> W["Spring Boot Worker"]
    W --> S
    W --> DB
    W --> P["Document Processor"]
    P --> S
    W --> DLQ[["Dead-letter Queue"]]
~~~

Normal flow:

1. The API creates an upload intent and an opaque random object key.
2. The client/backend uploads the file to the bucket/container.
3. The API verifies object key, version/generation, size, and checksum.
4. A single DB transaction transitions the document to `STORED` and writes an outbox event.
5. The relay publishes the event to the queue.
6. The worker receives the message, checks document state, and downloads the object.
7. The worker processes and saves the output under a deterministic object key.
8. A DB transaction inserts the inbox/event ID, updates state to `PROCESSED`, and writes any next outbox event.
9. The worker acks/deletes/completes the message after the transaction commits.

Queue messages carry only `eventId`, `documentId`, `objectKey`, `objectVersion`, checksum, and correlation ID. Never send file bytes, access tokens, or pre-signed URLs inside messages.

### 2.2. Components and failure boundaries

| Component | Responsibility | Failures to simulate |
| --- | --- | --- |
| Upload API | Create intent, upload, finalize metadata | Object PUT denied/timeout |
| Outbox relay | Publish events after DB commit | Queue Send/Publish denied/timeout |
| Worker | Consume messages, download objects, process | Object GET denied/timeout |
| Database | Metadata, outbox, inbox, leases | Connection/query timeout, unique conflict |
| Queue | Buffer, delivery, visibility/lock, DLQ | Redelivery, lock expiry, poison message |
| Reconciliation job | Detect incomplete states | Recover orphan/outbox/lease records |

Do not use a single all-powerful identity across every component. API, relay, and worker need distinct permissions scoped by action and resource.

### 2.3. Provider mapping for the lab

| Capability | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object storage | S3 | Blob Storage | Cloud Storage |
| Queue | SQS | Service Bus Queue | Pub/Sub subscription |
| Database | RDS/Aurora | Azure Database for PostgreSQL/SQL | Cloud SQL |
| Workload identity | Task role, Pod Identity/IRSA, instance role | Managed Identity/Workload Identity | Service account, Workload Identity |
| Dead letter | SQS DLQ/redrive | Service Bus DLQ | Dead-letter topic/subscription policy |
| Object version | S3 VersionId | Blob version ID | GCS generation |

Providers do not share identical semantics. Specifically, message visibility/lock/ack deadlines, event retries, and IAM/RBAC actions must be verified against the exact service in use.

## 3. Preparing the Environment and Test Data

### 3.1. Application configuration

Conceptual Spring Boot configuration example:

~~~yaml
app:
  document:
    bucket: lab-documents
    source-prefix: source/
    result-prefix: processed/
  queue:
    name: document-processing
    dlq-name: document-processing-dlq
    max-attempts: 5
  processing:
    object-read-timeout: 3s
    overall-timeout: 20s
    lease-duration: 30s
~~~

These properties are application-defined settings, not standard Spring Cloud properties. Map them to the AWS SDK, Azure SDK, Google Cloud client, and queue adapter in your project. Never place credentials in YAML.

Use dedicated profiles for labs and staging. Fault injection must be disabled in production; never allow client requests to toggle faults in real runtime environments.

### 3.2. Sample event

~~~json
{
  "eventId": "evt-doc-1001-v1",
  "eventType": "document.stored",
  "schemaVersion": 1,
  "documentId": "doc-1001",
  "tenantId": "tenant-42",
  "object": {
    "bucket": "lab-documents",
    "key": "source/doc-1001/upload-1.pdf",
    "version": "object-version-1",
    "checksumSha256": "expected-checksum"
  },
  "correlationId": "req-lab-001"
}
~~~

The event ID is generated once and stored in the outbox. If the relay republishes after an ambiguous timeout, it must reuse the original event ID. Never generate a new event ID per retry.

### 3.3. Minimal database schema

~~~sql
CREATE TABLE document (
    document_id       VARCHAR(100) PRIMARY KEY,
    tenant_id         VARCHAR(100) NOT NULL,
    object_key        VARCHAR(1024) NOT NULL,
    object_version    VARCHAR(256),
    checksum_sha256   VARCHAR(128),
    status            VARCHAR(32) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(128),
    lease_until       TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE processed_event (
    consumer_name     VARCHAR(128) NOT NULL,
    event_id          VARCHAR(128) NOT NULL,
    document_id       VARCHAR(100) NOT NULL,
    processed_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

In a real system, add outbox tables, lease/fencing tokens, error categories, created timestamps, schema versions, indices on state/lease, and retention policies. The `(consumer_name, event_id)` primary key is the final database safeguard against processing the same event multiple times.

### 3.4. Safe fault injection methods

There are two approaches:

- **Automated tests:** swap adapters with fakes/mocks that throw `AccessDenied`, add delays, or emit duplicate events. This is deterministic and fits CI.
- **Cloud staging:** use an isolated test bucket/container/queue/database and a test workload identity with restricted policies. Modify policies, timeouts, or messages per lab step and restore afterward.

Never intentionally alter production IAM or run labs with admin credentials. Before every experiment, know the exact resource ARN/ID, identity, and affected operations.

## 4. Instrumentation Before Injecting Faults

### 4.1. Correlation and logs

Every step writes structured logs containing:

- `correlationId`, `eventId`, `documentId`.
- `component`, `operation`, `attempt`.
- `principal` or masked identity alias.
- `resource`/bucket/queue logical name.
- `durationMs`, `errorCategory`, `providerRequestId`.
- `messageDeliveryCount` or receive count when supplied by the provider.

Never log authorization headers, access keys, SAS tokens, pre-signed URLs, or file contents. Log provider error codes and request IDs sufficiently for investigation while stripping secrets.

### 4.2. Metrics

| Metric | Meaning |
| --- | --- |
| `storage_access_denied_total` | Count of storage permission denials |
| `queue_publish_failed_total` | Count of publish failures |
| `dependency_timeout_total` | Timeouts by dependency |
| `document_processing_duration` | Document processing duration |
| `message_delivery_count` | Number of times a message was delivered |
| `duplicate_event_total` | Events blocked by the inbox |
| `document_retry_total` | Business retry count |
| `dlq_message_count` | Messages currently in the DLQ |
| `outbox_oldest_age_seconds` | Age of oldest unpublished event |
| `expired_lease_total` | Count of expired leases |
| `reconciliation_repaired_total` | States repaired by reconciliation |

Never attach `documentId`, object keys, or event IDs as metric labels due to unbounded cardinality. Use logs/traces to drill down into individual requests.

### 4.3. Baseline before fault injection

Run at least one document successfully and record:

- Event ID, object version, and checksum.
- State transitions from `PENDING_UPLOAD` to `PROCESSED`.
- Message delivery count.
- Upload, queue wait, and processing durations.
- Correlated logs across API, relay, and worker.

A baseline distinguishes faults caused by injection from pre-existing configuration errors.

## 5. Lab 1 — Simulating AccessDenied Permission Errors

### 5.1. Goal and symptoms

Create a scenario where the worker can receive messages but lacks permission to read source objects. Expected behavior:

- The queue delivers the message successfully.
- The worker begins processing and calls object storage.
- Storage returns `AccessDenied` or HTTP 403.
- The worker classifies the error as authorization, logs/records metrics, and does not ack success.
- The message is retried per policy or routed to the DLQ once limits are reached; it does not retry forever.

Identity distinction: `ReceiveMessage` does not grant `GetObject`. A worker can read a queue while lacking bucket read permissions.

### 5.2. Creating the fault in unit/integration tests

Define an exception at the application boundary:

~~~java
public class StorageAccessDeniedException extends RuntimeException {

    public StorageAccessDeniedException(String message) {
        super(message);
    }
}
~~~

A fake adapter can intentionally reject reads:

~~~java
public class FaultInjectingObjectStore implements ObjectStore {

    private final ObjectStore delegate;
    private final FaultProfile faults;

    public FaultInjectingObjectStore(
            ObjectStore delegate,
            FaultProfile faults) {
        this.delegate = delegate;
        this.faults = faults;
    }

    @Override
    public InputStream get(ObjectKey key, String version) {
        if (faults.isEnabled("object-read-denied")) {
            throw new StorageAccessDeniedException(
                    "Simulated object read permission denied");
        }
        return delegate.get(key, version);
    }

    // Put/head/delete methods delegate to the underlying store.
}
~~~

This is a test adapter; a real implementation must implement the full `ObjectStore` interface. Register fault-injection beans only under a `fault-lab` profile or test configuration.

### 5.3. Creating permission errors on AWS staging

Create a dedicated test bucket/prefix and role. The worker role needs queue read permission but lacks object read permission. Example lab-restricted policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLabQueueReceive",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:REGION:ACCOUNT_ID:document-processing-lab"
    },
    {
      "Sid": "DenyLabSourceRead",
      "Effect": "Deny",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::lab-documents/source/*"
    }
  ]
}
~~~

Attach the policy to the lab worker role. Explicit deny applies only to the lab bucket/prefix; never edit production policies. If the role carries other policies, explicit deny makes test outcomes unambiguous because deny overrides allow.

### 5.3.1. Creating permission errors on Azure staging

Create a dedicated Managed Identity for the lab worker. Assign Service Bus Data Receiver so the worker receives messages, without assigning Storage Blob Data Reader on the source container. Use a separate identity with upload permission to stage the file. When the worker downloads the Blob, the read fails due to missing data-plane permissions.

After recording the principal and resource scope, assign Storage Blob Data Reader to that exact identity on the lab container. Retry GET with the same object key/version and redrive the message. Never use a Storage Account Key to bypass RBAC, as that defeats the test objective.

### 5.3.2. Creating permission errors on Google Cloud staging

Create a service account for the worker and grant Pub/Sub Subscriber on the lab subscription without granting bucket read access. The worker receives the event successfully, then `storage.objects.get` is denied. After recording error/request context, grant an appropriate role such as Storage Object Viewer on the lab bucket or a minimal custom role; re-run GET and replay the same event ID.

### 5.3.3. Extension: relay publish permission errors

To simulate a producer-side failure, remove publish permission from the relay identity: AWS `sqs:SendMessage`, Azure Service Bus Data Sender, or Google Pub/Sub Publisher. Outbox rows must remain unpublished and the relay records the failure; never mark events published before broker confirmation. Restore scoped permission, let the relay resume with the stored event ID, and verify consumer receipt.

### 5.4. Observing and identifying the principal

When receiving 403, check in order:

1. Which role/service account is the worker's actual principal?
2. Which bucket, container, or object key is being called?
3. Is the denied operation `GetObject`, `Get Blob`, `storage.objects.get`, or something else?
4. Are identity policies, resource policies, KMS/key policies, or permission boundaries blocking it?
5. Is the worker targeting the right account/project/subscription/region?

Do not infer missing permissions solely from an HTTP status code. Gateways/proxies can return 403 due to network policies or token audience mismatches; inspect provider error codes and request IDs to distinguish.

### 5.5. Fixing permissions and recovering

After confirming the exact principal and resource, grant source object read access:

- AWS: grant the worker `s3:GetObject` on the source prefix; if objects use a customer-managed KMS key, grant decrypt permissions per key policy and IAM policy.
- Azure: assign a blob data-plane read role at the required container scope; verify the active Managed Identity/Workload Identity.
- Google Cloud: grant `storage.objects.get` on the required bucket via an appropriate role or minimal custom role.

Once policies take effect:
1. Verify the worker identity using runtime/provider tools.
2. Run a test HEAD/GET against a test object.
3. Retry queued messages or redrive from the DLQ in small batches.
4. Keep the original event ID and document ID.
5. Verify the document transitions cleanly without duplicate results.

Never mark a document `PROCESSED` merely because permissions were fixed. Only the consumer after reading, processing, and committing may complete the state.

### 5.6. PASS criteria

- Logs identify the exact operation, resource, and identity alias.
- `storage_access_denied_total` increments accurately per failed attempt.
- The document is not marked completed.
- The message is not acked as successful.
- After granting permission, the same event processes successfully.
- No broad policies like `s3:*`, Storage Account Keys, or project Editor are used.

## 6. Lab 2 — Simulating Timeouts and Recovery

### 6.1. Distinguishing timeouts by layer

A workflow has multiple distinct deadlines. Never use a single timeout for the entire system:

| Timeout | What it protects | Example |
| --- | --- | --- |
| SDK attempt timeout | Single provider API call | S3 GET or Blob GET |
| SDK API call timeout | Total API call including retries | S3 PUT with retries |
| Database query/transaction timeout | Queries or transactions holding connections/locks | Claiming document, committing state |
| HTTP client timeout | Request to downstream service | Calling OCR API |
| Processing deadline | Total worker time for one event | Download + scan + persist |
| Queue visibility/lock/ack deadline | Duration message stays hidden/locked before redelivery | SQS visibility, Service Bus lock, Pub/Sub ack deadline |
| Database lease | Duration worker owns a job | Lease for document in PROCESSING |

Align these deadlines explicitly. The processing deadline must be smaller than the maximum allowed worker runtime. Queue visibility/lock must exceed expected processing time plus a safety margin, or be renewed while the worker remains active. Database leases must be renewed or guarded by fencing tokens for long jobs.

If a queue message is redelivered while the original worker is still running, two workers may process concurrently. Timeouts/leases do not replace idempotency.

### 6.2. Fault injection with a fake adapter

Simulate object storage responding slower than the deadline:

~~~java
import java.io.InputStream;
import java.time.Duration;

public class StorageTimeoutException extends RuntimeException {

    public StorageTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class DelayedObjectStore implements ObjectStore {

    private final ObjectStore delegate;
    private final Duration delay;
    private final Duration allowedDelay;

    public DelayedObjectStore(
            ObjectStore delegate,
            Duration delay,
            Duration allowedDelay) {
        this.delegate = delegate;
        this.delay = delay;
        this.allowedDelay = allowedDelay;
    }

    @Override
    public InputStream get(ObjectKey key, String version) {
        try {
            Thread.sleep(Math.min(delay.toMillis(), allowedDelay.toMillis()));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new StorageTimeoutException(
                    "Object read interrupted", ex);
        }
        if (delay.compareTo(allowedDelay) > 0) {
            throw new StorageTimeoutException(
                    "Simulated object read timeout", null);
        }
        return delegate.get(key, version);
    }

    // Other methods delegate to the underlying store.
}
~~~

In real tests, use fake clocks, controllable futures, or mock servers to avoid slowing down the test suite. The snippet above illustrates boundary errors; production adapters still need real SDK/HTTP client timeouts.

### 6.3. Configuring timeouts for the AWS SDK

AWS SDK for Java v2 supports configuring attempt timeouts and API call timeouts:

~~~java
import java.time.Duration;

import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3Client = S3Client.builder()
        .region(Region.of(region))
        .overrideConfiguration(
                ClientOverrideConfiguration.builder()
                        .apiCallAttemptTimeout(Duration.ofSeconds(2))
                        .apiCallTimeout(Duration.ofSeconds(6))
                        .build())
        .build();
~~~

Attempt timeout caps a single attempt; API call timeout caps the whole call including retries. Choose values based on latency SLOs and file sizes. For large/multipart uploads, use transfer managers or appropriate APIs and budget per-part and total transfer timeouts.

Never set API call timeout smaller than attempt timeout. Avoid stacking retries across the SDK, Resilience4j, Spring Retry, and queue redelivery without calculating the combined budget.

### 6.4. Queue timeouts

Each queue uses a different mechanism to hold messages:

- **SQS:** messages become invisible during the visibility timeout. If a worker takes longer, extend via `ChangeMessageVisibility`. If the timeout expires before completion/ack, the message can be redelivered.
- **Azure Service Bus:** receivers hold a message lock. For long processing, use auto lock renewal or manual lock renewal; lock expiry allows redelivery.
- **Google Pub/Sub:** subscribers have an ack deadline; clients can auto-extend the deadline during processing. Failing to ack or extend in time triggers redelivery.

Do not assume a visibility/lock/ack deadline number has identical semantics across providers. Adapters must map deadlines, renewal, and settlement explicitly.

### 6.5. Simulating timeouts in staging

Use one of these techniques:
- Toxiproxy/network fault proxies to inject latency or drop connections to test endpoints.
- Slow mock HTTP server responses for downstream services.
- Fault profile causing the object adapter to delay before returning.
- Temporarily lowering client timeouts so valid requests exceed the threshold.
- Temporarily reducing worker concurrency to build queue backlog and observe age/visibility behavior.

Apply only to lab resources. Never deliberately introduce packet loss or latency on production endpoints.

### 6.6. Distinguishing timeouts from unknown outcomes

A timeout does not prove the provider failed to execute the operation. For example, an object PUT may have succeeded while its response was lost; a queue publish may have been accepted by the broker before the caller timed out.

Before retrying:
- For object PUT: HEAD object key/version, compare checksum and size; use deterministic keys or conditional writes.
- For queue publish: retry with the exact same event ID; consumers must deduplicate.
- For database commit timeouts: re-read state by document/event ID before re-running commands.
- For downstream APIs: pass an idempotency key if supported.

This is an `UNKNOWN_OUTCOME` state. Never treat it as a guaranteed failure and blindly issue a brand-new operation.

### 6.7. Retry policy and deadline budgets

Classify timeouts as transient/unknown outcomes. Retry within bounds using exponential backoff and jitter, e.g., 1s, 2s, 4s, 8s up to a max delay; cap total elapsed time and attempts.

A policy should define:
- Attempt timeout.
- Total API timeout.
- Max SDK/client attempts.
- Queue delivery count or redelivery limit.
- Overall processing deadline.
- DLQ and redrive policy.
- Circuit breaker/open duration during dependency outages.

If the SDK retries 3 times, the application retries 3 times, and the queue redelivers 5 times, one event can generate a huge number of API calls. Calculate the aggregate retry budget rather than tuning each layer in isolation.

### 6.8. Recovering from timeouts

1. Inspect dependency latency, throttling, connection pools, and provider request IDs.
2. Determine whether the outcome definitely failed or is unknown.
3. Re-read object/database/outbox state before creating new side effects.
4. For transient errors, let the queue retry or schedule bounded retries.
5. If the worker can continue, extend visibility/lock/ack deadlines and DB leases.
6. If attempts are exhausted, move to DLQ and alert.
7. Once the dependency stabilizes, redrive in small batches while preserving event IDs.
8. Verify final document state and confirm no duplicate artifacts/results exist.

### 6.9. PASS criteria

- SDK timeouts do not leave workers holding connections/transactions indefinitely.
- Logs record dependency, operation, timeout budget, and elapsed time.
- Messages are never acked before business transactions commit.
- Messages are not continuously redelivered due to overly short visibility/lock settings.
- Unknown outcomes are verified via state/checksum checks before retrying.
- After recovery, the same event completes business-wise exactly once.

## 7. Lab 3 — Simulating Duplicate Message Delivery

### 7.1. Why are messages delivered multiple times?

Queue/event systems generally favor at-least-once delivery. Duplicates occur when:
- A worker commits to the database but crashes before ack/delete/complete.
- An ack response is lost or the client times out.
- Visibility timeout/lock/ack deadline expires while the worker is still running.
- An outbox relay publishes successfully but crashes before marking the outbox row.
- An operator redrives messages from the DLQ.
- A provider/event source re-emits a notification.

Duplicates are normal in distributed systems. Never assume each event is delivered only once.

### 7.2. Sending the same event twice

Use the same event ID and document ID to simulate:

~~~json
{
  "eventId": "evt-doc-1001-v1",
  "eventType": "document.stored",
  "schemaVersion": 1,
  "documentId": "doc-1001",
  "object": {
    "key": "source/doc-1001/upload-1.pdf",
    "version": "object-version-1"
  }
}
~~~

Publish this payload twice, or let the worker finish processing and intentionally skip the first ack. The two messages may have different broker message IDs while sharing the same business event ID.

### 7.3. Unique barrier in the database

Use a unique key per consumer and event:

~~~sql
INSERT INTO processed_event (
    consumer_name,
    event_id,
    document_id,
    processed_at
)
VALUES (
    :consumer_name,
    :event_id,
    :document_id,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

This syntax is for PostgreSQL. For other databases, use an equivalent unique constraint and atomic insert/merge statement. The repository must return whether a new row was inserted or the event already existed.

Never implement a `SELECT first then INSERT` pattern without a unique constraint: two concurrent workers can both observe the event missing and both execute the side effect.

### 7.4. Committing inbox and business state together

Application service pseudocode:

~~~java
@Transactional
public ProcessingResult complete(
        DocumentStoredEvent event,
        ProcessedArtifact artifact) {

    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "document-worker",
            event.eventId(),
            event.documentId());

    if (!firstDelivery) {
        duplicateCounter.increment();
        return ProcessingResult.alreadyProcessed();
    }

    Document document = documentRepository
            .findByIdForUpdate(event.documentId())
            .orElseThrow();

    document.markProcessed(
            artifact.objectKey(),
            artifact.checksum());

    documentRepository.save(document);
    outboxRepository.save(
            OutboxEvent.documentProcessed(
                    event.documentId(),
                    artifact.objectKey()));

    return ProcessingResult.completed();
}
~~~

`insertIfAbsent` must be an atomic operation backed by a unique constraint. The inbox row, document state, and outbox event commit in the same DB transaction. If the transaction rolls back, all three changes roll back and the message can be reprocessed.

This code assumes the artifact was already uploaded and verified before calling `complete`. Use deterministic output keys derived from document ID, source version, and processor version; never trigger non-idempotent external side effects without a deduplication strategy.

### 7.5. Do not mark inbox completed too early

If you record inbox completion before downloading the object or running processing, a worker crash can cause the message to retry while the consumer sees the event as already processed and permanently skips it.

For long processing, separate two concepts:
- **Job claim/lease:** the worker temporarily owns the work; has `PROCESSING` state and a lease expiry.
- **Inbox completed:** the event committed its business side effects.

Record completion only in the transaction that updates the document/result/outbox. Expired leases can be reclaimed; fencing/version checks prevent a stale worker from overwriting a newer worker's result.

### 7.6. Idempotency for object outputs and external APIs

A unique inbox only protects database transactions. It does not roll back:
- Succeeded object PUTs.
- Sent emails/webhooks.
- Payment/third-party API calls already accepted.
- Side effects executed by downstream services.

Use deterministic object keys and conditional writes/versioning for outputs. For external APIs, pass an idempotency key equal to the event ID or operation ID when supported. If the target system lacks idempotency, use an outbox plus reconciliation/compensation and design for `UNKNOWN_OUTCOME` states.

### 7.7. Queue-specific behavior

| Provider | Duplicate source | Additional guard |
| --- | --- | --- |
| SQS Standard | At-least-once delivery, visibility expiry | Inbox unique key; FIFO deduplication only applies within configured scope/window |
| Azure Service Bus | Lock expiry, abandon, retry, redelivery | Duplicate detection when configured; inbox still needed for business idempotency |
| Google Pub/Sub | Redelivery on ack deadline expiry or unrecorded ack | Exactly-once delivery has specific limits/conditions; keep inbox for DB/external side effects |

Broker duplicate detection or exactly-once features do not turn database + object storage + external APIs into an exactly-once distributed transaction.

### 7.8. PASS criteria

- Receiving the same event ID twice does not complete document processing twice.
- Unique constraints block races when two workers insert concurrently.
- Duplicates are acked safely after verifying the event already committed.
- Event IDs remain unchanged across retries and DLQ redrives.
- Object outputs/external side effects have dedicated idempotency strategies.
- Duplicate metrics increment without being counted as processing failures.

## 8. Lab 4 — Comprehensive Recovery and Safe Replay

### 8.1. Fault injection sequence

Run the same document through three failures in sequence:

1. **AccessDenied:** worker receives the event but cannot read the source object.
2. **Timeout:** after fixing permissions, object GET or downstream processor exceeds timeout.
3. **Duplicate:** after successful processing, resend the same event ID or trigger redelivery by dropping the ack response.

Keep the same document ID, event ID, object version, and correlation ID throughout. Change only the fault profile/policy so you know what each step tests.

### 8.2. Recovery decision table

| Symptom | Classification | First action | Recovery method |
| --- | --- | --- | --- |
| Storage returns AccessDenied | Authorization/permanent until policy changes | Identify principal, action, resource | Fix least-privilege role/policy, then retry/redrive |
| Queue publish AccessDenied | Authorization | Check relay identity and destination | Grant Send/Publish on target topic/queue; relay resumes from outbox |
| Storage GET timeout | Transient or unknown outcome | Check timeout budget, provider request ID | Bounded retry; verify version/checksum |
| DB commit timeout | Unknown outcome | Query document/inbox/outbox by ID | Resume from committed state; do not issue a new command |
| Queue publish timeout | Unknown outcome | Inspect outbox and event ID | Republish same event ID; consumer deduplicates |
| Message redelivered | Duplicate delivery | Check inbox and document state | Ack if committed; process if incomplete |
| Message enters DLQ | Retry exhausted/poison | Read failure category and delivery count | Fix root cause, controlled redrive |
| Lease expired | Worker crash/overlong processing | Check old worker and fencing token | Reclaim job, block stale worker writes |

### 8.3. Standard recovery sequence

**Step 1 — Stop retry storms.** If permission errors or dependency outages are creating massive backlogs, reduce consumer concurrency or pause consumers where supported. Never purge queues just to make metrics look clean.

**Step 2 — Identify the failure boundary.** Use event ID/correlation ID to find the last successful step: object PUT, DB finalize, outbox publish, message receive, object GET, result PUT, DB commit, or ack.

**Step 3 — Verify outcome.** For timeouts, re-read object/database/outbox state before resending commands. For duplicates, check the inbox unique key and document state.

**Step 4 — Fix the root cause.** Grant proper IAM/RBAC, fix DNS/network/secrets, tune timeouts/visibility/locks, or fix schema/payload issues.

**Step 5 — Recover with limits.** Retry queued messages or redrive the DLQ in small batches while preserving event IDs. Monitor backlog drain rate, DB pools, and provider throttling.

**Step 6 — Verify results.** Confirm the document is in the right state, output object version/checksum is valid, inbox/outbox are consistent, and no duplicate side effects occurred.

**Step 7 — Close the incident.** Record audit logs, root cause, policy/config changes, replayed message counts, and any documents needing manual handling.

### 8.4. Never delete messages or outbox rows to "clean up"

Deleting failing messages can lose work already confirmed to clients. Deleting unpublished outbox rows loses events. If a payload is poison, move it to a DLQ/quarantine and preserve metadata for investigation. If an event is no longer valid, perform an audited business state transition rather than deleting records.

### 8.5. Replaying a message

Redrives must:
- Preserve the original event ID and document ID.
- Verify the source object version still exists and its checksum matches.
- Verify consumer code/schema compatibility.
- Check the inbox to see whether the event already completed.
- Start with small batch limits and low replay rates.
- Record actor, timestamp, DLQ source, and redrive batch ID.
- Monitor duplicate counters and downstream side effects.

If an event already committed before an ack failure, replay must follow the duplicate branch and end with an ack rather than re-running business operations.

## 9. Provider-Specific Recovery

### 9.1. AWS: S3, SQS, and RDS

**Permissions:**
- Worker role needs `s3:GetObject` on the source prefix; queue receive/delete permissions are separate SQS actions.
- If S3 objects use SSE-KMS with a customer-managed key, the worker needs decrypt permissions per both key policy and IAM policy.
- Relay role needs `sqs:SendMessage`; avoid sharing the worker role with the relay unnecessarily.
- Worker database credentials/roles only have read/write grants on required workflow tables.

**Timeouts and duplicates:**
- Configure AWS SDK v2 `apiCallAttemptTimeout` and `apiCallTimeout`.
- SQS visibility timeout must cover processing deadline plus buffer; extend via `ChangeMessageVisibility` if needed.
- SQS Standard has at-least-once delivery; FIFO deduplication has specific scope/window limits and does not replace the DB inbox.
- Redrive SQS DLQ after fixing policies/workers; preserve the event ID in the message body.

### 9.2. Azure: Blob Storage, Service Bus, and Azure Database

**Permissions:**
- Use the proper Managed Identity/Workload Identity of Function App, Container Apps, AKS, or VM.
- Worker needs a blob data-plane read role, e.g., Storage Blob Data Reader at the right scope.
- Service Bus receiver needs Data Receiver; relay needs Data Sender.
- Azure Database requires network access and separate database principals/roles; Azure resource RBAC does not automatically grant SQL permissions.

**Timeouts and duplicates:**
- Blob SDK has its own retry/network timeouts; Service Bus processors must handle lock renewal.
- Message lock expiry can cause redelivery. Never process longer than the lock without renewing.
- Service Bus duplicate detection must be configured and has a time window; still use inbox unique keys for business side effects.
- Permanently failing messages can be dead-lettered; after fixing the root cause, use an audited resubmit/redrive process.

### 9.3. Google Cloud: Cloud Storage, Pub/Sub, and Cloud SQL

**Permissions:**
- Use separate service accounts/workload identities for uploader, relay, and worker.
- Worker needs `storage.objects.get` on the source bucket; uploader needs object creation permissions.
- Relay needs Pub/Sub Publisher; consumer needs Pub/Sub Subscriber on the target topic/subscription.
- Cloud SQL requires IAM/connector connectivity permissions and separate database user grants.

**Timeouts and duplicates:**
- Configure Google Cloud client timeouts/retries per operation and worker deadline.
- Pub/Sub subscribers must ack or extend ack deadlines while processing; if deadlines expire, messages can redeliver.
- Configure dead-letter topics and max delivery attempts on the subscription appropriately.
- Exactly-once delivery applies only under specific scopes/conditions; a DB inbox is still required for transactions and external side effects.

### 9.4. Action comparison table

| Failure | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object read denied | IAM `s3:GetObject`, bucket/KMS policy | Blob data-plane role | IAM `storage.objects.get` |
| Queue publish denied | `sqs:SendMessage` | Service Bus Data Sender | Pub/Sub Publisher |
| Queue receive denied | Receive/Delete/Visibility actions | Service Bus Data Receiver | Pub/Sub Subscriber |
| Queue timeout | Visibility timeout/change visibility | Message lock/renewal | Ack deadline/extension |
| Duplicate | SQS redelivery/FIFO window + inbox | Lock expiry/dedup window + inbox | Redelivery/exactly-once scope + inbox |
| Dead letter | SQS DLQ/redrive | Service Bus DLQ/resubmit | Dead-letter topic/max delivery attempts |
| Database access | DB security group + DB user | Firewall/private endpoint + DB role | Cloud SQL connector/IAM + DB user |

## 10. Automated Testing

### 10.1. Unit tests for permission errors

Verify authorization errors are never converted into successes:

~~~java
@Test
void keepsDocumentUnprocessedWhenObjectReadIsDenied() {
    when(objectStore.get(any(), any()))
            .thenThrow(new StorageAccessDeniedException("denied"));

    assertThatThrownBy(() -> processor.process(event))
            .isInstanceOf(StorageAccessDeniedException.class);

    verify(documentRepository, never()).markProcessed(any());
    verify(messageAcker, never()).acknowledge(any());
}
~~~

Method/repository names here are pseudocode matching application ports. What matters is that exceptions are classified properly, the document is not completed, and the message is not acked as successful.

### 10.2. Unit tests for timeouts

~~~java
@Test
void retriesTransientStorageTimeoutWithinBudget() {
    when(objectStore.get(any(), any()))
            .thenThrow(new StorageTimeoutException("timeout", null))
            .thenReturn(validObjectStream());

    processor.processWithRetry(event);

    verify(objectStore, times(2)).get(any(), any());
    verify(documentRepository).markProcessed(any());
}
~~~

Tests should not use real sleeps. Use fake clocks/schedulers or retry policies with pluggable backoff strategies in tests. Verify attempts never exceed max attempts.

### 10.3. Integration tests for duplicates

~~~java
@Test
void processesSameEventOnlyOnce() {
    processor.process(event);
    processor.process(event);

    assertThat(documentRepository.findStatus(event.documentId()))
            .isEqualTo(DocumentStatus.PROCESSED);

    assertThat(processedEventRepository.count(
            "document-worker", event.eventId()))
            .isEqualTo(1);

    assertThat(processorMetrics.duplicateCount()).isEqualTo(1);
}
~~~

This test needs a real database or compatible test database to verify unique constraints and transactions. For concurrent invocations, add a concurrency test running two transactions with the same event ID and verify only one commits the completed event.

### 10.4. Failure injection test matrix

| Test | Fault injection | Assertion |
| --- | --- | --- |
| Permission denied | ObjectStore throws AccessDenied | State not PROCESSED; no ack |
| Timeout before response | Adapter delay exceeds client timeout | Bounded retry; outcome verified |
| Publish timeout | Queue adapter times out after broker may have accepted | Outbox retries same event ID |
| Duplicate sequential | Send same event twice | Only one processed_event |
| Duplicate concurrent | Two workers process same event | Unique constraint allows one commit |
| Crash before ack | Commit DB then simulate process crash | Redelivery takes duplicate path |
| DLQ redrive | Replay event after policy fix | Event completes, no repeated side effect |
| Lease expiry | Worker A slow, Worker B reclaims | Fencing token blocks stale write from Worker A |

### 10.5. Local integration and staging

You can use Testcontainers for databases, LocalStack for parts of S3/SQS flows, Azurite for Blob Storage, and the Pub/Sub emulator for message flows. Emulators do not prove real IAM/RBAC, private networking, KMS, full lock/ack semantics, or provider quotas.

Staging tests must use isolated workload identities and resources. At least once per provider, verify real AccessDenied, timeout/lock renewal, and duplicate redelivery using real services or provider-supported test harnesses.

## 11. Observability and Alerting

### 11.1. Workflow dashboard

Build a dashboard tracking:
- Upload success/failure and object PUT/GET latency.
- AccessDenied counts by provider/resource/operation.
- Timeouts by dependency and attempt.
- Outbox backlog and oldest event age.
- Queue depth, oldest message age, receive count, and DLQ depth.
- Processing success/error/duration.
- Duplicate event count and inbox conflicts.
- Expired leases, reclaims, and reconciliation repairs.
- Database connection pool usage, lock waits, and query latency.

Never use document IDs, event IDs, or object keys as metric labels. Use traces/logs with correlation IDs to drill down.

### 11.2. Actionable alerts

| Alert | Suggested threshold | Action |
| --- | --- | --- |
| AccessDenied spike | Any abnormal spike | Identify principal/action/resource; inspect policy rollout |
| Timeout increase | p95/p99 exceeds SLO | Check dependency latency, retries, and timeout budget |
| Oldest queue age rising | Exceeds processing SLO | Check worker capacity/downstream bottlenecks |
| DLQ non-empty | > 0 or age exceeds threshold | Investigate failure category; do not auto-redrive |
| Outbox backlog rising | Event age exceeds SLA | Check relay/queue permissions/network |
| Duplicate rate rising | Exceeds baseline | Check ack/lock/visibility and relay uncertainty |
| Lease expirations rising | Spike | Check worker crashes, timeouts, and fencing |

Exact thresholds depend on SLOs and traffic volume; do not apply one global threshold across all environments.

## 12. Symptom-Based Troubleshooting

### 12.1. AccessDenied even though the policy looks right

- Verify the actual runtime identity; avoid confusing local developer credentials with workload identity.
- Verify resource ARNs/IDs, account/project, region, and object prefixes.
- Check for denies from bucket policies, KMS key policies, Azure scope/RBAC conditions, or Google IAM conditions.
- Check token expiry/audience and private endpoint policies.
- Check pod or function service account/role bindings.
- Test a minimal operation on a test resource with the exact principal.

### 12.2. Timeouts even when the provider is healthy

- Check DNS, proxies, NAT, routing, TLS handshakes, and connection pools.
- Check whether SDK retries are exhausting the API call timeout.
- Check payload/file sizes and multipart/chunk configuration.
- Check database pool pending waits and lock waits.
- Check whether workers hold transactions open during network calls.
- Check whether queue lock/visibility/ack deadlines and leases expire before processing finishes.

### 12.3. Repeated messages despite consumer acks

Ack responses may be lost or the broker failed to record settlement. Check the event ID/inbox first; if already committed, the duplicate path must ack without re-executing business side effects. Check auto-ack/auto-complete modes and ensure listeners do not return before processing completes.

### 12.4. Document stuck in PROCESSING forever

Check lease expiry, worker heartbeats, attempt counts, and process terminations. Reconciliation can reclaim expired leases after verifying the prior worker is dead or the fencing token has changed. Never flip state back to STORED without knowing whether artifacts were already produced.

### 12.5. DLQ grows after fixing permissions

Messages in the DLQ may have exhausted retries before the policy was fixed. Fixing a policy does not automatically move messages back to the main queue. Test the role with a single operation, then redrive in small batches while preserving event IDs and observing outcomes.

## 13. Guided Comprehensive Lab Exercise

### 13.1. Preparation

- Create dedicated lab buckets/containers, queues, DLQs, and databases.
- Create roles/service accounts for the upload API, relay, and worker.
- Seed a document with an object version/checksum.
- Enable logs/metrics and capture a baseline.
- Set max retries to 3–5 in the lab environment to observe DLQ behavior quickly.

### 13.2. Injecting the three faults

**Run A — Permissions:** remove object read permission from the worker or enable the fake `object-read-denied` fault. Send an event, verify AccessDenied, and confirm state does not complete. Restore scoped permission and retry the same event.

**Run B — Timeout:** set object read timeout below test delay or inject latency via a proxy. Verify timeouts are classified as transient, workers do not ack early, and queue deadlines extend appropriately. Restore timeout and replay.

**Run C — Duplicate:** publish the same event ID twice; also simulate a crash after DB commit before ack. Verify subsequent runs enter the inbox duplicate path and do not repeat business results.

### 13.3. Results log table

| Run | Fault | Post-fault state | Recovery action | Final state | Side effect count |
| --- | --- | --- | --- | --- | --- |
| A | AccessDenied | Not yet PROCESSED | Grant permission and retry | PROCESSED | 1 |
| B | Timeout | Retryable/lease expired | Tune timeout, replay | PROCESSED | 1 |
| C | Duplicate | Event already in inbox | Ack duplicate | PROCESSED | 1 |

Record provider request IDs, event IDs, correlation IDs, delivery counts, attempt counts, and recovery durations. If side effect count exceeds 1, inspect inbox transactions, leases/fencing, and object/external API idempotency.

### 13.4. Lab completion criteria

- Can reproduce AccessDenied without using admin credentials.
- Can reproduce timeouts without impacting production.
- Can trigger duplicates by publishing twice or crashing before ack.
- Logs identify exact components, principals, operations, and correlation IDs.
- Retries are bounded, DLQs function, and replays are audited.
- The same event ID produces only one business completion.
- Reconciliation detects incomplete outbox/object/lease records.
- After recovery, queue backlog drains and documents settle in valid states.

## 14. Pre-Production Checklist

1. **Identity:** API, relay, worker, and triggers each have distinct principals.
2. **Least privilege:** permissions bind to exact buckets/prefixes, queues/topics, and database operations.
3. **Error mapping:** AccessDenied, timeouts, throttling, not found, and conflicts are classified separately.
4. **Timeout budget:** SDK attempt/API timeouts, processing deadlines, DB leases, and queue visibility/lock/ack deadlines align.
5. **Retry:** bounded max attempts, backoff/jitter, and no unchecked retry multiplication across layers.
6. **Unknown outcome:** PUT/publish/DB timeouts re-read state before retrying.
7. **Idempotency:** event IDs, inbox unique keys, and deterministic output keys.
8. **Ack:** ack only after business transactions commit.
9. **DLQ:** alerts, retention, redrive policies, and audit trails exist.
10. **Recovery:** runbooks cover permission fixes, timeout handling, duplicate replay, and reconciliation.
11. **Observability:** correlation IDs, provider request IDs, delivery counts, and state transitions.
12. **Testing:** unit tests, database concurrency tests, emulators, and staging fault injection.
13. **Isolation:** fault profiles, IAM test roles, and lab resources are never used in production.
14. **Data protection:** never log tokens, SAS, pre-signed URLs, secrets, or file bytes.
15. **Ownership:** every alert/DLQ/reconciliation task has an owner and recovery objective.

## 15. Self-Practice Exercises

1. Create a worker role allowed to receive SQS messages but denied S3 reads; observe the denied principal and action.
2. Create an Azure Managed Identity with Service Bus receive access but no Blob read access; verify the data-plane error.
3. Create a Google service account with Pub/Sub Subscriber but without `storage.objects.get`; compare IAM errors and role assignment.
4. Use a fake adapter to simulate storage timeouts; demonstrate separation between SDK/API timeouts and worker deadlines.
5. Let message visibility/lock/ack deadlines expire while a worker is running; observe redelivery.
6. Send the same event ID twice and verify the inbox unique constraint.
7. Simulate a worker crashing after DB commit but before ack; verify the duplicate path.
8. Simulate a publish timeout after the broker received the event; verify the outbox retries with the same event ID.
9. Route a message to the DLQ, fix the policy, and perform an audited batch redrive.
10. Write a reconciliation job that finds PROCESSING documents with expired leases.
11. Create a concurrency test where two workers claim the same document and verify fencing tokens.
12. Build a dashboard distinguishing AccessDenied, timeouts, duplicates, backlog, and DLQ counts.

**Completion criteria:** learners can reproduce permission/timeout/duplicate failures in an isolated environment, pinpoint identities and failure boundaries, recover messages safely, prove idempotency with database constraints, and operate retries/DLQs/reconciliation on at least one cloud provider.

## References

- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html): S3/SQS integration and AWS SDK.
- [AWS SDK for Java 2.x — Timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html): API call and attempt timeouts.
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html): visibility and message redelivery.
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html): DLQs and redrive.
- [AWS IAM policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html): identity/resource policies and explicit deny.
- [Azure Service Bus message locks](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement): locks, renewal, and settlement.
- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues): DLQs and resubmission.
- [Azure Blob Storage authorization](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory): Microsoft Entra ID and data-plane RBAC.
- [Google Cloud Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview): acknowledgments and redelivery.
- [Google Cloud Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics): delivery attempts and dead-lettering.
- [Google Cloud Storage IAM](https://cloud.google.com/storage/docs/access-control/iam): object permissions and bucket scope.
- [Testcontainers documentation](https://testcontainers.com/guides/getting-started-with-testcontainers-for-java/): integration tests with real dependencies in containers.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html): saving business state and events in the same transaction.
- [Idempotent Consumer pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html): safely handling repeated message deliveries.
