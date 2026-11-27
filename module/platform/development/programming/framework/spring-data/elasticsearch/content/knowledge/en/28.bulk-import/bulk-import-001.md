# Bulk API and How It Differs from Multiple Single Requests

The Elasticsearch Bulk API lets you send multiple write operations within a single HTTP request. Instead of calling the Index API, Update API, or Delete API separately for each document, the application groups the operations into a batch and sends them to the `/_bulk` or `/{index}/_bulk` endpoint. Elasticsearch routes each action to the shard containing the document and returns a separate result for each action.

The Bulk API generally improves throughput because it reduces the number of HTTP round trips, lowers request-setup overhead, and allows the application to tune the batch size. However, a bulk request is **not a transaction**: some items can succeed while other items fail. The HTTP status of the overall request is not sufficient to conclude that all documents were written successfully. The application must inspect `errors` and each element in `items`, classify the errors, and retry selectively.

In Spring Data Elasticsearch, you can use the bulk operations on `ElasticsearchOperations` or reactive operations to send multiple `IndexQuery`/`UpdateQuery` items. When using repository `saveAll`, you should understand the behavior of the Spring Data version you are running and not assume that every implementation produces a single Bulk API request. If you need explicit control over batch size, refresh policy, and per-item errors, use the explicit bulk API.

## 1. Why Do We Need the Bulk API?

Suppose you need to index 10,000 products. If the application sends each document in a separate request:

```text
Application                      Elasticsearch
   |                                  |
   |---- PUT document 1 -------------->|
   |<--- response 1 ------------------|
   |---- PUT document 2 -------------->|
   |<--- response 2 ------------------|
   |---- PUT document 3 -------------->|
   |<--- response 3 ------------------|
   |                ...               |
   |---- PUT document 10000 ---------->|
   |<--- response 10000 --------------|
```

Each individual operation incurs HTTP, request parsing, coordination, and response overhead. If the network has latency, round-trip wait time can account for a significant share of total time.

With the Bulk API:

```text
Application                      Elasticsearch
   |                                  |
   |---- one bulk request ------------>|
   |     action 1                     |
   |     source 1                     |
   |     action 2                     |
   |     source 2                     |
   |     ...                          |
   |     action N                     |
   |<--- one bulk response ------------|
```

A single request carrying many actions reduces round trips and makes more efficient use of connections. Elasticsearch still executes each operation on its respective shard; bulk does not turn multiple documents into an atomic operation.

### Key Benefits

- Reduces the number of HTTP requests and network round trips.
- Increases throughput when ingesting many documents.
- Allows tuning batch size by bytes and latency.
- Can combine index, create, update, and delete actions in the same batch.
- Makes it easy to organize retries per failed item.
- Well-suited for imports, data synchronization, event consumers, and reindex pipelines.

### Costs and Limitations

- Larger requests and responses, consuming more memory.
- A single batch can contain both successful and failed items simultaneously.
- Batches that are too large can increase latency, heap pressure, and timeout risk.
- Improper retries can cause duplicate writes or overwrite newer data.
- The Bulk API does not guarantee transactions across documents.

## 2. Comparing the Bulk API with Multiple Single Requests

| Criterion | Multiple Single Requests | Bulk API |
|---|---|---|
| Number of HTTP round trips | One round trip per operation | One round trip per batch |
| Throughput for large ingestion | Usually lower due to request overhead | Usually higher if the batch is tuned appropriately |
| Payload size | Small and independent | Can be large, consisting of multiple action/source pairs |
| Result | One response per operation | One response with an individual result for each item |
| Error handling | Error is tied to the corresponding request | Must inspect each item; partial success is possible |
| Retry | Retry the failed request | Selectively retry appropriate items |
| Ordering | Coordinated per request by the application | Actions are ordered in the payload, but execution across multiple shards is not a global transaction |
| Load control | Limit concurrent requests | Limit batch size and concurrent bulk requests |
| Best suited for | Single writes, read-after-write, interactive operations | Imports, batch ingestion, synchronization, and high-volume processing |

Bulk is not necessarily faster in every scenario. For a single document, calling the Index API directly is usually simpler and there is no benefit to constructing a bulk request containing only one action. Bulk excels when there are many independent operations to group together.

## 3. NDJSON Structure of the Bulk API

The Bulk API uses NDJSON (Newline Delimited JSON). Each line is an independent JSON object. For actions that carry a source document, the metadata line is followed by the source line.

Example:

```http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "products", "_id": "p-100" } }
{ "name": "Wireless Mouse", "status": "ACTIVE" }
{ "index": { "_index": "products", "_id": "p-101" } }
{ "name": "Mechanical Keyboard", "status": "ACTIVE" }
```

Important rules:

- Each JSON line must be a valid object.
- Action metadata sits on its own line.
- `index`, `create`, and `update` have an additional content line formatted according to the action.
- `delete` only needs the metadata line, with no following source line.
- Lines are separated by a newline `\n`.
- The payload must end with a final trailing newline.
- The content type should be `application/x-ndjson`.

Do not send a JSON array such as `[ {...}, {...} ]` to the Bulk API. That is not the NDJSON format the endpoint requires.

## 4. Actions in the Bulk API

The Bulk API supports four primary actions:

| Action | Purpose | Next Line |
|---|---|---|
| `index` | Create a document or replace an existing document with the same ID | Source document |
| `create` | Create only if the ID does not already exist | Source document |
| `update` | Partially update a document or run an update script | Update body |
| `delete` | Delete a document by ID | None |

### `index`: create or replace

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "Wireless Mouse", "price": 29.99 }
```

If the document ID does not exist yet, Elasticsearch creates the document. If the ID already exists, the `_source` content is replaced with the new source. Therefore, when using `index`, send the complete document that the application wants stored.

### `create`: create only if it does not exist

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "create": { "_id": "p-101" } }
{ "name": "Keyboard", "price": 79.00 }
```

If the ID already exists, the corresponding item fails with a conflict. `create` is useful when you need to detect duplicate IDs rather than silently replacing the document.

### `update`: partial update

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "update": { "_id": "p-100" } }
{ "doc": { "price": 27.99 } }
```

The update body can contain `doc`, `doc_as_upsert`, `upsert`, `script`, and supported options. Choose clear semantics to avoid accidentally creating a new document or overwriting fields.

### `delete`: delete document

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "delete": { "_id": "p-101" } }
```

Do not add a source line after a `delete` action; doing so will cause the parser to misinterpret the boundary of the next action.

## 5. Specifying the Index and Document ID

You can specify the index in the URL:

```http
POST /products/_bulk
```

In that case, the action can omit `_index`:

```json
{ "index": { "_id": "p-100" } }
{ "name": "Mouse" }
```

Or send to `/_bulk` and specify the index in each action:

```json
{ "index": { "_index": "products", "_id": "p-100" } }
{ "name": "Mouse" }
{ "index": { "_index": "categories", "_id": "c-100" } }
{ "name": "Accessories" }
```

The second approach allows multiple indices in a single bulk request. You must verify access permissions on every index the request may touch.

### Using Stable IDs

When synchronizing from a database, the source primary key is commonly used as `_id` so that a replay updates the same document instead of creating a new duplicate.

```text
database product.id = p-100
              |
              v
Elasticsearch _id = p-100
```

Stable IDs make upserts and retries easier to keep idempotent. If each retry generates a random ID, the same source record can end up as multiple documents.

## 6. Bulk Response: Inspecting Each Item

A bulk request typically returns an overall response with an `errors` field and an `items` list:

```json
{
  "took": 12,
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
    }
  ]
}
```

In this example, the bulk request completed, with `p-100` succeeding and `p-101` failing. The HTTP status of the request may still be 200. The application must inspect:

- `errors`: whether at least one item failed.
- `items`: the result corresponding to each submitted action.
- `status`: the HTTP status of each individual item.
- `error.type` and `error.reason`: the cause of failure.
- `_id`, `_index`, and the action: identifying the item to handle.

Response items are returned in the order of actions in the request, allowing the application to correlate them with the input batch. However, do not treat bulk as a globally ordered transaction across multiple shards or multiple documents.

### Do Not Only Check the HTTP Status

Code that only checks for HTTP 200 is not enough:

```java
if (response.statusCode() == 200) {
    markWholeBatchSuccessful();
}
```

You must iterate through each item's result and only mark the batch complete when every item has been handled according to business policy.

## 7. The Bulk API Is Not a Transaction

The Bulk API reduces request overhead, but it does not create a transaction spanning all actions. If one item has a mapping error, other items can still succeed. Elasticsearch does not automatically roll back successful items when another item fails.

Example:

```text
Bulk request containing A, B, C, D
       |
       +--> A: succeeded
       +--> B: mapping error
       +--> C: succeeded
       +--> D: version conflict error

Result: A and C are still written.
        B and D must be handled separately.
```

