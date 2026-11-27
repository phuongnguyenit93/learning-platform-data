# Scroll API and Batch Data Scanning Use Cases

Elasticsearch's Scroll API allows reading a large result set page by page without resending the query from scratch for each page. After the initial search, Elasticsearch creates a scroll context and returns a `scroll_id`. The application uses this ID to fetch subsequent batches until no hits remain, then releases the context.

Scroll is well suited for data-scanning tasks such as exporting millions of documents, backfilling indices, synchronizing data, running offline reports, or batch processing. It is not a good choice for deep interactive pagination in a user interface; for that case, consider `search_after` combined with Point in Time (PIT). When using scroll, control batch size, context retention time, application memory, per-batch errors, and proper scroll closure.

## 1. Why Do We Need the Scroll API?

Elasticsearch limits the number of documents you can retrieve using `from` and `size` in a single search request. Standard pagination works well for the first few pages:

```http
GET /events/_search
{
  "from": 0,
  "size": 20,
  "query": { "match_all": {} }
}
```

To fetch the next page, the application increments `from`. However, the larger `from` becomes, the more results Elasticsearch must hold and discard before the target position. This mechanism is resource-intensive for deep queries and is capped by `index.max_result_window` (typically defaulting to 10,000 for `from + size`).

When processing hundreds of thousands or millions of documents, continuously incrementing `from` is unsuitable. Scroll solves the scanning problem by keeping a search context open and resuming reads from the position saved in that context.

### Suitable Use Cases

- Exporting large datasets to CSV/JSON files or another storage system.
- Backfilling data from an old index to a new index.
- Periodically synchronizing a set of documents to an external system.
- Offline computations that need to read every document matching a condition.
- Running batch maintenance tasks, such as auditing and updating documents.
- Reading data to feed into a batch processing pipeline.

### Unsuitable Use Cases

- User pagination through pages 1, 2, 3, 4 in a UI.
- Autocomplete or low-latency search requests.
- Short HTTP requests needing immediate results for users.
- Workloads that only need the first few dozen or few hundred results.
- Tasks requiring stable resumption after many hours or days without a dedicated checkpoint.

## 2. How Does a Scroll Context Work?

When an application sends a search request with the `scroll` parameter, Elasticsearch opens a scroll context for that search. The context retains the read state on a snapshot of the search data as of start time. The initial response contains the first batch and a `scroll_id`.

Subsequent requests do not resend the original query. Instead, they send `scroll_id` to request the next batch. Elasticsearch resumes from the position saved in the context and returns the ID to use for the following call.

```text
Application
   |
   | 1. POST /events/_search?scroll=1m
   |    size = 500
   v
Elasticsearch
   |
   | 2. Batch 1 + scroll_id
   v
Application processes batch 1
   |
   | 3. POST /_search/scroll
   |    latest scroll_id
   v
Elasticsearch
   |
   | 4. Batch 2 + new scroll_id
   v
Application processes batch 2
   |
   |             ...
   v
No more hits
   |
   | 5. DELETE /_search/scroll
   v
Release scroll context
```

The scroll context preserves a consistent view of the index based on the search view at start time. Documents indexed after that point do not automatically appear in the running scroll. Later modifications also do not shift the scroll's snapshot to a newer state mid-scan.

A Scroll ID is an opaque string issued by Elasticsearch. Do not parse its structure, fabricate it, or reuse an old ID once a new response returns a different ID. Always use the latest `scroll_id` received from the most recent response.

## 3. What Does `keep_alive` Mean?

The `scroll`/`keep_alive` parameter specifies how long Elasticsearch retains the scroll context when the application has not yet sent the next scroll request.

Example:

```http
POST /events/_search?scroll=2m
```

`2m` means the context is kept for up to roughly two minutes since the most recent access if no subsequent request arrives. Every call to the Scroll API can extend the context retention time with a new `scroll` value.

This does not mean the entire job must finish within two minutes. A task can run for hours if it keeps fetching the next batch before the context expires and extends `keep_alive`. However, do not set `keep_alive` overly long just to mask a stalled consumer; a long-lived context holds resources on the cluster.

