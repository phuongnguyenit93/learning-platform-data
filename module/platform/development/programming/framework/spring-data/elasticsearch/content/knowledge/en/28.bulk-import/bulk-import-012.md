# Completeness Checks, Error Reconciliation, and Resuming After Interruption

An Elasticsearch ingestion pipeline typically reads data from files, databases, message queues, or source systems and sends batches of documents using the Bulk API. A single bulk request can carry many operations, yet Elasticsearch does not execute the entire request as a transaction. Some documents can succeed while other documents fail.

Therefore, reliable ingestion requires three capabilities: **counting and reconciling data**, **classifying and handling per-item errors**, and **resuming from checkpoints after process interruption**. Checking only the HTTP status of a bulk request or merely recording that a batch was sent can cause the application to miss errors, ingest duplicates, or lose track of which portion needs rerunning.

This lesson shows how to structure a bulk pipeline in Spring Data Elasticsearch: accounting for input counts, checking per-document outcomes, persisting batch states, retrying transient errors, routing non-recoverable errors to dedicated handling, and resuming safely after timeouts or restarts.

## 1. A Bulk Request Is Not a Transaction

The Bulk API bundles multiple index, create, update, or delete operations into one request to lower network overhead and increase throughput. Elasticsearch executes each operation inside the bulk independently.

Example batch of 100 documents:

- 92 documents indexed successfully.
- 5 documents failed mapping or data validation.
- 2 documents hit version conflicts.
- 1 document was temporarily rejected due to cluster load.

A bulk request can return an overall successful HTTP response while still containing failed items. The response carries per-operation details alongside a summary flag indicating whether errors occurred.

This yields two rules:

1. Never treat an HTTP-level success on a bulk request as proof that every document was written.
2. Never resend the entire batch just because one item failed if other items succeeded and the operations are not idempotent.

A bulk request has no full rollback. The application must reconcile and handle each item individually.

## 2. Defining Data Completeness

Before running an import, define the exact expected dataset. The number of rows in an input file does not always equal the number of documents to index.

Example file with 10,000 rows:

- 9,850 rows are valid and indexed.
- 100 rows are filtered out by business rules.
- 30 rows share duplicate source keys and are merged.
- 20 rows lack required fields and must be reported as errors.

Comparing only the succeeded index count against 10,000 fails to explain the discrepancy.

A reconciliation model should distinguish these counts:

| Metric | Meaning |
|---|---|
| `sourceRead` | Records read from the source |
| `accepted` | Records passing validation and accepted for processing |
| `rejected` | Records rejected due to validation or business rules |
| `duplicate` | Duplicate records under business key rules |
| `attempted` | Operations actually submitted to Elasticsearch |
| `succeeded` | Operations confirmed successful by Elasticsearch |
| `noop` | Operations making no document change, where operation semantics produce no-ops |
| `failed` | Operations that failed |
| `retryPending` | Operations awaiting retry |
| `deadLetter` | Operations that exhausted retries or require manual handling |

These categories must be mutually exclusive or follow clear summation rules. For instance, `rejected` may be a subset of `sourceRead`, while `succeeded + failed + retryPending` reconciles against `attempted` after processing the batch response.

### Defining a Reconciliation Key

Every source record should carry a deterministic identifier such as a source ID, business key, or event ID. Never rely on array positions inside a re-sorted list as a long-lived identifier.

A ledger record might contain:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "sourceId": "ERP-P-100",
  "targetId": "P-100",
  "sourceVersion": 42,
  "status": "SUCCEEDED",
  "attempts": 1,
  "lastError": null
}
~~~

A ledger lets you see which records were processed, which were rejected, and which need retry. For large sources, store the ledger in a database or suitable durable store rather than a local log file.

## 3. Splitting Data into Batches with Clear Boundaries

Do not build one bulk request containing the entire import dataset. Smaller batches bound payloads, memory, processing times, and recovery scope on failures.

Each batch should track:

