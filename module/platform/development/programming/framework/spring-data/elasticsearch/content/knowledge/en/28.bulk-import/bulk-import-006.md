# Classifying Retryable Errors vs. Invalid Data Errors

When bulk-importing data into Elasticsearch, not every error should be handled the same way. Some errors are transient—caused by cluster overload, unready shards, or interrupted connections. Other errors originate from the submitted data itself, such as wrong field types, missing required values, or invalid JSON. Retrying a record with bad data usually causes the request to fail again; conversely, dropping a transient error can lose data that should have been written.

With the **Bulk API**, a single request can contain many operations, and Elasticsearch processes each item individually. Consequently, the HTTP status of the overall request is not sufficient to conclude whether all records succeeded or failed. The application must inspect the **errors** flag, iterate through every element in **items**, classify failures by status and error type, and decide whether to retry, fix data, route to a quarantine queue, or raise an operational alert.

This lesson uses the **products** index and index, create, and update operations. It focuses on classifying retryable vs. invalid-data errors, handling partial success, backoff, idempotency, dead-letter queues, and Spring Data Elasticsearch implementation patterns.

## 1. Why Must Errors Be Classified?

Suppose an application sends a bulk request containing 500 products. Elasticsearch may successfully write 492 items, reject 5 items because their data violates the mapping, and reject the remaining 3 items because a node is overloaded.

If the application checks only HTTP 200, it might assume all 500 products were written. If the application retries the entire request, the 492 successful items get re-sent, creating duplicate conflicts, overwriting data, or applying quantity-increment scripts multiple times.

Each error class requires a distinct response:

- **Transient errors:** wait for an interval and retry with a cap.
- **Data errors:** quarantine the record and fix the data or mapping before re-sending.
- **Configuration/permission errors:** fix configuration, credentials, or index state.
- **Business conflicts:** re-read state and resolve per rules rather than retrying blindly.
- **Uncertain outcomes:** reconcile state using IDs or idempotency keys before resending.

A sound retry strategy answers three questions for each item:

1. Has Elasticsearch confirmed that the operation succeeded?
2. If it failed, can the root cause disappear on its own without altering the data?
3. If re-sent, could the operation cause duplicate writes or apply an extra mutation?

## 2. The Bulk API Can Partially Succeed

The Bulk API accepts multiple actions in the same request. A response typically includes:

- **errors:** whether at least one item failed.
- **items:** list of results corresponding to the submitted actions.
- Each item contains the operation key such as `index`, `create`, `update`, or `delete`.
- Item results contain status, result, or error depending on the outcome.

Abbreviated response example:

~~~json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "p-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "p-1002",
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
        "_id": "p-1003",
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

- `p-1001` was created.
- `p-1002` was rejected because the `price` value violated the mapping.
- `p-1003` was rejected because Elasticsearch refused execution under resource pressure.

The HTTP status of a bulk request can still be 200 even when some items fail. Therefore, the application must check **errors** and every entry in **items**.

The order of items in the response matches the order of actions in the request. Use IDs for explicit correlation as well; do not rely solely on position if the application transformed or filtered the list mid-processing.

## 3. Classify by Cause, Not Just Status

Status codes guide initial routing, but a single status can cover multiple root causes. Combine:

- HTTP status or per-item status.
- **error.type**.
- **error.reason**.
- Submitted operation (`index`/`create`/`update`/`delete`).
- State of the index, shards, and cluster.
- Whether the request might have executed before a client timeout occurred.

The table below provides a starting classification, not an absolute rule for every version or cluster:

| Category | Example Status/Type | Handling Approach |
|---|---|---|
| Temporary rejection due to overload | 429, `es_rejected_execution_exception` | Retry with backoff and reduce pressure |
| Shard or cluster temporarily unavailable | Some 503 errors, `unavailable_shards_exception` | Retry with limits after checking cluster state |
| Gateway or network error | 502, 503, 504, connection reset | Can retry; first account for possible already-written state |
| Request timeout | 408 or client timeout | Outcome may be uncertain; reconcile and retry idempotently |
| Invalid data | 400, `mapper_parsing_exception`, `document_parsing_exception` | Do not retry as-is; quarantine and fix data |
| Malformed query or payload | 400, `parse_exception`, `x_content_parse_exception`, `illegal_argument_exception` | Fix the request or producer |
| Script error | 400, `script_exception` | Fix script or params; do not retry as-is |
| Document already exists in create-only | 409, `resource_already_exists_exception` | Handle duplicate according to business policy |
| Version conflict | 409, `version_conflict_engine_exception` | Re-read, recompute, or apply appropriate retry policy |
| Missing document on update/delete | 404, `document_missing_exception` | Verify ID and semantics; do not retry by default |
| Index does not exist | 404, `index_not_found_exception` | Check provisioning/alias; retry only after index is created |
| Unauthorized / Forbidden | 401 or 403 | Fix credentials/permissions; do not retry continuously |
| Request too large | 413 or equivalent payload error | Split bulk smaller; check individual document sizes |
| Cluster block | Read-only or disk watermark block | Resolve the operational cause before resending |

