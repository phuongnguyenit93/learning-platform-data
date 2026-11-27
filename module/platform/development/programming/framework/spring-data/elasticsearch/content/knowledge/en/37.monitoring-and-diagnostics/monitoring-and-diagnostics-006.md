# HTTP 429, Rejections, Timeouts, and Partial Bulk Item Failures

When a Spring Data Elasticsearch application writes data at high speed, Elasticsearch may not keep up with incoming request volume. The application may encounter HTTP 429, `es_rejected_execution_exception`, timeouts, or a bulk response that only partially succeeds. These are distinct situations and require different handling.

The key point is that **a bulk request is not an all-or-nothing transaction**. A response may confirm hundreds of items succeeded while several others failed. If an application checks only the HTTP status or looks only at the `errors` flag, it can miss unwritten data or resend items that already succeeded.

A reliable operational strategy requires:

- Distinguishing full-request rejections from individual item errors.
- Recognizing resource pressure and throttling send rates.
- Distinguishing timeouts with unknown outcomes from confirmed failures.
- Bounded retries with backoff and jitter.
- Retrying only items that need retries when the response provides per-item results.
- Designing stable IDs/versions and idempotent operations for safe retries.
- Routing unrecoverable data errors to a dead-letter queue.
- Monitoring queues, rejections, latency, indexing pressure, and error rates.

## 1. At what levels can a bulk request fail?

A bulk request consists of multiple index/create/update/delete operations. When sending a request, failures can occur at three levels:

1. **Request-level failure:** Elasticsearch or the network layer rejects/fails the entire request. The application may not receive per-item results.
2. **Item-level failure:** a bulk response is returned, but one or more individual operations failed. Remaining items can still succeed.
3. **Client/application failure:** client timeout, connection reset, application cancellation, or process crash before receiving the response. Server-side state may be unknown.

```text
Application
    |
    | Bulk request: A, B, C, D
    v
Elasticsearch
    |
    +-- Request rejected (HTTP 429)
    |       -> No complete per-item results for the application
    |
    +-- Bulk response received
    |       +-- A: success
    |       +-- B: success
    |       +-- C: item failure (429 / 400 / 409 ...)
    |       +-- D: success
    |
    +-- Response lost / client timeout
            -> Server may have processed some or all items
```

Do not share one retry branch across all three cases. Request-level 429 usually requires resending the batch after shedding load; item-level 429 only needs retrying the rejected items; timeouts may require reconciliation or idempotent retries because the application does not know how far the server progressed.

## 2. HTTP 429 and `es_rejected_execution_exception`

HTTP 429 indicates the server is rejecting requests because it cannot accept more work at that moment. In Elasticsearch, a common cause is that the write/bulk thread pool has a full queue or no remaining capacity.

A response may contain an error similar to:

```json
{
  "error": {
    "type": "es_rejected_execution_exception",
    "reason": "rejected execution ..."
  },
  "status": 429
}
```

`es_rejected_execution_exception` is an overload or capacity-exhaustion signal in a processing component. It does not mean the document has a bad mapping. Resending immediately at the same rate usually makes things worse.

### 2.1. Why does Elasticsearch reject writes?

Common causes:

- Producers send bulk requests faster than shards can index.
- Too many concurrent bulk requests.
- Batches are too large, increasing processing time and memory demand.
- Shards/nodes are under heavy load from merges, disk I/O, CPU, or GC.
- Mappings/analyzers/ingest pipelines make each document expensive to process.
- Shard counts or routing concentrate load onto a subset of shards/nodes.
- Searches, aggregations, or other workloads compete with indexing for resources.
- Replicas must process the same write volume and are lagging behind.

A cluster can still report `green` health while the write thread pool is rejecting requests. Cluster health is not the sole indicator of sufficient capacity.

### 2.2. Write/bulk thread pools

Elasticsearch uses thread pools to schedule different kinds of work. Pool names and implementations can change across versions. In modern versions, write operations are typically handled by the `write` thread pool; some older versions or legacy docs mention a `bulk` pool.

You can inspect thread pool statistics:

```http
GET /_nodes/stats/thread_pool
```

Or use the CAT API for a quick overview:

```http
GET /_cat/thread_pool?v
```

Notable fields:

| Field | Meaning |
|---|---|
| `active` | Number of threads actively executing tasks. |
| `queue` | Number of tasks waiting in the queue. |
| `rejected` | Number of tasks rejected. |
| `completed` | Number of tasks completed. |

If `queue` is frequently near its limit and `rejected` rises steadily, producers exceed processing capacity or the cluster has a bottleneck. Do not arbitrarily enlarge queues/thread pools; larger queues can raise latency and memory pressure without improving throughput.

## 3. Distinguishing request-level 429 from item-level 429

This is the most important distinction when handling bulk writes.

### 3.1. Request-level 429

Elasticsearch rejects the entire request before returning per-item bulk results. The application receives HTTP 429 or a corresponding exception instead of a response containing per-operation statuses.

In this case, there is no item-level response indicating which documents succeeded. When the error is confirmed as a request rejection, the entire batch can be retried after backoff. If the response was lost or the error came from a proxy/network, state is uncertain; rely on idempotency and reconciliation.

### 3.2. Item-level 429 in a bulk response

The Bulk API can return a successful request-level HTTP response with `errors: true`. Each item carries its own status:

```json
{
  "took": 35,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-100",
        "status": 201
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-101",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution ..."
        }
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-102",
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
        "_id": "P-103",
        "status": 201
      }
    }
  ]
}
```

In this example:

- `P-100` succeeded.
- `P-101` was temporarily rejected due to overload.
- `P-102` has data incompatible with the mapping.
- `P-103` succeeded.

The application should acknowledge the two successful items, route `P-101` to a bounded retry flow, and route `P-102` to a data error handling flow. Resending all four items wastes resources and can trigger unintended side effects.

### 3.3. Do not infer solely from HTTP status

HTTP status reflects the protocol-level outcome of the request. With the Bulk API, you must read the body and every element in `items`. HTTP 200 does not guarantee all items succeeded; `errors: true` signals that item details must be inspected.

Conversely, if HTTP 429 is received without a bulk response, do not assume the application has a list of failed items. That is a request-level situation.

## 4. Error categories and classification

| Error group | Example | Should retry? | Handling direction |
|---|---|---|---|
| Temporary overload | HTTP 429, `es_rejected_execution_exception` | Yes, bounded | Backoff, jitter, reduce concurrency, and retry. |
| Timeout/connection | Read timeout, connection reset, gateway timeout | Conditional | State may be unknown; retry safely only if operation is idempotent or reconciled. |
| Temporary server error | HTTP 502/503/504 | Conditional | Backoff and bounded retry; check whether request might already be processed. |
| Invalid data | HTTP 400, `mapper_parsing_exception` | Do not retry as-is | Fix data or dead-letter. |
| Request too large | HTTP 413 or payload/request limit error | Do not retry whole batch | Split batch smaller, handle oversized documents. |
| Version conflict | HTTP 409, `version_conflict_engine_exception` | Do not retry blindly | Check version/state and resolve per business rules. |
| Auth/authorization | HTTP 401/403 | Do not retry continuously | Fix credentials/role; stop job. |
| Index/configuration | Index missing, wrong alias, missing pipeline | Do not retry continuously | Fix configuration and recheck. |
| Circuit breaker/resource | `circuit_breaking_exception` | Conditional | Shed load, reduce batch/concurrency, and retry after resources stabilize. |

Classifiers should rely on stable statuses/error types, not arbitrary keyword searches in exception messages. Messages can change across versions and may contain sensitive data.

## 5. Timeouts do not mean a request failed

Timeouts are one of the trickiest cases because the client may not know whether Elasticsearch executed the operation.

Example:

1. The application sends a bulk request.
2. Elasticsearch receives and writes some or all items.
3. The response is delayed or lost on the return path.
4. The client times out waiting and throws a timeout exception.

On the application side, the request failed because no response arrived. On the Elasticsearch side, part or all of the operations may have succeeded.

Therefore, timeouts must be treated as an **indeterminate outcome** unless you know for sure the request was never sent/received.

### 5.1. Types of timeouts to distinguish

