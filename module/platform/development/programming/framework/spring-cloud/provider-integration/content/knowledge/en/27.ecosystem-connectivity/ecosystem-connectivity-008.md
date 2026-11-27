# Coordinating Object Storage, Queues, and Databases in One Flow

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications combine managed services from AWS, Azure, and Google Cloud to build complete workflows. A common flow receives a file, stores the file in object storage, persists metadata in a database, and emits a message for asynchronous worker processing.

Three services take on three distinct responsibilities:

- **Object storage** stores large payloads such as images, documents, audio recordings, or processing artifacts. Examples: Amazon S3, Azure Blob Storage, and Google Cloud Storage.
- **Queue/event service** passes notifications or jobs between components, absorbs bursts, and enables asynchronous processing. Examples: Amazon SQS, Azure Service Bus, and Google Cloud Pub/Sub.
- **Database** stores metadata, business state, relationships, idempotency records, and processing history. Examples: Amazon RDS/Aurora, Azure Database for PostgreSQL, and Google Cloud SQL.

Do not push entire files into queues or use a database as a default blob store when object storage fits better. Messages normally carry only object identifiers, versions, checksums, and correlation IDs; workers use that pointer to download the object when needed.

This lesson focuses on coordinating all three services into a consistent workflow. You will design upload flows, transactional outboxes, queue consumers, idempotency, retries/DLQs, cross-system failure handling, provider service mappings, and safe operations.

After this lesson, you will be able to:

1. Divide responsibilities across object storage, queues, and databases.
2. Design data models and lifecycle state machines for objects.
3. Organize direct uploads or pre-signed URL uploads.
4. Emit messages after metadata commits via a transactional outbox.
5. Write consumers that read objects, process them, and update databases safely.
6. Handle duplicates, retries, ordering, poison messages, and partial failures.
7. Compare S3/SQS/RDS, Blob/Service Bus/Azure Database, and GCS/Pub/Sub/Cloud SQL.
8. Apply workload identity, least privilege, encryption, and secret management.
9. Test integrations and observe end-to-end workflows.
10. Build runbooks, rollback procedures, and reconciliation jobs.

> **Scope:** Examples use file uploads and document processing for illustration. The same architecture applies to images, media, exports, ingestion, and event-driven data processing. Property names, starters, and APIs vary by release train; manage dependencies via a Spring Boot-compatible BOM and check provider documentation before implementation.

## 2. Overall Architecture

### 2.1. Upload and Asynchronous Processing Workflow

Suppose an application receives documents from users. The API creates an upload intent in the database, issues a time-limited upload URL or accepts a file stream, then verifies the object was stored. When metadata transitions to `STORED`, the application writes an outbox event in the same transaction. A relay publishes the event to a queue. A worker receives the event, downloads the object, processes it, saves results, and updates database state.

~~~mermaid
flowchart LR
    U["Client"] --> API["Spring Boot API"]
    API --> DB[("Metadata DB")]
    API --> OS[("Object Storage")]
    DB --> OB["Transactional Outbox"]
    OB --> RELAY["Outbox Relay"]
    RELAY --> Q[["Queue / Event Bus"]]
    Q --> W["Worker / Spring Boot Consumer"]
    W --> OS
    W --> DB
    W --> PROC["Processing / Validation"]
    PROC --> OS
~~~

Steps:

1. Client requests an upload intent.
2. API records `PENDING_UPLOAD` metadata and generates a unique object key.
3. API returns a pre-signed URL or accepts the file via the backend.
4. Object storage persists bytes and returns version/ETag/checksum depending on provider.
5. API verifies object existence, size, and checksum against policy.
6. Transaction updates metadata to `STORED` and inserts an outbox event.
7. Relay publishes a message containing the object pointer to the queue.
8. Worker receives the message, verifies version/checksum, and downloads the object.
9. Worker processes, stores result artifacts, and updates status to `PROCESSED`.
10. Worker acks the message after committing results or lets the broker retry on failure.

### 2.2. Why Are All Three Services Needed?

| Component | Primary Data | Responsibility | Should Not Be Used For |
| --- | --- | --- | --- |
| Object storage | Bytes, object metadata, versions | Storing large files durably with lifecycles | Storing complex business relationships |
| Queue/event | Small events, pointers, retry metadata | Buffering, decoupling, delivery | Storing large files or acting as business source of truth |
| Database | Metadata, state, relationships, outbox/inbox | Transactions, queries, concurrency control | Storing large blobs by default |

The database governs business state; object storage holds content; the queue dispatches work. Messages can be redelivered or arrive late, so consumers must inspect state/version in the database and execute idempotently.

### 2.3. Synchronous and Asynchronous Flows

Uploading and verifying the object are usually synchronous with the client. Virus scanning, OCR, thumbnailing, indexing, or data analytics are usually asynchronous.

The API can return `202 Accepted` once the upload is verified and work is durably recorded. The client receives a `documentId` or `operationId` and polls status later. Never return final completion merely because a queue API accepted a message when business processing has not finished.

### 2.4. Source-of-Truth Boundaries

- Object key/version identifies the exact bytes.
- The database stores owner, status, object reference, checksum, size, processing result, and timestamps.
- A queue message is a work notification, not final business state.
- The outbox is the durable record of events to publish.
- Inbox/idempotency records let consumers recognize already-processed events.

Never allow a queue message to overwrite database state without checking version/state transitions. Never assume an object is still valid solely because a metadata row exists.

## 3. Data Model and State Machine

### 3.1. Metadata Record

A metadata table may include:

| Field | Meaning |
| --- | --- |
| `document_id` | Application-generated business ID |
| `tenant_id` | Tenant/owner per authorization model |
| `object_key` | Object path within bucket/container |
| `object_version` | Specific version/generation if provider versioning is enabled |
| `content_type` | Verified MIME type |
| `content_length` | Size in bytes |
| `checksum` | Checksum verified by application/provider |
| `status` | Workflow status |
| `idempotency_key` | Key preventing duplicate upload intent creation |
| `created_at`, `updated_at` | Lifecycle timestamps |
| `failure_code` | Standardized error code containing no secrets |
| `processed_object_key` | Pointer to result artifact if present |

Object keys should include random IDs or unpredictable identifiers, never using raw user filenames as the sole key. If the original filename must be retained, store it in the database or controlled metadata.

### 3.2. State Machine

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_UPLOAD
    PENDING_UPLOAD --> STORED: object verified
    PENDING_UPLOAD --> UPLOAD_FAILED: upload expired or invalid
    STORED --> QUEUED: outbox published
    QUEUED --> PROCESSING: worker claims
    PROCESSING --> PROCESSED: result committed
    PROCESSING --> RETRY_WAIT: transient failure
    RETRY_WAIT --> PROCESSING: retry
    PROCESSING --> FAILED: permanent failure / attempts exhausted
    STORED --> DELETED: cancellation / retention
    PROCESSED --> DELETED: retention policy
~~~

The `QUEUED` state is a helpful observability marker; the outbox record remains the durable source for the relay to determine whether an event was published. If publishing succeeds but the relay dies before marking the outbox, the event may be republished. Consumers must tolerate duplicates.

### 3.3. Object Keys and Versions

Object keys should be immutable per upload intent, for example:

~~~text
tenant/{tenantId}/documents/{documentId}/source/{uploadId}
tenant/{tenantId}/documents/{documentId}/derived/{processorVersion}/preview.webp
~~~

Use a fresh key per upload/revision so workers never read mismatched bytes if a key is overwritten. When the provider supports versioning, store the version ID/generation in both the database and messages. ETag is not always an MD5 checksum, especially with multipart uploads or encryption; use checksum APIs/metadata with clear provider semantics.

### 3.4. Idempotency Keys When Creating Uploads