### Choosing keep_alive

- Set it long enough for the application to process a batch and send the next request.
- If each batch takes 20 seconds to process, a `keep_alive` of only a few tens of seconds may be too tight; leave headroom for GC, network latency, and cluster load.
- Do not set it to several hours if batches normally finish in a few seconds.
- If a consumer can pause or stall for a long time, design checkpoint/restart handling instead of relying on an ever-living scroll context.

## 4. Calling the Scroll API via REST

### Step 1: Start the Scroll

The first request specifies the index, context retention duration, and batch size:

```http
POST /events/_search?scroll=1m
Content-Type: application/json

{
  "size": 500,
  "sort": ["_doc"],
  "track_total_hits": false,
  "query": {
    "range": {
      "@timestamp": {
        "gte": "2026-01-01T00:00:00Z",
        "lt": "2026-02-01T00:00:00Z"
      }
    }
  }
}
```

In this example:

- `size: 500` requests up to 500 documents per batch.
- `sort: ["_doc"]` uses an efficient internal order when only scanning data without business ordering.
- `track_total_hits: false` avoids computing the exact total hit count if the task does not need that number.
- `range` narrows the documents to scan by time range.

Abbreviated response:

```json
{
  "_scroll_id": "DXF1ZXJ5...opaque-scroll-id...",
  "timed_out": false,
  "_shards": {
    "total": 5,
    "successful": 5,
    "failed": 0
  },
  "hits": {
    "hits": [
      { "_id": "e-1", "_source": { "eventType": "login" } },
      { "_id": "e-2", "_source": { "eventType": "purchase" } }
    ]
  }
}
```

An actual response will contain more hits than the example. Save `_scroll_id` and process the hits in the current batch.

### Step 2: Fetch the Next Batch

Send the latest ID to the `_search/scroll` endpoint:

```http
POST /_search/scroll
Content-Type: application/json

{
  "scroll": "1m",
  "scroll_id": "DXF1ZXJ5...opaque-scroll-id..."
}
```

The response returns the next batch and may include a new `_scroll_id`. Replace your stored ID with this new ID.

### Step 3: Loop Until Data Is Exhausted

When `hits.hits` is empty, there are no more batches in that scroll run. Do not rely on the hit count of a previous batch to conclude you are done; the termination condition is when the current scroll response contains no hits.

### Step 4: Close the Scroll Context

When finished or when the task fails, release the context:

```http
DELETE /_search/scroll
Content-Type: application/json

{
  "scroll_id": [
    "DXF1ZXJ5...latest-scroll-id..."
  ]
}
```

You can delete multiple scroll IDs in the same request. If passing a single ID, the API also supports string form per server-accepted syntax. For tasks with multiple contexts, track and delete the exact IDs opened by the application.

## 5. Pseudocode for a Scroll Loop

Basic flow:

```text
scrollId = null

try:
    page = startScroll(query, batchSize, keepAlive)
    scrollId = page.scrollId

    while page.hits is not empty:
        process(page.hits)

        page = continueScroll(scrollId, keepAlive)
        scrollId = page.scrollId
finally:
    if scrollId is not null:
        clearScroll(scrollId)
```

The crucial point is that `clearScroll` must be called inside `finally`. If you only close on normal loop exit, an exception while processing a batch can leave the context alive until `keep_alive` expires.

## 6. Using the Scroll API via Spring Data Elasticsearch

Spring Data Elasticsearch provides a high-level API for streaming search results. `ElasticsearchOperations.searchForStream(...)` returns a `SearchHitsIterator<T>`, allowing the application to read hit by hit without manually managing `scroll_id` on every loop iteration.

Example:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.stereotype.Service;

@Service
public class EventExportService {

    private final ElasticsearchOperations operations;

    public EventExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportEvents() {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.range(r -> r
                .field("@timestamp")
                .gte(co.elastic.clients.json.JsonData.of("2026-01-01T00:00:00Z"))
                .lt(co.elastic.clients.json.JsonData.of("2026-02-01T00:00:00Z"))
            ))
            .withPageable(PageRequest.of(0, 500))
            .build();

