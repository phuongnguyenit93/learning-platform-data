# Distinguishing HTTP Success from Per-Item Failures in Bulk Requests

The Elasticsearch Bulk API accepts multiple write operations in a single request to reduce round trips between the application and the cluster. A single bulk request can contain hundreds of index, create, update, or delete operations. These operations are processed independently: some items can succeed while other items fail.

Therefore, the HTTP status of the request is not enough to conclude that the entire batch was written successfully. Elasticsearch can return HTTP 200 for a processed bulk request while the response body reports `errors: true` because one or more operations failed.

When importing data with Spring Data Elasticsearch, the application must distinguish:

1. **Request-level outcome:** whether the HTTP request was accepted by the server and returned a response.
2. **Bulk-level outcome:** whether the response has the `errors` flag indicating any operation failed.
3. **Item-level outcome:** each operation has its own status, result, or error.

Only checking all three layers lets the application know precisely which data was written, which needs fixing, and which can be retried.

## 1. The Bulk API Processes Multiple Operations in One Request

A bulk request can contain multiple operation types:

| Operation | Purpose | Accompanying Content |
| --- | --- | --- |
| `index` | Create a new document or replace a document by ID | Metadata and source document |
| `create` | Create a document only if the ID does not exist yet | Metadata and source document |
| `update` | Partially update a document or run a script | Metadata and update body |
| `delete` | Delete a document by ID | Metadata only |

Example request:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "products", "_id": "P-100" } }
{ "name": "Keyboard", "price": 129.5 }
{ "index": { "_index": "products", "_id": "P-101" } }
{ "name": "Mouse", "price": 49.9 }
{ "delete": { "_index": "products", "_id": "P-102" } }
~~~

Each action metadata object sits on its own line. For `index`, `create`, and `update`, the next line holds the source or update body. `delete` only requires a single metadata line.

The Bulk API is not a transaction. If the first and third operations succeed while the second fails, the two successful operations can still be persisted. Elasticsearch does not automatically roll back completed operations just because another operation failed.

## 2. Three Outcome Layers That Must Not Be Confused

A bulk response can have HTTP status 200 with a body like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "took": 12,
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
      "delete": {
        "_index": "products",
        "_id": "P-102",
        "status": 200,
        "result": "deleted"
      }
    }
  ]
}
~~~

Interpretation:

- HTTP 200: Elasticsearch processed the bulk request and returned a valid response.
- `errors: true`: at least one operation in the batch failed.
- Item `P-100`: document created successfully.
- Item `P-101`: failed because field `price` could not be parsed.
- Item `P-102`: document deleted successfully.

You must not conclude the batch succeeded solely from HTTP 200. Nor should you conclude every operation failed just because `errors` is true. You must read each item to determine the exact results.

### 2.1. Meaning of Each Layer

| Layer | Example | What Can Be Concluded? |
| --- | --- | --- |
| HTTP request | `200 OK` | The server returned a successful response at the HTTP level |
| Bulk response | `errors: true` | At least one operation has an error |
| Item response | `status: 400`, with `error` | That specific operation failed |
| Item response | `status: 201`, `result: created` | That specific operation created the document |

The HTTP status is the outcome of sending the request to the endpoint. `errors` summarizes the operation outcomes. `items` holds the detailed data for the application to process.

### 2.2. HTTP 200 Does Not Mean All Items Succeeded

The Bulk API is designed to return per-operation outcomes. A mapping error on one operation does not force Elasticsearch to abort other operations in the same request.

~~~text
Bulk request
   |
   +-- index P-100  ---> 201 created
   |
   +-- index P-101  ---> 400 mapper_parsing_exception
   |
   +-- update P-102 ---> 200 updated
   |
   +-- delete P-103 ---> 200 deleted

HTTP response: 200 OK
Bulk errors:   true
Successful:    3 operations
Failed:        1 operation
~~~

The application must record the three successful operations and route the failed operation into an error handling flow.

## 3. Distinguishing Request-Level Errors from Item-Level Errors

### 3.1. Request-Level Errors

A request-level error occurs at the HTTP or transport level. Elasticsearch does not return a normal bulk response with a full item list for the application to iterate over.

