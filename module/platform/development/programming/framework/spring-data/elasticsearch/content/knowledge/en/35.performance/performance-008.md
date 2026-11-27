# Optimizing Bulk Size, Concurrency, and Refresh Interval

When writing large volumes of documents into Elasticsearch, performance depends heavily on how requests are batched, how many requests run concurrently, and when documents are refreshed to become search-visible. Sending documents one by one creates excessive HTTP round trips; packing too many documents into a single bulk request increases memory, latency, and shard pressure. Raising concurrency too high can saturate the write thread pool and trigger `429 TOO_MANY_REQUESTS` errors. Refreshing too frequently also increases segment creation and merge costs.

Three tuning knobs must be considered together:

- **Bulk size:** the amount of data in a single bulk request, typically measured in bytes and document count.
- **Concurrency:** the number of bulk requests processed simultaneously.
- **Refresh interval:** the interval at which Elasticsearch performs a refresh so new documents become searchable.

There is no single optimal set of values for every cluster. An effective approach is to start with small batches, increase one variable at a time, measure throughput and latency, and stop when performance stops improving or resources begin saturating.

## 1. What problem does the Bulk API solve?

If an application sends 10,000 documents as 10,000 individual index requests, each document requires a separate request, HTTP handling, and coordination inside Elasticsearch. That overhead can exceed the actual write work.

The Bulk API lets you send multiple operations in a single request. Elasticsearch routes each action to its target shard and processes them within one HTTP exchange.

Example Bulk API request:

~~~http
POST /products/_bulk
Content-Type: application/x-ndjson

{"index":{"_id":"P-100"}}
{"name":"Keyboard","category":"ACCESSORIES","price":49.99}
{"index":{"_id":"P-101"}}
{"name":"Mouse","category":"ACCESSORIES","price":19.99}
{"delete":{"_id":"P-102"}}
~~~

The bulk body uses NDJSON (newline-delimited JSON):

- The first line is action metadata, such as `index`, `create`, `update`, or `delete`.
- For `index`, `create`, and `update`, the next line typically holds the document or update payload.
- For `delete`, the action metadata line alone is sufficient, with no trailing source line.
- Every line must end with a newline; requests normally end with a trailing newline.

The Bulk API reduces HTTP round trips, but does not turn the entire request into a transaction. One item can succeed while another fails.

### 1.1. Commonly used actions

| Action | Meaning | When to use |
| --- | --- | --- |
| `index` | Creates a document or replaces an existing one with the same ID. | Syncing the entire document source. |
| `create` | Creates only if the ID does not already exist. | Ensuring existing documents are not overwritten. |
| `update` | Partial update or runs a script on an existing document. | Modifying only part of the source. |
| `delete` | Deletes a document by ID. | Deleting a known list of IDs. |

If the whole document needs updating, `index` is usually simpler. If only a few fields change, `update` avoids resending the entire source, though it carries its own update handling cost. Measure against your actual workload.

## 2. Bulk size: measured in bytes and document count

Bulk size is the volume of data sent in a single request. Two complementary metrics describe it:

- Number of documents/actions in the batch.
- Serialized body size in bytes.

Capping only document count can produce oversized batches when documents have heavy sources. Conversely, capping only bytes can yield batches with very few documents when each document is large.

For example, 500 small documents might produce a 1 MB body, whereas 500 documents with nested arrays or long text could exceed tens of megabytes.

### 2.1. Starting point for benchmarking

You can start with a bulk body around 5 MB and adjust based on actual data. This is a starting point for experimentation, not a mandatory value.

A simple testing workflow:

1. Start with 1 MB or 5 MB.
2. Run enough batches to measure steady-state throughput.
3. Roughly double the body size.
4. Compare documents/second, MB/second, latency, and errors.
5. Stop when throughput plateaus or p95 latency, heap, GC, or rejected requests rise noticeably.

Never send requests exceeding the cluster's HTTP body limit. The default `http.max_content_length` is typically 100 MB; keep bulk requests well below this limit and leave headroom for metadata, serialization, and document size variance.

### 2.2. Document count does not replace byte limits

Suppose each document averages 10 KB after serialization:

