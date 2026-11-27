# Event-Driven File Upload Processing

## 1. The Architectural Problem

In cloud applications, receiving a file from a user is usually just the first step. After the file is saved, the system may need to validate its format, scan for malware, generate thumbnails, extract content, classify documents, update a search index, or notify other services. Running all of this inside a single HTTP request forces users to wait, invites timeouts, and makes it difficult for the system to absorb upload spikes.

**Event-driven file upload processing** decouples **file ingestion** from **file processing**: object storage emits an event when a new object lands; an intermediary routes the event to a durable queue; one or more workers pull jobs from the queue and process them asynchronously. This is a **reference architecture pattern**, not a single configuration applicable to every system.

Within **CLOUD_ARCHITECTURE**, this pattern illustrates how to move from business requirements to choices of **networking, compute, data, and deployment models**, while evaluating trade-offs across **reliability, security, scalability, cost, and operations** through a **Well-Architected** lens.

**Running scenario:** a document management system lets customers upload PDFs, invoice images, and receipt photos. Users need immediate confirmation that the file was received; security scanning, preview generation, and information extraction can happen afterward. A corrupt file must not block other files, and a redelivered event must not create duplicate documents.

### Translating Business Requirements into Measurable Criteria

The numbers below are **illustrative assumptions only** for practicing design, not default limits of any provider.

| Requirement group | Example requirement | Architectural consequence |
|---|---|---|
| Functional | Accept PDF, PNG, JPEG up to 25 MB; show per-file status | API creates upload sessions, stores metadata, and provides a status API |
| Experience | Upload session creation responds under 500 ms at p95 | Keep malware scanning and file conversion off the synchronous path |
| Latency | 95% of valid files ready for use within 2 minutes of upload completion | Queues, autoscaling workers, job-age alerting |
| Reliability | Never drop received files, never produce duplicate business results | Durable queues, idempotent processing, reconciliation jobs |
| Security | Each customer can access only their own files; unscanned files are never public | Tenant isolation, private storage, separating raw and vetted files |
| Data | Retain originals for 30 days; maintain operation logs and deletion policies | Lifecycle policies, durable metadata, audit logs |
| Operations | Detect processing failures and recover stuck jobs | Metrics, tracing, dead-letter queue, and replay procedures |

You must distinguish **upload success** from **business processing success**. An HTTP success response when bytes land in storage does not mean the file has been scanned or is ready to serve. Both UI and API should make these two milestones explicit.

## 2. Reference Architecture

~~~mermaid
flowchart LR
    U["User application"] -->|"1. Request upload session"| API["Auth and URL-issuing API"]
    API -->|"Create session"| DB[("Metadata DB")]
    API -->|"2. Time-limited URL"| U
    U -->|"3. Direct upload"| RAW[("Object storage: raw zone")]
    RAW -->|"4. Object created"| BUS["Event / Event bus"]
    BUS --> Q[["Durable queue"]]
    Q -->|"5. Receive job"| W["Processing worker"]
    W -->|"Validate, scan, transform"| W
    W -->|"6a. File passes checks"| SAFE[("Object storage: trusted zone")]
    W -->|"6b. Invalid file"| QUAR[("Quarantine zone")]
    W -->|"Update status"| DB
    DB --> OUT["Outbox / status notification"]
    OUT --> APP["Notification / lookup service"]
    Q -.->|"Max retries exhausted"| DLQ[["Dead-letter queue"]]
~~~

This is the **recommended flow for direct client-to-object-storage uploads**. If network rules or inspection policies force files through the application server, an upload proxy/streaming path can be used, at the cost of extra API-tier bandwidth, scaling effort, and failure points.

### Processing Sequence