Status 429 normally indicates resource pressure or temporary request rejection. However, if the same single document always triggers a circuit breaker due to excessive size, fast retries will not solve the problem. Conversely, a 404 `index_not_found` might be transient during index deployment, yet a configuration error if the index or alias name is permanently wrong.

## 4. Common Retryable Errors

The following errors can typically be retried after waiting, provided retries are bounded and the operation is safe to repeat:

### 429 Too Many Requests

Elasticsearch can return 429 when a thread pool rejects a request because its queue or node is under load. In the Bulk API, individual items may carry **`es_rejected_execution_exception`**.

How to handle:

- Pause before resending.
- Use exponential backoff with jitter.
- Lower the number of concurrent bulk requests.
- Reduce batch size if requests are too large or take too long.
- Monitor thread pool rejections, CPU, heap, and indexing rate.

Do not add more workers to "push through faster" when the cluster is returning 429s. That generates even more rejected requests and worsens the situation.

### 503 and Unready Shards

Some 503 errors or **`unavailable_shards_exception`** can appear when shards are not yet active, nodes are starting, or the cluster is recovering. You can retry after checking cluster status.

If the index was never created or shards cannot allocate due to misconfiguration, infinite retries will not help. Distinguish a recovering incident from a provisioning failure.

### 502, 504, and Network Errors

Gateways may return 502/504, or clients may encounter connection resets, socket timeouts, or connection failures. In these cases, the client cannot tell whether Elasticsearch processed the request.

This is an **uncertain outcome**. A request might have written successfully while the response was lost in transit. Retry only when the operation is idempotent or the application can reconcile state.

### Timeouts

Search/index/bulk requests can time out at the client, proxy, or server layer. Determine which timeout occurred:

- Client timeout: the client stopped waiting for a response.
- Gateway timeout: the proxy stopped waiting for upstream.
- Server timeout or task cancellation: the request may have been cancelled or partially completed depending on the API.

Never assume a timeout means no data was written. Check by ID, operation key, or data source before replaying.

## 5. Common Invalid-Data Errors

Data errors usually reproduce consistently when sending the same payload. Therefore, do not retry them as-is.

### Wrong Data Type for the Mapping

The mapping declares `price` as `double`, yet the producer sends a non-convertible string:

~~~json
{
  "sku": "KB-1001",
  "price": "ninety dollars"
}
~~~

Elasticsearch can return **`mapper_parsing_exception`**. Fix the producer or the data before resending.

### Missing or Invalid Field Structure

An index may set **`dynamic: strict`**, requiring fields to strictly match the schema. A document sending an unexpected field or invalid nested structure can be rejected.

~~~json
{
  "sku": "KB-1001",
  "unknownField": "unexpected"
}
~~~

With strict mapping, this is a schema error, not a network glitch.

### Malformed Dates

If the mapping expects dates in a configured format and the producer sends an invalid date, the document fails parsing. Standardize date, timezone, and formatting at the source.

### Unsupported Enum Values

The application only accepts `ACTIVE` and `INACTIVE`, but a producer sends `ARCHIVED` in a field constrained by a pipeline or validation. Update the data contract or transform values before writing.

### Malformed JSON or NDJSON

Bulk requests use NDJSON: each action metadata object sits on one line and the source/update body sits on the following line when needed. Missing trailing newlines, bad structure, or broken serialization can cause the request to be rejected. This is a producer/request bug, not a transient failure.

## 6. Distinguishing Data Errors from Mapping Errors

Not every **`mapper_parsing_exception`** means the source record is wrong. The root cause can be:

- The producer sent a value of the wrong type.
- The current mapping does not fit the business schema.
- An older index has a different mapping from a newer index.
- Dynamic mapping inferred an unsuitable type from the first document.
- An alias points to multiple indices with inconsistent mappings.
- A nested/object field has an unexpected structure.

Before patching individual records, inspect the actual mapping:

~~~http
GET /products/_mapping
~~~

Inspect the offending document and compare it against the producer schema. If the mapping itself is wrong, fix the mapping using the proper workflow (typically creating a new index and reindexing when field types must change), then replay quarantined records.

Do not retry thousands of documents into an index with a broken mapping. Fix the shared root cause first before replaying.

## 7. Initial Retry Decision Table

Use the following table as an initial policy, then tune for your error types and operational needs:

| Status / Error Type | Auto-Retry? | Conditions |
|---|---|---|
| 429 `es_rejected_execution_exception` | Yes | Backoff, reduce concurrency, and cap attempts |
| 503 `unavailable_shards_exception` | Yes | Cluster/shards recovering; time-bounded |
| 502 / 504 | Conditional | Outcome may be uncertain; operation must be idempotent or reconciled |
| Client connection timeout | Conditional | Do not assume request went unprocessed |
| 400 `mapper_parsing_exception` | No | Fix document or mapping |
| 400 `document_parsing_exception` | No | Fix structure or values |
| 400 `x_content_parse_exception` | No | Fix JSON/NDJSON |
| 400 `script_exception` | No | Fix script or params |
| 401 / 403 | No | Fix permissions or credentials |
| 404 `document_missing_exception` | Not by default | Check ID and upsert requirements |
| 404 `index_not_found_exception` | Only during intentional provisioning | Wait for index/alias readiness; do not retry infinitely |
| 409 `resource_already_exists_exception` | No | Handle duplicate / create-only policy |
| 409 `version_conflict_engine_exception` | Conditional | Re-read and recompute, or use `retry_on_conflict` when semantics allow |
| 413 Payload Too Large | Do not resend same bulk | Split smaller; handle oversized documents separately |
| Cluster read-only/block | Wait before retry | Resolve disk watermark or block first |

Do not use status code alone as the final classifier. Record error type and operation so you can refine rules accurately as new errors appear.

## 8. Handling Partial Success: Retry Only Failed Items

A bulk request can contain both successful and failed items. The application should build a separate retry list solely from items needing retry.

General flow:

~~~text
Build bulk request
       |
       v
Send to Elasticsearch
       |
       v
Read response.items
       |
       +---- item succeeded -------> record success
       |
       +---- retryable error ------> retry queue
       |
       +---- data error -----------> quarantine / DLQ
       |
       +---- configuration error --> alert and pause pipeline
~~~

Do not resend all 500 items just because one item returned status 400. Doing so wastes resources and can trigger unintended side effects.

Example response with 100 items:

- 93 items succeeded.
- 4 items failed mapping.
- 3 items hit 429.

The application should record 93 successes, move the 4 mapping failures to quarantine, and retry only the 3 429 items after backoff.

Retain the original payload and action metadata so you can accurately reconstruct each item's request. For bulk updates, an action's metadata and body span two NDJSON lines; when splitting items out, keep the action/body pair intact.

## 9. Exponential Backoff and Jitter

If multiple workers receive 429 at once and all retry after exactly one second, they will resend simultaneously and get rejected again. This causes a retry storm.

**Exponential backoff** increases wait duration across attempts:

\[
d_n = \min(d_{\max}, d_0 \times 2^n)
\]

Where:

- \(d_0\) is the initial delay.
- \(n\) is the number of retries already performed.
- \(d_{\max}\) is the maximum cap.

**Jitter** adds randomness so workers do not synchronize their retry timing.

Full jitter example:

\[
wait_n = random(0, \min(d_{\max}, d_0 \times 2^n))
\]

Illustrative configuration:

| Retry Attempt | Max Wait Window |
|---|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |

These are examples, not mandatory numbers. Respect `Retry-After` if a proxy or service layer supplies an appropriate header. Configure:

- Maximum retry count.
- Maximum total retry duration.
- Maximum wait interval.
- Retry worker concurrency limit.
- Policy for moving items to a DLQ once the retry budget is exhausted.

Do not retry continuously in a tight loop without delay. That burns CPU and intensifies cluster overload.

## 10. Reducing Batch Size on Overload or Oversized Payloads

Batch size affects how much data travels in one request. Oversized bulks increase memory usage, processing duration, and timeout probability. Conversely, tiny batches increase network overhead.

If you receive 413 or request-too-large errors, split the bulk into smaller chunks. If a single document is huge, splitting the bulk won't solve that document; examine source size, field limits, or storage design.

An adaptive strategy:

1. Start with a batch sized by target item count and total bytes.
2. On 429, reduce concurrency first; also shrink batch size if requests are generating heavy pressure.
3. On 413, halve the batch and resend smaller chunks.
4. If an item still fails on its own, quarantine that item.
5. When the cluster stabilizes, raise batch size gradually if throughput needs improvement.

Cap both **item count** and **total byte size**. 500 small documents and 500 documents with huge sources produce very different requests.

No single optimal batch size fits all clusters. Measure heap, CPU, indexing throughput, rejections, and latency under representative load.

## 11. Idempotency Determines Whether Retries Are Safe

An idempotent operation can be repeated without causing unintended changes to the final state. This is crucial when the client times out and does not know whether the request was processed.

| Operation | Behavior When Resent | Notes |
|---|---|---|
| `index` full document with fixed ID and identical payload | Usually idempotent in final `_source` | Watch out for pipelines, versions, and external side effects |
| `update` setting `status = ACTIVE` | Usually idempotent | Re-applies the same value |
| `update` script `stock += 1` | Not idempotent | Retry can increment an extra time |
| `create`-only with fixed ID | No duplicates created; repeat may return 409 | Distinguish when the first request succeeded but response was lost |
| `delete` with same ID | Usually idempotent in final state | Decide whether 404 is an acceptable outcome |
| Upsert partial doc setting fixed values | Usually idempotent for assigned fields | Watch out for scripts and other concurrent field changes |

