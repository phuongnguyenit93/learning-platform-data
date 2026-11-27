# Choosing Batch Size, Timeouts, and Memory Footprint

When exporting or processing a large number of documents from Elasticsearch, an application should not load all results into a single list before starting to process them. Doing so can cause heap usage to grow rapidly, trigger prolonged garbage collection, or result in `OutOfMemoryError`. Instead, read data in batches, finish processing the current batch, and only then fetch the next one.

Three parameters must be designed together: **batch size**, **scroll context retention duration**, and **memory budget**. They are interrelated, though they do not mean the same thing:

- **Batch size** determines how many hits are fetched in each read operation.
- **Scroll keep-alive** determines how long Elasticsearch keeps the search context alive so the application can request the next batch.
- **Search timeout** caps how long Elasticsearch waits to execute a query.
- **Client timeout** caps how long the application waits for a response over the network.
- **Memory budget** determines how many documents and intermediate structures the application can hold simultaneously.

There is no single batch size or timeout suitable for every index. Document size, mapping, shard count, application processing speed, network latency, and cluster resources all influence the choice. This lesson uses an example of exporting `Product` documents from the **products** index, focusing on how to select well-founded values and keep memory consumption steady.

## 1. Why Read Data in Batches?

Suppose an index has 2 million products. If the application runs a query fetching every document and converts them into `List<Product>`, it must retain a massive number of Java objects on the heap. Beyond the JSON source, each entity carries object headers, references, `String` instances, collections, and metadata created by the converter.

Load-all model:

~~~text
Elasticsearch
     |
     v
Fetch all 2 million documents
     |
     v
Convert into 2 million Product instances
     |
     v
Hold entire List<Product> in heap
     |
     v
Process or write file
~~~

If memory is insufficient, the application may experience:

- Steadily rising heap usage.
- Frequent, long-running garbage collection pauses.
- Increasing response times.
- JVM `OutOfMemoryError`.
- Mid-run export job failure.

Batch reading bounds the number of documents held at any one time:

~~~text
Fetch batch 1 --> process batch 1 --> release references
     |
     v
Fetch batch 2 --> process batch 2 --> release references
     |
     v
Fetch batch 3 --> process batch 3 --> release references
     |
     v
                  ...
~~~

The application can process millions of documents without keeping all of them in memory. The prerequisite is that downstream processing must also be bounded: never push all documents into an unbounded `List`, queue, or cache.

## 2. What Is Batch Size?

**Batch size** is the number of hits the application requests in a single fetch. In the Search API, it is typically expressed via the **size** field in the request body. In Spring Data Elasticsearch, page size can be configured via **Pageable** when constructing a `Query`.

Example request fetching 500 documents:

~~~http
POST /products/_search
{
  "size": 500,
  "query": {
    "match_all": {}
  }
}
~~~

In a scroll workflow, each response returns one batch of hits. When the application requests the next batch, Elasticsearch uses the search context retained from the initial query.

Batch size is not the total number of documents to export. If the index has 2 million documents and `size` is 500, the application will read many consecutive batches to finish the job.

Distinguish between:

| Concept | Meaning |
|---|---|
| **Batch size / size** | Number of hits requested in a single response |
| **Total hits** | Total number of documents matching the query, if tracked |
| **Scroll keep-alive** | Duration the search context is retained between batch fetches |
| **Search timeout** | Time limit for executing the query on Elasticsearch |
| **Client timeout** | Time the client waits for a request/response |
| **Export duration** | Total time the application spends processing all batches |

Do not set `size` equal to total hits simply because you want to export everything. Choose `size` based on document size, memory, and processing speed.

## 3. How Does Batch Size Affect Performance?

Both small and large batch sizes come with trade-offs.

| Small batch size | Large batch size |
|---|---|
| Each response contains fewer documents | Each response contains more documents |
| Less data held on the heap at once | Heap must accommodate more entities |
| More round-trips to Elasticsearch | Fewer round-trips |
| Can increase network and request-handling overhead | Can improve throughput up to a point |
| Easier to handle when documents are large | Risks sharp GC or memory spikes |
| Suited when each document is heavy or processing is slow | Better suited when documents are small and the sink is fast |