1. **Initialize session.** The client calls an authenticated API, declaring filename, size, and expected content type. The API checks quotas/permissions, generates an unpredictable **uploadId** and **object key**, and saves the session in **INITIATED** state.
2. **Grant short-lived upload permission.** The API returns a pre-signed URL or narrowly scoped upload credentials. Depending on the storage service's capabilities, it can constrain HTTP method, object key, expiration, content type, or size limits; any constraints unsupported by the provider must be **re-verified server-side**.
3. **Store the original.** The client sends bytes directly to the private **raw** zone. For large files, multipart/resumable uploads can be used; treat the file as complete only upon the corresponding completion event, never processing unmerged parts.
4. **Emit and route the event.** Object storage emits an object-created signal. An event bus can route by event type, bucket, or prefix; a **durable queue** buffers work when workers are slow, paused, or under heavy load.
5. **Worker claims and verifies.** The worker validates the event, fetches actual object metadata, looks up the matching upload session, claims processing rights via deduplication controls, and then checks magic-byte format signatures, size, malware, and content against policy.
6. **Persist results.** Compliant files move to the **trusted** zone or produce derived artifacts; policy-violating files are rejected or quarantined. Metadata transitions to the appropriate terminal state; business events such as **FileReady** are emitted only after durable state is committed.
7. **Read status.** The client polls the API by **uploadId** or receives a notification showing **AVAILABLE**, **REJECTED**, or **FAILED**. Download URLs are issued by the backend per user permissions; the raw zone is never opened publicly.

**Component roles:** an *event bus* helps filter/route to multiple targets; a *queue* helps buffer, distribute work, and retry. For simple flows, notifications from object storage can go **straight into a queue** without requiring both layers. Verify actual integration capabilities on your chosen cloud provider.

## 3. Data Boundaries and Event Contracts

### Storage Zones

| Zone | Role | Recommended policy |
|---|---|---|
| **raw** | Receives unverified bytes from clients | Private, encrypted, restricted read permissions, lifecycle rules for abandoned uploads |
| **quarantine** | Holds suspicious files for investigation or policy handling | Strict isolation, readable only by authorized teams/workflows |
| **trusted/processed** | Holds vetted files or transformed outputs | Served only via authorized applications; tenant-scoped download authorization |
| **metadata DB** | Stores uploadId, owner, object version, status, outcomes, and timestamps | Conditional updates, indexes by tenant/status, backups |

Separating buckets or prefixes for **raw** and **processed** prevents feedback loops like "worker creates thumbnail → new-file event triggers → worker runs again." If sharing a bucket, filter events by a trusted prefix/tag and re-verify inside the worker.

An event from storage should be treated only as a **signal requiring verification**. In particular, never use client-supplied filenames or tenantIds to decide access permissions; the worker must cross-check the object key against the API-issued session. Never place long-lived access URLs or secret data inside event payloads.

Example **internally normalized** event (not a fixed native schema of AWS, Azure, or GCP):

~~~json
{
  "eventType": "object.created",
  "eventId": "evt-9f2c",
  "occurredAt": "2026-11-18T09:00:00Z",
  "bucket": "documents-raw",
  "objectKey": "tenant-42/uploads/u-123/source.pdf",
  "objectVersion": "v-008",
  "uploadId": "u-123",
  "correlationId": "trace-7a1d"
}
~~~

**objectVersion** in the example is a version identifier provided by the storage system or an equivalent immutable identifier. Not every service/configuration enables versioning. Without a version ID, use a **unique object key per upload**, block overwrites, and verify metadata to preserve input identity. **ETag** is not always a reliable content checksum, especially with multipart uploads or certain encryption modes; use a dedicated checksum when business logic requires integrity verification.

### Metadata and States

A metadata record might contain:

~~~json
{
  "uploadId": "u-123",
  "tenantId": "tenant-42",
  "createdBy": "user-7",
  "rawKey": "tenant-42/uploads/u-123/source.pdf",
  "objectVersion": "v-008",
  "status": "PROCESSING",
  "attemptCount": 2,
  "processedKey": null,
  "errorCode": null,
  "createdAt": "2026-11-18T08:59:30Z",
  "updatedAt": "2026-11-18T09:00:08Z"
}
~~~