Non-idempotent script example:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

If the request already increased stock from 20 to 21 but the response was lost, resending can bump it to 22. Retrying after a timeout without an idempotency key corrupts data.

### Using Event IDs to Prevent Duplicate Application

For business events like inventory receipts, every event should carry a deterministic ID. The application can record processed event IDs or use a data model ensuring each event applies once. Implementation depends on system design; the product document ID alone cannot distinguish two legitimate inventory receipts from one duplicated retry.

Do not confuse **`retry_on_conflict`** with idempotency. `retry_on_conflict` handles version conflicts inside the Update API; it does not deduplicate two identical business messages redelivered from a queue.

## 12. Handling 409 Create Conflicts and Version Conflicts

Status 409 can carry multiple meanings.

### `resource_already_exists_exception`

Typically occurs with **`create`** actions when the ID already exists. This is not an overload error. Handling options:

- If business rules require create-only: report duplicate or mark record as existing per policy.
- If a prior request may have succeeded with a lost response: fetch the document and compare event key/version/payload to confirm the outcome.
- If updating existing documents is intended: use update/upsert with the right semantics.

Do not automatically treat every create conflict as a successful duplicate. Two documents sharing an ID with different contents could be a data conflict requiring investigation.

### `version_conflict_engine_exception`

This typically arises when optimistic concurrency or concurrent updates advance the version. Handle by:

- Re-reading the document and recomputing changes against the newer `_source`.
- Using `retry_on_conflict` for updates whose logic supports it.
- Returning a conflict to the caller if user resolution is needed.
- Using `if_seq_no` and `if_primary_term` when guarding a previously read version.

Do not retry a stale partial update if it could overwrite newer changes. Clarify whether an update sets absolute values, computes from current state, or requires compare-and-set.

## 13. Dead-Letter Queues and Quarantine

A **Dead-Letter Queue (DLQ)** stores items that cannot be processed further under current policy. It lets the pipeline continue processing healthy items while preserving failed ones for investigation or replay.

A DLQ record should store sufficient context:

~~~json
{
  "eventId": "evt-90812",
  "index": "products",
  "documentId": "p-1002",
  "operation": "index",
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "errorReason": "failed to parse field [price]",
  "attempts": 1,
  "firstFailedAt": "2026-11-13T10:00:00Z",
  "lastFailedAt": "2026-11-13T10:00:00Z",
  "payload": {
    "sku": "KB-1002",
    "price": "ninety dollars"
  }
}
~~~

This is an illustrative structure. Real DLQs need schema version, message source, trace/correlation ID, last attempt info, and processing state.

Distinguish two paths:

- **Retry queue:** items likely to succeed after waiting or once the cluster recovers.
- **Quarantine/DLQ:** items requiring human intervention or data/mapping/config fixes before replay.

Do not store passwords, access tokens, or unnecessary sensitive data in logs or the DLQ. Payloads may hold personal data or business secrets; apply proper access controls, retention, and masking.

### Replaying the DLQ

Once the root cause is fixed:

1. Pull a batch of items from the DLQ.
2. Verify schema/version and payload.
3. Transform or fix the data if needed.
4. Resend with a stable ID and idempotency key.
5. Inspect each item in the bulk response.
6. Mark replays successful or retain new failures.
7. Record replay history to avoid uncontrolled reprocessing.

Do not replay millions of items all at once right after fixing a mapping. Start with a small sample, verify the outcomes, and scale up gradually.

## 14. Request-Level Errors vs. Item-Level Errors

Separate requests that fail before producing item outcomes from per-item errors inside a response.

### Request-Level Failure

Examples:

- Unable to connect to Elasticsearch.
- Request rejected by a proxy.
- Invalid credentials.
- Request-wide malformed NDJSON syntax.
- Index or alias missing and request rejected upfront.
- Client timed out with no response received.

In these cases, the application may lack a list of succeeded/failed items. If the request might have reached the server, the outcome is uncertain.

### Item-Level Failure

Elasticsearch returns a bulk response with `items`, where each action has its own result. You can identify which items succeeded, which failed, and retry selectively.

Processing logic should maintain both layers:

~~~text
Send BulkRequest
      |
      +-- No BulkResponse received
      |       |
      |       +--> Request-level failure
      |              |
      |              +--> Determine if outcome is certain
      |              +--> Retry/reconcile per idempotency
      |
      +-- BulkResponse received
              |
              +--> errors = false: mark completed
              |
              +--> errors = true:
                       iterate each item
                         |
                         +--> success
                         +--> retryable
                         +--> invalid / conflict / config
~~~

Do not use the exact same exception handler for both cases. A request-level timeout does not tell you which items were processed; an item-level response gives exact details for targeted retry.

## 15. Example Java Item Classification

A simple model can map response items to actions:

~~~java
enum FailureAction {
    SUCCESS,
    RETRY,
    QUARANTINE,
    CONFLICT,
    CONFIGURATION_ERROR,
    INVESTIGATE
}
~~~

Illustrative classification function:

~~~java
FailureAction classify(int status, String errorType) {
    if (status >= 200 && status < 300) {
        return FailureAction.SUCCESS;
    }

    if (status == 429
            || status == 502
            || status == 503
            || status == 504) {
        return FailureAction.RETRY;
    }

    if (status == 400) {
        return FailureAction.QUARANTINE;
    }

    if (status == 401 || status == 403) {
        return FailureAction.CONFIGURATION_ERROR;
    }

    if (status == 409) {
        if ("resource_already_exists_exception".equals(errorType)) {
            return FailureAction.CONFLICT;
        }
        if ("version_conflict_engine_exception".equals(errorType)) {
            return FailureAction.CONFLICT;
        }
    }

    if (status == 404) {
        return FailureAction.QUARANTINE;
    }

    return FailureAction.INVESTIGATE;
}
~~~

This is only an initial skeleton. Production code must examine error type, operation, index state, and business policy. For example:

- 404 `index_not_found` may require pausing the pipeline to wait for provisioning rather than dumping every document into a DLQ.
- 404 `document_missing` on a non-upsert update may be a data or semantics issue.
- 400 circuit breaker or resource error may require investigation rather than treating the record as malformed.
- 409 version conflict might be retried after re-reading if business logic permits.
- 429 requires backoff and load reduction.

Isolating classification into a dedicated service makes adding new error types clean without scattering status conditionals across code.

## 16. Reading Each Item from the Elasticsearch Java API Client

With the Elasticsearch Java API Client, a bulk response provides the **`errors()`** flag and the **`items()`** list. Each item holds status and error details on failure.

Example processing skeleton:

~~~java
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkResponse response = elasticsearchClient.bulk(bulkRequest);

if (!response.errors()) {
    recordAllSuccessful(response.items());
} else {
    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            recordSuccess(item);
            continue;
        }

        int status = item.status();
        String errorType = item.error().type();
        String reason = item.error().reason();

        FailureAction action = classifier.classify(
                status,
                errorType
        );

        switch (action) {
            case RETRY -> retryQueue.enqueue(
                    item,
                    status,
                    errorType,
                    reason
            );
            case QUARANTINE -> deadLetterQueue.store(
                    item,
                    status,
                    errorType,
                    reason
            );
            case CONFLICT -> conflictHandler.handle(
                    item,
                    errorType,
                    reason
            );
            case CONFIGURATION_ERROR ->
                    pipeline.pauseAndAlert(errorType, reason);
            case INVESTIGATE ->
                    incidentQueue.store(item, status, errorType, reason);
            case SUCCESS -> recordSuccess(item);
        }
    }
}
~~~

This snippet illustrates the processing structure. In real applications, `item` is metadata/result for the bulk action and does not necessarily include the original source payload. Retain the original list of operations and payloads by ID or correlation key so retries and the DLQ have complete data.

Package names, generic types, and getter signatures in the Java API Client can differ across versions. Use dependencies compatible with your project's cluster and Spring Boot version; verify status/error types in your managed client before putting the snippet into a build.

### Correlating Responses with Submitted Payloads

Before sending the bulk request, build a structure holding payload and metadata:

~~~java
record PendingOperation(
        String eventId,
        String documentId,
        String operation,
        ProductDocument payload
) {
}
~~~

When building `BulkRequest`, keep the `PendingOperation` list in the exact same order. Response items arrive in action order and can be correlated by position, ID, and operation. Even better, carry an `eventId`/correlation ID at the application layer to record outcomes.

Do not use `error.reason` as a unique key. Two different documents can fail with the same error type while requiring separate handling.

## 17. Integrating with Spring Data Elasticsearch

Spring Data Elasticsearch provides bulk APIs such as **`bulkIndex`**, **`bulkUpdate`**, and **`bulkDelete`** via `ElasticsearchOperations`, depending on the version. These APIs convert entities or query objects using Spring Data abstractions.

Common `bulkIndex` pattern:

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
                BulkOptions.defaultOptions(),
                IndexCoordinates.of("products")
        );
~~~

This illustrates bulk indexing through `Operations`. Return contracts and error reporting can change across versions and overloads. If the API throws an exception when items fail, inspect the cause and available bulk error details; never assume the entire batch failed or succeeded.

When exact per-item classification is required—especially preserving error type and status per operation—the Elasticsearch Java API Client offers more direct control via `BulkResponse`.

### Retaining Payloads for Retry

When using Spring Data, do not discard the entity list right after calling bulk. Keep the original batch or operation envelope until every item is confirmed successful or moved to retry/DLQ.

A service might be structured as:

~~~java
public void ingest(List<ProductDocument> batch) {
    try {
        bulkWriter.write(batch);
    } catch (RuntimeException exception) {
        failureHandler.handleBatchFailure(batch, exception);
    }
}
~~~

