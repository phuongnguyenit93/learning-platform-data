# Externalizing state and limits of local data in serverless functions

Serverless functions are typically designed around a **stateless** model: each invocation receives input, performs work, and returns a result or emits follow-up events. The platform can spin up additional execution environments as load climbs, reuse an environment across multiple calls, or reclaim environments when no longer needed. Consequently, process memory and local filesystems are not places to store business data that must persist long-term.

To preserve data across invocations, deployments, horizontal scaling, or failures, applications must store state in external services such as databases, object storage, queues, or workflow orchestrators. Choosing the right store depends on data type, consistency requirements, access latency, capacity, cost, and recovery needs.

## 1. Why must serverless functions manage state externally?

A function can be invoked by an HTTP request, a schedule, a queue message, a storage event, or a workflow step. Each invocation may run in a different execution environment.

For example, a serverless order-processing API might receive three near-simultaneous requests. The platform can execute them across three separate environments to handle the load. If each environment keeps an order list in a global variable, each replica only sees its own data. Nothing guarantees the next request will return to the same environment.

Key execution-model characteristics:

- **Platform-managed environment lifecycle:** runtimes can be initialized, reused, or reclaimed without application control.
- **Horizontal scaling:** multiple execution instances can run concurrently across machines or zones.
- **Retries:** the platform or event source may re-invoke the function upon timeouts, transient errors, or missing acknowledgements.
- **New version deployments:** releases spin up fresh environments with updated code and configuration.
- **Bounded execution time:** a single invocation has a time limit; long tasks must be split or hand off state to workflows/queues.
- **Concurrency:** two invocations can update the same record or process the same event concurrently.

Therefore, functions should process inputs independently, read needed state from durable storage, persist outputs, and finish. When the next invocation runs in a different environment, it can pick up seamlessly from saved state.

## 2. Distinguishing in-memory state, local data, and durable data

Three categories of data commonly appear in serverless applications:

| Data category | Examples | Lifecycle and usability |
|---|---|---|
| In-memory state | Local variables, heap objects, cached data in global variables | Exists only within the current process; lost when the environment is reclaimed or restarted |
| Temporary filesystem data | Downloaded files for processing, intermediate compressed archives, temporary outputs | May survive for the execution environment’s lifetime or across reused calls depending on the platform; no long-term durability guarantee |
| Externally stored data | Database records, bucket objects, queue messages, workflow state | Managed by the storage service under configured durability, backup, replication, and recovery policies |

A global variable can be helpful for reusing database connections, SDK clients, or rarely changing reference caches across invocations inside the same environment. However, global variable data is not shared automatically across environments and must never serve as the business system of record.

For example, you can initialize a client outside the handler to cut initialization cost:

~~~javascript
// Node.js illustration: reuse client if the runtime keeps the environment warm.
const databaseClient = createDatabaseClient();

export async function handler(event) {
  const order = await databaseClient.getOrder(event.orderId);
  return processOrder(order);
}
~~~

Reusing the client is purely a performance optimization. Order records still reside in the database. Handler logic must work properly even when the platform creates a brand-new environment.

Never use global variables to store shopping carts, payment states, business sequence counters, or data shared across users. Doing so risks data loss, inconsistent state, and cross-invocation data leaks if shared references linger accidentally.

## 3. Limits of local data

### 3.1. Process memory

Process memory suits transient data within a single call: computation variables, parsed objects, intermediate outputs, or small caches. It has strict limits:

- Not shared across execution environments.
- Not guaranteed to survive after the invocation ends or the environment is reclaimed.
- Bounded by the function’s memory configuration; exceeding it fails or terminates the invocation.
- In-memory caches can go stale when another environment updates underlying data.
- Sensitive data left in variables or the heap must be handled carefully, especially when objects persist across reused invocations.

### 3.2. Temporary filesystem

Many platforms provide a temporary storage area for the execution environment, commonly used to download files, extract archives, process images, or stage artifacts before pushing to durable storage.

For instance, AWS Lambda provides `/tmp` with configurable temporary storage capacity. Data in this directory may persist when the execution environment is reused, yet can vanish when the environment terminates. Other platforms have their own paths, capacity caps, and lifecycles.

When using a temporary filesystem, keep in mind:

- Capacity is limited and must be sized for intermediate files.
- Concurrent invocations may run in separate environments; never assume they see the same local file.
- Leftover files from prior invocations can consume space or mix data if filenames are not unique.
- Environments can be reclaimed at any moment under platform lifecycle rules.
- Files holding sensitive data require proper permissions and cleanup upon completion when mandated by policy.
- When multiple functions or machines must share files, use managed shared storage rather than temporary directories.

Proper file-processing pattern: download the object to scratch space, validate size and format, process, upload outputs to object storage, then delete temporary files. If the invocation aborts mid-way, the source file remains safe in durable storage for retries.