~~~mermaid
stateDiagram-v2
    [*] --> INITIATED
    INITIATED --> UPLOADED: Complete file received
    INITIATED --> EXPIRED: Timed out
    UPLOADED --> PROCESSING: Claim succeeded
    PROCESSING --> AVAILABLE: Processing finished
    PROCESSING --> REJECTED: Policy violation
    PROCESSING --> RETRY_PENDING: Transient error
    RETRY_PENDING --> PROCESSING: Retry
    RETRY_PENDING --> FAILED: Unrecoverable
    AVAILABLE --> [*]
    REJECTED --> [*]
    FAILED --> [*]
    EXPIRED --> [*]
~~~

Allow only **valid state transitions** using conditional updates (*compare-and-set* or transactions). A delayed stale event must not revert **AVAILABLE** back to **PROCESSING**. **FAILED** is the error state after exhausting the retry policy; transient errors belong in **RETRY_PENDING**. Terminal states should only be reopened via controlled replay procedures with an audit trail.

## 4. Ensuring Correctness Under Duplicate, Delayed, or Out-of-Order Events

Many cloud notification and queuing mechanisms provide **at-least-once** delivery: the same event or job can be replayed. Delivery order is also not guaranteed. Therefore, the architecture must not rely on the assumption of "exactly one event per file."

### Designing Idempotent Processing

- **Business key:** combine **uploadId + objectVersion + task type**, or an equivalent immutable key; do not rely solely on **eventId** because two events with different IDs can still refer to the same object.
- **Atomic work claiming:** insert a job row with a unique constraint or run a conditional update. Only the worker holding a valid **lease** may execute the primary processing step.
- **Leases and fencing tokens:** when a worker hangs, lease expiration lets another worker take over; a monotonically increasing token prevents the stale worker from writing final state after losing ownership.
- **Deterministic outputs:** derive **processedKey** from the job identity so retries do not create multiple divergent output files. Writing an object and updating the DB span two separate systems; idempotency or reconciliation is needed when one step succeeds and the other fails.
- **Acknowledge messages last:** only ACK/delete the message from the queue after required results are durably persisted. Acking early risks losing work if the worker crashes; acking late requires tolerating redelivery.

The following pseudocode illustrates the orchestration idea without tying to a specific SDK:

~~~text
on_object_created(event):
    session = database.find_by_upload_id(event.uploadId)
    source = object_storage.head(event.bucket, event.objectKey, event.objectVersion)
    verify_session_owner_key_and_size(session, source)

    job_key = (session.uploadId, source.version_or_immutable_key, "scan-and-transform")
    claim = database.try_claim_job(job_key, lease_with_fencing_token)
    if claim.already_completed:
        acknowledge_message()
        return
    if not claim.acquired:
        retry_later()
        return

    result = validate_scan_and_transform(source)
    write_result_to_deterministic_key(result)
    database.commit_result_if_token_current(claim.token, result)
    database.append_outbox_event_in_same_transaction("FileReady", session.uploadId)
    acknowledge_message()
~~~

In real deployments, **REJECTED** has its own outcome and event, while transient errors must let the queue retry. Scanning, transforming, and writing objects should enforce timeouts, memory limits, and resource controls. If processing exceeds the queue's **visibility timeout**, renew the lease/visibility or split work into smaller stages. Also account for a worker losing its lease **while writing to storage**: fencing tokens protect DB updates, while immutable output names or conditional writes limit side effects.

### Avoiding "DB Updated Without Emitting Event"

If a worker marks **AVAILABLE** and crashes before publishing **FileReady**, downstream services may miss the signal. The **transactional outbox** pattern closes this gap:

1. Within the **same DB transaction**, write the new state and an outbox record.
2. A separate publisher reads the outbox, sends the event to the broker, and marks it sent.
3. The publisher may send duplicates on retry; consumers of **FileReady** must also be idempotent.

You cannot assume atomic transactions across object storage, databases, and event buses merely because each service has local transactions. Coordinate steps via state machines, reconciliation, and idempotent operations.

### When Events Are Lost

Beyond queue-driven processing, a periodic **reconciliation job** can scan for expired **INITIATED** sessions, raw objects without jobs, or **PROCESSING** jobs stuck too long; after verifying actual storage state, it recreates jobs or marks **EXPIRED/FAILED** per policy. This recovers integration glitches, misconfigured notifications, or rare outages; safeguard the reconciliation job itself against creating duplicates.

