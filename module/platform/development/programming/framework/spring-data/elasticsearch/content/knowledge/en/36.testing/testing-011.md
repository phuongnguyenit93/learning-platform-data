# Testing Partial Bulk Failures, Retries, and Idempotency

The Bulk API lets you send multiple index, create, update, or delete operations in a single request to reduce network overhead and boost throughput. However, a bulk request is not an atomic transaction. Elasticsearch processes each item independently: some documents can succeed while other items fail.

Therefore, receiving a successful HTTP response or having the bulk method return does not mean every document was written. The application must inspect item-level results, classify errors, retry only recoverable operations, and ensure retries do not create duplicate data or apply a mutation multiple times.

In Spring Data Elasticsearch, bulk operations can be executed through `ElasticsearchOperations` or the Elasticsearch Java API Client. Regardless of the abstraction, test design must verify three things: item-level results are observed accurately, retries apply only to recoverable failures, and repeated operations preserve the expected data state.

This lesson explains Bulk API semantics, how to inspect partial failures, retry strategies with backoff, idempotency per operation type, handling ambiguous timeouts, dead-letter handling, concurrency, and recommended tests.

## 1. A Bulk Request Is Not a Transaction

A bulk request contains multiple consecutive actions. Example NDJSON:

~~~http
POST /_bulk
{"index":{"_index":"products","_id":"P-1001"}}
{"sku":"SKU-1001","name":"Wireless Mouse","stock":42}
{"index":{"_index":"products","_id":"P-1002"}}
{"sku":"SKU-1002","name":"Keyboard","stock":18}
{"delete":{"_index":"products","_id":"P-1003"}}
~~~

Elasticsearch executes each action in the batch. The outcome can be:

- `P-1001` is indexed successfully.
- `P-1002` fails due to mapping or invalid data.
- `P-1003` is deleted successfully.

The Bulk API does not roll back `P-1001` and `P-1003` just because `P-1002` failed. Nor does it guarantee all items commit or fail together.

Thus, bulk is a mechanism to batch requests for transport efficiency, not a multi-document transaction.

### 1.1. Two Levels of Errors

Distinguish between:

**Request-level errors**

The entire request fails to process as expected. Examples:

- Invalid NDJSON request format.
- Payload too large or exceeding limits.
- Invalid endpoint/index at request level.
- Authentication/authorization rejected.
- Connection failure before receiving a response.
- Proxy or cluster returning a request-level error.

**Item-level errors**

A bulk response is returned, yet one or more actions fail. Examples:

- Document does not match the mapping.
- Version conflict.
- Target document for update does not exist.
- Index is read-only.
- Shard or node rejects the item due to overload.

A request can return HTTP 200 while the `errors` field in the response is `true`. That is why checking only HTTP status is wrong.

## 2. Bulk Response Structure

A bulk response contains an `errors` flag and an `items` list. Each item corresponds to one action in the request, in the exact same order.

Example:

~~~json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-1002",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [priceInCents]"
        }
      }
    },
    {
      "delete": {
        "_index": "products",
        "_id": "P-1003",
        "status": 200,
        "result": "deleted"
      }
    }
  ]
}
~~~

In this example:

- `errors = true` because at least one item failed.
- The first item succeeded.
- The second item failed mapping with status 400.
- The third item succeeded.

The application must correlate each item response with its corresponding operation/source record to know which business record needs retry, rejection, or quarantine.

### 2.1. Fields to Read

At the response level:

- `took`: time spent by Elasticsearch processing the request.
- `errors`: whether at least one item failed.
- `items`: per-action outcomes.

At the item level:

- operation type: `index`, `create`, `update`, or `delete`.
- `_index` and `_id`: target index and document ID.
- `status`: item-specific HTTP status.
- `result`: `created`, `updated`, `deleted`, `noop`, or equivalent outcome.
- `error`: error type and message when the item fails.

Not every item has the exact same set of response fields. On success, responses typically include `result` and version/sequence metadata; on failure, they include `error`. Verify the exact structure for your Elasticsearch/client version.

### 2.2. Do Not Assume Everything Is Done When errors = false and Ignore the Response

When `errors = false`, no item reported an error for that bulk response. Even so, the application may still inspect item results when it needs to:

- Store version or sequence metadata.
- Distinguish `created` from `updated`.
- Confirm `delete`/`noop`.
- Record metrics by operation type.
- Correlate documents back to source data.

When `errors = true`, iterate over every item to classify outcomes. Never retry the entire batch blindly by default.

## 3. Keeping Metadata to Correlate Requests with Responses

Bulk responses return `items` in action order. Therefore, the application should maintain a metadata list in the exact same order as the submitted operations.

Example metadata:

~~~java
public record BulkOperationMetadata(
    int position,
    String businessKey,
    String indexName,
    String documentId,
    String operationType,
    int attempt
) {
}
~~~

