# Batch Data Ingestion and Per-Document Error Handling

When ingesting thousands or millions of documents into Elasticsearch, sending individual requests one by one takes too long and adds unnecessary network overhead. The Bulk API lets you send multiple index, create, update, or delete operations in a single request. Spring Data Elasticsearch provides ElasticsearchOperations.bulkIndex(...) and bulkUpdate(...) to batch operations; for reactive flows, ReactiveElasticsearchOperations supports saving a Flux in batches.

Bulk improves throughput, but a bulk request is not a transaction. The HTTP response can succeed while individual items inside fail. For example, 998 documents may be indexed successfully while 2 documents fail with mapping errors. The application must know exactly which documents succeeded, which need retrying, which belong in a Dead Letter Queue (DLQ), and when source messages can safely be acknowledged.

This lesson covers designing batch sizes, creating IndexQuery instances, calling bulkIndex, reading BulkFailureException, handling BulkResponse at the item level, classifying transient vs. permanent errors, retrying with backoff, preventing duplicates, managing memory and backpressure, handling partial success with message brokers, using BulkIngester for continuous ingestion, tracking metrics, and testing per-document failures.

## 1. Why Ingest Data in Batches?

Suppose an application needs to sync 100,000 products into the products index. If sent one document at a time:

~~~text
Application
   |
   +-- PUT document 1
   +-- PUT document 2
   +-- PUT document 3
   +-- ...
   +-- PUT document 100000
~~~

Each request incurs overhead:

- Establishing and reusing HTTP connections.
- Serializing requests and parsing responses.
- Network round trips.
- Server-side request handling, authorization, and routing.
- Per-request timeout and retry tracking.

Bulk combines multiple operations into one request:

~~~text
Application
    |
    | Bulk request: documents 1..500
    v
Elasticsearch
    |
    | Bulk response: 500 item results
    v
Application
~~~

Request counts drop dramatically, throughput usually improves, and the application controls batch sizes. However, bulk does not eliminate per-document processing cost. Elasticsearch still processes each item independently and returns an individual status per operation.

### 1.1. Bulk Is Not a Transaction

A bulk request can produce mixed outcomes:

| Document | Result |
|---|---|
| product-001 | Indexed |
| product-002 | Indexed |
| product-003 | Mapping error |
| product-004 | Indexed |
| product-005 | Rejected, status 429 |

Elasticsearch does not roll back product-001, product-002, or product-004 just because product-003 or product-005 failed.

Therefore:

- Never treat HTTP 200 as meaning every item succeeded.
- Never blindly retry the entire batch.
- Never acknowledge the entire source batch if some items remain unhandled or not yet written to a DLQ per policy.
- Never assume successfully written items can be rolled back.

## 2. How Does the Bulk API Work?

The Elasticsearch Bulk API accepts data in NDJSON (newline-delimited JSON) format. Each operation has a metadata line and, depending on action type, an accompanying source or update body line.

Example with two index operations:

~~~http
POST products/_bulk
Content-Type: application/x-ndjson

{"index":{"_id":"p-100"}}
{"sku":"KB-100","name":"Keyboard","price":1299000}
{"index":{"_id":"p-101"}}
{"sku":"MS-101","name":"Mouse","price":299000}
~~~

Common actions:

| Action | Next line | Meaning |
|---|---|---|
| index | Document source | Create a new document or replace one with the same ID |
| create | Document source | Create only; fails if ID already exists |
| update | Partial document/script/upsert | Update existing document or upsert if configured |
| delete | No source line | Delete document by ID |

The Bulk API uses NDJSON to parse and stream each action efficiently. The final line of the request must end with a newline when calling the REST endpoint directly.

### 2.1. Differences Between index and create

The index action has create-or-replace semantics:

~~~json
{"index":{"_id":"p-100"}}
{"name":"Keyboard","price":1299000}
~~~

If document p-100 already exists, the new source replaces the old one.

The create action only creates new documents:

~~~json
{"create":{"_id":"p-100"}}
{"name":"Keyboard","price":1299000}
~~~

If p-100 already exists, the item fails with a version conflict. This is useful when you want to detect duplicates instead of overwriting.

Choose the action according to business semantics:

- Snapshots/projections needing idempotent retries usually use index with a stable ID.
- Events that may only be created once can use create and treat conflicts as duplicates.
- Partial updates use update and require evaluating script idempotency.
- Deletes require the proper ID and routing.

Data streams only support the create action. If you need to update or delete a document, you must target the appropriate backing index according to Elasticsearch rules.

## 3. Distinguishing Request-Level and Item-Level Errors

There are two distinct failure layers:

### 3.1. Whole-Request Failures

The request fails to complete or Elasticsearch does not return a valid response:

- Network timeout or connection reset.
- DNS or connection failure.
- Request-level authentication/authorization errors.
- Missing index or malformed request.
- Cluster unavailable.
- Proxy/load balancer returning 502/503/504.

In these cases, the application cannot tell which items were processed before the connection dropped. This is an ambiguous outcome.

### 3.2. Item-Level Failures

Elasticsearch accepts the bulk request and returns a response, but some individual actions fail:

- Mapping/parsing errors.
- Document already exists on a create action.
- Version conflicts.
- Rejected execution under heavy load.
- Invalid fields or values.

The bulk HTTP response can still be HTTP 200. The response-level errors flag indicates whether any item failed; each element in items carries its own status and error details.

Example:

~~~json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "p-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "p-101",
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
        "_id": "p-102",
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

- p-100 succeeded.
- p-101 has data incompatible with the mapping.
- p-102 was temporarily rejected due to load.

You cannot handle all three outcomes with the same retry strategy.

## 4. Using ElasticsearchOperations.bulkIndex

Spring Data Elasticsearch provides bulkIndex on ElasticsearchOperations. The API accepts a list of IndexQuery items, BulkOptions, and the target index.

Example entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
    private BigDecimal price;

    // getters and setters
}
~~~

Building an IndexQuery per document:

~~~java
List<IndexQuery> queries = products.stream()
        .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();
~~~