| Document count | Approximate source size |
| ---: | ---: |
| 100 | 1 MB |
| 500 | 5 MB |
| 1,000 | 10 MB |
| 5,000 | 50 MB |

These are rough estimates. The bulk body also includes action metadata and newlines, and individual document sizes can skew far from the average.

For documents with uneven sizes, track actual serialized bytes of the NDJSON body. If batches are assembled in the application, pre-serialize or track byte counts to flush when reaching the threshold.

### 2.3. Why are overly small bulks inefficient?

Too-small bulks increase:

- Number of HTTP requests sent.
- TLS/HTTP and serialization overhead.
- Number of coordinator receptions and distributions.
- Client-side request management cost.
- Ratio of overhead to useful payload.

If each request sends only 1–5 small documents, the application may be missing the benefits of the Bulk API.

### 2.4. Why are overly large bulks harmful too?

Too-large bulks can:

- Increase memory held for request bodies on both client and receiving node.
- Increase per-request processing time and batch latency.
- Create heap and network buffer pressure.
- Increase the number of items to inspect or retry on failure.
- Risk exceeding `http.max_content_length`.
- Cause a hot shard if most documents in the batch route to the same shard.

Larger bulk requests do not guarantee higher throughput. Once shards or disks saturate, larger bodies simply increase wait times and in-flight data volume.

## 3. Batching by bytes, count, and time

A solid batcher usually enforces at least two thresholds:

- **Max operations:** maximum number of actions.
- **Max bytes:** maximum bulk body byte size.

A time threshold can also be added so low-volume data still flushes instead of waiting indefinitely to fill a batch.

Example policy:

~~~text
flush when:
  operations >= 500
  OR body_bytes >= 5 MB
  OR batch wait time >= 200 ms
~~~

These numbers are only starting values for benchmarking. Tune them based on document size, throughput, latency targets, and cluster capacity.

### 3.1. Do not let batches wait indefinitely

If you flush only upon reaching 1,000 documents, low-write tenants might wait a long time before their data is sent. Add a timer or flush interval on the producer side so smaller batches still ship after a bounded delay.

The application batcher timeout differs from Elasticsearch's `index.refresh_interval`:

- Batch timeout controls when the client sends the bulk request.
- Refresh interval controls when indexed documents become search-visible.

Both delays add to end-to-end data visibility latency.

### 3.2. Splitting batches within practical bounds

Java example splitting a list into count-based chunks:

~~~java
static <T> List<List<T>> chunks(List<T> items, int batchSize) {
    List<List<T>> result = new ArrayList<>();

    for (int start = 0; start < items.size(); start += batchSize) {
        int end = Math.min(start + batchSize, items.size());
        result.add(items.subList(start, end));
    }

    return result;
}
~~~

This is straightforward when document sizes are relatively uniform. When document sizes vary widely, batch based on serialized bytes rather than element count alone.

Avoid materializing copies of every batch if the input list is already huge. Process via an iterator or stream to keep memory steady.

## 4. Bulk operations in Spring Data Elasticsearch

Spring Data Elasticsearch exposes bulk operations on `ElasticsearchOperations` and `ElasticsearchTemplate`. Entities can be wrapped in `IndexQuery` objects and sent together in one bulk request.

Example entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    // getters and setters
}
~~~

Building `IndexQuery` instances:

~~~java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> queries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();
~~~

Sending the bulk request:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

List<IndexedObjectInformation> results =
        operations.bulkIndex(
                queries,
                IndexCoordinates.of("products")
        );
~~~

`bulkIndex` sends multiple index actions in a single bulk request. The result type exposes information about the indexed documents according to your version's API.

### 4.1. Bulk update

For partial updates, create an `UpdateQuery` per document:

~~~java
UpdateQuery update = UpdateQuery.builder("P-100")
        .withDocument(Document.create().append("price", 45.99))
        .build();
~~~

Then send the list:

~~~java
operations.bulkUpdate(
        updateQueries,
        IndexCoordinates.of("products")
);
~~~

`bulkUpdate` fits scenarios where many documents modify only a few fields. Check partial update, script, and per-item version conflict semantics.

### 4.2. Bulk delete