For instance, a batch size of 50 may be safe for documents containing many nested objects or long text fields, though it generates more requests than a size of 500. Conversely, a size of 5,000 may reduce network calls but produce huge responses, consume heavy memory, and lengthen conversion times.

Increasing batch size does not guarantee linear speedups. Once network, CPU, disk, or destination write speed saturates, adding more documents per batch only increases memory usage and latency without meaningfully improving throughput.

## 4. How to Pick an Initial Batch Size

There is no universal standard number for all applications. You can start with a moderate value, measure, and tune.

A practical testing approach:

1. Start with 200 or 500 documents per batch.
2. Run against data matching production size and distribution closely.
3. Monitor heap, GC, per-batch duration, and throughput.
4. Increase to 1,000 if heap has plenty of headroom and per-request overhead is significant.
5. Lower to 100 or 50 if responses are large, entities are heavy, GC rises, or processing one batch takes too long.
6. Stop increasing once throughput stops improving noticeably or resources begin facing pressure.

Values like 50, 100, 200, 500, and 1,000 are merely convenient comparison benchmarks, not fixed Elasticsearch limits or prescriptions.

### Accounting for Document Size

Document count alone does not reflect response payload size. 500 documents with only a few keyword fields can be vastly smaller than 500 documents carrying long descriptions, nested objects, and large arrays.

When selecting `size`, measure:

- Average response size in bytes.
- Number of fields returned.
- Java object complexity after converter mapping.
- Number of collections or nested objects instantiated.
- Processing or write cost per document.

If documents have large sources, lower the batch size or use source filtering to fetch only the fields required for export. Source filtering reduces network transfer and conversion work, though it should only be applied if the excluded fields are unnecessary for business logic.

### Accounting for Destination Sink Speed

If the application reads much faster than it can write to a file, database, or target service, large batches can cause queued data to pile up in memory.

Example:

~~~text
Elasticsearch: 10,000 documents/sec
          |
          v
Application reads and converts quickly
          |
          v
Unbounded queue
          |
          v
Destination system: 1,000 documents/sec
~~~

The queue will grow endlessly because consumption trails production. Shrinking batch size only delays when memory fills up; it does not resolve the speed mismatch. Use bounded queues, backpressure, or pace reads to match destination write capacity.

## 5. Estimating Memory per Batch

Required memory is not merely the raw JSON size in the response. When Spring Data maps `_source` into Java objects, the heap also holds:

- `Product` entities and nested objects.
- `String` instances and char/byte arrays.
- `List`, `Map`, and other collections.
- `SearchHit` wrappers with metadata such as ID, score, and highlights.
- HTTP client and JSON parser buffers.
- The batch currently being processed by the application.
- Data serialized for writing to the target system.
- Queues or pending tasks.

You can use a simple estimation formula:

\[
M_{\text{batch}} \approx B \times H
\]

Where:

- \(B\) is the batch size.
- \(H\) is the average heap footprint of one document after conversion.

This estimates only the entity portion of a single batch. Actual peak memory also includes response buffers, the batch being written, queues, temporary objects, and concurrent processing threads.

For example, if one converted `Product` occupies an average of 8 KB on the heap and the batch size is 500:

\[
500 \times 8\text{ KB} \approx 4\text{ MB}
\]

This figure excludes auxiliary structures and temporary allocations. Do not treat JSON source size as exact heap footprint; Java objects carry overhead and different internal representations than JSON.

### When Processing Multiple Batches Concurrently

If the application allows 4 batches to be processed concurrently, memory held for active batches scales roughly with the number of in-flight batches:

\[
M_{\text{in-flight}} \approx C \times B \times H
\]

Where \(C\) is the number of batches or workers holding data at the same time. While still a rough estimate, this clarifies why raising concurrency also increases memory pressure.

Avoid increasing batch size and worker count simultaneously without measuring. Changing one variable at a time helps pinpoint the cause when heap usage or GC rises.