        try (SearchHitsIterator<EventDocument> hits =
                operations.searchForStream(
                    query,
                    EventDocument.class,
                    IndexCoordinates.of("events"))) {

            while (hits.hasNext()) {
                SearchHit<EventDocument> hit = hits.next();
                EventDocument event = hit.getContent();
                writeToExport(event);
            }
        }
    }

    private void writeToExport(EventDocument event) {
        // Write the event to a file or destination system.
    }
}
```

`searchForStream` is a convenient option for traversing large result sets. The iterator must be closed; `try-with-resources` guarantees `close()` is invoked even if the loop throws an exception. Under the hood, the implementation uses Spring Data's scroll mechanism in versions supporting this API.

`PageRequest.of(0, 500)` sets the initial page/batch size. An appropriate size depends on `_source` size, processing speed, and cluster capacity. Scroll duration configuration and API signatures may vary across Spring Data Elasticsearch versions; verify against the Javadoc of your active dependency.

### Why Keep `SearchHit<T>`?

`SearchHitsIterator<T>` iterates over `SearchHit<T>`, not just raw entities. This lets you read `_id`, score, index, and hit metadata when needed. If you only need the document, call `hit.getContent()`; if you need the ID or metadata, retain `SearchHit` during processing.

## 7. Managing Scroll Manually via `ElasticsearchOperations`

When you need per-batch control or direct access to the scroll ID, some Spring Data Elasticsearch versions provide operations such as:

- `searchScrollStart(...)`: starts the scroll and receives the first batch.
- `searchScrollContinue(...)`: uses the scroll ID to fetch the next batch.
- `searchScrollClear(...)`: releases the scroll context.

Example using a Spring Data API that provides these scroll methods:

```java
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchScrollHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public void scanInBatches(
        ElasticsearchOperations operations,
        Query query) {

    long keepAliveMillis = 60_000L;
    IndexCoordinates index = IndexCoordinates.of("events");
    query.setPageable(PageRequest.of(0, 500));

    String scrollId = null;
    try {
        SearchScrollHits<EventDocument> page =
            operations.searchScrollStart(
                keepAliveMillis,
                query,
                EventDocument.class,
                index
            );

        scrollId = page.getScrollId();

        while (!page.getSearchHits().isEmpty()) {
            for (SearchHit<EventDocument> hit : page.getSearchHits()) {
                process(hit.getContent());
            }

            page = operations.searchScrollContinue(
                scrollId,
                keepAliveMillis,
                EventDocument.class,
                index
            );

            scrollId = page.getScrollId();
        }
    } finally {
        if (scrollId != null) {
            operations.searchScrollClear(scrollId);
        }
    }
}
```

This pattern applies to versions offering `SearchScrollHits` and `searchScrollStart`, `searchScrollContinue`, `searchScrollClear`. Overload signatures may vary across Spring Data versions; if your project lacks these methods, use `searchForStream` or the corresponding Elasticsearch Java API Client. In production implementations, if a response returns a new scroll ID, always update the `scrollId` variable before continuing or cleaning up.

## 8. Choosing Batch Size

Batch size is the number of hits Elasticsearch attempts to return in each scroll page. It is not the total document count of the entire job.

| Batch size | Pros | Cons |
|---:|---|---|
| Small, e.g., 100 | Small payloads, easy to bound application memory | More round trips, higher network overhead |
| Medium, e.g., 500–1,000 | Balances payload size and request count across many workloads | Still needs measurement based on document size |
| Large, e.g., 5,000+ | Fewer requests when documents are small and the cluster is healthy | Large responses, higher heap, GC, and network pressure |

There is no universally optimal batch size for all indices. A batch of 1,000 documents may be tiny if each document is a few hundred bytes, yet huge if `_source` contains long text blobs or many nested objects.

### Practical Selection Approach

1. Start with a moderate batch, such as 500 or 1,000 documents.
2. Measure response size, batch fetch time, and batch processing time.
3. Monitor heap, GC, network throughput, and search thread pools.
4. Increase the batch if round trips are the bottleneck and memory headroom remains.
5. Decrease the batch if responses are large, GC spikes, or the consumer falls behind.

### Batch Size Is Not Equal to Write Batch Size

Scroll controls how much data is read from Elasticsearch. If the application writes data to another index using the Bulk API, the write batch can differ in size from the read batch. Reading 1,000 documents does not require writing all 1,000 documents in a single bulk request.

## 9. Choosing keep_alive and Avoiding Context Expiration

`keep_alive` must be long enough to process the current batch and send the next request. If a batch takes several minutes because it calls external services, the scroll context may expire before the application continues.

Options when processing is slow:

- Reduce synchronous work performed inside each hit's processing loop.
- Push data into a fast internal queue and process downstream with dedicated workers, if architecture permits.
- Increase `keep_alive` in a controlled manner while monitoring open context counts.
- Reduce batch size so no single batch takes too long to process.
- Use durable checkpoints and restart the scan if the context expires.

Avoid raising `keep_alive` indefinitely to preserve a scroll context while a consumer might stall for hours. A Scroll ID is not a durable checkpoint for a multi-day job.

## 10. Using `_doc` Sort When Scanning Data

If the goal is to read all documents without needing a business ordering, sorting by `_doc` is usually the most efficient choice for the Scroll API:

```json
{
  "size": 500,
  "sort": ["_doc"],
  "query": {
    "match_all": {}
  }
}
```

`_doc` lets Elasticsearch return documents in an internal order convenient for scanning. Do not use this order for displaying results to end users because it carries no stable business meaning.

If a specific order is required, declare a sort on the appropriate fields. Across multiple shards, consider tie-breaker values and sort semantics to avoid nondeterministic ordering among documents with equal values. Scroll continues from the created context, though field sorting can consume more resources than `_doc`.

## 11. Reducing Payload with Source Filtering

When exporting or batch processing, the application does not always need the entire `_source`. You can request only the required fields:

```http
POST /events/_search?scroll=1m
{
  "size": 500,
  "sort": ["_doc"],
  "_source": ["@timestamp", "eventType", "userId"],
  "query": {
    "match_all": {}
  }
}
```

Source filtering shrinks network payloads and reduces the data to deserialize. However, an entity class mapped by Spring Data may have missing fields if the query fetches only part of `_source`. For read-only projections or DTOs, use a target type that accurately reflects the retrieved fields.

You can omit `_source` altogether if only doc values or metadata are needed in certain queries, but in that case design field retrieval appropriately and do not expect a complete entity to be populated.

## 12. Scanning with Filters and Time Ranges

Avoid scanning an entire index by default if only a subset is needed. Narrowing the query upfront reduces the number of documents transferred over the network and processed.

Example scanning only events for a month:

```json
{
  "size": 500,
  "sort": ["_doc"],
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "@timestamp": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2026-02-01T00:00:00Z"
            }
          }
        },
        {
          "term": {
            "eventType": "purchase"
          }
        }
      ]
    }
  }
}
```

Use `filter` for filtering conditions that do not need relevance scoring. Batch scans rarely need scoring; `match_all`, `term`, `range`, and `bool` filters are common choices.

If data is partitioned into time-based indices, query only the relevant indices instead of wildcarding the entire history. You can use aliases or an explicit index list determined by the job.

## 13. Processing Each Batch Safely

A scroll loop only handles reading data. The application still must process batches with an appropriate error strategy.

A simple pipeline:

```text
Fetch batch
   |
   v