When building a bulk request, build corresponding metadata for each operation. When receiving the response, match item at position `i` with metadata at position `i`.

This enables you to:

- Identify the failing source record.
- Rebuild only the operations that need retrying.
- Write dead-letter records with business keys.
- Avoid retrying already-succeeded items by mistake.
- Track attempt counts per document.

Do not hold only a raw list of documents without correlation keys. When a batch contains thousands of items, logging one generic failure message is insufficient for accurate recovery.

### 3.1. Do Not Assume Order After Filtering or Re-sorting

When constructing a retry batch, the new operations list may be shorter and ordered differently from the original batch. Build fresh metadata for the retry batch matching the exact order of the new operations.

If code processes responses concurrently or aggregates multiple batches, assign a distinct correlation ID/batch ID to avoid matching one batch's response against another batch's source records.

## 4. Inspecting Bulk Responses with Elasticsearch Java API Client

With the Elasticsearch Java API Client, responses can typically be inspected via `BulkResponse` and `BulkResponseItem`.

Example:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkResponse response = client.bulk(request);

if (response.errors()) {
    for (int i = 0; i < response.items().size(); i++) {
        BulkResponseItem item = response.items().get(i);

        if (item.error() != null) {
            BulkOperationMetadata metadata = metadataForBatch.get(i);

            log.warn(
                "Bulk item failed: batchId={}, position={}, key={}, index={}, id={}, status={}, type={}, reason={}",
                batchId,
                metadata.position(),
                metadata.businessKey(),
                item.index(),
                item.id(),
                item.status(),
                item.error().type(),
                item.error().reason()
            );
        }
    }
}
~~~

This illustrates inspection using the modern Java client API. Packages, response types, and accessor names may vary by client version. Verify against your project's dependencies.

Key points in this example:

- Check `errors`.
- Iterate through each item.
- Use position to look up the corresponding operation's metadata.
- Log only the business key and necessary technical details.
- Never log the full source if documents contain sensitive data.

### 4.1. Building the List of Failed Items

You can classify the response into three groups:

~~~java
List<BulkOperationMetadata> succeeded = new ArrayList<>();
List<BulkOperationMetadata> retryable = new ArrayList<>();
List<FailedBulkRecord> permanentFailures = new ArrayList<>();

for (int i = 0; i < response.items().size(); i++) {
    BulkResponseItem item = response.items().get(i);
    BulkOperationMetadata metadata = metadataForBatch.get(i);

    if (item.error() == null) {
        succeeded.add(metadata);
        continue;
    }

    if (isRetryable(item.status(), item.error().type())) {
        retryable.add(metadata);
    } else {
        permanentFailures.add(
            new FailedBulkRecord(
                metadata,
                item.status(),
                item.error().type(),
                item.error().reason()
            )
        );
    }
}
~~~

Types like `FailedBulkRecord` and `isRetryable` are application logic you define. Do not rely on example class names; the goal is separating succeeded items, retryable errors, and permanent failures cleanly.

## 5. Classifying Errors Before Retrying

Retries help only when the error is likely to clear after a delay or corrective action. Retrying permanent errors merely increases load and delays processing.

Reference classification table:

| Error/status | Typical classification | Action |
|---|---|---|
| 400 mapper/parsing error | Permanent | Fix data or schema; do not auto-retry |
| 401 unauthorized | Configuration/credential | Fix authentication; halt or alert |
| 403 forbidden | Authorization | Fix permissions; do not retry continuously |
| 404 index/document missing | Depends on operation | Check target and upsert/delete semantics |
| 409 version conflict | Concurrency conflict | Re-read and resolve per business logic |
| 413 payload too large | Batch/request size | Split batch smaller; do not resend original size |
| 429 too many requests | Transient/backpressure | Back off, reduce concurrency |
| 502/503/504 | Usually transient | Bounded backoff and monitor cluster |
| Timeout/network reset | Outcome may be unknown | Reconcile or safely retry per idempotency |
| Other 5xx | Depends on root cause | Inspect error type and server logs |

The classification above is a starting point. Refine it based on error type, status, operation context, and cluster policy.

### 5.1. Mapping Errors Should Not Be Retried

For example, `priceInCents` is mapped as `long`, yet the producer sends `"unknown"`. Resending the exact same payload one second later will not turn the string into a valid number.

Appropriate handling:

- Record the business key and validation error.
- Route the record to dead-letter/quarantine for later repair.
- Return an error upstream or mark the batch as containing rejected records.
- Replay only after the data or mapping is fixed.

### 5.2. 429 Is a Signal to Reduce Load

429 usually indicates the cluster is rejecting operations due to overload or resource limits. Retrying immediately at the same concurrency can worsen the situation.

You need:

- Exponential backoff.
- Jitter so multiple workers do not retry in lockstep.
- Reduced concurrent requests or smaller batch sizes.
- Limits on queued pending items.
- Monitoring of thread pool queues, rejections, and ingest/indexing pressure for your version.

Retries do not substitute for load control.

### 5.3. 409 Requires Business Policy

409 can be a version conflict or a duplicate ID on create. The two cases are not identical:

- Version conflict: another writer modified the document. Re-read, recompute the change, and retry in a controlled way.
- Create conflict: the document ID already exists. This could be a valid duplicate, an unintended duplicate, or an earlier attempt that succeeded while its response was lost.

Never auto-retry 409 without understanding the operation's intent.

## 6. Retrying Only Failed Items

Suppose a batch has 100 operations:

- 94 items succeed.
- 4 items fail with 429.
- 2 items fail with mapping error 400.

Appropriate strategy:

1. Acknowledge the 94 succeeded items.
2. Record the 2 mapping error items to failure/quarantine.
3. Retry only the 4 items with 429.
4. Build a new bulk request containing exactly those 4 operations.
5. Increment the attempt counter for retried items.

Never resend all 100 operations. Doing so wastes load and can repeat non-idempotent operations that already succeeded.

### 6.1. Retry Subsets Must Preserve the Intended Payload

When retrying, retain enough data to reconstruct the operation:

- Operation type.
- Target index/alias.
- Document ID.
- Routing if applicable.
- Source or partial document.
- Script and params if using an update script.
- Version/concurrency condition if applicable.
- Pipeline ID if the request uses an ingest pipeline.
- Business key and correlation ID.

Do not store only an error message and expect to rebuild the request later. If the source mutated upstream in the meantime, retrying could write a different payload than the original operation.

### 6.2. Batch Processing Pseudocode

~~~text
pending = original operations
attempt = 0

while pending is not empty and attempt < maxAttempts:
    response = sendBulk(pending)

    nextRetry = []

    for each item result in response order:
        correlate result with pending operation

        if success:
            record success

        else if retryable:
            add operation to nextRetry

        else:
            write permanent failure to quarantine

    pending = nextRetry

    if pending is not empty:
        wait exponentialBackoffWithJitter(attempt)

    attempt = attempt + 1

if pending is not empty:
    move remaining operations to retry-exhausted queue
~~~

In practice, retries can run asynchronously via a queue instead of blocking a thread while waiting. Either way, bound both total elapsed time and attempt count.

## 7. Exponential Backoff and Jitter

A common retry policy grows the wait interval by attempt number:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

Example with `baseDelay = 200 ms`, `maxDelay = 5 s`:

| Attempt | Base delay |
|---:|---:|
| 0 | 200 ms |
| 1 | 400 ms |
| 2 | 800 ms |
| 3 | 1.6 s |
| 4 | 3.2 s |
| 5 onward | 5 s |

Avoid letting all workers retry at the exact same instant. Jitter adds randomness to spread out requests:

\[
actualDelay = random(0,\ delay_n)
\]

Systems commonly use full jitter, equal jitter, or decorrelated jitter. Choose a consistent policy and enforce an upper bound.

### 7.1. Retry Budget

Enforce bounds on:

- Max attempts per item.
- Max elapsed time.
- Max queue size.
- Max concurrent retry batches.
- Max batch size.
- Circuit breaker or pause when the cluster rejects persistently.
- Dead-letter routing when the retry budget is exhausted.

If an item can retry 100 times, a mapping issue can bloat queues and tie up resources indefinitely. A retry budget gives failures a clear termination point.

### 7.2. Respecting Retry-After When Present

Some proxies or service layers return `Retry-After`. If the client receives this information, consider respecting it rather than using a shorter internal delay.

Not every Elasticsearch item error includes `Retry-After`. Never assume the header is always present in Bulk API responses.

## 8. Java Examples for Retry Classifier and Backoff

Simple classifier:

~~~java
public boolean isRetryable(int status, String errorType) {
    if (status == 429) {
        return true;
    }

    if (status == 502 || status == 503 || status == 504) {
        return true;
    }

    if (status >= 500 && status <= 599) {
        return true;
    }

    // Mapping, validation, authentication and authorization
    // errors should normally be handled without blind retry.
    return false;
}
~~~

A production classifier should also inspect error types and operation semantics. For instance, a 404 on update might need upsert or not-found handling; a 409 needs a dedicated concurrency policy.

Delay calculation with jitter:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public Duration retryDelay(
        int attempt,
        Duration baseDelay,
        Duration maxDelay) {

    long multiplier = 1L << Math.min(attempt, 20);

    long baseMillis = baseDelay.toMillis();
    long maxMillis = maxDelay.toMillis();

    long exponential = Math.min(
        maxMillis,
        baseMillis * multiplier
    );

    long jittered = ThreadLocalRandom.current()
        .nextLong(exponential + 1);

    return Duration.ofMillis(jittered);
}
~~~

