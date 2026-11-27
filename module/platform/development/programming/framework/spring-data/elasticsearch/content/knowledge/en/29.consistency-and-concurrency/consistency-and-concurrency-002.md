# GET by ID and Search Have Different Consistency Characteristics

Elasticsearch provides two common ways to read documents: retrieving a single document by ID with the Get API and searching by criteria with the Search API. These two read paths have different consistency characteristics because they use different data-reading mechanisms.

**The Get API is real-time by default:** after an index/update/delete operation is accepted, the application can read the latest state of the document by ID without waiting for a refresh.

**The Search API is near-real-time:** search only sees changes that have been refreshed into searchable segments. A newly written document may be readable immediately via GET while not yet appearing in search results.

This is intentional behavior allowing Elasticsearch to balance write speed and searchability. When designing a Spring Data Elasticsearch application, you need to choose the right read path for the need: reading a single document immediately by ID, searching documents by content/criteria, or requiring read-after-write for a search query.

## 1. Two ways to read data

### Get by ID

The Get API retrieves a specific document from an index based on `_id`:

```http
GET /products/_doc/P-100
```

This is the right choice when the application already knows the ID and needs to read a single document. The Get API is real-time by default and does not depend on the index's refresh interval.

### Search by criteria

The Search API finds a set of documents matching a query:

```http
GET /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

The Search API operates under the near-real-time model. It searches over refreshed data and may not yet see a recently completed write if a refresh has not occurred.

| Characteristic | Get API | Search API |
|---|---|---|
| Document selection | By `_id` and optional routing. | By query, filter, sort, and aggregation. |
| Default visibility | Real-time. | Near-real-time. |
| Depends on refresh to see new writes | No, with default `realtime=true`. | Yes. |
| Can read a document by ID | Yes, its primary purpose. | Can query by ID, but not the Get API mechanism. |
| Best suited for | Read-after-write by ID, single-entity details. | Searching, filtering, ranking, aggregations, and lists. |

Do not interpret "real-time GET" to mean all reads across the entire cluster have strong transactional snapshots. It is a property of fetching a document by ID on the corresponding shard; multi-document and multi-shard searches have their own semantics.

## 2. Why does GET see new data before Search?

Elasticsearch writes documents into internal structures and the translog. The Get API can read the latest version of a document even before the document has been made visible in a new searcher. The Search API reads segments that have been refreshed to be searchable.

Simplified process:

```text
Client
  |
  | index/update/delete
  v
Elasticsearch shard
  |
  +---- writes changes and translog
  |          |
  |          +----> Real-time GET can see the new version
  |
  +---- waits for refresh
             |
             v
       Opens new searcher
             |
             +----> Search sees the change
```

Therefore, right after indexing a document:

- `GET /products/_doc/P-100` can return the new document.
- A search query matching that document might not return results yet.
- After a refresh, search will see the new document.

This is not a data error or a caching bug. It is the difference between real-time document retrieval and near-real-time search visibility.

## 3. Example: after indexing, GET sees it while Search does not

Suppose the `products` index exists and the application creates a product:

```http
PUT /products/_doc/P-100
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "status": "ACTIVE",
  "price": 2500000
}
```

After the write request returns successfully, read by ID:

```http
GET /products/_doc/P-100
```

The Get API can return the newly created document immediately.

However, searching by status:

```http
GET /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

might not include `P-100` if the shard has not refreshed since the write.

After refreshing the index:

```http
POST /products/_refresh
```

running the Search API again will find the document.

Key point to remember: a successful response from an index operation means Elasticsearch accepted/processed the write according to the API semantics. It does not inherently mean the document is immediately searchable in the Search API.

## 4. GET can be switched to non-real-time mode

The Get API has a `realtime` parameter. The default is `true`:

```http
GET /products/_doc/P-100?realtime=true
```

When `realtime=true`, GET can read the latest unrefreshed version.

If you set `realtime=false`:

```http
GET /products/_doc/P-100?realtime=false
```

GET reads only from the refreshed searchable view. In that case, it may not yet see the latest change, similar to search visibility.

`realtime=false` is useful when you want to verify the already-searchable state rather than the latest document state by ID. In normal applications, there is no need to disable real-time mode unless there is a specific requirement.

## 5. What is a refresh?

A refresh makes indexed changes searchable by opening a new searcher over the relevant segments. This is the step that establishes visibility through the Search API.

Refresh is distinct from flush and from durable persistence:

| Mechanism | Role |
|---|---|
| Index/update/delete | Writes document changes. |
| Translog | Records operations to support recovery/durability as configured. |
| Refresh | Makes changes visible through the Search API. |
| Flush | Creates a Lucene commit and manages the translog; a different mechanism from refresh. |

Do not call refresh a "transaction commit." Refresh primarily addresses search visibility. Durability and recovery have their own mechanisms, in which the translog and flush play distinct roles.

### 5.1. Refresh interval

Elasticsearch automatically refreshes an index according to its refresh interval. The default is commonly around one second for indices actively receiving searches, though it can vary by settings, version, and index activity state.

Applications should not rely on a fixed duration such as "wait exactly one second and search is guaranteed to see it." If you need guaranteed visibility for a specific write operation, use an appropriate refresh policy instead of `Thread.sleep`.

### 5.2. Refresh has a cost

Refresh is generally lighter than a flush, but it is not free. Refreshing too often can create many small segments, increase merge costs, and reduce indexing throughput.

Therefore:

- Do not refresh after every document unless necessary.
- Do not call refresh on every write request just to work around a read-after-write issue at the application layer.
- For large imports/bulk loads, typically write in batches and refresh when ready to publish the data.
- Choose the refresh interval based on freshness requirements and actual workload.

## 6. Refresh options when writing

Elasticsearch write APIs support the `refresh` parameter with three common choices:

| Value | Meaning | Consequence |
|---|---|---|
| `false` | Do not request an extra refresh. This is the common default. | Search sees the data after the next refresh. |
| `true` | Immediately refresh affected shards before the response completes. | Faster read-after-write via search, but may reduce throughput. |
| `wait_for` | Wait for the next refresh to make changes searchable. | Avoids forcing an immediate separate refresh, but the response may wait. |

### 6.1. `refresh=true`

Example:

```http
PUT /products/_doc/P-101?refresh=true
Content-Type: application/json

{
  "name": "Wireless Mouse",
  "status": "ACTIVE",
  "price": 450000
}
```

When the request completes, the write has been refreshed on the affected shards and search can see the change.

This is an aggressive way to achieve immediate search visibility after a write, and frequent use can trigger many unnecessary refreshes. Use it only when latency/visibility requirements truly demand it and the impact has been evaluated.

### 6.2. `refresh=wait_for`

Example:

```http
PUT /products/_doc/P-102?refresh=wait_for
Content-Type: application/json

{
  "name": "USB-C Hub",
  "status": "ACTIVE",
  "price": 850000
}
```

Elasticsearch waits for the next refresh to make the document searchable before completing the response. `wait_for` is generally preferable to `true` for read-after-write via search when the application can afford to wait for a refresh interval.

If automatic refresh is disabled, for example `refresh_interval=-1`, a `wait_for` request may wait until another refresh operation occurs or a timeout expires. When using this mode, you must understand the index's refresh configuration.

### 6.3. `refresh=false`

Example:

```http
PUT /products/_doc/P-103?refresh=false
Content-Type: application/json

{
  "name": "Monitor Stand",
  "status": "ACTIVE",
  "price": 650000
}
```

The request does not ask for a refresh. This is the right option for standard write throughput when search visibility can wait for the natural refresh cycle.

## 7. Read-after-write: choosing a strategy by requirement

No single read pattern fits every case. Check whether the application needs to read by ID or search by conditions.

