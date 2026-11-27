# Designing a Document Processing Pipeline with Storage, Queue, and Java Worker

A serverless document processing pipeline typically starts when a user uploads a file to object storage. An object-created event triggers a processing flow; a queue buffers work durably and throttles the rate; a Java worker reads the file, performs security checks, extracts content, runs business processing, and stores the result. An API can expose status so users can track progress without keeping an HTTP request open for the entire processing duration.

The design needs to handle real-world conditions: storage events can arrive duplicated or out of order, queues can deliver messages multiple times, workers can stop mid-flight, files can be malicious or oversized, databases can be slow, and one tenant must never read another tenant's documents. Therefore, the pipeline requires stable job identity, durable state, idempotency, bounded retries, a dead-letter queue, concurrency control, and end-to-end observability.

This lesson builds an end-to-end architecture using object storage, a queue, and a Java worker; describes contracts between components, implements processing stages, handles errors and security, and operates the pipeline with scaling, monitoring, and cost controls.

## 1. Project Goals and Scope

Build a service that accepts documents and processes them in the background. Users can upload PDFs, images, or office documents to storage; the system validates the file, extracts text/OCR, normalizes metadata, and produces outputs for callers to query.

Technical goals:

- The API accepts requests quickly and does not wait for the entire processing flow.
- Files are stored durably in object storage.
- Storage events initiate the pipeline through a queue.
- Java workers process work in independent stages.
- Job state is persisted in a database for recovery after restarts.
- Duplicate delivery does not produce repeated business side effects.
- Retries and DLQs isolate transient failures and poison documents.
- Access permissions, tenant isolation, and sensitive data are controlled.
- Metrics, logs, traces, and per-job cost attribution are available.
- Workers scale with backlog without overloading the database or OCR/AI services.

This scope fits Java serverless functions handling HTTP, messages, and storage events. Specific providers can be Amazon S3/SQS/Lambda, Google Cloud Storage/Pub/Sub/Cloud Run functions, or Azure Blob Storage/Queue/Functions. Configuration names differ, but principles of identity, durability, idempotency, and backpressure remain similar.

## 2. Overall Architecture

~~~mermaid
flowchart TD
    Client[Web / mobile client]
    API[Java upload API]
    DB[(Job database)]
    Storage[(Object storage: quarantine)]
    Event[Storage event notification]
    Router[Event adapter / router]
    Queue[Work queue]
    Worker[Java document worker]
    Scan[Malware and file validation]
    Extract[Text extraction / OCR]
    Process[Business enrichment]
    Result[(Processed object storage)]
    Status[Job status API]
    DLQ[Dead-letter queue]

    Client --> API
    API --> DB
    API -->|Presigned upload URL| Client
    Client -->|Upload bytes| Storage
    Storage --> Event --> Router --> Queue
    Queue --> Worker
    Worker --> Scan --> Extract --> Process
    Process --> Result
    Worker --> DB
    Worker -->|Retry exhausted| DLQ
    Client --> Status --> DB
~~~

Components and responsibilities:

| Component | Responsibility |
|---|---|
| Upload API | Authenticates callers, creates jobs, issues scoped upload URLs |
| Object storage | Stores source files and results with versioning/encryption |
| Storage event adapter | Normalizes notifications into an internal event contract |
| Queue | Buffers work, throttles load, and redelivers on processing failure |
| Java worker | Claims jobs, reads objects, runs each stage, and stores results |
| Job database | Stores state, lease, attempt, object reference, and error |
| Result storage | Stores text/OCR outputs or large artifacts |
| Status API | Lets callers view progress and download results after authorization checks |
| DLQ | Isolates messages that cannot be processed after the retry policy |

Storage events should not carry the entire file. Events only carry the necessary reference and metadata; workers read bytes directly from storage using workload identity.

## 3. Business Flow from Upload to Result

Basic flow:

1. Caller invokes the API to create a document job.
2. The API authenticates the caller, determines the tenant from trusted identity, and creates a job in `UPLOAD_PENDING` state.
3. The API issues a presigned URL or scoped upload mechanism targeting a quarantine prefix.
4. Caller uploads the file directly to object storage.
5. Storage emits an object-created event.
6. The event adapter validates the event and sends a normalized message to the queue.
7. The Java worker receives the message, verifies the job and object version, and claims the stage.
8. The worker validates the file, scans for malware, extracts text/OCR, and performs enrichment.
9. The worker stores outputs, updates state, and emits an event for the next stage if needed.
10. The Status API returns the result or terminal state.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java Upload API
    participant D as Job DB
    participant S as Object Storage
    participant Q as Queue
    participant W as Java Worker

    C->>A: POST /documents
    A->>D: Create UPLOAD_PENDING job
    A-->>C: 201 jobId + uploadUrl
    C->>S: PUT file using uploadUrl
    S-->>Q: ObjectCreated event
    Q->>W: DocumentUploaded message
    W->>D: Claim validation stage
    W->>S: Read exact object version
    W->>W: Scan, extract, process
    W->>S: Write result artifact
    W->>D: Commit stage + SUCCEEDED
    C->>A: GET /documents/{jobId}
    A->>D: Read status
    D-->>A: SUCCEEDED + resultRef
    A-->>C: 200 result metadata
~~~

Creating the job before issuing the upload URL ensures the worker always has a record to validate events against. If the upload fails or the caller abandons it, the job remains in `UPLOAD_PENDING` and can expire according to a cleanup policy.

## 4. API Contract for Upload and Status

The API should decouple upload session creation from uploading bytes. Large files should not pass through a Java function if object storage supports direct upload.

Create document:

~~~http
POST /v1/documents
Authorization: Bearer <access-token>
Idempotency-Key: 6f40b5...
Content-Type: application/json

{
  "fileName": "invoice-2026-041.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 284100,
  "checksumSha256": "optional-client-checksum"
}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /v1/documents/doc-918

{
  "documentId": "doc-918",
  "status": "UPLOAD_PENDING",
  "upload": {
    "method": "PUT",
    "url": "https://storage.example/short-lived-signed-url",
    "expiresAt": "2026-11-17T10:10:00Z",
    "requiredHeaders": {
      "Content-Type": "application/pdf"
    }
  }
}
~~~

The API must restrict lifetime, method, object key, content length, and checksum if the provider supports it. Do not let callers freely choose buckets, tenant prefixes, or arbitrary object keys.

Query status:

~~~http
GET /v1/documents/doc-918
Authorization: Bearer <access-token>
~~~

In-progress response:

~~~json
{
  "documentId": "doc-918",
  "status": "EXTRACTING",
  "createdAt": "2026-11-17T10:00:00Z",
  "updatedAt": "2026-11-17T10:01:22Z",
  "progress": {
    "stage": "TEXT_EXTRACTION",
    "completedUnits": 2,
    "totalUnits": 4
  }
}
~~~

Completed response:

~~~json
{
  "documentId": "doc-918",
  "status": "SUCCEEDED",
  "result": {
    "contentType": "application/json",
    "url": "/v1/documents/doc-918/result"
  }
}
~~~

The Status API must verify tenant and permissions on the document before returning metadata or a result URL. Knowing a document ID does not mean the caller is authorized to read the document.

## 5. Object Keys and Storage Organization

Never use user-supplied filenames directly as object keys. Filenames can contain path traversal, special characters, personal data, or collisions.

A reference key structure:

~~~text
quarantine/{tenantOpaqueId}/{documentId}/{uploadId}/source
processed/{tenantOpaqueId}/{documentId}/{pipelineVersion}/extracted.json
processed/{tenantOpaqueId}/{documentId}/{pipelineVersion}/preview.pdf
~~~

Principles:

- Use backend-generated opaque IDs.
- Separate quarantine and processed prefixes or buckets by trust boundary.
- Enable versioning or record the explicit object version ID in the job.
- Enable encryption at rest and TLS.
- Do not make buckets/containers public.
- Do not use object keys as proof of authorization.
- Store sanitized original filenames as metadata in the database.
- Set lifecycle policies for temporary files and results according to retention.
- Use checksums to detect incomplete or corrupted uploads.

When versioning is enabled, the worker should read the exact version that triggered the event. Reading only the current key risks a newer upload overwriting the key before the worker processes it, causing the old event to read the wrong bytes.

### Quarantine Before Processing

Newly uploaded files must be treated as untrusted. Place files in a quarantine prefix; only promote to a processed/approved prefix after checks succeed. Workers need read access to quarantine and write access to separate outputs. API callers should not have permission to write directly to the processed prefix.

Copying an object to an approved prefix does not itself make the file safe; only do so after validation, malware scanning, and policy checks complete.