You can batch IDs to delete:

~~~java
operations.bulkDelete(
        ids,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Verify that the ID list is authorized and scoped to the permitted tenant/index. Bulk delete does not automatically enforce business filters if the application only supplies IDs.

### 4.3. BulkOptions and refresh policy

Spring Data bulk overloads accept `BulkOptions` in supported versions. You can configure refresh policy, timeouts, and other bulk options via the builder.

Illustrative configuration:

~~~java
BulkOptions bulkOptions = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

operations.bulkIndex(
        queries,
        bulkOptions,
        IndexCoordinates.of("products")
);
~~~

Package names and builder methods on `BulkOptions` must match your project's Spring Data Elasticsearch version. If no custom options are needed, the default overload is usually sufficient; avoid setting the refresh policy to `IMMEDIATE` on every batch just to make data searchable right away.

### 4.4. Choosing Operations or Java API Client?

Prefer `ElasticsearchOperations.bulkIndex`, `bulkUpdate`, or `bulkDelete` when you need Spring Data entity mapping and existing abstractions.

Use the Elasticsearch Java API Client directly when you need Bulk API options or response metadata not exposed by your Spring Data version's abstraction. Reuse the Spring-managed client bean; never create a new client per batch.

## 5. Concurrency: number of concurrent bulk requests

Bulk size determines the size of one request. Concurrency determines how many requests execute in parallel.

Example:

~~~text
Producer
   |
   +--> Bulk 1 ----+
   +--> Bulk 2 ----+----> Elasticsearch
   +--> Bulk 3 ----+
   +--> Bulk 4 ----+
~~~

Increasing concurrency can better utilize network, CPU, and shards when a single request does not saturate cluster capacity. However, too many concurrent requests increase queued data, heap, disk, and write thread-pool pressure.

### 5.1. Start with low concurrency

A cautious benchmarking approach:

- Start with 1 concurrent bulk request.
- Increase to 2, 4, then 8 as long as throughput rises and latency stays stable.
- Monitor write rejections, bulk latency, CPU, heap, disk I/O, and network.
- Stop increasing when throughput plateaus or errors/latency climb.

This is not a fixed formula. Small clusters saturate at low concurrency; larger clusters can handle more requests. Document size, shard count, and routing all play a role.

### 5.2. Avoid unbounded concurrency

Do not use `parallelStream()` or spawn an unbounded Future per batch across millions of documents. That can keep excessive requests and payloads in memory.

Bound:

- Number of active batches.
- Total in-flight bytes.
- Number of items in the producer queue.
- Wait time when the queue is full.
- Number of concurrent retries.

Bounded concurrency provides backpressure: when Elasticsearch slows down, the producer slows or waits instead of accumulating payloads endlessly.

### 5.3. Concurrency must align with shard distribution

A bulk request can contain documents targeting multiple shards. Elasticsearch distributes each action to its destination shard. If all documents share the same routing key, many requests can pile onto a single shard and create a hotspot.

Observe:

- Primary shard count.
- Document distribution across shards.
- Whether routing keys are skewed.
- Write queue and rejected counts.
- Disk utilization and merge pressure.
- Whether any node receives most of the bulk traffic.

Raising concurrent requests will not fix a shard hotspot caused by routing skew. In that case, revisit routing strategy, index layout, or workload distribution.

## 6. Handling 429 errors and backpressure

When Elasticsearch cannot accept additional work, bulk items or requests may be rejected with HTTP `429 TOO_MANY_REQUESTS` or corresponding errors in the response.

This is a signal to slow down writes or retry after giving the system time to recover.

### 6.1. Bulk responses can partially succeed

A Bulk API response looks like:

~~~json
{
  "took": 42,
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "P-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_id": "P-101",
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

The overall HTTP request can return while individual items still fail. The application must inspect `errors` and each entry inside `items`.

Never assume HTTP 200 means every document was written successfully.

### 6.2. Retry only failed items

An appropriate workflow:

1. Send the bulk request.
2. Iterate through each item response.
3. Record successful items.
4. Enqueue only retryable failed items for retry.
5. For 429s, wait with backoff before resending.
6. For mapping or validation errors, route to dead-letter/error handling instead of retrying forever.

If you resend the entire bulk, previously succeeded items will be re-executed. For `index` with deterministic IDs, replacing the source can be idempotent in some use cases; for `create`, auto-generated IDs, or incrementing update scripts, resending can cause duplicates or apply changes twice.

### 6.3. Exponential backoff and jitter

Do not retry immediately in a tight loop. Use increasing backoff intervals:

~~~text
attempt 1: wait 200 ms
attempt 2: wait 400 ms
attempt 3: wait 800 ms
attempt 4: wait 1.6 s
...
~~~

Add random jitter so multiple producers do not retry in lockstep at the exact same instant. Cap maximum retry attempts and total retry duration.

These numbers are illustrative. Policies must align with latency targets and cluster recovery characteristics.

### 6.4. Classify errors before retrying

| Error type | How to handle |
| --- | --- |
| 429 / rejected execution | Backoff, lower concurrency or batch pressure, then retry failed items. |
| 502/503/504 or transient network errors | Bounded retry if confident the request will not cause non-idempotent side effects. |
| Mapping exception | Fix schema/document; do not retry unchanged. |
| Parsing/validation error | Send to error queue or dead-letter for handling. |
| 401/403 | Fix credentials/privileges; retrying will not help. |
| Version conflict | Re-read and apply concurrency rules; do not blind-retry. |
| Document missing on update | Check upsert logic or event ordering. |

### 6.5. Idempotency and write ordering

Safe retries depend on action type:

- `index` with deterministic ID and identical source can usually be retried without creating duplicate documents.
- `create` with fixed ID will conflict if the previous attempt succeeded before the response was lost.
- `update` scripts like `stock += 1` are non-idempotent; resending can double-increment.
- `delete` by ID usually converges to the same final state, though responses differ.
- State-dependent updates need OCC or sequence/event IDs to prevent duplicate processing.

If multiple producers update the same document, define business ordering and use optimistic concurrency or appropriate idempotency mechanisms. The Bulk API does not create transactions across requests.

## 7. Bulk size and concurrency interact

Do not tune one variable in isolation while ignoring total in-flight data volume.

Example:

| Bulk body | Concurrent requests | Approximate max in-flight data |
| ---: | ---: | ---: |
| 2 MB | 2 | 4 MB |
| 5 MB | 4 | 20 MB |
| 10 MB | 8 | 80 MB |
| 20 MB | 16 | 320 MB |

This simple multiplication estimates wire payload only, excluding Java objects, buffers, responses, and HTTP/client overhead. Actual heap usage can be several times the body size.

A 20 MB batch may work fine when running a single request, yet become heavy with 16 requests in flight. Therefore, concurrency limits must be tuned alongside bulk size.

### 7.1. A tuning example

Suppose initial settings:

- Bulk body around 5 MB.
- At most 4 concurrent requests.
- Refresh interval of 1 second.
- 429 retries with backoff.

If throughput rises when moving concurrency from 2 to 4 but stalls at 8, stay at 4. If increasing bulk size from 5 MB to 10 MB sharply raises latency for minimal throughput gain, revert to 5 MB.

Do not pick settings based solely on how fast a single batch runs. Measure long enough to include refreshes, merges, and concurrent search workloads.

## 8. Refresh interval and near-real-time search

Elasticsearch is near-real-time. A successfully indexed document is not necessarily immediately visible in search.

A refresh opens a new searcher so newly indexed changes become visible to search. This is distinct from writing documents to the translog and distinct from a flush.

The `index.refresh_interval` setting controls how often the index refreshes automatically.

Example:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "5s"
  }
}
~~~