- Job ID or run ID.
- Unique batch ID within the job.
- Source range, offset, page token, or partition.
- List of source IDs.
- Input, accepted, and rejected record counts.
- Submission status and reconciliation status.
- Start time, end time, and attempt number.

Example batch manifest:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "batchId": "partition-02-offset-5000",
  "sourcePartition": "02",
  "startOffset": 5000,
  "endOffsetExclusive": 6000,
  "recordCount": 1000,
  "status": "PENDING"
}
~~~

Batching by document count is simple, yet watch byte size. Documents with large content can make requests heavy even at low document counts.

Choose batch size by measuring real data. Track payload bytes, bulk duration, heap, CPU, error rates, and cluster load. No single fixed count fits every mapping and workload.

## 4. Reading Per-Item Results from the Bulk API

A bulk response contains an overall status and an `items` list ordered to match the operations in the request. Each item reports operation type, ID, status, result, or error details.

Abbreviated response example:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-101",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [price]"
        }
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-102",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    }
  ]
}
~~~

In this example:

- `P-100` was created successfully.
- `P-101` failed because data violated the mapping.
- `P-102` was temporarily rejected because the cluster was overloaded.

The `errors` flag indicates at least one item failed. It does not mean every item failed or that the whole request should be retried.

### Correlating Responses with Input

The Bulk API returns items in request operation order. When building a bulk request, maintain a parallel metadata list alongside the operations to correlate each response item back to its source record:

~~~java
record PendingItem(
    String sourceId,
    String targetId,
    int sourcePosition
) {}
~~~

When the response arrives, pair each item with the metadata entry at the same position. Never guess the source record solely from error messages or log order.

If a request mixes multiple operation types, keep the operation type in metadata as well. An `index`, `update`, `delete`, or `create` item can have distinct success semantics.

### Do Not Merely Count Response Items

The number of items in the response must equal the number of submitted operations. If counts mismatch, do not mark the batch complete. Log a protocol/response anomaly, keep the batch in a reconciliation-needed state, and investigate.

A valid response can mix item successes and item failures. Count each status separately and save the list of failed items.

## 5. Bulk Operations in Spring Data Elasticsearch

Spring Data Elasticsearch provides bulk operations through `ElasticsearchOperations`. For index operations, build a list of `IndexQuery`:

~~~java
List<IndexQuery> queries = products.stream()
    .map(product -> new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build())
    .toList();

List<IndexedObjectInformation> indexed =
    operations.bulkIndex(
        queries,
        IndexCoordinates.of("products")
    );
~~~

This pattern is common in Spring Data Elasticsearch. Overloads, `BulkOptions`, and return types can vary across release trains. Verify your project's dependencies and exact APIs.

Spring Data converts entities to documents using configured mappings/converters. However, for strict per-item reconciliation, understand how your version represents failures. Some APIs throw an exception carrying bulk failure details instead of returning a complete list of item outcomes.

### When Explicit Item-Level Responses Are Needed

The Elasticsearch Java API Client returns `BulkResponse` with the full item list. Illustrative example:

~~~java
BulkResponse response = elasticsearchClient.bulk(bulk -> bulk
    .index("products")
    .operations(operation -> operation.index(index -> index
        .id("P-100")
        .document(product)
    ))
    .operations(operation -> operation.index(index -> index
        .id("P-101")
        .document(anotherProduct)
    ))
);

if (response.errors()) {
    for (int i = 0; i < response.items().size(); i++) {
        BulkResponseItem item = response.items().get(i);

        if (item.error() != null) {
            // Correlate item with input metadata at the same position.
        }
    }
}
~~~

Builder syntax and generic document mapping depend on the Elasticsearch Java API Client version. This example highlights reading the response: check `errors`, loop over every item, and match each item back to its source record.

If the application uses Spring Data `Operations` for most tasks, you can keep bulk calls on `Operations` and build an adapter normalizing results or exceptions into a unified internal model.

### Normalizing Bulk Outcomes

