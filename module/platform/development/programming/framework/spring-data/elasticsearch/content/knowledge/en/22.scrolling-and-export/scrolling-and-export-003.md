# Combining PIT with search_after via the Active API Version

When reading a large number of documents across many pages, pagination with `from/size` becomes increasingly resource-intensive. Elasticsearch must process results at positions preceding the current page before returning the requested slice of data. Moreover, if the index is refreshed while the application reads page by page, results of independent search requests can shift mid-way.

**Point in Time (PIT)** and **`search_after`** solve two different problems and complement each other:

- PIT preserves a consistent view of data at the time it is opened.
- `search_after` continues from the position of the previous page's last hit without skipping over all preceding pages.

Combining both mechanisms enables the application to scan data in batches with a stable ordering, suited for exports, synchronization, background processing, and APIs requiring deep pagination.

This lesson uses Spring Data Elasticsearch 5.x APIs, with examples compatible with the 5.4.x API: `ElasticsearchOperations.openPointInTime(...)`, `Query.PointInTime`, `NativeQueryBuilder.withSearchAfter(...)`, `SearchHit.getSortValues()`, and `SearchHits.getPointInTimeId()`. If your project uses a different version, verify against the Javadoc of the exact version selected by your dependency management.

## 1. Why Combine PIT and search_after?

### Limitations of from/size for Deep Reads

A typical paginated request:

~~~http
POST /products/_search
Content-Type: application/json

{
  "from": 20000,
  "size": 500,
  "query": {
    "match_all": {}
  }
}
~~~

This request returns 500 hits starting at position 20,000. Elasticsearch still has to process enough preceding results to determine the page to return. As `from` grows, processing cost and memory usage rise accordingly.

Elasticsearch also caps the total number of hits accessible via `from + size` using `index.max_result_window`, typically defaulting to 10,000. Increasing that limit does not eliminate the cost of deep pagination.

### search_after Uses a Cursor Instead of an Offset

`search_after` accepts the sort values of the last hit from the previous page. Elasticsearch resumes finding hits after that position using the same sort order.

For example, the first page ends at:

~~~json
{
  "sort": [1299000, "P-1002"]
}
~~~

The next page passes:

~~~json
{
  "search_after": [1299000, "P-1002"]
}
~~~

The request does not need `from: 20000`. It uses the sort values as a cursor to continue from where reading left off.

However, if each search request sees the latest index state, changes between two requests can cause inconsistent results: new documents appear, deleted documents vanish, or sort values change. PIT maintains the same data view across the entire sequence of requests.

### Role of Each Component

| Component | Problem solved |
|---|---|
| PIT | Maintains a consistent search snapshot across multiple requests |
| Sort | Defines the result ordering |
| search_after | Identifies the continuation position from the previous page |
| Sort values | Carries the values passed as the cursor |
| keep_alive | Extends how long the PIT remains valid |
| close PIT | Releases the search context upon completion |

~~~mermaid
flowchart TD
    A["Open PIT on index or alias"] --> B["Build query + sort + PIT"]
    B --> C["Search first page"]
    C --> D["Read hits and sort values of last hit"]
    D --> E["Get new PIT ID from response"]
    E --> F["Search next page with search_after"]
    F --> G{"More hits?"}
    G -->|Yes| D
    G -->|No| H["Close PIT with latest ID"]
~~~

## 2. What Does PIT Retain?

PIT is a lightweight reference to the data state visible to Elasticsearch at the moment the PIT is opened. It allows multiple search requests to keep operating on the same view even if the index is refreshed afterward.

For example:

1. The application opens a PIT on the `products` index.
2. The PIT captures the data state visible at that moment.
3. The application reads the first page.
4. Another process adds, modifies, or deletes products.
5. The application reads the next page using the same PIT.
6. Subsequent pages are still read from the view established when the PIT was opened.

PIT does not lock the index and does not block other applications from writing data. Changes made after the PIT was opened are not included in the active snapshot. A document deleted or updated afterward is still seen in its state at PIT open time within that snapshot.

PIT is not a relational database transaction. It does not provide multi-document transactions, does not prevent an index from being deleted, and does not replace application-level data synchronization mechanisms.

