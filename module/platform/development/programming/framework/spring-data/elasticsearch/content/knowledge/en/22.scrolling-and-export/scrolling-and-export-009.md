# Data Changes During Scanning and Consistency Requirements

When exporting hundreds of thousands or millions of documents from Elasticsearch, the scan can run for a long time while other applications continue inserting, updating, or deleting data. If each page is read as an independent search request, the result set can shift between calls: documents get duplicated, skipped, or returned with different versions.

To pick the right scanning approach, first clarify the consistency requirement:

- **Snapshot export:** export data according to the state Elasticsearch sees at the moment the scan begins. Changes occurring afterward are handled in a separate sync pass.
- **Live scan:** tolerate data changing while reading; results reflect multiple points in time and may require handling duplicates or drift.
- **Snapshot plus changes:** export a stable snapshot while capturing changes occurring after the snapshot mark to apply subsequently.

Elasticsearch provides the Scroll API and Point in Time (PIT) to preserve a stable view when reading across multiple pages. `search_after` handles cursor-based pagination, yet when used alone it creates no snapshot and cannot guarantee stable results as data mutates.

## 1. Why Do Data Changes Skew Pagination?

Suppose an application exports orders sorted by `created_at` ascending, reading 100 documents per request. Initially, the list is ordered:

```text
Page 1: A, B, C, D, E, ...
Page 2: F, G, H, I, J, ...
```

After reading the first page, a new document is inserted before F's position. When the second-page request uses `from = 100`, every position after the new document shifts by one slot. The result can repeat the last document of page 1 or skip the document originally at the top of page 2.

Other scenarios include:

- **Insert:** a new document added before the cursor/offset shifts later documents backward.
- **Delete:** a deleted document shifts trailing positions forward.
- **Updating a sort field:** a document can move from behind the cursor to ahead of it or vice versa.
- **Updating a query field:** a document can begin matching or stop matching the query between pages.
- **Refresh:** written changes become searchable only after a refresh; two requests may hit different searchers.

The problem is not limited to `from/size`. Any pagination strategy issuing multiple independent search requests needs a plan for concurrent data mutations.

## 2. Refresh and When Data Becomes Searchable

Elasticsearch is a near real-time system. A successful index, update, or delete operation does not mean the document immediately appears in or disappears from search results. Changes must be refreshed to become searchable.

For example:

1. The application writes document `order-101`.
2. Elasticsearch acknowledges the write.
3. Before refresh, a new search may not see that document yet.
4. After refresh, a search can find the document.

When opening a Scroll or PIT, the search view is established from the state already searchable at context open time. Therefore, define clearly which write and which refresh the export cutoff follows.

If the workflow must guarantee prior writes are searchable before starting the scan, you can:

- Use `refresh=wait_for` on relevant write operations before opening the snapshot.
- Explicitly refresh the index during export preparation if operational guidelines permit.
- Lock in a source write watermark/sequence and confirm the data has refreshed before opening PIT or Scroll.

Refreshing only makes prior changes visible to searches. It does not lock the index and does not block subsequent writes after the refresh.

## 3. Scroll Preserves the Search View at Start Time

The Scroll API creates a search context and holds search state so the application can read subsequent batches. Follow-up scroll requests keep reading from that initial view instead of re-executing a fresh search against the newest index state.

With an active scroll context:

- Documents added after opening the scroll do not appear in that scan.
- Documents updated after opening the scroll continue to be seen at their initial view version.
- Documents deleted after opening the scroll can still be returned from the initial view.
- These changes do not cause scanned batches to shift unexpectedly as in normal offset pagination.

This property is valuable for consistent exports: every batch in one scan comes from the same search context. However, this is a search-level snapshot, not a cluster-wide ACID transaction or an atomic multi-index point-in-time guarantee across independent writes.

### 3.1. Opening a Scroll

Example reading 500 documents per batch:

```http
POST /orders/_search?scroll=1m
Content-Type: application/json

{
  "size": 500,
  "sort": ["_doc"],
  "track_total_hits": false,
  "query": {
    "match_all": {}
  }
}
```

Points to note:

- `scroll=1m` instructs Elasticsearch to retain the search context at least long enough for the client to fetch the next batch. Each follow-up scroll request can extend this window.
- `size` is the maximum number of documents per batch.
- Sorting by `_doc` is generally suited for fast full-data traversal when no business ordering is needed.
- `track_total_hits: false` avoids computing exact total counts if the export does not need them.

