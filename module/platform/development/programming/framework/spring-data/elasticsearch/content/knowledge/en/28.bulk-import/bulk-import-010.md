# Large Data Loads, Batching, and Memory Control

When loading a few dozen documents into Elasticsearch, calling `save()` per entity can still meet requirements. However, when importing hundreds of thousands or millions of records, issuing individual requests incurs heavy network, serialization, and request-handling overhead. Applications generally need to use the Bulk API to send many index/update/delete operations in a single request.

The Bulk API improves throughput, yet that does not mean stuffing the entire dataset into one list and sending it all at once. An oversized batch can spike heap usage, generate huge request payloads, lengthen processing times, and make retries expensive. An undersized batch creates too many requests and reduces efficiency.

A large import pipeline must control several dimensions simultaneously:

- **Data source:** read sequentially or by cursor, never loading the entire dataset into the heap.
- **Batch size:** cap the document count and payload size of each bulk request.
- **Concurrency:** cap the number of concurrent in-flight requests to establish backpressure.
- **Per-item errors:** distinguish succeeded items, retryable errors, and data errors requiring separate handling.
- **Refresh and replicas:** choose appropriate policies to maximize throughput during import.
- **Checkpoints:** record progress only after a batch has been handled safely.
- **Memory:** release objects, buffers, and responses after every batch.

In Spring Data Elasticsearch, `ElasticsearchOperations` provides bulk methods such as `bulkIndex`, `bulkUpdate`, and `bulkDelete`. Combining them with streaming data sources, bounded batches, and selective retries lets an application import large datasets reliably.

## 1. Why Do We Need the Bulk API?

Suppose an application needs to index 500,000 products. Calling `save()` separately for each product can require sending 500,000 requests to Elasticsearch.

```text
save(product-1)  -> HTTP request 1
save(product-2)  -> HTTP request 2
save(product-3)  -> HTTP request 3
...
save(product-N)  -> HTTP request N
```

Every single request incurs overhead such as:

- Opening and handling the HTTP request/response.
- Serializing the document and metadata.
- Coordinating the request across client, coordinating node, and shards.
- Handling refresh/replication per cluster configuration.
- Managing callbacks, futures, or connections on the application side.

The Bulk API lets you send many operations in a single request:

```text
Batch 1: document 1 ... document 500     -> HTTP request 1
Batch 2: document 501 ... document 1000  -> HTTP request 2
Batch 3: document 1001 ... document 1500 -> HTTP request 3
...
```

Instead of 500,000 requests, the application can send roughly 1,000 requests if each batch holds 500 documents. Actual figures should be benchmarked; optimal batch size depends on document size, shard count, mappings, analyzers, replicas, and cluster resources.

The Bulk API does not turn the whole batch into a transaction. Each item is processed independently and some items can succeed while others fail. Therefore, the application must inspect per-item results.

## 2. How Does the Bulk API Work?

The Elasticsearch Bulk API uses the NDJSON (Newline Delimited JSON) format. Each operation consists of a metadata/action line and optionally a source or payload line.

Example indexing two documents:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "P-100" } }
{ "name": "Mechanical Keyboard", "price": 2500000 }
{ "index": { "_id": "P-101" } }
{ "name": "Wireless Mouse", "price": 450000 }
```

Common actions:

| Action | Next Line | Meaning |
|---|---|---|
| `index` | Source document | Create or replace a document by ID. |
| `create` | Source document | Create new only; fails if ID already exists. |
| `update` | Update payload | Partially update or run a script/upsert. |
| `delete` | None | Delete a document by ID. |

Example update and delete:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "update": { "_id": "P-100" } }
{ "doc": { "price": 2600000 } }
{ "delete": { "_id": "P-101" } }
```

Bulk requests end with a trailing newline. When building NDJSON manually, missing the final newline can make the request invalid. When using Spring Data, the library generates the payload on behalf of the application.

### 2.1. Bulk Response Is Not an All-or-Nothing Result

A bulk response can have `errors: true` even though the overall HTTP request was processed by Elasticsearch. Each element in `items` carries its own status and outcome:

```json
{
  "took": 42,
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
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [price]"
        }
      }
    }
  ]
}
```

In this example, `P-100` was indexed successfully while `P-101` hit a mapping error. Never treat the whole batch as failed and blindly resend all items.

## 3. Using `ElasticsearchOperations.bulkIndex`

Spring Data Elasticsearch provides `ElasticsearchOperations` to execute bulk operations without building NDJSON manually. In Spring Data Elasticsearch 5.x APIs, you can create an `IndexQuery` for each entity and send the list via `bulkIndex`.

Example entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private double price;

    // constructors, getters, setters
}
```

Creating `IndexQuery` items and bulk indexing:

```java
import java.util.List;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

public class ProductBulkIndexer {

    private final ElasticsearchOperations operations;