This is only the outer flow skeleton. If `bulkWriter` does not provide item-level outcomes, `failureHandler` must inspect the exception or re-send under a controlled strategy. For systems needing exact partial-success tracking, use an API that returns individual item results rather than only a broad exception.

Never catch `Exception` and ignore it. Every item must reach an auditable terminal or tracked state: succeeded, queued for retry, quarantined, conflict pending resolution, or pipeline paused.

## 18. What Should a Retry Queue Store?

A retry item should include:

- Original payload or a reference to durable payload storage.
- Target index/alias.
- Document ID.
- Operation type (`index`/`create`/`update`/`delete`).
- Event ID or idempotency key.
- Latest error status and error type.
- Retry attempt count.
- First failed timestamp and latest failed timestamp.
- Next eligible retry timestamp.
- Schema version.
- Trace/correlation ID.
- Partition/offset metadata if sourced from a message broker.

Example envelope:

~~~json
{
  "eventId": "evt-90813",
  "index": "products",
  "documentId": "p-1003",
  "operation": "index",
  "attempt": 2,
  "nextAttemptAt": "2026-11-13T10:00:08Z",
  "lastError": {
    "status": 429,
    "type": "es_rejected_execution_exception"
  },
  "schemaVersion": 4,
  "payloadRef": "object-store://ingest/evt-90813"
}
~~~

If payloads are large or sensitive, store the payload in access-controlled storage and store only a reference in the queue. Ensure the payload remains retained until the item finishes processing.

The retry queue should have capacity bounds and a retention policy. Continuous queue growth signals the pipeline cannot keep up or the cluster has an ongoing problem.

## 19. Capping Retries and Preventing Retry Storms

Retries cannot run forever. An operational policy should define:

- Maximum retry attempts, e.g., 5 attempts.
- Maximum total retry duration, e.g., 10 minutes.
- Exponential backoff with jitter.
- Maximum retry workers.
- Retry volume ratio relative to normal ingestion.
- Conditions for pausing the pipeline when error rates cross a threshold.
- Criteria for moving items to the DLQ.

These numbers are illustrative examples only. Choose values based on SLAs, cluster recovery speed, and data freshness deadlines.

If entire bulk batches continuously return 429, throttle the producer, lower concurrency, or pause message consumption. If only specific shards are under pressure, examine shard distribution and node balance rather than only throttling the entire system.

An application-level circuit breaker can pause new requests when transient error rates exceed a threshold. Once the cluster recovers, allow a small number of probe requests before reopening full throughput.

## 20. Handling Missing Indices and Configuration Errors

Not all non-data errors should be retried automatically.

For example, **`index_not_found_exception`**:

- If a deployment just created the index and the job started ahead of provisioning, waiting briefly for the index may make sense.
- If the index name is wrong, the alias does not exist, or environment config is missing, retries will not fix it.
- If an index was accidentally deleted, an intentional recovery or recreation process is required.

For 401/403, inspect credentials, roles, and index permissions. Do not keep firing thousands of requests when the account lacks access.

For cluster blocks caused by disk watermarks or read-only indices, resolve storage capacity or the block first. Continuous retries while disks are full only inflate logs and queues.

If a configuration error impacts the entire pipeline, **pause** the consumer or worker and raise an alert. Do not dump every document into the DLQ when payloads themselves may be completely valid.

## 21. Validating Data Before Sending Bulk Requests

Application-side validation catches predictable errors early:

- ID is non-empty and follows conventions.
- Required fields are present.
- Numeric values fall within valid bounds.
- Date/time strings use a consistent format.
- Enums belong to the supported set.
- Strings do not exceed business limits.
- Nested objects and arrays have valid structure.
- Schema version is supported.
- Operation type is valid.

Example:

~~~java
public void validate(ProductDocument product) {
    if (product.id() == null || product.id().isBlank()) {
        throw new InvalidProductException("Product ID is required");
    }

    if (product.sku() == null || product.sku().isBlank()) {
        throw new InvalidProductException("SKU is required");
    }

    if (product.price() == null || product.price() < 0) {
        throw new InvalidProductException("Price must be non-negative");
    }

    if (product.stock() == null || product.stock() < 0) {
        throw new InvalidProductException("Stock must be non-negative");
    }
}
~~~

Application validation does not replace Elasticsearch mappings. It reports errors closer to the source with clearer messages for producers.

If validation fails before sending a request, the record can be quarantined without spending Elasticsearch resources. Store structured validation errors such as field, rule, and appropriately masked values.

## 22. Classifying Errors by Operation Type

The same status code can mean different things depending on the operation.

