# Designing Idempotent Tasks for Re-Execution

Interruptible compute—such as Spot VMs, preemptible VMs, or workers using reclaimable capacity—typically costs less or leverages spare cloud capacity. In return, the provider can stop instances when capacity is needed, when provisioning policies change, or per service terms. A running task can therefore be interrupted before completion.

To use this compute type safely, applications must assume a task can run again on the same machine, a different machine, or at another time. **Idempotency** ensures executing the same logical operation multiple times yields a business outcome equivalent to executing it once. Combined with durable checkpoints, deduplication, transactions, and controlled retries, the system can continue work after instance reclamation without creating duplicate charges, duplicate writes, or corrupted state.

In the `CLOUD_CORE_SERVICES_COMPUTE` module, this lesson frames idempotent design in the context of workloads running on replaceable VMs, containers, and workers. The focus is on defining work boundaries, persisting progress outside the instance lifecycle, handling side effects safely, and verifying re-execution capability after interruptions.

After this lesson, you will be able to:

- Explain why interruptible compute requires designing around the assumption that tasks can be re-executed.
- Distinguish idempotency, retries, deduplication, checkpointing, and exactly-once processing.
- Design stable idempotency keys for requests, jobs, and individual processing steps.
- Use unique constraints, transactions, outboxes, and fencing to prevent duplicate side effects.
- Save durable checkpoints and recover progress after a worker is reclaimed.
- Handle interruption notices, graceful stops, queue visibility/leases, and retries.
- Test tasks stopped at various points while preserving data integrity.

## 1. Why Does Interruptible Compute Require Idempotency?

Interruptible compute is compute capacity where an instance can be reclaimed before the user explicitly terminates it. Common names include Spot Instance, Spot VM, preemptible VM, or reclaimable capacity. Warning mechanisms and lead times vary by provider, service type, region, and reclamation reason.

Situations that can interrupt a task:

- The provider reclaims capacity to serve higher-priority demand.
- The instance no longer satisfies provisioning terms or the capacity pool shifts.
- Operators scale in, swap images, or perform infrastructure maintenance.
- The VM/container suffers a host failure, network loss, or sudden termination.
- The worker restarts during a deployment or configuration update.
- Message lease expires and the queue redelivers the work to another worker.

A task may have already performed partial side effects before being stopped. For example:

1. A worker pulls an invoice-generation job.
2. The worker writes a PDF file to object storage.
3. The worker inserts an invoice record into the database.
4. The instance is reclaimed before acknowledging message completion.
5. The queue redelivers the message to another worker.
6. The new worker runs from the start and may create duplicate files or records.

If the task is not designed for re-execution, an interruption can lead to duplicate data, missing data, half-finished state, or wasted rework cost. Idempotency enables the next execution to recognize completed work and proceed safely.

### Design Principles

Assume that:

- An instance can vanish without running its shutdown hook.
- An interruption notice, if present, is only an opportunity to save progress, not a guarantee of receipt.
- A request or message can be redelivered after a timeout.
- A worker can complete side effects yet die before sending an acknowledgement.
- Two workers can process the same job concurrently if a lease expires or retries overlap.
- Local RAM and ephemeral disk are never the sole place where progress lives.
- A job may rerun on a different instance or application version than before.

## 2. Distinguishing Core Concepts

These mechanisms are commonly combined, yet each solves a distinct problem.

| Concept | Role | Example |
|---|---|---|
| Retry | Re-attempt an operation on transient errors | Re-send a message after timeout |
| Idempotency | Repeating the same logical operation creates no extra business effect | Same payment key produces only one charge |
| Deduplication | Recognize and skip already-processed events/jobs | Store committed message IDs |
| Checkpoint | Save progress to resume from a completed point | Processed up to partition 42 |
| Transaction | Group multiple data mutations into one commit/rollback unit | Write result and mark job complete in one transaction |
| Lease/lock | Define which worker is permitted to process during a time window | Worker holds job lease for 30 seconds |
| Fencing token | Prevent stale workers from writing after ownership transfers | Each new lease carries an incrementing generation |
| Outbox | Write business state changes and outgoing events in one transaction | Commit order and outbox event together |
| Compensation/Saga | Undo or offset side effects that cannot share a transaction | Issue refund when a downstream step fails |

### Idempotency Does Not Mean Fast or Error-Free

An idempotent operation can still run slowly, time out, or fail. The key property is that when executed again, it creates no unintended extra outcome.