| Need | Approach |
|---|---|
| Immediately display the newly saved entity by ID | Use real-time GET by ID. |
| Immediately find the entity via query/search | Write with `refresh=wait_for` or refresh appropriately before searching. |
| Write many documents and then show a list | Bulk write, then refresh once when done if needed. |
| No need for immediate search visibility | Keep default `refresh=false`, accepting near-real-time. |
| Need to verify data is already searchable | Use search after refresh or GET with `realtime=false` for a known ID. |
| Need to read the latest state of a document in an update flow | Real-time GET by ID and handle concurrency/versioning. |

### 7.1. Do not use search instead of GET when the ID is known

If the UI just created a product and needs to navigate to its details page, you do not need to search with a `term` query on the ID. Using GET by ID is natural and can read the newly written version immediately.

Conversely, if the UI needs to refresh a list of "all active products under 1 million," that is a search query. A real-time GET of a single document does not make the list query see the change on its own.

## 8. GET and Search after an Update

The difference does not only appear on creation. After an update, GET can see the new content while Search still returns the old content until a refresh occurs.

Example initial document:

```json
{
  "name": "Mechanical Keyboard",
  "status": "ACTIVE",
  "price": 2500000
}
```

Update the price:

```http
POST /products/_update/P-100
Content-Type: application/json

{
  "doc": {
    "price": 2300000
  }
}
```

Immediately after the update succeeds:

- GET by ID can return `price = 2300000`.
- A search query may still return the previous searchable version with `price = 2500000` or evaluate the document against the old data.
- After refresh, search sees the new version.

If a query depends on the updated field, such as `price <= 2400000`, the document might not appear in the new results yet even though GET already shows the new price.

## 9. GET and Search after a Delete

Deletes also clearly show the visibility difference.

Delete the document:

```http
DELETE /products/_doc/P-100
```

After the delete is accepted:

- Real-time GET by ID can return 404 immediately.
- Search may still return the old document until the delete is refreshed and becomes searchable.

This can cause a list screen to temporarily display a document that was just deleted, while the detail page by ID already reports not found.

If business logic requires search lists to reflect deletes immediately after the operation, use an appropriate refresh policy. If the UI accepts near-real-time behavior, you can update the UI optimistically or wait for the natural refresh.

## 10. Spring Data Elasticsearch: `get` and `search`

Spring Data Elasticsearch provides two corresponding API paths:

- `ElasticsearchOperations.get(id, Entity.class)` retrieves an entity by ID.
- `ElasticsearchOperations.search(query, Entity.class)` runs a search and returns `SearchHits<Entity>`.

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

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private double price;

    // constructors, getters, setters
}
```

Save and then read by ID:

```java
ProductDocument saved = operations.save(product);

ProductDocument loaded = operations.get(
        saved.getId(),
        ProductDocument.class
);
```

`get` uses the get-document-by-ID operation and has Elasticsearch's real-time semantics by default.

Search by criteria:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query activeQuery = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(activeQuery)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

`search` uses the Search API, so it only sees refreshed data. If you call `save` and immediately search, the results might not yet contain the newly saved entity.

### 10.1. Repositories exhibit the same difference

With a Spring Data repository:

```java
Optional<ProductDocument> byId = productRepository.findById("P-100");
```

`findById` is a read-by-ID operation. Query methods such as:

```java
List<ProductDocument> activeProducts =
        productRepository.findByStatus("ACTIVE");
```

are executed as search queries. Therefore, the two methods may temporarily return different results right after a write.

When designing services, do not assume every repository method shares the same freshness semantics. Identify which methods go through the Get API and which issue Search API queries.

## 11. Refreshing with Spring Data Elasticsearch

If you need data to be searchable before running a search, you can call refresh via `IndexOperations`:

```java
operations.save(product);

operations.indexOps(ProductDocument.class).refresh();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Refresh makes indexed changes on the corresponding index visible through the Search API. Only call it when there is a clear requirement; using it on every write request can reduce throughput.

### 11.1. Refresh after bulk import