Clients can pass an idempotency key when creating an upload. The database enforces a unique constraint scoped to tenant and operation. If a client retries due to a lost response, the API returns the existing upload intent instead of creating extra object keys and workflows.

Never use filenames as idempotency keys. Two uploads sharing a filename may carry different contents; the same idempotency key must bind to identical payload/request semantics per contract.

## 4. Designing Safe Uploads

### 4.1. Uploading Through Spring Boot

The backend receives a multipart stream and uploads to object storage. This allows checking authorization and file limits before writing, though it increases network traffic, memory/disk pressure, and application throughput requirements.

Never read large files entirely into a byte array. Use the provider's streaming/multipart API, set max sizes, timeouts, and concurrent upload limits. When an upload fails mid-flight, abort the multipart upload and clean up parts per lifecycle policy.

### 4.2. Direct Uploads via Pre-Signed URLs

For large files, the backend can issue a time-limited pre-signed URL or upload token. Clients upload directly to object storage, offloading Spring Boot.

Flow:
1. Backend authenticates user/tenant and creates an upload intent.
2. Backend generates a unique object key, restricting method, key, expiry, and signed headers.
3. Client uploads bytes directly.
4. Client calls the finalize endpoint.
5. Backend calls HEAD/metadata APIs to verify object existence, size, content type, and version/checksum.
6. Backend transitions state and records an outbox event in a transaction.

A pre-signed URL is a bearer capability: anyone holding the URL can perform the signed operation within its scope and expiration. Never log URLs, never place them in analytics/referrers, never grant broad bucket permissions, and never issue non-expiring URLs. Constrain content length/content type if supported by the provider mechanism; the backend must still verify the object after upload.

### 4.3. Upload Intent and Finalization

Do not emit a processing event immediately when creating an upload intent. Workers should only receive events once the object exists and metadata is verified. If a client never finalizes, the intent expires and a cleanup job deletes incomplete objects per policy.

Finalization must be idempotent: multiple requests for the same document/upload ID must not produce multiple logical events. Use conditional state transitions—for example, transitioning `PENDING_UPLOAD` to `STORED` strictly once and inserting the outbox event in the same transaction.

### 4.4. File Validation and Malicious Content Protection

Never trust client-sent extensions or Content-Types. Verify magic bytes/file signatures, sizes, checksums, and file-type policies. Untrusted files should be quarantined before downstream processing. Antivirus/malware scanning and content disarm/reconstruction can serve as the first step in the workflow.

Never render HTML/SVG or open macro-enabled documents directly in high-privilege environments. Workers run with minimal permissions and appropriate sandboxing. Cap archive expansion/decompression ratios to defend against zip bombs.

### 4.5. Lifecycle and Cleanup

Configure lifecycle policies for incomplete multipart uploads, quarantined objects, temporary artifacts, and retention-expired files. Cleanup jobs must cross-check database state and object versions; never delete solely by prefix if active objects might reside there.

Use soft deletes/tombstones or retention/legal holds when required by business/compliance rules. Object versioning aids recovery while increasing storage costs; clearly define retention and delete-marker behavior.

## 5. Transaction Boundaries and the Transactional Outbox

### 5.1. Why Is There No Shared Transaction?

Object storage, queues, and relational databases do not typically participate in a single distributed ACID transaction. Partial states can arise:

- Object upload succeeds but database commit fails.
- Database commit succeeds but message publish fails.
- Queue receives message but relay fails to record publish success.
- Worker processes object successfully but database update fails.
- Database update succeeds but consumer dies before acking the message.

Do not attempt to solve this by wrapping every call in `@Transactional`. Spring's database transaction manager cannot roll back S3/Blob/GCS or queue calls unless an explicit distributed transaction protocol is supported; cloud services do not generally join a shared XA transaction.

### 5.2. Transactional Outbox

Within a single database transaction, persist business state and the outbox event:

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentFinalizationService {

    private final DocumentRepository documents;
    private final OutboxRepository outbox;

    public DocumentFinalizationService(
            DocumentRepository documents,
            OutboxRepository outbox) {
        this.documents = documents;
        this.outbox = outbox;
    }

    @Transactional
    public void markStoredAndQueue(
            UUID documentId,
            String objectVersion,
            String checksum) {

        Document document = documents.findByIdForUpdate(documentId)
                .orElseThrow();

        if (document.isAlreadyStored()) {
            return;
        }

        document.markStored(objectVersion, checksum);
        documents.save(document);

        outbox.save(OutboxEvent.documentStored(
                document.id(),
                objectVersion,
                checksum));
    }
}
~~~

The business row and outbox row commit together. If the transaction rolls back, neither appears. The relay publishes only committed outbox rows.

The entity/repository snippet above is an illustrative skeleton; locking methods, unique constraints, and mappings depend on your application's persistence layer.

### 5.3. Why Not Use TransactionalEventListener Alone?

`@TransactionalEventListener(phase = AFTER_COMMIT)` is useful for running actions after commit in the same process. However, if the process dies after the database commits but before the listener publishes the message, the in-memory event is lost. An outbox persists events durably in the database so the relay can resume after restarts.

You can use a listener to wake the relay early, while keeping the outbox row as the durable source of truth. Never rely on in-memory listeners as the sole event storage mechanism.

### 5.4. Outbox Relay

The relay can poll in batches or use CDC. With polling:
1. Select unpublished outbox rows whose retry time has arrived.
2. Claim rows with a lease/lock so multiple relays do not process simultaneously.
3. Publish messages to the queue/event bus.
4. Only after broker confirmation, mark rows as published.
5. If publish times out with an unknown outcome, retrying may produce duplicates.

Never mark rows published before sending, as crashes can lose events. Publishing first and marking afterward produces at-least-once delivery; consumers require idempotency.

### 5.5. Outbox Schema and Operations

Outbox rows typically include event ID, aggregate/document ID, event type, schema version, payload, creation timestamp, attempts, next attempt time, published timestamp, and lease owner/expiry. Payloads should be small and contain no secrets or raw bytes.

Bound outbox table retention. Delete/archive published rows after a window sufficient for auditing/replay. Monitor backlog age, publish failures, retry counts, and expired leases.

### 5.6. CDC vs. Polling

| Relay Approach | Advantages | Cost / Trade-offs |
| --- | --- | --- |
| Polling | Simple, minimal infrastructure, easy to understand | Periodic queries, requires locking/leases and batching |
| CDC | Low latency, leverages transaction logs | Requires connectors/streaming platform, higher ops complexity |
| DB trigger publishing directly to queue | Near real-time possible | Tight coupling, hard retry/secret management; not a pure outbox |

For small/medium systems, batched outbox polling is usually easier to operate. For high throughput, CDC can fit well while requiring management of schema evolution, offsets, replay, and connector availability.

## 6. Queue Contracts and Event Design

### 6.1. Messages Carry Pointers, Not File Bytes

A `DocumentStored` message might look like:

~~~json
{
  "eventId": "evt-01J9Q5K3",
  "eventType": "document.stored",
  "schemaVersion": 1,
  "documentId": "doc-1001",
  "tenantId": "tenant-42",
  "object": {
    "provider": "aws",
    "bucket": "rental-documents",
    "key": "tenant/tenant-42/documents/doc-1001/source/up-01",
    "version": "3Lg...abc",
    "contentLength": 524288,
    "checksumSha256": "base64-or-hex-digest"
  },
  "occurredAt": "2026-11-24T10:15:30Z",
  "correlationId": "req-8a3d"
}
~~~

This payload is an internal contract example, not a mandatory SQS, Service Bus, or Pub/Sub schema. In multi-cloud systems, you can standardize the application event envelope and map fields to provider-specific message attributes/headers.