Executing the bulk request:

~~~java
List<IndexedObjectInformation> indexed =
        operations.bulkIndex(
                queries,
                BulkOptions.defaultOptions(),
                IndexCoordinates.of("products"));
~~~

bulkIndex returns information about indexed documents when items succeed. If item failures occur, Spring Data Elasticsearch can throw BulkFailureException containing details about failed documents.

### 4.1. Creating IndexQuery with an Explicit ID

For imports and replays, assign a deterministic document ID:

~~~java
IndexQuery query = IndexQuery.builder()
        .withId(product.getId())
        .withObject(product)
        .build();
~~~

Stable IDs ensure retries index the same source into the same document. Letting Elasticsearch autogenerate IDs can create duplicate documents if retried after a timeout.

If the entity has @Id, mapping can derive the ID from the entity object; however, when constructing batches and correlating errors back to source records, building explicit ID maps remains useful.

### 4.2. Using BulkOptions

BulkOptions lets you configure request options:

~~~java
BulkOptions options = BulkOptions.builder()
        .withTimeout(Duration.ofSeconds(30))
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

List<IndexedObjectInformation> result = operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products"));
~~~

Common options include:

- timeout: wait duration for operations such as auto index creation, dynamic mapping updates, and active shards.
- refreshPolicy: when indexed data becomes visible to search.
- waitForActiveShards: number of shard copies that must be active before proceeding.
- pipeline: ingest pipeline to execute.
- routingId: default routing when applicable to the request.

BulkOptions timeout is not the same as HTTP client socket timeout. A request can time out at the HTTP client layer while the server continues processing.

### 4.3. Do Not Enable Refresh After Every Batch

Refreshing immediately after every batch degrades indexing throughput. For large ingestions, keep the default/NONE refresh policy and refresh once the import completes or rely on the schedule.

Use IMMEDIATE or WAIT_UNTIL only when the application genuinely requires immediate search visibility after the request. Refreshing does not make bulk transactional.

## 5. Handling BulkFailureException in Spring Data

BulkFailureException is the exception Spring Data Elasticsearch throws to report failures during a bulk operation. Current APIs provide:

- getFailedDocuments(): a map of failed documents.
- Map key is the document ID.
- Value is FailureDetails.
- FailureDetails exposes status and errorMessage.

Example:

~~~java
try {
    operations.bulkIndex(
            queries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((documentId, failure) -> {
        log.warn(
                "Failed to index document id={}, status={}, reason={}",
                documentId,
                failure.status(),
                failure.errorMessage());
    });
}
~~~

Never log the entire entity/source during error handling if documents contain personal or secret data. Logging ID, status, redacted error type/reason, and correlation ID is usually enough for investigation.

### 5.1. Correlating Errors Back to Source Records

Before sending the batch, build a map from document ID to source record or message metadata:

~~~java
Map<String, ProductInput> sourceById = new HashMap<>();
List<IndexQuery> queries = new ArrayList<>();

for (ProductInput input : batch) {
    ProductDocument document = mapper.toDocument(input);
    sourceById.put(document.getId(), input);

    queries.add(IndexQuery.builder()
            .withId(document.getId())
            .withObject(document)
            .build());
}
~~~

When catching the exception:

~~~java
try {
    operations.bulkIndex(
            queries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        ProductInput original = sourceById.get(id);
        handleFailure(original, id, failure.status(), failure.errorMessage());
    });
}
~~~

Keep either the source record or a durable reference to the source record so it can be retried or written to a DLQ. Do not keep only an exception message while discarding the payload needed for recovery.

### 5.2. Limitations of BulkFailureException

FailureDetails in current Spring Data releases provides only HTTP status and errorMessage. If you need finer classification by Elasticsearch error type, reason, shard failures, or per-operation context, use the Elasticsearch Java API Client BulkResponse or BulkIngester listener.

Furthermore, if a batch contains multiple operations targeting the same document ID, a map keyed by ID cannot distinguish individual operations. Avoid duplicate IDs in the same batch or use the low-level ordered response with per-item context.

### 5.3. Never Catch and Swallow Exceptions

Dangerous example:

~~~java
try {
    operations.bulkIndex(queries, index);
} catch (BulkFailureException ignored) {
    // continue
}
~~~

This code discards information about failed documents. If the caller subsequently acknowledges the batch or message, failed records can be lost permanently.

Always classify every failure and transition it to a trackable state: retry, DLQ, reject, or halt pipeline.

## 6. Inspecting Each BulkResponseItem with the Elasticsearch Java API Client

When full item-level detail is needed, call ElasticsearchClient directly inside a dedicated adapter:

~~~java
BulkResponse response = elasticsearchClient.bulk(request -> request
        .index("products")
        .operations(operation -> operation
                .index(index -> index
                        .id("p-100")
                        .document(productDocument))));

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() != null) {
            log.warn(
                    "Bulk item failed id={}, status={}, type={}, reason={}",
                    item.id(),
                    item.status(),
                    item.error().type(),
                    item.error().reason());
        }
    }
}
~~~

BulkResponse provides:

- errors: true if at least one operation failed.
- items: results for each operation in the exact order submitted.
- status: HTTP status for each item.
- error: error type and reason when the item failed.
- _id/_index/result/version/sequence metadata where applicable.

A whole-request HTTP status of 200 does not guarantee every item succeeded. Always check errors and each item.error().

### 6.1. Maintaining Mapping Between Request Items and Inputs

The Bulk API returns items in the order operations were sent. Keep the input list in matching order:

~~~java
List<ProductInput> inputs = batch;
BulkResponse response = sendBulk(inputs);

for (int i = 0; i < response.items().size(); i++) {
    ProductInput input = inputs.get(i);
    BulkResponseItem item = response.items().get(i);

    if (item.error() == null) {
        markIndexed(input, item.id());
    } else {
        handleItemFailure(input, item);
    }
}
~~~

This handles duplicate IDs or mixed action types within the same batch accurately. Never reorder the response list before correlating items.

### 6.2. An Item Can Be index, create, update, or delete