| Timeout type | Meaning | What to watch out for |
|---|---|---|
| Connection timeout | Failed to establish connection within allowed time. | Request was likely not sent, though inspect transport and failure phase. |
| Read/response timeout | Client sent request but did not receive response in time. | Server may have processed some or all items. |
| Proxy/gateway request timeout | Intermediary stopped waiting for upstream. | Elasticsearch may continue processing after proxy returns an error. |
| Application deadline/cancellation | Request cancelled due to deadline or client disconnect. | Application-side cancellation does not automatically roll back operations already inside Elasticsearch. |
| Elasticsearch operation timeout | An internal operation did not finish within the configured limit. | Read the exact API and response/error; do not equate with socket timeout. |

Do not use a single timeout setting to describe all layers. HTTP clients, reverse proxies, application deadlines, and API parameters can have different semantics.

### 5.2. Retrying after timeouts requires idempotency

If the operation is indexing a full document with a stable ID and identical source state, resending usually brings the document to the same final state. However, if the operation is incrementing a counter or running an accumulative script, resending can apply side effects twice.

Before retrying a timeout:

- Determine whether the operation is idempotent.
- Use stable IDs or event IDs to identify the operation.
- If versioned, ensure older versions do not overwrite newer versions.
- For non-idempotent updates, check current state or design an idempotency key.
- Reconcile documents by ID/version before resending when needed.

## 6. Handling per-item failures in the Bulk API

A bulk response with `errors: true` is no reason to retry the entire request. Iterate over `items`, confirm successful items, and classify failed items.

Processing flow:

```text
Bulk response
    |
    v
errors == false ? ------ yes -----> Mark all items successful
    |
    no
    v
Inspect each item
    |
    +-- 2xx -----------------------> Acknowledge success
    |
    +-- 429 / transient ----------> Bounded retry queue
    |
    +-- mapping / validation -----> Dead-letter / data correction
    |
    +-- 409 conflict -------------> Business/version conflict handling
    |
    +-- auth/config --------------> Stop and alert
    |
    v
Persist outcomes and checkpoint
```

### 6.1. Preserving correlation between request items and response items

The application must know which command/source record corresponds to each response item. You can use:

- Stable document ID.
- Operation type (index/create/update/delete).
- Source version/event ID.
- Batch sequence and item sequence.
- Routing value if the document uses custom routing.

Do not keep only a list of IDs if the same ID can appear in multiple operations within one batch. Store enough metadata to reconstruct the exact operation needing retry.

Bulk responses preserve item order matching the request operations, yet adapters should still retain command metadata and explicitly match ID/operation to avoid confusion with duplicate IDs or mixed actions.

### 6.2. Acknowledging successful items as soon as outcomes are known

Once the response confirms an item succeeded, record success/checkpoint via the job's durable mechanism. Do not put that item back into the retry queue simply because another item in the same bulk failed.

If the process crashes after Elasticsearch succeeds but before the application saves its checkpoint, the item may be sent again. This is why deterministic IDs, versioning, and idempotent writes are crucial.

### 6.3. Retrying only the failed subset of items

Suppose an initial batch has 1,000 items:

- 985 items succeeded.
- 10 items returned 429.
- 5 items had mapping errors.

Proper handling:

1. Record 985 items as successful.
2. Retry the 10 items with 429 after backoff.
3. Write the 5 mapping-error items to dead-letter, along with protected error codes and source references.
4. Mark the batch complete only when all items have been confirmed successful or durably recorded in error handling per policy.

## 7. Reading Bulk responses with the Elasticsearch Java API Client

When item-level result control is needed, the Elasticsearch Java API Client provides `BulkResponse` with the `errors()` flag and the list of item responses.

General example:

```java
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkResponse response = client.bulk(request);

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            // Acknowledge this item as successful.
            continue;
        }

        int status = item.status();
        String documentId = item.id();
        String errorType = item.error().type();

        if (status == 429) {
            // Persist this item for bounded retry.
        } else if (status == 400) {
            // Send to validation/dead-letter handling.
        } else if (status == 409) {
            // Resolve version/create conflict according to business rules.
        } else {
            // Classify other statuses explicitly.
        }
    }
}
```

This snippet illustrates how to read the response; request types, packages, and accessors may vary by Java API Client version. In production code, retain the mapping between each response item and its original command, and also handle exceptions thrown before a `BulkResponse` is obtained.

Do not log raw `item.error().reason()` if the reason can contain user data. Log sanitized error types/statuses and correlation references; store diagnostic details in controlled locations only when genuinely needed.