## 6. Storage Events and Message Normalization

Provider storage notifications have different schemas. An adapter should normalize them into an internal contract so workers do not depend directly on each provider.

Example internal message:

~~~json
{
  "schemaVersion": 1,
  "eventId": "storage-event-72c1",
  "eventType": "document.uploaded",
  "occurredAt": "2026-11-17T10:00:12Z",
  "documentId": "doc-918",
  "object": {
    "bucket": "document-quarantine",
    "key": "quarantine/t-42/doc-918/up-1/source",
    "versionId": "3Lg...x9",
    "etag": "provider-etag",
    "sizeBytes": 284100,
    "checksumSha256": "..."
  }
}
~~~

Queue payloads should stay small and never embed file bytes or document content. Workers use the object reference to read the file. For large files, payloads should only contain document ID, object version, and required metadata.

### Trusting the Event Source

Never use a tenant ID from a message as the sole source of authority. The worker looks up the document record by `documentId`, verifies the object reference matches the bucket/key/version issued for the job, and reads tenant and classification from the database.

The event adapter must authenticate the issuer if the provider supports resource policies, service identities, or signed events. Never allow Internet callers to inject spoofed messages directly into the queue.

## 7. Duplicate and Out-of-Order Event Delivery

Object storage notifications and queues typically have at-least-once delivery semantics or can replay events. The same object event may arrive multiple times. An older upload event may also arrive after a newer one if a key is written multiple times.

The design must handle:

- Duplicate notifications.
- Delayed events.
- Out-of-order events.
- Queue redelivery after visibility/ack timeout.
- Worker crashes after writing output but before ACK.
- Multipart uploads counted as complete only when the provider emits the appropriate event.
- Delete or overwrite events not being mistaken for new uploads.

Use object version ID or upload ID to pinpoint the exact input. If versioning is unavailable, generate a unique object key per upload session to prevent overwrites. Never rely solely on ETag as a SHA-256 checksum; ETag semantics vary by provider and multipart uploads.

## 8. Job Database and State Machine

The job database is the canonical source of state. The queue only carries processing requests; it should not be the sole place storing progress state.

Reference schema:

~~~sql
CREATE TABLE document_jobs (
    document_id       VARCHAR(128) PRIMARY KEY,
    tenant_id         VARCHAR(128) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    source_bucket     VARCHAR(256) NULL,
    source_key        TEXT NULL,
    source_version    VARCHAR(256) NULL,
    source_checksum   VARCHAR(128) NULL,
    pipeline_version  VARCHAR(64) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(128) NULL,
    lease_until       TIMESTAMP NULL,
    lease_generation  BIGINT NOT NULL DEFAULT 0,
    result_ref        TEXT NULL,
    error_code        VARCHAR(64) NULL,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    completed_at      TIMESTAMP NULL
);
~~~

Simple state machine:

~~~mermaid
stateDiagram-v2
    [*] --> UPLOAD_PENDING
    UPLOAD_PENDING --> UPLOADED
    UPLOADED --> VALIDATING
    VALIDATING --> EXTRACTING
    EXTRACTING --> PROCESSING
    PROCESSING --> SUCCEEDED
    VALIDATING --> RETRY_WAIT
    EXTRACTING --> RETRY_WAIT
    PROCESSING --> RETRY_WAIT
    RETRY_WAIT --> VALIDATING
    VALIDATING --> REJECTED
    EXTRACTING --> FAILED
    PROCESSING --> FAILED
    UPLOAD_PENDING --> EXPIRED
~~~

State meanings:

| State | Meaning |
|---|---|
| UPLOAD_PENDING | Upload session created, complete file not yet received |
| UPLOADED | Object verified and associated with the job |
| VALIDATING | Checking file type, size, checksum, and malware |
| EXTRACTING | Extracting text or running OCR |
| PROCESSING | Enrichment, classification, or business processing |
| RETRY_WAIT | Waiting to retry after a transient error |
| SUCCEEDED | Result durably persisted |
| REJECTED | File violates policy or is unsafe |
| FAILED | Terminal error or retries exhausted |
| EXPIRED | Upload session expired without a valid object |

For multi-stage pipelines, a parent job can be stored alongside a stage executions table. That way, one failed stage does not discard the state of already completed stages.

## 9. Idempotency and Inbox for the Java Worker

A worker may receive the same message multiple times. Deduplicate using a stable identity, such as:

~~~text
consumerName + documentId + pipelineVersion + stage + sourceVersion
~~~

Example inbox table:

~~~sql
CREATE TABLE document_inbox (
    consumer_name     VARCHAR(128) NOT NULL,
    document_id       VARCHAR(128) NOT NULL,
    pipeline_version  VARCHAR(64) NOT NULL,
    stage             VARCHAR(64) NOT NULL,
    source_version    VARCHAR(256) NOT NULL,
    payload_hash      VARCHAR(128) NOT NULL,
    processed_at      TIMESTAMP NULL,
    PRIMARY KEY (
        consumer_name,
        document_id,
        pipeline_version,
        stage,
        source_version
    )
);
~~~

If business updates live in the same database, record the inbox entry and update stage state within a single transaction. If the worker runs long tasks or calls external services, use a claim/lease and fencing token. Never use a static `Set` or local cache as canonical deduplication because serverless scale-out creates multiple independent execution environments.

An already-completed duplicate can be ACKed without re-running side effects. If another worker currently holds the lease, only ACK the duplicate when a recovery process guarantees expired leases will be scanned and re-enqueued; otherwise, let the message retry according to policy.

### Writing Results to Storage

Object storage and databases do not share transactions. Use a deterministic output key based on document, stage, pipeline version, and input version. If a worker crashes after writing the object but before committing to the DB, a subsequent run can verify that object and finish committing. Orphaned outputs require lifecycle/garbage collection.

Never let an older worker overwrite results from a newer pipeline version. Use immutable keys and fencing/version checks before updating `result_ref`.

## 10. Claiming Jobs with Leases and Fencing Tokens

A worker may time out during OCR or an AI call. If the job stays in `RUNNING` forever, nothing can continue. Leases let another worker reclaim the job after the lease expires.

When claiming:

- Use a conditional update or row lock so only one worker wins.
- Record `lease_owner` and `lease_until`.
- Increment `lease_generation` as a fencing token.
- Renew the lease while the stage is still running.
- Only allow the owner with the current generation to update state.
- Have a sweeper detect expired leases to re-enqueue or mark for reconciliation.

Never check a timestamp in Java and then issue a separate update. Claiming must be atomic at the database. Use database time to avoid clock skew across execution environments.

If an old worker wakes up after the lease has been granted to a new worker, the fencing token prevents the old worker from overwriting newer state. Downstream side effects also need idempotency or version conditions.

## 11. Java Worker: Message Contract and Handler

A message can be represented as a record:

~~~java
public record DocumentUploaded(
        int schemaVersion,
        String eventId,
        String documentId,
        String bucket,
        String objectKey,
        String versionId,
        String checksumSha256) {}
~~~

Framework-neutral illustrative handler:

~~~java
public final class DocumentWorker {

    private final JobRepository jobs;
    private final ObjectStore objectStore;
    private final DocumentPipeline pipeline;
    private final ResultStore results;
    private final TransactionRunner transactions;
    private final OutboxRepository outbox;

    public DocumentWorker(
            JobRepository jobs,
            ObjectStore objectStore,
            DocumentPipeline pipeline,
            ResultStore results,
            TransactionRunner transactions,
            OutboxRepository outbox) {
        this.jobs = jobs;
        this.objectStore = objectStore;
        this.pipeline = pipeline;
        this.results = results;
        this.transactions = transactions;
        this.outbox = outbox;
    }

    public void handle(DocumentUploaded message) {
        DocumentJob job = jobs.require(message.documentId());
        verifyObjectReference(job, message);

        Claim claim = jobs.tryClaim(
                job.documentId(),
                "VALIDATE_AND_PROCESS",
                workerIdentity(),
                leaseDuration());

        if (claim.completed()) {
            return; // Duplicate of a completed stage.
        }
        if (!claim.acquired()) {
            throw new RetryableProcessingException(
                    "Stage is owned by another worker");
        }

        try {
            StoredObject source = objectStore.get(
                    message.bucket(),
                    message.objectKey(),
                    message.versionId());

            ProcessingResult result = pipeline.process(source, job);

            String resultRef = results.putImmutable(
                    job.documentId(),
                    job.pipelineVersion(),
                    message.versionId(),
                    result);

            transactions.execute(() -> {
                jobs.completeIfLeaseOwner(
                        job.documentId(),
                        claim.leaseGeneration(),
                        resultRef);

                outbox.insertDocumentProcessed(
                        job.documentId(),
                        resultRef);
            });
        } catch (PermanentDocumentException error) {
            jobs.rejectIfLeaseOwner(
                    job.documentId(),
                    claim.leaseGeneration(),
                    error.safeCode());
        } catch (Exception error) {
            jobs.releaseForRetryIfLeaseOwner(
                    job.documentId(),
                    claim.leaseGeneration(),
                    classify(error));
            throw new RetryableProcessingException(error);
        }
    }

