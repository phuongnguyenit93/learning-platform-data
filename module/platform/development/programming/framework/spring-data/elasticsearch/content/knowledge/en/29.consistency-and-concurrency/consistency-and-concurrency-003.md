# Refresh Policy: NONE, IMMEDIATE, and WAIT_UNTIL

## 1. What is a refresh in Elasticsearch?

Elasticsearch is a near real-time (NRT) search engine. When an application writes or updates a document, the write operation may already be acknowledged as successful while the document does not yet appear in Search API results.

The reason is that the write operation and searchability occur at two different moments in time:

1. Elasticsearch receives and processes the write operation, updates internal data, and acknowledges the request.
2. A **refresh** makes the new changes searchable.

For example, suppose the application just created a product:

~~~http
PUT /products/_doc/p-100
{
  "name": "Wireless Headphones",
  "category": "audio",
  "price": 1200000
}
~~~

The request may return success. However, if the application immediately runs:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

the new document might not appear in the results yet. It will become searchable after the next refresh.

The **refresh policy** determines how a write operation handles that search visibility milestone. Elasticsearch supports three options:

- `NONE`: do not request a refresh for this request.
- `IMMEDIATE`: refresh immediately after the write operation completes.
- `WAIT_UNTIL`: wait until a refresh makes the request's changes searchable.

In the REST API, the three options correspond to `refresh=false`, `refresh=true`, and `refresh=wait_for`.

## 2. Distinguishing refresh, refresh interval, and flush

These three concepts relate to the data lifecycle in Elasticsearch, but they are not synonymous.

| Concept | Meaning |
|---|---|
| Refresh | Opens new changes so the Search API can find them |
| `index.refresh_interval` | Configured interval between automatic refreshes |
| Flush | Creates a Lucene commit and processes the translog to support crash recovery |

Refresh focuses on searchability. It does not mean the application requested a new Lucene commit or completed all long-term persistence work.

Similarly, `refresh_interval` is not a fixed wait time that every request must wait for. It is a setting controlling the shard's automatic refresh cycle. A request using `WAIT_UNTIL` waits for a refresh that makes its changes searchable.

The default in current Elastic Stack releases is `1s`; Elastic Cloud Serverless defaults to `5s`. The actual value depends on the environment and index settings. Elasticsearch can also adapt automatic refresh behavior based on a shard's search activity.

One way to visualize this:

~~~text
Write document
     |
     v
Request is acknowledged
     |
     v
Document is written, not necessarily searchable yet
     |
     v
Refresh
     |
     v
Search API sees the new document
~~~

Refresh is not an operation that should be executed after every write. Elasticsearch uses automatic refreshes to balance searchability and write performance.

## 3. Three refresh policy values

The three policies can be compared as follows:

| Spring Data | Elasticsearch REST | Behavior | Primary cost |
|---|---|---|---|
| `RefreshPolicy.NONE` | `refresh=false` | Takes no refresh action for the request | Lowest |
| `RefreshPolicy.IMMEDIATE` | `refresh=true` | Refreshes affected shards right after the operation | Increases write, search, and merge cost |
| `RefreshPolicy.WAIT_UNTIL` | `refresh=wait_for` | Waits for an automatic or other refresh to make changes searchable | Increases response latency, usually avoids a per-request refresh |

The right choice depends on the business flow's requirements:

- If the application can tolerate a short search delay, choose `NONE`.
- If the user needs to see the document right away in the next search result, consider `WAIT_UNTIL`.
- If an immediate refresh after the operation is truly required and the cost is acceptable, choose `IMMEDIATE`.

`NONE` is usually the right choice for standard write paths. Only enable a waiting or immediate-refresh policy when the business logic needs a searchability guarantee.

## 4. NONE: do not request a refresh

`RefreshPolicy.NONE` corresponds to `refresh=false` in Elasticsearch.

When using this policy:

- The write request does not ask Elasticsearch to refresh shards.
- The request still returns success once the write is acknowledged.
- The document becomes searchable when the next automatic refresh or another refresh runs.
- The application must not assume the Search API will see the document immediately after the write response returns.

REST example:

~~~http
PUT /products/_doc/p-101?refresh=false
{
  "name": "Bluetooth Speaker",
  "category": "audio",
  "price": 850000
}
~~~

Or omit the `refresh` parameter altogether:

~~~http
PUT /products/_doc/p-102
{
  "name": "USB Hub",
  "category": "accessories",
  "price": 350000
}
~~~

When the parameter is omitted, Elasticsearch defaults to taking no refresh action for the write request.

