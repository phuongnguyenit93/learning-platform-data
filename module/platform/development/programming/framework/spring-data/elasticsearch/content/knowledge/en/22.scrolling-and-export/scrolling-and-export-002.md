# Point in Time for Maintaining a Consistent Data View Across Pages

## 1. Why Does Pagination Need a Stable Data View?

A search page is typically loaded in a single request. When a user clicks to the next page, the application sends a new request with the same search criteria but a different starting position or cursor.

If data in the index changes between two requests, the next page's results may no longer seamlessly follow the previous page. For example:

1. The first page returns 20 products sorted by `createdAt` descending.
2. A new product is added to the index and Elasticsearch refreshes.
3. The user loads the next page.
4. Document positions in the result ordering may shift; an already-seen document may reappear or an unseen document may be skipped.

This issue is especially prominent when using `from` and `size`, but it can also happen with `search_after` if each request reads from a newer index state.

**Point in time (PIT)** solves this problem by creating a consistent view of the index at the moment the PIT is opened. Subsequent search requests can use the same PIT to keep reading data from that view, even while the index continues receiving new documents or refreshes.

PIT is commonly combined with `search_after` for deep, stable pagination. PIT does not paginate by itself; it preserves the data state that pages read from.

## 2. What Is Point in Time?

Point in time is a lightweight search context representing the state of Elasticsearch data at the moment the PIT is opened. Elasticsearch retains the necessary resources so that subsequent searches continue seeing that exact state.

You can visualize it as:

~~~text
Time T0: open PIT on index products
                 |
                 v
        PIT holds data view at T0
                 |
       +---------+----------+
       |                    |
       v                    v
  T1: load page 1       Index gets new document
       |                    |
       v                    v
  T2: load page 2       Index refreshes again
       |                    |
       v                    v
  T3: load page 3       Current data changes

Requests using PIT still read the T0 view.
~~~

PIT has the following characteristics:

- Preserves the view of data at the time the PIT was created.
- Allows multiple search requests to continue using the same search context.
- Does not lock the index and does not prevent the application from writing new documents.
- Changes refreshed after the PIT was opened do not appear in that PIT's view.
- Has a lifetime controlled by `keep_alive`.
- Holds resources on the cluster, so it should be closed when no longer needed.

PIT is not a full copy of the index, not a snapshot backup, and not a transaction spanning systems outside Elasticsearch. It is a mechanism for maintaining a search context so read queries can share a consistent data view.

## 3. How Does PIT Differ from search_after and from/size?

These three concepts are often used together, but they serve different roles:

| Mechanism | Role | Limits or notes |
|---|---|---|
| `from` and `size` | Fetch a page by starting offset and document count | Suited for early pages; deep pagination is resource-intensive and subject to `max_result_window` |
| `search_after` | Fetch the next page based on sort values of the previous page's last hit | Requires keeping query and sort identical; does not preserve a snapshot across requests on its own |
| PIT | Maintain a consistent index view across multiple requests | Requires managing ID, `keep_alive`, and closing the search context |

`search_after` handles continuing from the last hit's position. PIT ensures subsequent requests still see the same data state. Therefore, when deep and consistent pagination is needed, both are commonly combined:

~~~text
PIT: maintains a stable data view
  +
search_after: determines the continuation position
  =
Deep pagination over a single consistent view
~~~

PIT can also be used with `from` and `size` for the initial pages. However, if you need to retrieve more than 10,000 hits, use PIT with `search_after` rather than continuously incrementing `from`.

## 4. Opening a PIT with the Elasticsearch REST API

First, open a PIT on the target index:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Elasticsearch returns an ID:

~~~json
{
  "id": "46ToAwMDaWR5BXV1aWQy..."
}
~~~

This ID is the point-in-time identifier. The application must keep it to send in subsequent search requests.

`keep_alive=1m` asks Elasticsearch to keep the PIT alive at least long enough to execute the next request. When a search request continues using the PIT and sends a new `keep_alive`, the lifetime is extended.

A PIT can be opened on a single index, an alias, or multiple indices specified in the open-PIT request. When opened on an alias, the indices that the alias points to at open time define the PIT's data scope.