With a 5-second refresh interval, new changes normally become searchable after the next refresh, plus request processing and scheduling time.

For self-managed indexes, the default refresh interval is typically 1 second. Some managed or serverless environments may use different values; check the actual setting instead of assuming defaults.

### 8.1. What does refresh cost?

Refreshes create new searchers/segments so search can see recent data. Overly frequent refreshes can:

- Create many small segments.
- Increase merge overhead.
- Increase CPU and I/O.
- Reduce indexing throughput.
- Increase resource pressure during mixed ingest and search.

If the workload is primarily bulk ingestion and immediate search visibility is not required, lengthening the refresh interval can improve write performance.

### 8.2. Longer refresh intervals

Example increasing from 1 second to 30 seconds:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "30s"
  }
}
~~~

This reduces automatic refresh frequency. In return, new documents may wait longer before appearing in search.

A range of 5–30 seconds can serve as a testing band for ingest-heavy workloads, measured against search visibility SLAs and cluster behavior. No single value fits every index.

### 8.3. Temporarily disabling refresh during initial bulk loads

When loading large datasets into a new index that does not need to serve searches during loading, you can temporarily disable automatic refreshes:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

After bulk loading completes:

1. Send any remaining bulk requests and resolve all errors.
2. Restore the desired refresh interval.
3. Trigger a single refresh if data must become visible immediately.
4. Verify search and document counts.
5. Open read traffic or switch aliases once the index is ready.