### When should NONE be used?

`NONE` fits:

- Importing many documents.
- Background data writes or periodic synchronization.
- High-frequency write paths.
- Operations where users do not need to search for the document immediately.
- Systems that can tolerate data appearing in results after the next automatic refresh.

For example, a job importing 100,000 products does not need each product to become searchable immediately after every write. Letting Elasticsearch refresh on schedule is usually much more efficient than refreshing after each document.

### NONE does not mean data is lost

`NONE` only indicates the request does not ask for a refresh. It does not mean Elasticsearch skips the write or fails to save the document.

Distinguish between:

- Write response success: the write operation was processed and acknowledged under the request's semantics.
- Search visibility: the document can now be queried via the Search API.
- Durability: the ability to recover data after a failure, involving the translog, commits, and storage configuration.

Do not use Search API visibility as the sole proof of data durability.

## 5. IMMEDIATE: refresh immediately

`RefreshPolicy.IMMEDIATE` corresponds to `refresh=true`.

After the write operation finishes, Elasticsearch refreshes the affected primary and replica shards so changes are immediately searchable.

Example:

~~~http
PUT /products/_doc/p-103?refresh=true
{
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 1500000
}
~~~

Once the request returns success, the application can run the Search API and find the new document without waiting for the next automatic refresh cycle.

### Which shards does IMMEDIATE affect?

Elasticsearch does not necessarily refresh the entire index in every case. The refresh targets the shards involved in the write operation, including the primary and corresponding replicas.

This can still incur significant cost, especially when the application writes frequently or has many shards.

### Why is IMMEDIATE resource-intensive?

Refreshes create small searchable segments. If the application continuously forces refreshes:

- The index can accumulate many small segments.
- Search has to process more segments.
- Merging has to work harder to consolidate segments.
- CPU, I/O, and latency can rise.
- Indexing throughput can drop.

The cost of immediate refresh is not limited to write time. It can also affect subsequent queries and merge operations.

### When should IMMEDIATE be used?

Use it only when the business flow genuinely requires search results immediately after the write completes and forcing a refresh is an intentional choice.

An example might be a very rare administrative action that updates a configuration and immediately verifies it via the Search API.

Do not set `IMMEDIATE` on all write operations simply to avoid near real-time delay, which is normal Elasticsearch behavior.

## 6. WAIT_UNTIL: wait until the next refresh

`RefreshPolicy.WAIT_UNTIL` corresponds to `refresh=wait_for`.

With this policy, Elasticsearch does not proactively force an immediate refresh. The request is held until a refresh makes its changes searchable.

Example:

~~~http
PUT /products/_doc/p-104?refresh=wait_for
{
  "name": "Office Chair",
  "category": "furniture",
  "price": 2400000
}
~~~

When the request returns, the document is already searchable. The application can execute a subsequent search query without adding its own sleep interval.

### How does WAIT_UNTIL work?

Suppose `index.refresh_interval` is `1s`:

~~~text
T0: Application sends write request with refresh=wait_for
 |
 v
T1: Elasticsearch writes document and acknowledges the write processing
 |
 v
   Request waits for refresh
 |
 v
T2: Automatic refresh occurs
 |
 v
T3: Document becomes searchable
 |
 v
T4: Write request returns response to application
~~~

Wait duration depends on when the next refresh occurs. If the request arrives right before a refresh, the wait can be very short. If it just missed a refresh, the request may wait nearly the entire next cycle.

This is not a guarantee that the request always finishes in exactly one second. Latency also depends on cluster load, refresh scheduling, shard count, and waiting requests.

### When should WAIT_UNTIL be used?

`WAIT_UNTIL` suits flows such as:

1. A user creates or updates a document.
2. The backend needs to wait for the document to be searchable.
3. The backend runs a follow-up query based on the newly written data.
4. The backend returns results to the user.

For example, after creating a product, the screen navigates to a search page and needs to show that product in the list right away. `WAIT_UNTIL` guarantees searchability before the write request finishes.

Compared to `IMMEDIATE`, `WAIT_UNTIL` generally leverages the upcoming automatic refresh or another ongoing refresh, avoiding forcing a separate refresh for each request.

## 7. WAIT_UNTIL and index.refresh_interval = -1

Automatic refresh can be disabled via configuration:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

When automatic refresh is disabled:

- `NONE` continues to request no refresh.
- `IMMEDIATE` can still trigger an immediate refresh.
- `WAIT_UNTIL` can wait indefinitely if nothing else triggers a refresh.