This is an illustrative helper for full jitter. In production code:

- Guard against negative attempts.
- Prevent arithmetic overflow when multiplying delays.
- Ensure `maxDelay` is positive.
- Use a non-blocking scheduler when inside a reactive pipeline.
- Externalize policy settings into configuration to tune under load.

With Reactor, you can use `delayElement` or `retryWhen` with `Retry.backoff` and jitter, keeping in mind that request-level retry differs from item-subset retry. A `retryWhen` wrapped around the entire bulk publisher can resend the entire batch without filtering out succeeded items.

## 9. What Is Idempotency?

An operation is idempotent when executing it multiple times with the same inputs and conditions yields the same final state as executing it once.

In notation:

\[
f(f(state)) = f(state)
\]

Idempotency is especially critical when:

- The client times out and does not know whether the server processed the request.
- The connection resets after Elasticsearch indexed the document but before the response reached the client.
- A worker restarts after writing successfully but before marking the job complete.
- A message broker redelivers an event.
- Retries are executed across multiple workers.

Safe retrying depends not only on HTTP status codes; it depends on operation semantics and how documents are identified.

## 10. Idempotency by Bulk Operation Type

| Operation | Safe repeatability | Notes |
|---|---|---|
| `index` with fixed ID and identical full source | Usually idempotent regarding source state | Each write replaces with the exact same document state |
| `index` with auto-generated ID | Not idempotent | Retrying can create a new duplicate document |
| `create` with fixed ID | Not repeatable at protocol level | First call may have succeeded; subsequent calls return 409 |
| `update` doc setting fixed field values | Usually idempotent for those fields | E.g., setting `status = SHIPPED` |
| `update` script incrementing counter | Not idempotent | Retrying can add twice |
| `update` script appending to array | Not idempotent without duplicate check | Retrying can append duplicate elements |
| `delete` with same ID | Desired state usually idempotent | Subsequent calls may return not found |
| `upsert` setting fixed source | Usually idempotent regarding source state | Must consider scripts and concurrency |
| Scripted cumulative `upsert` | Not idempotent without guard | Retrying may run the script multiple times |

### 10.1. Indexing with a Deterministic ID

Example:

~~~http
PUT /orders/_doc/ORDER-2026-0001
{
  "orderId": "ORDER-2026-0001",
  "status": "PAID",
  "totalInCents": 259900
}
~~~

Resending the same ID and same source leaves the document in the exact same state. This is a relatively safe retry pattern.

However, note: the Index API replaces the current source. If another writer updated the document between retry attempts, resending an older snapshot can overwrite the newer change. Idempotency with identical inputs does not imply safety against concurrent writers.

### 10.2. Auto-Generated IDs

Example letting Elasticsearch generate the ID:

~~~http
POST /orders/_doc
{
  "orderId": "ORDER-2026-0001",
  "status": "PAID"
}
~~~

If the response is lost and the application retries, Elasticsearch can create a second document with a new ID. Therefore, safe retries for business events generally require deterministic document IDs derived from a business key or event ID.

### 10.3. Create and HTTP 409

Create-only ensures an ID is created at most once:

~~~http
PUT /orders/_create/ORDER-2026-0001
{
  "orderId": "ORDER-2026-0001",
  "status": "PAID"
}
~~~

If the initial request succeeded while the response was lost, the retry receives 409 because the ID already exists. Do not immediately treat that as a business failure.

The application can:

1. Read the document by ID.
2. Compare the event/business key and payload/version.
3. If the document reflects the exact original operation, treat it as completed.
4. If the data differs, handle the conflict per business rules.

Create prevents duplicate IDs, yet the caller still needs to reconcile ambiguous outcomes.

### 10.4. Assignment Updates vs Cumulative Updates

Assignment update with fixed values:

~~~http
POST /orders/_update/ORDER-2026-0001
{
  "doc": {
    "status": "SHIPPED"
  }
}
~~~

Resending the same payload keeps `status` at `SHIPPED`.

By contrast, an incrementing script:

~~~http
POST /metrics/_update/worker-1
{
  "script": {
    "source": "ctx._source.count += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

Retrying after a timeout can increment `count` twice. Array-append scripts carry the same risk.

## 11. Designing Idempotency Keys and Document IDs

A common pattern is deriving deterministic document IDs from a business key or event ID.

Examples:

- Order document: `orderId`.
- Payment event: payment provider transaction ID.
- Inventory movement: `movementId`.
- Outbox event: `eventId`.
- Import row: `sourceSystem + sourceRecordId`.

Never generate a fresh random UUID on each retry attempt. If a UUID is needed, generate it once at the event source and persist it with the event.

### 11.1. Combining Multiple Fields

When a business key has multiple parts, build the ID from a canonical representation:

~~~text
tenantId + ":" + sourceSystem + ":" + sourceRecordId
~~~

Avoid collisions caused by delimiters appearing inside components. Encode components or hash canonical bytes into an ID.

Deterministic IDs help retries find the exact document, though they do not replace tenant authorization or uniqueness checks in the source system.

### 11.2. Event ID and Payload Hash

You can also store:

- `eventId`.
- `sourceSystem`.
- `sourceVersion`.
- `payloadHash`.
- `processedAt`.

When encountering a duplicate event ID, the application can determine:

- Same event and same payload: duplicate delivery can be treated as already processed.
- Same event ID but different payload: contract violation or misused event ID.
- Older source version: can be ignored per versioning rules.
- Newer source version: update per policy.

Do not rely solely on timestamps when the source provides reliable, monotonically increasing versions.

## 12. Idempotency for Update Scripts

When cumulative arithmetic is required, a processed operation ID can prevent double application.

Conceptual example:

~~~json
{
  "script": {
    "source": "if (ctx._source.processedEvents == null) { ctx._source.processedEvents = []; } if (!ctx._source.processedEvents.contains(params.eventId)) { ctx._source.count += params.amount; ctx._source.processedEvents.add(params.eventId); } else { ctx.op = 'none'; }",
    "params": {
      "eventId": "evt-10001",
      "amount": 1
    }
  }
}
~~~

The script checks `eventId` before applying the addition. If the event was already processed, the operation becomes a no-op.

This is an illustrative example, not a design for unbounded deduplication storage. The `processedEvents` array can grow indefinitely and bloat the document. Real systems may need a dedicated deduplication index, bounded retention, an external idempotency store, or a suited event-processing architecture.

If an operation requires an exactly-once effect across multiple systems, a single Elasticsearch script does not provide a distributed transaction. Use idempotency keys, outbox/inbox patterns, or appropriate orchestration.

## 13. Timeouts and Ambiguous Outcomes

Timeouts are tricky because the client does not know whether the operation took effect.

Example:

1. The client sends a bulk request.
2. Elasticsearch receives and writes some or all items.
3. The response is lost on the network or the client times out.
4. The client only sees an exception.

You cannot conclude all items failed. Some or all may have succeeded.

This is an ambiguous outcome.

Handling depends on the operation:

- Fixed-ID `index` with deterministic full source: can resend and verify final state.
- Fixed-value `update`: generally safe to retry if no other writer modifies those fields.
- Cumulative script: needs an idempotency guard or read/reconcile before retrying.
- `create`: read document by ID and match the event ID.
- `delete`: verify absent state per business semantics.

When possible, record the batch ID and operation IDs before sending so ambiguous timeouts can be reconciled afterward.

### 13.1. Do Not Blindly Retry Exceptions

Wrapping `client.bulk(request)` in a retry loop resends every operation. This is safe only when all operations in the request are idempotent and produce no other side effects.

If a batch mixes `index`, `create`, update scripts, and `delete`, classify each item's semantics before picking a retry strategy. One blanket policy for all operations is too coarse.

## 14. Version Conflicts and Optimistic Concurrency

When multiple writers update the same document concurrently, Elasticsearch can return 409 version conflict if requests use optimistic concurrency control.

You can use sequence number and primary term:

~~~http
POST /products/_update/P-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "stock": 35
  }
}
~~~

If the document changed since it was read, the request is rejected rather than overwriting newer state.

The application should:

1. Read the latest document/version.
2. Check whether the change is still valid.
3. Recompute the command if necessary.
4. Retry with fresh concurrency tokens or surface the conflict to the caller.

Never strip concurrency conditions just to retry, as that turns a prevented lost update into a silent overwrite.

### 14.1. retry_on_conflict Does Not Replace Idempotency

The Update API offers `retry_on_conflict` for certain update operations. Elasticsearch can re-read the new source and re-run the update script on conflict.

This resolves one class of internal conflicts during an update, yet it does not make a script idempotent against duplicate client requests. An incrementing script can still increment twice if the whole request is resent after a timeout.

## 15. Bulk via Spring Data Elasticsearch

Spring Data Elasticsearch exposes bulk operations on `ElasticsearchOperations` such as `bulkIndex`, `bulkUpdate`, or `bulkDelete` depending on version.

Common pattern:

~~~java
List<IndexQuery> indexQueries = products.stream()
    .map(product -> new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build())
    .toList();

List<IndexedObjectInformation> indexed =
    operations.bulkIndex(
        indexQueries,
        IndexCoordinates.of("products")
    );
~~~

API signatures, return types, and item-failure representations change across Spring Data Elasticsearch versions. Some paths throw an exception carrying failed document details instead of returning a simple per-item result structure.

Therefore:

- Read the Javadoc for your exact dependency version.
- Check whether the API returns per-item results or throws a bulk failure exception.
- Ensure the application retains metadata per `IndexQuery`.
- Never catch a generic exception and mark the entire batch failed without checking which items succeeded.
- Write integration tests for the exact bulk method production calls.

When fine-grained item-level request/response control is needed, use the Elasticsearch Java API Client directly and manage transport through suitable Spring configuration.

### 15.1. Bulk Updates and Partial Failures

Bulk updates can combine `doc`, `script`, and `upsert` operations. Item-level failures still occur due to:

- Document not found.
- Mapping errors.
- Version conflicts.
- Script errors.
- Authorization or index state.
- Overload.

Retrying an update script can have different semantics than retrying an index operation. Retain full operation definitions, script params, and concurrency conditions if replay is required.

### 15.2. saveAll Does Not Mean Transaction

Repository `saveAll` may use bulk or multiple operations depending on implementation/version. Never assume `saveAll` is atomic. Inspect the concrete API path and failure semantics.

When business logic requires multiple mutations to succeed together, design a workflow/compensation mechanism or place transactions in an appropriate store. The Bulk API does not provide multi-document transactions.

## 16. Retry Queue and Dead-Letter Architecture

For high-volume ingestion, do not hold all retries in memory inside a single request handler. Use a queue or persistent job store.

Suggested flow:

~~~text
Source events
     |
     v
Batch builder
     |
     v
Bulk writer
     |
     +------ successful items ------> Mark completed
     |
     +------ transient failures ----> Retry queue
     |
     +------ permanent failures ---> Dead-letter / quarantine
                                      |
                                      v
                                Repair and replay
~~~

The retry queue should store:

- Event ID and business key.
- Operation type.
- Index and document ID.
- Payload or reference to an immutable payload.
- Attempt count.
- Last attempt timestamp.
- Last error.
- Next retry timestamp.
- Correlation/batch ID.

Dead-letter records need enough context to investigate and replay after fixing the root cause. Avoid storing unnecessary passwords, tokens, or sensitive data.

### 16.1. Do Not Let Retry Queues Grow Unbounded

Configure:

- Max attempts.
- Retention.
- Queue capacity.
- Alerts when backlog grows.
- Dead-letter thresholds.
- Replay procedures.
- Concurrency limits on retry workers.

If Elasticsearch goes down for an extended period, the queue must apply backpressure to protect memory and upstream systems. Do not keep accepting items indefinitely just because they fit in an in-process list.

## 17. Preserving Ordering by Document Key

Some domains require events for the same document to be processed in order.

Example:

1. Order created.
2. Order transitions to `PAID`.
3. Order transitions to `SHIPPED`.

If `SHIPPED` is retried and written before an older `PAID` event, state can regress to `PAID`.

Strategies:

- Partition queues by document ID/business key.
- Process sequentially within each partition.
- Use source versions/sequences to reject stale events.
- Use optimistic concurrency.
- Allow only one writer to own a key at a time in an appropriate architecture.

Idempotency alone does not guarantee ordering. An idempotent event can still overwrite newer state if replayed out of order.

## 18. Bulk Size, Concurrency, and Retry Storms

When a cluster is overloaded, retrying many requests concurrently can trigger a retry storm.

Monitor:

- Batch size by item count and bytes.
- Number of concurrent bulk requests.
- Bulk request latency.
- Item failure rate by status/error type.
- 429/rejections.
- Retry queue depth.
- Retry attempts and exhausted counts.
- Ingest/indexing thread pools and indexing pressure per version.
- Heap, CPU, disk I/O, and merge pressure.

### 18.1. Choosing Batch Size

There is no single fixed batch size for every cluster. Large batches reduce request count yet can:

- Increase client-side memory usage.
- Increase latency while waiting to fill batches.
- Produce oversized requests.
- Complicate subset retries if metadata is dropped.
- Create heavy pressure when the server rejects a request.

Measure with realistic document sizes. Increase batch size gradually until throughput stops improving or latency/rejections climb.

### 18.2. Tuning Concurrency on 429

If 429 errors spike:

1. Reduce the number of concurrent bulk requests.
2. Reduce or hold batch size steady depending on the cause.
3. Apply backoff with jitter.
4. Monitor queue depth/rejections.
5. Ramp load back up gradually once the cluster recovers.

Never increase retry concurrency to compensate for reduced throughput. That usually keeps the cluster overloaded longer.

## 19. Intentionally Testing Partial Failures

A good test demonstrates a single batch containing both successes and failures, then verifies the application handles each group properly.

Use Elasticsearch Testcontainers or an isolated test cluster.

Scenario:

1. Create an index mapping `priceInCents` as `long`.
2. Build a batch mixing valid documents and a document with an unparseable `priceInCents`.
3. Send the bulk request.
4. Verify `response.errors` is `true`.
5. Verify valid items were indexed.
6. Verify failed items carry the expected status/error.
7. Verify the application does not retry the mapping error item.
8. Repair the payload or route to quarantine.
9. Read documents back to verify final state.