## 3. PIT APIs in Spring Data Elasticsearch 5.x

Spring Data Elasticsearch exposes PIT APIs on `ElasticsearchOperations`.

Key methods:

| API | Role |
|---|---|
| `openPointInTime(IndexCoordinates, Duration)` | Opens a PIT and returns the PIT ID |
| `closePointInTime(String)` | Closes the PIT |
| `Query.PointInTime(id, keepAlive)` | Describes the PIT ID and extension duration for a query |
| `withPointInTime(...)` | Attaches a PIT to the query builder |
| `withSearchAfter(List<Object>)` | Attaches the previous hit's sort values to the query |
| `SearchHits.getPointInTimeId()` | Reads the new PIT ID returned after a search |
| `SearchHit.getSortValues()` | Reads the sort values of a hit |

PIT has been supported in Spring Data Elasticsearch since the 5.0 release line. `search_after` has been present in the `Query` abstraction since 4.2 and is inherited by `NativeQueryBuilder`.

Example imports:

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query.PointInTime;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.client.elc.NativeQueryBuilder;

import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
~~~

There are two types named `Query` in different packages:

- `co.elastic.clients.elasticsearch._types.query_dsl.Query`: query DSL from the Elasticsearch Java API Client.
- `org.springframework.data.elasticsearch.core.query.Query`: Spring Data's query abstraction; `PointInTime` is a nested record inside this type.

In the code below, `Query` is imported from the Java Client to build the DSL. To avoid import collisions, you can use the fully qualified name `org.springframework.data.elasticsearch.core.query.Query.PointInTime` when creating PIT metadata.

## 4. Opening a PIT Before Reading the First Page

Suppose the application needs to read data from the `products` index:

~~~java
import java.time.Duration;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;

public class ProductExporter {

    private final ElasticsearchOperations operations;

    public ProductExporter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void startExport() {
        Duration keepAlive = Duration.ofMinutes(1);

        String pitId = operations.openPointInTime(
                IndexCoordinates.of("products"),
                keepAlive
        );

        // Use pitId to build subsequent search requests.
    }
}
~~~

`IndexCoordinates.of("products")` identifies the index or alias to open. `keepAlive` is how long the PIT is retained if no subsequent request extends it.

The method returns a PIT ID string. This is an opaque identifier issued by Elasticsearch; the application only stores and passes it back without parsing its internal structure.

There is an overload that accepts `ignoreUnavailable` when you need to control how nonexistent or closed indices are handled. For export flows requiring complete data, it is usually better to let unavailable-index errors surface rather than silently skipping indices.

PIT requires read permissions on the target index. The application account does not need index administration privileges solely to open a PIT and search.

## 5. Defining a Stable Sort Before Using search_after

`search_after` only works properly when the query defines a sort. Subsequent requests must keep the sort order and data types of sort values unchanged.

Suppose a document contains:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "createdAt": "2026-10-20T08:30:00Z"
}
~~~

The mapping should declare:

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

We can sort by `createdAt` ascending, then `productId` ascending:

~~~java
SortOptions byCreatedAt = SortOptions.of(s -> s
        .field(f -> f
                .field("createdAt")
                .order(SortOrder.Asc)
        )
);

SortOptions byProductId = SortOptions.of(s -> s
        .field(f -> f
                .field("productId")
                .order(SortOrder.Asc)
        )
);
~~~

`productId` acts as a tie-breaker when multiple documents share the same creation timestamp. The tie-breaker field must have stable values, support sorting, and be sufficiently unique across the indices read by the PIT.

Avoid sorting directly on the `_id` metadata field as though it were an ordinary keyword field. If you need to sort by document ID, store a copy of the ID in a keyword field with doc values enabled, or use an appropriate PIT tie-breaker mechanism.

Elasticsearch can append `_shard_doc` as an internal tie-breaker when searching through a PIT. If you need an intelligible business order, use a unique business field as the tie-breaker. If you only need to scan the entire dataset in the PIT's stable internal order, consider sorting on `_shard_doc`.

## 6. Building the First Query with PIT