| Scenario | Example Outcome |
| --- | --- |
| Invalid NDJSON syntax or malformed request body | HTTP 400 |
| Authentication failed | HTTP 401 |
| Missing permission for index or operation | HTTP 403 |
| Index does not exist and auto-creation is disallowed | Possibly HTTP 404 |
| Request exceeds size limit | HTTP 413 |
| Cluster or node temporarily unable to process | Possibly HTTP 429 or 5xx |
| Timeout or connection loss | Client may receive a transport error instead of `BulkResponse` |

These errors must be handled at the request level. For example, HTTP 401 requires fixing credentials; HTTP 413 requires reducing batch size; HTTP 400 from malformed NDJSON requires fixing request construction.

### 3.2. Item-Level Errors

An item-level error occurs when the bulk request was processed and Elasticsearch returns a distinct status for an operation.

Examples:

- `mapper_parsing_exception`: source value does not match the mapping.
- `document_parsing_exception`: document content cannot be parsed.
- `version_conflict_engine_exception`: operation encountered a version conflict.
- `document_missing_exception`: update requires an existing document, but the ID was not found.
- `es_rejected_execution_exception`: node rejected the operation due to overload or a full queue.

A failed item typically has the structure:

~~~json
{
  "index": {
    "_index": "products",
    "_id": "P-101",
    "status": 400,
    "error": {
      "type": "mapper_parsing_exception",
      "reason": "failed to parse field [price] of type [double]"
    }
  }
}
~~~

Other items in the same response can still succeed.

### 3.3. Timeouts Differ from Confirmed Item Failures

If the client sends a request and times out before receiving a response, the application may not know how many operations Elasticsearch processed. Some operations may have succeeded before the connection dropped.

Do not treat every timeout as proof that no data was written. This is an **uncertain outcome** state. Design stable IDs, idempotent operations, and reconciliation mechanisms to recover safely.

## 4. Bulk Response Structure

A bulk response typically contains these fields:

| Field | Meaning |
| --- | --- |
| `took` | Time spent by Elasticsearch processing the bulk request, in milliseconds |
| `errors` | `true` if at least one operation failed |
| `items` | List of per-operation results, in request order |
| `ingest_took` | Ingest pipeline duration if included in the response |

Each element in `items` has a single key for the operation type (`index`, `create`, `update`, or `delete`) and a value holding the outcome of that operation.

A successful item can look like:

~~~json
{
  "index": {
    "_index": "products",
    "_id": "P-100",
    "_version": 3,
    "result": "updated",
    "_shards": {
      "total": 2,
      "successful": 2,
      "failed": 0
    },
    "status": 200
  }
}
~~~

A failed item can look like:

~~~json
{
  "update": {
    "_index": "products",
    "_id": "P-101",
    "status": 409,
    "error": {
      "type": "version_conflict_engine_exception",
      "reason": "[P-101]: version conflict"
    }
  }
}
~~~

### 4.1. Checking `status`, `result`, and `error`

When inspecting an item, check:

- `status`: HTTP status code corresponding to the operation.
- `result`: Elasticsearch-level result such as `created`, `updated`, `deleted`, `noop`, or `not_found`.
- `error`: error details if the operation failed.
- `_index`, `_id`: identify the targeted document.
- `_version`, `_seq_no`, `_primary_term`: concurrency metadata when present in the response.

Do not rely on `status` or `result` in isolation. For instance, `noop` in an update usually means the script made no change to the document; this can be a valid outcome rather than an error.

When deleting a non-existent document, the response may contain `result: not_found` and a corresponding status. The application must decide whether that is an error under its business contract. If the goal is idempotent deletion, a document that is already absent can be treated as the desired state.

### 4.2. `errors` Is a Summary Flag, Not an Error List

`errors: true` only indicates that at least one operation failed. It does not tell you which items failed, how many failed, or which errors are retryable. That information lives in `items`.

## 5. Bulk Is Not Atomic

The Bulk API bundles multiple operations into one request, but it does not turn them into an atomic transaction.

Example batch with 1,000 operations:

- 980 operations succeed.
- 15 operations fail with mapping errors.
- 5 operations are rejected due to overload.

Elasticsearch does not roll back the 980 successful operations. The application must preserve their results and handle the remaining 20 operations.

This has three implications:

1. Do not retry the entire batch just because `errors: true`.
2. Do not delete or roll back successful documents unless business logic explicitly calls for a compensating action.
3. Preserve the correlation between each submitted operation and its corresponding response item.