Response items are typed unions by action kind. If code inspects result or error fields, read the appropriate variant and null-check. Do not assume every operation is index.

### 6.3. When to Use the Client Directly?

Prefer Spring Data Operations when:

- Entity mapping and repository abstractions suffice.
- Simple batch indexing or updating is needed.
- Basic exception mapping is enough.

Use the Elasticsearch Java API Client directly when:

- Full error type and reason are required.
- Per-item correlation context is needed.
- BulkIngester automatic batching and flushing are needed.
- Fine-grained action metadata control is required.
- Newer bulk features not yet exposed by Spring Data are needed.

Keep direct client calls inside a dedicated adapter or repository so domain services remain decoupled from the transport API.

## 7. Classifying Per-Document Errors

Not every error should be retried. A starting classification matrix:

| HTTP status / error | Example | Typical appropriate action |
|---|---|---|
| 400 | mapper_parsing_exception, illegal_argument_exception | Permanent; fix data/mapping, send to DLQ |
| 401 | authentication_exception | Stop or pause pipeline; fix credentials |
| 403 | security_exception | Fix privileges/roles; do not keep retrying |
| 404 | index_not_found_exception | Check deployment/index provisioning |
| 409 | version_conflict_engine_exception | Handle per version/idempotency semantics |
| 413 | request entity too large | Split into smaller batches |
| 429 | es_rejected_execution_exception | Retry subset with backoff |
| 502/503/504 | gateway/service unavailable | Bounded retry |
| Network timeout/reset | No response received | Ambiguous outcome; retry only when operation is safe |

Classification should examine both status and error type/reason. A single status code can have multiple root causes, and not all errors sharing a status share the same remediation.

### 7.1. Data/Mapping Errors Are Permanent for the Current Payload

Examples:

- price sent as a string for a numeric mapping.
- Unparseable date.
- Object field structure incompatible with mapping.
- Value out of bounds or violating validation.
- Document contains a field rejected by an ingest pipeline.

Retrying the exact same payload without fixing the data will fail repeatedly. Move the item to a DLQ or rejected-record store, saving the error and source payload for investigation.

### 7.2. 429 Is a Retryable Error

429 indicates Elasticsearch is overloaded or rejecting work. How to handle it:

- Retry only the failed items.
- Apply exponential backoff.
- Add jitter so consumers do not retry in lockstep.
- Cap maximum attempts.
- Reduce batch size or concurrency if 429s persist.
- Monitor rejection rate and queue lag.

Never retry immediately in a tight loop. That amplifies load and slows cluster recovery.

### 7.3. 409 Version Conflict Requires Understanding Semantics

A version conflict can mean:

- Duplicate create.
- Older event arriving after a newer event.
- Optimistic concurrency control detecting a concurrent modification.

Do not automatically treat every 409 as success. If an older event is rejected because its source version is lower, mark it stale/ignored. If a conflict affects an update that still must apply, reload and reconcile according to business rules.

### 7.4. Timeout Has an Ambiguous Outcome

A client timeout does not prove Elasticsearch failed to write the document. The server may have processed the request while the response never reached the client.

For index operations using stable _id and full snapshot payloads, retrying is generally safe for final state. For increment scripts or delta updates, retrying can apply the change twice.

If a timeout happens at the whole-request level, there is no item response to identify which items succeeded. Idempotency, stable IDs, and reconciliation are critical safeguards.

## 8. Retrying Only Failed Items

Suppose a batch of 500 documents yields:

- 490 items succeeded.
- 7 items returned 429.
- 3 items hit mapping errors.

Right strategy:

- Mark the 490 items as succeeded.
- Place the 7 items with 429 into the retry queue.
- Send the 3 mapping-error items to the DLQ/rejected records.
- Do not resend the 490 successful items unnecessarily.

Flow:

~~~text
Batch of 500
     |
     v
Bulk request
     |
     v
Per-item results
     |
     +---- 490 success ----> Mark complete
     |
     +---- 7 transient ----> Retry queue
     |
     +---- 3 permanent ----> DLQ
~~~

### 8.1. Bounded Retries

Example policy:

~~~java
Duration delayFor(int attempt) {
    long baseMillis = 200;
    long maxMillis = 10_000;
    long exponential = Math.min(
            maxMillis,
            baseMillis * (1L << Math.min(attempt, 10)));

    long jitter = ThreadLocalRandom.current()
            .nextLong(Math.max(1, exponential / 2), exponential + 1);

    return Duration.ofMillis(jitter);
}
~~~

This illustrates backoff with jitter. Production systems should use a standardized retry/resilience library with bounded attempts and bounded total retry duration.

Avoid shifts or multiplications that can overflow if attempt is unbounded.

### 8.2. Retry Budget

Beyond max attempts, you can limit:

- Total retry duration.
- Concurrent retrying items.
- Concurrent retry batches.
- Ratio of retries to normal throughput.

If the retry budget is exhausted, move items to the DLQ or pause the pipeline and alert. Never let a set of failing items tie up workers indefinitely.

### 8.3. Retry Individually or Re-Batch?

Retrying one item at a time generates many small requests. You can re-batch retryable items into new batches to reduce overhead:

~~~text
Retry queue
    |
    +-- item p-101
    +-- item p-108
    +-- item p-209
           |
           v
    New bulk request
~~~

When re-batching, preserve source metadata and cap batch size. Never mix expired items or stale versions into a batch just because they share the queue.

## 9. Handling Partial Success in Message Consumers

A consumer may read batches of events from Kafka, RabbitMQ, or another broker and index them into Elasticsearch.

The critical rule is that acknowledgements or offset commits must reflect the processing state of every record.

### 9.1. Never Ack the Whole Batch When One Item Is Unaccounted For

If a consumer receives 100 events and 98 succeed, 1 is retryable, and 1 is permanent:

- 98 events are indexed.
- 1 event needs retry.
- 1 event must be durably written to the DLQ.

Ack/commit according to policy only once every record in the commit window has a durably persisted outcome. Permanent failures can be treated as handled once the DLQ write succeeds.