## 6. What Is Scroll Keep-Alive?

The Scroll API keeps a **search context** open so the application can keep fetching batches after the initial query. The **scroll** parameter specifies how long Elasticsearch preserves that context after each interaction.

Example:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

The first response contains a **_scroll_id**. The application uses this ID to request the next batch:

~~~http
POST /_search/scroll
{
  "scroll": "90s",
  "scroll_id": "ID_RETURNED_FROM_RESPONSE"
}
~~~

Each subsequent scroll call may return a new scroll ID. The application must use the latest ID received in the next request.

Upon completion, clear the scroll context:

~~~http
DELETE /_search/scroll
{
  "scroll_id": [
    "LATEST_SCROLL_ID"
  ]
}
~~~

### Keep-Alive Is Not Total Export Duration

Setting a keep-alive of 90 seconds does not mean the entire export must finish within 90 seconds. The context is extended each time the application sends the next scroll request with a fresh keep-alive duration.

For example:

- Batch 1 is returned.
- The application processes batch 1 in 40 seconds.
- The application requests batch 2 with a 90-second keep-alive.
- The context stays alive for the new interval.
- The cycle repeats until data is exhausted.

Keep-alive must be long enough to cover the time spent processing a batch and sending the next request, plus safety margin for network latency or transient load.

If each batch takes 2 minutes to process while keep-alive is only 30 seconds, the context may expire before the application requests the next batch.

You do not need to set keep-alive to the total runtime of a multi-hour export. Size it to the maximum expected interval between two consecutive scroll requests.

## 7. Search Timeout Differs from Scroll Keep-Alive

**Search timeout** and **scroll keep-alive** are two independent parameters.

- Search timeout limits how long Elasticsearch waits while executing a search request.
- Scroll keep-alive specifies how long the search context is kept between batch fetches.
- Client timeout is how long the application waits for a response over the connection.
- Batch processing time is how long application code spends consuming the data.

Example search request specifying both timeout and scroll:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "timeout": "20s",
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Here:

- **scroll=90s** asks to retain the search context for 90 seconds between scroll calls.
- **timeout=20s** bounds query execution wait time per Search API behavior.
- **size=500** requests 500 hits per batch.
- **sort: _doc** optimizes document traversal when relevance ordering is unnecessary.

If a search timeout occurs, the response may indicate the query timed out or that shards failed to finish, depending on partial results configuration and version. An export workflow must check response flags such as **timed_out** and shard metadata instead of assuming every response contains complete results.

### Client Timeout

The HTTP client or Elasticsearch Java API Client has its own timeout. If the client stops waiting after 10 seconds while the server is still processing the request, the application may receive a client-side timeout error even though the root cause differs from a Search API timeout.

Distinguish between:

| Parameter | Where configured | Effect |
|---|---|---|
| **scroll keep-alive** | Search/scroll request | Retains the search context between batches |
| **Search API timeout** | Search request body | Limits query execution wait time |
| **Client request/socket timeout** | HTTP transport/client configuration | Limits how long the client waits for a response |
| **Application deadline** | Application logic or job scheduler | Limits the total time a task is permitted to run |

Do not increase scroll keep-alive to fix a client timeout error. Nor should you increase client timeout to compensate for an expired scroll context. Before tuning, verify the exact timeout type in logs and exceptions.

## 8. Choosing Keep-Alive Based on Batch Processing Time

A practical way to choose is to measure the elapsed time from receiving a batch to sending the request for the next batch.

Example:

| Stage | Duration |
|---|---:|
| Receive response and convert | 2 seconds |
| Process 500 `Product` instances | 18 seconds |
| Write to destination | 25 seconds |
| Network latency and load jitter | 5 seconds |
| Total interval between two scroll calls | Around 50 seconds |

If the gap between requests is normally around 50 seconds, a 90-second keep-alive is a reasonable starting point to test. If the destination occasionally stalls for 2 minutes, adjust accordingly or shrink the batch to reduce per-batch retention time.