For instance, setting an order's status to `PAID` repeatedly can be idempotent if the operation always sets the same value. However, adding 100 to an account balance on every run is not idempotent without a transaction key to block duplicate writes.

## 3. At-Least-Once and the Limits of Exactly-Once

In distributed systems, a worker may finish work yet lose connectivity before the queue receives its acknowledgement. The queue does not know the work finished and can redeliver the message. Consequently, many queue systems use **at-least-once** semantics: messages are delivered one or more times until acknowledged or retry policies exhaust.

Never assume a message is processed strictly once. Instead, design idempotent consumers.

### Failure Window Between Commit and Acknowledgement

~~~mermaid
sequenceDiagram
    participant Q as Queue
    participant W as Worker
    participant DB as Database
    Q->>W: Deliver message M
    W->>DB: Write business result
    DB-->>W: Commit succeeded
    Note over W: Instance reclaimed before acknowledgement
    Q->>W: Lease expires, redeliver message M
    W->>DB: Check idempotency key M
    DB-->>W: Already processed previously
    W-->>Q: Acknowledge message
~~~

If a consumer commits the result first and then acks, the message may be redelivered. Idempotency/deduplication lets the next attempt detect the committed result and avoid repeating side effects.

If a worker acks before writing durable results, it can stop after acking and the message will not be redelivered, causing work loss. Therefore, the standard order is to commit results and processing state first, then acknowledge.

### Exactly-Once Must Be Scoped

Some systems provide exactly-once semantics within a bounded transaction or single platform. However, when a task interacts across multiple independent systems—such as queues, databases, object storage, and third-party APIs—maintaining a single global transaction is very difficult.

In practice, teams build an **effectively-once business outcome** by combining:

- Stable idempotency keys.
- Unique constraints or deduplication records.
- Database-scoped transactions.
- Outbox/inbox patterns for events.
- Idempotency APIs on external services where supported.
- Reconciliation or compensation when side effects cannot share a transaction.

## 4. Defining Task Boundaries and Idempotent Units

Before picking keys or writing retry logic, define what constitutes one logical operation.

For example, a video-processing job has these steps:

1. Download source object.
2. Validate format and metadata.
3. Generate thumbnail.
4. Transcode video.
5. Store output.
6. Write metadata to database.
7. Emit completion event.

You can split the job into independent steps with well-defined inputs/outputs. Each step needs to know:

- Job ID and step ID.
- Input object/version/checksum.
- Algorithm or execution image version.
- Idempotency key.
- Status: pending/running/completed/failed.
- Output location and checksum.
- Checkpoint or cursor needed to resume.

If the entire job is treated as one atomic operation, a retry may have to rerun every step. If split sensibly, a new worker can skip committed steps and resume from the incomplete step.

### Choosing Work-Unit Granularity

Units that are too large lose significant progress upon reclamation. Units that are too small generate excessive checkpoint, transaction, and metadata overhead.

Examples:

- Processing 10 million records: split into partitions or batches with stable IDs.
- Video rendering: split by segment or stage.
- ETL: checkpoint by partition and watermark.
- ML training: checkpoint by epoch or optimizer step count.
- Data crawling: checkpoint by cursor/page token.
- Image batching: one object or object group with a dedicated manifest.

Choose boundaries based on processing duration, rework cost, parallelism, and consistency requirements.

## 5. Designing Stable Idempotency Keys

An idempotency key uniquely identifies one logical operation. The key must remain unchanged across retries of that same operation.

### Keys Should Derive from Stable Business Identifiers

Examples:

- Payment: payment intent ID or order ID + transaction type.
- Invoice: order ID + invoice version.
- File processing: object key + object version + transformation version.
- Batch: dataset ID + partition ID + pipeline version.
- Message consumer: producer event ID.
- Scheduled job: job definition ID + scheduled execution timestamp.

Never generate a fresh random UUID on each retry. If every attempt uses a different key, the system cannot recognize them as the same operation.

Example key formula:

~~~text
idempotency_key =
  tenant_id + ":" +
  job_id + ":" +
  step_name + ":" +
  input_version
~~~

Canonicalize components before concatenating or hashing so identical data does not produce different keys due to field order, encoding, or whitespace.

### Key Scope and Expiration

Define:

- Whether keys are globally unique or scoped per tenant.
- Whether a key covers an API call, a job, or a step.
- When the key expires.
- How long results are retained to cover the maximum retry horizon.
- How the same key with a different payload is handled.
- Whether an `IN_PROGRESS` state is needed to block concurrent execution by two workers.