## 5. Error Handling, Retries, and Dead-Letter Queues

Errors must be classified as **retryable** versus **non-retryable**. Retrying every error wastes money and creates *poison messages*; giving up immediately on every error reduces reliability.

| Scenario | Classification | Recommended handling |
|---|---|---|
| Storage/DB temporarily returns timeout or throttling | Transient | Retry with *exponential backoff* and jitter; cap attempts and total duration |
| Wrong actual format, oversized file, prohibited content | Business/permanent | Record **REJECTED** with safe error code, quarantine/delete per policy; do not retry infinitely |
| Worker crashes mid-execution | Transient | Message reappears after visibility timeout; reclaim lease and process idempotently |
| Event lacks a valid upload session | Suspicious/anomalous | Do not blindly process; log structured details, alert above threshold, handle per security policy |
| Job keeps failing past max allowed attempts | Needs intervention | Route to **DLQ**, record error metadata, enable controlled replay |
| Processed artifact created but DB not updated | Partial state | Retry with deterministic output key, inspect current state, and complete transaction |
| Queue grows rapidly due to underpowered workers | Overload | Scale workers by backlog/age, cap concurrency toward DB and dependencies |

**A DLQ is not an indefinite archive.** Define retention, access controls, DLQ depth alerts, root-cause investigation workflows, and safe replay procedures. During replay, reuse idempotency keys, audit who or what triggered the replay, and never spawn duplicate business records.

## 6. End-to-End Security

Direct uploads to object storage offload servers, yet pre-signed URLs are **temporary bearer credentials**: anyone holding the URL can exercise its granted permissions until it expires or is revoked per platform capabilities.

**Defense-in-depth design:**

1. **Authentication and authorization at the API:** verify tenant, user, quota, and open session count; have the server generate the object key. Never sign arbitrary paths supplied by the client.
2. **Upload restrictions:** short-lived, narrowly scoped URLs/tokens; enforce size and content-type via storage-supported policies, then re-verify actual size and *magic bytes*. HTTP **Content-Type** and filename extensions are client-declared hints, not trustworthy proof.
3. **Private storage:** block public access, encrypt in transit and at rest, configure KMS/keys where needed, apply lifecycle policies, and enforce least-privilege IAM. Workers only need to read raw, write processed, and update metadata within their scope.
4. **Isolate untrusted content:** scan for malware before letting other users download; run document conversions inside sandboxes with restricted privileges, memory, CPU, runtime, outbound networking, and decompression limits. Guard against *zip bombs*, oversized payloads, and exploitable parsers.
5. **Output authorization:** serve trusted-zone objects only once state qualifies; issue short-lived download permissions with backend tenant checks; avoid leaking sensitive raw keys in public URLs/logs.
6. **Personal data protection:** pick regions meeting data residency rules, define retention for files/metadata/logs, and enforce deletion workflows; never log file contents, pre-signed URLs, or tokens. Use audit logs to trace who uploaded, viewed, or deleted files.
7. **Verify event sources:** accept events only from authorized event/queue pipelines; cross-check object metadata and upload sessions before taking action. Monitor bucket configuration and permission changes.

Never mark a file **AVAILABLE** merely because the upload succeeded. Unscanned files must remain off public serving paths, even when the CDN or downstream processors become unstable.

## 7. Networking, Compute, and Data Choices

### Networking and Byte Paths

- **Direct upload:** the client sends bytes over HTTPS straight to storage; the API handles only auth/metadata. Benefits include reduced application-server bandwidth and less need to autoscale the API tier by file size.
- **Upload via API/gateway:** suited when inline inspection is mandatory, a managed gateway policy requires it, or bespoke integration demands it. Trade-offs include extra hops, bandwidth charges, and timeout risk; stream bytes rather than buffering entire files in RAM.
- **Worker to storage/DB path:** prefer private endpoints or private network access where appropriate; restrict outbound Internet egress, separate subnets, and enforce security policies. Do not assume placing a worker inside a VPC automatically keeps all traffic private.
- **CDN for downloads:** use only for files cleared for serving, with proper access controls, cache-control headers, and cache invalidation strategies.