Do not pick an excessively long keep-alive without justification. Every scroll context holds resources on Elasticsearch, can keep old segments pinned, and slows resource reclamation after updates or merges. Many simultaneously open contexts add pressure to the cluster.

Equally, do not choose a keep-alive so short that contexts frequently expire while the application processes a batch.

## 9. Memory Consumption on the Elasticsearch Side

Scroll contexts consume resources on the cluster side, not solely inside the application JVM. Elasticsearch must retain search state to keep returning subsequent batches.

Impacts include:

- Search contexts remain open for the scroll duration.
- Segments required for the scroll's view of data may stay pinned.
- File descriptors and associated resources may remain unreleased.
- Many concurrent scroll contexts increase pressure on nodes.
- Long keep-alives keep resources allocated longer if the application stalls or fails to clear the context.

Therefore, close the scroll immediately upon completion or job failure. Do not leave scroll contexts lingering simply because the application forgot to call clear or left an iterator unclosed.

Elasticsearch enforces a cap on open scroll contexts, commonly controlled by the **search.max_open_scroll_context** setting. Defaults and configurability depend on version. Do not raise this limit merely to run more export jobs in parallel without evaluating heap, file descriptors, and cluster load.

You can monitor open search contexts via node stats, including search context metrics. Exact field names and API paths may vary by version, so observe open contexts, heap, GC, CPU, and node health throughout export runs.

## 10. Why Sort by `_doc` When Scrolling an Entire Index?

If the goal is solely to traverse all documents without needing relevance or business ordering, Elasticsearch recommends sorting by **_doc** in scroll for efficient scanning.

Example:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

**_doc** is an internal ordering suited for scanning data. It carries no business ordering semantics such as ascending price or newest creation date.

If the export requires a stable business-key order, explicitly define the sort fields and tie-breaker. Field sorting can make queries more expensive than `_doc` traversal depending on mappings and index structure.

For workflows simply transferring all documents to another system, relevance scoring is generally unneeded. Pairing `match_all` with `_doc` accurately expresses the pure scan intent.

## 11. Using SearchHitsIterator in Spring Data Elasticsearch

Spring Data Elasticsearch provides **SearchHitsIterator<T>** and **searchForStream(...)** to iterate over results as a stream. The iterator lets the application process each hit without holding all results in a `List`.

Example with Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

int batchSize = 500;

Query query = NativeQuery.builder()
        .withQuery(q -> q.matchAll(m -> m))
        .withPageable(PageRequest.of(0, batchSize))
        .build();

try (SearchHitsIterator<Product> hits = operations.searchForStream(
        query,
        Product.class,
        IndexCoordinates.of("products")
)) {
    while (hits.hasNext()) {
        SearchHit<Product> hit = hits.next();
        Product product = hit.getContent();

        exportProduct(product);
    }
}
~~~

In this example:

- **PageRequest.of(0, batchSize)** sets the page size used as the read batch size.
- **searchForStream(...)** returns an iterator to read hits sequentially.
- **hasNext()** checks whether more hits remain.
- **next()** fetches the next hit.
- **getContent()** retrieves the `Product` entity.
- **try-with-resources** ensures the iterator is closed upon completion or exception.

APIs and scroll keep-alive configuration can vary by Spring Data Elasticsearch version. Some versions offer overloads accepting **SearchScrollSpec** or dedicated scroll settings to specify context retention time. Check the signatures of your active version; do not assume batch size and keep-alive are the same setting.

### Do Not Convert the Iterator to a List If You Want to Save Memory

The following defeats streaming:

~~~java
List<Product> allProducts = new ArrayList<>();

try (SearchHitsIterator<Product> hits = operations.searchForStream(
        query,
        Product.class,
        IndexCoordinates.of("products")
)) {
    while (hits.hasNext()) {
        allProducts.add(hits.next().getContent());
    }
}
~~~

Although the iterator reads batch by batch, the code retains every entity in **allProducts**. For large indices, heap still grows with the total number of documents.

Process each entity as it is read or hold only the small batch required by the destination system.

## 12. Separating Read Batch Size and Write Batch Size