Messages must not carry raw bytes, long-lived pre-signed URLs, database passwords, access tokens, or full sensitive metadata. Workers use the object reference and their own identity to download files.

### 6.2. Event ID, Schema Version, and Correlation

- **eventId:** unique identifier for deduplication.
- **eventType:** identifies the event kind.
- **schemaVersion:** supports payload evolution.
- **documentId:** identifies the business aggregate.
- **object.version:** points to exact bytes.
- **occurredAt:** when the business event occurred, not when the consumer received it.
- **correlationId:** links logs/traces across API, relay, and workers.

Never use the queue message ID as the business event ID. Brokers may assign different message IDs on duplicate publishes. Event IDs must be generated and persisted alongside the outbox record.

### 6.3. Queue or Event Bus?

| Mechanism | When to Use | Characteristics |
| --- | --- | --- |
| Work queue | One worker group processes each job | Competing consumers, visibility/locks/acks |
| Pub/sub topic | Multiple independent consumers need the same event | Fan-out, separate subscriptions |
| Event bus | Route events by type/source/filter to multiple targets | Routing rules and integrations |
| Stream | Partition ordering, replay, or high throughput needed | Offsets/checkpoints, retention |

Document processing workflows typically use a queue to distribute tasks across a worker pool. When multiple bounded contexts need `document.stored`, publish to a topic/event bus and route to separate subscriptions/queues. Avoid having multiple independent consumers poll the same queue when every consumer must receive every event.

### 6.4. Ordering and Partition Keys

Never assume messages arrive in publish order. If a document emits `stored`, `scan.completed`, and `indexed` events, a worker may receive an older event after a newer one. Use aggregate versions/sequences and conditional state transitions to ignore stale events.

When ordering is required:
- AWS SQS FIFO uses `MessageGroupId` per document/aggregate with appropriate deduplication.
- Azure Service Bus offers sessions to process sequentially per session key.
- Google Pub/Sub supports ordering keys when topics/subscriptions are configured accordingly.

Ordering can reduce throughput because items sharing a group/session/partition serialize. Enable it only when business invariants genuinely require it.

### 6.5. Message Size and Schema Evolution

Keep messages small. Store large payloads in object storage and send pointers only; ensure workers have read permissions and versions are not deleted prior to processing. When evolving schemas:
- Add optional fields with clear defaults.
- Consumers accept prior versions during rollout windows.
- Never alter existing field meanings without versioning.
- Never use classpath-coupled Java serialization between producers and consumers.
- Run contract tests on JSON/CloudEvents payloads across services.

### 6.6. Native Object Events vs. Application Outbox?

Object storage can emit events when objects are created—for example S3 notifications, Azure Event Grid with Blob Storage, or Cloud Storage notifications/Eventarc. Two options exist:

1. **Application outbox:** application verifies the object, commits metadata and outbox in one DB transaction. Fits when events must align tightly with business state.
2. **Native storage events:** provider emits events on object changes. Fits when objects arrive from external producers or workflows originate in storage.

Do not process both sources as two separate events for the same document without deduplication. Storage events can duplicate, arrive delayed, or arrive out of order; consumers must still check database state, object versions, and event identity.

## 7. Queue Consumers and Database Updates

### 7.1. Consumer Flow

A safe consumer typically executes these steps:

1. Parse and validate the event envelope.
2. Check schema version, event ID, and object pointer.
3. Read database metadata to verify tenant, document state, and object version.
4. Claim work via a lease/conditional state transition.
5. Download the exact object version and verify checksum.
6. Process bytes outside long database transactions.
7. Upload result artifacts using deterministic object keys or dedicated versions.
8. Within one DB transaction, update state, insert inbox/dedup record, and write any next outbox event.
9. Ack the message strictly after the transaction commits.
10. On transient failures, let the queue retry per policy; route permanent failures to DLQ/quarantine.

Never hold a database transaction open across file downloads or OCR/virus scans. Long transactions hold locks/connections, increasing deadlocks and pool exhaustion.

### 7.2. Inbox and Idempotency

Consumers can maintain an inbox table with unique key `(consumer_name, event_id)`. Insert the inbox record and update business state in the same transaction. If an event is redelivered, the unique constraint detects the duplicate and the consumer can ack safely after verifying the prior event committed.

For long processing, do not insert an inbox "completed" record before side effects finish. Use a job/lease table to claim and track `PROCESSING`, `RETRY_WAIT`, and `COMPLETED`; write the inbox completion record inside the transaction committing the results.

### 7.3. Claiming via Leases

To prevent two workers from processing the same document simultaneously, use a conditional update or short row lock:

~~~sql
UPDATE document
SET status = 'PROCESSING',
    lease_owner = :worker_id,
    lease_until = :lease_until,
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = :document_id
  AND status IN ('STORED', 'RETRY_WAIT')
  AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP);
~~~

Check the affected row count. If 0, another worker already claimed it, the document is finished, or the state is invalid. Leases must expire and be renewed during long processing; if a worker dies, jobs can be reclaimed after timeout.

Use optimistic versions or fencing tokens so a stale worker cannot overwrite results after another worker acquires the lease. Checking lease ownership only at the start of processing is insufficient if a slow worker keeps running past lease expiry.

### 7.4. Completion Transaction

Pseudo-code example of an application service:

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCompletionService {

    private final DocumentRepository documents;
    private final InboxRepository inbox;
    private final OutboxRepository outbox;

    @Transactional
    public void complete(
            UUID documentId,
            String eventId,
            String resultKey,
            String resultChecksum) {

        if (inbox.exists("document-worker", eventId)) {
            return;
        }

        Document document = documents.findByIdForUpdate(documentId)
                .orElseThrow();

        if (document.isProcessed()) {
            inbox.save(InboxRecord.completed("document-worker", eventId));
            return;
        }

        document.markProcessed(resultKey, resultChecksum);
        documents.save(document);
        inbox.save(InboxRecord.completed("document-worker", eventId));
        outbox.save(OutboxEvent.documentProcessed(
                documentId, resultKey, resultChecksum));
    }
}
~~~

In production, avoid races between `exists` and `insert` by enforcing a unique constraint on the inbox table. Handle unique violations per transaction boundaries. Result objects must be uploaded and verified before the completion transaction; if the transaction fails, cleanup/reconciliation handles orphan artifacts.

### 7.5. Ack After Commit

If you ack a message before DB commit, a process crash can lose work. If you commit before ack, a crash can cause message redelivery. Choose commit-before-ack and make consumers idempotent.

Queue adapters must clarify when ack/complete/acknowledge happens per framework. Never dispatch work to a background thread and return early from a listener if the runtime auto-acks on return.

### 7.6. Result Objects and Off-Database Side Effects

Workers may upload thumbnails/OCR JSON to object storage before committing the database. If the DB commit fails, the result object becomes an orphan. Use deterministic keys derived from document ID, source version, and processor version so retries overwrite cleanly with the same logical result; or use attempt-specific keys and clean up unreferenced attempts.

If overwriting the same key is possible, enable versioning or conditional writes so stale workers cannot overwrite newer results. The database should point only to verified result versions.

## 8. Retries, DLQs, and Recovery

### 8.1. Error Classification

| Error Category | Examples | Action |
| --- | --- | --- |
| Transient | Timeouts, throttling, temporary network errors | Retry with exponential backoff and jitter |
| Dependency unavailable | Database failover, storage API outage | Bounded retries, circuit breakers, and alerts |
| Permanent input | Unsupported format, checksum mismatch | Mark `FAILED`/quarantine; do not retry indefinitely |
| Authorization | IAM/RBAC denied, secret access denied | Alert and fix policies; retry only after policy fix |
| Poison message | Malformed payload or unsupported schema | DLQ/quarantine, preserve event ID and error code |
| Concurrency conflict | Lease/version changed | Reload state; do not treat as provider error |