### Compute for Workers

| Execution model | Suitable for | Trade-offs |
|---|---|---|
| **Function/serverless** | Short, independent tasks with spiky traffic | Time/memory/runtime limits, cold starts, concurrency management required |
| **Container worker** | Scanning/conversion using native libraries, long tasks, custom resources | Requires deployment orchestration, autoscaling, image patching, and runtime observability |
| **Workflow orchestrator** | Multi-step stateful flows, branching, approvals, or external waits | Extra service and orchestration cost; does not replace idempotency |
| **Batch/job system** | High-volume batch processing with relaxed real-time needs | Can increase wait times and batch orchestration complexity |

Choose compute based on **p95/p99 processing time, file sizes, library needs, CPU/RAM/GPU demands, quotas, concurrency, and cost**, not merely familiar service names. CPU-heavy tasks like OCR can move to a separate queue so they do not delay thumbnail generation.

### Data and Orchestration

**Object storage** fits file bytes thanks to durability, low bulk storage cost, and lifecycle policies; a **transactional DB** stores upload sessions, owners, states, and permissions; a **queue** holds pending work. Never cram whole files into event payloads, queue messages, or metadata tables.

If the application needs content search, workers can write to a **search index** post-processing; the search index is a rebuildable projection, not the source of truth for upload status. As event volumes and processing types grow, consider splitting consumers for antivirus, OCR, and indexing while explicitly defining which steps are mandatory before transitioning to **AVAILABLE**.

## 8. Scalability and Cost Estimation

Queues let workers process at sustainable capacity and absorb traffic bursts. However, queues only **buffer** load: if arrival rates exceed service rates over extended periods, latency and backlog grow.

Rough capacity estimation:

~~~text
arrival_rate = files arriving per second
processing_time = average seconds a worker spends per file
minimum_concurrency ≈ arrival_rate × processing_time
estimated_throughput ≈ concurrent_workers / processing_time
~~~

For example, a peak of **1,200 files/minute = 20 files/sec** with an average processing time of **6 seconds/file** requires roughly **120 concurrent executions** to keep up with average throughput. Adding 25% headroom for variance yields around **150 concurrency**, assuming DB, storage, antivirus, and quotas all support it. Little's Law calculations are only a starting point; test with real file size distributions, actual processing times, p95/p99, resource limits, and retries.

At a raw ingestion rate of **100,000 files/day**, averaging **8 MB/file**, retained for **30 days**, original storage alone is roughly **24 TB** (decimal units), before counting processed derivatives, versions, replicas, metadata, and overhead. A pipeline that looks like "just a few functions" can incur substantial storage costs.

**Cost categories to include:** GB-month storage and tiers, PUT/GET/LIST requests, event/queue charges, compute duration and memory/CPU, OCR/AI if applicable, DB reads/writes, KMS, logs/metrics, cross-zone/region transfer, and user egress. Replay costs can jump sharply if bugs force large files to be re-scanned or re-converted repeatedly.

**Optimization levers:** set lifecycle policies for raw and derived files, avoid redundant copies, co-locate chatty components in the same region, autoscale on **message age and backlog per worker** (not CPU alone), cap retries, cache immutable outputs, and isolate queues by workload type. Region and tier choices must balance cost against latency, compliance requirements, and disaster recovery.

## 9. Observability and SLOs

Trace the full path from upload session to outcome; every log, trace, and metric should carry **uploadId**, **correlationId**, and task type. Use tenantId for auditing and controlled tracing; avoid attaching high-cardinality IDs to every metric label.