The initial response returns `_scroll_id` and the first batch inside `hits.hits`.

### 3.2. Reading the Next Batch

Send the scroll ID received in the previous response:

```http
POST /_search/scroll
Content-Type: application/json

{
  "scroll": "1m",
  "scroll_id": "DXF1ZXJ5QW5kRmV0Y2gBAAAAA..."
}
```

The response returns the next batch and may return a new `_scroll_id`. The client must always use the latest returned scroll ID, never assuming the initial ID stays valid throughout the entire run.

Repeat until the returned batch is empty. Then clear the search context.

### 3.3. Closing the Scroll Context

```http
DELETE /_search/scroll
Content-Type: application/json

{
  "scroll_id": [
    "DXF1ZXJ5QW5kRmV0Y2gBAAAAA..."
  ]
}
```

Close the context immediately upon completion or cancellation. Do not leave scroll contexts open merely because the application omitted cleanup. Search contexts pin resources and old segments needed for the initial view; many long-lived contexts increase pressure on memory, file handles, and retained disk space.

### 3.4. `keep_alive` Is Not the Maximum Duration of the Entire Export

The `scroll`/`keep_alive` value denotes how long the context is kept since the last access. Each follow-up batch fetch extends the context. Thus, an export lasting 30 minutes can still use a `keep_alive` shorter than 30 minutes if the client keeps fetching batches before expiration.

Do not set an unnecessarily long keep-alive. Choose a duration covering processing and network latency between two batches, allowing for transient delays. If the client pauses too long, the context may expire and the scan cannot resume using the old scroll ID.

## 4. Point in Time (PIT) Preserves a Snapshot Across Search Requests

Point in Time creates a stable view of an index at the moment the PIT is opened. PIT is commonly paired with `search_after` to traverse many pages without maintaining a scroll batch chain.

PIT fits well when:

- You need deep traversal with a meaningful business sort order.
- You want stable results while the index keeps receiving changes.
- You need cursor pagination instead of `from/size`.
- You want to fetch batches based on the sort values of the previous page's last hit.

Opening a PIT:

```http
POST /orders/_pit?keep_alive=2m
```

The response returns a PIT ID. Pass this ID in the Search API:

```http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "46ToAwMDaWR4BXV...",
    "keep_alive": "2m"
  },
  "track_total_hits": false,
  "sort": [
    { "created_at": "asc" },
    { "_shard_doc": "asc" }
  ],
  "query": {
    "match_all": {}
  }
}
```

The PIT ID is sent on every subsequent request. Elasticsearch may return a new PIT ID; the client should use the latest ID from the response. `keep_alive` is extended as requests continue using the PIT.

### 4.1. Using `search_after`

After receiving the first batch, take the `sort` array of the last hit. Pass that array in the next request:

```json
{
  "size": 500,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "2m"
  },
  "track_total_hits": false,
  "sort": [
    { "created_at": "asc" },
    { "_shard_doc": "asc" }
  ],
  "search_after": [
    "2026-11-13T10:15:00Z",
    4294967298
  ],
  "query": {
    "match_all": {}
  }
}
```

The values inside `search_after` must be taken intact from the previous batch's last hit `sort` array, preserving order and data types. Do not recompute them from `_source` fields when the response already provides sort values.

Repeat until a batch is empty. Finally, close the PIT:

```http
DELETE /_pit
Content-Type: application/json

{
  "id": "LATEST_PIT_ID"
}
```

### 4.2. Sort Must Have a Deterministic Order

If sorting uses only `created_at`, multiple documents may share the same timestamp. When resuming via `search_after`, a tie-breaker is needed so ordering among equal documents is deterministic.

With PIT, `_shard_doc` is an efficient tie-breaker for snapshot traversal order. You can declare it explicitly as shown above. If not using PIT, use a stable sort field unique within the query scope, such as a `keyword` `event_id`; do not assume `_id` behaves as a normal sortable field.

## 5. `search_after` Without PIT Does Not Create a Snapshot

`search_after` lets you pass the sort values of the previous page's last hit to find documents after the cursor. However, when requests omit PIT, Elasticsearch searches against whatever current state each request sees.

For example:

1. The first request returns documents with `created_at` from 10:00 to 10:05.
2. The application saves the last document's sort value as 10:05.
3. A new document with `created_at = 10:03` is written and refreshed.
4. The next request uses `search_after` at 10:05, so the new document falls ahead of the cursor and is omitted from the traversal.