    public ProductBulkIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void indexBatch(List<ProductDocument> products) {
        List<IndexQuery> queries = products.stream()
                .map(product -> new IndexQueryBuilder()
                        .withId(product.getId())
                        .withObject(product)
                        .build())
                .toList();

        operations.bulkIndex(queries, ProductDocument.class);
    }
}
```

`IndexQueryBuilder` lets you attach the ID and object to index. `bulkIndex` submits the list of operations in a single bulk request. If the ID already exists, the `index` action replaces the existing document per Elasticsearch index operation semantics.

If you want to reject already-existing IDs, choose `create` semantics appropriate for the API/version in use. Do not assume `bulkIndex` defaults to `create`.

### 3.1. Choosing the Right Bulk Operation

Spring Data Elasticsearch offers purpose-built bulk methods:

| Method | Purpose |
|---|---|
| `bulkIndex(...)` | Index or replace multiple documents. |
| `bulkUpdate(...)` | Send multiple `UpdateQuery` items to update documents. |
| `bulkDelete(...)` | Delete multiple documents by ID/query per API support. |

Select the operation matching business semantics. If replacing the entire document, use `index`. If updating only specific fields while preserving others, use `update` with a partial document. If creating only new documents and failing on duplicate IDs, use the `create` operation via the appropriate API.

## 4. Splitting Data into Bounded Batches

Do not construct a single `List` containing the entire dataset and call bulk once:

```java
// Unsuitable for very large datasets.
List<ProductDocument> allProducts = loadAllProducts();
indexer.indexBatch(allProducts);
```

If each document averages 5 KB, 500,000 documents represent roughly 2.5 GB of raw source data even before counting Java object overhead, `String`s, collections, mapping metadata, and payload serialization. Actual memory consumption can be substantially higher.

Instead, read sequentially and hold only one batch in the heap at a time:

```java
int batchSize = 500;
List<IndexQuery> batch = new ArrayList<>(batchSize);