An internal outcome model decouples orchestration from specific client APIs:

~~~java
enum ItemOutcome {
    SUCCEEDED,
    NOOP,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE
}

record BulkItemOutcome(
    String sourceId,
    String targetId,
    ItemOutcome outcome,
    Integer status,
    String errorType,
    String errorReason
) {}
~~~

The adapter converts `BulkResponse` or Spring Data exceptions into a `List<BulkItemOutcome>`. Higher-level services then operate solely on normalized states.

## 6. Classifying Errors to Decide Retries

Not every error can be fixed by resending the same request. Classify errors before retrying:

| Error Type | Example | Handling Approach |
|---|---|---|
| Data/mapping | 400, parse exception, wrong field type | Fix data or mapping; do not retry blindly |
| Authentication/authorization | 401, 403 | Stop job and fix permissions/configuration |
| Missing index or resource | 404, index not yet created | Check provisioning and target |
| Overload/transient | 429, certain 502/503 | Retry with backoff |
| Timeout/connection drop | Unknown whether request applied | Reconcile or replay idempotently |
| Version conflict | 409 | Re-read and handle per concurrency policy |
| Payload too large | Request rejected due to size | Shrink batch or document size |

Status code is just one signal. Read `error.type`, `error.reason`, and operation semantics. For instance, a 409 on `create` means the document ID already exists; depending on business rules, that can be a duplicate error or an acceptable outcome during idempotent import.

### Bounded Retries and Backoff

For transient errors, use exponential backoff with jitter:

~~~text
attempt 1: wait ~0.5 seconds
attempt 2: wait ~1 second
attempt 3: wait ~2 seconds
attempt 4: wait ~4 seconds
...
~~~

These delays are illustrative only. Configure base delay, max delay, max retries, and total timeout according to your SLAs. Jitter prevents workers from retrying simultaneously.

Never retry indefinitely. Once attempts are exhausted, transition the record to dead-letter or manual review along with source reference and last error.

### Retry Per Item, Not Whole Batches by Default

If a batch of 1,000 items has 990 successes, only the 10 transiently failed items belong in the retry queue. Resending all 1,000 wastes resources and can duplicate side effects if operations are non-idempotent.

If the system cannot determine which items succeeded because the request timed out before receiving a response, execute a safe replay and reconcile afterward. That is distinct from responses that clearly report per-item results.

## 7. Idempotency When Replaying Data

An import may be replayed because:

- The process crashed after Elasticsearch wrote data yet before the checkpoint persisted.
- The client timed out without knowing if the bulk finished.
- An operator re-ran the job.
- A message queue redelivered a message.
- Retries ran after a worker restart.

For safe replay, define what re-processing the exact same source record produces.

### Using Deterministic Target IDs

If each source record always maps to the exact same Elasticsearch document ID, an `index` operation with the same ID and content can be replayed without creating extra documents:

~~~java
IndexQuery query = new IndexQueryBuilder()
    .withId(sourceRecord.getBusinessId())
    .withObject(product)
    .build();
~~~

If each run generates a random ID, replays create duplicate documents.

### Distinguishing `index`, `create`, and `update`

| Operation | On Replay | Risk / Meaning |
|---|---|---|
| `index` same ID | Overwrites document with submitted content | Often fits snapshot sync when payload is deterministic |
| `create` same ID | Subsequent run may return conflict since ID exists | Useful for detecting duplicates |
| `update` setting fixed values | Can be safe when assigning identical values | Depends on script and payload |
| `update` incrementing | Each replay can increment again | Not idempotent without deduplication |
| Scripted append | Can append duplicates unless guarded | Must check uniqueness or event ID |
| `delete` same ID | Deletes first time; subsequent runs depend on `not_found` semantics | Decide if `not_found` counts as success or error |

A counter-increment script does not become idempotent simply because Elasticsearch executes the update atomically. Atomicity of a single update and idempotency across multiple deliveries are two separate properties.