### 9.2. Kafka Offsets Are Committed per Partition

Kafka offset commits track partition progress, not arbitrary individual acks per record inside a partition. If record at offset 10 fails while record 11 succeeds, do not commit past offset 10 if doing so prevents the consumer from ever receiving the failed record again.

Options:

- Pause the partition until retrying the failed record finishes.
- Persist the failed record to a durable DLQ before committing the next offset.
- Use retry topics with explicitly designed ordering semantics.
- Use a framework supporting partial batch acknowledgement and offset control.

With multiple partitions, other partitions can keep progressing while one partition is paused, depending on consumer configuration.

### 9.3. RabbitMQ Acknowledgements

With RabbitMQ, ack a message only after the Elasticsearch operation succeeds or the failed message has been moved to a DLQ per policy. Requeueing the same poison message repeatedly can create a hot retry loop.

### 9.4. DLQ Writes Must Also Be Reliable

Never commit offsets or ack messages before the DLQ record is durably persisted. A DLQ entry should store:

- Original message or suitably encrypted payload.
- eventId/correlationId.
- Document ID and target index.
- Error status/type/reason.
- Attempt count.
- Source partition/offset or message metadata.
- First and last failure timestamps.
- Schema version and consumer version.

Avoid storing unnecessary sensitive data and enforce retention and access policies on the DLQ.

## 10. Idempotency and Stable Document IDs

Retries are safe only when repeating an operation produces no corrupt state.

With snapshots:

~~~java
ProductDocument document = mapper.toDocument(event);
document.setId(event.productId());
repository.save(document);
~~~

Every retry writes the same document ID and the same snapshot. Final state produces no duplicates.

With increment updates:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 2
    }
  }
}
~~~

Retrying the same event adds twice. You need deduplication or a version guard.

### 10.1. Use Deterministic IDs

Document IDs typically derive from the source primary key or a composite tenant/source key:

~~~text
tenant-7:product-100
~~~

Never generate a fresh random UUID on each retry when the document represents the current state of the same entity.

### 10.2. Version Guards

If events carry aggregateVersion, use external versioning or conditional update scripts so older events never overwrite newer ones. When retrying the same version, define clear conflict/duplicate semantics.

### 10.3. Index Action vs. Create Action

With index, retries replace the same _id. With create, a retry after an earlier success returns a conflict. Treat conflicts as valid duplicates only after verifying event/document identity and semantics match.

## 11. Sizing Batches by Count and Byte Size

Too small a batch size:

- Many HTTP requests.
- Higher network overhead.
- Lower throughput.

Too large a batch size:

- Huge request payloads.
- High heap usage holding sources and serialized payloads.
- Longer processing times and higher timeout risk.
- A single transport failure leaves many items with ambiguous outcomes.
- Higher memory pressure and queueing on the cluster.

There is no single document count suitable for every workload. Optimal size depends on:

- Average document size.
- Field count and JSON nesting depth.
- Shard count.
- Ingest pipelines.
- Cluster hardware and concurrent search load.
- Network latency.
- Mappings and vector fields.
- Replicas and refresh settings.

### 11.1. Enforce Both Count and Byte Limits

A common starting point to benchmark is a few hundred to roughly a thousand operations per batch, alongside a payload byte cap. Elasticsearch Java's BulkIngester defaults to maxOperations 1000 and maxSize 5 MiB; those are helper defaults, not mandatory limits or optimal values for every system.

Measure throughput and p95/p99 latency in a production-like environment and tune from there.

### 11.2. Splitting Lists into Bounded Chunks

Example partitioning by document count:

~~~java
static <T> List<List<T>> partition(List<T> items, int batchSize) {
    List<List<T>> batches = new ArrayList<>();

    for (int start = 0; start < items.size(); start += batchSize) {
        int end = Math.min(start + batchSize, items.size());
        batches.add(items.subList(start, end));
    }

    return batches;
}
~~~

Usage:

~~~java
for (List<ProductInput> batch : partition(inputs, 500)) {
    processBatch(batch);
}
~~~

This is a simple count-based example. When document sizes vary widely, also bound serialized byte size or use BulkIngester.

### 11.3. Never Load Entire Import Files into Heap

Avoid:

~~~java
List<ProductInput> all = readEntireFileIntoMemory();
processAll(all);
~~~

For large files, read via a stream or cursor:

~~~text
Input stream
    |
    v
Parse bounded batch
    |
    v
Index batch
    |
    v
Persist batch result/checkpoint
    |
    v
Read next batch
~~~

Keep the number of concurrently in-flight batches bounded. If a producer reads faster than Elasticsearch indexes, an unbounded queue will exhaust heap memory.

## 12. BulkIngester for Continuous Ingestion

The Elasticsearch Java API Client provides BulkIngester to automatically buffer operations into bulk requests based on:

- Maximum operations.
- Maximum byte size.
- Flush interval.
- Concurrent request limit.

Example:

~~~java
BulkIngester<Void> ingester = BulkIngester.of(builder -> builder
        .client(elasticsearchClient)
        .maxOperations(500)
        .maxSize(5 * 1024 * 1024)
        .flushInterval(1, TimeUnit.SECONDS)
        .maxConcurrentRequests(1));

for (ProductDocument product : products) {
    ingester.add(operation -> operation
            .index(index -> index
                    .index("products")
                    .id(product.getId())
                    .document(product)));
}

ingester.close();
~~~

close flushes pending operations and releases resources. In long-running applications, manage the ingester's lifecycle properly; never create a new ingester per document.

### 12.1. Backpressure

BulkIngester bounds concurrent requests. When the limit is reached and buffers fill, add can block to apply backpressure instead of accumulating unboundedly.

This is intentional behavior:

- When Elasticsearch slows down, the producer slows down.
- In-memory queues remain bounded.
- The system does not accept work faster than it can index.

If you add a custom executor or queue, enforce bounded capacity and an explicit full-queue policy.

### 12.2. BulkListener and Per-Item Context

BulkIngester supports listeners:

~~~java
BulkListener<String> listener = new BulkListener<>() {

    @Override
    public void beforeBulk(
            long executionId,
            BulkRequest request,
            List<String> contexts) {
        // contexts correspond to operations in this request
    }

    @Override
    public void afterBulk(
            long executionId,
            BulkRequest request,
            List<String> contexts,
            BulkResponse response) {

        for (int i = 0; i < response.items().size(); i++) {
            BulkResponseItem item = response.items().get(i);
            String sourceReference = contexts.get(i);

            if (item.error() != null) {
                handleFailure(
                        sourceReference,
                        item.status(),
                        item.error().type(),
                        item.error().reason());
            } else {
                markIndexed(sourceReference, item.id());
            }
        }
    }

    @Override
    public void afterBulk(
            long executionId,
            BulkRequest request,
            List<String> contexts,
            Throwable failure) {
        // The whole request could not be sent or completed.
        handleRequestFailure(contexts, failure);
    }
};
~~~

When adding an operation, attach context:

~~~java
ingester.add(
        operation -> operation.index(index -> index
                .index("products")
                .id(product.getId())
                .document(product)),
        sourceRecordId);
~~~

Context links each response item directly back to its original record or message without guessing from logs or relying solely on document IDs.

### 12.3. Never Retry Infinitely Inside the Listener

The listener should classify results and route retryable items to a bounded retry scheduler or queue. If the listener immediately re-adds failing items unboundedly, it can form an endless loop and prevent the ingester from ever draining.

### 12.4. Closing the Ingester on Shutdown

BulkIngester buffers operations and may have requests in flight. Call close during application shutdown to flush pending operations and release resources per API semantics. If a process is killed abruptly, the data source must have checkpointing/replay so unacknowledged items are not lost.

## 13. Reactive Ingestion with Spring Data Elasticsearch

ReactiveDocumentOperations does not expose the exact same imperative bulkIndex returning IndexedObjectInformation. Instead, it supports saving a Flux by batch size:

~~~java
Flux<ProductDocument> saved = reactiveOperations.save(
        productFlux,
        ProductDocument.class,
        500);
~~~

The API buffers entities into batches of at most bulkSize elements with a max buffer timeout of 200 ms before issuing a bulk operation.

Example:

~~~java
return readProducts()
        .map(mapper::toDocument)
        .buffer(500)
        .concatMap(batch ->
                reactiveOperations.save(
                        Flux.fromIterable(batch),
                        ProductDocument.class,
                        500)
                    .collectList());
~~~

In this example, buffer batches at the application layer; save Flux also applies its own bulkSize. You can simplify by passing a continuous Flux directly into save(..., bulkSize) if per-batch application handling is unnecessary.

### 13.1. Bounding Concurrency

Avoid:

~~~java
productFlux.flatMap(
        product -> reactiveOperations.save(product),
        1000);
~~~

Concurrency of 1000 can flood the cluster with parallel requests. Pick a small concurrency, measure latency, and rely on backpressure.

### 13.2. Errors in Reactive Batches

Bulk save can emit BulkFailureException in the reactive chain. Handle it with onErrorResume or retryWhen according to policy:

~~~java
return reactiveOperations.save(
            Flux.fromIterable(batch),
            ProductDocument.class,
            batch.size())
        .collectList()
        .onErrorResume(BulkFailureException.class, error -> {
            return handleBulkFailure(batch, error);
        });
~~~

Do not use onErrorContinue as a blanket way to ignore errors. It breaks the association between records and failures and lets the pipeline keep advancing even when data was not saved.

### 13.3. RetryWhen Must Not Retry Every Exception

Retry only transient errors and idempotent operations. Never retry mapping errors, validation errors, or authentication errors endlessly. On bulk exceptions, classify each document failure before deciding to retry.

## 14. Whole-Request Retries When No Response Arrives

When the client receives a timeout or connection reset, there is no BulkResponse to classify items. Some or all operations may have been processed by Elasticsearch.

Example:

~~~text
Client sends bulk
       |
       v
Elasticsearch indexes 70 items
       |
       | connection drops before response
       v
Client sees timeout
~~~

The client cannot tell from the timeout alone which 70 items were written.

Rules:

- Use stable document IDs.
- Prefer idempotent snapshot/index operations.
- Persist batch sources/checkpoints for replay.
- Never retry delta scripts without deduplication or version guards.
- Reconcile afterwards using ID/sourceVersion.
- Cap retries and alert when timeouts spike.

Do not simply raise the request timeout as a cure-all. Investigate cluster load, shard latency, network health, and payload sizes.

## 15. Controlling Ordering and Version Conflicts

Multiple batches or consumers may update the same document concurrently. If an older event is processed after a newer one, newer data can be overwritten.

Example:

~~~text
Product version 10: price = 100
Product version 11: price = 120

Worker A sends version 10 (slow)
Worker B sends version 11 (fast)
Worker B writes first
Worker A writes second
~~~

Without a version guard, the document can revert to price = 100.

Solutions:

- Partition messages by aggregate ID to preserve ordering per partition.
- Keep a single sequential consumer per key when required.
- Use external versioning from source versions.
- Use if_seq_no/if_primary_term for optimistic concurrency control.
- Ignore stale events by comparing sourceVersion.

Bulk actions support per-item version and optimistic concurrency metadata. Never treat Elasticsearch's internal _version as your database's business version without an explicit mapping rule.

## 16. Are Bulk Updates and Scripts Safe to Retry?

Bulk updates can use partial documents or scripts.

Setting a value:

~~~json
{"update":{"_id":"p-100"}}
{"doc":{"price":1299000}}
~~~

Retrying the same value usually yields the same final state.

Adding a delta:

~~~json
{"update":{"_id":"p-100"}}
{"script":{"source":"ctx._source.stock += params.delta","params":{"delta":2}}}
~~~

Retrying the same operation adds twice. You need:

- eventId deduplication.
- sourceVersion checks.
- scripts that record version atomically with the update.
- or converting deltas into absolute snapshots before indexing.

Bulk updates can suffer partial failures just like bulk index. Inspect per-item errors and never blindly retry non-idempotent scripts.