For multi-batch imports:

```java
for (List<IndexQuery> batch : batches) {
    operations.bulkIndex(batch, ProductDocument.class);
}

operations.indexOps(ProductDocument.class).refresh();
```

This pattern avoids refreshing after each batch and only makes data searchable once the full import completes. In production applications, ensure all bulk items have been processed and errors handled before refreshing/publishing.

### 11.2. Refresh policy for the Bulk API

Spring Data Elasticsearch provides `BulkOptions` to configure the refresh policy for bulk operations in supported versions:

```java
import org.springframework.data.elasticsearch.core.BulkOptions;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        ProductDocument.class
);
```

`WAIT_UNTIL` waits for the next refresh to make the changes searchable. You can choose `IMMEDIATE` or `NONE` depending on requirements and API version. For large bulk loads, `NONE` followed by a single refresh upon completion generally reduces forced refreshes.

Enum names, packages, and `BulkOptions` overloads can differ across Spring Data Elasticsearch versions; use APIs compatible with your project's dependencies.

## 12. GET with custom routing

If a document was indexed with custom routing, the Get API must receive the same routing value. For example:

```http
PUT /orders/_doc/O-100?routing=customer-42
{
  "customer_id": "customer-42",
  "status": "PAID"
}
```

Reading by ID requires the routing:

```http
GET /orders/_doc/O-100?routing=customer-42
```

If routing is omitted, the request may look on the wrong shard and return 404. This is not a refresh issue; the document may already exist but was routed to a different shard.

In Spring Data, you can configure routing for get-by-ID operations:

```java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;

OrderDocument order = operations
        .withRouting(RoutingResolver.just("customer-42"))
        .get("O-100", OrderDocument.class);
```

Distinguish the two causes:

- GET does not find the document due to wrong/missing routing.
- Search does not see the document because data has not been refreshed.

Waiting for a refresh will not fix a routing error.

## 13. Search consistency in multi-shard environments

A search request can be distributed across multiple shards. Each shard has its own searcher/refresh state. Elasticsearch does not provide a cluster-wide transactional snapshot for ordinary Search API requests.

Several consequences follow:

- Changes on different shards may become searchable at different times.
- A search across multiple shards may observe refresh states that are not strictly simultaneous across shards.
- A subsequent search request may see additional documents after a shard refreshes.
- Replica selection and shard copy state can affect which shard copy serves the search.

Therefore, do not describe the Search API as a consistent transactional snapshot across all documents and shards. It is a query over the searchers available at the moment the request executes.

If you need to paginate over a stable result set across multiple requests, you can use Point in Time (PIT) combined with `search_after`. PIT preserves a stable search view for subsequent pages, though it does not include writes that occur after the PIT was opened.

## 14. Preference and refresh do not solve the same problem

The Search API has a `preference` parameter to control shard copy selection or selection stability in certain cases. For example, `_primary` requests searching on primary shard copies.

However, `preference=_primary` does not replace refresh. If the primary shard has not refreshed, searching on the primary still may not see the latest changes.

Similarly, simply selecting the same replica does not guarantee new data is already searchable. For changes to appear in search, proper refresh visibility is required.

## 15. Real-time GET does not replace optimistic concurrency control

GET by ID can return the latest currently available version of a document, but if multiple clients read and then update concurrently, there is still a risk of lost updates.

For example:

1. Client A reads stock quantity as 10.
2. Client B also reads stock quantity as 10.
3. A updates it to 9.
4. B updates it based on the stale value to 8.

Without concurrency control, one update can overwrite the other.

Elasticsearch supports optimistic concurrency control using `_seq_no` and `_primary_term`.

Read the document with metadata:

```http
GET /products/_doc/P-100?seq_no_primary_term=true
```

The response includes `_seq_no` and `_primary_term`. When writing an update, send both values back:

```http
PUT /products/_doc/P-100?if_seq_no=7&if_primary_term=3
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "status": "ACTIVE",
  "price": 2300000
}
```

