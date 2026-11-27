# Managing keep_alive, PIT IDs, and Closing Resources

When exporting large datasets or traversing many pages of results in Elasticsearch, an application must keep a search context alive long enough to continue fetching data. Two common mechanisms are Scroll and Point in Time (PIT). Both accept a `keep_alive` parameter, but their purposes and resource management differ.

With Scroll, Elasticsearch retains a scroll context to continue returning subsequent batches of documents. With PIT, Elasticsearch preserves a stable data view for a period of time; applications commonly combine PIT with `search_after` for deep pagination. In both cases, `keep_alive` specifies how long the context is kept since its most recent use. The application must store the latest ID returned by the server and explicitly close the resource once the job finishes.

If you forget to close a scroll or PIT, Elasticsearch will eventually reclaim resources when the context expires, but until then those contexts consume cluster resources. For long-running export jobs or high concurrency, explicit lifecycle management is an essential part of the design.

## 1. Why Is keep_alive Needed?

A normal search request returns a single page of results and completes. When fetching hundreds of thousands of documents, the application must send multiple requests. If data changes between requests, conventional pagination can skip or duplicate documents.

Scroll and PIT preserve a search context across multiple requests:

- **Scroll:** retains scroll state to fetch the next batch from a single search.
- **PIT:** preserves a view of the data at the time the PIT was opened, then uses `search_after` to continue from the sort values of the last hit.

`keep_alive` is the duration Elasticsearch keeps the context alive without a subsequent request. If the application sends another request before that period elapses, the request can extend the context's lifetime.

For example, an export opens a context with a `keep_alive` of one minute. If each batch is fetched within 10 seconds, each subsequent request keeps extending the context. If the application pauses for longer than one minute, the context may expire and the old ID becomes unusable.

`keep_alive` is not the maximum duration of the entire export. An export can run for many minutes if it continues using the context and extending it on time. However, the context still consumes resources for the entire time it remains open.

## 2. How Do Scroll Context and PIT Differ?

Both mechanisms support reading data across multiple requests, but they have different semantics:

| Criterion | Scroll | Point in Time (PIT) |
|---|---|---|
| Typical purpose | Scanning/exporting large datasets in batches | Preserving a snapshot for deep pagination or sequential queries |
| Fetching next page | Use the scroll ID to request the next batch | Use the PIT ID and `search_after` |
| Server-side state | Scroll context maintains scroll position | PIT maintains the data view |
| Result ordering | Should use a suitable sort; typically not for interactive UI | Requires a stable sort to use `search_after` |
| Renewal | Send a scroll request with a new `keep_alive` | Send a search request with a new PIT `keep_alive` |
| Termination | Clear scroll | Close PIT |
| Suitable scenarios | Batch export, reindexing, or sequential processing | Deep pagination requiring a consistent snapshot |

Scroll is typically used for sequential scan tasks rather than interactive pagination UIs. For deep pagination, Elasticsearch recommends PIT combined with `search_after` when consistent results are needed while the index changes.

PIT does not store the page position itself. It only preserves the data view. The application must still retain the sort values of the last hit and send them in `search_after` on the next request.

## 3. keep_alive Is Context Idle Time

A common misconception is that setting `keep_alive: 5m` means the export may run for at most five minutes. In reality, `keep_alive` is how long the context is retained after the most recent request.

Example:

    Open PIT with keep_alive = 1m
        |
        v
    Search batch 1
        |
        | next request after 20 seconds
        v
    Search batch 2, extend 1m
        |
        | next request after 25 seconds
        v
    Search batch 3, extend 1m
        |
        | next request after 30 seconds
        v
    Search batch 4, extend 1m
        |
        v
    Close PIT upon completion

As long as the next request arrives before the context expires and the server accepts it, the application can continue working far longer than the initial `keep_alive` value.

The `keep_alive` duration must be long enough to cover the expected interval between two consecutive requests, including:

- Batch processing time in the application.
- Network latency and Elasticsearch response time.
- Time to write data to a file or target system.
- Pauses caused by scheduling, backpressure, or retries.