In Spring Data Elasticsearch 5.x, `NativeQuery.builder()` accepts the query DSL, sort, page size, and PIT metadata.

First-page example:

~~~java
import org.springframework.data.domain.PageRequest;

Query matchAll = Query.of(q -> q
        .matchAll(m -> m)
);

Duration keepAlive = Duration.ofMinutes(1);

NativeQuery firstPageQuery = NativeQuery.builder()
        .withQuery(matchAll)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withPointInTime(
                new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                        pitId,
                        keepAlive
                )
        )
        .build();

SearchHits<ProductDocument> firstPage =
        operations.search(firstPageQuery, ProductDocument.class);
~~~

Points to note:

- `PageRequest.of(0, 500)` keeps the offset at the first page and caps results at 500.
- The PIT is attached to the query via `withPointInTime(...)`.
- `search_after` is not passed on the first page.
- When a query includes a PIT, call `operations.search(query, ProductDocument.class)`; do not pass `IndexCoordinates` again. The index was already determined when opening the PIT.
- `matchAll` is only an example for scanning all documents. In practice, you can use business queries/filters as long as they stay identical across pages.

A PIT carries the index, routing, and preference determined at open time. When sending a search request with a PIT, do not specify `index`, `routing`, or `preference` again in the request.

## 7. Extracting Sort Values from the Last Hit

After receiving the first page, the application processes the documents and then reads the sort values of the last hit:

~~~java
List<SearchHit<ProductDocument>> pageHits =
        firstPage.getSearchHits();

if (firstPage.hasSearchHits()) {
    for (SearchHit<ProductDocument> hit : pageHits) {
        ProductDocument product = hit.getContent();

        // Process or write the product to the destination file.
    }

    SearchHit<ProductDocument> lastHit =
            pageHits.get(pageHits.size() - 1);

    List<Object> searchAfter = lastHit.getSortValues();
}
~~~

`getSortValues()` returns the list of values in the exact order of the sort clauses. With sort `createdAt` followed by `productId`, sort values might look like:

~~~json
[
  "2026-10-20T08:30:00.000Z",
  "P-1002"
]
~~~

Keep this list untouched to pass into the next request. Do not reconstruct it from the entity, do not convert numeric types to strings, and do not reorder elements.

If a query has no sort, `getSortValues()` will not provide a usable cursor for `search_after`. Therefore, sorting is a mandatory prerequisite for this pagination flow.

## 8. Updating the PIT ID After Each Search

An important detail: the response to each search request through a PIT may return a new PIT ID.

In Spring Data Elasticsearch, read the new ID using:

~~~java
String newPitId = searchHits.getPointInTimeId();
~~~

If a new value is returned, you must use it for the next request and when closing the PIT:

~~~java
if (searchHits.getPointInTimeId() != null) {
    pitId = searchHits.getPointInTimeId();
}
~~~

Do not continue using the initial PIT ID throughout the entire process. Elasticsearch expects subsequent requests to use the latest PIT ID returned by the previous response.

`getPointInTimeId()` may return `null` if the response contains no new ID. In that case, retain the most recent ID you have. In a normal PIT flow, the response typically returns an ID to continue with.

## 9. Creating the Next Page Request with withSearchAfter

The next page uses:

- The same query.
- The same sort.
- The same page size.
- The latest PIT ID.
- The sort values of the previous page's last hit.

Example:

~~~java
NativeQuery nextPageQuery = NativeQuery.builder()
        .withQuery(matchAll)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withPointInTime(
                new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                        pitId,
                        keepAlive
                )
        )
        .withSearchAfter(searchAfter)
        .build();

SearchHits<ProductDocument> nextPage =
        operations.search(nextPageQuery, ProductDocument.class);
~~~

`withSearchAfter(searchAfter)` accepts the `List<Object>` obtained from `SearchHit.getSortValues()`.

Note that `PageRequest.of(0, 500)` stays at page 0. `search_after` already defines the continuation position; do not increment the page index as in offset pagination. Using a non-zero page index alongside `search_after` can introduce unnecessary offsets or cause unintended query behavior.

## 10. Example Service Reading All Documents in Batches