A manual refresh or another request using `refresh=true` can unblock requests waiting on `WAIT_UNTIL`.

This is an important detail in bulk indexing workflows. If a job disables automatic refresh to speed up ingest but sends a `WAIT_UNTIL` request and awaits its response before any refresh occurs, the job can hang at that step.

After bulk indexing completes, the application can re-enable the refresh interval and run an intentional refresh if immediate searchability is needed.

## 8. WAIT_UNTIL can force a refresh in special cases

Elasticsearch limits the number of requests waiting for a refresh per shard via the `index.max_refresh_listeners` setting. The default value is 1,000.

If the number of waiting requests on a shard reaches this limit, a new request using `refresh=wait_for` can behave like `refresh=true` and force a refresh to avoid holding waiting requests indefinitely.

In that case, the response may contain:

~~~json
{
  "forced_refresh": true
}
~~~

This means the request forced a refresh instead of merely waiting for the next one.

For the Bulk API, a single bulk request consumes only one refresh listener per shard it touches, regardless of how many write operations target that shard. Therefore, batching multiple operations into one bulk request is usually better than sending many individual `WAIT_UNTIL` requests.

## 9. Refresh policy in Index, Update, Delete, and Bulk APIs

Elasticsearch supports the `refresh` parameter on primary write APIs such as Index, Update, Delete, and Bulk.

### Index API

~~~http
PUT /products/_doc/p-105?refresh=wait_for
{
  "name": "Standing Desk",
  "category": "furniture",
  "price": 5200000
}
~~~

### Update API

~~~http
POST /products/_update/p-105?refresh=wait_for
{
  "doc": {
    "price": 5400000
  }
}
~~~

### Delete API

~~~http
DELETE /products/_doc/p-105?refresh=true
~~~

### Bulk API

~~~http
POST /products/_bulk?refresh=wait_for
{"index":{"_index":"products","_id":"p-106"}}
{"name":"Monitor Stand","category":"accessories","price":700000}
{"index":{"_index":"products","_id":"p-107"}}
{"name":"Desk Lamp","category":"furniture","price":450000}
~~~

The `refresh` parameter is set at the Bulk request level and applies to the operations within that request.

There is no need to invoke refresh separately for every action in a bulk request. When all changes in a batch need to be searchable before proceeding, use a single bulk request with `refresh=wait_for`.

## 10. Refresh policy is not a Search API parameter

Refresh policy controls behavior after a write operation. It is not an option to make the Search API refresh an index.

For example, the following request makes no sense as a mechanism to wait for a refresh:

~~~http
GET /products/_search?refresh=wait_for
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

To control when data becomes searchable, place the policy on the write request. The Search API simply reads already-searchable data at the time it executes.

If the application needs to search for a newly written document:

1. Send the write request with `WAIT_UNTIL`.
2. Wait for the write response to complete.
3. Send the Search API request normally.

There is no need to pass a refresh policy on the subsequent search request.

## 11. Manual refresh with the Refresh API

Elasticsearch provides the Refresh API:

~~~http
POST /products/_refresh
~~~

This API requests a refresh of the specified index's shards. It can be used when:

- Verifying data in development environments.
- Finishing an ingest batch and needing to make the data searchable.
- Performing an intentional administrative task.

Do not call the Refresh API after every document or every user request. That can create the same kind of overhead as overusing `IMMEDIATE`.

In tests, an intentional refresh can be used after preparing test data. However, if you want to test refresh policy semantics, test all three modes rather than always calling manual refresh to mask latency.

## 12. Configuring RefreshPolicy in Spring Data Elasticsearch

Spring Data Elasticsearch defines the enum:

`org.springframework.data.elasticsearch.core.RefreshPolicy`

Three values:

~~~java
public enum RefreshPolicy {
    NONE,
    IMMEDIATE,
    WAIT_UNTIL
}
~~~

Mapping to Elasticsearch:

| Spring Data | REST API |
|---|---|
| `RefreshPolicy.NONE` | `refresh=false` |
| `RefreshPolicy.IMMEDIATE` | `refresh=true` |
| `RefreshPolicy.WAIT_UNTIL` | `refresh=wait_for` |

This enum has been provided by Spring Data Elasticsearch since version 4.2. Starting in version 4.2, the package used is `org.springframework.data.elasticsearch.core.RefreshPolicy` instead of the refresh policy enum from the legacy Elasticsearch Java client.

When using current Spring Data Elasticsearch, import:

~~~java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
~~~

