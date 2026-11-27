# Distinguishing Refresh from Flush and Data Durability

In Elasticsearch, a document can be written successfully without appearing in search results immediately. This does not necessarily mean the data is lost. Elasticsearch separates making data **searchable** from persisting data **durably for crash recovery**.

Three concepts must be distinguished:

- **Refresh:** opens a new searcher so recent changes become visible through the Search API. This is the mechanism that provides near real-time (NRT) consistency.
- **Flush:** performs a Lucene commit and starts a new translog generation. It completes index commits and manages the translog; Elasticsearch usually performs it automatically when needed.
- **Durability:** the ability to retain acknowledged operations after a node or process failure. Elasticsearch relies on the transaction log (translog), disk syncing, and replication to support this goal.

Refresh is not flush. Nor is flush a backup mechanism. A refresh makes data searchable without by itself creating a durability guarantee; a flush creates a Lucene commit without replacing snapshot and recovery policies.

## 1. Why does a write succeed while Search does not see the document?

Elasticsearch is optimized for high-throughput searching and writing. Rather than creating a Lucene commit for every single write operation, Elasticsearch batches changes and periodically refreshes to open a new searcher.

Example:

1. The application sends a request to index a product.
2. Elasticsearch processes the write and records the necessary information in the translog.
3. The request returns success.
4. The current searcher may still be reading an older snapshot.
5. After the next refresh, the new document appears in Search API results.

As a result, the following situation can occur:

- `GET /products/_doc/42` reads the document by ID and sees the new data.
- `GET /products/_search` does not find the document yet because the shard has not refreshed.

The Get API by ID is real-time by default, whereas the Search API is near real-time. The two APIs have different semantics; do not use an immediate Search result after a write as the sole way to determine whether the write request succeeded.

## 2. What is refresh?

Refresh makes processed changes in an index visible to subsequent search requests. At the Lucene level, a refresh opens a new searcher over the segments created from the new data.

Refresh does not require creating a full Lucene commit every time. It is an operation to refresh the search view, designed to occur much more frequently than commits.

General flow:

~~~text
Index / update / delete request
             |
             v
       Write changes
             |
             v
    Translog + indexing buffer
             |
             v
          Refresh
             |
             v
      Open new searcher
             |
             v
  Search sees the new document
~~~

Refresh primarily addresses visibility (making data visible through the Search API), not the durability boundary.

### 2.1. Refresh interval

An index has the `index.refresh_interval` setting to define the automatic refresh cycle. The default value is typically `1s` in standard configurations, though actual behavior depends on the version and index activity state.

Do not treat the refresh interval as a guarantee that every document will appear after exactly one second. Actual timing also depends on cluster load, shard activity, and whether refreshes are triggered. Elasticsearch also optimizes indices that have not been searched recently, so idle indices may not refresh continuously in the background like actively searched indices.

You can read the setting:

~~~http
GET /products/_settings?filter_path=*.settings.index.refresh_interval
~~~

Set a longer interval:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "5s"
  }
}
~~~

A longer interval can improve indexing efficiency by reducing refreshes, but Search results will lag more. Choose a value based on your application's freshness requirements and actual load.

### 2.2. Manual refresh

You can trigger a refresh on an index:

~~~http
POST /products/_refresh
~~~

Once the API completes, processed changes on the affected shards become visible through the Search API.

Manual refresh is useful in:

- Integration tests that need to verify Search immediately after writing.
- Import pipelines with a clear end point.
- Administrative tasks that need to actively refresh visibility.

Do not call refresh after every document in normal write flows. Refreshing too often creates many small segments, increases merge overhead, and lowers indexing throughput.

## 3. Refresh values in write APIs

Many Elasticsearch write APIs support the `refresh` parameter with three main values:

| Value | Behavior | When to consider |
|---|---|---|
| `false` | Do not request a separate refresh for the request; rely on automatic refresh | Default for most write flows |
| `true` | Immediately refresh affected shards so changes are visible to Search when the request finishes | Use only when immediate visibility is truly required |
| `wait_for` | Wait for the next refresh to make the request's changes visible without forcing an immediate refresh | Read-after-write needing visibility while avoiding per-request refreshes |

Example of immediate refresh:

~~~http
PUT /products/_doc/42?refresh=true
Content-Type: application/json

{
  "name": "Keyboard",
  "status": "ACTIVE"
}
~~~

Example of waiting for the next refresh:

~~~http
PUT /products/_doc/43?refresh=wait_for
Content-Type: application/json

