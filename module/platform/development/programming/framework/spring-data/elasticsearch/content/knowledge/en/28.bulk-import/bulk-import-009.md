# Refresh Policies During Data Ingestion and Speed Trade-offs

Elasticsearch is a near-real-time (NRT) search engine: a document that has been written successfully will not necessarily appear immediately in `_search` results. A document only becomes visible to search after the shard refreshes. Therefore, when ingesting data via the Index API or Bulk API, the application must choose a refresh timing that balances search freshness against write throughput.

A refresh policy decides whether a write request requests an immediate refresh, waits for the next scheduled refresh, or lets Elasticsearch refresh on its normal schedule. The three common options are `false`, `true`, and `wait_for`. Additionally, `index.refresh_interval` can be adjusted to change how frequently an index refreshes, especially during large bulk loads.

The right choice depends on how the application reads data after writing:

- If users need to find a document immediately after each write, prefer `refresh=wait_for` or `refresh=true` at the specific point requiring read-after-write.
- For continuous high-throughput ingestion, leave the default refresh behavior or raise the interval.
- When loading millions of documents into a new index, temporarily disable periodic refresh, load via bulk, and refresh once upon completion.

## 1. What Is Refresh?

Elasticsearch stores data in Lucene indices. When a document is indexed or updated, the change is recorded in internal buffers and the translog, yet the active searcher cannot see it yet. A refresh opens new segments so they become searchable.

```text
Application sends index/bulk request
             |
             v
Elasticsearch writes change
             |
             +----> Real-time GET can read the new document
             |
             v
       Not yet refreshed
             |
             +----> _search may not see the document yet
             |
             v
          Refresh
             |
             v
        New searcher
             |
             v
        _search sees the data
```

Refresh is the operation that makes written data visible to search. It is not the same as a flush, force merge, or business commit.

### Near-Real-Time vs. Real-Time

Elasticsearch provides real-time GET by ID by default: a newly written document can usually be fetched via GET even before the next refresh. Search relies on Lucene searchers, so it only sees changes after a refresh.

Example:

```http
PUT /products/_doc/p-100
Content-Type: application/json

{
  "name": "Wireless Headphones"
}
```

Right after the write request succeeds, the following call can retrieve the document:

```http
GET /products/_doc/p-100
```

However, a search query:

```http
POST /products/_search
{
  "query": {
    "term": {
      "_id": "p-100"
    }
  }
}
```

may not see the document until the shard refreshes.

## 2. Default Refresh Interval

`index.refresh_interval` controls how often an index refreshes automatically. A common default is `1s` for indices actively receiving searches. Elasticsearch may optimize refreshes for indices with no search activity for a period of time; when configuring a workload, inspect the actual setting rather than assuming every index refreshes strictly every second.

Checking the setting:

```http
GET /products/_settings?include_defaults=true&filter_path=*.settings.index.refresh_interval,*.defaults.index.refresh_interval
```

Example setting the interval to 5 seconds:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "5s"
  }
}
```

A larger value lowers refresh frequency and generally improves indexing throughput, while increasing the delay before documents appear in search. A smaller value surfaces new data faster, yet creates more small segments and increases merge work.

### Common Values

| Value | Behavior | Use Case |
|---|---|---|
| `1s` | Frequent refreshes, low search latency | Near-real-time search for interactive applications |
| `5s` or `10s` | Less frequent refreshes | Continuous ingestion tolerating a few seconds of lag |
| `30s` | Further reduces refresh overhead | Systems prioritizing throughput over instant freshness |
| `-1` | Disables periodic refresh | Large bulk loads or controlled batch-import phases |

These values are examples for selection and measurement, not rigid rules for every index.

## 3. Three Refresh Values for Write Requests

The Index API, Update API, and Bulk API support the `refresh` parameter with three main choices:

| Value | Meaning | Trade-off |
|---|---|---|
| `false` | Do not request a refresh from this request; rely on scheduled refresh | Higher throughput; search may see data with a delay |
| `true` | Request an immediate refresh of the shards affected by the request | Faster read-after-write via search; higher refresh cost |
| `wait_for` | Wait for the next refresh to make changes visible to search | Does not force an immediate refresh; often balances visibility and throughput better |

`false` is the default when the parameter is omitted. It does not disable automatic index refreshes; it only means the write request itself does not demand an immediate refresh.

## 4. `refresh=false`: Let Elasticsearch Refresh on Schedule

Example:

```http
POST /products/_doc/p-101?refresh=false
Content-Type: application/json