for (ProductDocument product : source) {
    batch.add(new IndexQueryBuilder()
            .withId(product.getId())
            .withObject(product)
            .build());

    if (batch.size() >= batchSize) {
        operations.bulkIndex(batch, ProductDocument.class);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    operations.bulkIndex(batch, ProductDocument.class);
    batch.clear();
}
```

Each batch is sent as soon as it fills. After the request completes, `clear()` drops references to the `IndexQuery` instances in the list so the garbage collector can reclaim objects if no other references remain.

### 4.1. Do Not Rely on Document Count Alone

A batch of 500 documents can be tiny if each document has a few fields, yet huge if each document contains HTML content, long nested arrays, or large text fields.

Bound all of:

- **Document count:** maximum documents per batch.
- **Estimated bytes:** total estimated payload size.
- **Processing time:** duration to process one batch.

For example, an initial cap might be 500 documents or 5–10 MB of payload depending on the workload; this is only a starting point for benchmarking, not a universal threshold for every cluster. For very large documents, lower the item count per batch.

Elasticsearch recommends benchmarking to discover the optimal bulk size. Scale batch size up until throughput stops improving significantly or you start seeing memory pressure, rising latency, and 429 errors, then back down to the prior stable level.

### 4.2. Using a Byte Threshold

If the application can estimate source size before serialization, flush whenever the byte cap is reached:

```java
int maxDocuments = 500;
long maxEstimatedBytes = 8L * 1024 * 1024;

List<IndexQuery> batch = new ArrayList<>(maxDocuments);
long estimatedBytes = 0;

for (ProductDocument product : source) {
    IndexQuery query = new IndexQueryBuilder()
            .withId(product.getId())
            .withObject(product)
            .build();

    long documentBytes = estimatePayloadBytes(product);
    boolean batchFull = batch.size() >= maxDocuments;
    boolean bytesFull = !batch.isEmpty()
            && estimatedBytes + documentBytes > maxEstimatedBytes;

    if (batchFull || bytesFull) {
        operations.bulkIndex(batch, ProductDocument.class);
        batch.clear();
        estimatedBytes = 0;
    }

    batch.add(query);
    estimatedBytes += documentBytes;
}

if (!batch.isEmpty()) {
    operations.bulkIndex(batch, ProductDocument.class);
}
```

`estimatePayloadBytes` is an application-implemented function estimating JSON/UTF-8 size. Object size in the Java heap does not equal JSON size over the wire. When exact payload limits are needed, measure after serialization or use a bulk client that tracks byte thresholds.

If a single document itself exceeds the threshold, decide how to handle it separately, reject it, or write it via a dedicated path. Never let an empty batch loop infinitely because an oversized document cannot fit under the cap.

## 5. Streaming Data Sources

Batching on the Elasticsearch side is not enough if the application loads the entire data source into the heap first. The source must also be read incrementally.

Common approaches:

- JDBC cursor/stream with an appropriate fetch size.
- Spring Data repositories returning `Stream<T>`, closed properly.
- Keyset or monotonically increasing ID pagination.
- Reading CSV/JSON files line-by-line or record-by-record.
- Consumers pulling messages in batches from a queue.
- Source APIs with cursors or continuation tokens.

Example reading a stream from a repository:

```java
try (Stream<SourceProduct> products = sourceRepository.streamAllProducts()) {
    // Consume incrementally and close the stream when finished.
}
```

With JDBC, streaming typically requires an open transaction and driver-specific fetch size configuration. If the driver defaults to buffering the whole result set on the client, returning a Java `Stream` does not automatically mean records are fetched one by one.

### 5.1. Combining Source Streams and Bulk Batches

Example import service reading a source stream and flushing batches:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

public class ProductImportService {

    private static final int BATCH_SIZE = 500;

    private final SourceProductRepository sourceRepository;
    private final ElasticsearchOperations operations;

    public ProductImportService(
            SourceProductRepository sourceRepository,
            ElasticsearchOperations operations) {
        this.sourceRepository = sourceRepository;
        this.operations = operations;
    }

    public void importAll() {
        List<IndexQuery> batch = new ArrayList<>(BATCH_SIZE);

        try (Stream<SourceProduct> source = sourceRepository.streamAllProducts()) {
            source.forEach(sourceProduct -> {
                ProductDocument document = map(sourceProduct);

                batch.add(new IndexQueryBuilder()
                        .withId(document.getId())
                        .withObject(document)
                        .build());

                if (batch.size() >= BATCH_SIZE) {
                    operations.bulkIndex(batch, ProductDocument.class);
                    batch.clear();
                }
            });
        }

        if (!batch.isEmpty()) {
            operations.bulkIndex(batch, ProductDocument.class);
            batch.clear();
        }
    }

    private ProductDocument map(SourceProduct source) {
        // Map source fields to the Elasticsearch document.
        throw new UnsupportedOperationException("Example only");
    }
}
```

This example illustrates the data flow, not a complete production implementation for every repository. In production code, ensure the source stream actually uses a cursor/fetch size and avoid retaining source entities after mapping.

`Stream.forEach` executes sequentially here. Do not casually tack on `.parallel()`, as that constructs many objects concurrently, creates thread contention on the batch list, and breaks concurrency/memory controls. If parallel mapping is needed, use a bounded queue and bounded consumers.

### 5.2. Keyset Pagination When Sources Do Not Support Streaming

If the source supports querying by ascending ID, read page-by-page using keyset pagination:

```sql
SELECT id, name, price
FROM source_products
WHERE id > :lastSeenId
ORDER BY id
LIMIT :pageSize;
```

After a batch is indexed successfully, update `lastSeenId` to the final ID of the batch. This avoids deep offset pagination in databases and enables resuming from a checkpoint.

If IDs do not reflect update order, or older rows can be updated during import, use a version/updated-timestamp watermark or CDC. Never treat `id > lastSeenId` alone as guaranteeing every concurrent mutation is captured.

## 6. Controlling Application-Side Memory

An import job consumes memory across multiple layers:

```text
Source database / file / queue
           |
           v
  Source objects in heap
           |
           v
   Mapping / transformation
           |
           v
      Batch buffer
           |
           v
 JSON serialization buffer
           |
           v
 HTTP request / response
           |
           v
 Bulk response metadata
```

If every layer retains copies of the data, peak heap usage can vastly exceed raw source size. The following principles keep memory bounded:

- Read the source page-by-page or record-by-record.
- Hold only one or a small number of in-flight batches.
- Use batch lists with bounded capacity.
- Clear buffers after flushing and drop references to old entities.
- Never accumulate all bulk responses in a large collection.
- Never collect a stream into a `List` for large datasets.
- Limit concurrent async requests in flight.
- Bound queues between producers and consumers.
- Never accumulate full exception/source payloads in logs or an in-heap dead-letter list.
- Monitor heap usage, allocation rate, GC pauses, and direct buffers.

### 6.1. Avoid `findAll()` for Large Imports

Unsuitable pattern:

```java
List<SourceProduct> products = sourceRepository.findAll();
List<ProductDocument> documents = products.stream()
        .map(this::map)
        .toList();

operations.save(documents);
```

This snippet holds at least two huge lists in memory simultaneously: source entities and target documents. Combined with serialization buffers, peak memory climbs even higher.

Replace with streaming and batching:

```java
try (Stream<SourceProduct> products = sourceRepository.streamAllProducts()) {
    Iterator<SourceProduct> iterator = products.iterator();
    List<IndexQuery> batch = new ArrayList<>(500);

    while (iterator.hasNext()) {
        SourceProduct source = iterator.next();
        ProductDocument document = map(source);

        batch.add(new IndexQueryBuilder()
                .withId(document.getId())
                .withObject(document)
                .build());

        if (batch.size() == 500) {
            operations.bulkIndex(batch, ProductDocument.class);
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        operations.bulkIndex(batch, ProductDocument.class);
    }
}
```

### 6.2. Do Not Retain Payloads Only to Retry Whole Batches

If a batch fails, retaining entire object graphs in an unbounded retry list can grow the heap without bound. Instead:

- Retain only retryable failed items inside a bounded buffer.
- Cap retry attempts and total retry duration.
- Write non-retryable errors to a durable dead-letter store/file/queue.
- If a batch is too large, split the failed subset before resending.
- Never dump huge source JSON into logs; log ID, status, error type, and a payload reference if needed.

### 6.3. Heap Is Not the Only Memory Consumer

HTTP clients can allocate off-heap direct buffers; TLS, compression, serialization, and response bodies also consume memory. Therefore, looking at `-Xmx` alone is insufficient to assess total memory footprint.

Also monitor:

- Heap used/committed and old-generation occupancy.
- Allocation rate and GC pauses.
- Direct/mapped buffer pools.
- Open connections and pending requests.
- Queue/batch sizes.
- Container memory limits and RSS.

## 7. Concurrency and Backpressure

Increasing concurrent bulk requests can boost throughput up to a threshold. Beyond that, the cluster can saturate, request latency rises, write/bulk thread pool queues fill, and Elasticsearch returns 429 errors.

Do not create a future upfront for every batch in the entire dataset:

```java
// Unsuitable: task/future count grows with total batch count.
List<CompletableFuture<?>> futures = allBatches.stream()
        .map(this::sendAsync)
        .toList();
```

For large datasets, the future list grows without bound. Instead, cap in-flight batches and read/submit new batches only when capacity is available.

### 7.1. Producer-Consumer Model with a Bounded Queue

```text
Source reader
     |
     v
Bounded queue (e.g. max 4 batches)
     |
     +--------+--------+
     |        |        |
     v        v        v
 Worker 1  Worker 2  Worker 3
     |        |        |
     +--------+--------+
              |
              v
       Elasticsearch
```

When the queue is full, the producer must wait or slow down reading. This is backpressure: the source read pace adjusts to Elasticsearch's write throughput.

Example using `BlockingQueue`:

```java
BlockingQueue<List<IndexQuery>> queue = new ArrayBlockingQueue<>(4);
```

The producer can enqueue at most four unprocessed batches. If consumers fall behind, `put()` blocks rather than generating more batches.

In real applications, also handle completion signals, worker exceptions, cancellation, and queue shutdown. Never use an unbounded queue such as default `LinkedBlockingQueue` for an unbounded import.

### 7.2. Choosing Concurrency from Measurements

Start with a single worker and a moderate batch size. Measure throughput, latency, and resource usage. Then increase concurrency incrementally—such as 1 → 2 → 4—and observe where throughput plateaus or 429s/latency spike.

There is no universal rule like "one worker per shard" across workloads. A single bulk request can fan out to multiple shards; document routing, payload size, and analyzer cost all affect capacity. Pick concurrency based on benchmarks and cluster capacity.

## 8. Handling Per-Item Bulk Errors

The Bulk API can partially succeed. The application must classify failures instead of retrying the entire request.

Common error groups:

| Error Group | Example | Handling Approach |
|---|---|---|
| Invalid data | Mapping parse error, wrong field type, oversized document. | Do not retry as-is; fix data or route to dead-letter. |
| Business conflict | `version_conflict_engine_exception`, ID already exists on `create`. | Handle per version/upsert policy or skip if already processed. |
| Temporary overload | HTTP 429, rejection. | Retry failed items with backoff and cap concurrency. |
| Transient infrastructure error | Timeout, connection reset, 502/503/504. | Determine item status; controlled retry ensuring idempotency. |
| Config/permission error | Index missing, unauthorized/forbidden. | Stop job and fix config/permissions; do not retry continuously. |

### 8.1. Retry Only Failed Items

Suppose a bulk request of 500 items has 490 successes, 5 429s, and 5 mapping errors. A sound strategy:

- Record the 490 succeeded items.
- Route the 5 429 items to a bounded retry queue.
- Write the 5 mapping errors to a dead-letter store for investigation.
- Do not resend the 490 succeeded items simply because the response reported `errors: true`.

If the Spring Data API you use throws an exception containing the failed documents/errors, extract that list to classify. With the lower-level Elasticsearch Java API Client, inspect `BulkResponse.errors()` and every `BulkResponseItem` in the response. Exact exception types and response structures depend on client version.

### 8.2. Exponential Backoff and Jitter

When Elasticsearch returns 429 due to overload, immediate retries amplify load. Use exponential backoff:

```text
attempt 1: wait ~200 ms
attempt 2: wait ~400 ms
attempt 3: wait ~800 ms
attempt 4: wait ~1600 ms
...
```

Add random jitter so multiple workers do not retry simultaneously. Configure:

- Maximum retry attempts.
- Maximum wait cap.
- Total time budget a job can spend retrying.
- Allowlist of retryable status/error types.
- Mechanism to lower concurrency when 429 rates climb.

These numbers are illustrative only. Choose real values from observed latency and operational policy.

### 8.3. Do Not Retry Mapping Errors Infinitely

A field parse error caused by sending a string into a numeric field will not disappear one second later. Retrying unrecoverable errors wastes bandwidth, heap, and cluster capacity. Route data errors to dead-letter storage with ID, source version, error type, and reason.

## 9. Idempotency During Retries

Safe retries depend on the operation type:

- Indexing a document with a stable ID and full source usually retries safely by overwriting to the same state.
- Creating a document can return a conflict if the prior attempt succeeded while the response was lost.
- Additive partial updates (such as incrementing a counter) may not be idempotent; retries can apply twice.
- Scripted updates must be designed to recognize version/event IDs or preserve idempotent semantics.
- Deleting by the same ID is usually safe to retry under policies treating an already-deleted document as acceptable.

Example using a deterministic ID:

```java
IndexQuery query = new IndexQueryBuilder()
        .withId(sourceProduct.getBusinessId())
        .withObject(document)
        .build();
```

If the same source record always produces the exact same `_id`, resending the same index operation will not create duplicate documents. If a random ID is generated on every retry, the same record can appear as multiple documents.

For event streams, persist event IDs or source versions to avoid re-applying older events. If data can arrive out of order, verify version/timestamp before writing so stale versions do not overwrite newer ones.

## 10. Checkpoints and Resuming Imports

Large imports can run for minutes or hours. If the process stops at batch 700, the application needs to know which batches were successfully written in order to resume.

Checkpoints typically record:

- Import job ID and source dataset/version.
- Last processed source key or cursor.
- Counts of batches sent/succeeded/failed.
- Start/update timestamps.
- Target index/alias and mapping version.
- Completion or recovery status.

Golden rule: update the checkpoint only after the batch has been confirmed successful by Elasticsearch under job policy. If a batch contains failed items, the checkpoint must not skip past them unless those items have already been persisted in a durable retry/dead-letter store.

```text
Read source batch
       |
       v
Bulk index batch
       |
       v
Inspect every item
       |
       +---- retryable errors? ----> persist retry work
       |
       +---- permanent errors? ----> persist dead-letter
       |
       v
All items accounted for
       |
       v
Commit source checkpoint
```

If the application writes the checkpoint before the bulk completes, a crash right after checkpointing skips unindexed documents. If it writes the checkpoint after the bulk succeeds yet crashes before persisting the checkpoint, the batch can be resent; deterministic IDs and idempotent sinks make that replay safe.

## 11. Refresh Policy During Bulk Imports

Elasticsearch is near real-time. Successfully indexed documents do not automatically appear in searches immediately; they become searchable after a refresh.

During a large bulk load, refreshing too often reduces throughput by generating many small segments and increasing merge work. If the application does not need to search newly imported documents immediately, avoid refreshing after every batch.

Common refresh options:

| Policy | Meaning |
|---|---|
| `NONE` / no refresh requested | Fast writes; documents become searchable on natural refresh cycles or manual refresh. |
| `IMMEDIATE` / `true` | Requests immediate refresh after the request; can hurt throughput if used per batch. |
| `WAIT_UNTIL` / `wait_for` | Waits for the next refresh to make documents searchable. |

Enum names and configuration methods in Spring Data vary by version. For large imports, typically send bulks with a policy that does not trigger per-request refreshes, then refresh once when publishing data.

REST example:

```http
POST /products/_bulk?refresh=false
Content-Type: application/x-ndjson

{ "index": { "_id": "P-100" } }
{ "name": "Mechanical Keyboard", "price": 2500000 }
```

After the import finishes:

```http
POST /products/_refresh
```

Do not refresh after every batch unless immediate reads are required. If imports run continuously and users require new data within a specific SLA, tune the refresh interval and visibility policy rather than forcing refreshes on every request.

## 12. Replicas and Active Shards During Data Loads

Replicas improve fault tolerance and search throughput, yet during large imports every document index must also update replica shards. This can impact throughput.

Some systems follow a batch load workflow on a new index:

1. Create the new index with proper mappings and settings.
2. During bulk import, consider replica settings aligned with availability needs.
3. Load data and handle failures.
4. Wait for shards to become active per policy.
5. Restore required replica settings.
6. Refresh and validate data.
7. Switch the alias to the new index.

Do not blindly set replicas to 0 in production without evaluating availability risk. If a node fails while replicas are 0, the index can lose availability or lack the expected durability protection.

`wait_for_active_shards` governs how many shard copies must be active before an operation proceeds. It is an availability/acknowledgement setting—it does not replace item retries and does not guarantee every item in the bulk request succeeded.

## 13. Using `BulkOptions`

Spring Data Elasticsearch provides `BulkOptions` to configure bulk request options such as refresh policy, timeout, and required active shard copies. Builder usage and `bulkIndex` overloads vary by Spring Data Elasticsearch version.

General example:

```java
import org.springframework.data.elasticsearch.core.BulkOptions;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

operations.bulkIndex(indexQueries, options, ProductDocument.class);
```

Here `RefreshPolicy.NONE` indicates no refresh is requested after the bulk request. When the import finishes, the service can trigger a refresh via `IndexOperations` if immediate publication is needed.

Check packages, builder methods, and overloads against the exact dependency version in use. Not every version shares identical APIs or enum names.

## 14. Importing with a Reindex / Alias Strategy

For large imports where user impact must be minimized, create a new index and switch an alias after completion:

```text
Alias products-read
       |
       v
Index products-v1 (currently serving)

Create products-v2
       |
       v
Bulk import into products-v2
       |
       v
Validate count / sample / errors
       |
       v
Atomic alias switch
       |
       v
Alias products-read -> products-v2
```

Example creating the new index:

```http
PUT /products-v2
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "price": { "type": "double" },
      "category": { "type": "keyword" }
    }
  }
}
```

After importing and verifying, switch the alias in a single `_aliases` request:

```http
POST /_aliases
{
  "actions": [
    { "remove": { "index": "products-v1", "alias": "products-read" } },
    { "add": { "index": "products-v2", "alias": "products-read" } }
  ]
}
```

Switching aliases in one request updates the alias atomically in cluster state. If the source keeps receiving writes during the import, you also need dual-writes or delta/CDC catch-up so updates between the snapshot and alias switch are not lost.

## 15. Monitoring Progress and Throughput

An import job should emit batch-level metrics rather than merely logging "started" and "finished."

Useful metrics:

| Metric | Meaning |
|---|---|
| `documents_read_total` | Documents read from source. |
| `documents_indexed_total` | Items confirmed successful. |
| `documents_failed_total` | Failed items. |
| `bulk_requests_total` | Bulk requests sent. |
| `bulk_batch_documents` | Items per batch. |
| `bulk_payload_bytes` | Estimated/actual payload size. |
| `bulk_request_duration` | Processing time of a bulk request. |
| `bulk_retry_total` | Items/requests retried. |
| `queue_depth` | Batches waiting to be processed. |
| `heap_used` / `gc_pause` | Memory and GC health. |
| `http_429_total` | Rejection/overload error count. |

Throughput can be computed as:

\[
Throughput = \frac{\text{documents indexed successfully}}{\text{elapsed seconds}}
\]

Monitor p50/p95/p99 latency of bulk requests. If batch size increases without raising throughput while latency and memory grow, revert to a smaller batch size.

Batch logs should include job ID, batch sequence, count, duration, success/failure counts, and checkpoint. Avoid logging complete source documents or payloads, as that risks leaking data and bloating log storage.

## 16. Optimizing Mappings and Data Before Import

Bulk throughput also depends on how documents are indexed:

- Declare only needed fields; avoid mapping explosion from uncontrolled dynamic fields.
- Choose appropriate `keyword`, `text`, numeric, date, geo, or nested types.
- Avoid excessive nested objects unless required.
- Normalize data before sending to avoid mapping parse errors.
- Use deterministic IDs to support retries and upserts.
- Avoid sending unnecessary null/empty fields on massive datasets.
- Consider ingest pipelines for centralized transformations; measure pipeline cost.
- Avoid heavy aggregations/searches on the same index during peak import windows when possible.

Do not disable mappings or analyzers merely for speed and forget to re-enable them. When preparing a fresh index for import, design the right mapping upfront and validate queries after import.

## 17. Bulk Update and Bulk Delete

Not every import creates new documents. Some jobs update or delete many documents.

### 17.1. Bulk Update

Example updating product prices:

```java
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateQueryBuilder;

List<UpdateQuery> updates = new ArrayList<>();

for (PriceChange change : changes) {
    UpdateQuery update = UpdateQuery.builder(change.productId())
            .withDocument(Document.create().append("price", change.newPrice()))
            .build();
    updates.add(update);
}

operations.bulkUpdate(updates, ProductDocument.class);
```

This snippet illustrates partial updates; verify `UpdateQuery` and `Document` builder APIs against your Spring Data version. Partial updates preserve fields omitted from the payload. If upserting when a document does not exist, configure upsert semantics explicitly.

### 17.2. Bulk Delete

When you have a list of IDs to delete, bulk delete can be used:

```java
List<String> ids = expiredProducts.stream()
        .map(ExpiredProduct::id)
        .toList();

operations.bulkDelete(ids, ProductDocument.class);
```

For large lists, split IDs into batches as well. Never materialize a list of millions of IDs if you can stream from the source.

If deleting by query criteria across many documents, consider the Delete By Query API. It has its own semantics, throttling, slicing, and conflict handling; it is not equivalent to a bulk delete by ID list.

## 18. Bulk API vs. Reindex API

Both APIs process many documents, yet serve different purposes:

| Bulk API | Reindex API |
|---|---|
| Client submits index/create/update/delete actions. | Elasticsearch reads documents from a source index and writes to a destination index. |
| Best when source data resides in a database, file, queue, or application. | Best when copying/transforming data between Elasticsearch indices. |
| Application handles reading source, batching, and retries. | Elasticsearch manages scanning/reindexing per request. |
| Can combine multiple action types in one request. | Can apply scripts and queries to filter/transform during reindex. |

When source data originates outside Elasticsearch, the Bulk API is usually the right fit. When migrating data from an old index to a new index, the Reindex API can be simpler; still manage slicing, throttling, conflicts, and destination capacity.

## 19. Complete Large-Import Workflow

A safe workflow can be structured across these steps:

1. **Prepare index:** create the index/alias and exact mapping before loading.
2. **Establish source snapshot:** record the data cutoff or source version.
3. **Open source cursor:** use streams, fetch size, or keyset pagination to read sequentially.
4. **Map documents:** convert source rows into Elasticsearch entities with deterministic IDs.
5. **Create bounded batches:** cap both count and estimated bytes.
6. **Send bulk requests:** use `bulkIndex`, `bulkUpdate`, or `bulkDelete`.
7. **Classify responses:** inspect each item and split success/retry/dead-letter.
8. **Retry with backoff:** retry only transiently failed items with idempotent semantics.
9. **Checkpoint:** persist progress only once every item in the batch is processed or durably saved to retry/dead-letter.
10. **Adjust load:** watch 429s, latency, heap, queue depth, and reduce concurrency when needed.
11. **Finalize visibility:** refresh when needed and verify data in the index.
12. **Publish:** switch aliases or mark the job complete after verification.
13. **Reconcile:** compare source/target counts, error counts, sample documents, and business metrics.

## 20. Example Skeleton of a Checkpointed Import

The example below illustrates structuring batching and checkpoints. The source, checkpoint, and dead-letter interfaces are application abstractions to be backed by a real database or queue.

```java
public class ImportJob {

    private static final int BATCH_SIZE = 500;

    private final SourceProductRepository source;
    private final ElasticsearchOperations operations;
    private final ImportCheckpointStore checkpoints;
    private final DeadLetterStore deadLetters;

    public void run(String jobId) {
        String lastId = checkpoints.loadLastId(jobId);
        List<IndexQuery> batch = new ArrayList<>(BATCH_SIZE);
        String lastIdInBatch = lastId;

        try (Stream<SourceProduct> rows = source.streamAfter(lastId)) {
            Iterator<SourceProduct> iterator = rows.iterator();

            while (iterator.hasNext()) {
                SourceProduct row = iterator.next();
                ProductDocument document = map(row);

                batch.add(new IndexQueryBuilder()
                        .withId(document.getId())
                        .withObject(document)
                        .build());
                lastIdInBatch = row.id();

                if (batch.size() >= BATCH_SIZE) {
                    sendAndAccount(batch, jobId);
                    checkpoints.saveLastId(jobId, lastIdInBatch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            sendAndAccount(batch, jobId);
            checkpoints.saveLastId(jobId, lastIdInBatch);
            batch.clear();
        }
    }

    private void sendAndAccount(List<IndexQuery> batch, String jobId) {
        // Send the batch, inspect item-level outcomes, persist retryable
        // and permanent failures, and return only when every item is accounted for.
    }
}
```

The crucial detail is that `sendAndAccount` must ensure every item is classified before the checkpoint is committed. If you simply send a bulk request and ignore the response, the checkpoint can advance past failed documents and the import will never retry them.

This skeleton uses `lastId` as a keyset checkpoint. If the source can update older IDs while the job runs, add source versions, watermarks, or change logs so updates are not missed.

## 21. Testing and Operating Imports

Test against a real Elasticsearch instance or Testcontainers using a compatible version. Mocking `ElasticsearchOperations` works for verifying batch construction, yet cannot verify Bulk API behavior, mappings, partial failures, or throughput.

Scenarios to cover:

- Import smaller than one batch.
- Import matching the exact batch size.
- Multiple batches with a partial final batch.
- One document with a mapping error inside a valid batch.
- Bulk response returning 429 and succeeding on retry.
- Bulk request timing out after Elasticsearch may have partially processed it.
- Process stopping after bulk success but before checkpointing.
- Process stopping after checkpoint persistence.
- Source stream throwing an exception and closing cleanly.
- Queue filling up and applying backpressure to the producer.
- Index missing or user lacking permissions.
- Refreshing post-import and verifying search visibility.

When benchmarking:

1. Use data matching production size and field distribution.
2. Fix shard count, replicas, mappings, and analyzers.
3. Test multiple batch sizes and concurrency levels.
4. Measure docs/second, p95 bulk latency, 429s, heap, and GC.
5. Repeat runs enough times to smooth out cache and background load variance.
6. Pick a stable configuration, not merely the configuration with the highest single-run peak throughput.

## 22. Common Pitfalls

| Symptom | Possible Cause | Fix |
|---|---|---|
| Heap grows continuously during import | Using `findAll()`, accumulating all batches/futures/responses, or unbounded retry lists. | Stream sources, bound batches/queues, clear references, and cap retries. |
| Bulk requests are too slow | Batches too large, heavy documents, overloaded shards/nodes, or poor concurrency. | Measure payload/latency, tune down batch/concurrency, optimize mappings. |
| Too many tiny requests | Batch size too small or flushing per document. | Increase batch size gradually and benchmark. |
| Bulk response has errors yet job reports success | Only checking HTTP status, ignoring item-level errors. | Inspect `errors` and every item in the response. |
| Retries duplicate data | Generating new IDs per attempt or non-idempotent updates. | Use deterministic IDs, source versions, and idempotent operations. |
| Single mapping error retries whole batch forever | Not separating permanent and transient failures. | Dead-letter data errors; retry only recoverable errors. |
| Elasticsearch returns 429s continuously | Producer outpaces cluster, concurrency/queue too high. | Apply backpressure, reduce workers, exponential backoff with jitter. |
| Documents indexed yet absent in search | Refresh has not occurred yet. | Wait for natural refresh or refresh once post-import if needed. |
| Checkpoints skip failed documents | Saving checkpoints before full item classification. | Commit only after every item is processed or durably stored in retry/dead-letter. |
| Import remains slow despite disabling refresh | Mapping/analyzers/replicas/aggregations or I/O are the true bottleneck. | Profile the full pipeline and cluster rather than focusing solely on refresh. |
| Count-based batch sizes cause OOM | Document sizes vary wildly. | Bound estimated payload bytes too and handle oversized documents separately. |
| Parallel streams spike memory | Constructing too many objects and requests concurrently without backpressure. | Use bounded queues and a finite consumer pool. |

## 23. Design Principles

- Use the Bulk API instead of one request per document for large data imports.
- Split batches by both document count and estimated payload size.
- Read sources via streams, cursors, or keyset pagination; avoid `findAll()` for large datasets.
- Keep only a bounded number of batches in flight; use bounded queues when running concurrently.
- Never instantiate futures/tasks for the entire dataset at once.
- Inspect per-item errors in bulk responses; HTTP success does not mean every item succeeded.
- Retry selectively with backoff, jitter, and caps; never retry mapping errors infinitely.
- Use deterministic IDs/versions for safe retries and duplicate prevention.
- Persist checkpoints only after batches are processed or errors are durably saved.
- Avoid per-batch refreshes unless immediate visibility is needed; refresh once upon completion when appropriate.
- Benchmark batch size and concurrency on real workloads; no single value fits every cluster.
- Monitor heap, GC, direct buffers, queue depth, 429s, and p95/p99 latency.
- Use alias switches when importing into a new index and publishing verified data.

## 24. Key Takeaways

- The Bulk API sends multiple index/create/update/delete actions in a single NDJSON request.
- Bulk is not an all-or-nothing transaction; every item carries its own status.
- Spring Data Elasticsearch provides `bulkIndex`, `bulkUpdate`, and `bulkDelete` via `ElasticsearchOperations`.
- `IndexQueryBuilder` creates index operations from IDs and entity objects.
- Never load the whole source into the heap; read via streams/cursors/keysets and flush bounded batches.
- Batch sizing must consider both document count and bytes; large documents can make same-count batches consume vastly different memory.
- Calling `clear()` on batches drops references, yet does not replace bounding sources, responses, and concurrency.
- Bounded queues provide backpressure when Elasticsearch slows down.
- Check `errors` and every item; retry only transient failures rather than blindly resending whole batches.
- Deterministic IDs and idempotent operations make retries safe.
- Checkpoints must commit only after every item is handled or durably saved as retry/dead-letter.
- Avoid refreshing after every batch; select visibility policies based on read requirements.
- Monitor bulk imports via throughput, latency, 429s, heap, GC, and queue depth.

Efficient large-scale ingestion is an orchestration challenge spanning the source, batching, network, Elasticsearch, and application memory. Stream data cleanly, keep batches and concurrency within measured limits, handle per-item outcomes, and advance checkpoints only when data is safely accounted for. Structuring imports this way delivers solid throughput while keeping memory, errors, and resumability under control.

## References

- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch — BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/BulkOptions.html)