{
  "name": "Mouse",
  "status": "ACTIVE"
}
~~~

`refresh=wait_for` is usually a better choice when the caller must find the data right after writing without forcing a new refresh per request. The request completes only after an appropriate refresh occurs.

If automatic refresh is disabled via `index.refresh_interval: -1`, a `wait_for` request may have to wait until a manual refresh or another mechanism makes the data visible. Do not disable refresh and expect `wait_for` to refresh the index on its own.

### 3.1. Impact of refresh=true

`refresh=true` can trigger immediate refreshes on affected shards. If an application sends many individual write requests with this option, the cluster must refresh continuously, which can:

- Increase the number of small segments.
- Increase merge work.
- Increase CPU and I/O.
- Reduce indexing throughput.
- Cause higher latency for other requests.

When writing many documents, prefer batching via the Bulk API and choosing an appropriate refresh policy for the whole batch. Avoid refreshing per item.

### 3.2. Refresh listeners and wait_for

`wait_for` needs to register to wait for a refresh. If too many requests wait simultaneously while refreshes are delayed or disabled, the listener count can grow and hit the shard's configured limit.

Therefore:

- Do not use `wait_for` indiscriminately on very high-traffic workloads without measuring.
- Ensure a suitable refresh interval.
- Do not keep refresh disabled while requests are waiting on visibility.
- Monitor timeouts and errors related to refresh listeners.
- Use batching if multiple documents belong to the same write process.

## 4. What is flush?

A flush in Elasticsearch performs a Lucene commit and starts a new translog generation. Once the commit completes, operations already written to the Lucene index can be managed independently of the old translog generation, allowing Elasticsearch to trim translog files no longer needed for recovery.

General flow:

~~~text
Index / update / delete
          |
          v
       Translog
          |
          v
    Refresh (if needed)
          |
          v
      Lucene segments
          |
          v
         Flush
          |
          +----> Lucene commit
          |
          +----> New translog generation
          |
          v
 Old translog can be trimmed safely
~~~

Flush is a commit and translog management step, not a way to force the Search API to see data. Refresh and flush serve separate purposes.

### 4.1. Flush API

You can request an index flush:

~~~http
POST /products/_flush
~~~

Elasticsearch usually flushes automatically based on internal thresholds and conditions. In normal applications, you rarely need to call flush manually after writes.

Manual flush can be helpful in certain special operational workflows, but it should not be used as periodic cleanup in business services. Let Elasticsearch manage flushes automatically unless there is a measured and verified operational requirement.

### 4.2. Flush is not the same as refresh

| Criterion | Refresh | Flush |
|---|---|---|
| Goal | Make changes visible via the Search API | Lucene commit and roll translog generation |
| Frequency | More frequent, per refresh interval or request | Less frequent, managed automatically by Elasticsearch |
| Primary effect | Search visibility | Commit and translog/recovery lifecycle |
| Is it a backup? | No | No |
| Call after every document? | Usually shouldn't | Shouldn't |

A flush operation is not a substitute for `refresh=wait_for`. If the goal is to write and then immediately see results in Search, use an appropriate refresh policy.

### 4.3. Flush is not force merge

Flush also differs from force merge:

- Flush creates a Lucene commit and a new translog generation.
- Force merge merges Lucene segments to reduce segment count, typically used for indices that rarely change or have finished receiving writes.

Do not run force merge after every flush. Force merge can generate heavy I/O and CPU load, and it is not a prerequisite for data searchability or durability.

## 5. Translog and data durability

The translog (transaction log) records Elasticsearch write operations. It enables recovery of changes not yet persisted in a completed Lucene commit when a node restarts after a failure.

One way to picture this:

- Lucene index segments serve searches.
- Translog holds write operation records needed for recovery.
- Refresh makes searchers see new data.
- Flush creates a commit and switches the translog generation.

The translog is a key part of durability. A document might not yet be visible in Search while the write operation has already been durably recorded in the translog according to the index's durability policy.

### 5.1. index.translog.durability

Elasticsearch has the `index.translog.durability` setting with two common modes:

| Mode | Behavior |
|---|---|
| `request` | Syncs the translog to storage before acknowledging the write request as successful |
| `async` | Syncs periodically according to `index.translog.sync_interval`, leaving a window where acknowledged operations may not yet be fsynced |

`request` is the default in standard configurations and fits when durability is a priority. `async` can improve write performance in some workloads, but accepts the risk of losing operations since the last sync if a node or machine crashes severely.

Check the setting:

~~~http
GET /products/_settings?filter_path=*.settings.index.translog
~~~