{
  "name": "Mechanical Keyboard"
}
```

The request writes the document and returns without waiting for search visibility. When the next automatic refresh runs, the document appears in search.

This is usually the right choice for:

- Continuous ingestion with many documents.
- Bulk imports that do not require search to see each batch immediately.
- Event streams or log indexing.
- Pipelines where consumers read data after an acceptable lag.

Do not pass `refresh=true` after every single document just to guarantee instant search visibility unless business requirements genuinely demand such low latency.

## 5. `refresh=true`: Refresh Immediately After the Request

Example with the Index API:

```http
PUT /products/_doc/p-102?refresh=true
Content-Type: application/json

{
  "name": "USB-C Hub"
}
```

Once the request completes, the affected shards are refreshed so changes become visible to search.

With the Bulk API:

```http
POST /products/_bulk?refresh=true
Content-Type: application/x-ndjson

{ "index": { "_id": "p-103" } }
{ "name": "Monitor Stand" }
{ "index": { "_id": "p-104" } }
{ "name": "Laptop Sleeve" }
```

This bulk request executes multiple actions and requests a refresh afterward. The refresh applies to the shards touched by the request; it does not refresh every shard across the entire cluster.

### Why Does `refresh=true` Reduce Throughput?

Refreshing creates new searchers/segments and generates segment-management overhead. If an application sends many small requests with `refresh=true`, each request can trigger another refresh. Common consequences:

- More small segments.
- Higher segment merge overhead.
- Increased CPU and I/O.
- Lower indexing throughput.
- Higher latency for other search or write requests when the cluster is under load.

If you need to write 10,000 documents, a single bulk request followed by a refresh at the end is usually far more efficient than 10,000 individual requests each requesting a refresh.

## 6. `refresh=wait_for`: Wait for Data to Become Searchable

`wait_for` instructs the write request to wait until a refresh makes its changes visible to search. Unlike `true`, it does not proactively force an immediate refresh; the request can be satisfied by the next periodic refresh or a refresh triggered by another request.

Example:

```http
PUT /products/_doc/p-105?refresh=wait_for
Content-Type: application/json