Elasticsearch only accepts the update if the document still has the matching sequence number and primary term. If another client updated it first, the request can return `409 version conflict`.

The application needs to reload the document, reapply the business change, or report the conflict to the user. Do not retry the same stale payload indefinitely.

### 15.1. Distinguishing refresh consistency from write concurrency

Two issues are often confused:

| Issue | Question | Mechanism |
|---|---|---|
| Search visibility | Has search seen the new write yet? | Refresh, `refresh=wait_for`, refresh interval. |
| Lost update | Will one client overwrite another client's change? | Optimistic concurrency control, `_seq_no`, `_primary_term`, versioning. |
| Multi-page snapshot | Do pages see the same dataset? | PIT + `search_after` or Scroll. |
| Finding the right shard | Does GET reach the shard holding the document? | Consistent routing value. |

Refresh does not prevent lost updates. OCC does not make documents immediately searchable. PIT does not make new writes appear in the snapshot. Routing does not replace the other mechanisms.

## 16. Practical scenarios and appropriate choices

### 16.1. Create an order and open the details page

After saving an order, the application already knows the returned ID. Use GET by ID to render the details page. No refresh is needed just for GET to see the document.

### 16.2. Create a product and update the search listing

If the UI immediately runs a search to find the new product by name or category, you need `refresh=wait_for` on the write operation or an appropriate refresh before searching. Otherwise, the product may be missing from the list briefly.

### 16.3. Update status and then filter the list

For example, transitioning an order from `PENDING` to `PAID`. GET by ID can return `PAID` immediately, while a search filter `status=PENDING` may still return the order until a refresh happens. If the UI needs the list to reflect the change immediately, choose the appropriate visibility policy.

### 16.4. Delete a document and verify by ID

GET by ID can return 404 right after delete. Search may still return the old document until a refresh occurs. If a deletion flow must confirm the document no longer appears in search queries, wait for refresh visibility.

### 16.5. Bulk import and then open a dashboard

Do not refresh per document or per batch if the dashboard only needs data once the import finishes. Finish importing, check item errors, refresh the index once, and then open the dashboard.

## 17. Testing the difference between GET and Search

You should have integration tests with a real Elasticsearch instance or Testcontainers. Mocking `ElasticsearchOperations` cannot verify refresh behavior and real-time GET.

### 17.1. Testing a new index

1. Create a test index.
2. Index document `P-100` without requesting a refresh.
3. Call the Get API by ID and assert the document exists.
4. Call the Search API with a matching query and observe it may not see the document yet.
5. Call index refresh.
6. Run the Search API again and assert the document appears.

To make the test deterministic, you can disable automatic refresh on the test index with `refresh_interval=-1`, then trigger refresh explicitly in step 5. This eliminates races with background refreshes.

### 17.2. Testing update

1. Index an initial document and refresh.
2. Update a field.
3. GET by ID and assert the new value.
4. Search for the new value before refresh and confirm it is not yet seen in the old searchable snapshot.
5. Refresh, then search again and assert the new value.

### 17.3. Testing delete

1. Index a document and refresh.
2. Delete the document.
3. GET by ID and assert 404.
4. Search before refresh may still see the old document.
5. Refresh, then search again and confirm the document is gone.

### 17.4. Testing `realtime=false`

After indexing a document without refreshing:

- Default GET can see the document.
- GET with `realtime=false` may not see the document yet.
- After refresh, both non-real-time GET and Search can see the new state.

### 17.5. Avoid testing with `Thread.sleep`

Do not write tests like:

```java
Thread.sleep(1000);
assertThat(search(...)).isNotEmpty();
```

Tests can be flaky due to refresh interval, machine load, and timing. Call the refresh API or use `refresh=wait_for` to synchronize using actual mechanisms.

## 18. Common mistakes