### 3.3. Mounting shared filesystems

Some platforms allow functions to mount network filesystems or managed file services. These act as shared resources that outlive execution environments, though you must verify provider support, deployment regions, access permissions, throughput, connection limits, and disconnect behavior.

A shared filesystem is still an external dependency. Design error handling, file locking, concurrent access control, backups, and recovery. Mounting a volume does not automatically make writes safe against faults or conflicts.

## 4. Choosing storage services by data type

No single service fits every kind of state. Choose storage according to access patterns and business requirements.

| Storage type | Suitable data | Advantages | Trade-offs to consider |
|---|---|---|---|
| Relational database | Orders, payments, accounts, relational and transactional data | Constraints, ACID transactions, SQL queries, configurable strong consistency | Requires connection management, connection limits, query cost, and scaling planning |
| NoSQL database | Profiles, key-value state, metadata, workloads with clear access patterns | Scales by service design, fast key lookups, often supports conditional writes | Requires designing partition keys, indexes, query limits, and consistency models |
| Object storage | Images, videos, documents, input/output files, backups | Ideal for large files, high service durability, capacity-based storage pricing | Does not replace databases for field-level updates or relational queries |
| Distributed cache | Repeated reads, ephemeral sessions, rate limits, TTL-bound data | Lowers latency and offloads databases | Data can expire or be evicted; requires cache-miss and staleness handling |
| Queue or stream | Pending jobs, events moving between steps | Decouples producers/consumers, absorbs bursts, supports retries and load leveling | May replay or duplicate deliveries; needs idempotency and retention policies |
| Workflow/state orchestration | Multi-step process state, callback waits, long retries | Persists progress, orchestrates retries, timeouts, and branching | Adds orchestrator dependency, per-step/duration costs, and workflow limits |

Common service examples include Amazon S3, Amazon DynamoDB, Amazon RDS/Aurora, Amazon SQS, Amazon ElastiCache; Google Cloud Storage, Firestore, Cloud SQL, Pub/Sub; Azure Blob Storage, Cosmos DB, Azure SQL, and Service Bus. Product names differ, yet selection principles remain similar: object storage for files, databases for structured state, caches for regenerable data, queues for async work, and workflow engines for multi-step processes.

Avoid storing entire large files inside a database when object storage fits better. Typically, store the file in a bucket while keeping metadata—owner, object key, processing status, checksum, and creation timestamp—in the database.

## 5. Designing externalized state

A resilient design clearly defines which store is the system of record, who can update it, and which state transitions are valid.

For example, a document-processing workflow might follow these states:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> RETRY_PENDING
    RETRY_PENDING --> PROCESSING
    PROCESSING --> FAILED
    COMPLETED --> [*]
    FAILED --> [*]
~~~

The state record can store fields such as:

~~~json
{
  "jobId": "job-2026-00042",
  "objectKey": "incoming/customer-42/document.pdf",
  "status": "PROCESSING",
  "attempt": 2,
  "createdAt": "2026-11-22T08:00:00Z",
  "updatedAt": "2026-11-22T08:02:10Z",
  "lastErrorCode": null
}
~~~

This example only illustrates data structure. Real systems must specify field types, timezones, ID formats, and protection rules for sensitive fields.

Key design principles:

1. **Clear system of record:** define which database or data store records authoritative state. Caches hold only regenerable copies.
2. **Conditional state transitions:** allow transitions only from valid states—such as `RECEIVED` to `PROCESSING`—preventing two workers from claiming the same job.
3. **Track timestamps and versions:** record update times, attempt counts, and versions to detect stale writes or conflicts.
4. **Store reference keys:** for large files, store the object key and version rather than embedding file contents inside the state record.
5. **Define retention:** specify how long completed states, temporary data, logs, and backups are retained.
6. **Plan recovery paths:** define how to resume from saved state if a function times out or a workflow is interrupted.

For processes running longer than one invocation limit, split the work into short steps. After each step, write a checkpoint to the database or let a workflow engine track progress. The next invocation reads the checkpoint and resumes. Avoid holding overall progress solely in memory during a long-running function, because a timeout or environment reclamation discards unsaved progress.

## 6. Concurrency, retries, and idempotency

Serverless systems typically scale by executing many invocations concurrently. Events may be redelivered when consumers time out, fail to acknowledge, or hit transient errors. Thus, a single event can be processed more than once.

**Idempotency** is the property of processing a repeated request without creating unintended extra business side effects beyond the expected outcome. For example, receiving the same payment event twice must never record two payments.

A common handling pattern:

1. Identify a stable idempotency key, such as a system-assigned event ID or business operation ID.
2. Create a processing record guarded by a unique constraint or conditional write.
3. If the key already exists and is completed, return the saved result or skip repeating side effects.
4. If the key is currently in progress, apply wait, retry, or lease/timeout checks.
5. Persist the outcome and completed state consistently.