{
  "name": "Wireless Mouse"
}
```

Once the request returns successfully, the document has been refreshed and can be found via search.

### When Should You Use `wait_for`?

- A write operation must immediately run a search afterward to render a results page.
- A user just created data and the UI needs to search for that data right after the write API returns.
- You want to wait for visibility without forcing an immediate refresh on every request.

### `wait_for` Still Has Latency

If the refresh interval is 1 second, the request may wait up to nearly one refresh cycle depending on timing. If the index is busy or refreshes are slow, the wait can be longer.

### Caution When Periodic Refresh Is Disabled

If `index.refresh_interval` is set to `-1`, periodic refresh is off. Requests using `refresh=wait_for` may block until some other refresh is triggered, such as a manual refresh. Do not use `wait_for` while periodic refresh is disabled unless the application actively triggers a refresh.

## 7. Comparing `true` and `wait_for`

| Criterion | `refresh=true` | `refresh=wait_for` |
|---|---|---|
| Guarantees visibility when request completes? | Yes | Yes |
| Proactively forces a refresh? | Yes | No, waits for next refresh |
| Can piggyback on periodic refresh? | Usually skips waiting for the next cycle | Yes |
| Dedicated refresh cost per request | Can trigger an immediate refresh | Can batch with periodic or other requests' refreshes |
| Request latency | Can rise due to refresh work | Can rise due to waiting |
| Best suited for | Intentional immediate refresh | Read-after-write via search without forcing isolated refreshes |

If many concurrent requests use `wait_for`, Elasticsearch must track the listeners waiting for a refresh. Too many waiting requests can create pressure. For many documents, group them into a bulk request and apply a single suitable refresh policy rather than sending many small requests waiting individually.

## 8. Manual Refresh API

You can explicitly refresh one or more indices using the Refresh API:

```http
POST /products/_refresh
```

Or:

```http
POST /products,inventory/_refresh
```

The Refresh API is useful after a bulk load or when a workflow step must ensure data is searchable. It does not replace write mechanisms and is not a commit/flush operation.

Do not call refresh after every document. Group multiple writes and refresh once when there is an explicit visibility requirement.

## 9. Refresh vs. Flush and Force Merge

These three operations are easily confused:

| Operation | Goal | Makes New Data Immediately Searchable? |
|---|---|---|
| Refresh | Open a new searcher to see new segments | Yes |
| Flush | Perform a Lucene commit and start a new translog generation | Not flush's primary purpose; search visibility is handled by refresh |
| Force merge | Consolidate segments into fewer, larger segments | Not a replacement for periodic refresh |

Refresh serves search visibility. Flush relates to commit/translog management and durability. Force merge is a segment optimization operation generally reserved for indices receiving virtually no more writes.

Do not call `_flush` instead of `_refresh` when the goal is simply making documents appear in search. Nor should you run force merge frequently on actively written indices.

## 10. Impact on Segments and Merges

Lucene writes data into immutable segments. Refreshing makes new segments searchable. When refreshes happen too often, an index generates many tiny segments. Elasticsearch must merge these segments to keep search and storage costs under control.

```text
Many small write requests + refresh=true
             |
             v
       Many tiny segments
             |
             v
       Frequent merges
             |
             v
       CPU / I/O rises
             |
             v
       Write throughput drops
```

Raising the refresh interval or batching writes via bulk reduces tiny segment creation. However, overly infrequent refreshes delay search visibility. The goal is finding a balance aligned with product SLAs.

## 11. Increasing `refresh_interval` for Continuous Ingestion

If a system ingests data continuously without requiring search to see every document right away, you can raise the refresh interval.

Example setting 10 seconds:

```http
PUT /events/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "10s"
  }
}
```

Effects:

- Fewer refreshes.
- Typically lower tiny-segment overhead.
- Indexing throughput can increase.
- New data can take up to the new interval to appear in search, depending on load and refresh activity.

This is an index-level setting. If you have multiple indices, each index can have its own refresh interval. Update the right index/alias and verify the setting afterward.

## 12. Temporarily Disabling Refresh During Large Bulk Loads

For a massive data load into a new index or an index not currently serving real-time search, you can temporarily disable periodic refresh using `-1`.

### Step 1: Record the Current Setting

```http
GET /products/_settings?include_defaults=true
```

Save the current `index.refresh_interval` value so you can restore it accurately after the bulk load. Do not blindly assume it should be restored to `1s`, as the index may have had a custom setting.

### Step 2: Disable Periodic Refresh

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
```

### Step 3: Send Bulk Requests with Default Refresh

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-201" } }
{ "name": "Keyboard", "category": "accessories" }
{ "index": { "_id": "p-202" } }
{ "name": "Gaming Mouse", "category": "accessories" }
{ "index": { "_id": "p-203" } }
{ "name": "4K Monitor", "category": "displays" }
```

During this phase, searches may not see the new documents. The application must still inspect `errors` and every item in the bulk response; refresh settings do not turn bulk requests into transactions.

### Step 4: Restore the Refresh Interval

Suppose the index originally used 1 second:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
```

In practice, restore the exact value saved in Step 1.

### Step 5: Refresh Once After Loading