Below is a complete service. Each batch is processed immediately upon receipt without accumulating all documents into an in-memory list.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.function.Consumer;

import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.client.elc.NativeQueryBuilder;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductExportService {

    private static final int BATCH_SIZE = 500;
    private static final Duration KEEP_ALIVE =
            Duration.ofMinutes(1);

    private final ElasticsearchOperations operations;

    public ProductExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportAll(Consumer<ProductDocument> sink) {
        String pitId = operations.openPointInTime(
                IndexCoordinates.of("products"),
                KEEP_ALIVE
        );

        List<Object> searchAfter = null;

        try {
            Query matchAll = Query.of(q -> q
                    .matchAll(m -> m)
            );

            SortOptions byCreatedAt = SortOptions.of(s -> s
                    .field(f -> f
                            .field("createdAt")
                            .order(SortOrder.Asc)
                    )
            );

            SortOptions byProductId = SortOptions.of(s -> s
                    .field(f -> f
                            .field("productId")
                            .order(SortOrder.Asc)
                    )
            );

            while (true) {
                NativeQueryBuilder builder = NativeQuery.builder()
                        .withQuery(matchAll)
                        .withSort(byCreatedAt, byProductId)
                        .withPageable(PageRequest.of(0, BATCH_SIZE))
                        .withPointInTime(
                                new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                                        pitId,
                                        KEEP_ALIVE
                                )
                        );

                if (searchAfter != null) {
                    builder.withSearchAfter(searchAfter);
                }

                SearchHits<ProductDocument> page =
                        operations.search(
                                builder.build(),
                                ProductDocument.class
                        );

                String returnedPitId = page.getPointInTimeId();
                if (returnedPitId != null && !returnedPitId.isBlank()) {
                    pitId = returnedPitId;
                }

                if (!page.hasSearchHits()) {
                    break;
                }

                List<SearchHit<ProductDocument>> pageHits =
                        page.getSearchHits();

                for (SearchHit<ProductDocument> hit : pageHits) {
                    sink.accept(hit.getContent());
                }

                SearchHit<ProductDocument> lastHit =
                        pageHits.get(pageHits.size() - 1);

                searchAfter = lastHit.getSortValues();

                if (searchAfter == null || searchAfter.isEmpty()) {
                    throw new IllegalStateException(
                            "Search response did not contain sort values"
                    );
                }

                if (pageHits.size() < BATCH_SIZE) {
                    break;
                }
            }
        } finally {
            if (pitId != null && !pitId.isBlank()) {
                operations.closePointInTime(pitId);
            }
        }
    }
}
~~~

In this example:

1. The PIT is opened once before the loop.
2. Each request reads at most `BATCH_SIZE` documents.
3. The query and sort remain unchanged.
4. The first page has no `searchAfter`.
5. Subsequent pages pass the sort values of the previous page's last hit.
6. The PIT ID is updated after each response.
7. When no hits remain or the last batch has fewer than `BATCH_SIZE` hits, the loop stops.
8. `finally` closes the PIT using the latest ID, even if processing throws an exception.

`Consumer<ProductDocument>` represents writing to a file, publishing a message, or transforming data. If processing a single batch may take a long time, ensure `KEEP_ALIVE` is long enough for the next request to be sent before the PIT expires.

In production systems, log the count of processed documents, per-batch duration, and any PIT closure errors. Do not log the PIT ID to public locations because it is a search context identifier.

## 11. Can CriteriaQuery Be Used Instead of NativeQuery?

Yes. PIT and `search_after` belong to Spring Data's `Query` abstraction and are not exclusive to `NativeQuery`.

Example using `CriteriaQuery`:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("status").is("PUBLISHED");

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 500));
query.setSearchAfter(searchAfter);
query.setPointInTime(
        new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                pitId,
                keepAlive
        )
);
~~~

`CriteriaQuery` fits simple query conditions that the Criteria API expresses cleanly. `NativeQuery` is more convenient when you need the typed Elasticsearch Java Client DSL, multiple sort options, or advanced queries.

Regardless of which query type you choose, the rules are the same:

- Attach the PIT to every query.
- Keep the sort stable.
- Extract search-after values from the last hit.
- Use the latest PIT ID.
- Close the PIT upon completion.

## 12. Using the REST API to Understand the Actual Requests

Spring Data Elasticsearch translates PIT and `search_after` settings into the corresponding Elasticsearch requests.

### Opening the PIT

~~~http
POST /products/_pit?keep_alive=1m
~~~

The response returns an ID:

~~~json
{
  "id": "46ToAw..."
}
~~~

### Searching the First Page

When searching with a PIT, the endpoint path no longer includes the index name:

~~~http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "46ToAw...",
    "keep_alive": "1m"
  },
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "createdAt": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ]
}
~~~

### Searching the Next Page

Suppose the previous response returned a new PIT ID and the sort values of the last hit:

~~~json
{
  "pit_id": "46ToAw...new",
  "hits": {
    "hits": [
      {
        "_id": "P-1002",
        "sort": [
          "2026-10-20T08:30:00.000Z",
          "P-1002"
        ]
      }
    ]
  }
}
~~~

The next request must use the new PIT ID and the sort values of the last hit:

~~~http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "46ToAw...new",
    "keep_alive": "1m"
  },
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "createdAt": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "search_after": [
    "2026-10-20T08:30:00.000Z",
    "P-1002"
  ]
}
~~~

Do not send `index`, `routing`, or `preference` in a search request with a PIT; those values were fixed when the PIT was opened.

### Closing the PIT

When reading finishes:

~~~http
DELETE /_pit
Content-Type: application/json

{
  "id": "46ToAw...new"
}
~~~

Always close using the latest PIT ID held by the application. If not closed, the PIT will expire after `keep_alive`, but waiting for expiration leaves the search context occupying resources during that interval.

## 13. Direct Java API Client vs. Spring Data API

If you need to invoke Elasticsearch APIs directly, the Java API Client provides equivalent operations:

| Operation | Spring Data Elasticsearch 5.x | Elasticsearch Java API Client |
|---|---|---|
| Open PIT | `operations.openPointInTime(index, keepAlive)` | `client.openPointInTime(...)` |
| Attach PIT | `withPointInTime(new Query.PointInTime(...))` | `SearchRequest.pit(...)` |
| Pass cursor | `withSearchAfter(List<Object>)` | `SearchRequest.searchAfter(...)` |
| Read sort values | `SearchHit.getSortValues()` | `Hit.sort()` |
| Read new PIT ID | `SearchHits.getPointInTimeId()` | `SearchResponse.pitId()` |
| Close PIT | `operations.closePointInTime(id)` | `client.closePointInTime(...)` |

The Spring Data API has the advantage of converting results into entities via Spring Data's mapping converter. When calling the Java Client directly, responses are deserialized using the client's JSON mapper; Spring Data custom conversions are not automatically applied as they are with `ElasticsearchOperations`.

Do not mix legacy `RestHighLevelClient` APIs such as `SearchSourceBuilder` or the old `SearchRequest` with `NativeQuery` and the Java API Client. Use the exact dependencies and packages matching the Spring Data Elasticsearch version in your project.

## 14. How Does PIT + search_after Differ from Scroll?

Both Scroll and `PIT + search_after` can read large datasets in batches, but their usage differs.

| Criterion | PIT + search_after | Scroll |
|---|---|---|
| Page advancement | Based on sort values of the last hit | Based on scroll ID |
| Snapshot | PIT maintains a consistent data view | Scroll context maintains the search state |
| Ordering | Requires a stable sort | Can use an order suited for scan jobs |
| Deep pagination | Well suited | Suited for traditional batch flows |
| Next request | Send PIT ID and `search_after` | Send scroll ID |
| Termination | Close PIT | Clear scroll |
| Used for | Deep-pagination APIs, exports needing an explicit cursor | Batch scans or flows already using the Scroll API |

If you need deep pagination for a UI or want a cursor that can be stored and passed between requests, `PIT + search_after` is usually the better fit.

If the application already uses Spring Data's `searchForStream(...)`, understand that this streaming API uses Scroll internally per the Spring Data documentation. It does not automatically turn into `PIT + search_after`.