In an export or data transfer pipeline, the batch size read from Elasticsearch and the batch size written to the target system do not have to match.

For example:

- Read 500 `Product` documents from Elasticsearch.
- Transform each `Product`.
- Accumulate 100 transformed records.
- Write 100 records to the destination system.
- Repeat until all 500 `Product` items are handled.

The two parameters mean different things:

| Parameter | Controls |
|---|---|
| **readBatchSize** | Number of documents fetched from Elasticsearch per read |
| **writeBatchSize** | Number of records buffered before writing to the destination |
| **maxInFlightBatches** | Number of batches permitted to be processed concurrently |
| **queueCapacity** | Maximum number of waiting items or batches |

If the destination system's bulk API performs best at 100 records, you do not have to shrink the read batch size down to 100. The application can read 500 and flush 5 writes, provided memory and concurrency are bounded.

Example grouping writes:

~~~java
int readBatchSize = 500;
int writeBatchSize = 100;

List<ExportRecord> writeBatch = new ArrayList<>(writeBatchSize);

try (SearchHitsIterator<Product> hits = operations.searchForStream(
        query,
        Product.class,
        IndexCoordinates.of("products")
)) {
    while (hits.hasNext()) {
        Product product = hits.next().getContent();

        writeBatch.add(toExportRecord(product));

        if (writeBatch.size() == writeBatchSize) {
            destination.writeBatch(writeBatch);
            writeBatch.clear();
        }
    }

    if (!writeBatch.isEmpty()) {
        destination.writeBatch(writeBatch);
    }
}
~~~

In this example, the read batch size is configured via `Pageable` when building the query; the write batch size governs the application-side collection. The code holds at most one write group beyond the internal batch managed by the iterator.

If the destination writes slowly, the `writeBatch` call naturally pauses the reader. This provides built-in backpressure and prevents unbounded memory accumulation.

## 13. Using the Scroll API Directly When Keep-Alive Control Is Needed

In Spring Data Elasticsearch versions exposing an explicit scroll API, you can start, continue, and clear scroll contexts through corresponding methods on **ElasticsearchOperations**. Exact signatures depend on version, so inspect the API available in your project.

At the Elasticsearch REST API level, the scroll lifecycle has three stages:

~~~text
1. Initial search with scroll parameter
          |
          v
2. Receive _scroll_id and first batch
          |
          v
3. Call _search/scroll with latest ID
          |
          v
4. Loop until batch is empty
          |
          v
5. Call clear scroll to release context
~~~

Example initial request:

~~~http
POST /products/_search?scroll=2m
{
  "size": 500,
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Continuation request:

~~~http
POST /_search/scroll
{
  "scroll": "2m",
  "scroll_id": "LATEST_SCROLL_ID"
}
~~~

Clearing the context:

~~~http
DELETE /_search/scroll
{
  "scroll_id": [
    "LATEST_SCROLL_ID"
  ]
}
~~~

Always use the latest scroll ID returned in each response. Never assume the initial ID remains valid for the entire lifecycle.

When using the scroll API directly, ensure the context is cleared inside a `finally` block or equivalent cleanup hook. When using `SearchHitsIterator`, close the iterator with `try-with-resources` so the library performs cleanup.

## 14. Scroll Contexts and Data Changes During Export

Scroll maintains a view of data from the time of the initial search. Consequently, changes occurring after the scroll starts do not necessarily appear in the active scroll session.

For example:

1. An export begins at 10:00.
2. The search context is created.
3. A new product is written at 10:05.
4. Scroll continues fetching remaining batches.

Documents added after the start time may not appear in the current scroll session. Likewise, documents updated or deleted mid-export will not cause scroll results to reflect the newest state automatically.

This is useful when you want to export a consistent view as of start time, though important to remember if continuous synchronization is the goal.

If near-real-time export is needed, design a separate change-sync mechanism, such as:

- Recording a timestamp or watermark for the export run.
- Using `updatedAt` or sequence/version fields per the data model.
- Running an incremental sync pass for changes after the watermark.
- Using change data capture or an event log if supported by the source system.
- Saving checkpoints to resume safely after failures.

Do not assume scroll automatically picks up new documents written while the export is in flight.

## 15. When to Use scroll, search_after, and Point in Time?

Scroll is not the only option for deep data reads.

| Mechanism | Suitable scenario | Characteristics |
|---|---|---|
| **from/size** | Standard pagination at shallow depths | Easy to use, but unsuitable for large deep pagination |
| **scroll** | Batch exports or large sequential processing | Retains a search context; must be cleared upon completion |
| **search_after** | Deep traversal by sort values | Does not materialize prior pages; requires a stable sort |
| **Point in Time (PIT) + search_after** | Deep pagination needing a consistent data view | PIT preserves index view; `search_after` continues from cursor |

For user interfaces paging through many results, **PIT + search_after** is usually a better fit than scroll. Scroll fits sequential reading and bulk batch-processing jobs.

Do not use scroll as the pagination mechanism backing a "Next Page" button in a user interface. A long-lived scroll context ties up cluster resources and fits poorly with user behavior that may pause or abandon mid-flow.

## 16. Timeouts in Spring Data Elasticsearch

When using Spring Data Elasticsearch, identify which API controls each type of timeout.

**Scroll keep-alive:** Some stream/scroll APIs accept a scroll spec or context retention duration. Class names and overloads vary by version. When using them, size the duration to the maximum interval between two batch fetches, not total export runtime.

**Search timeout:** If the initial query can be slow, configure a search-request timeout via the `Query` abstraction or `NativeQuery` where supported by your version. Search timeout does not replace keep-alive.

**Client timeout:** Settings on the Elasticsearch Java API Client or HTTP transport govern how long the client waits for a request. It should be long enough for an expected batch response without letting requests hang indefinitely.

**Application timeout:** Job schedulers, workers, or external HTTP requests may enforce their own deadlines. For background exports, choose execution limits matching the job type and status-tracking mechanism.

When a timeout occurs, record:

- Which type of timeout occurred.
- Which batch was being processed.
- Query latency and application processing latency.
- Whether the scroll context is still valid or expired.
- Whether the response reported `timed_out` or shard failures.
- Whether the client disconnected before the server replied.

Do not blindly retry the entire export without knowing which batches have already been written to the destination. Design checkpoints or idempotent writes to avoid duplicating data.

## 17. Controlling Memory with Backpressure

Backpressure aligns reading speed with the downstream system's processing capacity. If the destination is slow, the application must not keep fetching batches faster than it can write.

An unbounded pipeline:

~~~text
Elasticsearch --> Reader --> Unbounded Queue --> Slow Writer
                                  |
                                  v
                          Memory grows forever
~~~

A bounded pipeline:

~~~text
Elasticsearch --> Reader --> Bounded Queue --> Writer
                      ^                         |
                      |                         |
                      +---- Wait when full -----+
~~~

You can implement this by:

- Processing sequentially within a single loop.
- Using a fixed-capacity bounded queue.
- Capping the number of concurrently running tasks.
- Fetching a new batch only after the previous batch finishes writing or a slot frees up.
- Using a reactive pipeline with backpressure if the entire chain properly supports reactive backpressure.

Avoid feeding millions of documents into an `Executor` backed by an unbounded queue. When the writer slows down, tasks and objects accumulate on the heap.

When processing in parallel, define clear batch ownership and write ordering rules. Also account for open scroll contexts if each worker holds its own scroll session. More workers do not always raise throughput; they can overload Elasticsearch or the destination system.

## 18. Reducing Returned Data with Source Filtering

If the export needs only a few fields, instruct Elasticsearch to return only those fields. This shrinks network payloads and reduces conversion work.

Example exporting only SKU, name, and price:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "_source": [
    "sku",
    "name",
    "price"
  ],
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

In Spring Data Elasticsearch, the `Query` abstraction or `NativeQuery` may support source filtering depending on version. When mapping results to DTOs, ensure the target type expects only the fields actually returned.

Do not apply source filtering and map into a full entity if application code would misinterpret omitted fields as genuine `null` values. Use a projection or dedicated DTO to model the exported subset explicitly.

## 19. Estimating and Monitoring JVM Memory

During export runs, monitor:

- Heap used and heap committed.
- Garbage collection frequency and pause durations.
- Old generation occupancy.
- Allocation rate during entity conversion.
- Active batch size.
- Queue depth.
- Concurrent workers and in-flight batches.
- Destination write latency.
- Retry counts and failed batches.

If heap usage climbs steadily over time and fails to drop after GC, the application may be retaining references to old data. Common causes:

- An aggregate `List` holding every `Product`.
- Unbounded caches.
- Unbounded queues.
- Logs or metrics retaining oversized `_source` strings.
- Callbacks or lambdas holding references to objects longer than needed.
- Batches submitted to an executor faster than they are consumed.

Release unneeded references after processing each batch. Never invoke **System.gc()** after every batch; it does not fix reference retention and can degrade performance.

On the Elasticsearch side, monitor node heap, search contexts, CPU, disk I/O, search thread pools, and rejected requests. Oversized batches inflate response sizes and processing time on both client and server.

## 20. Tracking Progress and Checkpoints for Long Exports

A long-running export may be interrupted by application restarts, network errors, or timeouts. Restarting from scratch every time can waste substantial time and resources.

Record progress in a recoverable unit:

- ID of the last successfully written document.
- Sync timestamp or watermark.
- Count of documents read and written.
- Current batch or partition.
- Job status and most recent error.

A Scroll ID is Elasticsearch-side search context state; do not treat it as a durable checkpoint saved across restarts. If the application must resume after a process crash, redesign around **search_after** with a stable sort key and cursor checkpoint, or rerun from a watermark with idempotent writes.

When writing to the destination system, use stable IDs or idempotency keys so retries do not create duplicate records. If a batch fails mid-write, know how to identify succeeded records and replay safely.

## 21. Example Export Service with Bounded Batch Sizes

The following example uses `SearchHitsIterator` to read sequentially and write groups of 100 records to `destination`. Read batch size is configured separately via `Pageable`.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductExportService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private static final int READ_BATCH_SIZE = 500;
    private static final int WRITE_BATCH_SIZE = 100;

    private final ElasticsearchOperations operations;
    private final ProductDestination destination;

    public ProductExportService(
            ElasticsearchOperations operations,
            ProductDestination destination) {
        this.operations = operations;
        this.destination = destination;
    }

    public void exportAll() {
        Query query = NativeQuery.builder()
                .withQuery(q -> q.matchAll(m -> m))
                .withPageable(PageRequest.of(0, READ_BATCH_SIZE))
                .build();

        List<ExportRecord> writeBatch =
                new ArrayList<>(WRITE_BATCH_SIZE);

        try (SearchHitsIterator<Product> hits =
                     operations.searchForStream(
                             query,
                             Product.class,
                             PRODUCTS
                     )) {

            while (hits.hasNext()) {
                SearchHit<Product> hit = hits.next();
                writeBatch.add(toExportRecord(hit.getContent()));

                if (writeBatch.size() == WRITE_BATCH_SIZE) {
                    destination.writeBatch(writeBatch);
                    writeBatch.clear();
                }
            }

            if (!writeBatch.isEmpty()) {
                destination.writeBatch(writeBatch);
            }
        }
    }

    private ExportRecord toExportRecord(Product product) {
        return new ExportRecord(
                product.getId(),
                product.getSku(),
                product.getName(),
                product.getPrice()
        );
    }
}
~~~