Never retry every exception. Retrying permanent errors drives up costs and backlogs; failing to retry transient errors breaks resilience.

### 8.2. Exponential Backoff and Jitter

Backoff increases delays between attempts, e.g., 1s, 2s, 4s, 8s up to a max delay; random jitter prevents workers from retrying in lockstep. Cap max attempts and total job age per SLO.

Queue visibility timeouts/lock durations must exceed expected processing time or be renewed. For batch consumers, define partial failures clearly so one poison record does not unnecessarily retry the whole batch.

### 8.3. Dead-Letter Queues

A DLQ captures messages that exceeded retry limits or cannot be processed. DLQs need:
- Alerts when the first message arrives or age crosses thresholds.
- Retention sufficient for investigation.
- Procedures to inspect masked payloads and correlation IDs.
- Controlled redrive tooling after fixing root causes.
- Idempotency verification before replay.
- Restricted read/redrive permissions since payloads may contain sensitive metadata.

Do not continuously redrive an entire DLQ while downstream dependencies remain down. Doing so creates retry storms and risks overloading downstream services.

### 8.4. Reconciliation Jobs

Queues are not the only place to detect incomplete work. A periodic reconciliation job can find:
- Documents marked `STORED` lacking outbox events or with unpublished events.
- Documents in `PROCESSING` with expired leases.
- Outbox rows unpublished for too long.
- Objects existing whose metadata intents expired.
- Metadata pointing to missing objects/versions.
- Result objects unreferenced by the database.
- DLQ events whose documents remain in retryable states.

Reconciliation repairs state per policy and writes audit logs. Never auto-delete an object simply because one query missed metadata; enforce grace periods and verify versions/retention.

### 8.5. Compensation and Sagas

Multi-step workflows lacking distributed transactions can use sagas/compensation:
- Object upload succeeds but metadata fails to commit: mark orphan candidate or clean up after grace period.
- Metadata is `STORED` but publish fails: outbox relay retries.
- Worker creates artifact but DB update fails: retry with deterministic key or clean up artifact.
- Processing fails permanently: mark `FAILED`, retain source object per retention/quarantine policy.
- User cancels before worker claim: transition state and ignore stale events; if a worker is already running, use cancellation flags/compensation.

Compensation is a business-level corrective action, not an ACID rollback. Deleting an object may be irreversible if downstream services already downloaded it; define side effects and retention clearly during design.

## 9. Provider Mapping: AWS, Azure, and Google Cloud

### 9.1. AWS: S3 + SQS/EventBridge + RDS/Aurora

| Role | Service | Spring Integration |
| --- | --- | --- |
| Object storage | Amazon S3 | AWS SDK for Java v2, Spring Cloud AWS S3 |
| Work queue | Amazon SQS | AWS SDK v2, Spring Cloud AWS SQS |
| Event routing | Amazon EventBridge | AWS SDK v2 / compatible AWSpring integration |
| Relational database | Amazon RDS/Aurora | Spring JDBC/JPA, PostgreSQL/MySQL drivers |
| Secrets | AWS Secrets Manager / SSM Parameter Store | AWS SDK / AWSpring integration |

Common flow: API uploads objects to S3; database transaction records metadata and outbox; relay sends SQS messages; workers read S3 via IAM roles, process, and update RDS. If using S3 event notifications instead of an application outbox, design event deduplication and state verification.

The API IAM role needs `PutObject` on upload prefixes; workers need `GetObject` on source prefixes and `PutObject` on result prefixes; queue publishers/consumers need `SendMessage`/`ReceiveMessage`/`DeleteMessage`; database identities are separate. Never grant a single full-access S3/SQS/RDS role to every component.

### 9.2. Azure: Blob Storage + Service Bus/Event Grid + Azure Database

| Role | Service | Spring Integration |
| --- | --- | --- |
| Object storage | Azure Blob Storage | Azure Storage Blob SDK, Spring Cloud Azure |
| Work queue | Azure Service Bus Queue | Azure Service Bus SDK / Spring Cloud Azure |
| Event routing | Azure Event Grid | Event Grid SDK/integration |
| Relational database | Azure Database for PostgreSQL or Azure SQL | Spring JDBC/JPA and drivers |
| Secrets | Azure Key Vault | Azure Identity + Key Vault SDK / Spring integration |

A flow can upload Blobs, record metadata/outbox in Azure Database, publish Service Bus messages, and have workers download Blobs for processing. If Blob events pass through Event Grid to Service Bus, event envelopes differ from application-emitted messages; adapters must normalize them to the internal event contract.

Use Managed Identity/Workload Identity with appropriate data-plane roles for Blob, Service Bus, Key Vault, and database auth where supported. If using SAS connection strings, restrict scope/expiry and maintain a rotation plan. Azure RBAC management-plane roles do not automatically grant Blob data-plane read/write permissions.

### 9.3. Google Cloud: Cloud Storage + Pub/Sub/Eventarc + Cloud SQL

| Role | Service | Spring Integration |
| --- | --- | --- |
| Object storage | Google Cloud Storage | Google Cloud Storage Java client / Spring Cloud GCP |
| Work queue/pub-sub | Pub/Sub | Google Cloud Pub/Sub client / Spring Cloud GCP |
| Event routing | Eventarc | Eventarc triggers and Cloud Run/Functions targets |
| Relational database | Cloud SQL | JDBC driver / Cloud SQL Java Connector, Spring JDBC/JPA |
| Secrets | Secret Manager | Google Cloud Secret Manager client / Spring Cloud GCP |

A flow can upload objects to GCS, record metadata/outbox in Cloud SQL, publish Pub/Sub messages, and have workers fetch the exact object generation. When using Cloud Storage notifications/Eventarc, verify event types, bucket/object generations, and CloudEvent envelopes before mapping to internal events.

Workload Identity assigns principals to APIs/workers. Grant storage object creator to uploaders, object viewer to workers, Pub/Sub publisher/subscriber per component, and separate Cloud SQL connectivity/database privileges. Never store service account JSON keys in containers or queue messages.

### 9.4. Differences to Preserve in Adapters

Do not force all three providers into an overly thin abstraction. Key differences include:

- Object versioning/generation and checksum semantics.
- Pre-signed URLs/SAS/signed URLs and headers/expirations.
- Message acks, visibility/locks, ordering, and retries.
- Event envelopes and notification delivery.
- IAM/RBAC roles, identity tokens, and networking models.
- Database connectivity, IAM authentication, and connection pooling.
- Native encryption, retention, lifecycles, and auditing.

You can define application ports such as `ObjectStore`, `WorkQueue`, and `DocumentRepository`; each provider adapter translates the internal contract to SDK/provider APIs. Never leak provider SDK types into the domain model if you want to keep the domain independent.

## 10. Designing Application Ports and Provider Adapters

### 10.1. Keeping the Domain Model Independent of SDKs

Application services should operate on business contracts. Adapters translate those contracts to the AWS SDK, Azure SDK, or Google Cloud client. Illustrative package layout:

~~~text
document/
  domain/
    Document.java
    DocumentStatus.java
    DocumentStoredEvent.java
  application/
    UploadDocumentUseCase.java
    ProcessDocumentUseCase.java
    port/
      ObjectStore.java
      WorkQueue.java
      DocumentRepository.java
      OutboxRepository.java
  adapter/
    in/
      http/
      queue/
    out/
      s3/
      sqs/
      rds/
      azure-blob/
      service-bus/
      gcs/
      pubsub/
      cloud-sql/
~~~

Do not let domain entities depend on provider SDK types like `S3Object`, `BlobClient`, or `Storage.Blob`. Adapters handle error mapping, retryable statuses, version IDs, checksums, and metadata.