Restoring the setting:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

Do not forget to restore `refresh_interval` after initial loading. Leaving it at `-1` can prevent new documents from appearing in search automatically until a manual refresh or configuration change occurs.

Disabling refresh suits bulk loads during maintenance windows or indexes not yet serving queries. Do not use it on live indexes requiring near-real-time search.

## 9. Request-level refresh policy

The Bulk API accepts a `refresh` query parameter with these primary options:

| Value | Behavior | Impact |
| --- | --- | --- |
| `false` | Does not trigger a dedicated refresh for the request. | Better throughput; search visibility waits for automatic refresh. |
| `wait_for` | Waits for the next refresh to make changes visible. | Can increase request latency without forcing an immediate refresh. |
| `true` | Forces an immediate refresh after the operation. | High overhead; avoid on every bulk batch in large pipelines. |

Example:

~~~http
POST /products/_bulk?refresh=wait_for
Content-Type: application/x-ndjson

{"index":{"_id":"P-100"}}
{"name":"Keyboard","price":49.99}
~~~

`refresh=wait_for` is helpful when an operation must ensure documents are searchable right after the request finishes, such as a user creating a record and immediately navigating to a search view.

Do not attach `refresh=true` to every bulk request. Forcing a refresh on every batch can make Elasticsearch generate many tiny segments and drop throughput sharply.

A practical strategy:

- Routine bulk ingestion: request no explicit refresh.
- Flows needing read-after-write: use `wait_for` on specific requests where needed.
- Initial loads: lengthen or disable refresh interval, then refresh once upon completion.
- Never use `true` as the default for batch pipelines.

### 9.1. Refresh vs. flush

| Operation | Purpose |
| --- | --- |
| Refresh | Makes indexed changes visible to search. |
| Flush | Performs a Lucene commit and processes the translog per Elasticsearch's mechanism. |
| Force merge | Consolidates segments; a resource-intensive administrative task. |

Do not call `_flush` after every bulk just to make data visible to search. Search visibility is governed by refresh. Nor should you run force merge continuously during ingestion, as it competes with indexing for CPU and I/O.

## 10. Coordinating bulk and refresh in Spring Data

Spring Data can submit bulks with `BulkOptions` and configure a request-level refresh policy. Keep in mind that `refresh_interval` is an index setting, whereas refresh policy applies to a specific request.

Distinction:

- `index.refresh_interval`: automatic refresh schedule for the index.
- `BulkOptions` refresh policy: refresh behavior applied to a bulk request.
- `IndexOperations.refresh()`: requests an index refresh at the moment it is called.

Example avoiding forced refreshes:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products")
);
~~~

When search visibility is required after a bulk request:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products")
);
~~~

Enum names, packages, and builder methods can vary across Spring Data Elasticsearch versions. Check your project's API dependency. The key point is avoiding `IMMEDIATE`/`true` on every batch when throughput is the primary goal.

You can explicitly refresh after a bulk run:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
~~~

`refresh()` is synchronous in the imperative API. For reactive applications, use `ReactiveIndexOperations.refresh()` and compose the publisher into the pipeline instead of blocking.

## 11. Bulk pipelines in imperative applications

A bulk-writing service usually has three parts:

1. Convert entities into `IndexQuery` objects.
2. Split lists into batches.
3. Send batches with bounded concurrency and handle results.