Do not set `keep_alive` so short that the context expires during a slow file write. Nor should you set it excessively long if a job might crash unexpectedly, because the context will continue consuming resources until closed or expired.

## 4. Opening a PIT and Receiving the PIT ID

A PIT is opened on an index, alias, or data stream. Elasticsearch returns an ID representing the newly created point in time.

REST API:

    POST /products/_pit?keep_alive=1m

The response looks like:

    {
      "id": "46ToAw..."
    }

The application must store this ID for subsequent search requests and for closing the PIT when finished.

Key points to remember:

- The PIT ID is an opaque value issued by Elasticsearch; do not parse or modify the ID string.
- A PIT ID is not a document ID.
- The PIT ID is tied to the search context and its lifetime.
- The ID may change across search requests; always update to the latest ID from the response if a new ID is returned.
- Avoid exposing PIT IDs in public logs or user-facing API responses unless necessary.

A PIT opened on an alias retains a view of the indices the alias points to at open time. If the alias is later switched to another index, the open PIT still represents the context that was created and does not automatically move to a new snapshot of the alias.

## 5. Searching with PIT and search_after

After opening the PIT, the application sends a search request containing the `pit` section rather than specifying an index in the URL path:

    POST /_search
    {
      "size": 500,
      "pit": {
        "id": "46ToAw...",
        "keep_alive": "1m"
      },
      "sort": [
        { "created_at": "asc" }
      ],
      "query": {
        "match_all": {}
      }
    }

The search response contains hits and may contain a new PIT ID. Each hit includes a `sort` array if the request declared a sort.

Example last hit:

    {
      "_id": "p-0500",
      "sort": [
        "2026-11-13T10:30:00Z",
        4294967298
      ]
    }

The next request uses the sort values of the last hit in `search_after`:

    POST /_search
    {
      "size": 500,
      "pit": {
        "id": "46ToAw...",
        "keep_alive": "1m"
      },
      "sort": [
        { "created_at": "asc" }
      ],
      "search_after": [
        "2026-11-13T10:30:00Z",
        4294967298
      ],
      "query": {
        "match_all": {}
      }
    }

The `search_after` values must be taken from the last hit of the previous batch, preserving order and data types. Do not fabricate timestamps or document IDs instead of the sort values returned by Elasticsearch.

When using PIT, Elasticsearch adds an internal `_shard_doc` tie-breaker to the sort if needed for stable pagination within the snapshot. Response hits may include that corresponding sort value. Pass the entire sort values array of the last hit—including that tie-breaker value—into the next request.

If the application saves only `created_at` and drops the tie-breaker value from the sort array, documents sharing the same timestamp may be duplicated or skipped during pagination.

## 6. Always Use the Latest PIT ID

A critical aspect of managing PITs is that a search response may return a new PIT ID. The API documentation recommends using the latest ID returned in the response for the next request.

Processing flow:

    pitId = openPointInTime()

    while (more data):
        response = search(pitId, searchAfter)

        if response has pit_id:
            pitId = response.pit_id

        process hits

        if hits is empty:
            break

        searchAfter = sort values of the last hit

    closePointInTime(pitId)

Do not hold onto the initial ID if the response provides a new one. Likewise, do not use an ID from an older response after receiving a newer ID.

If an application has multiple workers processing the same PIT, coordinate updates to the PIT ID and cursor. Two workers must not independently overwrite state with out-of-order responses. The simplest approach is a sequential loop owning the cursor and PIT ID per export session.

## 7. Extending PIT with keep_alive

A PIT is opened with a `keep_alive` duration. Subsequent search requests can send a new `keep_alive` to extend the context's lifetime.

Example:

    POST /_search
    {
      "pit": {
        "id": "46ToAw...",
        "keep_alive": "2m"
      },
      "size": 500,
      "sort": [
        { "created_at": "asc" }
      ],
      "query": {
        "match_all": {}
      }
    }

Here, the request asks to keep the PIT alive for another two minutes from this usage. If the next batch requires longer processing, the application can send an appropriate `keep_alive` in the next request.