### Versioning and Data Ordering

If the source provides monotonically increasing versions, store the source version on the document and reject stale data overwriting newer data. Elasticsearch supports external versioning in the Index API; configuration details depend on your API.

Another approach is storing `sourceUpdatedAt` or `sourceVersion` in the document and using a script to check version before applying updates. If events arrive out of order, accept only newer events per defined rules.

Never use worker wall-clock timestamps as the version if the upstream data source defines business order.

## 8. What Is a Checkpoint and Where Should It Be Stored?

A checkpoint records progress so a job can resume after a restart. It must survive process restarts and be updated strictly based on reconciled outcomes.

Example checkpoint:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "partition": "02",
  "lastCommittedOffset": 5999,
  "lastCommittedBatchId": "partition-02-offset-5000",
  "status": "RUNNING",
  "updatedAt": "2026-11-13T10:30:00Z"
}
~~~

Checkpoints can be stored in:

- A relational database if the system already maintains job tables.
- A durable key-value store.
- Message broker offsets when reading from Kafka or similar systems.
- Durable object storage/manifests for partitioned file imports.
- A dedicated job-tracking index if appropriate, recognizing Elasticsearch is not a cross-system transactional coordinator for both source and target.

Never store checkpoints only in an in-memory variable or ephemeral local file on a worker if jobs must recover across host replacements.

### Checkpoints Must Reflect Confirmed Progress

Do not write a checkpoint saying "processed up to offset 10,000" right after reading from the source. Commit progress only once every record in that range has a durably recorded outcome:

- Succeeded.
- Rejected by validation with a recorded reason.
- Persisted into a durable retry/dead-letter store.
- Or another terminal state accepted by job policy.

If a failed record has not yet been durably saved for follow-up handling, never advance the checkpoint past it.

## 9. Safe Processing Sequence for a Batch

A common execution sequence:

~~~text
Read source range
      |
      v
Validate and normalize
      |
      +----> Rejected records -> save validation errors
      |
      v
Build bulk operations and metadata
      |
      v
Send bulk request
      |
      v
Inspect per-item outcomes
      |
      +----> Success / Noop -> record success status
      |
      +----> Retryable -> persist to retry queue
      |
      +----> Permanent -> persist to dead-letter/error store
      |
      v
Reconcile counts and save batch result
      |
      v
Commit checkpoint
~~~

This order prevents advancing the checkpoint before knowing batch outcomes. Persisting item outcomes and committing the checkpoint should be structured so a crash between steps leaves no unrecoverable gap.

### Crashes Between Elasticsearch and the Checkpoint Store

Elasticsearch and the checkpoint database usually do not share a distributed transaction. Consider this sequence:

1. Elasticsearch writes succeed.
2. Process crashes before the checkpoint database commits.
3. On restart, the uncommitted source range is read again.

This is why idempotency matters. When replaying with the same ID and same payload is safe, the job can resend the uncommitted range and re-verify states.

For non-idempotent operations, maintain a durable deduplication ledger or event ID log so you know whether an event was already applied. No standalone checkpoint creates exactly-once semantics across two independent systems.

## 10. Resuming After Interruption by Source Type

How a job resumes depends on the data source.

### CSV or JSONL Files

Files can be split into ranges by byte offset or record number. However, byte offsets are safe only when parsers can start cleanly at record boundaries. With CSV containing quoted newlines, you cannot arbitrarily seek by physical line breaks.

Options:

- Pre-build a manifest containing valid byte/record ranges before importing.
- Split huge files into independent part files.
- Persist read record counts and parser state if format permits.
- Write failed record source IDs to an error file/queue.
- On resume, read from the checkpoint or replay a partition safely.

For compressed streams, seeking may be impossible; either split files beforehand or replay from the start using deterministic target IDs.

### Databases

Use keyset pagination over a stable key or ordered key pair:

~~~sql
SELECT id, name, price, updated_at
FROM products
WHERE id > :lastId
ORDER BY id
LIMIT :batchSize;
~~~