Avoid opening unnecessary PITs or scroll contexts for the same task. Choose one mechanism and release resources once reading completes.

## 15. Managing keep_alive and Resources

`keep_alive` is how long the PIT continues to exist without a renewing request. Every search request resending the PIT with `keep_alive` extends the PIT's lifetime.

`keep_alive` does not need to be long enough to scan the entire index. It only needs to cover the expected interval between two consecutive requests, including batch processing time.

For example:

- A batch usually finishes in 2 seconds: a keep-alive of around 1 minute may be chosen.
- A batch includes external processing outside Elasticsearch taking 30 seconds: factor that wait time into the keep-alive.
- A job may pause for several minutes: design explicit timeouts, checkpoints, and restartability.

PIT retains old segments needed for the snapshot. Consequently, opening too many PITs or keeping them open too long can increase:

- Disk usage due to unreleased old segments.
- File handle count.
- Heap memory needed to track deleted/updated document state.
- Search context resources on nodes.

Close the PIT as soon as you finish. `keep_alive` is a fallback expiration safeguard, not a reason to skip `closePointInTime(...)`.

## 16. Error Handling and Resumability

### PIT Expiration

If the application fails to send a request before `keep_alive` expires, the PIT may become invalid. The next search request will fail.

You cannot recover the exact old snapshot simply by opening a new PIT. A new PIT sees the data state as of the new open time.

If strict single-snapshot consistency is required for an export, fail and restart the full read under a new PIT, or use a business checkpoint strategy with explicit reconciliation rules. Do not silently open a new PIT and resume from old sort values, as that can skip or duplicate documents.

### Response Returning a New PIT ID

Always update to the new ID after every search. If the application keeps only the ID from when the PIT was opened, later requests or the close operation may use a stale ID.

### Batch Processing Failures

If writing a batch to a file, database, or target system fails, determine whether the checkpoint was committed before advancing to the next page.

A safe ordering:

1. Read one page.
2. Write and confirm successful processing of the entire page.
3. Only then persist the sort values of the last hit as the checkpoint.
4. Advance to the next page.

If you save the checkpoint before writing to the destination completes, a mid-flight failure can drop documents upon restart.

PIT IDs expire and may change with every response. If a checkpoint needs to survive longer than a PIT, you cannot simply save the PIT ID and expect to resume hours later. Design a process to open a new snapshot and reconcile by business key, timestamp, or data version.

### Shard Failures and Timeouts

If a search response reports shard failures or a timeout, do not treat that batch as completely read. Inspect shard status, timeout flags, and error logs before recording a completed checkpoint.

For exports requiring full data completeness, configure error handling to stop and report failure rather than silently accepting partial shard results.

## 17. Using PIT with Aliases or Multiple Indices

A PIT can be opened on a single index, an alias, or a set of indices. When opening a PIT via an alias, Elasticsearch resolves the target indices at open time.

Example:

~~~java
String pitId = operations.openPointInTime(
        IndexCoordinates.of("products"),
        Duration.ofMinutes(1)
);
~~~

If `products` is an alias pointing to `products-v1` and `products-v2`, the PIT retains a view over the indices resolved by the alias at open time.

In subsequent requests, use the PIT ID without specifying the alias or index again. If the alias is repointed to another index while the export is running, the existing PIT still represents the set of indices with which it was opened.

When searching across multiple indices, ensure mappings are compatible with the query and sort. Sort fields must exist with compatible data types across every index opened under the PIT.

If the same business key appears in multiple indices, the application needs its own deduplication rules. PIT does not automatically merge documents across indices.

## 18. Security When Exposing Cursors to External APIs

An API may split reading across multiple client requests:

1. The client requests the first page.
2. The server opens a PIT, searches the first page, and produces a cursor.
3. The client sends the cursor to fetch the next page.
4. The server continues using the stored PIT ID and sort values.

Do not let clients tamper with the PIT ID, sort values, tenant filter, or query. A cursor should be an opaque server-generated token—potentially signed or encrypted—containing only necessary fields such as:

- Current PIT ID.
- Sort values of the last hit.
- Query/filter fingerprint.
- Page size.
- Expiration timestamp.
- Authenticated tenant or access scope.

The server must verify that the cursor belongs to the right user/tenant and original query. PIT is not an authorization mechanism; every request must still be authenticated and enforce appropriate access-control filters.

Do not log PIT IDs or cursors containing sensitive information to public logs. When a cursor expires, the API should return a meaningful error so the client can restart the search session.

## 19. Common Mistakes

### Using search_after Without PIT

Requests can observe different index states after refreshes. For read workflows requiring a consistent snapshot, open a PIT first.

### Using PIT Without sort/search_after

PIT preserves the snapshot, but it does not automatically create a deep-pagination cursor. You need sorting and sort values to continue.

### Lacking a Stable Tie-Breaker

If multiple documents share the same sort value, ordering may be nondeterministic. Add a unique field or use a tie-breaker compatible with PIT.

### Incrementing `from` Alongside search_after

`search_after` is already the continuation position. Keep offset at `0` and use a fixed page size.

### Forgetting to Take Sort Values from the Last Hit

Using sort values from the first hit or an arbitrary hit will skip or duplicate parts of the dataset. Always call `getSortValues()` on the last hit of the successfully processed batch.

### Forgetting to Update the PIT ID

Every response may return a new PIT ID. Keeping the old ID can cause the next request or closing the PIT to fail.

### Passing the Index Again When Searching with PIT

The PIT already stores the index, routing, and preference. A search request with a PIT must not specify these parameters again. In Spring Data, use the `operations.search(query, Entity.class)` overload for queries with a PIT.

### Using a Non-Sortable Sort Field

`text` fields or fields missing doc values cannot be used directly for sorting. Use `keyword`, numeric, `date`, or an appropriate multi-field.

### Not Closing the PIT

A PIT expires automatically, but it continues holding resources for its lifetime. Close the PIT in `finally` upon completion or error.

### Extending keep_alive for Too Short a Duration

If batch processing takes longer than `keep_alive`, the PIT may expire before the next request. Choose `keep_alive` based on actual processing times and renew it on each search.

### Opening a New PIT and Reusing an Old Cursor

A new PIT holds a different snapshot. Sort values from an old snapshot are not guaranteed to continue accurately on the new snapshot. If the PIT expires, restart or reconcile according to business design.

## 20. Implementation Workflow

When building an export or deep-pagination feature:

1. Verify the versions of Spring Data Elasticsearch and the Elasticsearch Java API Client in use.
2. Select the index/alias and verify read permissions.
3. Inspect the mappings of fields used in queries and sorts.
4. Choose a stable sort with a unique tie-breaker.
5. Open a PIT using `operations.openPointInTime(...)`.
6. Build the query with `Query.PointInTime`, sort, and page size.
7. Search the first page without passing `search_after`.
8. Process the batch and extract sort values from the last hit.
9. Update the PIT ID using `SearchHits.getPointInTimeId()`.
10. Build the next query with `withSearchAfter(...)`.
11. Loop until no hits remain.
12. Close the PIT using the latest ID inside `finally`.
13. Record the checkpoint only after the batch is successfully processed.
14. Monitor timeouts, shard failures, batch durations, and open PIT counts.

## References

- [Spring Data Elasticsearch 5.4 — SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/SearchOperations.html)
- [Spring Data Elasticsearch 5.4 — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch 5.4 — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — PIT API guide](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html#point-in-time-pit-api)
- [Elasticsearch — Point in time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Elasticsearch — Paginate search results with search_after](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)

## Conclusion

PIT maintains a consistent data view while `search_after` lets you advance from one batch to the next using the sort values of the last hit. With Spring Data Elasticsearch 5.x, open a PIT with `ElasticsearchOperations.openPointInTime(...)`, attach it with `withPointInTime(new Query.PointInTime(...))`, pass the cursor with `withSearchAfter(...)`, update the ID via `SearchHits.getPointInTimeId()`, and close the PIT with `closePointInTime(...)`. Keep the query and sort unchanged across pages, pick a stable tie-breaker, process each batch before saving checkpoints, and always release the PIT upon completion.