If keys expire too early, an old redelivered message can trigger the side effect again. If kept forever, the dedup table can grow unbounded. Choose retention based on queue retention, retry horizon, business auditing, and data regulations.

### Payload Hash

Store a hash of the canonicalized payload alongside the key. If the same key appears with a different payload, return a conflict error instead of silently returning the stale result or executing a different operation.

## 6. Storing Idempotency Records in a Database

An idempotency record table can include:

- Key and tenant/scope.
- Operation type.
- Payload hash.
- Status: `IN_PROGRESS`, `COMPLETED`, or `FAILED_RETRYABLE`.
- Result or reference to the result.
- Created/updated timestamps and expiration time.
- Lease owner or fencing generation if needed.

Illustrative SQL schema:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id       VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    operation_type  VARCHAR(80)  NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(30)  NOT NULL,
    result_ref      VARCHAR(500),
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

The primary key guarantees two workers cannot simultaneously insert two records for the same tenant/key. However, a unique constraint alone is not enough; conflict-handling and transaction logic must also be sound.

### Conceptual Processing Flow

1. Receive job and determine key.
2. Begin transaction.
3. Insert idempotency record if not present.
4. If key is already `COMPLETED`, return stored result.
5. If key is `IN_PROGRESS` and lease is active, do not execute in parallel.
6. If lease expired, the new worker can take over via fencing/versioning.
7. Execute business mutations in the appropriate transaction.
8. Record result and transition record to `COMPLETED` in the same transaction.
9. Commit.
10. Ack message after commit.

Handle concurrent worker arrivals using unique constraints, row locks, compare-and-swap, or equivalent database primitives.

### Do Not Hold Transactions Open Across Long Jobs

A job can run for minutes or hours. Holding a database transaction open the entire time causes long locks, ties up connections, and increases contention. Instead, break the job into short steps, each committing results and durable checkpoints.

## 7. Idempotency for Side Effects Outside the Database

Not every side effect can participate in a database transaction. For example:

- Sending email.
- Calling a payment gateway.
- Sending SMS.
- Creating resources via cloud APIs.
- Writing objects to storage.
- Publishing messages to another broker.

If a worker calls an external API successfully but stops before saving the outcome, a retry may call again and create duplicate impact.

### Using Target Service Idempotency Keys

If the external API supports idempotency keys, send the same key across all retries of the same operation. The target service can return the recorded outcome rather than executing again.

Keys must remain stable across every attempt and have scope/retention compatible with the target service.

### Using Pending States and Reconciliation

If the external service does not support idempotency:

1. Write an operation record before calling the service.
2. Send the request with a queryable business reference.
3. On timeout, never conclude the operation failed.
4. Query status from the target service using the reference.
5. Retry only after confirming the operation did not occur or that retrying is safe.
6. If status cannot be determined, route to reconciliation/manual review per policy.

A timeout does not mean the request was not executed. Assuming otherwise is a common cause of duplicate transactions.

### Sagas and Compensation

A multi-system workflow may require compensation. For instance, placing an order involves reserving inventory, charging payment, and creating a shipment. If charging succeeds but shipment fails, the workflow may need to issue a refund or release inventory.

Compensation is a new business operation that restores the system to an acceptable state; it is not a physical rollback of a committed transaction. Compensation itself must be idempotent because it too can be retried.

## 8. Outbox and Inbox Patterns

### Transactional Outbox

Suppose an API writes an order to the database and then publishes an `OrderCreated` event to a queue. If the database commits but publishing fails, downstream workers never learn about the new order. If publishing succeeds but the database rolls back, the event describes a nonexistent order.

An outbox writes business changes and outgoing events inside the same transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status)
VALUES ('ord-1042', 'cust-81', 'CREATED');

INSERT INTO outbox_events (event_id, aggregate_id, event_type, payload)
VALUES ('evt-1042', 'ord-1042', 'OrderCreated', '{...}');

COMMIT;
~~~

A separate publisher reads the outbox, dispatches events, and marks them published. The publisher can be stopped after sending but before updating status, so it may resend events. Consumers need an inbox/dedup keyed by event ID.

### Consumer Inbox / Deduplication

The consumer stores processed event IDs in the same transaction as business mutations:

~~~sql
BEGIN;