## 8. Bulk operations via Spring Data Elasticsearch

Spring Data Elasticsearch exposes bulk APIs through `ElasticsearchOperations`, such as `bulkIndex`, `bulkUpdate`, and `bulkDelete`. These APIs save applications from serializing NDJSON manually.

Example batch indexing:

```java
List<IndexQuery> queries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();

operations.bulkIndex(queries, Product.class);
```

When using Spring Data, read the exact return and exception contract for your pinned version. Some wrappers may throw exceptions on item failures instead of returning a response object similar to the low-level client. If you need per-item status/error types, use the API/exception details provided by that version or place a clean adapter around the Elasticsearch Java API Client.

Do not catch all exceptions and retry the entire batch without distinguishing request-level and item-level errors. Place classification logic in a bulk adapter/service layer so business repositories/services stay decoupled from transport details.

### 8.1. Building an adapter for bulk operations

An abstraction can return standardized results:

```java
public record BulkItemOutcome(
        String documentId,
        int status,
        String errorCode,
        boolean success
) {}

public record BulkWriteResult(
        int submitted,
        List<BulkItemOutcome> items
) {
    public List<BulkItemOutcome> failures() {
        return items.stream().filter(item -> !item.success()).toList();
    }
}
```

The adapter translates client-version-dependent responses/exceptions into the application's `BulkWriteResult`. The retry layer can work against stable statuses/error codes without depending on raw Elasticsearch messages.

In the adapter, do not include raw documents or queries in `BulkItemOutcome`. Retain only metadata needed to retry or dead-letter; payloads must be stored separately and securely.

## 9. Exponential backoff and jitter

When Elasticsearch returns 429, retrying immediately can fill queues even further. Use exponential backoff to increase wait times between attempts.

Illustrative example:

```text
Attempt 1: wait around 200 ms
Attempt 2: wait around 400 ms
Attempt 3: wait around 800 ms
Attempt 4: wait around 1.6 s
Attempt 5: wait around 3.2 s
```

Jitter adds randomness to wait times so multiple workers do not retry simultaneously. One option is full jitter:

\[
delay = random(0, min(maxDelay, baseDelay \times 2^{attempt}))
\]

Values in the example are only starting points. Tune them based on latency, SLAs, cluster load, and job time budgets.

### 9.1. Retry limits

A retry policy should specify:

- Maximum retry attempts.
- Initial backoff and maximum wait duration.
- Overall deadline for an item/job.
- List of retryable statuses/error types.
- Idempotency preconditions.
- Bounded retry queue.
- Handling when retries are exhausted.

Do not retry infinitely. When limits are reached, record the item in a dead-letter store or flag the job for intervention depending on data criticality.

### 9.2. Retry example with Reactor

For reactive workflows, you can use `retryWhen`:

```java
return sendBulk(batch)
        .retryWhen(Retry.backoff(4, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(5))
                .jitter(0.5)
                .filter(this::isRetryableRequestFailure));
```

This is a request-level retry example. It fits only when `sendBulk` emits an error for request-level failures and the operation has safe resend semantics. For item-level failures inside a normal response, classify `items` and create a separate retry publisher for only the failed items; do not use `retryWhen` around the whole publisher to resend the entire batch.

## 10. Backpressure and load shedding on rejections

Retrying is insufficient if producers keep sending faster than Elasticsearch can process. You must regulate the source rate.

Measures include:

- Reducing the number of concurrent in-flight bulk requests.
- Reducing batch size when payloads are large or items are heavy.
- Limiting the number of queued batches.
- Pausing/throttling producers when queues fill up.
- Automatically lowering concurrency when 429 rates climb.
- Gradually raising concurrency once the cluster stabilizes.
- Partitioning load by tenant/routing if a single shard becomes hot.

### 10.1. Bounded queues

A bounded queue enforces backpressure:

```java
BlockingQueue<List<IndexQuery>> queue = new ArrayBlockingQueue<>(4);
```

When four batches are waiting, the producer must wait for consumers to process them instead of allocating more batches. Unbounded queues can cause uncontrolled heap growth when Elasticsearch slows down.

### 10.2. Concurrency limits

With Reactor:

```java
Flux<Void> writes = batches
        .flatMap(batch -> sendBatch(batch), 2);
```