If business requirements demand that all changes commit or roll back together, bulk is not the right transaction mechanism. Handle the transaction in the source system and build the Elasticsearch read model from events or projections.

## 6. NDJSON: Request Formatting Affects Outcomes

The Bulk API uses NDJSON (newline-delimited JSON), not a regular JSON array.

Correct:

~~~text
{ "index": { "_index": "products", "_id": "P-100" } }
{ "name": "Keyboard", "price": 129.5 }
{ "delete": { "_index": "products", "_id": "P-101" } }
~~~

Incorrect:

~~~json
[
  {
    "index": {
      "_index": "products",
      "_id": "P-100"
    }
  },
  {
    "name": "Keyboard"
  }
]
~~~

Key rules:

- Each action metadata object is a single JSON line.
- The source/update body sits on the next line when the operation requires a body.
- Do not add commas between lines.
- Do not pretty-print a JSON object across multiple lines.
- End the request with a final trailing newline.
- Use content type `application/x-ndjson`.

A malformed request can fail at the request level before returning item responses as expected.

### 6.1. Line Count per Operation

| Operation | Line Count |
| --- | ---: |
| `index` | 2 |
| `create` | 2 |
| `update` | 2 |
| `delete` | 1 |

Update example:

~~~text
{ "update": { "_index": "products", "_id": "P-100" } }
{ "doc": { "price": 119.5 } }
~~~

Update with upsert example:

~~~text
{ "update": { "_index": "products", "_id": "P-200" } }
{ "doc": { "name": "New Product" }, "doc_as_upsert": true }
~~~

Omitting the source line for an operation that requires a body, or misplacing a body on the next action line, can prevent the parser from understanding the request.

## 7. Reading Items in Exact Request Order

The bulk response returns `items` in the order of the submitted operations. The application can match them by index position in the request list.

Do not use only the document ID as the correlation key if the same bulk request contains multiple operations on the same ID. For example, one request might index a document and then update that same document. Store position, operation type, index, and ID together.

~~~java
public record SubmittedOperation(
    int position,
    String operation,
    String index,
    String id
) {}
~~~

When sending a bulk request, keep the `SubmittedOperation` list in the same order as the request. When receiving the response, pair `items.get(i)` with the operation at position `i`.

## 8. Reading `BulkResponse` with Elasticsearch Java API Client

When you need to inspect `errors`, status, and error details for every item, the Elasticsearch Java API Client provides `BulkResponse`.

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkRequest.Builder request = new BulkRequest.Builder();

request.operations(op -> op
    .index(index -> index
        .index("products")
        .id("P-100")
        .document(product100)
    )
);

request.operations(op -> op
    .index(index -> index
        .index("products")
        .id("P-101")
        .document(product101)
    )
);

BulkResponse response = elasticsearchClient.bulk(request.build());
~~~

Inspecting the results:

~~~java
if (response.errors()) {
    System.out.println("At least one bulk item failed");
}

for (BulkResponseItem item : response.items()) {
    if (item.error() == null) {
        System.out.printf(
            "SUCCESS index=%s id=%s status=%d result=%s%n",
            item.index(),
            item.id(),
            item.status(),
            item.result()
        );
    } else {
        System.out.printf(
            "FAILED index=%s id=%s status=%d type=%s reason=%s%n",
            item.index(),
            item.id(),
            item.status(),
            item.error().type(),
            item.error().reason()
        );
    }
}
~~~

Key points:

- `response.errors()` is the summary flag.
- `response.items()` contains each operation result.
- `item.status()` is the item's status.
- `item.error()` contains error information when the item failed.
- `item.id()` and `item.index()` identify the document.
- `item.result()` indicates the outcome such as `created`, `updated`, or `deleted` when present.

If the request encounters an HTTP 4xx/5xx or transport error, the client may throw an exception instead of returning a normal `BulkResponse`. Handle request-level exceptions separately from item classification inside the response.

### 8.1. Checking the Item Count

If a request contains N operations, a normal response must contain N item results. If the counts do not match, do not infer which operations succeeded. Treat this as an anomaly: log request metadata and the response, and check client/endpoint compatibility.

## 9. Using `BulkOperations` in Spring Data Elasticsearch

Spring Data Elasticsearch provides the `BulkOperations` abstraction to batch write operations:

~~~java
import org.springframework.data.elasticsearch.core.BulkOperations;
import org.springframework.data.elasticsearch.core.BulkMode;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

BulkOperations bulk = operations.bulkOps(
    BulkMode.BULK,
    ProductDocument.class
);

bulk.insert(products);
bulk.execute();
~~~

The bulk abstraction is suitable when the application wants to work through Spring Data mappings and APIs. However, the level of detail returned for individual operation failures depends on the Spring Data Elasticsearch API and version.

If the business flow must make retry decisions per `BulkResponseItem`, use a bulk API that exposes per-item response details—such as the Elasticsearch Java API Client—or use a specific Spring Data API that exposes failed document details in your project's version.

Do not assume that a call to `execute()` returning without an exception means every document was written properly. Nor should you assume every version of `BulkOperations` directly returns the list of item results.

### 9.1. `ElasticsearchOperations` Bulk Index APIs

Some `ElasticsearchOperations` APIs provide bulk index/update methods that take a list of queries and return indexed document metadata. Depending on the version, these APIs can throw `BulkFailureException` or a corresponding exception when documents fail.

When using them:

- Check the Javadoc of your exact Spring Data Elasticsearch version.
- Check whether the exception carries a map or list of failed documents.
- Do not ignore failed document details.
- If you need the raw status/error of every operation, consider reading the response from the Java API Client.

### 9.2. Choosing the Right Abstraction

| Need | Approach |
| --- | --- |
| Write multiple entities using Spring Data mapping | `BulkOperations` or `ElasticsearchOperations` bulk APIs |
| Work at the entity level | Spring Data abstraction |
| Need `BulkResponse.errors()` and each item's status/error | Elasticsearch Java API Client |
| Need to retry only the failed items | Store request metadata and inspect detailed item responses |
| Need full control over operation metadata | Java API Client or Bulk REST API |

## 10. Classifying Per-Item Errors

Not every error should be retried. Classify errors by cause and recoverability.

| Item Status / Error | Common Cause | Handling Approach |
| --- | --- | --- |
| 400 `mapper_parsing_exception` | Source value does not match mapping | Fix the data or mapping; do not retry as-is |
| 400 `document_parsing_exception` | Document is invalid | Fix the serializer/source |
| 400 `illegal_argument_exception` | Invalid parameter or operation config | Fix the request |
| 404 `document_missing_exception` | Update targeting non-existent document without upsert | Verify ID and create/upsert policy |
| 409 `version_conflict_engine_exception` | Version or optimistic concurrency conflict | Re-read, merge, or retry conditionally |
| 409 on `create` | ID already exists | Handle duplicate according to business rules |
| 429 `es_rejected_execution_exception` | Node or write queue overloaded | Backoff, reduce concurrency/batch size |
| Transient 5xx | Node, shard, or service failure | Retry with limits after classification |

Actual error types and statuses can vary by operation, cluster configuration, and version. Use `error.type`, `error.reason`, status, and operation type rather than relying on a single status code.

### 10.1. Mapping Errors Should Not Be Retried As-Is

For example, field `price` is mapped as `double`, but the source sends an unconvertible string:

~~~json
{
  "price": "unknown"
}
~~~

Retrying the same document will keep failing. Fix the data to a valid value, omit the field if business rules allow, or change the mapping after impact analysis.

### 10.2. Overload Errors Can Be Retried

`429` usually indicates Elasticsearch rejected the operation due to overload. This is an appropriate case for retrying with backoff, whereas aggressive immediate retries worsen the overload.

You should:

- Wait using exponential backoff.
- Add jitter so multiple workers do not retry at the exact same moment.
- Cap the retry count.
- Reduce batch size or concurrent requests.
- Monitor rejected counts and write queues.

### 10.3. Version Conflicts Require Business Logic Handling

`409 version_conflict_engine_exception` is not always a transient error where resending the exact same operation works.

If two writers update the same document concurrently, determine which writer has newer data, whether to re-read and recompute the update, or whether optimistic concurrency is required.

`retry_on_conflict` is a conflict-retry mechanism for update operations; it does not resolve mapping errors, request timeouts, or 429 overload rejections.

## 11. Retrying Only Failed Items

Suppose a bulk request contains 100 operations and the response shows 96 succeeded and 4 failed. Do not resend all 100 operations if the goal is simply to handle the four failed items.