If business requirements demand that all changes succeed together or roll back together, the Bulk API does not provide those transaction semantics. Use transactions in the authoritative data source or design an appropriate saga/compensation flow; do not simulate a transaction by sending a bulk request and then deleting the successful items back out if you have not accounted for every failure mode.

## 8. Why Is the Bulk API Usually Faster?

The Bulk API reduces several repeated costs:

1. Fewer HTTP requests opened and sent.
2. Fewer network round trips.
3. Reduced parse/dispatch overhead at the request layer.
4. Ability to distribute many actions to shards within the same batch.
5. The application can tune batch size to utilize cluster throughput.

However, Elasticsearch still has to parse each action, route it to the shard, index the document, update the translog, and handle refresh/merge according to configuration. Bulk does not eliminate the per-document processing cost.

### Bulk Too Small

If a batch contains only a few documents, the overhead of creating and sending the batch may not be meaningfully lower than individual requests. Throughput can become bottlenecked by round trips and scheduling.

### Bulk Too Large

Large batches can:

- Increase application memory used to build the payload and hold the response.
- Increase processing time per request.
- Increase the risk of timeouts or rejected requests.
- Force a retry to process many more items.
- Put heavy pressure on the coordinating node and data nodes.

The goal is to find a batch size large enough to reduce overhead while staying within memory and latency budgets.

## 9. Choosing Batch Size by Bytes, Not Just Document Count

A batch of 1,000 small documents can be lighter than 100 documents with very large sources. Therefore, you should not just configure `batchSize = 1000` while ignoring payload size.

Factors to consider:

- Average and high-percentile size of the JSON source.
- Number of fields and nested objects.
- Size of the metadata/action lines.
- Number of shards receiving data.
- Network throughput.
- Application and Elasticsearch heap.
- Target latency for a bulk request.
- Retry and failure rates.

Some practical guidelines start with a batch payload of a few MB and scale up through benchmarking. There is no single fixed optimal size for every cluster. You should measure actual NDJSON bytes rather than estimating from document count alone.

### Example Batching by Item Count

```java
Flux.fromIterable(products)
    .buffer(500)
    .concatMap(this::sendBulkBatch);
```

This snippet limits each batch to 500 elements and sends them sequentially. If source sizes vary widely, add byte-based flush logic or use a bulk processor that supports a request-size threshold.

### Batching by Both Count and Time

For a continuous event stream, you can flush when enough items arrive or a wait duration elapses:

```java
Flux<List<ProductDocument>> batches = source
    .bufferTimeout(500, Duration.ofSeconds(2));
```

This avoids holding a batch for too long during low traffic. If payloads can be very large, add a byte limit or split the batch before sending.

## 10. Tuning Concurrent Bulk Requests

Bulk size and bulk concurrency are two distinct parameters:

- Batch size determines the number/volume of actions in one request.
- Concurrency determines how many bulk requests are in flight simultaneously.

Example:

```java
return Flux.fromIterable(batches)
    .flatMap(this::sendBulkBatch, 2);
```

At most two bulk batches are processed concurrently in this pipeline. Increasing concurrency can improve throughput when the cluster has spare capacity, but it can also increase indexing pressure, queuing, heap usage, and rejected requests.

### Calculating Total Load Across Instances

If each instance allows 4 concurrent bulk requests and 6 instances run simultaneously, that flow can generate around 24 in-flight bulk requests. You must also account for schedulers, other consumers, retries, and other services sharing the cluster.

Do not choose concurrency solely based on the application's CPU count. Measure Elasticsearch's ingest capacity, connection pool, shard distribution, and latency.

## 11. Monitoring and Handling HTTP 429

When Elasticsearch is overloaded or cannot accept more indexing work, requests or items may be rejected with `429 Too Many Requests` or a corresponding rejection error.

The application should:

- Reduce bulk concurrency when the 429 rate rises.
- Retry items with transient errors using exponential backoff and jitter.
- Cap the maximum number of retries.
- Avoid retrying immediately at the same rate.
- Monitor indexing pressure, thread pool rejections, CPU, heap, and merges.
- Pause or throttle the consumer if the data source supports backpressure.

A retry storm can make the situation worse. When a cluster is overloaded, immediately resending a large batch usually only adds more load.

### Illustrative Backoff

```text
Retry 1: wait 200 ms + jitter
Retry 2: wait 400 ms + jitter
Retry 3: wait 800 ms + jitter
After limit: send to retry queue/DLQ or mark job failed
```

Actual values must be benchmarked and may need a maximum delay cap. Only retry errors identified as transient; mapping or validation errors require fixing the data or configuration first.