The concurrency parameter caps how many batches execute concurrently. Raising it too high causes the application to generate more requests and buffers than the cluster can handle.

There is no single magic concurrency number for every cluster. Measure throughput, latency, 429s, heap, and queue depth, then step concurrency up or down incrementally.

### 10.3. Simple adaptive concurrency

A controller can reduce concurrency when rejection rates exceed a threshold and increase slowly once the cluster stabilizes:

```text
429 rate rises
      |
      v
Decrease in-flight bulk limit
      |
      v
Wait for cooldown window
      |
      v
Measure latency / queue / rejection
      |
      +---- still overloaded ----> decrease again
      |
      +---- stable --------------> increase slowly
```

Do not increase concurrency right after a single successful batch. Use a sufficiently long measurement window and min/max bounds to avoid continuous oscillation.

## 11. Choosing an appropriate batch size

Oversized batches create huge payloads, consume heap, lengthen processing times, and make a retry costly. Undersized batches create too many requests and network overhead.

Size batches by considering all of:

- Document count.
- Estimated/actual payload size.
- Number of shards receiving data.
- Document size and ingest pipeline cost.
- Latency and rejection rate.
- Client and server memory.

For example, a batch of 500 small documents may be fine, whereas 500 documents with large JSON or nested arrays can be too heavy. Measure byte sizes rather than counting documents alone.

When encountering HTTP 413 or request-too-large errors, lower the batch/byte threshold and retry in smaller chunks. Do not retry the original request at the same payload size.

### 11.1. Splitting failed item sets

If a group of items continues getting rejected even after lowering concurrency, you can split the retry group into smaller batches. This helps when certain documents are very large or put localized pressure on a shard.

Do not split endlessly. Set a minimum batch size and an oversized-document threshold for special handling.

## 12. Idempotency and retry safety

Retries are only reliable if resending the same operation does not corrupt data or create unwanted duplicates.

### 12.1. Using stable document IDs

Example using the business ID as the Elasticsearch `_id`:

```java
IndexQuery query = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build();
```

If the same source record always yields the same `_id`, re-indexing the same state usually overwrites the same document rather than creating a new one.

Do not generate a new UUID on every retry if an event must always update the same document. If the ID changes, retries can create duplicates.

### 12.2. `index` and `create` have different semantics

- `index`: creates a new document or replaces an existing document by ID.
- `create`: creates only; if the ID already exists, it returns a conflict.

With at-least-once delivery, a `create` may succeed on the first try while the response is lost. A retry will hit 409 because the document already exists. The application must verify whether the existing document belongs to the same event/source version before treating the conflict as success.

### 12.3. Accumulative updates are not automatically idempotent

Example script incrementing a count:

```json
{
  "script": {
    "source": "ctx._source.view_count += params.delta",
    "params": { "delta": 1 }
  }
}
```

If the request succeeded but the client timed out and retried, `view_count` can increment twice.

Options:

- Use processed event IDs to skip duplicates.
- Write absolute state instead of increments if the domain allows it.
- Use versions/source sequences to discard stale events.
- Persist durable idempotency records at the application layer.

### 12.4. Optimistic concurrency control

Elasticsearch supports `_seq_no` and `_primary_term` to prevent overwriting documents modified since a read. When updates carry version conditions, 409 conflicts must be resolved per business rules rather than infinitely retrying stale payloads.

If migration/replay relies on source versions, ensure the version reflects authoritative change ordering. Do not use unstable timestamps as versions if events can arrive out of order.

## 13. Handling mapping and validation errors

Mapping errors are usually data errors, not overload:

```json
{
  "type": "mapper_parsing_exception",
  "reason": "failed to parse field [price]"
}
```

For example, the `price` field is mapped as numeric, yet the source sends an unconvertible string. Retrying the same payload will not make the error go away.

Handling procedure:

1. Record the item ID/reference and error type.
2. Identify the failing field/type using sanitized diagnostics.
3. Route the item to a dead-letter queue or a data-correction state.
4. Fix the source/mapping/transform.
5. Reprocess the item with an idempotent operation.

Do not retry 400 errors indefinitely. Nor should you ignore every 400 blindly: it could indicate a broken query/request or configuration bug requiring a job halt.

## 14. Dead-letter queues for unprocessable items