~~~text
Send batch of 100 operations
          |
          v
Receive response for 100 items
          |
          +----> 96 success: mark completed
          |
          +----> 4 failed: classify errors
                         |
             +-----------+-----------+
             |                       |
             v                       v
        Retryable                 Permanent
             |                       |
             v                       v
     Retry with backoff        DLQ / fix data
~~~

### 11.1. Retaining Original Operations

To retry, the application must retain the operation type, index, document ID, routing, source or update body, version constraints, retry count, batch ID, and error type/reason.

Keeping only the ID is insufficient if the operation needs the source or script to re-run.

### 11.2. Exponential Backoff and Jitter

| Retry Attempt | Base Delay |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 | 3,200 ms |

In practice, add random jitter and cap the maximum delay. These numbers are only examples; adjust them to match latency, cluster load, and SLAs.

### 11.3. Bounded Retries

Do not retry indefinitely. After the allowed attempts, route the item to a dead-letter queue, record the cause and payload reference, alert on thresholds, and enable controlled data correction/replay.

## 12. Idempotency and Ambiguous Timeouts

Safe retries depend on whether the operation is idempotent.

### 12.1. Using Stable IDs

~~~text
{ "index": { "_index": "products", "_id": "P-100" } }
{ "name": "Keyboard", "price": 129.5 }
~~~

If the request timed out after Elasticsearch already wrote the document, resending the same `index` operation with the same ID and same source generally replaces the document with the same content rather than creating a second document.

Conversely, generating a random ID on every retry can write the same data into multiple duplicate documents.

### 12.2. `create` and Duplicates

`create` only creates when the ID does not exist yet. If the first attempt succeeded before the client timed out, the retry can return 409 because the ID now exists.

You cannot conclude data was not written simply from a 409 on retry. You may need to fetch the document by ID and compare content/version.

### 12.3. Non-Idempotent Update Scripts