Sequential example, suitable as a baseline:

~~~java
@Service
public class ProductBulkWriter {

    private static final IndexCoordinates INDEX =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductBulkWriter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void write(List<Product> products, int batchSize) {
        for (List<Product> batch : chunks(products, batchSize)) {
            List<IndexQuery> queries = batch.stream()
                    .map(product -> new IndexQueryBuilder()
                            .withId(product.getId())
                            .withObject(product)
                            .build())
                    .toList();

            operations.bulkIndex(queries, INDEX);
        }
    }
}
~~~

This baseline runs one bulk request at a time. Starting here lets you measure baseline throughput and determine bulk size before adding concurrency.

### 11.1. Adding bounded concurrency

If benchmarks show the cluster still has headroom, you can run multiple batches using a bounded executor or a fixed worker pool.

Principles:

- Do not submit millions of batches into an unbounded queue.
- Limit worker count.
- Cap total queued and in-flight bytes.
- Inspect batch results to catch errors.
- Pause producers when the queue reaches its limit.
- Provide a shutdown mechanism that awaits in-flight batches.

Do not use `parallelStream()` for load throttling. It offers no byte bounds, per-item retry policies, or backpressure suited for bulk workloads.

### 11.2. Writing the same document ID from multiple batches

If two batches write to the same `_id`, completion order may differ from the order producers built the batches. Older data can overwrite newer data.

Ways to handle this:

- Partition queues by document ID so the same ID always goes to the same worker.
- Use versioning or OCC when updates are snapshot-based.
- Ensure events carry business sequence/version numbers and discard stale events.
- Use clearly defined idempotent operations.

Increasing concurrency without defining write ordering can leave final data stale even when every request succeeds.

## 12. Reactive bulk pipelines and backpressure

In WebFlux applications, keep publishers end-to-end. Never call imperative `ElasticsearchOperations.bulkIndex` directly on an event-loop thread.

`ReactiveElasticsearchOperations` provides publisher-based bulk APIs in supported versions. Inputs can be grouped using Reactor's `bufferTimeout` to batch by count and time:

~~~java
Flux<IndexQuery> queries = products
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build());

return queries
        .bufferTimeout(500, Duration.ofMillis(200))
        .flatMap(batch ->
                reactiveOperations.bulkIndex(
                        Flux.fromIterable(batch),
                        IndexCoordinates.of("products")
                ),
                4
        )
        .then();
~~~

This example illustrates batching with at most 4 concurrent bulk operations. Exact `bulkIndex` return types, `Publisher` overloads, and generic result types must match your Spring Data Elasticsearch version.

`flatMap(..., 4)` bounds active inner publishers to 4. If batch processing order must be preserved, use `concatMap`; if parallelism is needed while emitting results in source order, consider `flatMapSequential`.

### 12.1. Backpressure and buffering

`bufferTimeout(500, Duration.ofMillis(200))` flushes upon 500 items or 200 ms. It bounds item count only, not bytes. When document sizes vary widely, use custom byte-based batching or cap payload size before buffering.

Do not use unbounded `onBackpressureBuffer()` for ingestion. If Elasticsearch is slower than the producer, the buffer grows indefinitely and can exhaust heap. Bound buffers, throttle producers, or stage into a durable queue.

### 12.2. Bounding reactive concurrency

`flatMap(..., 4)` does not mean the cluster receives at most 4 requests system-wide. It only limits subscriptions within that pipeline. With multiple application instances or multiple pipelines, total cluster concurrency equals the sum across all callers.

Account for all producers/instances and apply rate limits or concurrency budgets system-wide.

## 13. Mappings and data also affect bulk throughput

Bulk size and concurrency are not the only factors.

Mapping aspects that affect write performance:

- Text analyzers add tokenization CPU cost.
- `doc_values` and inverted indexes must be built for indexed fields.
- High-cardinality fields can increase index structure costs.
- Nested objects can create multiple Lucene documents for one source document.
- Overly permissive dynamic mappings can bloat mappings.
- Ingest pipelines/script processors add per-document CPU overhead.
- Unneeded fields left indexed still add indexing work.