Do not confuse it with:

~~~java
import org.elasticsearch.action.support.WriteRequest.RefreshPolicy;
~~~

The second import belongs to the legacy client API and is not the enum type required by current Spring Data.

## 13. Setting a policy for an operation with ElasticsearchOperations

`ElasticsearchOperations` provides `withRefreshPolicy` to create an instance with the same configuration but using a different refresh policy.

Example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Product saveAndWaitUntilSearchable(Product product) {

        return operations
            .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
            .save(product);
    }
}
~~~

In this example:

- `withRefreshPolicy` returns a copy of operations with the new policy.
- `save` executes the write operation using that policy.
- When the method returns successfully, the change is searchable according to WAIT_UNTIL semantics.

Other policies can be used:

~~~java
operations.withRefreshPolicy(RefreshPolicy.NONE).save(product);

operations.withRefreshPolicy(RefreshPolicy.IMMEDIATE).save(product);

operations.withRefreshPolicy(RefreshPolicy.WAIT_UNTIL).save(product);
~~~

`withRefreshPolicy` was introduced in Spring Data Elasticsearch 5.2. It is useful when only certain operations need a specific policy without altering the global configuration of the entire template.

It can also be applied to delete operations or multi-document writes via the corresponding methods on `ElasticsearchOperations`.

## 14. Setting a policy directly on ElasticsearchRepository

`ElasticsearchRepository` has overloads accepting `RefreshPolicy` for several write operations.

Example:

~~~java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Service:

~~~java
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product saveAndWait(Product product) {
        return repository.save(product, RefreshPolicy.WAIT_UNTIL);
    }

    public Iterable<Product> saveBatch(Iterable<Product> products) {
        return repository.saveAll(products, RefreshPolicy.NONE);
    }

    public void deleteAndRefresh(String id) {
        repository.deleteById(id, RefreshPolicy.IMMEDIATE);
    }
}
~~~

Overloads are available for:

- `save(entity, refreshPolicy)`.
- `saveAll(entities, refreshPolicy)`.
- `delete(entity, refreshPolicy)`.
- `deleteById(id, refreshPolicy)`.
- `deleteAll(...)` with the corresponding policy.

The overloads accepting a refresh policy have been available since Spring Data Elasticsearch 5.2.

The convenience here is choosing the policy directly at the repository call site. This clearly expresses each business flow's requirement: batch imports use NONE, while operations needing immediate search use WAIT_UNTIL.

## 15. Default policy configuration and notes on null

Spring Data can use a refresh policy at the template/operations level. However, distinguish two states:

- `null`: no explicit refresh policy is set, letting the integration layer or cluster defaults decide.
- `RefreshPolicy.NONE`: actively requests taking no refresh action for the write request.

These two states are not necessarily equivalent across every Spring Data code path.

Since the change in Spring Data Elasticsearch 4.2:

- `ElasticsearchOperations` and `ReactiveElasticsearchOperations` use the policy configured on the template if it is non-null. If the policy is null, the template sets no explicit refresh action and lets cluster defaults apply.
- Built-in Spring Data repository implementations perform an explicit refresh when the policy is null. If a specific policy is passed, the repository uses that policy.

Therefore, do not infer that `repository.save(entity)` and `operations.save(entity)` always share the exact same default refresh behavior just because both write an entity.

If you need explicit, consistent behavior, pass the policy explicitly or use `withRefreshPolicy`.

Example setting a policy on a single operation:

~~~java
Product saved = repository.save(
    product,
    RefreshPolicy.NONE
);
~~~

Example setting a policy on operations:

~~~java
ElasticsearchOperations noRefreshOperations =
    operations.withRefreshPolicy(RefreshPolicy.NONE);

Product saved = noRefreshOperations.save(product);
~~~

When reading older code, check the Spring Data Elasticsearch version and the call path being used. Default rules have changed across the framework's history, especially in versions 4.2 and above.

## 16. Reactive Elasticsearch and refresh policies

Spring Data Elasticsearch also provides reactive APIs using the same `RefreshPolicy` enum as the synchronous API.

Example:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import reactor.core.publisher.Mono;

public Mono<Product> saveAndWait(Product product) {
    return reactiveOperations
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .save(product);
}
~~~

Reactive repositories also provide overloads accepting a policy:

~~~java
Mono<Product> saved =
    reactiveProductRepository.save(
        product,
        RefreshPolicy.WAIT_UNTIL
    );
~~~