```http
POST /products/_refresh
```

After this step, imported documents become searchable. You can verify using `_count` or a representative `_search` query.

### Bulk Load Diagram

```text
Read old refresh_interval
          |
          v
Set refresh_interval = -1
          |
          v
Load data via Bulk API
          |
          v
Inspect all bulk items
          |
          v
Restore old refresh_interval
          |
          v
POST /index/_refresh
          |
          v
Verify search visibility
```

### Always Restore the Setting When a Job Fails

If a bulk load fails midway, do not leave the index with refresh disabled indefinitely. Job orchestration must include a cleanup/finally step to restore the setting even if a batch throws an exception or the process terminates with an error state.

If multiple processes use the index, only a single coordinated job should modify the refresh interval during the bulk load phase. Two jobs changing the setting concurrently can restore the wrong value or make search visibility unpredictable.

## 13. Choosing a Refresh Policy by Workload Type

| Workload | Suggested Choice | Rationale |
|---|---|---|
| API creates a product and must search it immediately afterward | `wait_for` | Waits for visibility without necessarily forcing an immediate refresh |
| Test suite needs immediate document confirmation | `true` or manual refresh | Eliminates test timing flakiness |
| Continuous event ingestion tolerating a few seconds of lag | `false` with a larger interval | Reduces refresh overhead |
| Bulk loading a new index with millions of documents | Temporarily `-1`, bulk load, restore, and refresh once | Avoids continuous refreshing during load |
| Batch writes needing search visibility only after each batch | `wait_for` or one refresh after the batch | Balances visibility and refresh frequency |
| High-throughput log/metric ingestion | `false`, interval per SLA | Prioritizes ingestion throughput |
| Infrequently updated data requiring fresh search right after a workflow | `wait_for` at the end of the workflow | Waits for visibility once at the exact point needed |

Do not apply a single refresh policy uniformly across every request in the system. Different write paths can have different visibility SLAs.

## 14. Bulk API and Refresh Policy

The Bulk API accepts multiple actions in a single request. The `refresh` parameter applies to the bulk request, not individual actions.

Example:

```http
POST /products/_bulk?refresh=wait_for
Content-Type: application/x-ndjson

{ "index": { "_id": "p-301" } }
{ "name": "USB Cable" }
{ "index": { "_id": "p-302" } }
{ "name": "USB Charger" }
{ "index": { "_id": "p-303" } }
{ "name": "USB Dock" }
```

The request waits until changes from the bulk request become visible to search. This is usually much better than calling the Index API individually with `refresh=true`.

### Checking the Bulk Response

A bulk response can return HTTP 200 while some items still fail:

```json
{
  "errors": true,
  "items": [
    { "index": { "_id": "p-301", "status": 201 } },
    {
      "index": {
        "_id": "p-302",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
```

Refresh only governs when changes become visible to search. It does not fix mapping errors and does not guarantee every item in the bulk request succeeded. The application must inspect `errors` and every item.

## 15. Configuring `RefreshPolicy` in Spring Data Elasticsearch

Spring Data Elasticsearch provides the `RefreshPolicy` enum to express refresh behavior in supported APIs.

Corresponding values:

| Spring Data | Elasticsearch REST | Meaning |
|---|---|---|
| `RefreshPolicy.NONE` | `false` | Do not request a refresh specifically for the request |
| `RefreshPolicy.IMMEDIATE` | `true` | Refresh immediately |
| `RefreshPolicy.WAIT_UNTIL` | `wait_for` | Wait for the next refresh |

### Declaring on `@Document`

You can configure a default refresh policy for entity writes via the `@Document` annotation in Spring Data Elasticsearch versions supporting this attribute:

```java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

@Document(
    indexName = "products",
    refreshPolicy = RefreshPolicy.WAIT_UNTIL
)
public class ProductDocument {
    // fields
}
```