### 10.2. ObjectStore Port

A contract can express the operations needed by the workflow:

~~~java
import java.io.InputStream;

public interface ObjectStore {

    StoredObject put(
            ObjectKey key,
            InputStream content,
            long contentLength,
            String contentType,
            String checksum);

    ObjectMetadata head(ObjectKey key, String version);

    InputStream get(ObjectKey key, String version);

    void delete(ObjectKey key, String version);
}
~~~

`StoredObject` should return the verified key, version/generation, checksum, and content length. Never treat ETag as a checksum when provider semantics do not guarantee it. `delete` should require an explicit version when object versioning is enabled to avoid deleting the wrong revision.

### 10.3. WorkQueue Port

The application can emit events through a port:

~~~java
public interface WorkQueue {

    PublishReceipt publish(DocumentStoredEvent event);

}
~~~

The outbox relay invokes this port. The adapter serializes the event per the internal schema and maps it to an SQS, Service Bus, or Pub/Sub message. `PublishReceipt` confirms only that the broker accepted the publish; it does not mean a worker finished processing.

Do not expose queue URLs, subscription names, receipt handles, or provider SDK types to business logic. Details needed for ack/settlement belong inside the inbound adapter.

### 10.4. Orchestrators Must Not Hold Transactions Across Network Calls

An upload use case can coordinate steps:

~~~java
import java.io.InputStream;

import org.springframework.stereotype.Service;

@Service
public class UploadDocumentUseCase {

    private final UploadIntentService intents;
    private final ObjectStore objectStore;
    private final DocumentFinalizationService finalization;

    public UploadDocumentUseCase(
            UploadIntentService intents,
            ObjectStore objectStore,
            DocumentFinalizationService finalization) {
        this.intents = intents;
        this.objectStore = objectStore;
        this.finalization = finalization;
    }

    public UploadReceipt upload(UploadCommand command, InputStream stream) {
        UploadIntent intent = intents.create(command);

        StoredObject stored = objectStore.put(
                intent.objectKey(),
                stream,
                command.contentLength(),
                command.contentType(),
                command.checksum());

        finalization.markStoredAndQueue(
                intent.documentId(),
                stored.version(),
                stored.checksum());

        return new UploadReceipt(intent.documentId(), "STORED");
    }
}
~~~

Intent creation, object upload, and finalization are three separate boundaries. Never wrap this entire method in one transaction to hold a DB lock while streaming files. If the object upload succeeds but finalization fails, reconciliation locates the orphan object after a grace period.

### 10.5. Consumer Adapters and Application Services

The inbound adapter reads the message, validates the envelope, and calls the application service. The application service does not need to know whether the message arrived from SQS, Service Bus, or Pub/Sub.

~~~java
import org.springframework.stereotype.Service;

public interface DocumentStoredHandler {
    void handle(DocumentStoredEvent event);
}

@Service
public class DocumentStoredHandlerImpl implements DocumentStoredHandler {

    private final DocumentProcessor processor;

    public DocumentStoredHandlerImpl(DocumentProcessor processor) {
        this.processor = processor;
    }

    @Override
    public void handle(DocumentStoredEvent event) {
        processor.process(event.documentId(), event.object());
    }
}
~~~

The inbound adapter acknowledges/completes the message only after the handler returns cleanly and transactions commit per framework contract. If the listener framework auto-acks upon method return, never offload processing to a background thread and return early.

### 10.6. Error Mapping

Standardize errors at the adapter boundary:

| Provider Error Class | Application Category | Behavior |
| --- | --- | --- |
| Throttling/rate exceeded | `TRANSIENT` | Backoff and retry |
| Service unavailable/timeout | `TRANSIENT` or `UNKNOWN_OUTCOME` | Idempotent retry |
| Not found | `NOT_FOUND` | Check state/version; may be permanent |
| Access denied | `AUTHORIZATION` | Alert, do not retry indefinitely |
| Invalid checksum/unsupported content | `INVALID_INPUT` | Quarantine/`FAILED` |
| Precondition/ETag conflict | `CONCURRENCY_CONFLICT` | Reload metadata and decide retry |
| Quota exceeded | `CAPACITY` | Alert, backpressure, and bounded retry |

Never catch every SDK exception and convert it into a generic HTTP 500. Preserve provider error codes in controlled logs without recording credentials or full request headers.

## 11. Provider Integration Configuration

### 11.1. AWS SDK and Spring Cloud AWS

Spring Boot can construct S3/SQS clients using AWS SDK v2. Regions and credential providers come from runtime/default chains; endpoint overrides are strictly for local emulators or test environments.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration
public class AwsStorageConfiguration {

    @Bean
    S3Client s3Client(AwsProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .build();
    }

    @Bean
    SqsClient sqsClient(AwsProperties properties) {
        return SqsClient.builder()
                .region(Region.of(properties.region()))
                .build();
    }
}
~~~

This example relies on the default credentials provider chain. In ECS/EKS/EC2, attach the corresponding task role, Pod Identity/IRSA, or instance profile. Never place static access keys in configuration properties.

Spring Cloud AWS offers integrations for S3 and SQS per release. Use the corresponding starters when you want Spring-managed templates/listeners; use the SDK directly when specialized APIs are required. Never register two listeners simultaneously on the same queue causing unintended processing.

### 11.2. S3 Upload and SQS Publish

Example object upload adapter:

~~~java
import java.io.InputStream;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ChecksumAlgorithm;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

public StoredObject put(
        String bucket,
        String key,
        InputStream input,
        long length,
        String contentType) {

    PutObjectResponse response = s3Client.putObject(
            PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .contentType(contentType)
                    .checksumAlgorithm(ChecksumAlgorithm.SHA256)
                    .build(),
            RequestBody.fromInputStream(input, length));

    return new StoredObject(
            key,
            response.versionId(),
            response.checksumSHA256(),
            length);
}
~~~

This snippet assumes SDK/provider support for SHA-256 request checksums; the application should still compare checksums against expected values and store the verified checksum. Do not treat ETag as SHA-256/MD5 across all upload modes. Add multipart strategies for large files, server-side encryption, and metadata policies in real deployments.

The SQS relay can send JSON events via `SendMessageRequest`; the message body contains the pointer and event ID. For FIFO queues, set message group/deduplication fields per aggregate/event semantics. Workers need receive/delete permissions and read access on the target object prefix.

### 11.3. Azure Blob Storage and Service Bus

The Azure SDK provides distinct clients for Blob and Service Bus. Blob adapters can use `BlobContainerClient`/`BlobClient`; queue adapters use `ServiceBusSenderClient` or processor clients. Use `DefaultAzureCredential` to resolve Managed Identity/Workload Identity in supported runtimes.

Conceptual configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