    private void verifyObjectReference(
            DocumentJob job,
            DocumentUploaded message) {
        // Compare bucket, key and version with the upload session
        // recorded by the trusted API. Never trust tenant data
        // supplied only by the queue payload.
    }

    private String workerIdentity() {
        return "runtime-instance";
    }

    private Duration leaseDuration() {
        return Duration.ofMinutes(3);
    }

    private RetryDecision classify(Exception error) {
        return RetryDecision.from(error);
    }
}
~~~

This is an illustrative skeleton; interfaces and models must be defined in the application. In production, ensure stage completion, outbox insertion, and job state transition execute within the same transaction. For multi-stage processing, each stage can have its own worker/queue rather than a single function doing everything.

If a message arrives while the stage is being processed by another worker, handling depends on the recovery model. You can retry the message or ACK the duplicate if a durable sweeper will replay the job upon lease expiration. Never ACK and drop it when no recovery mechanism exists.

## 12. Document Processing Steps

A secure pipeline should separate file inspection from business processing.

### Step 1: Object Verification

- Check that bucket/key/version match the upload session.
- Check actual size and checksum.
- Verify content type using bytes/signatures, not just the extension.
- Enforce limits on page count, image dimensions, and compression ratio.
- Reject empty or oversized files.
- Record object metadata in the job record.

### Step 2: Malware Scan and Quarantine

- Scan for malware using an approved service or engine.
- Do not open the file with business parsers before passing required checks.
- Quarantine suspicious files.
- Record scan result, engine version, and timestamp.
- Proceed only when policy allows.

### Step 3: Content Extraction

- PDF: extract text; run OCR on image pages.
- Images: run OCR or classify document type.
- DOCX: extract content and metadata.
- CSV: validate encoding, delimiter, and row/column limits.
- Archives: limit nesting, entry count, and total uncompressed size.

### Step 4: Normalization and Enrichment

- Normalize Unicode and whitespace.
- Extract metadata such as invoice number or date.
- Classify the document.
- Validate schemas/business rules.
- Optionally call an AI model for summarization or classification.
- Record confidence and model/prompt version if AI is used.

### Step 5: Persist Results

- Store large outputs in object storage.
- Store reference, checksum, and metadata in the database.
- Transition the job to `SUCCEEDED` only after outputs are durable.
- Emit a `document.processed` event via outbox if downstream consumers need it.

## 13. Never Trust Filenames, Extensions, and MIME Types

Callers can send a filename like `report.pdf` while the actual bytes are an executable or archive. The `Content-Type` header is also caller-supplied and can be spoofed.

Layered checks are required:

- File signature/magic bytes.
- Parsers restricted to allowlisted formats.
- Compressed and uncompressed sizes.
- Page count, image dimensions, pixel count, and recursion depth.
- Limits on CPU, memory, and wall-clock time.
- Reject macros or embedded objects if not required by the business.
- Never execute scripts or embedded content.
- Run parsers inside a least-privilege, resource-limited runtime/container.

### Zip Bombs and Parser Exhaustion

A small compressed file can expand to massive size or contain millions of entries. Do not check compressed size alone; bound expanded size, entry count, nesting depth, and extraction time. Stop processing when thresholds are exceeded and record a safe error code.

## 14. Splitting Stages or Using a Single Worker?

You can deploy a single worker for the entire pipeline or split it into multiple stages.

| Design | Pros | Trade-offs |
|---|---|---|
| Single worker | Fewer components, easy to deploy for short pipelines | Longer timeouts, retries redo more work, harder to scale per stage |
| Multi-stage queues | Each stage has its own timeout, memory, and concurrency | Requires state transitions, outbox, and cross-stage correlation |
| Workflow engine | Manages state, waits, branches, retries, and callbacks | Orchestration cost and provider limits |
| Container job for heavy steps | Fits large files, high CPU/RAM, or long runs | Requires managing images, capacity, and job runtime |