Example configuring request durability:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "translog": {
      "durability": "request"
    }
  }
}
~~~

If choosing async, understand `sync_interval`, acceptable data loss bounds, and the types of failures the system must tolerate. Do not change this setting just to boost benchmark numbers without evaluating data impact.

### 5.2. fsync and write acknowledgement

With `request`, Elasticsearch syncs the translog to storage according to policy before returning acknowledgement for a write request. This protects operations against abrupt process or node stops, provided the storage and infrastructure honor flush/fsync guarantees.

End-to-end durability also depends on:

- Storage quality and configuration.
- Filesystem and storage hardware health.
- Replication and shard recovery capability.
- Active shard copies configuration during writes.
- Backup and snapshot procedures.

Do not interpret an HTTP 200 as an absolute guarantee against all hardware failures, total cluster loss, or operational mistakes. Design replication, snapshots, and restore procedures as well.

## 6. Refresh, flush, and translog within the same lifecycle

An overview sequence of events:

~~~text
1. Client sends index/update/delete
          |
          v
2. Elasticsearch processes operation and writes translog
          |
          v
3. Under durability=request, syncs translog
          |
          v
4. Write response is returned
          |
          +---------------------------+
          |                           |
          v                           v
5a. Refresh                     5b. Flush
    opens new searcher              Lucene commit
    Search sees data                new translog generation
          |                           |
          v                           v
   Visibility changes           Recovery log managed
~~~

Refresh and flush can occur at different times. Do not assume every refresh triggers a flush or that a flush is invoked to satisfy a search request.

## 7. Read-after-write in applications

Some business flows need to write and read immediately afterward, for example:

- Creating a product and navigating to a details page that uses the Search API.
- Updating an order status and immediately executing a search query.
- Importing data and verifying it via aggregations.

First, identify the read path:

- If reading by ID with the Get API, the get operation is real-time by default and can usually see new writes without a refresh.
- If reading with the Search API, wait for a refresh to make changes visible.
- If you only need to return the result of the write operation, use the write response instead of re-querying Elasticsearch.

### 7.1. Using refresh=wait_for

Example of a write that Search must see right after the request finishes:

~~~http
POST /products/_update/42?refresh=wait_for
Content-Type: application/json

{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

Once the request completes, an appropriate refresh has happened so the update is visible in Search. This is useful for read-after-write via Search when avoiding forcing an immediate refresh per request.

Do not add `refresh=wait_for` to every write operation if callers do not need immediate Search visibility. Making every request wait for a refresh can increase application latency.

### 7.2. Using GET when the document ID is known

If you only need to confirm the newly written document, use the Get API:

~~~http
GET /products/_doc/42
~~~

The Get API by ID is real-time by default. This is usually preferable to forcing a full-index refresh just to inspect one specific document.

### 7.3. Do not use flush for read-after-write

Flush is not a visibility policy. If a test or service calls flush expecting Search to see the document immediately, the design confuses commit/translog management with refresh. Use refresh or `refresh=wait_for` according to read needs.

## 8. Integrating refresh policy in Spring Data Elasticsearch

Spring Data Elasticsearch provides abstractions for working with refresh. Exact package names and configuration details depend on the release train in use, but the semantics match Elasticsearch's policies.

### 8.1. Manual refresh via IndexOperations

In integration tests or administrative workflows that need Search to see written data, you can call refresh on the index:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
~~~

With an entity declaring an index mapping, you can obtain index operations from the entity class:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Product.class);

indexOperations.refresh();
~~~

Only call this when clearly needed. Do not place refresh calls inside every save in normal services.

### 8.2. RefreshPolicy for bulk operations

When sending multiple `IndexQuery` instances via the bulk API, you can specify a refresh policy in bulk options. Illustrative example:

~~~java
BulkOptions bulkOptions = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        bulkOptions,
        IndexCoordinates.of("products")
);
~~~

`BulkOptions` types, the `RefreshPolicy` enum, and builder method names can differ across release trains. Check the API of your project's dependency. The meanings to preserve are:

- `NONE`: request no separate refresh; follow normal refresh schedule.
- `IMMEDIATE`: request immediate refresh after the operation.
- `WAIT_UNTIL`: wait for the next refresh to make changes visible.

For large bulk imports, usually avoid IMMEDIATE for each small batch if immediate visibility is not required. You can write batches with the default policy and then refresh once after the import finishes if the business flow needs Search to see all data.

### 8.3. Flush from Spring Data or the client