Do not assert only that the bulk method throws an exception. Verify specifically which items succeeded and which failed.

### 19.1. Testing Response Correlation

Include multiple documents with distinct business keys and intentionally fail an item in the middle of the batch. Verify the failure maps back to the exact business key and document ID.

This catches a common bug: iterating over filtered error lists while indexing into the original source list with the wrong offset.

### 19.2. Testing Retry Subsets

Simulate a response where:

- Item A succeeds.
- Item B returns 429.
- Item C fails with 400.

Verify the next transmission contains only B. A must not be resent; C must move to the permanent failure path.

Use a mock client or fake bulk gateway to test classifiers and retry orchestration without forcing real cluster errors in every unit test.

### 19.3. Testing Retry Exhaustion

Simulate an item returning 503 or 429 repeatedly. Verify:

- Attempt count never exceeds the budget.
- Delay policy is applied.
- The item eventually lands in retry-exhausted/dead-letter storage.
- Queues do not retain items forever.
- Metrics and alerts emit per contract.

## 20. Testing Idempotency

Verify final state after sending the same operation multiple times.

### 20.1. Indexing with Fixed IDs

1. Send the index operation once.
2. Resend the same ID and source.
3. Read the document.
4. Confirm only one document exists with the right source.

### 20.2. Auto-Generated IDs

1. Send create/index without an ID.
2. Resend the same payload.
3. Count documents.
4. Observe that duplicates can be created.

This test demonstrates why event processing needs deterministic IDs.

### 20.3. Counter-Incrementing Scripts

1. Send the increment script once.
2. Resend the exact same request.
3. Read the counter.
4. Confirm the counter incremented twice when no dedup guard exists.
5. Add an idempotency guard and confirm repeated delivery applies only once.

### 20.4. Create Conflict After Timeout

Simulate an operation that already created the document while the client missed the response. Resend `create` with the same ID and receive 409. Read the document, compare `eventId`/`payloadHash`, and verify the outcome can be reconciled as completed.

### 20.5. Concurrent Retries

Run two workers processing the same event ID concurrently. Verify only one worker applies the effect or that deduplication/concurrency protects final state. In-memory deduplication inside a single worker is insufficient when multiple instances run.

## 21. Unit Testing Classifiers and Backoff

Keep the classifier pure for easy testing:

~~~java
@Test
void shouldRetryTooManyRequests() {
    assertThat(retryPolicy.isRetryable(429, "rejected_execution_exception"))
        .isTrue();
}

@Test
void shouldNotRetryMappingErrors() {
    assertThat(retryPolicy.isRetryable(400, "mapper_parsing_exception"))
        .isFalse();
}
~~~

Backoff tests should check bounds:

- Delay is non-negative.
- Delay never exceeds `maxDelay`.
- Large attempt counts do not overflow.
- Jitter stays within the expected range.
- Max attempts stop at the right limit.

If using random jitter, inject the random source or clock so tests stay deterministic. Avoid sleeping in unit tests; use virtual time or assert calculated delay values.

## 22. Reactive Bulk and Retries

If the application uses reactive APIs, bulk publishers must process item-level responses inside the reactive chain. Never call `block` to wait for results.

Conceptual flow:

~~~java
return bulkGateway.send(operations)
    .flatMap(response -> classifyItems(response, metadata))
    .flatMapMany(classification -> processClassification(classification));
~~~

If using Reactor's `retryWhen` around the whole bulk request, remember `retryWhen` typically resubscribes to the publisher and can resend the entire request. It does not automatically filter out items that already succeeded in a partial response.

For reactive bulk:

- Classify items inside the response.
- Build a separate publisher for the retry subset.
- Use `delayElement` or `retryWhen` with backoff/jitter on the appropriate subset.
- Bound concurrency.
- Preserve metadata and idempotency keys across retries.
- Never subscribe manually inside a service.
- Never hold an unbounded retry list in memory.

Reactive execution does not alter Bulk API semantics: every item still has its own outcome, and batches are not transactions.

## 23. Observability and Logging

A reliable bulk system needs metrics at both batch and item levels.

Suggested metrics:

- `bulk_requests_total`.
- `bulk_items_total`.
- `bulk_items_succeeded_total`.
- `bulk_items_failed_total`.
- `bulk_item_failures{status,error_type}`.
- `bulk_retry_items_total`.
- `bulk_retry_exhausted_total`.
- `bulk_dead_letter_total`.
- `bulk_request_duration`.
- `bulk_batch_bytes`.
- `bulk_retry_queue_depth`.

Logs should include:

- Batch ID.
- Operation type.
- Index.
- Document ID or log-safe business key.
- Attempt number.
- Status.
- Error type.
- Correlation ID.
- Retry decision.