You do not need to set `keep_alive` to the expected total duration of the entire job. Set it long enough for any expected gap between two consecutive uses. If an export can be paused by a queue system for 10 minutes, a 1-minute `keep_alive` will not suffice unless the application actively extends the context while waiting.

### Do Not Extend When Data Is No Longer Needed

When the export finishes, close the PIT immediately. Do not keep sending requests merely to keep the context alive if the application no longer needs the snapshot.

If a job is cancelled, a user clicks cancel, or the application detects an unrecoverable destination error, transition to cleanup and close the PIT. Do not rely on `keep_alive` expiration as the normal termination path.

## 8. PIT Expiration and Error Handling

If no request arrives within the `keep_alive` window, the PIT may expire. Any request using an expired ID will fail because the context no longer exists or is no longer valid.

Common causes:

- The previous batch took too long to process.
- The job was paused or a worker was not scheduled.
- Writing the destination file or upload was slow.
- Retries/backoff stretched longer than `keep_alive`.
- The application restarted without persisted PIT state or could not resume.
- The PIT was already closed by cleanup or another task.

When a PIT expires, you cannot assume that opening a new PIT and continuing with the old `search_after` preserves the original snapshot. A new PIT represents a new view of the data; documents may have been added, modified, or deleted between the two snapshots.

The recovery strategy should follow business requirements:

1. If the export can restart from the beginning, close or discard the old cursor state and start a new session.
2. If an exact consistent snapshot is required, ensure the PIT stays alive long enough and pair it with durable job/cursor management.
3. If the system tolerates changing data and eventual consistency, open a new PIT and resume from a business checkpoint while implementing deduplication and missing-record handling.
4. Never loop indefinitely retrying the same request with an expired PIT ID.

### Retrying Does Not Mean Extending

If a search request fails transiently due to a network error, a retry may succeed while the PIT is still valid. However, once the PIT has expired, retrying with the same ID will not revive the context.

When handling errors, distinguish between:

- Transient network or cluster errors: retry with limits and backoff.
- Invalid or expired PIT ID: restart the session according to policy.
- Query or mapping errors: fix the query/data; do not retry indefinitely.
- Destination write errors: handle per export/checkpoint policy, then clean up the PIT if the job is aborted.

## 9. Explicitly Closing the PIT

When the snapshot is no longer needed, the application must invoke the Close Point in Time API:

    DELETE /_pit
    {
      "id": "46ToAw..."
    }

The response indicates whether the PIT was closed:

    {
      "succeeded": true,
      "num_freed": 3
    }

`num_freed` reports the number of shard contexts freed in the response. This value may differ from the document count or index count.

Close the PIT whenever:

- The export has finished reading all data.
- A user cancels the export.
- The job fails and cannot continue.
- An unrecoverable search error terminates the job.
- The application is no longer using the snapshot.

Closing the PIT frees resources promptly instead of waiting for `keep_alive` to expire.

If the final search response returned a new PIT ID, use that latest ID when closing. If the API or an error prevented receiving a new ID, use the most recent ID held by the application and handle the case where the context has already expired or been freed.

## 10. Using try/finally to Guarantee PIT Closure

Resource closure should live inside a `finally` block so it executes even when batch processing throws an exception:

    String pitId = openPit();

    try {
        String searchAfter = null;

        while (true) {
            SearchResponse<Product> response =
                searchWithPit(pitId, searchAfter);

            if (response.pitId() != null) {
                pitId = response.pitId();
            }

            List<Hit<Product>> hits = response.hits().hits();
            if (hits.isEmpty()) {
                break;
            }

            export(hits);
            searchAfter = extractSortValues(hits.getLast());
        }
    } finally {
        closePit(pitId);
    }

This is pseudocode illustrating the lifecycle; exact response type names and accessors depend on your Elasticsearch Java API Client version. The key invariant is updating `pitId` whenever a response returns a new ID and closing the tracked ID inside `finally`.

In production code, guard both opening and closing the PIT:

- Only call close once a valid PIT ID has been received.
- If closing fails because the PIT already expired, record the cleanup outcome and conclude the job per policy.
- Do not let an exception in cleanup mask the original export exception.
- Log sufficient correlation/job IDs for troubleshooting, while avoiding writing full PIT IDs to broadly accessible logs.

## 11. Java API Client: Opening, Searching, and Closing PIT

The Elasticsearch Java API Client provides methods for opening a PIT, searching, and closing a PIT. Exact builder syntax can vary across client versions managed by Spring Boot/Spring Data.

Opening a PIT:

    OpenPointInTimeResponse opened =
        client.openPointInTime(request -> request
            .index("products")
            .keepAlive(time -> time.time("1m"))
        );

    String pitId = opened.id();

Searching with a PIT:

    SearchResponse<Product> response =
        client.search(request -> request
            .pit(pit -> pit
                .id(pitId)
                .keepAlive(time -> time.time("1m"))
            )
            .size(500)
            .sort(sort -> sort
                .field(field -> field
                    .field("created_at")
                    .order(SortOrder.Asc)
                )
            )
            .query(query -> query
                .matchAll(matchAll -> matchAll)
            ),
        Product.class);

Updating the PIT ID if the response returns a new ID:

    if (response.pitId() != null) {
        pitId = response.pitId();
    }

Closing the PIT:

    ClosePointInTimeResponse closed =
        client.closePointInTime(request -> request.id(pitId));

Response class names, `Time` types, sort enums, and accessors may vary by version. Use the APIs matching your installed dependencies; do not mix legacy High Level REST Client builders with the modern Elasticsearch Java API Client.

When using the Java client directly inside a Spring service, inject the configured client bean rather than creating a new client per export. The client is a shared resource managed by Spring/the container.

## 12. Managing the Cursor When Using search_after

The PIT ID and `search_after` are two distinct pieces of state:

- The PIT ID identifies the snapshot/context.
- `search_after` identifies the continuation position in that snapshot's sort order.

An export may need to store:

    ExportState
      jobId
      pitId
      searchAfterValues
      keepAlive
      processedCount
      status

`searchAfterValues` should preserve the exact data types and order of the `sort` array. If the sort includes a timestamp, numeric ID, and `_shard_doc`, the cursor must store all of those values.

Do not reconstruct the cursor from the document entity when the response already provides sort values. Sort values may include internal values or formats normalized by Elasticsearch.

### Checkpoints and PIT Expiry

If you persist the cursor to a database to resume after a restart, remember that the PIT can expire while the application is down. Saving a cursor checkpoint does not keep the snapshot alive.

On restart:

- If the PIT is still valid and the ID remains usable, continue with the latest saved PIT ID and `search_after`.
- If the PIT has expired, do not pair the old cursor with a new PIT and claim it is the same snapshot.
- If a full consistent export is required, open a new PIT and start over.
- If resuming from a business checkpoint is acceptable, implement deduplication and change-handling logic.

A common pattern for restartable exports is writing to the destination using idempotent keys, checkpointing per batch, and allowing partial re-runs. This is an application-level strategy, not an automatic capability of PIT.

## 13. Scroll keep_alive and Scroll IDs

Scroll has its own lifecycle. The first request opens the scroll context:

    POST /products/_search?scroll=1m
    {
      "size": 500,
      "sort": [ "_doc" ],
      "query": {
        "match_all": {}
      }
    }

The response returns `_scroll_id` and the first batch.

Subsequent requests use the scroll ID:

    POST /_search/scroll
    {
      "scroll": "1m",
      "scroll_id": "DnF1ZXJ5VGhlbkZldGNo..."
    }

Each scroll request may return a new scroll ID. The application must use the latest ID on the next call, mirroring the PIT ID update rule.

`scroll` in subsequent requests specifies how long to retain the context from that request onward. If the job processes batches slowly, pick an interval long enough to cover processing and the next request.

### Closing the Scroll Context

When reading finishes or a job is cancelled, invoke Clear Scroll:

    DELETE /_search/scroll
    {
      "scroll_id": [
        "DnF1ZXJ5VGhlbkZldGNo..."
      ]
    }

Clear Scroll frees the context early. Do not simply exit the loop after the final batch and neglect cleanup.