A dead-letter queue (DLQ) stores failed items that cannot be retried automatically or have exhausted their retry budget.

A DLQ record should contain:

- Job/batch ID.
- Document ID or source reference pseudonymized per policy.
- Operation type.
- Error code/type and status.
- Retry attempt count.
- Most recent failure timestamp.
- Source version/event ID.
- Reference to the protected payload if reprocessing is needed.

You do not necessarily need to store raw documents inside the DLQ. If payloads contain PII/secrets, apply encryption, access control, auditing, and short retention. Do not dump raw payloads into application logs as a substitute for a DLQ.

### 14.1. Distinguishing retry queues and DLQs

| Retry queue | Dead-letter queue |
|---|---|
| Holds transient, potentially recoverable errors. | Holds data/logic errors or items with exhausted retry budgets. |
| Has backoff schedules and attempt limits. | Awaits investigation, data fixes, or controlled reprocessing. |
| Processed automatically per policy. | Not automatically retried endlessly. |
| Example: 429, certain timeouts. | Example: mapping parse error, invalid field, conflicts needing business resolution. |

## 15. Timeouts and request cancellation in the application

Timeouts can be configured across multiple layers:

- HTTP client connect timeout.
- HTTP client response/read timeout.
- Connection pool acquire timeout.
- Application request deadline.
- Reverse proxy/gateway timeout.
- Elasticsearch API timeout/operation wait.

Align timeouts around a coherent overall deadline. If a proxy timeout is shorter than the client timeout, the application may only see proxy errors. If an application deadline expires while the client leaves the background request running, the operation may complete after the caller gave up.

### 15.1. Do not stack retries endlessly across layers

If the HTTP client retries 3 times, the service retries 5 times, and the queue consumer retries 10 times, an operation can be resent far more times than expected.

Design a holistic retry budget:

- Pick a primary layer that owns retries.
- Bound retries across client/service/consumer.
- Log attempt count and correlation ID.
- Do not retry concurrently at multiple layers without accounting for total attempts.
- Use idempotency to guard resends.

### 15.2. Distinguishing socket timeouts from server-side `timeout` parameters

An API parameter named `timeout` may control waiting on internal conditions such as shard availability rather than capping how long the HTTP client waits for a response. Read the exact API being called and configure transport timeouts accordingly.

Do not try to fix socket timeouts solely by raising the Elasticsearch `timeout` parameter if the problem lies in the network/client/proxy.

## 16. Monitoring the cluster during 429/rejections

When 429 rates climb, inspect multiple signals together.

### 16.1. Thread pool stats

```http
GET /_nodes/stats/thread_pool
```

Inspect `active`, `queue`, `rejected`, and `completed` for write-related pools. Compare `rejected` counters over time rather than looking at a single snapshot.

### 16.2. Indexing pressure

```http
GET /_nodes/stats/indexing_pressure
```

Indexing pressure signals memory pressure from node indexing activity. Field names and response details vary across Elasticsearch versions.

### 16.3. Cluster and node health

```http
GET /_cluster/health
```

```http
GET /_cat/nodes?v
```

```http
GET /_cat/indices/products?v
```

Check for missing nodes, shard relocations, unassigned shards, disk pressure, or unbalanced load.

### 16.4. Application metrics to record

| Metric | Purpose |
|---|---|
| `bulk_requests_total` | Total bulk requests. |
| `bulk_request_duration` | Bulk request latency. |
| `bulk_items_submitted_total` | Number of submitted items. |
| `bulk_items_succeeded_total` | Number of succeeded items. |
| `bulk_items_failed_total` | Number of failed items. |
| `bulk_rejected_total` | Requests/items hitting 429 or rejections. |
| `bulk_retry_total` | Number of retries. |
| `bulk_dead_letter_total` | Number of items sent to DLQ. |
| `bulk_payload_bytes` | Payload size. |
| `bulk_in_flight` | Concurrent in-flight requests. |
| `bulk_queue_depth` | Number of queued batches. |
| `bulk_timeout_total` | Timeouts by type. |
| `bulk_retry_exhausted_total` | Items that exhausted retry budgets. |

Do not use document ID, customer ID, email, or query string as metric labels because of high cardinality and potential data leakage. Use bounded-value labels such as operation, status class, error category, and index group.