If the source mutates during the import, `lastId` alone can miss updates to earlier rows. You may need snapshots, `updated_at` + ID watermarks, change data capture, or a follow-up reconciliation sweep.

Avoid deep offset pagination on large, actively changing tables.

### Message Queues

For partition-offset queues, commit offsets only after the batch completes and outcomes are durably stored. When processing messages concurrently within one partition, never commit past a lower-offset message whose outcome is still pending.

Use a per-partition contiguous watermark: advance the watermark only across contiguous completed offsets. Higher offsets that finish early are tracked separately until earlier offsets complete.

### Paginated APIs

When a source API returns a continuation token, save the token alongside query parameters and job state. Tokens can expire or depend on server-side snapshots. When a token expires, have a strategy to restart the partition or reconcile by source ID.

Never synthesize tokens from page numbers when an API specifies opaque cursors.

## 11. Checkpointing Under Concurrent Execution

If multiple workers process independent batches, never update a single `lastOffset` variable on arbitrary completion order.

Example:

- Batch A handles offsets 0–999 and is still running.
- Batch B handles offsets 1000–1999 and finishes.
- Batch C handles offsets 2000–2999 and finishes.

If the checkpoint records 2999 before A finishes, a restart skips 0–999.

Two common solutions:

**Per-batch checkpointing:** each batch tracks its own state; resume by querying non-terminal batches. This is easy to reconcile and fits parallel execution well.

**Contiguous watermark:** track the highest offset for which every prior offset is complete. Once A finishes, the watermark jumps from -1 straight to 2999 if B and C are already complete.

For partitioned queues, manage watermarks independently per partition. Never share one offset across independent partitions.

## 12. Persisting Job and Batch States

A simple state model:

~~~text
PENDING
   |
   v
RUNNING
   |
   +----> SUCCEEDED
   |
   +----> COMPLETED_WITH_ERRORS
   |
   +----> RETRY_PENDING
   |
   +----> FAILED
   |
   +----> CANCELLED
~~~

Definitions to formalize in the application:

- **PENDING**: batch is planned, not yet sent.
- **RUNNING**: currently reading, validating, or sending bulk.
- **SUCCEEDED**: every record reached an accepted outcome with no unresolved errors.
- **COMPLETED_WITH_ERRORS**: batch finished, yet contains rejected or dead-lettered records per policy.
- **RETRY_PENDING**: transient failures remain awaiting retry.
- **FAILED**: job cannot continue due to configuration/infrastructure errors or exhausted retry policies.
- **CANCELLED**: operator stopped the job cleanly.

Do not mark a batch `SUCCEEDED` just because the request was sent. Require bulk outcomes and reconciliation.

### Separating Job State from Item State

A job can remain `RUNNING` even after some items enter dead-letter, provided policy allows continuing remaining batches. Similarly, a batch can finish while holding recorded rejected items.

Job status is an aggregate; item state is the fine-grained detail for resumption and reporting.

## 13. Persisting Errors and Dead-Letter Records

Each error record should preserve enough context for fixing or retrying:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "sourceId": "ERP-P-101",
  "targetId": "P-101",
  "batchId": "partition-02-offset-5000",
  "attempt": 3,
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "errorReason": "failed to parse field [price]",
  "payloadReference": "object://imports/job-123/records/ERP-P-101",
  "firstFailedAt": "2026-11-13T10:20:00Z",
  "lastFailedAt": "2026-11-13T10:25:00Z",
  "state": "DEAD_LETTER"
}
~~~

Store either the full payload or a secure storage reference. Avoid writing sensitive data into logs or dead-letter stores unnecessarily.

A good error record captures:

- Source ID and target ID.
- Job/batch/partition.
- Operation type.
- Attempt count.
- Status and error type.
- Normalized reason.
- Payload or payload reference.
- First failed and last failed timestamps.
- Retry/dead-letter state.
- Source version info if present.