A practical approach is starting with a validation + extraction worker if total duration is short and recovery is straightforward. Once OCR, AI enrichment, or conversion have distinct resource profiles, split stages to scale and cap them independently.

Do not over-split to the point where trivial operations cause extra invocations, unnecessary queue hops, and excessive database writes.

## 15. Queues, Retries, and Dead-Letter Queues

Queues absorb bursts and decouple upload rate from processing rate. Consumer concurrency must be capped according to database, OCR service, and model provider capacity.

Retry policy:

- Transient errors like network timeouts or provider 429/503: bounded retries.
- Malformed files or malware: terminal reject/quarantine, never blind-retry.
- Database conflicts: short retry if the transaction can safely re-run.
- Ambiguous outcome after calling a provider: look up/check idempotency before resending.
- Exhausted attempts or elapsed deadline: move to DLQ or `FAILED` per policy.

Use capped exponential backoff with jitter. Never sleep for minutes inside a function; persist `RETRY_WAIT` and use queue delays, schedulers, or workflow timers.

### Visibility/Ack Timeout

For queues with a visibility timeout or ack deadline, the duration must cover processing time plus cleanup per provider semantics. If a message reappears while the old worker is still running, two workers may process it concurrently. Inbox/lease/fencing and idempotent outputs serve as safeguards.

The DLQ must retain enough metadata for investigation without storing excessive sensitive data. Redrive in small batches, preserving document ID and object version, and rate-limit redrives to avoid creating a new burst.

## 16. Security and Tenant Isolation

Documents often contain personal data, contracts, invoices, or internal information. Security must be enforced end to end.

### Identity and Access Control

- API authenticates callers and derives tenant from trusted identity.
- Upload URLs grant write access only to the exact object key with short expiration.
- Workers use dedicated workload identities rather than embedded credentials.
- Workers only read the necessary quarantine prefix and write to the processed prefix.
- The Status API filters by tenant and authorization policy.
- Queue policies only allow approved storage event adapters or publishers.
- Result downloads use authorization checks or short-lived scoped URLs.

### Data Protection

- TLS in transit and encryption at rest.
- Key policies scoped by environment and data classification.
- Never log document contents.
- Redact PII in telemetry.
- Retention and deletion policies aligned with business requirements.
- Audit who uploaded, who read, who downloaded results, and when.
- Separate bucket/key namespaces or access policies across tenants.
- Enforce authorization on the backend, never relying on callers knowing an object key.

### Parsers and SSRF

If the pipeline fetches content from caller-supplied URLs, protect against SSRF: block loopback, private, link-local, and metadata endpoints; validate DNS resolution and redirects; restrict schemes/ports; or allow only registered domains. Prefer uploads via system-generated presigned URLs instead of having workers fetch arbitrary URLs.

## 17. End-to-End Pipeline Observability

Every document job needs a stable correlation identity. Use `documentId`/`jobId` to link the API, storage event, queue message, worker stage, and result. Propagate trace context via message attributes when supported.

Recommended metrics:

| Metric | Purpose |
|---|---|
| Upload accepted/rejected | Track upload experience |
| Queue depth and oldest message age | Measure backlog |
| Stage duration p50/p95/p99 | Identify slow stages |
| End-to-end completion time | Measure user-facing SLO |
| Worker concurrency/throttle | Track capacity |
| Retry count and DLQ depth | Detect processing failures |
| Lease expiry/stuck RUNNING | Detect dead or hung workers |
| Malware/validation rejection | Track invalid files |
| Object read/write errors | Detect storage issues |
| Database pool wait | Detect DB bottlenecks |
| Cost per successful document | Track unit economics |

Structured logs should include `documentId`, `stage`, `attempt`, `pipelineVersion`, `objectVersion`, and `errorCode`. Do not use `documentId`, `tenantId`, or object keys as high-cardinality metric labels; use logs/traces to drill down.

Dashboards should distinguish queue wait, validation, extraction, enrichment, and persistence. Measuring only total duration makes bottlenecks hard to isolate.

### Pipeline SLOs

An SLI can measure the percentage of eligible documents successfully processed within a target timeframe:

~~~text
Completion SLI =
  eligible documents completed within deadline
  / eligible documents accepted
~~~