**ProductDestination** and **ExportRecord** are illustrative application classes, not built-in Spring Data APIs.

Key takeaways from the example:

- `READ_BATCH_SIZE` controls how many hits are fetched per read batch.
- `WRITE_BATCH_SIZE` controls how many records are buffered before writing.
- The iterator closes automatically when the loop finishes or throws an exception.
- Only one small write batch is held in application code.
- Products are never accumulated into an all-encompassing `List`.

In production, configure scroll keep-alive to match your Spring Data Elasticsearch version and destination write speed. If the `searchForStream` overload accepts `SearchScrollSpec`, set keep-alive explicitly based on measured batch processing times.

## 22. Signs That Batch Size or Timeouts Are Mismatched

| Symptom | Possible cause | Adjustment |
|---|---|---|
| Heap spikes sharply after each response | Batch too large or heavy entities | Lower batch size, apply source filtering |
| Prolonged GC pauses | Too many objects allocated or held concurrently | Reduce batch/concurrency, remove unbounded queues |
| Many tiny requests and low throughput | Batch too small | Increase size incrementally and re-measure |
| Scroll context expires | Keep-alive shorter than interval between scroll calls | Raise keep-alive or reduce batch processing time |
| Search requests frequently time out | Initial query or shards too slow | Optimize query, inspect load and timeouts |
| Client times out while server keeps working | Client timeout lower than response latency | Check transport timeout and actual latency |
| Open scroll contexts climb continuously | Iterator unclosed or job fails to clear context | Use `try-with-resources`/`finally` and verify cleanup |
| Slow destination, growing queue | Reader outpaces writer | Apply backpressure and bounded queues |
| Export runs slowly with steady heap | Throughput or I/O bottleneck | Measure fetch, conversion, and write times separately |
| Export misses documents after timeout | Partial response or job resumed with wrong cursor | Check `timed_out`/shards and checkpointing |