## 12. Classifying Errors Before Retrying

Not every error can be resolved by resending the same item.

| Error | Example | Action |
|---|---|---|
| Mapping/parse error | `mapper_parsing_exception` | Do not retry the payload as-is; fix the source or mapping |
| Validation error | Wrong field type or invalid document | Route to error handling/DLQ, fix the data |
| Version conflict | `version_conflict_engine_exception` | Re-read state/token and recompute business logic |
| 429/rejection | Cluster overloaded | Backoff, reduce concurrency, retry with a cap |
| Timeout/network error | Unclear whether server processed it | Idempotent retry using a stable ID and check state |
| Authorization error | 401/403 | Fix credentials/permissions; do not retry continuously |
| Index missing | Index/alias does not exist | Fix lifecycle/configuration or create the index properly |

In particular, a timeout does not prove the operation was not executed. The server may have already written the document while the response was lost. Retries must be safe in case the earlier request actually succeeded.

## 13. Idempotency When Resending Bulk Items

Idempotency means that resending the same operation does not corrupt the final state.

### Indexing with a Stable ID

```json
{ "index": { "_index": "products", "_id": "p-100" } }
{ "name": "Wireless Mouse", "price": 29.99 }
```

Resending the same action/source with the same ID writes to the same document instead of creating a new document with a random ID. However, if the retried source is older than the current source, it can still overwrite newer data. A stable ID does not solve ordering by itself.

### `create` Is Not Idempotent with the Same Semantics

`create` only succeeds when the ID does not exist yet. Retrying after the first attempt already succeeded can return a conflict. The application must treat that conflict as a result to reconcile, not automatically assume the data is wrong.

### Update Scripts May Not Be Idempotent

Example counter-increment script:

```json
{ "update": { "_id": "p-100" } }
{ "script": { "source": "ctx._source.views += params.n", "params": { "n": 1 } } }
```

If retried after the update already succeeded but the response was lost, the counter can be incremented twice. For additive/subtractive updates, you need an idempotency key, processed event ID, version condition, or an operation design where retries do not double the effect.

## 14. Version Conflicts and Optimistic Concurrency in Bulk

Bulk actions support metadata conditions such as `if_seq_no` and `if_primary_term` for applicable operations. Example:

```http
POST /_bulk
Content-Type: application/x-ndjson

{ "update": { "_index": "products", "_id": "p-100", "if_seq_no": 42, "if_primary_term": 3 } }
{ "doc": { "price": 27.99 } }
```

If the document changed since the metadata was read, the item can return 409. In that case, do not retry with the same stale token. The application must re-read the document, obtain the new token, validate business logic, and recompute the change.

Within a batch, each document has its own token. Do not share a single sequence number/primary term pair across all items.

### A Bulk Conflict Does Not Break Other Items

A single 409 item does not roll back the other items. The response must be classified per action and only safely resolvable items should be retried.

## 15. Action Ordering and Dependencies Between Documents

A bulk request can contain actions targeting multiple shards. It does not provide a global transaction or guarantee consistency across multiple documents.

If two operations depend on each other—for example, updating a product and then updating an aggregate document—do not treat placing them next to each other in a bulk request as a transaction mechanism. If one action fails, the other may have already succeeded.

With multiple actions for the same document, define the required semantics and ordering. If correctness depends on order, consider serializing by document ID, using version/conditional updates, or splitting into controlled steps. Do not allow multiple workers to send competing bulk batches for the same ID without ordering rules.

## 16. Bulk and Refresh Policy

The Bulk API supports the `refresh` parameter just like other write APIs:

| Value | Meaning |
|---|---|
| `false` | Do not request an explicit refresh for this request; wait for periodic refresh |
| `true` | Request an immediate refresh of the affected shards after the request |
| `wait_for` | Wait for the next refresh to make changes searchable |

Example:

```http
POST /products/_bulk?refresh=wait_for
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "Mouse" }
{ "index": { "_id": "p-101" } }
{ "name": "Keyboard" }
```

If ingestion is high-throughput and searches do not need to see each batch immediately, `refresh=false` or omitting the parameter is typically used. For a workflow that needs search to see the entire batch right after writing, you can use `wait_for` or refresh once at the batch boundary.

Do not use `refresh=true` on every small bulk batch in a high-rate stream without an explicit read-after-write requirement; frequent refreshes can increase segment counts and merge overhead.

## 17. Optimizing Large Bulk Loads with Refresh Interval