@Configuration
public class AzureStorageConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(AzureProperties properties) {
        return new BlobServiceClientBuilder()
                .endpoint(properties.blobEndpoint())
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
~~~

Service Bus senders/processors can share an identity, yet roles must separate sender and receiver permissions. If using connection strings, load them from Key Vault/secret sources and rotate them; never commit them to YAML. Azure Blob version IDs/ETags and Service Bus message locks/sessions must be preserved in adapter contracts when required by business flows.

### 11.4. Google Cloud Storage and Pub/Sub

Google Cloud client libraries use Application Default Credentials. On GKE, Cloud Run, or identity-configured workloads, ADC resolves credentials from the runtime. Never store service account JSON keys inside images.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

@Configuration
public class GoogleStorageConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Publisher adapters use `Publisher` and `PubsubMessage`; subscription consumers must ack after handlers finish. For ordering, configure ordering keys and matching subscription semantics. GCS object generations must be stored so workers fetch the exact version if objects can be overwritten.

### 11.5. Databases and Connection Pools

Datasources use Spring Boot JDBC/JPA or R2DBC. Pool sizing must sum across all replicas/workers:

**maximum connections = pool size per instance × maximum instances + migration/admin reserve**

If 20 workers each hold a pool of 10, the database can receive up to 200 connections from workers alone, excluding APIs/monitoring. Scaling queue consumers without budgeting connection limits will overload the database.

Configure connection timeouts, max lifetimes, idle timeouts, and leak detection per database/provider. When using short-lived IAM/database tokens, the pool must fetch fresh credentials when creating new connections. Never treat expired tokens as static passwords.

## 12. Security and Data Governance

### 12.1. Separating Identities by Responsibility

Never share one over-privileged identity across API, relay, and worker. Separate permissions by action:

| Component | Object Storage | Queue | Database |
| --- | --- | --- | --- |
| Upload API | Create/upload in source prefix; HEAD object for verification | No direct publish needed when using outbox | Create intent, update metadata, write outbox |
| Outbox relay | No file read permissions needed | Publish/send messages | Read and update outbox |
| Processing worker | Read source version, write result prefix | Receive/ack messages | Claim jobs, write inbox, update state |
| Reconciliation job | List/head/delete within approved scope | Optionally inspect DLQ metadata | Read state, repair state with audit |
| Admin/support | Controlled operational access | Inspect/redrive per role | Read-only or break-glass |

If a component does not need a permission, do not grant it. For example, the outbox relay does not need to read files; workers do not need permissions to create buckets or modify IAM policies.

### 12.2. AWS IAM

Use ECS task roles, EKS Pod Identity/IRSA, or EC2 instance profiles. Scope policies to specific bucket/prefix and queue ARNs:
- Uploader: `s3:PutObject` on upload prefix.
- Worker: `s3:GetObject` on source prefix and `s3:PutObject` on result prefix.
- Relay: `sqs:SendMessage` on target queue.
- Consumer: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility` if needed.
- Secret reader: `secretsmanager:GetSecretValue` and `kms:Decrypt` only when required by secret/KMS policies.

S3 bucket policies, KMS key policies, and IAM identity policies must agree consistently. Never grant `s3:*` on all buckets or `sqs:*` on all queues.

### 12.3. Azure RBAC and Managed Identity

Use Managed Identity or Workload Identity. Separate management-plane roles from data-plane roles. For example:
- Upload API gets blob creation rights in the target container/prefix.
- Workers get blob read rights and result write rights.
- Relay gets Azure Service Bus Data Sender.
- Consumer gets Azure Service Bus Data Receiver.
- Secret reader gets read permission on the specific Key Vault secret.

Scope role assignments as narrowly as possible. SAS tokens are bearer secrets; restrict resources, permissions, protocols, and expirations. Never use long-lived account keys in application config when identity-based auth is supported.

### 12.4. Google Cloud IAM

Use distinct service accounts/workload identities for API, relay, and workers:
- Uploader has object creation permissions in the bucket/prefix.
- Worker has read permissions on source objects and creation permissions on result objects.
- Relay has Pub/Sub Publisher on the topic.
- Consumer has Pub/Sub Subscriber on the subscription.
- Workloads have Cloud SQL connection permissions and separate database user privileges.
- Secret reader has Secret Accessor on the specific secret.

IAM permission to connect to Cloud SQL does not grant SQL privileges. Database roles must still restrict schemas/tables/operations.

### 12.5. Encryption and Private Networking

Protect data in transit with TLS and at rest with appropriate server-side encryption/KMS. Use private endpoints/VPC endpoints when network isolation is required; verify DNS, routing, firewalls, NAT, and security groups/NSGs.

When using customer-managed keys, separate key usage permissions from key administration permissions. Key rotation, disabling, or loss can render objects unreadable; runbooks must account for this dependency.

### 12.6. Keep Secrets Out of Object Metadata and Messages

Object metadata and queue messages can surface in logs, consoles, event archives, or support tools. Never store passwords, access tokens, pre-signed URLs, private keys, or unnecessary PII there. Store only classified resource references and identifiers.

### 12.7. Tenant Isolation and Object Authorization

Never trust a tenant ID in a message without cross-checking the database/identity. Workers must verify the document belongs to a valid tenant and the object key sits inside an authorized namespace/prefix. Never build object keys by concatenating raw client path inputs; canonicalize and block path traversal.

Pre-signed URLs grant access strictly to a specific object key, operation, and short window. Never hand a source object read URL to a user without authorization checks; signed URLs do not replace business policies.

### 12.8. Retention, Legal Hold, and Data Deletion

Deleting a database row does not delete objects and their versions. Build a deletion workflow:
1. Mark document `DELETE_PENDING`.
2. Prevent new worker claims and emit cancellation events if needed.
3. Delete object versions/results per retention policy.
4. Verify provider responses.
5. Record `DELETED` status and audit log.
6. Retry/reconcile on partial delete failures.

Respect legal holds, backups, retention rules, and object locks. Never delete source objects immediately after worker completion if replay, auditing, or investigation may be needed.

## 13. Performance, Capacity, and Cost

### 13.1. Do Not Ship Bytes Through Queues

Queue messages carry only object pointers and small metadata. This avoids payload limits, reduces network overhead, and lets workers stream or range-read objects. Ensure lifecycle policies do not purge objects before messages are processed.

### 13.2. Multipart Uploads and Streaming

Large files require multipart/resumable uploads. Tune part size, concurrency, and retries per provider. Cap concurrent uploads to avoid exhausting connections, file descriptors, or temporary disk.

If workers only need a slice of an object, use range requests when supported by the format. For gzip/archives, use streaming decompression and cap expanded sizes.

### 13.3. Queue Backpressure

Scale consumers by backlog/oldest message age while staying within database connection, object API quota, and downstream capacity limits. Do not scale purely on queue depth if each message consumes heavy memory/CPU or database connections.

Limits you can enforce:
- Max concurrent messages.
- Batch size.
- Worker replica count.
- Max in-flight processing per tenant.
- Per-provider request rates.
- Database pool size and transaction duration.

When downstream slows down, reduce consumer concurrency or pause subscriptions as supported by the provider; let the queue buffer instead of creating retry storms.

### 13.4. Database Capacity

Total connections equal the sum of API replicas, worker replicas, relays, migrations, and monitoring. Per-instance pool size must be budgeted against maximum autoscale counts, not normal replica counts.

Index status/lease/outbox queries; partition/archive the outbox as volume grows. Polling relays should use small batches and proper indexes, avoiding full table scans each cycle.

### 13.5. Cost Model

Costs include:
- Storage capacity, object versions, PUT/GET/LIST requests, retrieval tiers, and egress.
- Queue requests, message retention, subscriptions/throughput units, or event routing.
- Database compute, storage, IOPS, backups, and connection capacity.
- KMS operations, private networking/NAT, logging, tracing, and cross-AZ/region data transfer.
- Worker execution time, memory/CPU, and duplicate retries.

Never compare per-GB storage rates alone. Designs with excessive HEAD/LIST calls, tight polling, or duplicate processing can cost more than storage. Track costs by tenant/workflow/resource tags where cardinality and privacy policies allow.

### 13.6. Regions and Data Residency

Co-locate buckets/containers, queues, and databases to minimize latency and egress. Define data residency, replication, backup regions, and disaster recovery. Cross-region event delivery can raise latency/cost and introduce compliance requirements.

Never assume object replication automatically replicates database metadata or queue state. Disaster recovery must define how all three stores are restored and how events are replayed/reconciled after failover.

## 14. End-to-End Testing

### 14.1. Unit Tests

Verify domain/state transitions:
- Upload intents create only one document per idempotency key.
- Finalize transitions `PENDING_UPLOAD` to `STORED` strictly once.
- Messages are created with exact object versions/checksums.
- Stale events do not regress state.
- Duplicate consumers never execute side effects twice.
- Permanent input errors transition to `FAILED`; transient errors stay retryable.

Mock `ObjectStore`/`WorkQueue` in application service unit tests. Verify interactions such as publishing outbox rows after commit in integration tests rather than merely verifying mock calls inside a single transaction.

### 14.2. Database Integration Tests

Use PostgreSQL Testcontainers or a compatible database to verify:
- Transaction rollbacks leave no partial business/outbox rows.
- Unique constraints for idempotency/inbox.
- Locks/leases and optimistic versions.
- Multi-worker outbox relay claiming.
- Transaction commits preceding acks.
- Reconciliation queries and indexes.

Testcontainers verifies real database engines in containers; it does not prove cloud provider IAM, object storage, or queue semantics.

### 14.3. Provider Emulators and Fake Services

You can use:
- LocalStack for selected S3/SQS flows.
- Azurite for Azure Blob Storage; Service Bus emulators have limits and do not replace every cloud feature.
- Pub/Sub emulator for publisher/subscriber flows.
- Fake `ObjectStore`/`WorkQueue` implementations for business logic tests.

Emulators do not prove real permissions, encryption key policies, private endpoints, lifecycles, quotas, cross-region behavior, or provider retry semantics. Check emulator limitations before treating tests as contract passes.

### 14.4. Staging Contract Tests

On each provider's staging environment, verify:
1. Workload identities hold exact roles per resource.
2. Uploads produce expected object metadata/versions/checksums.
3. Finalize creates one metadata row and one outbox event.
4. Relay publishes the expected event envelope.
5. Consumers fetch the exact object version.
6. DB state, inbox, and outbox commit in the same transaction.
7. Duplicate messages do not repeat side effects.
8. Retries/DLQs/redrives follow policy.
9. Object lifecycles do not delete files mid-processing.
10. Logs/metrics leak no secrets and carry correlation IDs.

Use dedicated tagged resources with cleanup policies. Never run destructive tests against production buckets, queues, or databases.

### 14.5. Failure Injection

Simulate crashes at every boundary:
- After object upload but before DB finalize.
- After DB commit but before outbox publish.
- After queue publish but before mark-published.
- After object download but before processing.
- After result upload but before DB commit.
- After DB commit but before queue ack.
- When a lease expires and a second worker claims.
- During database failovers or provider throttling.

Each test must prove the final state can reconcile, no confirmed data is lost, and no business side effects repeat.

## 15. Observability and Operational Runbooks

### 15.1. Cross-Workflow Correlation

An upload request traverses API, object storage, database, outbox relay, queue, worker, and downstream services. Generate a correlation ID and propagate it across events/messages. Record event IDs, document IDs, provider request IDs, and processing attempts to stitch steps together.

Logs should include:
- Document ID and event ID.
- Masked object key or logical reference per policy.
- Object version/generation and classified checksum.
- Queue/topic/subscription logical name.
- Processing attempt, lease owner, and duration.
- State transition, error category, and provider request ID.
- Correlation/trace ID.

Never log pre-signed URLs, SAS tokens, authorization headers, database connection strings, or file contents. If document IDs/tenant IDs are sensitive, apply appropriate hashing/masking.

### 15.2. Metrics

| Metric | Meaning |
| --- | --- |
| Upload success/failure | Upload and finalization success rate |
| Upload duration/bytes | Object storage latency and throughput |
| Orphan object count/age | Objects unreferenced by metadata |
| Outbox backlog/oldest age | Events awaiting publish |
| Publish retries/errors | Queue unavailability or permission/quota issues |
| Queue depth/oldest message age | Whether workers keep up with producers |
| Consumer success/failure/duration | Processing effectiveness |
| Duplicate/inbox hit count | Redelivery or duplicate publish rates |
| Leases expired/reclaimed | Worker crashes or slow processing |
| DLQ depth/age | Poison messages and unrecovered failures |
| DB pool active/pending | Database connection pressure |
| Reconciliation corrections | State drift across stores |

Metric labels must stay low-cardinality. Never use object keys, user IDs, arbitrary tenant IDs, or event IDs as labels. Use traces/logs for fine-grained lookups.

### 15.3. Distributed Tracing

Create spans for:
- HTTP upload/finalize.
- Object storage PUT/HEAD/GET.
- DB transactions.
- Outbox relay publish.
- Queue receive/ack.
- Worker processing and downstream calls.

Queues do not always propagate W3C trace context automatically. Where needed, pass trace context via provider message attributes/headers while bounding size. Never put secrets or PII into baggage.

### 15.4. Runbook: Object Uploaded but Document Still PENDING_UPLOAD

1. Check the upload intent, expiry, and upload ID.
2. HEAD the object key/version to verify existence.
3. Verify checksum, size, and content type against policy.
4. Determine whether the finalize API timed out or the DB transaction rolled back.
5. If the object is valid, run idempotent finalization for the document/upload ID.
6. If invalid or intent expired, quarantine/delete per cleanup policy.
7. Write an audit entry and verify the outbox event was created only once.

Never flip database state to `STORED` merely because an object key exists; verify tenant, version, and checksum first.

### 15.5. Runbook: Document STORED but No Message in Queue

1. Inspect the outbox row and published timestamp.
2. Check relay health, leases, and retry schedules.
3. Check target queue/topic and provider API errors.
4. Verify the relay identity holds publish permissions.
5. Check throttling/quotas and networking/DNS/TLS.
6. Let the relay retry from the outbox; do not generate a fresh event ID.
7. Verify the consumer receives the expected event after publishing.

If a publish outcome was ambiguous due to timeout, the relay may emit a duplicate. Consumers must enforce event ID deduplication.

### 15.6. Runbook: Growing Queue Backlog

1. Check oldest message age, queue depth, and DLQ.
2. Inspect worker replicas/concurrency and processing duration.
3. Inspect database pools, lock waits, and query latency.
4. Inspect object GET latency, throttling, and network egress.
5. Classify failing messages by schema, authorization, or dependency.
6. Reduce producer rates or worker concurrency if downstream is overloaded.
7. Scale consumer capacity within bounds if DB/object services have headroom.
8. Monitor backlog drain rate and costs after recovery.

Never scale workers indefinitely when the bottleneck is database connections or provider quotas.

### 15.7. Runbook: Messages in DLQ

1. Retrieve event ID, document ID, failure category, and delivery count.
2. Check database state and whether the object version remains valid.
3. Determine whether the failure is permanent or transient.
4. Fix schema/permission/data/dependency issues before redriving.
5. Use audited redrive tooling with batch limits.
6. Preserve the original event ID or idempotency key during replay.
7. Verify documents complete and DLQ shrinks.
8. Record root causes to fix producers, consumers, or policies.

Never manually edit payloads to force messages through processing without verifying integrity and auditing.

### 15.8. Runbook: Orphan Objects or Missing Metadata

Run reconciliation comparing object inventory against database references with a grace period. Classify orphans:
- Unfinalized upload intents.
- Result objects uploaded before a failed DB commit.
- Old object versions no longer referenced.
- Objects deleted manually or purged early by lifecycle policies.

Delete only after checking versions, retention, legal holds, in-flight leases, and backups. For large object inventories, use batch/inventory reports instead of listing entire buckets on every run.

## 16. Failure Matrix and Recovery States

| Failure Point | Possible Residual State | Recovery Approach |
| --- | --- | --- |
| Object upload fails | Intent `PENDING_UPLOAD`, missing/partial object | Retry upload or expire intent; abort multipart |
| Upload finishes, DB finalize fails | Object exists, metadata not `STORED` | Retry finalize or clean up orphan after grace period |
| DB finalize commits, relay has not run | `STORED` + unpublished outbox | Relay continues publishing |
| Publish succeeds, relay has not marked | Message may exist, outbox still pending | Republish; consumer deduplicates |
| Worker crashes before claim | Message redelivered, document not `PROCESSING` | Another worker claims |
| Worker crashes after claim | `PROCESSING` lease expires | Reclaim with fencing/version check |
| Result upload finishes, DB commit fails | Orphan result object | Retry with deterministic key or clean up |
| DB commit finishes, ack fails | State completed, message redelivered | Inbox/state check then ack |
| Source object deleted prematurely | Metadata points to missing object | Alert, restore version/backup, or `FAILED` |
| Database outage | Queue backlog grows, outbox relay pauses | Restore DB, cap consumers, replay/reconcile |

Every row needs alerts, an owner, a runbook, and a recovery objective. Clearly define which data has been confirmed to clients and which states are retryable.

## 17. Key Architectural Decisions

### 17.1. Outbox or Storage Events?

Use an outbox when database metadata and business events must stay consistent. Use native storage events when object creation from diverse producers is the primary trigger. You can combine both: storage events trigger an ingest service, which verifies objects and records metadata/outbox. Avoid emitting the same logical event from two sources without a shared deduplication key.

### 17.2. Queue or Pub/Sub?

Use a work queue for competing worker pools. Use topics/pub-sub/event buses when multiple independent consumers need the event. One event can route to multiple subscriptions; each subscription needs independent idempotency since each consumer advances and retries separately.

### 17.3. One Database or One Database per Service?

A single database simplifies outbox transactions and metadata in small services. When splitting bounded contexts, each service owns its own database; avoid cross-service database transactions. Communicate via events/APIs and use sagas/reconciliation for cross-service workflows.

### 17.4. Direct Upload or Proxy Through Backend?

Direct uploads fit large files, many clients, and high throughput; they require pre-signed URLs, finalize verification, and CORS policies. Backend proxying fits small files or cases needing streaming validation before storage; it requires capacity, timeouts, and backpressure. Hybrid routing by size/policy is also viable.

### 17.5. Store Metadata in Objects or Database?

Object metadata fits small technical attributes that do not need relational queries. Databases fit owners, status, ACLs, lifecycles, business state, and queries. Avoid maintaining two sources of truth for the same business field. If duplicating metadata for search, define update and reconciliation rules.

## 18. Production Readiness Checklist

1. **Ownership:** owners defined for objects, queues, databases, outbox, and consumers.
2. **Data model:** schemas defined for document ID, object key/version, checksum, tenant, and status.
3. **Upload:** direct/proxy flow, size limits, streaming, multipart abort, and idempotent finalize.
4. **Verification:** HEAD/version/checksum/content type verified before emitting events.
5. **Transactions:** metadata state and outbox rows commit in the same transaction.
6. **Relay:** polling/CDC, leases, retries, idempotent publishing, and retention designed.
7. **Messages:** small payloads with event ID, schema version, correlation ID, and object pointers.
8. **Consumers:** claim/lease, inbox unique keys, state transitions, and ack after commit.
9. **Result objects:** deterministic or attempt-specific keys/versions; orphan cleanup with grace periods.
10. **Retries:** transient/permanent error separation, backoff/jitter, max attempts, and DLQs.
11. **Ordering:** aggregate sequence/session/FIFO enabled only when business invariants demand it.
12. **Identity:** API, relay, workers, and reconciliation hold distinct per-resource roles.
13. **Secrets:** no static keys, SAS/pre-signed URLs, or credentials in code/logs/messages.
14. **Networking:** TLS, private endpoints, DNS, firewalls, egress, and data residency verified.
15. **Capacity:** worker concurrency, queue backlog, database pools, and object API quotas bounded.
16. **Lifecycle:** retention, versioning, legal holds, deletion, and multipart cleanup defined.
17. **Testing:** unit, database integration, emulator, and staging contract/failure-injection tests.
18. **Observability:** correlation, outbox age, queue age, DLQ, orphans, and reconciliation metrics.
19. **Recovery:** runbooks for upload gaps, publish gaps, backlogs, DLQs, lease expirations, and orphans.
20. **Cost:** requests, storage versions, egress, queues, DB, KMS, logs, and worker retries tracked.

## 19. Practice Exercises

1. Diagram the sequence for uploading a file across Spring Boot, object storage, database, and queue; mark transaction boundaries.
2. Design `document`, `outbox`, and `inbox` tables with appropriate unique constraints.
3. Write an upload intent/finalize flow using pre-signed URLs; verify checksums and object versions.
4. Implement a transactional outbox polling relay; simulate a crash after publish but before mark-published.
5. Write a consumer using leases and an inbox; prove duplicate messages do not trigger repeated side effects.
6. Design deterministic result object keys based on source version and processor version.
7. Implement the AWS S3 + SQS + RDS flow; assign separate IAM policies for API, relay, and workers.
8. Implement the Azure Blob + Service Bus + Azure Database flow; use Managed Identity and data-plane roles.
9. Implement the Google Cloud GCS + Pub/Sub + Cloud SQL flow; use Workload Identity and Pub/Sub IAM.
10. Compare native storage events with an application outbox; handle duplicate and out-of-order events.
11. Simulate object upload succeeding while database finalization fails; build reconciliation cleanup.
12. Simulate database commit succeeding while queue publishing fails; prove outbox relay recovery.
13. Simulate worker crash after DB commit but before ack; prove inbox/state checks.
14. Design an audited DLQ redrive with batch limits and preserved event IDs.
15. Calculate database connection budgets when APIs and workers autoscale to maximum replicas.
16. Build a dashboard for outbox backlog, oldest queue message, DLQ, orphan objects, and processing latency.
17. Design a deletion workflow respecting versioning, retention, and legal holds.
18. Write a recovery runbook for inconsistent state across objects, queues, and databases.

**Completion criteria:** learners can build a Spring Boot workflow coordinating object storage, queues, and databases; guarantee atomic metadata/outbox persistence in the database; handle duplicates/retries with inbox/idempotency; accurately distinguish AWS, Azure, and Google Cloud behaviors; test failure boundaries; and operate the workflow using metrics and runbooks.

## References

- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html): S3, SQS, and AWS SDK integration in Spring.
- [Amazon S3 User Guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html): objects, multipart uploads, versioning, lifecycles, and event notifications.
- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html): visibility timeouts, delivery, FIFO, DLQs, and redrive.
- [AWS RDS Documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html): database connectivity, backups, and operational practices.
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/): Spring integration with Blob Storage, Service Bus, and Azure identity.
- [Azure Blob Storage documentation](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction): objects/containers, uploads, and lifecycles.
- [Azure Service Bus documentation](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview): queues/topics, locks, settlement, duplicate detection, and DLQs.
- [Azure Database for PostgreSQL](https://learn.microsoft.com/azure/postgresql/): connectivity, identity, and database operations.
- [Spring Cloud GCP Reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html): Cloud Storage, Pub/Sub, and Cloud SQL integration.
- [Google Cloud Storage documentation](https://cloud.google.com/storage/docs/introduction): objects, generations, uploads, and lifecycles.
- [Google Cloud Pub/Sub documentation](https://cloud.google.com/pubsub/docs/overview): topics, subscriptions, acknowledgments, retries, and dead-lettering.
- [Cloud SQL documentation](https://cloud.google.com/sql/docs/introduction): database connectivity and Cloud SQL connectors.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html): persisting business state and events in the same database transaction.
- [Idempotent Consumer pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html): safely handling repeated message deliveries.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): configuration and secret reference management.