| Operation | Error | Interpretation |
|---|---|---|
| **index** | 409 version conflict when using external versioning | Source version arrived late or out of order |
| **create** | 409 resource already exists | ID already exists; duplicate or previous request succeeded |
| **update** | 404 document missing | Document does not exist and upsert is disabled |
| **update** | 409 version conflict | Concurrent update occurred or version precondition no longer holds |
| **delete** | 404 document missing | May be an acceptable outcome if delete is business-idempotent |
| **any operation** | 429 rejected execution | Resource pressure; retryable after backoff |
| **index/update** | 400 mapper parsing | Payload or mapping incompatible |

For instance, a 409 on `create` should not be treated identically to a 409 version conflict on `update`. One means the ID already exists; the other means the document version changed during an update.

Similarly, a 404 on `delete` can be considered success by final state if the requirement is "ensure the document does not exist." Yet a 404 on an update without upsert normally indicates a missing target document. Decide based on business semantics, not status code alone.

## 23. Data Ordering and Late-Arriving Events

When ingesting from a message broker or multiple producers, the same document can receive events out of order. An older event arriving after a newer event can overwrite newer data if using `index` with a fixed ID and no version control.

Options:

- Use external versioning or an appropriate version type matching the source model.
- Use a business sequence/timestamp and apply only newer events.
- Use a script checking the version inside `_source` before updating.
- Use optimistic concurrency when the client reads before updating.
- Route conflicting events to a reconciliation workflow.

Do not use Elasticsearch receipt time instead of business event time if producers can deliver late. Source timestamps must be well-defined and synchronized.

If using external versioning, understand `external` vs. `external_gte` semantics before deploying. `external_gte` allows equal versions to overwrite under its condition; this can fit idempotent replays, yet can also mask two different payloads sharing the same version. Establish clear versioning rules.

## 24. Monitoring Ingestion and Alerting

An ingestion pipeline should track at least:

- Items submitted.
- Items succeeded.
- Items failed by status and error type.
- Retry rate.
- Items in the retry queue.
- Items in the DLQ/quarantine.
- Age of the oldest item in queues.
- Average and maximum retry counts.
- Bulk latency and bytes/request.
- Rate of 429s and rejected executions.
- Count of 400 mapper parsing errors by index/field.
- Count of 409 create conflicts and version conflicts.
- Count of timeouts / uncertain-outcome requests.
- Cluster heap, CPU, disk, and indexing pressure.

Break out metrics by **error type** and **index** so mapping errors isolated to one dataset stand out immediately. Do not emit only a single generic `bulk_failed` counter.

### Example Dashboard

| Metric | Meaning |
|---|---|
| `bulk_items_total` | Total items processed |
| `bulk_items_succeeded_total` | Succeeded items |
| `bulk_items_retry_total` | Items currently or previously retried |
| `bulk_items_quarantined_total` | Quarantined items |
| `bulk_retry_queue_depth` | Retry queue depth |
| `bulk_dlq_depth` | Items awaiting investigation |
| `bulk_request_duration` | Duration per bulk request |
| `bulk_item_failure{type,status}` | Failures by error type and status |
| `bulk_payload_bytes` | Bulk request size |
| `bulk_unknown_outcome_total` | Timed-out or lost-response requests needing reconciliation |

Alert when retry queue depth grows steadily, DLQ exceeds thresholds, 429 rate climbs, or mapping errors spike right after a deployment.

## 25. Example Ingestion Flow with Retry and DLQ

An ingestion service can separate responsibilities:

~~~java
public void processBatch(List<PendingOperation> operations) {
    BulkOutcome outcome = bulkWriter.execute(operations);

    for (ItemOutcome item : outcome.items()) {
        switch (item.action()) {
            case SUCCESS -> successRecorder.record(item);
            case RETRY -> retryQueue.schedule(
                    item.originalOperation(),
                    item.nextAttemptAt()
            );
            case QUARANTINE -> deadLetterQueue.store(
                    item.originalOperation(),
                    item.failure()
            );
            case CONFLICT -> conflictResolver.resolve(item);
            case PAUSE_PIPELINE -> pipelineController.pause(
                    item.failure()
            );
        }
    }
}
~~~

The **`BulkOutcome`**, **`ItemOutcome`**, **`PendingOperation`**, and queue interfaces here are application models, not built-in Spring Data Elasticsearch classes.

Separating components ensures:

- Bulk writer handles only sending and collecting responses.
- Classifier determines error categories.
- Retry queue schedules retries.
- DLQ stores invalid data.
- Conflict resolver handles duplicates or version conflicts.
- Pipeline controller halts ingestion on system-wide configuration failures.
- Metrics record outcomes per item.

Do not cram retry logic, mapping validation, queuing, and HTTP response handling into one giant loop. When a new error type appears, you can add rules without rewriting the whole pipeline.

## 26. Testing Error Classification

Test both the classifier and bulk response handling behavior.

### Unit Tests for the Classifier

~~~java
@Test
void classifiesRejectedExecutionAsRetryable() {
    assertEquals(
            FailureAction.RETRY,
            classifier.classify(
                    429,
                    "es_rejected_execution_exception"
            )
    );
}