With this configuration, writes associated with the entity can apply `WAIT_UNTIL` from mapping metadata. Verify your project's Spring Data Elasticsearch version, as overloads and refresh policy scope can vary across versions.

### Manual Refresh via `IndexOperations`

When the application finishes writing a batch and wants to refresh explicitly:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
```

Or obtain `IndexOperations` from the entity class:

```java
IndexOperations indexOperations = operations.indexOps(ProductDocument.class);
indexOperations.refresh();
```

This API is appropriate when batching multiple writes and proactively refreshing once at a batch or workflow boundary.

### Bulk Writes in Spring Data

When using `ElasticsearchOperations` for bulk indexing, select `BulkOptions` or configure refresh policy according to your version's API. For example, in versions supporting the builder refresh policy:

```java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions bulkOptions = BulkOptions.builder()
    .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
    .build();
```

Then pass `bulkOptions` to the corresponding bulk operation method on `ElasticsearchOperations`. Overload names and bulk index signatures vary across versions; use the exact API of your project's dependency. If immediate post-batch visibility is unnecessary, use a policy that does not request refreshes and let the index refresh on schedule.

## 16. Refresh in Repositories and `ElasticsearchOperations`

Repository abstractions make entity writes convenient, though the refresh policy is typically governed by entity metadata or operation/client configuration.

Example:

```java
productRepository.save(product);
```

A `save` call should not be assumed by default to guarantee the document is already searchable when the method returns. If the application needs to search for a newly saved document, either:

- Configure a suitable refresh policy on the entity or operation.
- Or call `IndexOperations.refresh()` where synchronization is required.
- Or design the read path to use GET by ID if only that document needs to be fetched.

Do not call refresh after every `save()` inside a large ingestion loop. Use bulk operations and refresh once per batch or per SLA.

## 17. Testing and Refresh

Integration tests commonly encounter scenarios like:

```java
repository.save(product);

List<ProductDocument> results =
    repository.findByName("Wireless Headphones");

assertThat(results).hasSize(1);
```

This test can fail intermittently if the search runs before the next refresh. Several approaches handle this:

### Option 1: Use `WAIT_UNTIL` in Tests

Ensures write operations wait until documents become searchable. This models read-after-write behavior, though the test waits for a refresh.

### Option 2: Refresh the Index After Loading Fixtures

```java
repository.saveAll(products);
operations.indexOps(ProductDocument.class).refresh();

List<ProductDocument> results = repository.findAll();
```

This is usually the clearest pattern for test fixtures: load data first, refresh once, then run assertions.

### Option 3: Use a Refresh Policy on Test Requests

If the write API supports per-operation refresh policies, small tests needing instant visibility can use `IMMEDIATE`. Never carry `IMMEDIATE` from test configs into production ingestion without evaluating throughput.

### Do Not Use Fixed Sleeps

`Thread.sleep(1000)` is not a reliable synchronization mechanism. Refresh intervals can vary, clusters can get busy, and CI environments can slow down. Use the refresh API or `WAIT_UNTIL` to synchronize on actual events.

## 18. Trade-off Between Throughput and Search Visibility

The shorter the refresh interval, the faster data appears in search, yet the more frequent refresh/segment work becomes. The longer the refresh interval, the higher write throughput tends to be, while searches may see stale results longer.

```text
Short refresh interval
    |
    +--> Fast search visibility
    +--> Many refreshes / tiny segments
    +--> Higher merge and CPU/I/O cost
    +--> Write throughput may drop

Long refresh interval
    |
    +--> Fewer refreshes
    +--> Lower segment overhead
    +--> Write throughput may rise
    +--> Delayed search visibility