Validate each document
   |
   v
Process / transform
   |
   v
Write result or send to queue
   |
   v
Record metrics / checkpoint
   |
   v
Fetch next batch
```

### Do Not Hold All Results in RAM

If the goal is exporting millions of documents, write each batch to the output or stream it downstream. Never collect all documents into a large `List` before writing the file, as memory usage scales linearly with the total document count.

### Per-Document Error Handling

A single invalid document should not necessarily abort an entire job. Depending on requirements, you can:

- Write the error to a dead-letter file/queue and continue with the next document.
- Stop the batch if the error compromises overall data correctness.
- Retry transient errors with backoff.
- Never retry mapping, validation, or malformed-data errors indefinitely.

### Error Handling When Writing via the Bulk API

If each read batch is written to another Elasticsearch index, the Bulk API may succeed for some items and fail for others. A successful HTTP response does not guarantee every item succeeded. Inspect per-item errors and retry selectively.

## 14. Idempotency and Checkpoints for Scan Jobs

A scroll context is transient state on Elasticsearch. If the process crashes, the network drops, or `keep_alive` expires, the scroll ID may become invalid. Therefore, never treat a scroll ID as a long-lived checkpoint.

To make a job safe to rerun:

- Use stable source IDs when writing to the target system.
- Design writes to be idempotent or upsertable.
- Record durable business checkpoints if resumption is needed.
- Optionally partition work by time range, tenant, or stable key ranges.
- When restarting a partition from scratch, ensure reprocessing neither creates duplicates nor corrupts state.

For jobs checkpointing by timestamp, use half-open intervals `[from, to)` and save the processed watermark. However, a lone timestamp can collide across multiple documents; add a tie-breaker such as ID or use `search_after` with a stable sort for exact checkpointing.

Scroll fits finite-duration scan passes. If you need to pause and resume across hours or days with durable positioning, `PIT + search_after` or custom partition/checkpoint design is usually a better fit.

## 15. Snapshots and Data Changes During a Scroll

Scroll maintains a search context based on the index state at start time. This lets subsequent batches read from the same view rather than each request seeing a newer set of documents.

Consequences:

- New documents indexed after the scroll starts do not appear in that scan.
- Changes after start time do not advance the scroll's snapshot mid-run.
- Scroll is not a business transaction and does not lock system writes.
- A job that scans and mutates the same index must recognize that reads still reflect the initial snapshot.

If processing must capture changes occurring during the scan, add a delta-capture mechanism such as a change log, outbox, CDC, or an incremental scan after backfill. Do not assume scroll automatically catches up with new writes.

## 16. Releasing the Scroll Context

Every scroll context consumes resources on nodes holding shard contexts. Release it immediately upon completion.

Guidelines:

- Always use `try/finally` or `try-with-resources` with closeable iterators.
- Use the latest scroll ID from the most recent response.
- Clean up even when batch processing throws an exception.
- Do not open more concurrent scroll contexts than the cluster can sustain.
- Do not keep a scroll context open while waiting on user input or interaction.

You can inspect open context counts via Node Stats:

```http
GET /_nodes/stats/indices/search
```

In the response, monitor `indices.search.open_contexts` across nodes. If open contexts climb continuously, the application may be failing to close scrolls or launching too many concurrent scans.

### Scroll Contexts and Segments

A scroll context can keep old segments referenced for its snapshot, preventing merges from reclaiming those segments immediately. This increases temporary disk usage and resource overhead if contexts remain open for long durations. Consequently, context lifetimes and open context counts must be controlled.

## 17. Handling Timeouts, Shard Failures, and Expired Scroll IDs

A search response may report `timed_out: true` or `_shards.failed` greater than 0. A batch application must decide whether partial results are acceptable or the job must fail.

Common scenarios:

| Error | Possible cause | Resolution |
|---|---|---|
| Scroll ID no longer valid | Context exceeded `keep_alive` or was cleared | Start a new scan from a durable checkpoint |
| Request timeout | Busy cluster, oversized batch, or slow network | Reduce batch size, inspect cluster load, and adjust timeouts carefully |
| Shard failure | Shard unavailable or query error | Inspect `_shards.failures`, logs, and cluster state |
| Consumer processing too slowly | Large batch or slow downstream | Shrink batch, reduce synchronous work, or use queues/backpressure |
| Too many open contexts | Unclosed scrolls or excessive concurrent jobs | Clean up contexts and limit concurrency |
| Job dies mid-batch | Process terminated or unhandled error | Retry idempotently and restart from checkpoint |

Do not ignore `timed_out` or shard failures when the task requires complete data. For exports, billing, or auditing, define clear success criteria and track processed document counts.

## 18. Scroll vs. `search_after` + Point in Time (PIT)

Both Scroll and `search_after` help traverse large result sets, but they serve different kinds of workloads.

| Criterion | Scroll | `search_after` + PIT |
|---|---|---|
| Primary goal | Batch data scanning, export, batch processing | Deep pagination and ordered result traversal |
| Continuation mechanism | Server-managed Scroll ID | Sort values of the last hit |
| Snapshot | Scroll context preserves initial search view | PIT preserves snapshot; each request uses `search_after` |
| Sorting | `_doc` is usually efficient when only scanning | Requires a stable sort and uses sort values as cursor |
| State management | Server-side context, must be cleared | Server-side PIT and client-held cursor |
| UI pagination fit | No | Better suited |
| Long-term resumption | Ephemeral Scroll ID, not a durable checkpoint | Cursor/PIT also expire; needs application checkpoints for long-term resume |

Elasticsearch recommends PIT combined with `search_after` instead of scroll for many deep-pagination scenarios. Scroll remains useful for scans/batches when the application wants to pull the entire result set sequentially without building a business sort.

### Example: Opening a PIT

```http
POST /events/_pit?keep_alive=1m
```

The response returns a PIT ID.

### Searching the First Page with PIT

```http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "PIT_ID_FROM_OPEN_RESPONSE",
    "keep_alive": "1m"
  },
  "sort": [
    { "@timestamp": "asc" },
    { "_shard_doc": "asc" }
  ],
  "query": {
    "match_all": {}
  }
}
```

### Searching the Next Page

Take the `sort` array of the last hit from the previous page and pass it in `search_after`:

```json
{
  "size": 500,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "@timestamp": "asc" },
    { "_shard_doc": "asc" }
  ],
  "search_after": [
    "2026-01-01T12:30:00Z",
    4294967298
  ],
  "query": {
    "match_all": {}
  }
}
```

The PIT ID may be refreshed in the response; use the latest ID. When finished, close the PIT:

```http
DELETE /_pit
Content-Type: application/json