Illustrative SLO example: 99% of valid documents under 20 MB complete within 3 minutes over a rolling 30-day window. The definition must specify which files are eligible, how rejected documents are counted, the start timestamp, and terminal outcomes.

## 18. Scaling and Backpressure

Workers can scale with queue backlog, but unbounded scaling can exhaust database connections or exceed OCR/model API quotas.

Define:

- Maximum worker concurrency.
- Memory-appropriate batch size.
- Per-tenant rate limits.
- Global provider rate limits.
- Database connection budget.
- Queue retention and maximum age.
- Admission control for upload/job creation.
- Separate queues for document types with different resource profiles.

If queue age grows while workers are already at max concurrency, inspect processing throughput and downstream saturation before raising limits. If database connection wait time increases, raising worker concurrency may worsen the issue.

Queues can be separated by workload class: small text documents, large PDF/OCR, and AI enrichment. Each queue gets its own worker configuration and concurrency cap.

## 19. Cost Model

Total cost per document may include:

~~~text
Cost per document =
  storage write/read + retained bytes
  + queue/event operations
  + Java worker compute
  + OCR/AI provider usage
  + database reads/writes
  + network transfer
  + logs/metrics/traces
  + retry and duplicate processing
~~~

Factors to measure:

- File size and retention duration for source/results.
- Number of object reads/writes.
- Worker memory/duration.
- Number of queue messages and stage transitions.
- OCR pages or AI input/output tokens.
- Retry rate and DLQ redrives.
- Egress and cross-region transfer.
- Observability volume.

Optimize by passing object references instead of files through queues; sizing memory via benchmarks; batching small operations where appropriate; avoiding redundant OCR/AI calls on retries; applying lifecycle rules to temporary files; and tracking cost per successful document rather than just cost per invocation.

Do not delete source files immediately upon worker completion if audit, replay, or retention requirements dictate keeping them. Deletion policies must match contracts and compliance.

## 20. Provider Mapping

| Platform | Storage | Queue/event | Java compute |
|---|---|---|---|
| AWS | S3 | SQS, EventBridge, S3 notifications | Lambda |
| Google Cloud | Cloud Storage | Pub/Sub, Eventarc | Cloud Run functions / Cloud Run |
| Azure | Blob Storage | Queue Storage, Service Bus, Event Grid | Azure Functions |

This mapping only reflects architecturally equivalent choices. Verify event delivery, retries, ordering, dead-lettering, identity, and timeouts for the specific provider and service generation. Never assume all storage notifications share identical semantics.

Some providers can deliver storage events directly to a function; still use a queue or event bus when buffering, retry control, fan-out, or producer-consumer decoupling is required.

## 21. Pipeline Testing

Testing is not just uploading one PDF and seeing `SUCCEEDED` status. Failure windows and load must be tested.

| Scenario | Expected Outcome |
|---|---|
| Valid upload | Job created, storage event emitted, and processed successfully |
| Expired upload URL | Storage rejects the upload |
| Oversized upload | Blocked at upload policy or validation |
| Spoofed MIME type | Content sniffing detects and rejects |
| Duplicate storage event | Only one stage produces side effects |
| Out-of-order event | Worker verifies the exact object version |
| Worker crash before DB commit | Transaction rolls back and message retries |
| Worker crash after output write | Retry uses stable output identity, avoids overwriting newer results |
| Queue redelivery | Inbox/lease prevents invalid concurrent processing |
| Database unavailable | Bounded retries, backlog preserved |
| OCR/provider 429 | Backoff and concurrency limits applied |
| Malware file | Quarantined, never promoted to processed |
| Zip bomb/huge page count | Stopped at resource limits |
| Different tenant queries job | No metadata/result returned |
| Expired lease | Sweeper reclaims or re-enqueues |
| DLQ redrive | Preserves document ID and source version |
| New storage version appears | Old job still reads its recorded version |
| Retention expires | Lifecycle deletes the right objects per policy |

### Load and Recovery Testing

- Ramp up upload rates to determine worker throughput.
- Spike tests to verify queue buffering and scale-out.
- Soak tests to uncover memory leaks or parser resource leaks.
- Kill workers mid-stage.
- Induce database slowness and provider rate limits.
- Build up a backlog and measure drain time.
- Redrive a small DLQ batch.
- Restore database/object references in a test environment and verify consistency.

Never test real malicious files in production. Use safe test fixtures in isolated environments.