### 16.1. retry_on_conflict Does Not Solve Every Error

The update action supports retry_on_conflict to retry updates on concurrent version conflicts. It is not a retry policy for mapping errors, 429s, network timeouts, or duplicate events.

Do not confuse retry_on_conflict with whole-request retries or event deduplication.

## 17. Separating the Retry Queue and Dead Letter Queue

The DLQ stores items that cannot be processed automatically after exhausting retries or hitting permanent errors:

~~~text
Bulk item failure
       |
       v
Classify error
       |
       +---- transient ----> Retry queue
       |
       +---- permanent ----> DLQ
       |
       +---- unknown ------> Quarantine / operator review
~~~

A DLQ record should contain:

~~~json
{
  "sourceRecordId": "evt-100",
  "documentId": "product-100",
  "targetIndex": "products",
  "attempts": 5,
  "firstFailedAt": "2026-11-13T09:00:00Z",
  "lastFailedAt": "2026-11-13T09:02:00Z",
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "errorMessage": "failed to parse field [price]",
  "sourceVersion": 18,
  "payloadReference": "object-store://failed-events/evt-100"
}
~~~

Payloads can be stored inline or in object storage/databases via reference. Choose retention, encryption, and access policies suited to the data.

### 17.1. DLQ Redrive

Redrive workflow:

1. Identify the root cause of the failure.
2. Fix the data, mapping, or code.
3. Verify the event is not stale relative to current source version.
4. Reprocess using the same document ID / idempotency key.
5. Record the redrive result.
6. Mark the DLQ record as resolved.

Do not replay the entire DLQ blindly after fixing a mapping bug; some events may already be obsolete or invalid.

### 17.2. The DLQ Is Not a Dumping Ground

Monitor:

- Item count in the DLQ.
- Age of the oldest item.
- Failures broken down by type, index, and producer.
- Redrive success rate.
- Stale/duplicate item count.

Assign clear ownership and runbooks for the DLQ. Without alerts and redrive procedures, a DLQ merely hides data loss behind silent queues.

## 18. Checkpoints and Import Recoverability

For file imports or batch jobs, record a checkpoint only after each batch has durable item outcomes:

~~~text
Read source records 1..500
       |
       v
Bulk index
       |
       v
Classify all item results
       |
       +---- success -> mark complete
       +---- retry -> persist retry state
       +---- permanent -> persist DLQ
       |
       v
Commit source checkpoint
       |
       v
Read records 501..1000
~~~

Checkpoints can be:

- File offset or line number.
- Database primary key or cursor.
- Kafka partition offset.
- Change log sequence number.
- Batch ID and processing state.

Never commit a checkpoint before every item's outcome is persisted. If the job crashes after indexing but before checkpointing, the batch may be replayed; stable IDs and idempotent operations keep replay safe.

### 18.1. Batch Ledger

For critical imports, maintain a batch ledger:

| Batch ID | Source range | Success | Retry | DLQ | State |
|---|---|---:|---:|---:|---|
| run-01-0001 | 1–500 | 498 | 1 | 1 | Partial |
| run-01-0002 | 501–1000 | 500 | 0 | 0 | Complete |

A ledger makes restarting jobs, investigating issues, and reconciling data straightforward without piecing facts together from logs.

### 18.2. Never Mark a Batch Complete Just Because the Bulk API Returned HTTP 200

A batch is complete only when every item has been:

- Successfully indexed, updated, or deleted; or
- Confirmed duplicate/stale per policy; or
- Durably stored in a DLQ or rejected-record store.

Items currently retrying or with ambiguous outcomes leave the batch incomplete.

## 19. Optimizing Throughput and Cluster Stability

Bulk throughput depends on multiple factors:

- Batch count and byte size.
- Concurrent request count.
- Shard count and routing distribution.
- Refresh interval.
- Replica count.
- Ingest pipelines.
- Mappings and dynamic fields.
- Document size.
- Competing search workload.

Tuning approach:

1. Start with a moderate batch size, e.g., 500 operations.
2. Cap payload bytes.
3. Start with low concurrency.
4. Measure throughput and latency.
5. Increase batch size or concurrency step by step.
6. Watch 429s, heap, indexing pressure, and search latency.
7. Stop increasing once throughput plateaus or rejections start.

### 19.1. Refresh Interval

During large bulk imports into a new index, you can raise the refresh interval or temporarily disable automatic refresh as part of a planned operational run, then refresh after import. Never do this on an index serving live search without understanding visibility impact.

If temporarily setting refresh_interval = -1, restore the setting afterward and explicitly refresh so documents become searchable.

### 19.2. Replicas

During massive initial loads into a new index, replicas may be adjusted in a controlled procedure to reduce replica write work, then restored before waiting for cluster health. This is an operational trade-off involving durability and availability; never mutate replica settings automatically for routine batches.

### 19.3. Dynamic Mapping

If incoming batches introduce arbitrary new fields, dynamic mapping can create excessive fields and bloat cluster state. Predefine mappings/templates, validate payloads, and cap field counts.

## 20. Observability for Batch Ingestion

Every batch should carry a batchId/correlationId and track:

- input_count.
- indexed_count.
- updated_count.
- failed_count.
- retry_count.
- dlq_count.
- duplicate/stale_count.
- request_latency.
- bulk_bytes.
- retry_delay.
- batch_age.
- consumer_lag.

Metrics by failure outcome:

~~~text
bulk_items_total{result="success"}
bulk_items_total{result="retry"}
bulk_items_total{result="dlq"}
bulk_items_total{result="duplicate"}
bulk_requests_total
bulk_request_duration_seconds
bulk_payload_bytes
bulk_retry_attempts
bulk_dlq_depth
~~~

Avoid using document IDs or user IDs as metric labels because unbounded cardinality breaks monitoring backends. Keep specific IDs in structured logs or controlled trace attributes.

### 20.1. Structured Logs

Example:

~~~json
{
  "event": "elasticsearch_bulk_item_failed",
  "batchId": "import-2026-11-13-001",
  "documentId": "product-100",
  "sourceRecordId": "evt-100",
  "index": "products",
  "status": 429,
  "errorType": "es_rejected_execution_exception",
  "attempt": 2,
  "decision": "RETRY"
}
~~~

Never log full payloads if they contain sensitive data. Store payloads in an access-controlled store and log references when needed.

### 20.2. Alerts

Useful alerts:

- Sustained rise in 429 rate.
- Bulk timeouts exceeding threshold.
- Growing DLQ depth.
- Retry queue age too high.
- Import job stalled with no progress.
- Sudden spike in permanent failures.
- Continuously growing consumer lag.
- High cluster indexing pressure or heap usage.

## 21. Testing Bulk Ingestion

Tests should cover both happy paths and partial failures.

### 21.1. Testing Successful Batches

1. Create the index and mapping.
2. Build 3–5 documents.
3. Call bulkIndex.
4. Refresh the index if searching immediately.
5. Verify documents exist with expected fields.

### 21.2. Testing a Mapping Error on One Document

Build a batch containing one document with an invalid field type:

~~~text
product-1 price = 1000
product-2 price = "not-a-number"
product-3 price = 2000
~~~

Verify:

- Valid items are indexed.
- The bad item appears in failedDocuments or BulkResponse item errors.
- The batch is not treated as a transactional rollback.
- The bad source record goes to the DLQ or rejected queue.

### 21.3. Testing Retrying Only Transient Items

Mock BulkResponse or test the retry classifier:

- 429 is retried.
- 400 mapping error goes to DLQ.
- 403 is not retried repeatedly.
- 409 follows version/duplicate semantics.

Confirm the retry queue contains only retryable items.

### 21.4. Testing Ambiguous Timeout Outcomes

Simulate a transport timeout after the server may already have processed the request. Resend the snapshot with a stable ID and confirm no duplicate document is created.

For delta operations, tests must prove deduplication or version guards prevent double application.

### 21.5. Testing Batch Boundaries

Test:

- Fewer than batch size.
- Exact batch size.
- Batch size + 1.
- Unusually large documents.
- A batch with one invalid record.
- Empty batch.

You do not need massive integration tests for every boundary; unit test the partitioner and use small integration tests to verify Elasticsearch semantics.

### 21.6. Testing Message Acknowledgement

Confirm offsets/acks never advance past records that have neither succeeded nor been written to the DLQ. Verify that an error in one partition does not unnecessarily stall unrelated partitions when partial progress is desired.

### 21.7. Testing Shutdown

For BulkIngester or background batch workers, test that shutdown flushes pending operations or persists checkpoints so the next startup resumes cleanly.

## 22. Complete BatchIndexer Example with Spring Data

Illustrative service:

~~~java
@Service
public class ProductBatchIndexer {

    private static final int BATCH_SIZE = 500;

    private final ElasticsearchOperations operations;
    private final ProductMapper mapper;
    private final FailedItemHandler failedItemHandler;

    public ProductBatchIndexer(
            ElasticsearchOperations operations,
            ProductMapper mapper,
            FailedItemHandler failedItemHandler) {
        this.operations = operations;
        this.mapper = mapper;
        this.failedItemHandler = failedItemHandler;
    }

    public void index(List<ProductInput> inputs) {
        for (int start = 0; start < inputs.size(); start += BATCH_SIZE) {
            int end = Math.min(start + BATCH_SIZE, inputs.size());
            processBatch(inputs.subList(start, end));
        }
    }

    private void processBatch(List<ProductInput> batch) {
        Map<String, ProductInput> inputById = new HashMap<>();
        List<IndexQuery> queries = new ArrayList<>();

        for (ProductInput input : batch) {
            ProductDocument document = mapper.toDocument(input);
            inputById.put(document.getId(), input);

            queries.add(IndexQuery.builder()
                    .withId(document.getId())
                    .withObject(document)
                    .build());
        }

        try {
            operations.bulkIndex(
                    queries,
                    BulkOptions.defaultOptions(),
                    IndexCoordinates.of("products"));
        } catch (BulkFailureException exception) {
            exception.getFailedDocuments().forEach((id, failure) -> {
                ProductInput original = inputById.get(id);
                failedItemHandler.handle(
                        original,
                        id,
                        failure.status(),
                        failure.errorMessage());
            });
        }
    }
}
~~~

This skeleton illustrates processing boundaries. Production code should add:

- Input validation before creating queries.
- Ensuring no duplicate IDs within the batch.
- Error classification by status and reason.
- Persistent retry queues and DLQs.
- Checkpoint/ack semantics.
- Handling request-level errors beyond BulkFailureException.
- Metrics and structured logging.
- Payload byte caps in addition to count caps.
- Reconciliation when timeouts cause ambiguous outcomes.

With BulkFailureException alone, FailureDetails lacks a separate error type. When deeper classification is needed, switch to BulkResponse from the Elasticsearch Java API Client.

## 23. Example Handling Per-Item Outcomes with BulkResponse

A low-level adapter can return normalized outcomes:

~~~java
public record BulkItemOutcome(
        String sourceId,
        String documentId,
        boolean success,
        Integer status,
        String errorType,
        String errorReason) {
}
~~~

Sending the request and matching responses:

~~~java
public List<BulkItemOutcome> indexBatch(List<ProductInput> inputs) {
    BulkResponse response = elasticsearchClient.bulk(request -> {
        request.index("products");

        for (ProductInput input : inputs) {
            ProductDocument document = mapper.toDocument(input);

            request.operations(operation -> operation
                    .index(index -> index
                            .index("products")
                            .id(document.getId())
                            .document(document)));
        }

        return request;
    });

    List<BulkItemOutcome> outcomes = new ArrayList<>();

    for (int i = 0; i < response.items().size(); i++) {
        ProductInput input = inputs.get(i);
        BulkResponseItem item = response.items().get(i);

        if (item.error() == null) {
            outcomes.add(new BulkItemOutcome(
                    input.sourceId(),
                    item.id(),
                    true,
                    item.status(),
                    null,
                    null));
        } else {
            outcomes.add(new BulkItemOutcome(
                    input.sourceId(),
                    item.id(),
                    false,
                    item.status(),
                    item.error().type(),
                    item.error().reason()));
        }
    }

    return outcomes;
}
~~~