### Searching the First Page with PIT

After opening the PIT, send a search request to `/_search` and pass the PIT in the body:

~~~http
GET /_search
{
  "size": 100,
  "pit": {
    "id": "46ToAwMDaWR5BXV1aWQy...",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    }
  ],
  "track_total_hits": false
}
~~~

Key points:

- When searching with a PIT, do not include the index name in the `/_search` path.
- Do not pass `index`, `routing`, or `preference` again in a search request using PIT; these are already bound to the PIT when opened.
- `size` specifies the number of documents in the current page.
- `sort` must remain identical across pages.
- `track_total_hits: false` can reduce overhead if the application does not need an exact total document count.

### Reading Sort Values of the Last Hit on the Page

Each hit in the response may include `sort` values. For example:

~~~json
{
  "pit_id": "46ToAwMDaWR5BXV1aWQy...",
  "hits": {
    "hits": [
      {
        "_id": "p-100",
        "_source": {
          "createdAt": "2026-10-10T09:00:00Z",
          "name": "Wireless Headphones"
        },
        "sort": [
          "2026-10-10T09:00:00Z",
          4294967298
        ]
      }
    ]
  }
}
~~~

When using PIT, Elasticsearch automatically appends a sort tiebreaker named `_shard_doc`. This value is added to the end of the sort values to distinguish documents that share the same primary sort field value.

The application takes the entire `sort` array of the last hit as the cursor for the next request. Do not construct it manually or take only part of the sort values.

## 5. Fetching the Next Page with search_after

To fetch the next page, resend the same query and sort, adding `search_after` from the previous page's last hit:

~~~http
GET /_search
{
  "size": 100,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    }
  ],
  "search_after": [
    "2026-10-10T09:00:00Z",
    4294967298
  ],
  "track_total_hits": false
}
~~~

In this example:

- `LATEST_PIT_ID` is the latest PIT ID received from the previous response.
- `search_after` holds the sort values of the last hit from the previous page.
- `query` and `sort` remain unchanged.
- `size` can remain the same so pages have uniform size.

Repeat this process until no hits remain:

~~~text
Open PIT
  |
  v
Search first page
  |
  v
Extract sort values of last hit
  |
  v
Send search_after + latest PIT ID
  |
  v
Fetch next page
  |
  +------ more hits ------> Repeat
  |
  +------ no hits --------> Close PIT
~~~

For requests using PIT, `from` must be `0` (default) or `-1`. Do not increment `from` by page number when `search_after` is used.

## 6. Always Use the Latest PIT ID

A critical detail is that Elasticsearch may return a new `pit_id` after each search request.

Therefore, do not open a PIT once and keep the initial ID for the entire process. After every response:

1. Read `pit_id` from the response.
2. If a new ID is present, update the stored ID.
3. Use the latest ID in the next request.
4. When finished, close the PIT using the latest ID.

Example:

~~~text
Open PIT
  |
  v
pit_id = A
  |
  v
Search page 1
  |
  v
Response pit_id = B
  |
  v
Search page 2 uses B
  |
  v
Response pit_id = C
  |
  v
Search page 3 uses C
  |
  v
Close PIT using C
~~~

Updating the ID is part of the PIT lifecycle. If the application keeps using an old ID after Elasticsearch has returned a new one, the next request may fail to target the latest search context.

For a single pagination cursor, execute requests sequentially. If you send multiple concurrent requests with the same PIT ID, each response may return a different new ID, requiring the application to manage selecting the next ID much more carefully.

## 7. keep_alive and the PIT Lifecycle

`keep_alive` is how long Elasticsearch retains the PIT's search context before it expires automatically.

Example of opening a PIT for one minute:

~~~http
POST /products/_pit?keep_alive=1m
~~~

A subsequent search request can extend it by another minute:

~~~json
{
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  }
}
~~~

`keep_alive` does not need to be as long as the total time required to process every page. It only needs to be long enough for the application to finish processing the current page and send the next request. Each continuing request can extend the lifetime.

Common values:

| Value | Meaning |
|---|---|
| `10s` | 10 seconds |
| `30s` | 30 seconds |
| `1m` | 1 minute |
| `5m` | 5 minutes |