| Metric | Operational meaning |
|---|---|
| **Upload completed rate** | Fraction of sessions that actually produce a complete stored object |
| **Time-to-available p50/p95/p99** | Duration from object completion until ready for user consumption |
| **Oldest message age / queue backlog** | Whether workers are falling behind incoming traffic |
| **Processing success/reject/failure rate** | Separates infrastructure failures from legitimate policy rejections |
| **Retry count and DLQ depth** | Detects poison messages, persistent failures, or new bugs |
| **Worker duration, throttling, concurrency** | Pinpoints compute, dependency, or quota bottlenecks |
| **Reconciliation gap/stale jobs** | Detects missing events, stuck sessions, or half-finished updates |
| **Storage volume and egress** | Tracks data growth and transfer spend |

An illustrative SLO: **99% of valid files reach AVAILABLE within 120 seconds of upload completion**, measured over a 30-day window. Clearly define which files are excluded for policy violations, how start/end timestamps are measured, and how external dependency outages are accounted for. This SLO is **different** from "the URL-issuing API returned HTTP 200."

Alerts are actionable when tied to user impact: **oldest message age** approaching the latency budget; **DLQ depth** climbing steadily; workers getting throttled; **PROCESSING** sessions timing out; infrastructure error rate rising. Dashboards should let operators drill down from system-wide symptoms to a specific **uploadId** for investigation.

## 10. Mapping to Cloud Platforms

The names below are directional guides for service selection; event sources, quotas, ordering, retries, private networking, and URL-signing policies **must be verified against the target platform's documentation**.

| Role | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| File byte storage | Amazon S3 | Azure Blob Storage | Cloud Storage |
| Event routing | S3 Event Notifications / EventBridge | Event Grid | Eventarc / Pub/Sub |
| Durable queue | Amazon SQS | Azure Service Bus / Storage Queue | Pub/Sub |
| Worker | AWS Lambda / ECS Fargate | Azure Functions / Container Apps | Cloud Run / Cloud Run functions |
| Multi-step orchestration | AWS Step Functions | Durable Functions | Workflows |
| Metadata | DynamoDB / RDS | Cosmos DB / Azure SQL | Firestore / Cloud SQL |
| Observability | CloudWatch / X-Ray | Azure Monitor / Application Insights | Cloud Monitoring / Cloud Trace |

For instance, **S3 → SQS → Lambda** can fit short pipelines on AWS; if OCR runs long or needs specialized binaries, container workers can be used. On Azure, **Blob Storage → Event Grid → Service Bus → Function/Container Apps** is one variant; on GCP, **Cloud Storage → Pub/Sub/Eventarc → Cloud Run** is another. Pick components for required functionality and guarantees rather than forcing every service into a single path.

## 11. Evaluation Against the Six Well-Architected Pillars

| Pillar | Evaluation question | Typical measures |
|---|---|---|
| **Operational Excellence** | Can you trace an upload, handle the DLQ, and deploy/roll back safely? | Structured logs, tracing, runbooks, IaC, replay, and dashboards |
| **Security** | Can unvetted files be read publicly or cross tenant boundaries? | Least-privilege IAM, private buckets, malware scanning, encryption, permission checks |
| **Reliability** | How do worker crashes, duplicate events, or lost events affect the system? | Durable queues, idempotency, retries, DLQ, reconciliation, backup/restore |
| **Performance Efficiency** | Does the pipeline meet p95 under multi-fold traffic surges? | Backlog-based autoscaling, split queues, concurrency caps, benchmarks |
| **Cost Optimization** | Which bytes, processing runs, or retries generate unnecessary spend? | Lifecycle rules, cross-region reduction, retry caps, storage tiering |
| **Sustainability** | Are resources right-sized and expired data pruned? | Right-sizing, on-demand processing, expiring stale data, avoiding wasted rework |

There is no single universally optimal answer. For example, keeping a processed copy speeds serving and isolates trusted data, yet raises storage spend; synchronous scanning before responding shrinks the lifespan of unscanned files, yet worsens upload UX and timeout risk. Prioritize using **agreed SLOs and business risk**.

## 12. Error-Prone Designs