INSERT INTO inbox_events (consumer_name, event_id, processed_at)
VALUES ('invoice-worker', 'evt-1042', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Execute business changes only if the event row was newly inserted.
-- Real implementations must check the inserted row count within the transaction.

COMMIT;
~~~

If the event already exists in the inbox, the consumer skips the already-completed side effect. Inbox retention must be long enough to cover retries/replays; if intentional replay is needed, use a namespace/version or dedicated reprocessing mechanism.

## 9. Checkpointing to Resume Instead of Restarting from Scratch

A checkpoint is a durable progress record for a job. New workers read the checkpoint to know which parts are already done.

### What Should a Checkpoint Store?

Depending on the workload, store:

- Job ID, step ID, and input version.
- Partition, offset, cursor, or committed record count.
- Output object/key and checksum.
- Code/model/algorithm version.
- Step status and timestamp.
- Fencing generation or worker lease.
- Counts of succeeded/failed records.
- Information needed to verify outputs before resuming.

Do not store secrets, access tokens, or unnecessary personal data in checkpoints.

### Committing Outputs and Checkpoints in Safe Order

A common mistake is updating the checkpoint before outputs are durably written. If the instance stops after checkpointing, the next worker may skip nonexistent outputs.

Conversely, if outputs are written before the checkpoint updates, a worker may recreate outputs. Use one of these approaches:

- Write outputs to deterministic keys with safe overwrite semantics.
- Write immutable objects per attempt/step and commit a manifest pointing to verified outputs.
- Write outputs and checkpoints in the same transaction if in the same database.
- Use `PREPARED`/`COMMITTED` states to finalize or clean up uncommitted outputs.
- Use checksums and versions to verify outputs before continuing.

### Batch Manifest Example

~~~json
{
  "job_id": "etl-2026-11-22",
  "input_version": "dataset-v17",
  "pipeline_version": "3.2.1",
  "completed_partitions": [0, 1, 2, 3],
  "outputs": {
    "0": "s3://result/etl-2026-11-22/part-000",
    "1": "s3://result/etl-2026-11-22/part-001"
  },
  "status": "RUNNING"
}
~~~

This is an illustrative manifest. In production, manifest updates require conditional writes/version checks so two workers do not overwrite each other's progress. Mark a partition complete only after its output is written and verified.

## 10. Designing Splittable and Resumable Jobs

Interruptible compute suits workloads that can be broken into independent units or frequently checkpointed.

### Batch Processing

Split datasets into partitions with stable IDs. Each partition is processed independently with deterministic output keys. If a worker stops, uncommitted partitions can be reassigned.

### MapReduce and Fan-Out / Fan-In

Map tasks process data slices and write independent outputs. Reduce reads only committed outputs listed in the manifest. Never use random filenames as proof of completion; use manifests, checksums, and task states.

### Render / Transcode

Split media into segments or stages. Each segment has an input version and output key. If a segment already finished, another worker can verify its checksum and skip it.

### Machine Learning

Save model checkpoints, optimizer state, learning rate scheduler, random seed, and dataset position by version. On resume, confirm checkpoint compatibility with current code, framework, and hardware. Do not save only model weights if optimizer state is needed to resume optimization accurately.

### Crawling or Pagination

Save cursors or page tokens only after all page records are durably persisted. If the cursor updates before writing records, data can be skipped. If records write before the cursor updates, the page may rerun; consumers must dedup by record/business key.

## 11. Handling Interruption Notices

Some services emit a signal or event before reclaiming an instance. Mechanisms include metadata/event endpoints, notifications, lifecycle hooks, OS signals, or orchestrator events. Lead times and firing conditions vary; never assume every reclamation gives ample warning.

### Goals of an Interruption Handler

Upon receiving a signal:

1. Mark the worker as draining.
2. Stop polling the queue or accepting new messages.
3. Stop claiming new jobs or stop renewing leases if work cannot finish.
4. Complete small, safely committable units of work.
5. Write a durable checkpoint.
6. Flush required outputs and metadata.
7. Release or allow leases on incomplete work to expire.
8. Close connections and exit before the deadline if time remains.

Interruption handlers must run fast and stay time-bounded. Do not perform full volume backups, huge data uploads, or long transactions inside a short warning window.

### Graceful Shutdown Is Not Guaranteed

Instances can suffer sudden termination, kernel panics, or network loss before handlers finish. Therefore:

- Checkpoint periodically while jobs run.
- Commit in small batches.
- Persist progress to independent storage.
- Keep operations idempotent.
- Use leases/visibility timeouts so jobs can be reassigned.
- Test scenarios where no interruption notice arrives.

### Interruption Handler Pseudocode

~~~python
def on_interruption():
    worker_state.mark_draining()
    queue.stop_receiving_new_messages()

    for task in active_tasks():
        if task.can_finish_within_shutdown_budget():
            task.finish_current_atomic_step()
        else:
            task.persist_checkpoint()
            task.release_or_allow_lease_expiry()

    flush_telemetry_with_timeout()
    close_connections()
~~~

This pseudocode illustrates execution order. Checkpoint functions must persist durably with appropriate conditional updates/fencing; never merely update RAM variables or ephemeral files and consider state saved.

## 12. Queue Leases, Visibility Timeouts, and Worker Ownership

Queues typically hand a message to a worker for a bounded window. Depending on the platform, this mechanism is called visibility timeout, message lock, or lease.

### Lease Too Short

If normal processing exceeds the lease and the worker fails to renew, the queue may deliver the same message to a second worker while the first is still running. Both workers can produce concurrent side effects.

### Lease Too Long

If a worker dies, the message waits a long time before redelivery. Job RTO rises and the queue holds unacknowledged messages unnecessarily.

### How to Design It

- Choose the initial lease based on real processing times and service limits.
- Renew the lease while the worker makes progress and still holds ownership.
- Stop processing if lease renewal fails or ownership expires.
- Ack only after results and checkpoints commit.
- Use idempotency to handle redeliveries.
- Use fencing tokens/generations if stale workers can keep running after lease transfer.

### Fencing Tokens

Each time a worker acquires processing ownership of a job, the system issues an incrementing generation. Storage accepts writes only from the latest generation. If an old worker wakes up after its lease expired, its stale token is rejected.

Example:

- Worker A receives lease generation 7.
- A pauses longer than the lease duration.
- Worker B receives a new lease generation 8.
- B writes a checkpoint with generation 8.
- A resumes and attempts to write with generation 7.
- Storage rejects A's write because generation is already 8.

Fencing must be enforced at the state store or side-effect target. Checking leases only inside the worker is insufficient if stale workers can still send requests after losing ownership.

## 13. Controlled Retries and Error Classification

Not every error should be retried. Retrying permanent errors wastes capacity and loads dependencies.

### Error Classification

| Error class | Example | Action |
|---|---|---|
| Transient | Network timeout, temporary throttling, service unavailable | Retry with backoff and jitter |
| Interruption/preemption | Instance receives reclamation signal | Checkpoint, release lease, or let queue redeliver |
| Permanent input | Malformed file, invalid schema | Mark failed/quarantine; do not retry infinitely |
| Business rejection | Order ineligible | Record business outcome and finish |
| Dependency configuration | Bad credentials, endpoint, or permissions | Fail fast, alert, and fix configuration |
| Unknown outcome | External request timed out with unclear execution status | Query via reference/idempotency key before retrying |

### Exponential Backoff and Jitter

Exponential retries ease pressure on failing dependencies. Random jitter prevents workers from retrying in synchronized bursts.

Example formula:

~~~text
delay = random(0, min(max_delay, base_delay * 2^attempt))
~~~

Include:

- Maximum retry count or overall deadline.
- Per-attempt timeout.
- Backoff with jitter.
- Retry concurrency limits.
- Dead-letter queue or investigation state.
- Metrics for retry counts and job age.
- Idempotency in both consumers and side effects.

Never configure infinite retries for payments, emails, or external APIs without reconciliation. If it is unclear whether a request succeeded, query status before resending.

## 14. Idempotent Worker Implementation Example

A worker processes jobs that generate object thumbnails. Each job contains an object key, object version, and transformation version. Outputs are written to keys derived from those components.

### Constructing the Idempotency Key

~~~python
def make_key(tenant_id, job_id, input_version, transform_version):
    return (
        f"{tenant_id}:{job_id}:thumbnail:"
        f"{input_version}:{transform_version}"
    )
~~~

All retries of the same job and input/transform version must use the same key. If the algorithm changes, a new version creates a distinct logical operation.

### Conceptual Processing Flow

~~~python
def process_thumbnail(job):
    key = make_key(
        job.tenant_id,
        job.job_id,
        job.input_version,
        job.transform_version,
    )

    record = idempotency_store.claim_or_read(key, job.payload_hash)

    if record.status == "COMPLETED":
        return record.result_ref

    if not record.lease_is_owned_by_current_worker:
        raise RetryLater()

    source = object_store.get(
        job.input_key,
        version=job.input_version,
    )

    thumbnail = transform(source, job.transform_version)

    output_key = f"thumbnails/{key}.webp"
    checksum = object_store.put_if_absent_or_verify(
        output_key,
        thumbnail,
    )

    result = {
        "output_key": output_key,
        "checksum": checksum,
    }

    idempotency_store.commit_completed(
        key=key,
        result=result,
        fencing_token=record.fencing_token,
    )

    return result
~~~

This is pseudocode. In real implementations, claiming must be atomic; committing must validate the fencing token; object writes need conditional semantics or checksum verification; and `COMPLETED` records must be written only after outputs are durable.

### Why Deterministic Output Keys?

If each attempt generates a random filename, retries can produce multiple thumbnails for the same input. Deterministic keys let workers identify which output belongs to which logical operation. If the object store lacks desired create-if-absent or conditional write semantics, use versioning/manifests and a separate commit workflow.

## 15. SQL Example: Safe Job Claiming and Completion

A job table can track status, leases, and generations:

~~~sql
CREATE TABLE job_steps (
    job_id          VARCHAR(120) NOT NULL,
    step_name       VARCHAR(100) NOT NULL,
    input_version   VARCHAR(120) NOT NULL,
    status          VARCHAR(30) NOT NULL,
    lease_owner     VARCHAR(120),
    lease_until     TIMESTAMP,
    fencing_token   BIGINT NOT NULL DEFAULT 0,
    checkpoint_ref  VARCHAR(500),
    result_ref      VARCHAR(500),
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (job_id, step_name, input_version)
);
~~~

Workers must claim jobs atomically, such as via a transaction with row locks or a conditional update:

~~~sql
UPDATE job_steps
SET lease_owner = :worker_id,
    lease_until = :new_lease_until,
    fencing_token = fencing_token + 1,
    status = 'RUNNING',
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND step_name = :step_name
  AND input_version = :input_version
  AND (
      status IN ('PENDING', 'RETRYABLE')
      OR lease_until < CURRENT_TIMESTAMP
  );
~~~

In practice, the worker must check the affected row count. If zero rows updated, the worker failed to claim. After claiming, read the new generation and pass it on all checkpoint/commit updates.

Checkpoint updates must validate owner and generation:

~~~sql
UPDATE job_steps
SET checkpoint_ref = :checkpoint_ref,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND step_name = :step_name
  AND input_version = :input_version
  AND lease_owner = :worker_id
  AND fencing_token = :fencing_token
  AND status = 'RUNNING';
~~~

If zero rows update, the worker lost ownership or status changed; it must halt further side effects and avoid overwriting newer progress.

SQL locking syntax, timestamps, and transaction isolation vary across database engines. Implement for your target database and test race conditions under concurrency.

## 16. Calculating Checkpoint Intervals

Checkpointing too infrequently increases rework; checkpointing too frequently creates write overhead and storage/database load.

Suppose:

- Time between checkpoints is `C`.
- Cost to create a checkpoint is `S`.
- Interruption rate per unit time is `λ`.
- Work runs continuously at a steady rate.

An approximate overhead model:

- Checkpoint overhead is proportional to `S/C`.
- Expected lost work from interruptions is proportional to `λ × C/2`.

Use this simple model as a starting point for experimentation; do not treat it as an exact universal optimum for every workload. Real interruption intervals may not be uniformly distributed, checkpoint costs can vary, and jobs can have multiple phases.

Practical rules:

- For long jobs, checkpoint at reproducible batch/partition boundaries.
- For ML training, consider step-based or time-based checkpoints.
- For file processing, checkpoint after each committed object or segment.
- For short transactions, commit individual transactions rather than adding overly frequent separate checkpoints.
- Measure checkpoint duration, restore time, and rework volume.
- Verify checkpointing does not degrade latency for other critical workloads.

## 17. Selecting Workloads for Interruptible Compute

Not every workload belongs on interruptible compute.

### Suitable

- Partitionable batch analytics.
- Job-based rendering, transcoding, and image processing.
- CI builds/tests with recreatable artifacts and caches.
- Simulations or Monte Carlo runs with independent tasks.
- ML training with full checkpoints.
- Queue workers processing idempotent messages.
- Data processing with cursors/checkpoints and clear output commits.

### Caution or Avoidance Without Additional Design

- Database primaries or systems storing sole state on local disk.
- Jobs with unverifiable or non-compensatable side effects.
- Synchronous tasks with very tight deadlines and no replacement capacity.
- Licenses or software disallowing frequent instance changes.
- Workloads holding long-lived connections without reconnect/resume.
- Uncheckpointable tasks with prohibitively high rerun costs.
- Services needing steady capacity with no on-demand fallback.

### Hybrid Architecture

A common pattern keeps the control plane and stateful dependencies on stable capacity while running independent job workers on interruptible capacity. Queues and databases coordinate work; workers can be reclaimed without losing the source of truth.

## 18. Testing Idempotency and Interruptions

Idempotent design cannot be verified merely by running a job once successfully. Intentionally inject interruptions at points prone to duplicate side effects.

### Fault Injection Points

- Before creating the idempotency record.
- After claiming the lease but before processing.
- After reading input but before writing output.
- After writing output but before checkpointing.
- After checkpointing but before acking.
- After database commit but before returning response.
- After calling an external API but before saving the result.
- When a lease expires while the old worker is still running.
- When two workers receive the same job near-simultaneously.

### Test Matrix

| Scenario | How to test | Pass criterion |
|---|---|---|
| Retry same key | Re-submit the same operation multiple times | Only one business outcome occurs |
| Same key, different payload | Modify payload while keeping key | Rejected or flagged as conflict; never silently misapplied |
| Worker dies before commit | Kill process before transaction commit | Job is reassigned and processed normally |
| Worker dies after commit, before ack | Stop process after commit | Redelivery detects `COMPLETED` and skips duplicate side effects |
| Two concurrent workers | Assign same job to two workers | Only one worker holds valid lease or commits |
| Lease expiration | Pause worker A and let B take over | Fencing rejects writes from A |
| Output written, checkpoint missing | Stop between the two operations | Retry verifies output and finalizes manifest safely |
| Stale checkpoint | Restore from an earlier checkpoint | Reruns only uncommitted parts without dropping data |
| Interruption notice | Send stop signal mid-job | Worker drains, checkpoints, and releases lease within budget |
| Missing notice | Terminate abruptly | Queue/checkpoints recover without relying on shutdown hooks |
| Dependency timeout | Force external API timeout after receipt | Queries status or retries with the same idempotency key |
| DLQ | Trigger permanent error | Message is quarantined for controlled investigation/replay |

### Acceptance Criteria

- One logical operation produces exactly one business effect within guaranteed scope.
- Jobs can rerun after interruptions at any tested point.
- No checkpoint points to uncommitted outputs.
- Workers losing their lease cannot overwrite newer state.
- Retries are bounded and avoid retry storms.
- Poison messages do not block queues indefinitely.
- Checkpoint RPO and recovery times meet targets.
- Rework cost after interruptions stays within acceptable limits.

## 19. Observability and Operations

To know whether interruptible workloads are safe and cost-effective, monitor both job lifecycles and interruptions.

Useful metrics:

- Interruptions by instance type, capacity pool, and region.
- Advance warning lead times when provided by the platform.
- Retried jobs, redeliveries, and average attempts.
- First-attempt completion rate vs. post-retry completion rate.
- Checkpoint frequency, duration, size, and failure rate.
- Time to resume from checkpoint.
- Rework volume after each interruption.
- Idempotency hits, duplicates suppressed, and payload conflicts.
- Lease expirations, fencing rejections, and worker overlaps.
- Queue depth, oldest message age, and DLQ counts.
- Rate of side-effect conflicts or reconciliations needing manual intervention.
- Cost per successful job and wasted compute time.

Logs should include job ID, step ID, attempt, input version, hashed idempotency key or safe reference ID, checkpoint version, and worker ID. Never log tokens, session cookies, secrets, or sensitive data.

Dashboards should distinguish:
- Permanently failed jobs.
- Jobs currently retrying.
- Interrupted jobs awaiting resumption.
- Completed jobs with unacked messages.
- Jobs blocked by leases or fencing.
- Jobs awaiting reconciliation due to unknown external outcomes.

### Runbook When Interruption Rate Spikes

1. Identify affected capacity pools, regions, and instance types.
2. Check interruption rate and observed notice windows.
3. Review queue age, retry rate, checkpoint restore time, and DLQ depth.
4. Verify new workers have replacement capacity.
5. Inspect duplicate side effects, idempotency conflicts, and lease expirations.
6. If needed, shift deadline-sensitive load onto stable capacity.
7. Tune batch sizes / checkpoint intervals based on measured data.
8. Record rework costs and update capacity selection policies.

## 20. Common Mistakes

**Generating a new idempotency key per retry.** The system cannot recognize attempts as belonging to the same operation. Keys must derive from stable business identifiers and be stored with the job.

**Acking messages before writing durable results.** A worker stopped after acking can lose the job. Commit results/checkpoints first, then ack.

**Writing checkpoints before outputs exist.** New workers may skip unwritten outputs. Commit outputs first or use manifests/transactions to coordinate.

**Assuming an at-least-once queue prevents duplicates automatically.** Queues can redeliver; consumers must deduplicate and stay idempotent.

**Using distributed locks without fencing.** Old workers can continue after lease expiration. State stores must reject stale generations.

**Retrying every payment API timeout blindly.** The request may have succeeded while the response was lost. Query status or use the target service's idempotency keys.

**Checkpointing too frequently.** Storage and databases can become bottlenecks. Measure checkpoint cost and pick sensible batch boundaries.

**Handling interruptions only in shutdown hooks.** Instances can vanish without hooks executing. Periodic checkpoints and idempotency are the primary defense.

**Using local ephemeral disk as the sole checkpoint store.** When the instance is reclaimed, checkpoints vanish too. Persist to a database, object storage, or durable service.

**Not testing concurrent worker execution.** Lease expirations or redeliveries can create overlaps. Test atomic claims, fencing, and commit conflicts.

**Assuming queues alone provide exactly-once across all systems.** Cross-service side effects need idempotency, transactions/outboxes, and reconciliation at every boundary.

## 21. Idempotent Task Design Checklist

### Work Definition

- [ ] Jobs and individual steps have stable IDs.
- [ ] Input versions and algorithm versions are tracked.
- [ ] Batch/partition/checkpoint boundaries are appropriate.
- [ ] Source of truth lives outside the instance lifecycle.
- [ ] Local disk holds only recreatable or temporary data.

### Idempotency and Side Effects

- [ ] Idempotency keys remain invariant across retries.
- [ ] Keys have clear scope, retention, and payload hashes.
- [ ] Databases enforce unique constraints or atomic claiming.
- [ ] Results and `COMPLETED` status commit in the same transaction when possible.
- [ ] External APIs use idempotency keys or reconciliation.
- [ ] Event publishing uses an outbox; consumers use an inbox/dedup.
- [ ] Compensations are also idempotent.

### Checkpoints and Worker Lifecycle

- [ ] Checkpoints are written to durable storage.
- [ ] Outputs are written/verified before marking checkpoints complete.
- [ ] Leases have appropriate timeouts and renewals.
- [ ] Fencing tokens block stale workers from writing after losing ownership.
- [ ] Interruption handlers stop accepting new jobs and checkpoint within budget.
- [ ] Data integrity does not depend on shutdown hooks running.
- [ ] Acknowledgements happen only after commit.

### Retries and Testing

- [ ] Transient, permanent, and unknown-outcome errors are classified.
- [ ] Retries use exponential backoff, jitter, timeouts, and caps.
- [ ] DLQ and replay procedures exist.
- [ ] Tested same-key retries, payload conflicts, and worker concurrency.
- [ ] Tested interruptions before/after output, checkpoint, commit, and ack.
- [ ] Tested missing interruption notices.
- [ ] Metrics cover interruptions, retries, checkpoints, duplicates, and cost per successful job.

## 22. Self-Check

1. Why must workers on interruptible compute assume a job can be delivered multiple times?
2. How does idempotency differ from deduplication and checkpointing?
3. Why does generating a new UUID per attempt defeat idempotency?
4. A worker commits to the database successfully but is reclaimed before acknowledgement. What must the redelivery handle?
5. Why does at-least-once delivery not automatically guarantee an exactly-once business effect?
6. When output has been written but the checkpoint has not updated, what should a retry verify?
7. What two different problems do leases and fencing tokens solve?
8. Why is a timeout calling a payment API insufficient to conclude the transaction failed?
9. What should an interruption handler do during a short warning window, and what must happen periodically beforehand?
10. How do you choose a checkpoint interval that balances progress-saving cost against rework volume?
11. Which fault injection points are needed to test idempotent tasks?
12. Design a batch-processing worker that can be terminated abruptly without creating duplicate records or skipping partitions.

Idempotent design turns interruptions from an exceptional failure into a normal lifecycle condition of compute. When jobs have stable identities, side effects are guarded by transactions or idempotency keys, progress is durably checkpointed, workers carry leases/fencing, and retries are bounded, instances can be reclaimed and replaced while work continues safely.