If a user leaves a search page open too long without sending a new request, the PIT may expire. At that point, the old cursor can no longer be used. The application must open a new PIT and restart pagination if a consistent view is still needed.

Avoid setting an overly long lifetime solely in case a user returns hours later. A PIT holds resources on Elasticsearch; the longer it lives, the more resources may remain pinned.

## 8. Closing the PIT When Finished

A PIT expires automatically when its `keep_alive` duration elapses. However, the application should proactively close the PIT as soon as the user finishes paginating or the export process ends.

REST API:

~~~http
DELETE /_pit
{
  "id": "LATEST_PIT_ID"
}
~~~

Response:

~~~json
{
  "succeeded": true,
  "num_freed": 3
}
~~~

Closing the PIT lets Elasticsearch release the associated search contexts. Perform this in a `finally` block or equivalent cleanup mechanism so closure still runs if processing throws an exception.

If the final request returned a new PIT ID, use that new ID to close it. Do not close with an outdated ID if an updated ID was received.

## 9. Integrating PIT with Spring Data Elasticsearch

Spring Data Elasticsearch supports PIT through `ElasticsearchOperations` and `SearchOperations`.

Key APIs:

| API | Role |
|---|---|
| `openPointInTime(IndexCoordinates, Duration)` | Opens a PIT and returns the PIT ID |
| `closePointInTime(String)` | Closes the PIT |
| `Query.PointInTime(String, Duration)` | Carries the PIT ID and keep-alive in a query |
| `Query.setPointInTime(...)` | Attaches a PIT to a query |
| `SearchHits.getPointInTimeId()` | Retrieves the new PIT ID from the response |
| `Query.setSearchAfter(...)` | Sets the cursor from sort values |
| `SearchHit.getSortValues()` | Retrieves sort values of a hit |

The PIT API in Spring Data Elasticsearch has been available since version 5.0. Package names or query construction may differ in older versions; check your project's actual dependencies.

### Opening a PIT and Searching with CriteriaQuery

Example entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters, and setters
}
~~~

Opening a PIT and searching the first page:

~~~java
import java.time.Duration;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Duration keepAlive = Duration.ofMinutes(1);

String pitId = operations.openPointInTime(
    IndexCoordinates.of("products"),
    keepAlive
);

CriteriaQuery query = new CriteriaQuery(
    new Criteria("active").is(true)
);

query.setPageable(PageRequest.of(
    0,
    100,
    Sort.by(Sort.Order.asc("createdAt"))
));

query.setPointInTime(new Query.PointInTime(pitId, keepAlive));

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Points to note:

- Open the PIT using `IndexCoordinates` for the target index or alias.
- `Query.PointInTime` takes the PIT ID and keep-alive duration.
- `setPointInTime` attaches the PIT to the query.
- When a query uses PIT, call the `operations.search(query, Product.class)` overload without passing `IndexCoordinates` again.
- `PageRequest` uses page `0` and limits the number of hits for the first page.

### Continuing Pages with SearchAfter

You can extract the sort values of the last hit and build the next query:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

List<SearchHit<Product>> pageHits = hits.getSearchHits();

if (!pageHits.isEmpty()) {
    SearchHit<Product> lastHit =
        pageHits.get(pageHits.size() - 1);

    List<Object> searchAfter = lastHit.getSortValues();

    String latestPitId = hits.getPointInTimeId() != null
        ? hits.getPointInTimeId()
        : pitId;

    CriteriaQuery nextQuery = new CriteriaQuery(
        new Criteria("active").is(true)
    );

    nextQuery.setPageable(PageRequest.of(
        0,
        100,
        Sort.by(Sort.Order.asc("createdAt"))
    ));

    nextQuery.setSearchAfter(searchAfter);

    nextQuery.setPointInTime(
        new Query.PointInTime(latestPitId, keepAlive)
    );

    SearchHits<Product> nextHits = operations.search(
        nextQuery,
        Product.class
    );
}
~~~

In this example, `searchAfter` is taken directly from the previous page's last hit. `latestPitId` comes from the previous response and is not necessarily identical to the ID returned when opening the PIT.