Declare mappings aligned with the use case. If a field only needs to be stored and never searched, consider `index: false` or an appropriate type. Do not disable indexing wholesale if business logic filters or sorts on those fields.

### 13.1. Replicas during initial loads

Replica shards must also be updated when indexing documents. For initial loads into a new index, some teams temporarily set `number_of_replicas` to 0 and restore it afterward to reduce write amplification.

This operational choice carries risk:

- While replicas are 0, the index has no redundant copies for primaries.
- Node failures can cause service interruption or loss of written data depending on state and setup.
- Once replicas are restored, the cluster needs time to copy shards and incurs extra I/O.

Use this only during controlled load windows when data can be re-ingested from a source of truth and availability risk is acceptable. Never adjust replica counts on live production indexes without a plan.

## 14. Refresh, replicas, and search workloads

When an index handles both reads and writes, longer refresh intervals improve write throughput at the cost of delayed visibility. When search latency and freshness matter, measure both targets simultaneously:

- Write throughput: documents/second and MB/second.
- Search visibility delay: time from bulk success until documents appear in search.

Increasing the refresh interval often raises write throughput while lowering freshness. This is a business trade-off, not purely technical tuning.

When search load is heavy alongside ingestion:

- Monitor search latency and indexing latency separately.
- Avoid overly frequent refreshes.
- Consider splitting indexes or workloads by time.
- Keep page sizes and aggregation sizes reasonable.
- Do not force refreshes just to test a request if it does not reflect the real workload.

## 15. Measuring performance and choosing settings

Use identical datasets, mappings, and cluster states when comparing configurations.

Metrics to collect:

| Metric | Meaning |
| --- | --- |
| Documents/second | Throughput by document count. |
| MB/second | Throughput by actual bytes. |
| Bulk latency p50/p95/p99 | Time to process a batch. |
| 429/rejected count | Cluster overload or saturated write queues. |
| Client queue depth | How many batches the producer is accumulating. |
| In-flight bytes | Volume of payload currently sent/awaiting response. |
| CPU/heap/GC | Processing and memory pressure. |
| Disk I/O and merge time | Segment write and merge cost. |
| Refresh time/count | Refresh cost and frequency. |
| Search latency/freshness | Impact of ingestion on readers. |

### 15.1. Benchmarking one variable at a time

Example test matrix:

| Run | Target bulk body | Concurrency | Refresh interval |
| --- | ---: | ---: | --- |
| A | 1 MB | 1 | 1s |
| B | 5 MB | 1 | 1s |
| C | 5 MB | 2 | 1s |
| D | 5 MB | 4 | 1s |
| E | 10 MB | 4 | 1s |
| F | 10 MB | 4 | 5s |
| G | 10 MB | 4 | 30s |

This is an example matrix, not a universal recommended configuration. Each run should vary one primary parameter to isolate its effect.

Do not benchmark with only a few hundred tiny documents. Use data with production-like sizes and mappings, comparable shard counts, and concurrent search traffic if production has it.

### 15.2. Criteria to stop increasing load

Stop increasing bulk size or concurrency when:

- Throughput stops growing meaningfully.
- p95/p99 latency breaches SLA.
- 429/rejected requests begin rising.
- Heap or GC pressure rises continuously.
- Disk I/O or merge backlog becomes a bottleneck.
- Search latency/freshness fails requirements.
- Producer queues grow endlessly without draining.

Optimization does not mean pushing the cluster to 100% resource utilization. Leave headroom for bursts, recovery, merges, and read workloads.

## 16. Observability APIs and tools

Use Elasticsearch APIs to inspect cluster and indexing health:

- Nodes stats: CPU, heap, thread pools, filesystem, indexing/search stats.
- Cluster stats: cluster-wide node, index, shard, and resource overview.
- Index stats: indexing, refresh, merge, segments, and store.
- Thread pool stats: active, queue, and rejected counts for the write thread pool.
- CAT indices/shards: shard sizes and distribution for quick diagnostics.

Example checking thread pools:

~~~http
GET /_nodes/stats/thread_pool
~~~

Example checking index stats:

~~~http
GET /products/_stats/indexing,refresh,merge,segments,store
~~~