## 22. Deployment and Operations

A practical rollout roadmap:

1. Create quarantine and processed buckets/containers with encryption, versioning, and lifecycle policies.
2. Provision the job database and schema migrations.
3. Build the upload API with authentication, tenant scoping, idempotency, and signed URLs.
4. Configure storage events to emit only from the intended bucket/prefix.
5. Route events into a queue with retention, retries, and a DLQ.
6. Deploy the Java worker with workload identity and concurrency caps.
7. Implement inbox/lease/outbox and a sweeper for stuck jobs.
8. Build the status/result API with authorization.
9. Set up dashboards, alerts, and trace propagation.
10. Test duplicates, timeouts, malformed files, and redrives.
11. Canary by tenant or traffic percentage.
12. Monitor queue age, completion SLO, provider quotas, and costs.
13. Periodically review retention, access logs, and deletion policies.

Use Infrastructure as Code to version buckets, queues, policies, roles, functions, and alarms. Keep separate configurations per environment; never share production buckets/queues with testing.

## 23. Common Design Mistakes

- **Sending file bytes over the queue:** inflates payloads, costs, and message limit risks; send object references instead.
- **Using filenames as object keys:** prone to collisions and path manipulation; use opaque document IDs.
- **Reading the current key instead of the object version:** workers may read overwritten files; pin the version.
- **Trusting client-sent Content-Type:** files can spoof formats; validate signatures and parsers.
- **Returning 202 before durable job creation:** work can be lost; commit the job before returning.
- **Ignoring duplicate storage events:** causes repeated worker execution; use an inbox and idempotency.
- **ACKing before committing state:** messages can be lost; commit before ACK.
- **No lease recovery:** `RUNNING` jobs get stuck; use leases and sweepers.
- **Writing outputs and DB without a strategy:** creates orphans or inconsistent state; use immutable output keys, transactions, and cleanup.
- **Unbounded worker scaling:** overloads DB/OCR providers; set concurrency and rate limits.
- **Feeding malicious files to parsers:** risks exploits/resource exhaustion; quarantine and scan first.
- **Unbounded decompression/OCR:** zip bombs or massive page counts exhaust resources; enforce hard limits.
- **Using the queue as the state store:** hard to report progress and recover; use a database.
- **Missing DLQ/redrive:** poison messages loop indefinitely; quarantine them and define a redrive process.
- **Skipping tenant checks on status/result:** leaks documents across customers; authorize every request.
- **Logging full payloads:** leaks sensitive data; log redacted metadata only.

## 24. Process for Building a Serverless Java Pipeline

1. Define document types, size limits, retention, and completion SLO.
2. Design the API for upload session creation and idempotency keys.
3. Create the job record before issuing a signed upload URL.
4. Store files in quarantine using opaque object keys and versioning.
5. Receive storage events and normalize them into a versioned message schema.
6. Push messages to a queue while keeping payloads small.
7. Have the worker look up the job record, verify the object reference, and claim the stage.
8. Validate bytes, checksum, malware, and resource limits.
9. Run extraction/OCR and business processing by stage.
10. Write immutable outputs, update state, and insert outbox records in an appropriate transaction.
11. ACK the message after state is durable.
12. Retry transient errors; reject/quarantine permanent errors; send exhausted messages to a DLQ.
13. Use leases/fencing and a sweeper to recover from dead workers.
14. Secure tenants, secrets, network, and result access.
15. Monitor end-to-end latency, queue age, retries, DLQ, and cost per successful document.
16. Run load tests, fault injection, and redrive tests before production.

## 25. Key Takeaways

A serverless document pipeline decouples upload, storage, orchestration, and processing. Object storage holds files durably; storage events notify of new objects; queues absorb bursts and dispatch work; Java workers run validation, scanning, extraction, and enrichment; a database tracks job state; result storage holds outputs.

The design must assume events/messages can duplicate or arrive out of order and workers can stop at any moment. Use object versions, event identity, inbox/idempotency, leases/fencing, immutable outputs, and retries/DLQs to recover safely. Only ACK after required state has committed.

Protect documents from upload through result download: quarantine, content validation, malware scanning, tenant authorization, encryption, retention, and log redaction. Cap worker concurrency according to database and provider capacity; watch queue age and completion SLOs to throttle load. When components have clear contracts and durable state, the pipeline can scale with demand while keeping correctness, security, and costs under control.