~~~json
{
  "script": {
    "source": "ctx._source.viewCount += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

If the request executed but the response was lost, retrying this script can increment the count an extra time. This is a non-idempotent operation.

To avoid duplicate updates, track processed event IDs, store source sequence/version numbers, design updates that assign absolute values, use optimistic concurrency, or project idempotently from an event log.

### 12.4. Do Not Blindly Retry the Entire Request After a Timeout

A timeout can occur before the server receives the request, while the server is processing, or after completion while the response is in transit.

When the state is unknown:

1. Use stable IDs and idempotent operations.
2. Reconcile documents by ID when confirmation is needed.
3. Resend only unconfirmed operations.
4. Do not repeat update scripts with side effects unless deduplication is in place.

## 13. Controlling Batch Size and Concurrency

Bulk requests that are too small increase HTTP overhead. Bulk requests that are too large increase memory usage, latency, response size, and processing time.

There is no single optimal batch size for all clusters. Benchmark by source size, operation count, payload bytes, mapping, ingest pipeline, shard/replica count, write rate, and 429 error rate.

### 13.1. Limiting by Both Item Count and Bytes

Split batches by both operation count and total payload size. A batch of 1,000 small documents can be lighter than 100 documents with very large sources.

If a request exceeds body size limits, the server or proxy can return HTTP 413. Split the batch smaller instead of retrying the same payload.

### 13.2. Tuning Concurrency

If increasing worker count drives up 429s, lower the number of concurrent bulk requests. Too many simultaneous large requests can overwhelm the write thread pool and queue.

A producer-consumer mechanism with backpressure ensures the source read rate does not exceed Elasticsearch's write capacity.

### 13.3. Monitoring Latency

`took` in the response is how long Elasticsearch spent processing the request. It does not necessarily include total time from when the application built the batch to when it received the response.

Measure batch preparation time, client latency, `took`, operations/second, item success/failure counts, and retry rate separately.

## 14. Bulk and Refresh Do Not Change Error Semantics

The Bulk API can accept a refresh policy or `refresh` parameter to control when changes become searchable.

For example, `refresh=wait_for` waits for the next refresh so written changes become visible to search. It does not turn bulk into a transaction and does not mean every item succeeded.

Even when a request uses `refresh=wait_for`, the application must still inspect the HTTP request outcome, `errors`, and each item's status/error.

Similarly, `wait_for_active_shards` governs how many shards must be active before executing the operation; it does not replace checking per-item outcomes.

## 15. Logging and Observing Bulk Ingestion

A bulk pipeline should log enough context to answer which batch was sent, how many operations it held, how many succeeded/failed, which items errored, which error categories occurred, how many retries ran, and how many items went to the dead-letter queue.

Example summary log:

~~~text
bulkId=bulk-20260312-00042
index=products
submitted=1000
succeeded=982
failed=18
retryable=12
permanent=6
esTookMs=245
clientLatencyMs=318
~~~

Example item log:

~~~text
bulkId=bulk-20260312-00042
position=147
operation=index
index=products
id=P-10147
status=400
errorType=mapper_parsing_exception
retryable=false
~~~

Do not log the entire source document if it contains sensitive data or huge payloads. Logging ID, batch ID, error type, and filtered fields is sufficient in most cases.

### 15.1. Recommended Metrics

| Metric | Meaning |
| --- | --- |
| `bulk_requests_total` | Number of bulk requests sent |
| `bulk_request_failures_total` | Request-level failures |
| `bulk_items_submitted_total` | Total items submitted |
| `bulk_items_succeeded_total` | Total items succeeded |
| `bulk_items_failed_total` | Total items failed |
| `bulk_items_retried_total` | Total items retried |
| `bulk_items_dead_letter_total` | Total items unprocessable automatically |
| `bulk_duration_seconds` | Bulk processing duration |
| `bulk_item_failure_rate` | Item failure rate |

Track HTTP request errors separately from item failure rates. If dashboards only count HTTP 2xx responses, ingestion can appear healthy even while thousands of documents fail mapping.

## 16. Example Per-Item Error Handling

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

public record FailedOperation(
    int position,
    String index,
    String id,
    int status,
    String errorType,
    String reason
) {}

public record BulkOutcome(
    int succeeded,
    List<FailedOperation> failed
) {}

public BulkOutcome inspect(BulkResponse response) {
    List<FailedOperation> failed = new ArrayList<>();
    int succeeded = 0;

    for (int i = 0; i < response.items().size(); i++) {
        BulkResponseItem item = response.items().get(i);

        if (item.error() == null) {
            succeeded++;
            continue;
        }

        failed.add(new FailedOperation(
            i,
            item.index(),
            item.id(),
            item.status(),
            item.error().type(),
            item.error().reason()
        ));
    }

    return new BulkOutcome(succeeded, failed);
}
~~~

This is the response inspection step. To retry, the application must match `position` against the original list of submitted operations, retrieve the original source/update body, and build a new request containing only items classified as retryable.

### 16.1. Classifying Retryable Failures

~~~java
boolean isRetryable(FailedOperation failure) {
    if (failure.status() == 429) {
        return true;
    }

    if (failure.status() >= 500 && failure.status() <= 599) {
        return true;
    }

    return false;
}
~~~

This rule is only a starting point. Production systems must inspect error type, operation semantics, and specific policies for 409, 404, or specific transient errors. Do not treat all 5xx errors as safe to retry if the operation is non-idempotent and the earlier outcome is unknown.

### 16.2. Resending the Failed Subset

~~~java
List<PendingOperation> retryOperations = new ArrayList<>();

for (FailedOperation failure : outcome.failed()) {
    if (isRetryable(failure)) {
        PendingOperation original =
            submittedOperations.get(failure.position());
        retryOperations.add(original);
    } else {
        deadLetterQueue.publish(
            submittedOperations.get(failure.position()),
            failure
        );
    }
}

// Wait for backoff, then build a new bulk request from retryOperations only.
~~~

`PendingOperation` is an application data type holding operation metadata and the original source. Do not try to reconstruct the source from the item response because responses do not contain the full original payload.

## 17. Special Cases Requiring Dedicated Handling

### 17.1. Mapping Changes Between Batches

If a field's mapping type changes while the pipeline is actively sending data, part of a batch may succeed while another part fails. Pause or throttle the producer, perform the mapping migration, and retry items only after the mapping is compatible.

### 17.2. Index Aliases and Rollover

If bulk writes through an alias, ensure the alias has the right write index. If an alias points poorly or lacks a write index, requests can fail at the request or item level depending on the error and configuration.

You can use `require_alias` when you want Elasticsearch to reject writes if the target name is not an alias. This helps avoid accidentally creating a new index due to a typo.

### 17.3. Ingest Pipelines

An ingest pipeline can transform or reject a document. Processor failures can appear as item errors even when the overall bulk request was processed.

When errors recur, check the pipeline ID, the failing processor, missing/wrongly typed input fields, and the pipeline version attached to the request/index.

### 17.4. Updates with Upsert

An update without a target document can return a missing error. If business rules allow creating on miss, configure `doc_as_upsert` or `upsert` in the update body:

~~~json
{ "update": { "_index": "products", "_id": "P-200" } }
{ "doc": { "name": "New Product" }, "doc_as_upsert": true }
~~~

Do not enable upsert automatically if a missing document actually indicates bad data or broken referential integrity.

## 18. Common Mistakes

**Checking only HTTP 200.** A bulk response can still contain item failures. Check `errors` and iterate over `items`.

**Checking only `errors: true`.** This flag does not tell you which items succeeded or failed. You must read each item.

**Retrying the whole batch when only a few items fail.** Successful items can be re-written or cause side effects. Build a retry batch from only the failed subset.

**Treating bulk as a transaction.** Elasticsearch does not roll back successful items when other items fail.

**Assuming a timeout means no data was written.** The server may have executed part or all of the request. Use stable IDs and reconcile.

**Retrying mapping errors.** Data incompatible with the mapping will keep failing. Fix the source or mapping before retrying.

**Retrying 429s immediately.** Immediate retries increase load. Use exponential backoff, jitter, and lower concurrency.

**Retrying 409s without re-reading data.** Version conflicts require merge rules or version control.

**Using `create` with random IDs on retry.** This can create duplicate documents. Use deterministic business IDs.

**Retrying non-idempotent increment/decrement update scripts.** A timeout after the script executed can apply the side effect twice. Use event IDs, versions, or deterministic assignments.

**Correlating responses solely by document ID.** A single request can contain multiple operations on the same ID. Use position and operation type alongside index/ID.

**Building NDJSON without a trailing newline.** The bulk parser requires newline-delimited formatting and a trailing newline at the end of the request.

**Pretty-printing each source JSON across multiple lines.** An operation's body must be a single JSON object on one NDJSON line.

**Assuming `BulkOperations` always returns item responses.** Spring Data abstractions vary across versions and not every API exposes the full response. Check Javadoc or use the Java API Client when full details are required.

**Logging only HTTP request failures.** Dashboards will miss item failures. Record metrics at both the request level and the item level.

## 19. Workflow for Processing a Bulk Batch

An ingestion pipeline can follow this sequence:

1. Prepare source documents and stable IDs.
2. Split data by batch size and payload byte limit.
3. Store the list of operation metadata in exact submission order.
4. Send the bulk request with valid NDJSON or the Java API Client.
5. On a request-level exception, classify the HTTP/transport error and assess whether the outcome is certain.
6. Upon receiving `BulkResponse`, check `errors` and the `items` count.
7. Match each item with its original operation by position.
8. Record successful items.
9. Classify failed items by status, error type, and operation semantics.
10. Retry the recoverable subset using exponential backoff and jitter.
11. Route data errors or non-retryable errors to a dead-letter queue.
12. Reconcile timed-out requests or uncertain outcomes.
13. Monitor latency, throughput, error rates, retry counts, and queue pressure.
14. Mark the batch complete only when every operation has reached a final state under application policy.

## 20. References

- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): NDJSON format, operation types, response errors, and item results.
- [Elasticsearch - Bulk API concepts](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html): handling multiple operations and per-item results.
- [Elasticsearch Java API Client - Bulk operations](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk): building bulk requests and reading `BulkResponse` with the Java client.
- [Spring Data Elasticsearch - Bulk operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): using `ElasticsearchOperations` and `BulkOperations`.
- [Elasticsearch - Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control): sequence numbers, primary terms, and version conflicts.
- [Elasticsearch - Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index): semantics of indexing and document IDs.

Classes and builder methods in Spring Data Elasticsearch and the Elasticsearch Java API Client can differ across versions. When implementing, verify the Javadoc for your project's dependencies. The core rule stays the same: the HTTP response indicates the request-level outcome; `errors` reports whether any item failed; each element in `items` reveals which specific operations succeeded or failed.