Example checking shards:

~~~http
GET /_cat/shards/products?v
~~~

Thread pool names and stat fields vary across versions. Focus on rejected counts, queue growth, refresh/merge activity, and shard imbalance.

On the application side, record metrics per bulk:

- Action count.
- Request bytes.
- Send and receive durations.
- Successful/failed item counts by error type.
- Retry counts and backoff delays.
- Current concurrency.
- Queue depth.
- Tenant or workload class if breakdowns are needed.

Do not log full document sources on every bulk error. Log ID, index, status, and error type in accordance with data protection policies.

## 17. Anti-patterns to avoid

| Anti-pattern | Consequence | Remedy |
| --- | --- | --- |
| Sending documents one by one | Excessive HTTP overhead. | Batch into bulk requests. |
| Bounding bulks only by document count | Batches can get huge for heavy sources. | Bound both count and bytes. |
| Oversized bulk requests | Higher heap, latency, and retry costs. | Scale up via benchmarks and stay below body limits. |
| Sending too many concurrent requests | 429s, queues, and heap pressure. | Bounded concurrency and backpressure. |
| Retrying immediately on 429 | Worsens cluster overload. | Exponential backoff, jitter, and throttling. |
| Retrying the entire bulk | Replays already-succeeded items. | Retry only retryable failed items. |
| Ignoring bulk item responses | Misses failures even when the request returns. | Check `errors` and individual items. |
| Using `refresh=true` on every batch | Many tiny segments, slow indexing. | Rely on automatic refresh or `wait_for` when needed. |
| Disabling refresh and forgetting to re-enable | Documents never become periodically searchable. | Save previous setting and restore after initial load. |
| Raising concurrency without checking routing | A single shard can become a hotspot. | Inspect shard distribution and routing skew. |
| Unbounded `parallelStream()` | Hard to control in-flight payload and retries. | Bounded worker pool or Reactor concurrency. |
| Unbounded reactive buffers | Fast producers exhaust heap. | Bounded buffers and backpressure. |
| Unordered bulk updates to the same ID | Older writes can finish after newer ones. | Partition by ID or use OCC/versioning. |
| Dropping replicas carelessly in production | Loses redundancy during loading. | Perform only inside controlled windows. |
| Force merging during ingestion | Competes for CPU and disk I/O. | Let merges run naturally; force merge only in dedicated workflows. |

## 18. Tuning workflow for a Spring Data application

A practical workflow in order:

1. Define goals: throughput, freshness, or both; document SLAs.
2. Measure average and p95 document sizes after serialization.
3. Batch by count, bytes, and timeout.
4. Start with 1–5 MB bulk bodies and 1 concurrent request.
5. Inspect partial failures and implement item-level retries for transient errors.
6. Increase bulk size until throughput stops improving.
7. Hold that bulk size and step up concurrency gradually.
8. Monitor 429s, write queues, heap, CPU, disk, and merges.
9. Tune `refresh_interval` based on search visibility requirements.
10. For initial loads, consider a long refresh interval or `-1`, then restore afterward.
11. Inspect mappings, routing, and shard distribution if throughput stalls.
12. Test with concurrent search workloads running.
13. Run benchmarks long enough to observe steady-state merges and refreshes.
14. Save settings per workload/index and keep monitoring as data grows.

Do not copy bulk/concurrency settings from another environment without measuring. The same batch size that works well on a multi-node cluster can overload a smaller cluster or unbalanced shards.

## 19. References

- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch — Refresh API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)
- [Elasticsearch — Index settings: refresh interval](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules.html)
- [Elasticsearch — Thread pool settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html)
- [Elasticsearch — Nodes stats API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-nodes-stats.html)
- [Spring Data Elasticsearch — Bulk operations and templates](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Reactive operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

Bulk size determines how much data travels in one request; concurrency determines how many requests run at once; refresh interval determines search visibility delay. Measure bulks by both bytes and document count, bound total in-flight payload, retry recoverable items individually with backoff, and check partial failures. For write-heavy workloads, raising the refresh interval or temporarily disabling refreshes can boost throughput, provided settings are restored and the visibility delay is acceptable.