Another document with a sort value newer than the cursor may appear on a later page even though it did not exist when page 1 was read. If an already-read document has its sort field updated to move past the cursor, it can appear again. If an unread document moves ahead of the cursor, it can be skipped.

A unique tie-breaker resolves ordering ties at equal sort values, yet it does not turn independent search requests into a snapshot. When consistency across the full scan is needed, combine `search_after` with PIT.

## 6. What Happens to Inserts, Updates, and Deletes During a Scan?

The table below describes behavior at the search-snapshot level:

| Change after opening Scroll/PIT | Scan using the active snapshot | New search without snapshot |
|---|---|---|
| Insert new document | New document is invisible in the current snapshot. | Visible once the change refreshes. |
| Update document | Sees the old version belonging to the snapshot; does not see the new version in the active snapshot. | Sees the new version after refresh. |
| Delete document | Document from the initial snapshot may still be returned. | Document disappears once delete refreshes. |
| Update sort field | Position inside the snapshot does not change with the new update. | Document may shift positions across requests. |
| Update query field | Snapshot match status follows the initial data. | Document may start or stop matching after refresh. |

This is ideal for a snapshot-consistent export, but understand the business implication: a document deleted during the export may still appear in the exported file, and a document created mid-export will be absent from it.

If the goal is "export all data that existed at start time," this behavior is usually right. If the goal is "export every change occurring up until the job ends," a lone snapshot is insufficient.

## 7. Search Snapshots Are Not Cluster-Wide Transactions

Scroll contexts and PITs preserve a search view so multiple requests read consistently across participating shards. They do not create a database transaction with write locks and rollback across the cluster.

Limits to keep in mind:

- Elasticsearch still accepts writes during the scan; new writes are never locked by PIT or Scroll.
- The search view reflects data already searchable when the context opened.
- An update spanning multiple indices does not become an atomic transaction merely because a client opened a PIT across an alias or multiple indices.
- With multiple independent write sources, define data cutoffs and synchronization at the business layer.
- Search snapshots do not replace backups. For index backup/restore, use the Elasticsearch Snapshot and Restore API with a proper snapshot repository.

Describe consistency requirements accurately: a search snapshot gives a stable read view for a scan, not transactional guarantees across all system writes.

## 8. Choosing Scroll or PIT Combined with `search_after`?

| Criterion | Scroll | PIT + `search_after` |
|---|---|---|
| Typical goal | Large export or batch scan. | Deep pagination, cursors, or exports requiring deterministic sort. |
| Fetching next batch | Scroll ID and continuation request. | Sort values of last hit and `search_after`. |
| Snapshot | Retains search context from initial request. | PIT keeps a stable view across search requests. |
| Sort | `_doc` is usually best for fast scans. | Can sort by business fields; PIT supports `_shard_doc` tie-breaker. |
| Server-side state | Retains scroll context. | Retains PIT context; client manages PIT ID and cursor. |
| UI pagination fit | Not the default choice. | Better suited for cursor pagination. |
| Termination | Clear scroll context. | Close PIT. |

Choose Scroll for straightforward batch exports, especially when business ordering is unneeded. Choose PIT with `search_after` when you need stable cursors, field sorting, and explicit control over continuation position.

Do not use `from/size` for very large exports simply because the API looks simple. Offset pagination must skip preceding results, is capped by `index.max_result_window`, and drifts when data changes between requests.

## 9. Scanning Data with Spring Data Elasticsearch

Spring Data Elasticsearch provides `ElasticsearchOperations.searchForStream(...)` to iterate results like an iterator. This API uses scroll underneath and returns `SearchHitsIterator`, letting applications process hits one by one without loading everything into memory.

Example:

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import java.util.function.Consumer;

@Service
public class OrderExportService {

    private final ElasticsearchOperations operations;

    public OrderExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportActiveOrders(Consumer<OrderDocument> writer) {
        Query query = buildActiveOrdersQuery();

        try (SearchHitsIterator<OrderDocument> hits =
                     operations.searchForStream(query, OrderDocument.class)) {
            while (hits.hasNext()) {
                SearchHit<OrderDocument> hit = hits.next();
                writer.accept(hit.getContent());
            }
        }
    }