Illustrative SQL example:

~~~sql
CREATE TABLE processed_events (
    event_id       VARCHAR(128) PRIMARY KEY,
    status         VARCHAR(24) NOT NULL,
    result_ref     VARCHAR(512),
    created_at     TIMESTAMP NOT NULL,
    completed_at   TIMESTAMP
);
~~~

The `event_id` primary key prevents inserting two records for the same event. However, a deduplication table alone is insufficient: updating business tables and marking the event complete must be coordinated using transactions or an appropriate pattern. When calling external payment APIs, pass the idempotency key downstream if the API supports it.

When multiple invocations update the same record, use:

- Transactions to bundle multiple changes that must succeed or fail atomically.
- Conditional updates or version-based compare-and-swap.
- Unique constraints to prevent duplicate rows.
- Time-bounded leases granting temporary worker ownership that expires if the worker dies.
- Distributed locks only when strictly necessary; locks require timeouts, fencing tokens, or safeguards against stale workers writing after losing their lease.

Never use an in-memory mutex inside an execution environment to coordinate invocations system-wide. An in-process mutex only spans one process and offers zero protection across separate environments.

## 7. Practical example: receiving and processing uploaded files

Suppose customers upload invoices to a serverless application. The system must store the file, validate its contents, extract data, and update processing status.

~~~mermaid
flowchart TD
    A["User uploads file"] --> B["Object storage: input bucket"]
    B --> C["Object-created event"]
    C --> D["Queue or event bus"]
    D --> E["File-processing function"]
    E --> F["Download file to temp space"]
    E --> G["Database: status and metadata"]
    F --> H["Validate / extract"]
    H --> I["Object storage: output"]
    H --> G
    G --> J["Status lookup API"]
    J --> K["User views result"]
~~~

### 7.1. File intake

The API authenticates the user and creates a unique job ID. The file uploads to the bucket under a traceable object key, such as:

`incoming/customer-42/job-2026-00042/invoice.pdf`

The database stores initial metadata:

- `jobId` and owner.
- Object key, version, or file checksum.
- Initial `RECEIVED` status.
- Creation timestamp and retention policy.
- Correlation metadata for request tracing.

Do not use user-supplied filenames as arbitrary filesystem paths. Construct object keys from application rules, verify ownership, and validate file contents.

### 7.2. Asynchronous processing

The object event goes onto a queue or event bus. The consumer function receives the message, extracts `jobId`, verifies status, and uses an idempotency key to prevent duplicate execution.

The function downloads the file to temporary storage, checks size, content type, and checksum, then runs extraction. Results are saved as a new object, such as:

`processed/customer-42/job-2026-00042/result.json`

The database updates status to `COMPLETED`, storing the result path and completion time. The API queries the database to display status to users without depending on the processing function’s memory.

### 7.3. Error handling and retries

If the function times out after writing the output file but before updating the database, retries may run again. Design repeated runs so they do not produce duplicate outputs or corrupt status.

Use deterministic output object keys derived from `jobId`, conditional writes, or stored versions/checksums to detect existing outputs. When updating the database, use transactions or conditional updates to transition status only when the job sits in an eligible prior state.

For unrecoverable errors, move messages to a dead-letter queue after configured attempts, record error codes, and let operators replay once root causes are fixed. Never mark a job complete merely because the function received the event.

### 7.4. Result verification

Operators should verify both data and event flow:

- Input object exists with expected version/checksum and proper access controls.
- Messages were processed or have clear entries in the queue/dead-letter queue.
- Database transitions follow valid state paths.
- Output object exists, is readable, and links to the right job.
- Retrying the same event introduces no duplicate business side effects.
- Users can access only data belonging to them.

## 8. Consistency across databases, object storage, and queues

A workflow may write across multiple services: creating a database record, uploading a file to object storage, and publishing a queue message. These steps rarely share a single distributed transaction. If the function halts mid-way, the system can enter a partial state.

Examples:

- File uploaded, yet database lacks metadata.
- Database marked `PROCESSING`, yet the queue message was never published.
- Message published, yet the database transaction rolled back.
- Output object created, yet status remains `PROCESSING`.

Design patterns that mitigate these risks:

- **Outbox pattern:** write business changes and an outbox row inside the same database transaction; a separate publisher reads the outbox and dispatches messages. Since the publisher may deliver duplicates, consumers still need idempotency.
- **Saga:** break the workflow into steps with compensating actions when later steps fail, instead of assuming one transaction spans all services.
- **Reconciliation jobs:** periodically scan for overdue records or orphaned objects, compare cross-service states, and repair according to business rules.
- **Checkpoints:** persist progress after each step so retries resume from incomplete work.
- **Dead-letter queues:** isolate persistently failing messages for investigation and controlled replay.