For large data loads into a new index, you can temporarily increase `index.refresh_interval` or set it to `-1` to disable periodic refresh during the bulk load, if the workload permits.

General procedure:

1. Read and save the current refresh interval.
2. Temporarily disable or increase the interval.
3. Send bulk batches with bounded concurrency.
4. Check all item responses and handle errors.
5. Restore the original refresh interval.
6. Call the Refresh API once if data needs to be searchable immediately.
7. Verify search visibility.

Example disabling periodic refresh:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
```

After the import finishes, restore the original value and refresh:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
```

```http
POST /products/_refresh
```

In production, restore the exact value read in the first step rather than assuming it is always `1s`. The job needs a cleanup/finally step to restore the setting even if a batch fails or a worker stops.

Do not use `refresh=wait_for` while periodic refresh is disabled unless there is another refresh step; the request may block waiting for a refresh.

## 18. Routing in the Bulk API

If an index uses custom routing, each action must pass the appropriate routing so the document is written to the right shard:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100", "routing": "tenant-42" } }
{ "tenantId": "tenant-42", "name": "Mouse" }
```

When updating, deleting, or retrying an action, pass the same required routing. If routing is wrong or missing, the operation may fail to find the document or write to a different shard under default routing.

With multi-tenant indices, routing can help co-locate data by tenant, but an oversized tenant can create a hot shard. Design routing around tenant size and workload; do not use a single routing key for every document if that causes imbalance.

## 19. Pipelines and Action Metadata

A bulk action can specify an ingest pipeline:

```http
POST /products/_bulk?pipeline=normalize-product
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "  Wireless Mouse  " }
```

A pipeline can normalize, enrich, or transform the source before indexing. When using a pipeline, factor its processing cost into batch size and concurrency. A complex pipeline can become a bottleneck even when network overhead is reduced.

Some metadata such as routing, version conditions, pipeline, or retry-on-conflict can be specified per action or per request depending on the API. Verify the exact semantics and Elasticsearch version before relying on a specific parameter.

## 20. Bulk and Aliases

Applications often send bulk requests to a write alias instead of a physical index:

```http
POST /products-write/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "Mouse" }
```

Aliases allow changing the write index during rollover or rebuilds without modifying code. If an alias points to multiple indices, a write index must be explicitly configured or actions must be routed intentionally.

When rebuilding a new index, manage event/backfill synchronization and the alias switch separately. The Bulk API only executes the submitted actions; it does not combine alias switching, backfilling, and event replay into a single transaction.

## 21. Spring Data Elasticsearch: When to Use Bulk Operations?

Spring Data Elasticsearch provides `ElasticsearchOperations` for template-level index/update/delete operations. When you need to send many actions, you can use its bulk methods instead of calling `save` repeatedly.

Appropriate use cases:

- Importing data from CSV/JSON or a database.
- Consumers receiving events in batches.
- Synchronizing search projections.
- Reindexing data through an application mapper.
- Deleting or updating many documents for a known set of IDs.

For a single document in an interactive request, `save()` or a repository method is usually more readable and sufficient. For hundreds or thousands of documents, consider the Bulk API and benchmark it.

## 22. Using `IndexQuery` and `bulkIndex`

Example creating a list of `IndexQuery`:

```java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> queries = products.stream()
    .map(product -> new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build())
    .toList();
```

Sending the bulk request:

```java
List<IndexedObjectInformation> indexed =
    operations.bulkIndex(
        queries,
        IndexCoordinates.of("products")
    );
```

Return types and `bulkIndex` overloads vary across Spring Data Elasticsearch versions. Some versions allow passing `BulkOptions` to configure bulk settings. Use the exact API of your project's dependency.

### Do Not Build an Unbounded List

The example above uses `stream().toList()` to illustrate a batch already in memory. For large sources, do not load the entire dataset into a `List`. Read page-by-page or chunk-by-chunk from the source, build `IndexQuery` objects for a bounded batch, send the bulk request, and release the batch before fetching the next one.

## 23. Using `BulkOptions`

Some Spring Data Elasticsearch versions support `BulkOptions` to pass extra configuration to a bulk operation, such as refresh policy, timeout, pipeline, or options supported by the client/version.

Example illustrating refresh policy:

```java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions options = BulkOptions.builder()
    .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
    .build();