Flush is an index/translog administration operation and typically does not belong in a repository's normal save path. If an operational workflow genuinely needs to invoke the Flush API, use the Elasticsearch Java Client or index operations API supported by your Spring Data version, and document the operational reason clearly.

Do not add flush after every `save()` or `bulkIndex()`. Elasticsearch manages flushes automatically according to internal thresholds and conditions; calling it manually all the time can hurt performance without improving read-after-write.

## 9. Bulk indexing and refresh interval

When importing large volumes of documents, frequent refreshes can reduce throughput. A common strategy is temporarily increasing the refresh interval or disabling automatic refresh during a controlled write window, then re-enabling it and refreshing once.

Example workflow:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Run bulk indexing in batches:

~~~http
POST /products/_bulk
Content-Type: application/x-ndjson

{"index":{"_id":"p-1"}}
{"name":"Keyboard","status":"ACTIVE"}
{"index":{"_id":"p-2"}}
{"name":"Mouse","status":"ACTIVE"}
~~~

After writing finishes, restore the refresh interval:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

Then trigger a refresh if Search needs to see the data immediately:

~~~http
POST /products/_refresh
~~~

### 9.1. Risks of disabling refresh

When `refresh_interval` is `-1`:

- Search does not see new documents until a refresh runs.
- `refresh=wait_for` requests may block waiting.
- An import process that fails mid-way can leave the index with refreshes disabled.
- Operators might forget to restore the setting.

Therefore, if using this strategy, manage it as a stateful workflow:

1. Record the current setting.
2. Temporarily disable or increase the interval.
3. Execute batch imports.
4. Check bulk responses and failed document counts.
5. Restore the setting in both success and failure paths.
6. Refresh once when needed.
7. Verify Search visibility.

Do not disable refresh if the system serves live queries requiring continuous fresh data without a dedicated import window.

### 9.2. Disabling refresh does not disable durability

Refresh interval and translog durability are two different settings. Disabling refresh does not automatically disable translog fsync. If `index.translog.durability` remains `request`, write requests still follow the corresponding translog sync policy.

Do not trade away durability just to speed up imports if business requirements do not allow losing acknowledged data. Optimize batch size, concurrency, refresh interval, and workload before considering async durability.

## 10. Replication, durability, and backup

Three concepts must also be kept distinct:

- **Translog durability:** protects writes for recovery after a node crash according to the sync policy.
- **Replication:** maintains shard copies to increase availability and recover when a node/shard fails.
- **Snapshot:** creates backups that can restore data after major failures, accidental deletions, or cluster loss.

A replica is not a backup. If a document is accidentally deleted or corrupted data is replicated, the replica can reflect that change too. Snapshots are the backup mechanism requiring a schedule, retention policy, and tested restore procedures.

### 10.1. wait_for_active_shards

Write APIs can accept `wait_for_active_shards` to require a minimum number of active shard copies before starting the write operation. This setting relates to availability and replication readiness, not refresh.

Example:

~~~http
PUT /products/_doc/42?wait_for_active_shards=all
Content-Type: application/json

{
  "name": "Keyboard"
}
~~~

Requiring `all` can cause requests to wait if a replica is down. It does not mean the document is immediately visible via Search; refresh remains a separate visibility mechanism.

Do not treat `wait_for_active_shards=all` as a replacement for snapshots or a guarantee against every failure. Choose the required active shard copy count based on SLA and cluster topology.

## 11. Common scenarios

| Scenario | Appropriate mechanism |
|---|---|
| After save, Search can see it after automatic refresh | Default refresh |
| After save, caller must see it in Search before returning | `refresh=wait_for` |
| Test writes then immediately queries Search | `IndexOperations.refresh()` or `wait_for` |
| Read back document by ID | Real-time Get API |
| Import millions of documents | Bulk, adjust refresh interval, refresh upon completion |
| Commit and rotate translog generation | Flush, usually left to Elasticsearch to manage |
| Protect acknowledged writes after node crash | Translog durability |
| Recover from accidental deletion or cluster loss | Snapshot and restore |
| Wait for enough shard copies before writing | `wait_for_active_shards` |

## 12. Testing refresh and durability

Integration tests should separate visibility from durability rather than using a single refresh call to test everything.

### 12.1. Testing Search visibility

A test can perform:

1. Index a document with default refresh.
2. Use the Get API by ID to verify the document was written.
3. Search by a field to observe the state before refresh.
4. Call `IndexOperations.refresh()` or write with `WAIT_UNTIL`.
5. Search again and verify the document appears.

Pseudocode example:

~~~java
operations.save(product);

// Get by ID can see the document before refresh.
Product loaded = operations.get(product.getId(), Product.class);

// Search visibility requires refresh.
operations.indexOps(Product.class).refresh();

SearchHits<Product> hits = operations.search(
        query,
        Product.class
);
~~~

Exact results depend on refresh timing, so do not write tests asserting Search must always miss the document immediately after a default write. A background refresh might run before the assertion executes. Instead, test deterministically using refresh policies or manual refreshes.

### 12.2. Testing wait_for

Send a write with `WAIT_UNTIL`, wait for the request to finish, and then Search. The test confirms the caller can read via Search after the write returns.

If the refresh interval is disabled, the test needs to trigger a refresh or restore the interval; otherwise `wait_for` may block longer than expected.

### 12.3. Testing flush

Do not use Search seeing a document after flush as proof that flush is a refresh mechanism. Test flush as a separate index/translog operation if operational tooling genuinely requires it. For most business services, there is no need to write tests calling flush after every write.

### 12.4. Testing durability

Durability cannot be proven by a unit test alone or by calling refresh. Durability must be evaluated at the integration/chaos or operational level:

- Verify translog durability settings.
- Verify write responses under the `request` policy.
- Test shard recovery after controlled restarts in a staging/test environment.
- Verify replication and active shard copies.
- Test snapshot/restore procedures.
- Document storage and infrastructure limitations.

Do not crash production nodes to test durability. Use a staging environment and controlled failure scenarios.

## 13. Common mistakes

### 13.1. Confusing refresh with flush

Refresh makes data visible via Search; flush performs a Lucene commit and starts a new translog generation. Choose the API matching the actual goal.

### 13.2. Calling refresh after every save

Continuous refreshes create small segments and raise merge costs. Use the default or `wait_for` when read-after-write is needed.

### 13.3. Calling flush to force Search to see data

Flush is not a read-after-write mechanism. Use refresh or a refresh policy.

### 13.4. Assuming a successful write response means Search sees it right away

Write acknowledgement and Search visibility occur at different times. Search requires refresh; Get by ID has real-time semantics.

### 13.5. Assuming refresh guarantees durability

Refresh does not substitute for translog fsync or Lucene commits. Understand your translog durability configuration.

### 13.6. Thinking flush is a backup

Flush does not create backups capable of restoring a deleted index or lost cluster. Use snapshots.

### 13.7. Disabling refresh and forgetting to re-enable it

The index may fail to update Search visibility as expected. Record old settings and restore them in a cleanup step.

### 13.8. Using wait_for while refresh is disabled

Requests can wait until a refresh occurs. Restore the refresh interval or refresh explicitly in the workflow.

### 13.9. Using async durability without accepting the risk

Operations acknowledged since the last sync can be lost in certain crashes. Only choose async when business requirements allow it and the trade-off has been assessed.

## 14. Policy selection process

When designing read and write flows:

1. Determine whether callers read via the Get API or Search API.
2. If immediate Search visibility is unnecessary, keep the default refresh.
3. If Search visibility is required before returning a response, consider `refresh=wait_for`.
4. Only use `refresh=true` when forcing an immediate refresh is genuinely necessary and its cost is understood.
5. For bulk imports, adjust the refresh interval for the write window and restore the setting afterward.
6. Do not use flush as a mandatory step after each write.
7. Choose translog durability based on acceptable data-loss tolerance.
8. Design replication, active shard copies, and snapshots separately for availability/backup.
9. Test Search visibility and durability as two distinct properties.
10. Monitor refreshes, merges, translog, indexing latency, and task failures on the cluster.

## 15. Conclusion

Refresh makes changes visible through the Search API by opening a new searcher. Flush performs a Lucene commit and rotates the translog generation to manage committed data and translog lifecycle. The two operations serve different purposes and are usually managed automatically by Elasticsearch.

Write durability depends on the translog and sync policy. With `index.translog.durability=request`, Elasticsearch syncs the translog per write request before acknowledging; `async` mode syncs periodically and accepts a window of potential operation loss on crashes. Refresh is not durability, flush is not backup, and replicas do not replace snapshots.

In Spring Data Elasticsearch, use `IndexOperations.refresh()` or an appropriate refresh policy when Search visibility is needed. For normal write paths, keep the default refresh; for read-after-write via Search, consider `WAIT_UNTIL`; for bulk imports, adjust the refresh interval in a controlled manner. Select policies according to how the application reads data, latency requirements, and the durability level the business requires.