Clearly define write ordering, intermediate states, retry conditions, and compensation steps. Never update status to `COMPLETED` before durable outputs are written and verified.

## 9. Security and data lifecycle governance

Data stored outside functions needs consistent protection policies:

- **Least privilege:** execution roles may read/write only the exact buckets, tables, queues, or secrets required.
- **Encryption:** enable encryption in transit and at rest; manage keys per organizational policy.
- **Tenant isolation:** enforce ownership checks at the API and data access layers; never trust client-supplied object keys.
- **Secrets:** store credentials in a secret manager or secure config service, never in images, public env variables, or logs.
- **Retention and deletion:** define retention periods for inputs, outputs, state records, logs, and backups; enforce deletion for business and compliance needs.
- **Backup and recovery:** configure backups, versioning, or replication appropriately; regularly test restores to verify RPO and RTO.
- **Auditing:** log who or which workload read, wrote, or deleted data and when, at the required granularity.
- **No sensitive data in logs:** log correlation IDs and error codes; keep tokens, passwords, personal data, and file contents out of logs.

Treat temporary data as potentially sensitive too. Files in `/tmp` are not inherently secure just because they sit inside a serverless runtime. Restrict permissions, avoid predictable filenames across invocations, and clean up data after processing.

## 10. Performance, scalability, and cost

Externalizing state lets concurrent invocations share data, at the cost of added network latency and service charges. Design efficient access paths:

- Initialize and reuse connections/clients in warm environments when supported by the SDK, while handling expired or closed connections.
- Cap concurrent database connections; rapid function scale-out can overwhelm database connection limits.
- Use managed connection poolers or proxies when suited to the platform and engine.
- Choose partition keys and indexes aligned with real query patterns to avoid hotspots.
- Use TTL-bounded caches for hot, regenerable reads; always provide a cache-miss path.
- Offload heavy or slow tasks to queues to smooth concurrency and avoid blocking invocations.
- Keep large files in object storage, passing only object keys or time-limited URLs between steps.
- Track database calls, object sizes, storage duration, message volume, retries, and egress costs.

Function autoscaling can outpace backend database scaling. Cap concurrency or concurrent invocations, buffer bursts with queues, and monitor connection saturation. Scaling functions without scaling downstream capacity simply widens failures.

## 11. Verifying designs and failure testing

Before launch, test both normal flows and environment-replacement scenarios:

1. Invoke the function repeatedly across separate calls and verify every call reads consistent state from external storage.
2. Simulate cold starts or fresh environments; verify logic does not depend on global variables or leftover temporary files.
3. Submit two concurrent events for one job; verify only one valid state transition succeeds.
4. Resend the same event ID; verify idempotency prevents duplicate business effects.
5. Abort execution between two write steps; verify retries or reconciliation restore valid state.
6. Slow down or break the database; verify timeouts, bounded retries, and backoff avoid infinite loops.
7. Send oversized or malformed files; verify the function rejects safely without leaving orphaned processing states.
8. Test restoring data from backups or versions; verify the application can read and resume processing.

Metrics to track include invocation errors, timeouts, concurrency, duration, memory used, retry counts, queue message age, dead-letter counts, database connections, query latency, object storage errors, and overdue job rates.

Include a correlation ID or job ID in every log entry to tie together requests, events, invocations, and data records. Avoid logging full payloads if they carry sensitive details.

## 12. State and data management checklist

- [ ] Business state has an authoritative system of record in an appropriate database, object store, or workflow service.
- [ ] Global variables hold only reusable clients or regenerable caches, never sole business data.
- [ ] Local memory and temporary files handle only transient processing within size caps and cleanup rules.
- [ ] Large files live in object storage; databases store required metadata and references.
- [ ] Retention, versioning, backups, and recovery procedures are defined per data category.
- [ ] Every event carries an idempotency key; writes are guarded by transactions, conditional writes, or unique constraints.
- [ ] Concurrency, retries, timeouts, duplicate messages, and dead-letter queues are handled.
- [ ] Multi-service writes use checkpoints, outbox, sagas, or reconciliation mechanisms.
- [ ] Access follows least privilege; data is encrypted and never leaked in logs.
- [ ] Concurrency and connections are capped to protect databases, queues, and dependencies.
- [ ] Cold starts, fresh environments, mid-flight failures, retries, and data restores have been tested.

Externalizing state lets serverless applications behave reliably when invocations run across multiple environments, get retried, or are reclaimed. Local memory and temporary filesystems remain useful for computation and intermediate data, while business state belongs in durable services with explicit lifecycles and protections. Combining appropriate storage, idempotency, concurrency controls, and recovery procedures lets applications scale without sacrificing data consistency or durability.