    private Query buildActiveOrdersQuery() {
        Criteria criteria = new Criteria("status").is("ACTIVE");
        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(PageRequest.of(0, 500));
        return query;
    }
}
```

The example uses `Consumer` as an illustrative sink, filtering `ACTIVE` orders and setting a batch size of 500 via `Pageable`. In production code, replace the consumer with a file/object-storage writer or proper batch sink. `SearchHitsIterator` must be closed to free the scroll context; `try-with-resources` ensures closure even if `writer` throws an exception. Check scroll `keep_alive` configuration and `searchForStream` overloads against your project's Spring Data Elasticsearch version.

### 9.1. Do Not Hold All Results in a List

Avoid materializing the iterator into a giant list when exporting large datasets:

```java
List<OrderDocument> all = StreamSupport
        .stream(hits.spliterator(), false)
        .map(SearchHit::getContent)
        .toList();
```

This snippet can retain every document on the heap and negate batch processing benefits. Instead, write documents to a file, object storage, message queue, or sink in small batches.

### 9.2. Batch Writing and Error Handling

When writing to a sink, group documents into batches to cut I/O overhead while bounding batch size to memory limits. If the sink fails, decide whether to abort the entire export or retry the batch.

When retrying sink writes, use stable document IDs as idempotency keys so replaying the same record creates no duplicates. Scroll/PIT guarantees a stable read view; neither guarantees single-delivery to the sink.

### 9.3. Spring Data Versions and Low-Level Scroll APIs

Spring Data Elasticsearch versions may provide low-level scroll APIs to start scrolling, continue by scroll ID, and clear the context. Method names and overloads vary by version. When using them directly:

1. Save the latest scroll ID from each response.
2. Pass an appropriate `keep_alive` on each continuation call.
3. Stop when a batch is empty.
4. Invoke clear scroll inside `finally` or an equivalent cleanup hook.

For typical application code, `searchForStream` with `try-with-resources` is usually simpler than managing scroll IDs manually.

## 10. Handling Changes Occurring During Export

Scroll/PIT delivers a stable snapshot, yet it does not automatically fold post-snapshot changes into the export output. If business rules demand the latest data up to job completion, add a change stream.

### 10.1. Snapshot Followed by Delta Sync

A common pattern:

```text
Record watermark W
       |
       v
Open PIT / Scroll snapshot
       |
       v
Export all documents in the snapshot
       |
       v
Read change log from W up to sync time
       |
       v
Apply inserts/updates/deletes in order
       |
       v