In a reactive flow, the request still waits until Elasticsearch satisfies the policy. Using `Mono` does not make refreshes instantaneous or eliminate wait time. It simply represents the asynchronous operation in a reactive model.

If there are many writes, consider batching them and choosing a batch-level policy to reduce the number of waiting requests.

## 17. WAIT_UNTIL in integration testing

A common scenario in integration tests:

1. Save a document.
2. Search for the newly saved document.
3. Verify the results.

If using NONE, the search step may execute before the automatic refresh and miss the document. The test becomes dependent on execution timing, causing flakiness.

Do not solve this by adding `Thread.sleep(...)`:

~~~java
repository.save(product);
Thread.sleep(1000);
List<Product> results = searchProducts();
~~~

This approach has several drawbacks:

- Does not guarantee a refresh occurred after exactly one second.
- Slows down tests.
- Can still fail under high system load.
- Fails to express the searchability requirement clearly.

You can use WAIT_UNTIL:

~~~java
repository.save(product, RefreshPolicy.WAIT_UNTIL);

List<Product> results = searchProducts();

assertThat(results)
    .extracting(Product::getId)
    .contains(product.getId());
~~~

When the write response returns, the document is searchable. The test does not need to guess refresh timing.

If a test prepares hundreds of documents, use `saveAll` or the Bulk API once with WAIT_UNTIL rather than calling WAIT_UNTIL on every individual document.

## 18. Batch indexing and policy selection

Suppose a system imports 50,000 products.

Writing one document at a time with IMMEDIATE:

~~~text
Index product 1  -> refresh
Index product 2  -> refresh
Index product 3  -> refresh
...
Index product 50,000 -> refresh
~~~

This can trigger a massive number of refreshes, degrading throughput and increasing the number of small segments.

A better approach:

~~~text
Batch 1: write 5,000 documents
Batch 2: write 5,000 documents
Batch 3: write 5,000 documents
...
Batch 10: write 5,000 documents
             |
             v
Bulk request with NONE
             |
             v
Let automatic refresh run
             |
             v
If immediately searchable is needed:
Final bulk request with WAIT_UNTIL
~~~

If the application needs complete control over the refresh cycle during a bulk import, it can:

1. Temporarily disable automatic refresh using `index.refresh_interval = -1`.
2. Execute bulk indexing with NONE.
3. Restore the refresh interval.
4. Trigger one manual refresh or send an operation waiting for refresh.
5. Resume the search flow.

This workflow must be carefully controlled because disabling refresh affects all clients searching that index. Do not apply it to a live production index serving real-time queries without assessing the impact.

## 19. Refresh policy does not solve concurrency or optimistic locking

Refresh policy only controls when changes become searchable. It does not solve concurrency issues when multiple clients update the same document.

For example:

- Client A reads an old version of the document.
- Client B updates the document.
- Client A sends an update based on stale data.

Using `WAIT_UNTIL` or `IMMEDIATE` does not stop Client A from overwriting Client B's change.

To handle write conflicts, consider optimistic concurrency control with `if_seq_no` and `if_primary_term`, or an appropriate versioning mechanism.

Similarly, refresh does not replace replication, acknowledgement, or durability mechanisms. It only determines when data becomes searchable.

## 20. Relationship between real-time GET and near real-time Search

A common point of confusion is that after a successful write, a GET by ID can see the document before the Search API sees it.

Example:

~~~http
PUT /products/_doc/p-108
{
  "name": "Desk Lamp",
  "category": "furniture"
}
~~~

Immediately afterward, GET by ID:

~~~http
GET /products/_doc/p-108
~~~

The Get API operates in real-time by default and can return the newly written document without waiting for a refresh.

Meanwhile, the Search API:

~~~http
GET /products/_search
{
  "query": {
    "ids": {
      "values": ["p-108"]
    }
  }
}
~~~

still might not find the document until the next refresh.

This is not a contradiction. GET by ID and the Search API use different read paths.

If the business logic only needs to confirm the document was saved and read it back by ID, there is no need to force a refresh. If it needs to search by fields, filters, or full-text right after writing, consider WAIT_UNTIL.

## 21. Adjusting an index's refresh_interval

`index.refresh_interval` is an index setting controlling the automatic refresh cycle.

You can inspect it:

~~~http
GET /products/_settings?include_defaults=true
~~~

Change the refresh interval:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "5s"
  }
}
~~~

You can disable automatic refresh:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Re-enable it:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

This setting can be changed dynamically on an index. However, do not set the interval too low just so all WAIT_UNTIL requests respond faster. Refreshing too often increases segment creation and merge overhead.