Scroll IDs are also opaque values. Do not parse or edit the string. If a response returns a new ID, update state and use the latest ID.

## 14. Reading Scroll Results Completely and Safely

A scroll loop normally continues until the returned batch has no hits:

    response = initialSearchWithScroll()
    scrollId = response.scrollId

    try:
        while response has hits:
            process(response.hits)
            response = continueScroll(scrollId)
            if response has new scroll_id:
                scrollId = response.scroll_id
    finally:
        clearScroll(scrollId)

This is pseudocode. In an actual implementation:

- Process the current batch before requesting the next batch when backpressure is needed.
- Update the scroll ID after each response.
- Stop when hits are empty.
- Ensure clear scroll runs even when an exception occurs.
- Avoid holding all data in memory when the goal is streaming export.

If a batch is written to a destination file or database, mark the batch complete only after the write succeeds. If writing fails, decide whether to retry the batch, restart the job, or abort the scroll per policy. Scroll context does not replace durable checkpoints.

## 15. Scroll in Spring Data Elasticsearch

Spring Data Elasticsearch provides a streaming search API for iterating results hit by hit while managing scroll underneath in supported versions.

High-level example:

    Query query = new NativeQueryBuilder()
        .withQuery(q -> q.matchAll(m -> m))
        .withPageable(PageRequest.of(0, 500))
        .build();

    try (SearchHitsIterator<Product> stream =
             operations.searchForStream(
                 query,
                 Product.class,
                 IndexCoordinates.of("products")
             )) {

        while (stream.hasNext()) {
            SearchHit<Product> hit = stream.next();
            export(hit.getContent());
        }
    }

`SearchHitsIterator` is a closeable iterator. Use `try-with-resources` to guarantee scroll resources are released when reading finishes or an exception occurs.

Scroll duration APIs, `keep_alive` configuration, and iterator types can vary across Spring Data Elasticsearch versions. Check the `searchForStream` signature and query configuration options in your project's dependencies. Do not assume `Pageable` configures `keep_alive` if the specific API lacks that setting.

If you need fine-grained control over scroll IDs or `keep_alive` per request, use the Elasticsearch Java API Client directly. In that case, the application is responsible for updating the ID and clearing the context.

## 16. Closing Resources When an Application Has Multiple Exit Paths

An export can terminate in several ways:

- All data has been read.
- A user cancels it.
- The job exceeds its deadline.
- Reading from Elasticsearch fails.
- Writing the file or uploading to the destination fails.
- The process receives a shutdown signal.

Every exit path after the context has been opened requires cleanup.

Management pattern:

    String pitId = null;
    Throwable failure = null;

    try {
        pitId = openPit();
        runExport(pitId);
    } catch (Exception ex) {
        failure = ex;
        throw ex;
    } finally {
        if (pitId != null) {
            try {
                closePit(pitId);
            } catch (Exception cleanupError) {
                if (failure != null) {
                    failure.addSuppressed(cleanupError);
                } else {
                    throw cleanupError;
                }
            }
        }
    }

This pattern demonstrates preserving the original exception if cleanup also fails. In production applications, use a helper or resource wrapper to avoid duplicating this logic.

If using `try-with-resources`, you can wrap the PIT in an `AutoCloseable` class:

    try (PitSession session = pitSessionFactory.open(
            IndexCoordinates.of("products"),
            Duration.ofMinutes(1))) {
        exportAll(session);
    }

`PitSession` is an application-defined class that holds the latest PIT ID and closes it inside `close()`. It is not a built-in Spring Data class; it illustrates wrapping lifecycle management so services never forget cleanup.

## 17. Managing PIT in Asynchronous Jobs

For export jobs triggered via a queue or scheduler, the PIT lifecycle may span beyond a single HTTP request. Avoid opening a PIT in a controller and leaving a separate worker to guess the ID or cursor.

A possible design:

    Export API
       |
       v
    Create export job
       |
       v
    Worker opens PIT
       |
       v
    Read batch with search_after
       |
       v
    Write batch to destination
       |
       +----> Persist checkpoint
       |
       v
    More results?
       |
       +---- yes ---> next batch; renew keep_alive
       |
       +---- no ----> close PIT; mark complete