| Error-prone design | Consequence | Improvement |
|---|---|---|
| API waits for OCR and scanning before responding | Timeouts, poor scalability, cascading upload failures | Return upload session, process asynchronously, track status |
| Treating events as unique and strictly ordered | Duplicate documents, newer results overwritten by stale events | Idempotency keys + conditional state transitions |
| Using an event bus without a buffer/queue for bottlenecked workers | Loses ability to absorb traffic spikes | Durable queue and backlog-driven scaling |
| Putting raw and processed files under the same unfiltered trigger | Event loops, runaway cost | Separate zones or explicit event filtering |
| Trusting client-submitted filenames and Content-Type | Malicious or mis-typed files slip through | Inspect actual bytes, antivirus, sandboxing |
| Acking the queue before committing DB/output | Lost work if worker crashes | ACK after durable state commit; support idempotent retries |
| Infinite retries on all error types | Unmanaged DLQs, runaway costs | Error classification, backoff+jitter, caps, and runbooks |
| Tracking only upload API 5xx errors | Invisible files stuck mid-pipeline | Measure end-to-end SLO, queue age, DLQ, and reconciliation |

## 13. Practical Design Exercise

**Prompt:** an e-commerce platform lets sellers upload product images up to 15 MB. The system must scan for malware, generate three image sizes, and publish images publicly only after completion. During a campaign, uploads surge tenfold for 15 minutes. Image data must remain in an approved region and sellers must only see their own images.

**Design** the component diagram and answer:

1. Should clients upload bytes through the API or directly to storage? Why?
2. Where are events, queues, and workers used? What signal drives autoscaling?
3. Given two duplicate events and a worker crashing right after writing thumbnails, how do you guarantee two products are not created?
4. When a file is flagged with malware, how must state and access permissions change?
5. Which metrics reveal whether the campaign broke the SLO? How is backlog drained afterward?

### Reference Solution

Choose **short-lived URL-issuing API → private raw zone → object-created event → durable queue → scan-and-resize worker → trusted zone → DB status and outbox → authorized API/CDN**. The API records **uploadId, merchantId, rawKey**; the worker verifies them against the actual object before processing. Never let the CDN serve the raw zone.

For each image, the processing key is **uploadId + objectVersion**; a conditional DB write acquires the lease. Thumbnails are written to three deterministic output keys derived from that key. Upon rerun, the worker checks existing outputs and finishes the DB update rather than creating a second product image record. **ImageReady** emits from the outbox; downstream consumers also process idempotently.

Workers autoscale on **backlog/oldest message age** with concurrency caps so DB and scanners are not overwhelmed. When arrivals outpace workers, the queue absorbs the spike; size workers from arrival rate, scan/resize duration, and latency budget. Malicious files transition to **REJECTED**, are quarantined/deleted per policy, and receive no public URLs. Dashboards track **time-to-available p95**, aged messages, DLQ depth, scan errors, spend, and unfinished sessions. Post-spike, workers drain the backlog to normal thresholds before scaling down.

**Self-check:** does the solution address *correctness* (no lost/duplicate uploads), *safety* (no unvetted files exposed), *latency* (SLO under spikes), *cost* (storage/compute/egress), and *operability* (detecting and recovering incidents)?

## 14. Pre-Production Checklist

- [ ] Clearly define **upload success**, **processing success**, state transitions, and SLOs.
- [ ] Enforce quotas, scoped/short-lived URLs, and server/worker re-verification of actual size and format.
- [ ] Keep raw files private; scan/quarantine before granting access.
- [ ] Use immutable object keys or enable versioning; define explicit idempotency keys.
- [ ] Tolerate duplicate events, out-of-order delivery, worker crashes, and message redelivery.
- [ ] Assign ownership for retries, backoff, DLQ, replay, and reconciliation.
- [ ] Validate timeouts, leases, concurrency, and per-component quotas under load testing.
- [ ] Monitor end-to-end latency, backlog age, DLQ, stuck states, and cost.
- [ ] Maintain metadata backup/restore, data lifecycle policies, IaC, and incident runbooks.
- [ ] Review architecture against all six Well-Architected pillars, recording trade-offs against real requirements.

When these conditions are explicitly designed, event-driven upload processing not only makes applications faster to respond, but also builds a pipeline that can scale, recover, audit, and evolve independently of interactive user flows.