When continuing across multiple pages, both pieces of information must be updated after each search:

- Cursor: sort values of the last hit in the newly received page.
- PIT ID: the latest ID from `SearchHits.getPointInTimeId()`.

If `getPointInTimeId()` returns `null`, the application should keep its current PIT ID rather than overwriting it with `null`.

## 10. Complete Pagination Loop Example in Spring Data

The following code illustrates a workflow that reads all active products in batches. Each request continues from the previous page's last hit and uses the latest PIT ID.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.function.Consumer;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductExportService {

    private static final int PAGE_SIZE = 100;

    private final ElasticsearchOperations operations;

    public ProductExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportActiveProducts(Consumer<Product> consumer) {

        Duration keepAlive = Duration.ofMinutes(1);

        String latestPitId = operations.openPointInTime(
            IndexCoordinates.of("products"),
            keepAlive
        );

        List<Object> searchAfter = null;

        try {
            while (true) {
                CriteriaQuery query = new CriteriaQuery(
                    new Criteria("active").is(true)
                );

                query.setPageable(PageRequest.of(
                    0,
                    PAGE_SIZE,
                    Sort.by(Sort.Order.asc("createdAt"))
                ));

                query.setPointInTime(
                    new Query.PointInTime(latestPitId, keepAlive)
                );

                query.setTrackTotalHits(false);

                if (searchAfter != null) {
                    query.setSearchAfter(searchAfter);
                }

                SearchHits<Product> hits = operations.search(
                    query,
                    Product.class
                );

                String returnedPitId = hits.getPointInTimeId();

                if (returnedPitId != null) {
                    latestPitId = returnedPitId;
                }

                List<SearchHit<Product>> page = hits.getSearchHits();

                if (page.isEmpty()) {
                    break;
                }

                for (SearchHit<Product> hit : page) {
                    consumer.accept(hit.getContent());
                }

                SearchHit<Product> lastHit = page.get(page.size() - 1);
                searchAfter = lastHit.getSortValues();

                if (page.size() < PAGE_SIZE) {
                    break;
                }
            }
        } finally {
            operations.closePointInTime(latestPitId);
        }
    }
}
~~~

How the loop works:

1. Open a PIT on the `products` index.
2. Build a query with `active = true`.
3. Set the initial page at `0`, size 100, and sort by `createdAt`.
4. Attach the PIT ID and `keep_alive`.
5. Call `operations.search`.
6. Update the PIT ID if the response returns a new one.
7. Process the documents in the page.
8. Extract the sort values of the last hit.
9. If the page had a full 100 hits, continue using `search_after`.
10. When data is exhausted or an error occurs, close the PIT using the latest ID.

This is a synchronous example. If the application uses reactive APIs, manage the same PIT lifecycle and cleanup asynchronously in a manner appropriate for the reactive pipeline.

In production code, handle PIT expiration and shard failures. Once a PIT has expired, you cannot continue with the old cursor; open a new PIT and restart the read if business requirements allow.

## 11. Why Does PIT Need a Stable Sort?

`search_after` requires sort values to pinpoint the exact starting point of the next page. If multiple documents share the same sort value, pagination may skip or duplicate hits without a tiebreaker.

For example, sorting only by `createdAt`:

~~~json
{
  "sort": [
    {
      "createdAt": "asc"
    }
  ]
}
~~~

Many products can be created at the same timestamp. Elasticsearch needs a secondary value to distinguish the ordering of those documents.

When using PIT, Elasticsearch automatically adds `_shard_doc` as a tiebreaker for search requests. `_shard_doc` is unique per document within the PIT's scope and remains stable for the lifetime of that PIT.

If not using PIT, add a field with a unique value per document to the sort, such as `id` or a tie-breaker field with suitable `doc_values`.

A few notes:

- Keep the sort order and sort fields identical across requests.
- Use all sort values from the last hit, including the tiebreaker added by PIT.
- Do not compute `_shard_doc` yourself.
- If sorting on a date across multiple indices with differing data types, normalize the format and numeric type so `search_after` is interpreted consistently.
- When a business ordering is needed, pick the appropriate sort fields and let PIT provide a stable tiebreaker.