```

Then pass `options` into the corresponding bulk operation overload on `ElasticsearchOperations`.

Exact builder names, methods, and available options depend on the Spring Data Elasticsearch version. Do not copy an example verbatim into a project without checking the dependency Javadoc. If an option is not supported by the abstraction in the current version, you can use the Elasticsearch Java API Client configured in the Spring context.

## 24. Does `saveAll()` Always Use the Bulk API?

`CrudRepository`/Elasticsearch repositories provide `saveAll()` to save multiple entities. It is a convenient repository-layer API:

```java
productRepository.saveAll(products);
```

However, you should not assume that every version, repository implementation, or configuration path produces a single Bulk API request with an optimal batch size. Internal implementation details can change across versions and implementations.

If throughput and request size are critical requirements:

- Check the Javadoc/source of the exact Spring Data Elasticsearch version.
- Measure actual request counts through client metrics or instrumentation.
- Use `ElasticsearchOperations.bulkIndex(...)` when explicit control over bulk behavior is needed.
- Split data into bounded batches before calling.
- Inspect per-item results and errors.

`saveAll()` remains appropriate for simple use cases, small batches, and code that does not require fine-grained control over bulk options.

## 25. Bulk with Reactive Operations

Reactive Spring Data Elasticsearch provides corresponding bulk APIs returning `Mono` or `Flux` depending on the operation and version. Using reactive APIs does not change the nature of the Bulk API: a single bulk request still has multiple items and the response can still partially succeed.

Example illustrating a batch flow:

```java
Flux.fromIterable(source)
    .buffer(500)
    .concatMap(batch -> reactiveOperations.bulkIndex(
        toIndexQueries(batch),
        IndexCoordinates.of("products")
    ))
    .then();
```

Exact method names, return types, and overloads depend on the version. The snippet illustrates how to structure the pipeline: collect a bounded batch, send the bulk request, wait for the batch to finish, and then process the next batch.

If you want to send multiple bulk batches in parallel, use `flatMap` with an explicit concurrency limit:

```java
Flux.fromIterable(source)
    .buffer(500)
    .flatMap(batch -> sendBulk(batch), 2)
    .then();
```

Do not use unbounded `flatMap` over a large source. Each in-flight batch can hold payloads and responses in the heap while also putting pressure on Elasticsearch.

### Backpressure and Batching

`buffer(500)` limits the number of items in each batch, while the concurrency parameter of `flatMap` limits how many batches are processed concurrently in the pipeline. If the source is paginated from Elasticsearch or a database, also control how many pages are prefetched. Do not call `collectList()` on the entire source just to send a giant bulk request.

## 26. Bulk with `UpdateQuery`

When updating only specific fields, create an `UpdateQuery` per document:

```java
Document partial = Document.create();
partial.put("status", "ACTIVE");

UpdateQuery update = UpdateQuery.builder("p-100")
    .withDocument(partial)
    .build();
```

Then collect multiple update queries and send them via the bulk update API on `ElasticsearchOperations` for your version.

A bulk update can contain partial documents, upserts, or scripts. Choose explicitly:

- `doc`: partially updates `_source`.
- `doc_as_upsert`: uses the partial doc to create the document if it does not exist when enabled.
- `upsert`: source used when the document does not exist.
- `script`: executes update logic on the Elasticsearch side.

Scripted updates require idempotency and parameter control. If you retry an addition/subtraction operation, the effect can be applied multiple times if the previous attempt succeeded but the response was lost.

## 27. Bulk Delete

If you need to delete multiple documents with known IDs, you can create a delete action for each ID and send them in a bulk request:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "delete": { "_id": "p-100" } }
{ "delete": { "_id": "p-101" } }
{ "delete": { "_id": "p-102" } }
```

Bulk delete is appropriate when the application already has the list of IDs. If the goal is deleting by query, `_delete_by_query` has its own semantics and mechanism; there is no need to load all IDs into the application just to perform a mass delete.

Deleting an item that is not found can return a `not_found` result depending on the situation/API. Decide whether this is an acceptable idempotent outcome or an error to report.

## 28. Bulk Response and Mapping Errors Back to Input

The application needs to preserve the link between each action and its source record in order to handle item failures. A wrapper can be used:

```java
public record PendingIndex(
    String sourceId,
    long sourceVersion,
    IndexQuery query) {
}
```

When building the batch, keep the list in the same order as the submitted actions. When reading the response, map each item back to its corresponding `sourceId`, source version, and event ID.

If you only keep `List<IndexQuery>` without source metadata, finding which record to retry or route to a dead-letter queue becomes harder.

### Reporting Batch Results

An application result structure might contain:

```java
public record BulkBatchResult(
    int submitted,
    int succeeded,
    int retryableFailures,
    int permanentFailures,
    List<BulkItemFailure> failures) {
}
```

This result is an application model, not a fixed Spring Data response type. It helps the job runner decide whether to continue, retry, alert, or mark the batch as partial.

## 29. Selective Retry and Dead-Letter Queue

A resilient bulk pipeline typically separates items into three groups:

```text
Bulk response
     |
     +--> Success --------------------> mark completed
     |
     +--> Retryable failure ----------> retry queue with backoff
     |
     +--> Permanent failure ----------> DLQ / error report
```

The retry queue should retain enough metadata to reconstruct the action: document ID, index/alias, routing, source payload or event reference, source version, attempt count, and latest error.

A dead-letter queue (DLQ) stores items that cannot be processed automatically, such as mapping errors or malformed data. The DLQ needs a process for correction and replay; do not just log and ignore items if the data is required to be synchronized.

### Do Not Retry the Entire Batch When Only One Item Fails

If 999 out of 1,000 items succeed and one item has a mapping error, resending the whole batch can repeat unnecessary operations and add load. Construct a retry batch containing only the retryable items. For idempotent operations, retrying the whole batch may be state-safe, yet it still wastes resources and obscures errors.

## 30. Bulk and Ingest Pipelines

An ingest pipeline can process data before indexing, such as normalizing fields, enriching, parsing timestamps, or removing fields. You can specify a pipeline for a bulk request or action depending on API support.

Notes:

- Pipelines run on ingest nodes or nodes configured to handle ingest per cluster configuration.
- Heavy pipelines can become a bottleneck.
- A processor can fail for a single item; inspect item responses.
- Modifying a pipeline can cause the same source to produce different projections over time.
- If deterministic replay is required, version the pipeline and keep transformation logic explicit.

Measure ingest pipeline duration alongside indexing throughput. Large bulk batches cannot compensate for a CPU-bound pipeline or slow enrichment calls.

## 31. Bulk and Mapping

Mapping errors are a common reason why part of a bulk batch fails. For example, field `price` is mapped as `double` but the source sends an unparseable string:

```json
{ "index": { "_id": "p-100" } }
{ "name": "Mouse", "price": "not-a-number" }
```

The bulk response can return a `mapper_parsing_exception` item error. Other items can still succeed.

Before large ingestion:

- Create the index and explicit mapping before sending data.
- Normalize data types in the application mapper.
- Check date, numeric, keyword, and nested fields.
- Avoid dynamic mapping creating unexpected fields.
- Test a representative batch before running a large import.

Do not retry a mapping error without changing the payload or mapping; it will keep failing.

## 32. Bulk and Aliases / Data Streams

A bulk request can write through an index, alias, or data stream according to Elasticsearch rules. When writing through an alias, a write index must be configured. With a data stream, actions generally must follow the append-only semantics of data streams; updates/deletes by ID have specific constraints and requirements.

In an import job:

- Identify whether the target is a physical index, write alias, or data stream.
- Do not mix multiple targets without clear permissions and routing.
- Account for rollovers that may occur while the job is running.
- Use IDs and actions matching the target semantics.
- Inspect item results to see which index each action actually wrote to.

## 33. Monitoring Bulk Performance

To choose batch size and concurrency, monitor both the application and Elasticsearch.

### Application Metrics

- Number of documents/bytes per batch.
- Bulk request latency p50/p95/p99.
- Documents indexed per second.
- Number of in-flight bulk requests.
- Item success/failure counts by error type.
- Retry count and backoff duration.
- Queue depth and consumer lag.
- Heap usage while constructing payloads/responses.
- Timeouts and pending connection pool acquisitions.

### Elasticsearch Metrics

- Indexing rate and indexing latency.
- Indexing pressure.
- CPU, heap, and GC.
- Write/bulk thread pool rejections per version.
- Merge time and segment count.
- Disk I/O and network.
- Refresh count/time.
- Shard distribution and hot shards.

You can check index stats:

```http
GET /products/_stats/indexing,refresh,merge
```

And appropriate node stats to observe indexing pressure/thread pools for the running version.

## 34. Benchmarking Batch Size and Concurrency

A controlled benchmarking approach:

1. Select a representative dataset and production-like mapping.
2. Fix the shard count, replicas, pipeline, and refresh interval.
3. Start with a small batch size and low concurrency.
4. Increase batch size incrementally, recording throughput and p95 latency.
5. Keep the good batch size and increase concurrency incrementally.
6. Stop increasing when throughput stops improving or CPU/heap/rejections spike.
7. Re-run with large documents and realistic routing distribution.
8. Verify item failures and final data after the benchmark.