## 17. Safe logging during error diagnosis

On bulk errors, log enough metadata to find the cause:

```java
log.warn(
        "Elasticsearch bulk partially failed index={} batchId={} total={} succeeded={} failed={} retryable={} permanent={} durationMs={}",
        indexAlias,
        batchId,
        total,
        succeeded,
        failed,
        retryable,
        permanent,
        duration.toMillis()
);
```

Avoid logging:

- Full entity/document sources.
- Full Query DSL if it contains user literals.
- Authorization headers/tokens.
- Unclassified raw exception messages.
- Dead-letter payloads containing PII.

For failed items, record error code/type, status, and a pseudonymized reference if log correlation is needed. Sensitive details belong in a controlled error store, not general logs.

## 18. Resilient bulk processing architecture

A pipeline can be organized as follows:

```text
Source database / queue
          |
          v
      Batch builder
   (count + byte limit)
          |
          v
   Bounded in-flight queue
          |
          v
   Bulk request adapter
          |
          v
     Bulk response
          |
     +----+-------------------+
     |                        |
     v                        v
Item successes           Item failures
     |                        |
     v                        +-- retryable -> retry queue
Checkpoint                   |
                              +-- permanent -> DLQ
                              |
                              +-- conflict -> business handler
```

The adapter communicates with Elasticsearch and normalizes outcomes. Retry workers process only classified items. Checkpoints advance only when every item in the batch has been handled or failures have been durably persisted in the right place.

### 18.1. Advancing checkpoints at the right time

Do not commit checkpoints before knowing which items succeeded and which were saved to retry/DLQ. Advancing a checkpoint past failed items without durable failure storage can silently drop data forever.

If a process crashes after Elasticsearch writes succeed but before checkpoint commit, items may be resent. Idempotent operations and deterministic IDs make this safe.

### 18.2. Bounding retry queues

Retry queues must have bounded capacity and appropriate durability. If the queue fills, producers need backpressure or jobs must pause cleanly. Never append all errors into an in-heap `List` and keep reading from the source.

## 19. Example item classification and retry plan

A classifier can map status/error type into categories:

```java
enum FailureCategory {
    RETRYABLE,
    PERMANENT_DATA_ERROR,
    CONFLICT,
    CONFIGURATION_ERROR,
    UNKNOWN
}

FailureCategory classify(int status, String errorType) {
    if (status == 429
            || status == 502
            || status == 503
            || status == 504) {
        return FailureCategory.RETRYABLE;
    }

    if (status == 400
            || "mapper_parsing_exception".equals(errorType)) {
        return FailureCategory.PERMANENT_DATA_ERROR;
    }

    if (status == 409) {
        return FailureCategory.CONFLICT;
    }

    if (status == 401 || status == 403 || status == 404) {
        return FailureCategory.CONFIGURATION_ERROR;
    }

    return FailureCategory.UNKNOWN;
}
```

This classifier is only a starting point. Inspect specific context: HTTP 404 may be index missing (configuration) or document not found (business); 409 may be a create conflict or optimistic concurrency conflict; 429 may be a rejection or circuit breaker. Do not classify solely by status when error type provides necessary context.

Classifier results should feed into policy:

```text
RETRYABLE             -> retry with backoff, within budget
PERMANENT_DATA_ERROR  -> dead-letter and alert/report
CONFLICT              -> read/compare version, then business resolution
CONFIGURATION_ERROR  -> stop affected job and alert
UNKNOWN               -> quarantine, preserve diagnostics safely
```

## 20. When to stop a job instead of retrying?

Not every error should be handled at the item level. Stop the job if:

- Credentials expired or the user lost permissions.
- Target index/alias does not exist or points to the wrong target.
- Mapping/template/pipeline has not been installed.
- Permanent error rate exceeds threshold.
- Retry queue/DLQ cannot write durably.
- Checkpoint store fails, making progress unreliable.
- The cluster suffers prolonged overload and retry budgets are exhausted.
- Source data is inconsistent or version ordering cannot be determined.

Continuing to write under these conditions can produce an incomplete or irreconcilable index.

## 21. Common mistakes