| Symptom | Possible cause | How to handle |
|---|---|---|
| Save succeeds but search misses the document | Document has not been refreshed yet. | Use `refresh=wait_for` or refresh when truly needed. |
| GET finds the document but search list omits it | GET is real-time, Search is near-real-time. | Normal semantics; synchronize search visibility. |
| GET returns 404 even though document is in the index | Custom routing not passed, or wrong ID/index. | Verify index, ID, and routing. |
| GET returns new data but search still returns old field | Update has not refreshed yet. | Wait for refresh or use a refresh policy. |
| Delete succeeds but search still returns document | Delete is not searchable yet due to missing refresh. | Refresh before verifying with search. |
| Using `realtime=false` still shows old state | Searcher has not been refreshed. | Refresh the index or wait for natural refresh. |
| Calling `refresh=true` on every request slows indexing | Too-frequent refreshes create overhead. | Use `wait_for`, batch refreshes, or accept NRT. |
| `Thread.sleep` causes flaky pass/fail tests | Refresh timing is not synchronized. | Use the refresh API or `refresh=wait_for`. |
| Searching on primary still misses write | `preference=_primary` does not force a refresh. | Address refresh visibility. |
| One client overwrites another client's update | Missing optimistic concurrency control. | Use `_seq_no`/`_primary_term` or versioning. |
| PIT does not see newly written documents | PIT holds a snapshot at open time. | Open a new PIT if new data must be seen. |
| Read-after-write only fails for certain tenants | Inconsistent routing values. | Use the same routing for index and get. |

## 19. Read-after-write selection process

When designing a write-then-read flow, follow these steps:

1. **Determine the read type:** reading a single document by ID or searching by query?
2. **If the ID is known:** use Get API/Spring Data `get` to leverage real-time GET.
3. **If search is needed:** decide whether immediate visibility is required or near-real-time is acceptable.
4. **If immediate search is needed:** choose `refresh=wait_for` or a controlled refresh.
5. **If writing many items:** batch them and refresh once upon completion if appropriate.
6. **If there are multiple writers:** use OCC/versioning to avoid lost updates.
7. **If paginating across multiple requests:** consider PIT + `search_after` when a stable snapshot is needed.
8. **If using custom routing:** pass the exact routing to the Get API by ID.
9. **Test:** verify GET, Search, update, delete, and refresh with integration tests.

## 20. Key takeaways

- The Get API by ID is real-time by default and does not need a refresh to see new writes.
- The Search API is near-real-time; it only sees changes after the shard is refreshed.
- Consequently, GET can see a new document while Search does not yet, or GET can return 404 after a delete while Search still sees the old document.
- `realtime=false` makes GET read only the refreshed searchable state.
- Refresh makes changes searchable; it differs from flush and is not a transaction commit.
- `refresh=true` forces an immediate refresh and can reduce throughput; `refresh=wait_for` waits for the next refresh; `false` requests no refresh.
- Spring Data `ElasticsearchOperations.get` reads by ID; `search` executes the Search API.
- `operations.indexOps(Entity.class).refresh()` can be used to refresh an index when needed.
- Do not use `Thread.sleep` to wait for search visibility; synchronize with the refresh API or `wait_for`.
- `preference=_primary` does not substitute for refresh.
- Real-time GET does not prevent lost updates; use `_seq_no` and `_primary_term` or versioning.
- PIT maintains a stable search view across requests, but does not include writes made after the PIT was opened.
- If using custom routing, GET by ID needs the same routing used during indexing.

GET and Search serve two different goals and thus have different consistency semantics. Use GET when you already know the ID and need the latest state of a single document; use Search for querying across a dataset and accept near-real-time behavior or explicitly synchronize with a refresh policy when read-after-write is required. Understanding this boundary helps Spring Data Elasticsearch applications avoid "write succeeded but search didn't find it" issues while maintaining good throughput.

## References

- [Elasticsearch — Get API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-get.html)
- [Elasticsearch — Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html)
- [Elasticsearch — Refresh API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)
- [Elasticsearch — Index API refresh parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