Example test matrix:

| Batch Size | Concurrent Bulk Requests | Observation Goal |
|---:|---:|---|
| 100 docs | 1 | Baseline |
| 500 docs | 1 | Impact of larger batch |
| 500 docs | 2 | Impact of higher concurrency |
| 1,000 docs | 2 | Impact of even larger batch |
| 1,000 docs | 4 | Impact of total load |

These numbers are benchmark examples, not default configurations. Choose based on payload bytes and cluster capacity.

## 35. When Should You Use Single Requests?

Bulk is not the best choice for every write:

- A user creates a single document and needs an immediate response.
- An operation needs clear read-after-write semantics.
- A write stream has low volume and low frequency.
- Errors for a single document must be handled independently and returned directly.
- An operation immediately depends on the response of the previous operation.

In these cases, individual Index/Update/Delete APIs can be simpler and easier to observe. Do not wrap a single operation into a batch just because the system supports the Bulk API.

## 36. Common Pitfalls When Using the Bulk API

### Sending a JSON Array Instead of NDJSON

The Bulk API requires each action/source on separate lines with a trailing newline. A JSON array is not valid bulk format.

### Missing Trailing Newline in Payload

NDJSON must end with a newline. A payload truncated at the end can cause request parsing to fail.

### Using the Wrong Content Type

Send `Content-Type: application/x-ndjson`.

### Only Checking HTTP 200

Some items can fail while the bulk request returns an overall successful response. Check `errors` and each item in `items`.

### Treating Bulk as a Transaction

One failed item does not roll back other items. Design for partial success as a normal part of the flow.

### Batches Too Large

Increases memory, latency, timeouts, and retry cost. Measure by bytes and split batches.

### Unbounded Concurrency

Many simultaneous bulk requests can overload Elasticsearch. Cap concurrency according to the total load across all instances.

### Retrying the Whole Batch Unselectively

Increases load and can repeat side effects. Classify items and retry only the retryable group.

### Retrying Non-Idempotent Script Updates

Counters or additions can be applied twice. Use idempotency keys/versions or design safe updates.

### Ignoring 429s

Without backoff, retries create a retry storm. Reduce concurrency and retry with limits.

### Forgetting Routing

Updates/deletes may fail to find the document or hit the wrong shard if routing is inconsistent.

### Assuming `saveAll()` Is Guaranteed Optimal Bulk

Check the implementation/version or use explicit bulk operations when control is needed.

## 37. Workflow for Building Resilient Bulk Ingestion

A data ingestion pipeline can follow these steps:

1. Identify the authoritative source, document ID, and semantics of index/create/update/delete.
2. Create mappings and ingest pipelines before loading data.
3. Read source data in bounded pages/chunks.
4. Convert each record into a bulk action and retain source metadata for correlation.
5. Split batches by item count and payload bytes.
6. Send with a bounded number of concurrent bulk requests.
7. Inspect `errors` and every item response.
8. Mark successful items; classify retryable and permanent failures.
9. Retry selectively with backoff, jitter, and idempotency.
10. Route unprocessable errors to a DLQ/error report.
11. Monitor throughput, latency, 429s, heap, and Elasticsearch indexing pressure.
12. Apply a refresh policy matching the search visibility SLA.
13. Reconcile counts/versions to confirm data synchronization.
14. Persist checkpoints so the job can resume after a failure.

## 38. Conclusion

The Bulk API groups multiple index/create/update/delete operations into a single NDJSON HTTP request, reducing round trips and typically increasing throughput for large data imports. Compared to multiple single requests, the Bulk API lowers overhead but produces larger requests and responses and requires the application to manage batch size, concurrency, memory, and partial failures.

Bulk is not a transaction: some items can succeed while others fail. Always inspect `errors` and each element in `items`, classify errors, and retry selectively. Use stable IDs, version conditions, and idempotency to avoid duplicates or overwriting newer data; apply backoff when encountering 429s; bound batches by bytes and count; and choose appropriate refresh, routing, and pipeline settings. In Spring Data Elasticsearch, use `ElasticsearchOperations` bulk methods or reactive bulk operations when explicit control is needed, and verify the API for your version. `saveAll()` is convenient, but it should not be assumed to be a single optimal bulk request without verifying the implementation.

## References

- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Tune for indexing speed](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/indexing-speed)
- [Elasticsearch – Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch – Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – Bulk operations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