## 12. PIT and Data Changes During Pagination

PIT preserves the data view at the moment it was opened. That means:

- Documents added after the PIT opened will not appear in that PIT's pages.
- Updates or deletes after the PIT opened do not alter the view held by the PIT.
- A new refresh does not advance the PIT to the newer index state.
- When a new PIT is opened, the application will see the latest data state refreshed and visible in Elasticsearch.

Example:

~~~text
T0: index has A, B, C
    Open PIT-1

T1: add D, refresh
    PIT-1 still sees A, B, C

T2: load next page using PIT-1
    Results still belong to set A, B, C

T3: open PIT-2
    PIT-2 sees A, B, C, D
~~~

This is very useful for search UIs that need stable results during a browsing session. However, if users want to see newly added data, the application must start a new search session with a new PIT.

PIT does not replace application data synchronization or transactions. It only controls the read view of Elasticsearch data.

## 13. PIT with Aliases, Rollover, and Multiple Indices

A PIT can be opened on an alias or multiple indices. When opening a PIT on an alias, Elasticsearch resolves the target indices at the moment the PIT is created.

Example:

~~~http
POST /products-read/_pit?keep_alive=1m
~~~

Suppose `products-read` currently points to `products-v1`. Later, the system switches the alias to `products-v2`. Requests using the already-open PIT continue reading from the view created when the PIT was opened; a new pagination session opening a new PIT will use the current alias target.

This is useful in systems using aliases and rollover:

- An in-progress search session can continue reading the same set of indices.
- New search sessions can see the new generation index.
- The application does not need to change index paths per page while using PIT.

When an alias points to multiple indices, the mappings and data types of sort fields must be compatible across indices. If sorting by date while one index uses `date` and another uses `date_nanos`, configure `numeric_type` and `format` appropriately per Elasticsearch requirements.

## 14. Does PIT Consume Resources?

Yes. PIT retains search contexts and related resources to preserve the older data view. Elasticsearch may have to keep old segments referenced by the PIT even after the index has refreshed or merged new segments.

Possible impacts include:

- Increased number of open search contexts.
- Retaining old segments longer.
- Increased pressure on file handles, memory, and disk space.
- Slower resource reclamation after merges if a PIT stays open too long.

Therefore:

- Use a short `keep_alive` that is still sufficient for the next request.
- Extend it only when actually continuing pagination.
- Close the PIT immediately upon completion.
- Do not open a new PIT per request if a search session can share one PIT.
- Monitor the number of open search contexts and cluster health.
- Limit concurrent PIT sessions according to application needs.

Avoid keeping a PIT open indefinitely while a user leaves a tab open. If a search session is abandoned, let the TTL release resources and prompt the user to start a new search session if needed.

## 15. How to Handle PIT Expiration or Errors?

A PIT can become unusable in several situations:

- `keep_alive` has expired.
- A cluster or node failure rendered the search context unavailable.
- A shard in the PIT failed or became unavailable.
- The application sent a wrong PIT ID or continued using an outdated ID.

When a PIT expires, Elasticsearch may return an error for the search request. The application should not keep sending the old `search_after` with a newly opened PIT ID, because that cursor belongs to a different view.

Appropriate handling flow:

1. Record that the old search session is no longer valid.
2. If possible, close the old PIT using the stored ID.
3. Open a new PIT on the current index or alias.
4. Rebuild the query and sort.
5. Restart pagination from the first page.
6. Notify the user if the UI needs to refresh results.

If the response reports shard failures, inspect the shard details instead of assuming the returned data is complete. With a PIT having a missing shard, Elasticsearch may keep reporting corresponding errors on subsequent searches; once the shard recovers, opening a new PIT may be necessary.

## 16. PIT, Scroll, and Large Data Exports

PIT with `search_after` is typically well suited for deep pagination and maintaining a consistent view. Scroll still has a role in certain batch reading workflows or traditional export processing.