@Test
void classifiesMappingErrorAsQuarantine() {
    assertEquals(
            FailureAction.QUARANTINE,
            classifier.classify(
                    400,
                    "mapper_parsing_exception"
            )
    );
}

@Test
void classifiesCreateDuplicateAsConflict() {
    assertEquals(
            FailureAction.CONFLICT,
            classifier.classify(
                    409,
                    "resource_already_exists_exception"
            )
    );
}
~~~

### Testing Partial Success

Construct a mock response containing:

- One successful item.
- One 400 mapper parsing item.
- One 429 rejected execution item.

Verify:

- The successful item is not resent.
- The 400 item is routed to DLQ/quarantine.
- The 429 item is scheduled for retry.
- Item counts and IDs at each destination are exact.

### Integration Tests

Against a compatible Elasticsearch instance, you can:

- Send a valid document.
- Send a document with a type mismatch against the mapping.
- Send `create` twice with the same ID.
- Trigger a concurrent update conflict.
- Verify the bulk response has `errors` and matching item statuses.

Do not rely solely on mocks to verify Elasticsearch error types. Error types and response details must be verified via integration tests against your real cluster version or a compatible environment.

## 27. Common Implementation Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Bulk HTTP 200 yet missing data | Not checking `errors` and individual items | Iterate all `items` |
| Whole batch retried | Not separating succeeded and failed items | Retry only failed items |
| Repeated 400s | Retrying payloads with broken mapping/JSON | Quarantine and fix data |
| 429s spike after enabling retries | Synchronized retries without backoff | Exponential backoff, jitter, reduce concurrency |
| Inventory doubled | Retrying increment script after timeout | Idempotency keys or event deduplication |
| Create retry returns 409 | First request may have succeeded or ID already existed | Reconcile document and event ID |
| Continuous 409s on update | Write contention or stale version | Re-read, recompute, or adjust concurrency |
| Retry queue never drains | Persistent config or cluster failure | Pause pipeline and fix root cause |
| DLQ spikes after deploy | Producer/schema incompatible with mapping | Check schema version and mapping, replay after fixing |
| Bulk times out without knowing what wrote | Response lost after server execution | Reconcile by ID/version/event key |
| Items lost when splitting retries | Original payload/action not retained | Store operation envelope until completion |
| All errors logged as invalid data | Classifier inspects only top-level exception | Classify request-level and item-level errors separately |

## 28. Operational Workflow When Bulk Encounters Errors

When a batch partially fails, follow this order:

1. **Determine whether a `BulkResponse` was received.** If not, classify as request-level and treat the outcome as potentially uncertain.
2. **Read `errors`.** If false, mark the batch successful per response.
3. **Iterate every item.** Save ID, operation, status, error type, and reason.
4. **Mark succeeded items.** Do not enqueue them for retry.
5. **Classify failed items.** Retryable, invalid data, conflict, config, or needs investigation.
6. **Schedule retries.** Use backoff, jitter, attempt caps, and time limits.
7. **Quarantine invalid data.** Save structured payload and error context in the DLQ/quarantine.
8. **Pause on widespread config errors.** Stop flooding an index or cluster in an invalid state.
9. **Reconcile uncertain outcomes.** Use ID, version, or event key to check before replaying.
10. **Monitor and report.** Emit metrics by error type, index, and producer.
11. **Fix the root cause.** Mapping, producer, permissions, cluster capacity, or concurrency logic.
12. **Replay under control.** Start with a small group and verify per-item results.

## 29. Principles for Designing a Retry Policy

- Do not retry every exception.
- Do not use HTTP 200 to conclude the entire bulk request succeeded.
- Distinguish request-level failures from item-level failures.
- Retry only items with potentially recoverable causes.
- Do not retry mapping, JSON, validation, or script errors as-is.
- Use error type alongside status and operation to classify.
- Retry only failed items when the response exposes per-item outcomes.
- Use exponential backoff and jitter to avoid retry storms.
- Cap attempts, elapsed time, and concurrency.
- Ensure idempotency or reconcile before retrying requests with uncertain outcomes.
- Handle create conflicts and version conflicts per their distinct semantics.
- Retain payloads alongside metadata for retries and the DLQ.
- Pause the pipeline when configuration errors or cluster state affect operations broadly.
- Monitor error rates, queue depth, DLQ, and processing times.

A reliable Bulk API pipeline treats every item as an independent result. **Transient errors** such as 429 or certain 5xx statuses can be retried after backoff; **data errors** such as mapper parsing or malformed JSON must be quarantined and fixed before replay; **409** must distinguish create duplicates from version conflicts; and timeouts must be treated as potentially uncertain outcomes. By inspecting each item, retrying only the failed subset, keeping stable payloads and IDs, and ensuring operations can repeat safely, applications avoid duplicate writes, surface bad data rather than hiding it, and keep ingestion moving forward even when part of a batch fails.