## 23. Tuning Workflow for Batch Size, Timeouts, and Memory

A practical tuning process follows these steps:

1. **Measure document size.** Sample representative documents and measure source bytes plus post-conversion heap footprint.
2. **Pick an initial batch.** Try 200 or 500 documents depending on entity size.
3. **Time each stage per batch.** Separate search, network, conversion, and destination write durations.
4. **Set keep-alive.** Pick a value larger than the expected gap between scroll requests, with safety headroom.
5. **Set Search API timeout.** Give queries enough time to finish while still catching stalled shards.
6. **Set client timeout.** Long enough for a single batch response and aligned with transport settings.
7. **Bound memory.** Never retain all results; bound write batches, queues, and concurrency.
8. **Measure throughput.** Track documents per second and per-batch latency.
9. **Step batch size up or down.** Adjust incrementally; stop once throughput plateaus or heap/GC rises.
10. **Verify cleanup.** Close iterators or clear scroll contexts on both success and failure.
11. **Verify completeness.** Confirm responses did not time out, no shards failed, and written record counts match expectations.
12. **Design resumption.** Use checkpoints and idempotent writes for long-running jobs.

Test in an environment whose data volume, shard count, and load approximate production. Measurements on a tiny index of a few thousand documents rarely predict behavior when exporting millions of documents.

## 24. Operational Principles to Remember

- Choose batch size based on document size, heap footprint, and destination speed.
- Start moderately, measure, then adjust; do not apply one fixed number to all indices.
- Distinguish batch size from total hits.
- Distinguish scroll keep-alive, Search API timeout, client timeout, and application deadline.
- Keep-alive must cover the interval between two batch fetches, not total export duration.
- Use `SearchHitsIterator` or the appropriate scroll API and always close resources.
- Never convert the iterator into a `List` containing the entire dataset.
- Decouple read batch size and write batch size when the destination has different optimal limits.
- Bound queues and concurrent batches to prevent heap buildup.
- Use source filtering when only a subset of fields is needed.
- Use `_doc` sort when scanning all data without business ordering requirements.
- Check timeouts, shard failures, and actual record counts to prevent incomplete exports.
- Use checkpoints and idempotent writes when jobs must resume after errors.
- Monitor both JVM resources and Elasticsearch search contexts and cluster load.

Selecting batch size, timeouts, and memory limits is a balancing act among throughput, latency, and resource usage. Larger batches reduce round-trips at the cost of larger per-response memory; longer keep-alives give the application time to process batches while pinning search contexts longer; search and client timeouts govern separate phases. By reading via streams, bounding processing, closing scroll contexts reliably, and measuring against real data, a Spring Data Elasticsearch application can export large datasets stably without keeping everything on the heap.