```

You cannot optimize both sides infinitely. Define your SLA: do users need to see new data within 100 ms, 1 second, 5 seconds, or 30 seconds? Select the refresh policy and interval accordingly.

### Example Selection by SLA

| Search Visibility Requirement | Suitable Approach |
|---|---|
| Immediately after a single operation | `wait_for` or `true` on that operation |
| Within ~1–2 seconds | Default or near-default refresh interval |
| Within 5–10 seconds | Raise interval and use `refresh=false` |
| After finishing an entire batch import | Temporarily disable periodic refresh, then refresh once |
| No real-time search requirement | Longer interval, evaluated against specific workload |

## 19. Measuring Performance Before and After Changing Policy

Do not rely on intuition that "bulk feels faster." Measure on production-like data and clusters.

Metrics to observe:

- Documents indexed per second.
- Bulk request latency p50/p95/p99.
- Search latency p50/p95/p99.
- CPU and heap on data nodes.
- GC pauses and allocation rates.
- Segment count per shard.
- Merge time and merge throttling.
- Disk I/O and network throughput.
- Lag from write acknowledgment to search visibility.
- Bulk item failure rate.

Inspect segments with:

```http
GET /products/_segments
```

And monitor index stats:

```http
GET /products/_stats/indexing,refresh,merge,search
```

Compare scenarios holding data, bulk size, and shard count constant:

1. Default refresh.
2. Longer `refresh_interval`.
3. Bulk requests with `refresh=wait_for`.
4. Periodic refresh disabled during bulk load followed by a single refresh.

Record both throughput and search visibility lag. A configuration that accelerates writes while violating visibility SLAs is still not an acceptable configuration.

## 20. Optimizing Bulk API Together with Refresh Policy

Refresh is only one factor in ingestion speed. Bulk indexing also depends on batch size, worker count, shard/replica count, mappings, pipelines, network, and cluster capacity.

Key principles:

- Use the Bulk API instead of single-document requests whenever possible.
- Size bulk requests by bytes and processing duration, not just document count.
- Start with moderate worker concurrency and scale up while the cluster has headroom.
- Avoid firing too many concurrent bulk requests that drive up indexing pressure.
- Include only needed fields in the processing pipeline.
- Use longer refresh intervals when SLAs permit.
- For large bulk loads into a new index, consider disabling periodic refresh during the load phase.
- Check every item in bulk responses and retry transient failures selectively.
- Run force merge only when an index is nearly read-only and for a clear operational goal.

### Do Not Confuse Bulk Size with Refresh Interval

Bulk size controls the number/volume of actions in one request. Refresh interval controls how often shards open new searchers. Increasing bulk size does not automatically change the refresh interval; the two parameters address distinct sources of overhead.

## 21. Risks of Disabling Refresh

Setting `index.refresh_interval = -1` can accelerate bulk loads, but you must understand the consequences:

- Search will not see new data until a refresh runs.
- `refresh=wait_for` can block indefinitely if no refresh happens.
- Other applications reading the index continue seeing a stale snapshot.
- If the job fails and forgets to restore the setting, the index may remain without automatic refreshes.
- Multiple jobs modifying the setting can overwrite each other's settings.
- Disabling refresh does not disable the translog or remove default durability mechanisms.

Disable refresh only inside clear bulk load boundaries with a single owner responsible for restoration.

## 22. Refresh and Durability

Refresh controls search visibility, not durability guarantees. Elasticsearch relies on the translog and flush/commit mechanisms to manage durability. Under default settings, translog durability is typically synced per request to protect acknowledged operations.

Therefore:

- You do not need to call refresh to "persist" a document.
- Do not use `refresh=false` as a way to disable durability.
- Do not use flush instead of refresh when the goal is search visibility.
- Do not change `index.translog.durability` solely to optimize refreshes without understanding crash data-loss trade-offs.

Separate two requirements: "the write was safely acknowledged by Elasticsearch" and "search sees the document." They are governed by different mechanisms.

## 23. Refresh with Aliases and Multiple Indices

If an application writes through an alias pointing to multiple indices or a rollover alias, a request's refresh policy affects only the shards involved in the write. `POST /alias/_refresh` refreshes the indices backing that alias.

During bulk loads:

- Identify the actual backing index the alias writes to.
- Adjust the refresh interval on the specific index being loaded.
- If an alias targets multiple indices, inspect settings on each index.
- Avoid accidentally disabling refresh on an index serving interactive workloads.
- After loading, restore the setting on every modified index.

For data streams, understand the current write backing index and rollover policy. Do not assume modifying a setting on one backing index applies to future indices; use an index template to configure defaults for newly rolled-over indices when appropriate.

## 24. Common Pitfalls

### Thinking `refresh=false` Disables Automatic Refresh

`false` only skips requesting a refresh for that write request. The index continues refreshing per `index.refresh_interval` if periodic refresh is enabled.

### Using `refresh=true` After Every Document

This creates tiny segments and hurts throughput. Batch with the Bulk API and refresh by batch or per SLA.

### Using `wait_for` When Refresh Interval Is `-1`

Requests can block until another refresh occurs. During bulk loads with refresh disabled, do not use `wait_for` unless another step refreshes manually.

### Thinking `refresh=true` Refreshes the Whole Cluster

It requests refreshes only on shards touched by that request, not every shard of every index in the cluster.

### Confusing Refresh with Flush

Refresh makes data searchable; flush deals with Lucene commits and translogs. Use the right API for your goal.

### Forgetting to Restore `refresh_interval`

After a bulk load, periodic refresh may stay disabled. Record the prior setting and restore it in cleanup/finally.

### Checking HTTP Status While Ignoring Bulk Item Errors

A bulk response can return HTTP 200 with `errors: true`. Check every item before refreshing and marking the batch successful.

### Using Sleeps in Integration Tests

Fixed sleeps do not guarantee a refresh occurred. Use `WAIT_UNTIL` or call `IndexOperations.refresh()`.

### Calling Force Merge After Every Bulk Batch

Force merge is expensive and does not replace refresh. Use it only when an index is effectively read-only and has a clear operational purpose.

## 25. Workflow for Controlled Ingestion

A data ingestion pipeline can follow this sequence:

1. Define search visibility SLAs for new data.
2. Choose `refresh=false`, `true`, or `wait_for` per operation type.
3. Verify the actual `index.refresh_interval`.
4. Use the Bulk API to reduce request overhead.
5. Select bulk size and worker count via measurements.
6. For massive bulk loads, save the old setting and temporarily set the interval to `-1` if workload permits.
7. Write data and inspect every bulk item.
8. In cleanup/finally, restore the original refresh interval.
9. Manually refresh once if data must be searchable immediately post-load.
10. Verify search visibility with representative queries.
11. Monitor throughput, latency, segments, merges, CPU, heap, and search lag.
12. Tune the interval based on SLAs and measurements rather than rigid defaults.

## 26. Conclusion

Refresh policies govern when new data becomes visible to search. `refresh=false` lets the index refresh on schedule; `refresh=true` requests an immediate refresh of affected shards; `refresh=wait_for` waits for the next refresh. `index.refresh_interval` tunes automatic refresh frequency, while the Refresh API enables explicit refreshes at batch or workflow boundaries.

Frequent refreshes surface new data faster in search, yet generate more tiny segments, increase merge load, and lower write throughput. For continuous ingestion, raising the refresh interval can help when SLAs allow. For massive bulk loads, temporarily disabling periodic refresh, loading via the Bulk API, restoring the prior setting, and refreshing once upon completion works well. In Spring Data Elasticsearch, use `RefreshPolicy` and `IndexOperations.refresh()` matching your project's version. Always distinguish refresh from flush/durability, check individual bulk items, and guarantee setting restoration even when a job fails.

## References

- [Elasticsearch – Near real-time search](https://www.elastic.co/docs/manage-data/data-store/near-real-time-search)
- [Elasticsearch – Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
- [Elasticsearch – Index API refresh parameter](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Index settings: `index.refresh_interval`](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Elasticsearch – Tune for indexing speed](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/indexing-speed)
- [Spring Data Elasticsearch – Object mapping and `@Document`](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