In real code, build the operation list upfront and maintain a matching list of context/source IDs. This snippet demonstrates that response items align with request order; never modify or sort responses before correlating.

## 24. Common Pitfalls

### Checking Only the HTTP Status of the Bulk Request

Bulk can return HTTP 200 with errors = true. Inspect every item.

### Treating Bulk as a Transaction

Some items can succeed while others fail. Handle partial success explicitly.

### Retrying the Whole Batch After One Item Fails

Wastes resources and can duplicate delta updates. Retry only eligible items.

### Generating Random IDs on Every Retry

Timeouts and redeliveries can create duplicate documents. Use deterministic IDs.

### Retrying Mapping Errors

The payload remains invalid, so retries never fix it. Route to DLQ or fix data/mapping.

### Retrying 429s Immediately

Increases load and delays cluster recovery. Use backoff, jitter, and concurrency limits.

### Retrying Every 409

Version conflicts may indicate stale events or duplicate creates. Handle according to semantics.

### Catching and Ignoring BulkFailureException

Failed documents disappear silently. Read getFailedDocuments and route to retry or DLQ.

### Logging Only Exception Messages

Insufficient for retrying the right item. Keep document ID, source reference, status, error type, and payload reference.

### Assuming BulkFailureException Exposes Full Error Types

Current FailureDetails only has status and errorMessage. Use low-level BulkResponse when detailed error types/reasons are required.

### Putting Multiple Operations for the Same ID in One Batch

Error maps keyed by ID cannot distinguish operations. Deduplicate batches or correlate by ordered response context.

### Ignoring Byte Size Limits

500 small documents and 500 huge documents differ drastically in payload size. Cap both count and bytes.

### Loading the Entire Source into Heap

Large imports can trigger OutOfMemoryError. Stream inputs and process bounded batches.

### Setting Concurrency Too High

Causes 429s, queueing, and latency spikes. Start low, measure, and adjust.

### Acknowledging Messages Before Persisting Outcomes

Crashes can lose unindexed items. Ack/commit only after success or durable DLQ/retry state persistence.

### Committing Kafka Offsets Past Failed Records

Failed records may never be re-delivered. Manage offsets per partition with contiguous progress.

### Non-Idempotent Delta Bulk Updates

Retries can add or subtract twice. Use event IDs, version guards, or absolute snapshots.

### Failing to Flush BulkIngester on Shutdown

Buffered operations may never be sent. Manage lifecycle shutdown and checkpoints.

### Refreshing After Every Batch

Degrades throughput. Pick a refresh policy matching search visibility requirements.

### Running a DLQ Without a Redrive Process

Failed items accumulate forgotten. Monitor DLQ depth/age and assign an owner.

## 25. Batch Data Ingestion Workflow

When building an import pipeline:

1. Read sources via streams or cursors instead of loading everything into memory.
2. Validate and normalize each record before creating IndexQuery instances.
3. Derive deterministic document IDs from source keys.
4. Maintain mapping/context between each operation and its source record.
5. Batch by both operation count and serialized bytes.
6. Execute bulkIndex or BulkIngester with bounded concurrency.
7. Inspect BulkFailureException or every BulkResponseItem.
8. Classify request-level vs. item-level failures.
9. Mark succeeded items complete.
10. Retry only transient failures with backoff, jitter, and a retry budget.
11. Persist permanent/poison errors to a DLQ or rejected-record store.
12. Handle version conflicts, duplicates, and ambiguous timeouts per idempotency policy.
13. Commit source checkpoints/acks only once every record has a durable outcome.
14. Monitor metrics, consumer lag, retry queues, and DLQ depth.
15. Reconcile source against Elasticsearch after imports or ambiguous failures.
16. Refresh indices according to visibility needs instead of forcing refresh on every batch.
17. Test partial success, timeouts, retries, DLQs, shutdown, and replay.

## 26. Summary

The Bulk API reduces overhead and increases throughput when ingesting many documents, yet every action produces its own outcome. A bulk request can return HTTP 200 while individual items fail. Spring Data Elasticsearch provides ElasticsearchOperations.bulkIndex(...) and BulkFailureException to inspect failed documents; current FailureDetails exposes status and errorMessage. When detailed error types/reasons or per-operation contexts are needed, use the Elasticsearch Java API Client BulkResponse or BulkIngester listener.

Batches must be bounded by both operation count and byte size. No single batch size fits every workload; benchmark throughput, latency, 429 rates, and memory to tune. BulkIngester supports buffering operations, flushing by count/size/time, and applying backpressure via bounded concurrent requests. Reactive Spring Data can use save(Flux, type, bulkSize) to batch Flux elements into bulk operations.

Handle errors per document: retry transient failures such as 429 with exponential backoff and jitter; route mapping/validation errors to a DLQ; treat 401/403 as configuration/permission errors; evaluate 409 using version semantics; and split oversized payloads. Whole-request timeouts produce ambiguous outcomes, making stable document IDs, snapshot/idempotent operations, checkpoints, and reconciliation essential.

Never ack messages or commit source checkpoints before items are indexed, confirmed duplicate/stale per policy, or durably written to a DLQ. Bulk is not a transaction; successful items do not automatically roll back when others fail. A solid pipeline preserves the link from every source record to its operation, response, retry, and DLQ so recovery remains exact.

## References

- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – BulkFailureException API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.html)
- [Spring Data Elasticsearch – BulkFailureException.FailureDetails API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.FailureDetails.html)
- [Spring Data Elasticsearch – BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/BulkOptions.html)
- [Spring Data Elasticsearch – IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
- [Spring Data Elasticsearch – ReactiveDocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveDocumentOperations.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch Java API Client – Bulk indexing](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk)
- [Elasticsearch Java API Client – BulkIngester](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk)
- [Elasticsearch – Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