Reconcile and finalize export
```

The watermark may be a change-log offset, CDC position, or reproducible business mark. Crucially, establish a clear ordering between snapshot capture and where delta reading begins; otherwise boundary changes can be missed.

A practical design records the change stream position before starting the snapshot, exports the snapshot, and then replays events from that position. Because the snapshot might already reflect some changes occurring after the watermark, the sink must handle upserts/deletes by version or event order so stale states never overwrite newer data. Exact mechanics depend on your source system's CDC capabilities.

### 10.2. Using `updated_at` as a Watermark

If no CDC exists, you can run a delta scan using an `updated_at` field:

```json
GET /orders/_search
{
  "query": {
    "range": {
      "updated_at": {
        "gte": "2026-11-13T10:00:00Z",
        "lt": "2026-11-13T11:00:00Z"
      }
    }
  }
}
```

However, `updated_at` is trustworthy only if updated consistently with adequate precision. Account for:

- Clock skew across services.
- Multiple updates sharing the same timestamp.
- Delayed refreshes causing a change to appear only in a later delta scan.
- Deleted documents disappearing from normal searches so delta scans cannot observe deletions.
- A single document updated multiple times within the scan window.

To lower risk, use an overlap window: start the next scan slightly earlier than the saved watermark, then upsert by stable ID so re-reads do not duplicate records. For deletes, maintain tombstones or a dedicated change log. When zero missed changes are permitted, CDC/outbox patterns are far more reliable than timestamps alone.

### 10.3. Using Immutable Indices or Time-Based Partitions

For append-only data, organize indices by day, week, or batch. Exporting closed, read-only partitions is simpler because the dataset stops mutating.

For example:

```text
events-2026-11-10  (closed, read-only)
events-2026-11-11  (closed, read-only)
events-2026-11-12  (actively receiving writes)
```

Closed indices can be exported via snapshot search while the active index is handled by a separate delta flow. Ensure writers never write back into an older index once its partition is considered finalized.

## 11. Consistency of Export Files and Sinks

A consistent read does not automatically produce a consistent export file. For example, a job may read 50 batches and fail writing batch 51. On rerun, creating a new file while retaining partial old output can introduce duplicate documents.

Design the sink using one of these patterns:

- Write to a temporary file and rename/publish only once the entire export succeeds.
- Write each batch to a numbered object with a checksum, then write a manifest on completion.
- Upsert to the destination by stable ID so retries create no duplicates.
- Persist per-batch checkpoints committed strictly after durable sink writes.
- Emit tombstones for deleted documents if deletion state must sync.

If an export must resume after a process crash, remember that scroll/PIT contexts can expire or vanish when the cluster changes. Never treat scroll IDs or PIT IDs as long-lived durable checkpoints. For multi-hour jobs needing crash recovery, combine snapshot versions, change logs, and idempotent sinks so a fresh scan can restart cleanly.

### 11.1. At-Least-Once and Exactly-Once

Scroll/PIT governs what the reader observes; it does not deliver exactly-once semantics between Elasticsearch and the destination system.

- **At-most-once:** records can be lost if checkpoints are saved before the sink confirms success.
- **At-least-once:** batch retries may write the same records more than once; the sink must be idempotent.
- **Exactly-once effect:** usually requires stable IDs, upsert/version checks, transactions, or sink deduplication. Scroll IDs alone cannot provide this guarantee.

The safe ordering is to write the batch successfully first, then update the checkpoint. If the process dies between those two steps, the batch is replayed and the idempotent sink handles duplicates.

## 12. Data Cutoffs and Consistency Requirements by Scenario

| Requirement | Approach | Limit to understand |
|---|---|---|
| Export data as of start time | Scroll or `PIT + search_after`. | Excludes inserts/updates after snapshot mark. |
| Scan millions of documents in batches without business sort | Scroll, `_doc` sort. | Must maintain and close scroll context. |
| Deep traversal with stable sort | `PIT + search_after`. | PIT expires; always use latest PIT ID. |
| Near-current scan tolerating shifts across pages | `search_after` without PIT, or offset pagination. | May duplicate/skip when data or sort values change. |
| Export must include changes during job run | Snapshot + CDC/change log or delta pass. | Must handle watermarks and update ordering. |
| Append-only data, closed historical partitions | Export closed partitions. | Ensure no late writes hit closed partitions. |
| Full index backup/restore | Snapshot and Restore API. | Do not substitute by scanning documents via Scroll. |
| Job must resume after long pauses or node restarts | Snapshot version + durable change log + idempotent sink. | Scroll/PIT contexts are not long-term checkpoints. |

## 13. Testing Data Mutations During Scans

Write integration tests verifying both snapshot and live search semantics explicitly. Use real Elasticsearch or Testcontainers with a compatible version; mock repositories cannot verify search contexts or refresh behavior.

### 13.1. Testing Scroll Snapshots

Test scenario:

1. Index documents A, B, C and refresh.
2. Open a scroll with batch size 1 or 2.
3. Read the first batch.
4. Insert document D and refresh.
5. Update B and refresh.
6. Delete C and refresh.
7. Continue reading remaining scroll batches.
8. Assert the scan still reflects the initial snapshot per the search context.
9. Run a fresh non-scroll search to confirm the mutated state is searchable.
10. Clear the scroll context.

### 13.2. Testing PIT + `search_after`

Repeat the scenario above with PIT:

1. Index initial data and refresh.
2. Open a PIT.
3. Fetch the first page and save the last hit's sort values.
4. Perform inserts, updates, and deletes, then refresh.
5. Send the next request with the latest PIT ID and `search_after`.
6. Assert pages remain bound to the opened snapshot.
7. Close the PIT.

### 13.3. Testing `search_after` Without PIT

Run the same scenario without opening a PIT. Insert a document whose sort value precedes the cursor, alter the sort value of an unread document, and delete another document. Verify that results can shift between requests; design the test to demonstrate non-snapshot behavior without pinning brittle timing-dependent ordering.

### 13.4. Testing Export Failures

Simulate a sink failure between two batches:

- Verify the context is closed when the job halts.
- Verify the checkpoint is saved only after a batch writes successfully.
- Rerun the batch and confirm an idempotent sink produces no duplicates.
- Verify temporary files are not published as complete outputs.

Avoid `Thread.sleep` to wait for refreshes in tests. Use the refresh API or proper test configuration so searchable timing is deterministic.

## 14. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Export drops documents during concurrent inserts | Scanning with independent searches; new document lands ahead of cursor/offset. | Use Scroll/PIT for snapshots or run a separate delta pass. |
| Same document appears twice | Shifted offset, altered sort value, or non-idempotent sink retry. | Use snapshots, stable sorts, and ID-based deduplication/upserts. |
| Deleted document still appears in export | Scroll/PIT retains the initial snapshot version. | Process deletes via post-snapshot delta/tombstones if latest state is needed. |
| Updated document lacks new values in export | Snapshot opened before update/refresh. | Run a delta pass after snapshot or align export cutoff timing. |
| `search_after` skips documents | Sort value changed or new document inserted ahead of cursor. | Combine with PIT and stable sort. |
| Scroll request expires | Client paused too long or keep-alive too short. | Renew context steadily, shorten batch processing, or restart export. |
| Cluster retains many old segments | Scroll/PIT contexts left open too long or leaked. | Close contexts promptly, limit concurrent exports, and size keep-alive prudently. |
| Export cannot resume after restart | Scroll/PIT ID expired or context vanished. | Build restartable exports with fresh snapshots, watermarks/change logs, and idempotent sinks. |
| Count and export totals mismatch | Snapshot and count ran at different times. | Run counts within the same snapshot or explicitly document cutoff differences. |
| Assuming PIT locks new writes | Confusing search snapshots with database locks/transactions. | Writes remain allowed; PIT only preserves a read view. |

## 15. Workflow for Selecting and Operating an Export

1. **Define the data cutoff:** export as of start time, a fixed cutoff, or include changes until completion.
2. **Choose the mechanism:** Scroll for simple batch scans; `PIT + search_after` for stable cursors/sorts; CDC/delta when concurrent changes must be captured.
3. **Prepare data:** confirm required writes are refreshed before opening the context.
4. **Pick batch size:** large enough to limit overhead without inflating heap or per-batch latency.
5. **Choose sort:** `_doc` for unordered scroll exports; field sort with tie-breaker when deterministic order is needed.
6. **Manage contexts:** set sensible keep-alives, cap concurrent exports, and always close Scroll/PIT.
7. **Write safely to sink:** write in batches using stable IDs, idempotent retries, and post-commit checkpoints.
8. **Sync deltas:** if latest state is required, replay CDC/change logs or watermarked delta scans post-snapshot.
9. **Reconcile:** compare counts at the same data cutoff, inspect batch errors, and verify manifest/export completion.
10. **Clean up:** close contexts, remove temporary files, and record export metadata.

## 16. Key Takeaways

- Data can change between paginated requests; `from/size` and `search_after` without PIT do not guarantee a stable snapshot.
- Scroll preserves a search context from the initial search; later inserts, updates, and deletes do not alter the running scroll's view.
- PIT maintains a stable view across multiple search requests and is commonly combined with `search_after`.
- Scroll/PIT reflects data already searchable when the context opened; unrefreshed writes may not yet appear in the snapshot.
- Post-snapshot documents are excluded from the scan; documents updated or deleted post-snapshot may still be read in their initial versions.
- Scroll IDs and PIT IDs are temporary state; use the latest ID from responses and close contexts when finished.
- `keep_alive` is how long the context must stay alive between requests, not the maximum duration of the entire export.
- Sorting requires deterministic ordering; PIT can use `_shard_doc` as a tie-breaker, while non-PIT searches need a stable tie-breaker field.
- Spring Data Elasticsearch's `searchForStream` enables iterator-based scrolling; always close the iterator using `try-with-resources`.
- Search snapshots are not ACID transactions, do not lock writes, and do not replace the Snapshot and Restore API.
- To capture changes occurring mid-export, use delta passes, CDC/outbox, watermarks, or immutable data models.
- Scroll/PIT does not guarantee exactly-once delivery to sinks; use stable IDs, idempotency, and properly ordered checkpoints.

When data continues changing during a scan, the essential step is defining exactly which state the export must represent. Use Scroll or PIT for a stable read view, pair `search_after` with PIT for ordered cursors, and add change logs or delta passes when post-snapshot updates must be captured. Design the reader, sink, and checkpoints together to prevent lost or duplicated records.

## References

- [Elasticsearch — Scroll search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html#scroll-search-results)
- [Elasticsearch — Point in Time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Elasticsearch — Search after](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html#search-after)
- [Spring Data Elasticsearch — Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