| Criterion | PIT + search_after | Scroll |
|---|---|---|
| Common goal | Deep pagination, maintaining a consistent view | Batch reading of results within a single process |
| Cursor | Sort values of the last hit | Scroll ID |
| Data view | PIT preserves index state at open time | Scroll preserves search context of the search |
| Next request | Send query, PIT, and search_after | Send scroll ID and keep-alive duration |
| Cleanup | Close PIT | Clear scroll context |
| Best suited for | Multi-page search, cursor pagination | Batch processing and certain export tasks |

Do not use `from`/`size` to read hundreds of thousands of documents. For deep pagination, PIT combined with `search_after` is the right choice. For batch exports, choose PIT or scroll based on processing requirements, resumability, runtime, and resource usage.

Spring Data Elasticsearch also supports `searchForStream(...)` for streaming results; the framework documentation describes using scroll internally for this API. If you choose stream/scroll, close the resource or release the scroll context via the corresponding API.

## 17. Common Mistakes When Using PIT

**Assuming PIT paginates by itself.** PIT only preserves the data view. You must use `search_after` or another pagination mechanism to fetch the next page.

**Reusing the initial PIT ID.** Each response may return a new ID. Always update and use the latest ID.

**Forgetting to preserve sort values.** `search_after` must receive all sort values of the last hit, including the tiebreaker added by PIT.

**Changing query or sort between pages.** Requests sharing a cursor must keep the same query and sort for the continuation position to remain meaningful.

**Setting `keep_alive` too short.** If the application fails to send the next request before the PIT expires, the pagination session is lost.

**Setting `keep_alive` too long.** PIT holds resources on the cluster. Extend it only long enough for the next step and close it when finished.

**Not closing the PIT.** Although PIT expires automatically, the application should close it proactively to free resources early.

**Including an index path with PIT search.** A search request with PIT must not pass `index`, `routing`, or `preference` again; these were determined when opening the PIT.

**Incrementing `from` alongside `search_after`.** With PIT and `search_after`, keep `from` at its default or `0`; continue using sort values.

**Assuming PIT locks writes.** PIT does not block write operations. It only preserves a stable read view.

**Using an old PIT's cursor with a new PIT.** Sort values from an old session are not a valid cursor for a new view. If the PIT expires, restart pagination.

## 18. Implementing PIT for a Search Screen

You can implement it in the following sequence:

1. Identify the target index or alias to search.
2. Choose sort fields with compatible data types and a deterministic result order.
3. Open a PIT with an adequate `keep_alive`.
4. Execute the first-page request with query, sort, and PIT ID.
5. Store the latest PIT ID from the response.
6. Store the sort values of the last hit as the cursor.
7. When the user requests the next page, resend the same query/sort, latest PIT ID, and `search_after`.
8. Extend `keep_alive` on the subsequent request.
9. Continue until results are exhausted or the user ends the session.
10. Close the PIT using the latest ID in `finally` or a cleanup handler.
11. If the PIT expires, create a new session and restart from the first page.
12. Monitor open PIT counts, lifetimes, and cluster resources.

If the UI supports multiple concurrent search sessions, each session needs its own PIT ID and cursor. Do not share a single PIT/cursor across queries with different criteria or sort orders.

## Conclusion

Point in time preserves a consistent view of Elasticsearch data at the moment the PIT is opened. As a result, subsequent page-loading requests are unaffected by documents newly added, updated, or deleted after the PIT was created.

PIT is commonly paired with `search_after`: PIT preserves the data state, while `search_after` determines the continuation position. To paginate accurately, keep the query and sort unchanged, capture all sort values of the last hit, and always update to the latest PIT ID from the response.

In Spring Data Elasticsearch, you can open a PIT with `ElasticsearchOperations.openPointInTime`, attach it to a query with `Query.PointInTime`, read the new ID via `SearchHits.getPointInTimeId()`, and close it with `closePointInTime`. Proper `keep_alive` management and post-completion cleanup maintain stable results while keeping cluster resources under control.

## References

- [Elasticsearch — Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch — Open a point in time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
- [Elasticsearch — Close a point in time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-close-point-in-time)
- [Spring Data Elasticsearch — Point in Time API](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Spring Data Elasticsearch — SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchOperations.html)
- [Spring Data Elasticsearch — Query.PointInTime API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Query.PointInTime.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHits.html)