The refresh interval should be chosen based on:

- Write frequency.
- Search frequency.
- Freshness latency requirements for new data.
- Shard count and segment sizes.
- Cluster CPU, I/O, and load.

Refresh interval and refresh policy are two different configuration layers: one controls the automatic refresh schedule, while the other controls how an individual write request interacts with refreshes.

## 22. Common mistakes

**Assuming a successful write means the Search API sees it immediately.** Write acknowledgement and search visibility are two different milestones. Use WAIT_UNTIL if searchability is needed before the response returns.

**Using IMMEDIATE for every write operation.** Frequent refreshes create many small segments and increase indexing, search, and merge overhead. Use it only when genuinely required.

**Using WAIT_UNTIL when automatic refresh is disabled.** When `refresh_interval` is `-1`, requests can wait indefinitely if nothing else triggers a refresh.

**Sending many sequential WAIT_UNTIL requests.** Each request must wait for a refresh. Batching operations into a single bulk request with WAIT_UNTIL is more efficient.

**Using Thread.sleep to wait for refresh.** Sleep does not guarantee a refresh has completed. Use WAIT_UNTIL to synchronize on actual refresh events.

**Confusing null with RefreshPolicy.NONE in Spring Data.** Null can trigger different default behaviors between operations and repositories. Pass an explicit policy when control is needed.

**Thinking the Refresh API is a document write operation.** The Refresh API only makes already-written changes searchable; it does not replace Index, Update, or Delete APIs.

**Confusing refresh with flush.** Refresh makes changes searchable; flush creates a Lucene commit and processes the translog. The two operations serve different purposes.

**Setting refresh policy on the Search API.** Refresh policy belongs on write requests. The Search API reads already-searchable data and does not use `refresh=wait_for` to wait for other writes.

**Assuming WAIT_UNTIL never forces a refresh.** If a shard's refresh listeners are full, Elasticsearch can force a refresh and return `forced_refresh: true`.

**Confusing real-time GET with the Search API.** GET by ID can see changes before the Search API sees them. This is normal near real-time search behavior.

**Thinking refresh resolves write conflicts.** Refresh does not replace optimistic concurrency control or versioning.

## 23. Process for choosing a refresh policy in an application

You can choose a policy using this process:

1. Determine whether the next operation needs to search for the newly written document.
2. If immediate searchability is not required, use `NONE`.
3. If searchability is needed before the write request returns, prefer considering `WAIT_UNTIL`.
4. Only use `IMMEDIATE` when there is a specific reason requiring an immediate refresh.
5. For multiple writes, group them into a Bulk API call or `saveAll`.
6. In Spring Data, choose an explicit policy via repository overloads or `ElasticsearchOperations.withRefreshPolicy`.
7. Check `index.refresh_interval`, especially if it is set to `-1`.
8. Do not use sleep or manual refresh after each document.
9. Monitor write latency, search visibility delay, and segment counts.
10. Verify the default behavior of your Spring Data Elasticsearch version if the policy is null.

## Conclusion

Refresh policy controls when written changes become searchable through the Search API. `NONE` requests no refresh and is generally suitable for normal write paths. `IMMEDIATE` refreshes affected shards right after the operation, which can increase indexing, search, and merge costs. `WAIT_UNTIL` waits for a refresh to make changes searchable before the write request returns, making it usually the right choice for immediate read-after-write via search.

In Spring Data Elasticsearch, the `RefreshPolicy` enum lives in the `org.springframework.data.elasticsearch.core` package and has three values mapping to the Elasticsearch REST API. You can set the policy per operation using `ElasticsearchOperations.withRefreshPolicy` or pass it directly to `ElasticsearchRepository` overloads. Distinguish `null` from `NONE` because default behaviors between operations and repositories can differ.

When designing write paths, default to NONE when immediate search is unnecessary, use WAIT_UNTIL when search visibility must be synchronized, and reserve IMMEDIATE for cases that genuinely require forcing a refresh. Combining bulk writes, a sensible refresh interval, and searchability-based testing helps applications balance latency with throughput.

## References

- [Elasticsearch — The refresh parameter](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/refresh-parameter)
- [Elasticsearch — Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
- [Elasticsearch — Index settings: refresh interval](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index)
- [Spring Data Elasticsearch — RefreshPolicy API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/RefreshPolicy.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch — ElasticsearchRepository API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/repository/ElasticsearchRepository.html)
- [Spring Data Elasticsearch — RefreshPolicy migration notes](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-4.1-4.2.html)