A dead-letter queue is not a graveyard to forget errors. Establish workflows to review, fix data, replay under control, and close errors.

## 14. Resuming Jobs After a Worker Restart

On startup, the orchestration service should:

1. Find interrupted jobs left in `RUNNING` or `RETRY_PENDING`.
2. Load durable checkpoints and batch manifests.
3. Distinguish committed batches, in-progress batches, and unstarted batches.
4. Load unexpired retry items.
5. Verify target index/alias and mappings.
6. Resume from unfinished batches or replay uncommitted ranges per idempotency policy.
7. Record outcomes and update checkpoints.
8. Complete the job once every record reaches a terminal state per rules.

Never just see `RUNNING` and blindly rerun the entire job from scratch. Identify which batches succeeded, which have failed items, and which were never sent.

### Job Leases and Worker Ownership

When multiple instances can pick up the same job, use a lease/lock mechanism so only one worker owns a partition or batch at a time. Leases must have an expiration time and be renewed while the worker stays healthy.

When a worker dies, its lease expires so another worker can take over. Yet leases alone do not eliminate the chance of a paused worker waking up late. Combine leases with idempotency, fencing tokens, or job-state versioning to prevent stale workers from committing outdated state.

## 15. Reconciling After Job Completion

A job should only be declared complete once all counts reconcile cleanly.

Example report:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "sourceRead": 10000,
  "accepted": 9850,
  "rejected": 100,
  "duplicate": 50,
  "attempted": 9850,
  "succeeded": 9820,
  "noop": 0,
  "deadLetter": 30,
  "retryPending": 0,
  "status": "COMPLETED_WITH_ERRORS"
}
~~~

In this example, `accepted` is 9,850 records after subtracting `rejected` and `duplicate`. 9,820 succeeded and 30 landed in dead-letter; their sum equals `attempted`.

If duplicates are configured to update existing documents instead of being dropped, adjust how `accepted`/`attempted` are defined. What matters is keeping rules consistent and explainable.

### Count Reconciliation Alone Does Not Prove Data Accuracy

Two systems can have matching document counts while differing in content. When deeper validation is required, verify:

- Source IDs and target IDs.
- Source versions or updated timestamps.
- Canonicalized payload hashes.
- Counts grouped by partition/category.
- Critical business fields.
- Aggregated sums or checksums per group.

Never hash arbitrary JSON strings directly if field ordering, number formatting, timezones, or null/empty representations can vary. Canonicalize data before computing checksums.

### Inspecting the Index Post-Import

If the job must guarantee documents are searchable right after finishing, configure an appropriate refresh policy. Refresh establishes search visibility, not proof of per-item bulk success.

For large imports, defer refreshes during indexing and refresh once at the end when use case and index settings allow. Do not enable immediate refresh on every individual item.

## 16. `BulkProcessor` and Continuous Ingestion Pipelines

For continuous streams, you can use the Elasticsearch Java API Client's `BulkProcessor` (or your version's equivalent abstraction) to batch requests by:

- Operation count.
- Total payload size.
- Flush interval.
- Concurrent requests.

Configure bounded concurrency and memory limits. If producers read faster than Elasticsearch writes, the pipeline must apply backpressure or bounded queues rather than piling documents up in heap.

`BulkProcessor` listeners typically provide callbacks before and after each bulk request. After a success callback, still iterate item-level responses for individual operation failures. A request failure callback does not prove all items went unapplied; timeouts can leave outcomes uncertain.

### Flushing and Closing

On normal job shutdown:

1. Stop accepting new inputs.
2. Flush buffered operations.
3. Wait for in-flight bulk requests to complete.
4. Reconcile responses and retry queues.
5. Persist final checkpoints.
6. Close processor/client resources per application lifecycle.

On abnormal crashes, durable sources and persisted checkpoints must suffice to resume without relying on any in-heap buffers.

## 17. Backpressure and Throttling Import Pace