Never log full document sources by default. Data may contain PII, tokens, or business secrets. If failed payloads must be saved for replay, use storage with proper access control, retention, and encryption.

Alert when:

- Item failure rates spike suddenly.
- Persistent 429 responses occur.
- Retry queues grow rapidly.
- Dead-letter volume rises.
- Retry exhaustion exceeds thresholds.
- Bulk latency rises or throughput drops.
- Mapping errors appear after deployments.

## 24. Common Pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| Bulk returns HTTP 200 yet records are missing | Not inspecting `errors`/`items` | Iterate through every item response |
| Retries create duplicate documents | Auto-generated IDs or missing idempotency keys | Use deterministic IDs and reconcile |
| Batch retry increments counters twice | Non-idempotent increment script | Deduplicate event IDs or use idempotent operations |
| Failed items tied to wrong source records | Dropped ordering/correlation metadata | Match by position and batch ID |
| Retrying mapping errors endlessly | Not distinguishing permanent vs transient errors | Classify by status and error type |
| Cluster keeps returning 429 | Immediate retries, excessive concurrency | Backoff, jitter, and load reduction |
| Timeout yet document was already written | Response lost after server processed write | Reconcile by ID/event ID |
| Create retry returns 409 | Prior attempt may have succeeded | Read and reconcile the document |
| Update returns 404 | Document missing or wrong index | Handle not-found or upsert per domain |
| Repeated version conflicts | Concurrent writers | Re-read and resolve per concurrency policy |
| Retry queue grows without bound | Missing max attempts/backpressure | Enforce retry budgets and dead-letter queues |
| Newer event overwritten by older event | Retries ignore ordering/versions | Partition by key or check source versions |
| Bulk method throws and drops details | Missing failed-item details in exception handling | Use version-appropriate APIs/responses and test |
| `saveAll` assumed atomic | Misunderstanding bulk semantics | Handle outcomes per item |
| Reactive retry resends whole batch | `retryWhen` wraps the full request | Filter retry subset before resubscribing |

## 25. Workflow for Processing a Bulk Batch

An effective processing pipeline can follow:

1. Assemble batches bounded by item count and byte size.
2. Assign a batch ID and retain metadata for every operation.
3. Send the request via the configured client.
4. On response, correlate every item in order.
5. Mark succeeded items complete.
6. Classify permanent errors, transient errors, and conflicts.
7. Send permanent failures to quarantine/dead-letter.
8. Build the retry batch solely from transient failures.
9. Apply backoff, jitter, and retry budgets.
10. On timeouts without a response, mark outcomes ambiguous and reconcile by operation ID.
11. When the retry budget is exhausted, write a retry-exhausted record.
12. Emit metrics and update batch status.

Never mark an entire batch completed just because some items succeeded. Batch status should reflect counts of succeeded, permanent failures, retrying, and ambiguous items.

## 26. Quick Reference Table

| Need | Approach |
|---|---|
| Detect item failures in bulk | Check `response.errors` |
| Identify failed items | Iterate `response.items` and `error`/`status` |
| Match responses to sources | Keep metadata in exact operation order |
| Retry transient 429/5xx errors | Backoff, jitter, and retry subset |
| Avoid retrying mapping errors | Quarantine or fix payloads |
| Handle version conflicts | Re-read and apply concurrency policy |
| Make index retries safer | Stable IDs and deterministic source |
| Avoid auto-generated ID duplicates | Derive document IDs from business/event keys |
| Reconcile create 409 | Read document and compare event ID/payload |
| Protect increment scripts | Idempotency guard or deduplication store |
| Handle ambiguous timeouts | Reconcile by operation ID before retrying |
| Bound retries | Max attempts, elapsed time, and queue capacity |
| Handle unrecoverable failures | Dead-letter/quarantine |
| Preserve ordering | Partition by document key or check source version |
| Test Spring Data bulk | Test exact bulk API and exception semantics of your version |
| Test reactive bulk | Classify response inside Publisher, never block |
| Operational visibility | Metrics by batch and item |

Bulk tests must prove the application inspects per-item outcomes, detects partial failures, and retries only recoverable operations. The Bulk API is not a transaction, so succeeded items may still persist when other items fail. Retries need backoff, jitter, a retry budget, and error classification; mapping/authentication errors are permanent, while 429/5xx generally need load reduction and bounded retries. Safe repeatability depends on operation type: fixed-ID indexing with deterministic sources is easy to retry, whereas creates, auto-generated IDs, and cumulative scripts need deduplication or reconciliation. For ambiguous timeouts, check document/event IDs before resending. Preserve per-item metadata, test both partial responses and ambiguous outcomes, and monitor retries/dead-letters so bulk ingestion recovers cleanly without creating duplicates or applying mutations multiple times.