| Symptom | Possible cause | Solution |
|---|---|---|
| HTTP 429 rising steadily | Producer/concurrency exceeds Elasticsearch capacity. | Lower in-flight requests, backoff, and inspect write queue. |
| Bulk returns HTTP 200 yet `errors=true` | Some items failed. | Inspect every `items[]`; retry only retryable items. |
| Retrying whole batch increases load | Successful items are also resent. | Classify response and retry only failed items. |
| Duplicates appear after timeout | Retrying non-idempotent operations or generating new IDs. | Use deterministic IDs/event IDs and versioning. |
| Timeout with unknown state | Response lost after server may have written. | Treat as unknown outcome; reconcile or retry idempotently. |
| Mapping errors retried forever | Permanent and transient errors not distinguished. | Dead-letter and fix data/mapping. |
| 429 persists after enlarging thread pool | Bottleneck is CPU, disk, shards, merges, or indexing pressure. | Measure cluster; throttle producer and fix real bottleneck. |
| Large batches trigger timeout/413 | Payload too large or slow to process. | Reduce batch byte/count size and handle oversized docs separately. |
| Synchronized retries overload cluster | No jitter; many workers retry together. | Exponential backoff + jitter and adaptive concurrency. |
| In-app queue grows unbounded | Producer lacks backpressure. | Bounded queues and limit in-flight batches. |
| Checkpoint skips failed items | Checkpoint committed before persisting retry/DLQ. | Commit only once every item is durably accounted for. |
| `create` retry hits 409 | Prior attempt may have succeeded while response was lost. | Check event/version/document to decide if conflict is an expected duplicate. |
| Logs expose document source on error | Dumping full request/exception. | Log status/error type/counts and sanitized references. |

## 22. 429/rejection/timeout incident checklist

When an incident occurs, follow this order:

1. **Determine failure level:** request-level, item-level, or client timeout/connection.
2. **Read the response:** check HTTP status, `errors`, item statuses, and error types.
3. **Shed load immediately:** lower concurrency/in-flight limits; throttle or pause producers if needed.
4. **Inspect the cluster:** write thread pool queue/rejected, indexing pressure, node health, disk, CPU, and GC.
5. **Classify items:** transient, permanent data error, conflict, configuration, or unknown.
6. **Retry within limits:** retry only eligible requests/items with backoff and jitter.
7. **Ensure idempotency:** deterministic IDs, event IDs, versioning, or reconciliation.
8. **Persist failures:** durably save retry/DLQ items and checkpoints.
9. **Monitor recovery:** rejection rates, latency, retry queue depth, and DLQ counts.
10. **Post-incident reconciliation:** compare source/destination and resolve items that exhausted retry budgets.

## 23. Key points to remember

- HTTP 429 and `es_rejected_execution_exception` typically signal Elasticsearch lacks capacity or is rejecting work.
- Request-level 429 differs from item-level 429 inside a bulk response.
- Bulk responses can return HTTP 200 with `errors=true`; inspect every item.
- Successful items must never be put back into retry solely because another item failed.
- Timeouts can happen after the server has already processed a request; treat state as unknown unless proven otherwise.
- Retries require exponential backoff, jitter, attempt limits, and an overall deadline.
- Retrying 429 must go hand-in-hand with lowering concurrency/backpressure; fast retries do not cure overload.
- Mapping/validation errors are usually permanent and need dead-lettering or data fixes.
- 409 conflicts must be handled per version/operation semantics, not retried blindly.
- Use stable IDs, event IDs, and versioning for safe retries.
- Bounded queues, byte-sized batches, and concurrency limits protect heap/client/cluster.
- Monitor write thread pools, indexing pressure, latency, 429s, retries, and DLQs.
- Do not log raw documents, queries, or exception reasons if they can contain sensitive data.
- Advance checkpoints only once all items are processed or failures are durably saved.

HTTP 429, rejections, timeouts, and per-item bulk failures are distinct signals in a write pipeline. Determine whether the entire request was rejected, individual items failed, or the outcome is unknown due to a timeout; then shed load, classify errors, and retry selectively with idempotency. By combining backpressure, bounded retries, dead-lettering, and durable checkpoints, applications can recover from overload without silently dropping or duplicating data.

## References

- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch — Thread pool settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html)
- [Elasticsearch — Nodes stats API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-nodes-stats.html)
- [Elasticsearch — Indexing pressure](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-indexing-pressure.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html)