Adding workers or inflating batch sizes does not always increase throughput. Once Elasticsearch saturates, 429 rates climb, retries generate extra traffic, and jobs slow down further.

Monitor:

- Bulk latency p50/p95.
- Payload bytes per request.
- 429 and 5xx rates.
- Mapping/validation item error rates.
- Queue depth.
- Pending retries.
- Cluster CPU, heap, disk I/O, and indexing pressure.
- End-to-end time from source read to acknowledgement.

When 429 rates rise, lower concurrency or submission rate, add backoff, and ramp back up gently once the cluster stabilizes. Tune using metrics rather than pinning to maximum throughput.

## 18. Example Batch Import Orchestration in a Service

An orchestration service can cleanly separate source reading, bulk writing, reconciliation, and checkpointing:

~~~java
public BatchResult importBatch(SourceBatch batch) {
    ValidatedBatch validated = validator.validate(batch);

    errorStore.saveRejected(
        batch.jobId(),
        validated.rejectedRecords()
    );

    List<BulkItemOutcome> outcomes =
        bulkWriter.write(validated.acceptedRecords());

    reconciliation.verify(
        validated,
        outcomes
    );

    errorStore.saveFailures(
        outcomes.stream()
            .filter(outcome ->
                outcome.outcome() == ItemOutcome.RETRYABLE_FAILURE
                    || outcome.outcome() == ItemOutcome.PERMANENT_FAILURE)
            .toList()
    );

    checkpointStore.commitBatch(
        batch.jobId(),
        batch.batchId(),
        outcomes
    );

    return BatchResult.from(validated, outcomes);
}
~~~

This structure is illustrative and does not form a single atomic transaction. In production, persisting item outcomes and committing the batch must be recoverable if a crash happens between steps—for instance, using `PREPARED`/`RESULTS_RECORDED`/`COMMITTED` states or a uniquely keyed ledger table so replays never create inconsistent states.

### Separation of Responsibilities

- `SourceReader`: reads ranges or partitions and holds the source cursor.
- `Validator`: validates schemas and business rules.
- `BulkWriter`: converts records to operations and calls Elasticsearch.
- `OutcomeMapper`: translates responses/exceptions into per-item states.
- `RetryScheduler`: schedules retries for transient failures.
- `DeadLetterStore`: persists errors needing fixes or intervention.
- `ReconciliationService`: compares expected vs. actual counts.
- `CheckpointStore`: persists durable progress.
- `JobCoordinator`: manages leases, resumption, and job state.

Layering makes components independently testable and lets you swap Spring Data APIs without rewriting reconciliation logic.

## 19. Testing Failures and Resumability

An import pipeline cannot be tested on the happy path alone. Simulate failures across boundaries between source, Elasticsearch, and the checkpoint store.

| Scenario | Expected Verification |
|---|---|
| One item fails mapping inside a bulk | Failed item recorded; other items confirmed successful |
| One item returns 429 | Only the retryable item enters retry |
| Bulk response has `errors = true` | Job reads item list; does not mark the whole batch failed |
| Timeout before receiving response | Batch retains reconciliation-needed or idempotent-replay state |
| Crash after bulk success, before checkpoint | Restart replay creates no duplicates or double increments |
| Crash after saving retry, before checkpoint | Resume does not lose the retry record |
| Crash between two batches | Committed batch is skipped; uncommitted batch reruns |
| Concurrent workers | Checkpoint never advances past unfinished batches |
| Worker lease expires | New worker takes over safely |
| Retries exhausted | Record transitions to dead-letter |
| Source mutates during import | Snapshot/watermark or reconciliation detects discrepancies |
| Refresh has not occurred yet | Distinguish indexed items from search-visible items |

### Testing Reconciliation

Create a batch of 10 records:

- 7 valid records succeeding.
- 1 record failing mapping.
- 1 record hitting 429.
- 1 record rejected by validation.

Expectations:

- `sourceRead` = 10.
- `accepted` = 9.
- `rejected` = 1.
- `attempted` = 9.
- `succeeded` = 7.
- `retryPending` = 1.
- `deadLetter` = 1 if mapping error is classified permanent.

After fixing data and successfully retrying the 429 item, updated reports must reflect the final state and attempt history. Never double-count the same item in `succeeded` simply because it was submitted multiple times.

### Testing Crash Resumption

A test can simulate:

1. Read batch A.
2. Send bulk and receive some successes plus one retryable item.
3. Persist item outcomes.
4. Halt the process before committing the checkpoint.
5. Restart the job.
6. Replay batch A or recover from the ledger per design.
7. Verify successful documents were not duplicated, counters did not double-increment, and the retryable item was processed.
8. Commit the checkpoint once the batch holds durable outcomes.

This test verifies far more than simply asserting that a checkpoint method was called.

## 20. Common Import Pitfalls

| Symptom | Possible Cause | Fix |
|---|---|---|
| Job reports success yet documents are missing | Only checked HTTP status or ignored item errors | Reconcile per-item results and expected counts |
| Whole batch resent repeatedly | Did not persist per-item outcomes | Retry only failed items or replay idempotently |
| Duplicate documents after restart | Target ID is unstable | Use deterministic IDs/business keys |
| Counters incremented multiple times | Increment script replayed | Use event IDs/deduplication |
| Checkpoint skipped failed records | Committed by read offset instead of persisted outcome | Commit by batch or contiguous watermark |
| Mapping errors retried forever | Did not separate permanent from transient errors | Classify by error type/status |
| Cluster overloaded more after retries | Simultaneous retries without backoff | Exponential backoff with jitter and reduce concurrency |
| Bulk responses cannot match source | Metadata not saved in operation order | Store parallel source ID/target ID metadata |
| Total counts do not reconcile | Unclear definitions of rejected/duplicate/attempted | Standardize reconciliation formulas |
| Old worker overwrote new worker's checkpoint | Missing leases/fencing/versions | Use leases and fencing tokens |
| Search misses newly imported data | Refresh has not run | Define refresh policy and separate indexing from visibility |
| Dead-letter items go unhandled | Logged only, no replay workflow | Build a data-fix and controlled replay pipeline |

## 21. Bulk Import Operational Checklist

- [ ] Deterministic job IDs and batch IDs exist.
- [ ] Every source record has an ID for reconciliation.
- [ ] Clear definitions exist for `sourceRead`, `accepted`, `rejected`, `duplicate`, and `attempted`.
- [ ] Batches bound both document count and payload bytes.
- [ ] Metadata is preserved to match every response item to its source record.
- [ ] `errors` flag and every item in the bulk response are inspected.
- [ ] Errors are classified into permanent, retryable, and uncertain outcomes.
- [ ] Retries use attempt limits, backoff, and jitter.
- [ ] Whole batches are never retried when exact item successes are known.
- [ ] Deterministic target IDs and idempotent operations make replays safe.
- [ ] Durable ledgers, retry stores, or dead-letter stores exist.
- [ ] Checkpoints advance only after batch outcomes are durably recorded.
- [ ] Crashes between Elasticsearch writes and checkpoint commits are handled.
- [ ] Concurrent workers use per-batch checkpoints or contiguous watermarks.
- [ ] Leases/ownership prevent two workers from committing the same partition concurrently.
- [ ] Counts and, when needed, checksums/source versions are reconciled.
- [ ] Refresh policies match search visibility requirements.
- [ ] Latency, 429s, queue depth, and retry rates are monitored.
- [ ] Integration tests simulate item errors and mid-job restarts.

A reliable bulk pipeline does not end when a request is sent. It finishes only when every record has a recorded terminal state, input and output counts reconcile, failures are retried or persisted for resolution, and checkpoints point precisely to where work can resume. Combining item-level responses, deterministic IDs, idempotency, durable ledgers, and batch-level checkpoints lets jobs recover from timeouts or restarts without silently dropping or duplicating data.