{
  "id": "LATEST_PIT_ID"
}
```

`search_after` requires a stable sort. PIT often adds `_shard_doc` as a tie-breaker to determine ordering among documents with duplicate sort values.

## 19. Scroll Is Not the Bulk API

Scroll is a read mechanism. The Bulk API is a write mechanism for executing multiple actions in one request. The two APIs are frequently paired in migration jobs, but they serve distinct roles.

```text
Scroll API
   |
   v
Read 500 documents
   |
   v
Transform data
   |
   v
Bulk API
   |
   v
Write multiple documents to target index
```

For example, a custom reindex job can read batches from a source index via scroll, transform each document, and write batches to the target index via the Bulk API. Inspect every item in the bulk response and selectively retry transient errors.

If you only need to copy data between Elasticsearch indices without complex transformations, the `_reindex` API is usually simpler and runs internally. When custom Java logic, enrichment from external systems, or complex schema transformations are required, `scroll + bulk` provides finer-grained control.

## 20. Comparing Scroll with `_reindex`

| Criterion | Scroll + application + Bulk | `_reindex` API |
|---|---|---|
| Data transformation in Java | Flexible | Limited to server-side scripts/pipelines |
| Enrichment from external APIs | Possible | Not directly supported |
| Simple index-to-index copy | Must write pipeline manually | Usually better suited |
| Per-document control | High | Lower at the application tier |
| Operational complexity | Must manage scroll, bulk, retries, and checkpoints | Elasticsearch manages most of the internal pipeline |
| Best suited for | Custom ETL | Query-based copy/reindex to target mapping |

Do not implement `scroll + bulk` manually when `_reindex` already meets your requirements. Conversely, when business logic or external integrations are needed, the application may need per-batch control.

## 21. Tracking Progress and Metrics

A scan job should record progress at the batch level:

- Number of batches read.
- Total documents read.
- Total documents processed successfully.
- Total documents failed or skipped.
- Batch fetch latency.
- Batch processing latency.
- Average response size.
- Retry count.
- Start and completion timestamps.

Avoid logging full documents or scroll IDs. Safe counts and checkpoints aid troubleshooting without exposing sensitive data or bloating logs.

If a job runs multiple partitions concurrently, track metrics per partition and cap concurrency. Opening too many scrolls simultaneously can exhaust cluster resources even when each scroll uses a small batch.

## 22. Security and Access Control

Scroll jobs often read huge volumes of data, so the job's service account should hold only the required read permissions on the relevant indices/aliases. Do not grant cluster admin privileges if the job only needs to search.

Scroll IDs represent temporary search context state. Do not log them publicly or pass them through untrusted channels. Protect connections with TLS and manage credentials via runtime secret stores.

For exports containing personal data, restrict fields via source filtering and govern output storage locations, retention, and access permissions. That is the application pipeline's responsibility, not an automatic feature of the Scroll API.

## 23. Common Mistakes

### Forgetting `scroll` on the First Request

Without a scroll context, subsequent requests cannot continue with a scroll ID. The initial request must request a scroll.

### Using an Outdated Scroll ID

Subsequent responses may return a new ID. Always replace the current variable with the latest ID before the next call and before cleanup.

### Failing to Clear the Context

The context keeps holding resources until `keep_alive` expires. Use `finally` or `try-with-resources` to close early.

### Setting `keep_alive` Too Short

If batch processing takes longer than `keep_alive`, the context can expire. Measure processing time and add appropriate headroom.

### Setting Batch Size Too Large

Large responses can spike heap, GC, network usage, and processing latency. Tune according to document size and consumer throughput.

### Using Scroll for UI Pagination

Scroll retains a server-side context and is ill-suited for users stepping arbitrarily between pages. Use `search_after + PIT` for deep pagination.

### Treating Scroll ID as a Durable Checkpoint

Scroll contexts expire and can vanish if a node/context is lost. Use durable business checkpoints and idempotent processing.

### Checking Only the Bulk API HTTP Status

A bulk request can have individual failing items. Check every item before marking a batch complete.

### Scanning the Full `_source` When Only a Few Fields Are Needed

Large payloads degrade throughput. Use source filtering or an appropriate projection.

## 24. Workflow for Implementing a Batch Scan Job

When building a large-data read job, follow this sequence:

1. Identify the source index/alias and query scoping the documents to read.
2. Choose Scroll for scan/batch tasks; choose `PIT + search_after` if ordered traversal or deep pagination is needed.
3. Pick an initial batch size based on document size and consumer capacity.
4. Choose a `keep_alive` long enough to process one batch with headroom.
5. Use `_doc` sort if business ordering is unnecessary.
6. Retrieve only required fields using source filtering.
7. Process batch by batch without holding the entire result set in RAM.
8. Design retries, idempotency, and durable checkpoints so the job is restartable.
9. Always clear the scroll context in `finally` or close the iterator.
10. Monitor open contexts, heap, GC, network, shard failures, and batch progress.
11. Test expired contexts, mid-batch process crashes, and downstream failures.
12. Mark the job complete only after all batches and destination writes are confirmed.

## 25. Conclusion

The Scroll API enables scanning large sets of documents in batches by keeping a search context open and advancing via `scroll_id`. The first request defines the query, batch size, and `keep_alive`; subsequent requests fetch new batches with the latest ID; upon completion or failure, the application must clear the context.

In Spring Data Elasticsearch, `searchForStream(...)` provides a convenient way to iterate results while requiring you to close the iterator. When manual control is needed, use the scroll start/continue/clear operations supported by your Spring Data version or call the REST API directly. Choose batch size based on document size and processing capacity, use `_doc` for pure scans, restrict `_source`, and process batches with idempotency and checkpoints. Scroll fits exports, backfills, and batch processing; for ordered deep pagination, `PIT` combined with `search_after` is generally the better choice.

## References

- [Elasticsearch – Scroll search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results#scroll-search-results)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Clear scroll API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-clear-scroll)
- [Elasticsearch – Point in Time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
- [Elasticsearch – Search after and PIT pagination](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Spring Data Elasticsearch – Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – `SearchHitsIterator` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHitsIterator.html)