Job state should include:

- Job ID.
- Status: running, completed, failed, or cancelled.
- Latest PIT ID if continuing the same snapshot.
- Sort values of the last hit.
- Count of processed documents.
- Timestamp of the last heartbeat or renewal.
- Error details and retry policy.

If a worker loses connectivity or restarts, job state helps decide whether to resume, rerun, or mark failed. Do not rely on in-memory variables of a single process for exports that may span deployments.

## 18. Resource Limits and Monitoring

Each PIT or scroll context reserves resources on Elasticsearch. Concurrent context counts, lifetimes, and data volume can affect heap, file descriptors, segments, and merging.

Key guidelines:

- Limit the number of concurrent exports.
- Use moderate batch sizes.
- Choose a `keep_alive` sufficient for processing time between two batches.
- Close contexts immediately upon completion or cancellation.
- Avoid opening a PIT before a worker is ready to use it.
- Avoid holding contexts open while waiting for user interaction.
- Monitor cluster search context metrics.

Elasticsearch exposes stats APIs to observe search contexts and node/index activity. Depending on operational goals, inspect node stats or index stats, such as open search contexts and search-related metrics.

If open context counts steadily climb without dropping, check:

- Are jobs clearing scrolls or closing PITs?
- Do exception paths run cleanup?
- Is the client saving the latest ID or trying to close an outdated ID?
- Are jobs hanging between batches?
- Is `keep_alive` much longer than necessary?
- Are multiple workers opening contexts without actively processing data?

Do not try to mask a missing-cleanup bug by shrinking `keep_alive` excessively. Fix the resource lifecycle first.

## 19. Choosing keep_alive and Batch Size

`keep_alive` and batch size are interrelated:

- Too small a batch increases request count and overhead.
- Too large a batch increases processing time, memory usage, and the gap between requests.
- Too short a `keep_alive` risks expiration while the application processes a batch.
- Too long a `keep_alive` keeps contexts alive long after a job stops abnormally.

Start by measuring:

1. Time to fetch a batch from Elasticsearch.
2. Time to process each document.
3. Time to write a batch to the destination.
4. Network latency and expected retries.
5. Number of concurrent workers.

For instance, if a batch typically completes in 5 to 10 seconds but file writes occasionally take 30 seconds, a 1-minute `keep_alive` offers reasonable headroom. If batches might sit in a queue for several minutes, design heartbeats or renewals appropriately; blindly raising `keep_alive` to hours keeps contexts pinned unnecessarily long.

There is no single optimal batch size or `keep_alive` for every cluster. Benchmark with realistic document sizes, shard counts, and search/indexing load.

## 20. PIT and Scroll When Exporting to External Systems

Exports generally have two sides: reading from Elasticsearch and writing to files, object storage, databases, or external APIs. Writing to the destination can take longer than fetching a batch.

A safe loop should consider:

1. Read a batch from Elasticsearch.
2. Write the batch to the destination.
3. Confirm destination write success.
4. Persist the batch checkpoint.
5. Fetch the next batch and extend the context.

Fetching the next batch before finishing the write of the current batch forces the application to hold multiple batches in memory and stretches the gap between context renewals.

If the destination write succeeds but the process stops before saving the checkpoint, the batch may be written again on restart. Use idempotent keys or upsert mechanisms at the destination when duplicates must be avoided.

If the checkpoint is saved before the destination write succeeds, the job may skip unwritten data. Therefore, the commit order of batch writes and checkpoints must reflect the export's consistency requirements.

PIT guarantees the source snapshot while the context is alive; it does not create a distributed transaction between Elasticsearch and the destination system.

## 21. Security and Handling PIT IDs

PIT IDs and scroll IDs are opaque tokens used to continue a context. They should not be treated as business data or exposed unnecessarily to clients.

Guidelines:

- Store IDs only in job state or required runtime memory.
- Do not write full IDs to public logs.
- Do not let users submit arbitrary PIT IDs to access data.
- Bind cursors to an authenticated job, user, or tenant.
- Enforce authorization checks on every export request per application security design.
- Restrict lifetime and close contexts upon completion.

PIT does not replace authorization. Possessing a PIT ID must never be treated as sufficient proof that a user is authorized to view the data.

## 22. Common Mistakes

### Thinking keep_alive Is the Maximum Job Duration

`keep_alive` is how long the context is kept after its most recent use. Subsequent requests extend it. A job can run longer than the initial `keep_alive` if it keeps using the context on time.

### Setting keep_alive Too Short

If batch processing or destination writes take longer than `keep_alive`, the PIT/scroll context can expire. Measure actual processing times and choose reasonable headroom.

### Setting keep_alive Too Long Without Cleanup

Unneeded contexts continue holding resources. Close them immediately on completion or cancellation rather than relying solely on expiration.

### Continuing to Use an Old PIT ID

Search responses can return a new PIT ID. Always update and use the latest ID for the next request and when closing.

### Saving Incomplete search_after Values

Store all sort values of the last hit, including tie-breakers. Never reconstruct a cursor from a single field.

### Opening a New PIT and Treating an Old Cursor as the Same Snapshot

A new PIT sees a different data view. An old `search_after` does not restore an expired snapshot; restart or use a business checkpoint strategy that handles duplicates and gaps.

### Failing to Close PIT on Exceptions

Place closure inside `finally` or use an `AutoCloseable` resource wrapper. Cleanup must run even when exports are cancelled or destination writes fail.

### Forgetting to Clear Scroll

Scroll contexts must be cleared once reading completes. Exiting a loop does not immediately guarantee context release.

### Failing to Update to the New Scroll ID

Scroll responses may return a new ID. Use the latest ID for the next batch and when clearing the scroll.

### Using Scroll for Deep Interactive Pagination

Scroll is designed for context-based batch reads, typically suited for exports. For deep pagination needing a consistent snapshot, `PIT + search_after` is usually a better choice.

### Treating PIT as a Durable Checkpoint

PIT has an expiration time and consumes server resources. Saving IDs/cursors does not guarantee the context survives a restart. Design restart/retry handling separately.

## 23. Lifecycle Checklist for an Export

A PIT-based export flow can follow these steps:

1. Authenticate the requester and identify the permitted index/alias.
2. Check concurrency and export size limits.
3. Open a PIT with a `keep_alive` sufficient for processing one batch.
4. Store the latest PIT ID.
5. Search the first batch using a stable sort.
6. Process and write the batch to the destination.
7. Save the checkpoint after the batch is successfully written.
8. Update the PIT ID from the response if provided.
9. Save all sort values of the last hit as `search_after`.
10. Send the next request before `keep_alive` expires, extending it if needed.
11. Stop when no hits remain.
12. Close the PIT inside `finally`.
13. Mark the job completed after cleanup per policy.
14. On error, classify the error and decide retry/restart; never reuse an expired PIT.

For Scroll, replace the PIT/`search_after` steps with opening the scroll, using the latest scroll ID to fetch the next batch, and calling clear scroll in `finally`.

## Conclusion

`keep_alive` controls how long a Scroll context or PIT is retained after its most recent use; it is not the maximum duration of the entire job. Scroll uses a scroll ID to fetch subsequent batches and requires clearing the scroll when done. PIT preserves a data view and is commonly combined with `search_after`; the application must save full sort values, update to the latest PIT ID from responses, and close the PIT when the snapshot is no longer needed.

In Spring Data Elasticsearch, `SearchHitsIterator` must be closed with `try-with-resources` when using streaming/scroll. For PIT or workflows requiring fine-grained control over IDs and `keep_alive`, you can use the Elasticsearch Java API Client and place cleanup in `finally` or an `AutoCloseable` wrapper. Choose a `keep_alive` sufficient for the interval between batches, limit concurrent contexts, handle expiration intentionally, and never treat PIT IDs or cursors as durable checkpoints. Proper lifecycle management keeps exports stable and prevents holding Elasticsearch resources longer than needed.
