# search_after and Continuation Position Based on Sort Values

When a query returns thousands or millions of documents, offset-based pagination (`from` and `size`) becomes increasingly expensive as users navigate deeper into the results. Elasticsearch must find and skip the hits before the offset, while also capping `from + size` via `index.max_result_window` under the common default configuration.

**search_after** solves advancing through a result set by using the sort values of the last hit from the previous page. Instead of saying "skip the first 10,000 hits," the next request says "return hits after this sort position." Spring Data Elasticsearch retains those values in `SearchHit` metadata and lets you pass them into the subsequent query.

For accurate pagination, you must keep the query and sort order identical across requests, use a stable sort order, pass back the original sort values, and consider **Point in Time (PIT)** if data may change while the user is browsing. This lesson explains how `search_after` works, how it integrates with Spring Data Elasticsearch, how to design cursors, and how it differs from `scroll`.

## 1. Why Is Offset Pagination Unsuitable for Deep Results?

With `from` and `size`, the first request might fetch 20 results:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

The next page increases the offset:

~~~http
POST /products/_search
{
  "from": 20,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

This approach is easy to understand and works well for the first few pages. However, to retrieve a page at a deep offset, Elasticsearch must process the results preceding the target position across shards and then coordinate them on the coordinating node. Processing cost and memory usage grow with page depth.

Elasticsearch also limits the result window via `index.max_result_window`; the default is typically 10,000 for `from + size`. While the index setting can be changed, raising the limit does not make offset pagination cheaper.

For example, a request with `from: 10000` and `size: 20` is not a good strategy for continuous deep traversal. For use cases that require stepping through many pages, consider `search_after`.

### How Do Offset and Cursor Differ?

| Pagination approach | Next request is based on | Characteristics |
|---|---|---|
| from + size | Number of hits to skip | Easy to jump to any page number, but expensive at deep offsets |
| search_after | Sort values of the last hit on the previous page | Continues from a sort position; suited for deep pagination |
| Scroll | Search context and scroll ID | Iterates in batches for large data read/export jobs |

`search_after` is not a mechanism for jumping directly to page 500. It requires a cursor from the previous page. If the UI needs a "jump to any page" button, offset pagination or a strategy that stores cursors per page may be more suitable, though cost and potential data changes must be weighed.

## 2. How Does search_after Work Based on Sort?

Elasticsearch needs a deterministic result order to know which hits follow the last hit of the previous page. Therefore, `search_after` is always paired with `sort`.

Suppose we sort by price ascending:

~~~http
POST /products/_search
{
  "size": 3,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

The response contains three hits. Each hit includes a `sort` array corresponding to the declared sort order:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-10",
        "_source": { "price": 49.0 },
        "sort": [49.0]
      },
      {
        "_id": "p-22",
        "_source": { "price": 59.0 },
        "sort": [59.0]
      },
      {
        "_id": "p-31",
        "_source": { "price": 69.0 },
        "sort": [69.0]
      }
    ]
  }
}
~~~

The last hit has sort values `[69.0]`. The next request passes that exact array into `search_after`:

~~~http
POST /products/_search
{
  "size": 3,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "search_after": [69.0]
}
~~~

Elasticsearch returns hits whose sort position comes after `[69.0]`. The application continues by taking the sort values of the last hit in the new response to build the next cursor.

Processing flow:

~~~text
Page 1 request
      |
      v
Page 1 SearchHits
      |
      v
Extract sort values of the last hit
      |
      v
Send search_after with those sort values
      |
      v
Page 2 request
      |
      v
Extract sort values of the last hit on page 2
      |
      +------> Page 3 request ...
~~~

The `search_after` value is a continuation position in the sort order, not a document ID and not a page number.

## 3. Why Must the Sort Be Stable and Have a Tie-Breaker?

Sorting on a single field can produce multiple hits with the same value. For example, several products may have the same price of `69.0`. If you sort only by `price`, Elasticsearch has no guaranteed unique order among documents sharing that value.

When using `search_after`, the continuation position must distinguish between hits. If the sort is not sufficiently deterministic, results may be duplicated or skipped across page transitions, especially when shards or data change.

The solution is to add a unique tie-breaker field:

~~~http
POST /products/_search
{
  "size": 3,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
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

Suppose `productId` is a `keyword` field with unique values and doc values enabled. A hit's sort values might be:

~~~json
[69.0, "p-31"]
~~~

The next request must pass both values:

~~~json
{
  "search_after": [69.0, "p-31"]
}
~~~

Do not pass only `69.0`, because the cursor would then be unable to pinpoint the exact position among products sharing the same price.

### Choosing a Tie-Breaker Field

A tie-breaker field should:

- Have unique values within the scope of the result set.
- Have a mapping that supports sorting, typically `keyword`, numeric, or `date` with doc values.
- Maintain a stable value throughout the traversal.
- Be kept in the exact same sort order across every request.

Avoid defaulting to `_id` directly as a sort field. Elasticsearch restricts sorting and aggregations on `_id`; if not using PIT, you can copy the identifier into a dedicated `keyword` field such as `productId` with doc values enabled for sorting.

When using PIT, Elasticsearch adds `_shard_doc` as an internal tie-breaker when needed. This value is returned in the sort values and must be preserved when constructing the next request. PIT and `_shard_doc` are covered later.

### Multiple Sort Criteria

Each sort criterion adds an element to the `sort` array. For example:

~~~json
{
  "sort": [
    { "updatedAt": "desc" },
    { "price": "asc" },
    { "productId": "asc" }
  ]
}
~~~

A hit's sort values will follow the same order:

~~~json
[
  "2026-10-20T08:30:00Z",
  69.0,
  "p-31"
]
~~~

The cursor must contain all three values, with the exact types and order. If you change the sort order, direction, date format, or sort fields between requests, the old cursor becomes invalid.

## 4. The search_after Pagination Flow

A typical pagination flow consists of the following steps:

1. Normalize user filters and keywords.
2. Build a fixed query for the entire browsing session.
3. Declare a stable sort order and tie-breaker.
4. Send the first request with the desired `size` and no `search_after`.
5. Receive the results and extract the sort values of the last hit.
6. Pass those sort values into the next request.
7. Repeat until the response returns no hits.

If the response is empty, there is no last hit from which to create a new cursor. The API should indicate that no more data remains or omit `nextCursor`.

### Note: Do Not Increment `from` When Using `search_after`

When paginating with `search_after`, keep `from` at `0` or omit the field entirely. Do not combine a cursor with an increasing offset such as `from: 20`, `from: 40`. The continuation position is already determined by the sort values.

### Page Size

`size` still controls the maximum number of hits per response. For instance, `size: 50` means each request fetches at most 50 hits after the cursor.

Avoid setting `size` excessively large merely to reduce request count. Page size should balance:

- Document size and payload size.
- Per-request latency.
- Application memory consumption.
- The number of requests the client can execute.
- Elasticsearch cluster limits and load.

## 5. Keeping Query and Sort Identical Across Requests

`search_after` only makes sense when the subsequent request continues through the same result set in the same order.

Components that must remain consistent include:

- Full-text query.
- Business filters.
- Sort fields and sort directions.
- Missing-value behavior.
- Nested sort or other sort options.
- Routing and the queried index/alias.
- Options that affect the result set.

For example, if the first page filters by the `accessories` category, but the next page drops the category filter, the cursor points to a position within a different result set. The results will no longer be a true continuation of the previous page.

Similarly, if the first page sorts by `price asc, productId asc` and the next page switches to `price desc, productId asc`, the sort values no longer represent the same order.

### Generating a Query Fingerprint for the Cursor

At the application layer, you can compute a fingerprint from the components that affect the result set:

- Normalized query keywords.
- Normalized filters.
- Index or alias.
- Sort definition.
- Relevant mapping/query options.

A fingerprint lets the server verify that the cursor is being used with the exact original criteria. You do not necessarily have to store the entire query JSON in the token; you can store a server-side search session ID or a hash of the normalized structure.

## 6. Data Changing While Users Paginate

If the index continues receiving new documents, updates, or deletes between two requests, the same query and sort can still yield a different result set.

For example:

1. Page 1 returns products priced between 20 and 40.
2. A new product is indexed with a price of 25.
3. The client sends the next request using page 1's cursor.
4. The result set has changed; the sort position may cause the client to see results that differ from the initial snapshot.

A tie-breaker guarantees uniqueness of the sort order, but it does not automatically create a data snapshot. To maintain a consistent view across multiple requests, use **Point in Time (PIT)** if your Elasticsearch and Spring Data versions support that use case.

## 7. Combining search_after with Point in Time (PIT)

PIT opens a stable point-in-time view of an index. Subsequent search requests use the same PIT to browse data from that snapshot, even while the underlying index continues to change.

High-level flow:

1. Open a PIT on the target index or alias.
2. Send the search request with PIT, query, sort, and page size.
3. Extract the sort values of the last hit.
4. Use the latest PIT ID together with the sort values in the next request.
5. Extend `keep_alive` while continuing to browse, as supported by the API.
6. Close the PIT when the user finishes or the session expires.

Example opening request using the Elasticsearch REST API:

~~~http
POST /products/_pit?keep_alive=1m
~~~

The response returns a PIT ID. The search request uses the PIT:

~~~http
POST /_search
{
  "size": 50,
  "pit": {
    "id": "PIT_ID_FROM_OPEN_RESPONSE",
    "keep_alive": "1m"
  },
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    { "price": "asc" }
  ]
}
~~~

When using PIT, Elasticsearch adds `_shard_doc` as a tie-breaker if the sort does not already have a suitable tie-breaker. Therefore, the sort values may contain this extra element. You must pass back the entire sort values array returned by the hit, including the `_shard_doc` element.

Next request:

~~~http
POST /_search
{
  "size": 50,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    { "price": "asc" }
  ],
  "search_after": [
    69.0,
    4294967298
  ]
}
~~~

The values above are illustrative only. In practice, always use the latest PIT ID if the response returns a new ID, and use the actual sort values of the last hit. Do not compute `_shard_doc` yourself.

### Managing the PIT Lifecycle

PIT retains search context resources on the cluster. The application should:

- Set `keep_alive` just long enough for the user to continue interacting.
- Extend it on subsequent requests according to the API rules.
- Close the PIT when the browsing session completes.
- Have an expiration mechanism to release abandoned PITs.
- Handle expired PITs or invalid IDs gracefully.
- Limit the number of concurrent PIT sessions based on system load.

Do not open a new PIT for every page. Pages belonging to the same pagination session must share the same PIT to preserve the snapshot.

## 8. Reading Sort Values in Spring Data Elasticsearch

When calling search via `ElasticsearchOperations`, the result is typically `SearchHits<T>`, where each `SearchHit<T>` holds the content and metadata of a hit.

`SearchHit.getSortValues()` returns the sort values provided by Elasticsearch:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

if (!hits.getSearchHits().isEmpty()) {
    SearchHit<Product> lastHit =
        hits.getSearchHits().get(
            hits.getSearchHits().size() - 1
        );

    List<Object> nextPosition = lastHit.getSortValues();
}
~~~

This is the authoritative source for the continuation position. Do not construct the list manually from entity properties, because sort values may include hidden fields, tie-breakers, normalized values, or an ordering determined by Elasticsearch.

### Sort Values Depend on the Sort Definition

Example query sort:

~~~json
{
  "sort": [
    { "updatedAt": "desc" },
    { "productId": "asc" }
  ]
}
~~~

`getSortValues()` returns the values corresponding to `updatedAt` followed by `productId`. If the query uses PIT and Elasticsearch adds `_shard_doc`, the list may contain an additional element.

Do not assume `sortValues.get(0)` is always an ID, score, or timestamp. Understand the sort order of the running query and pass back the entire list.

## 9. Using NativeQuery to Pass search_after

In modern Spring Data Elasticsearch, `NativeQuery` lets you declare Query DSL, sort, pageable, and search-after values. Builder APIs may vary depending on the release train and Elasticsearch Java API Client version.

The example below illustrates the implementation structure; verify exact sort/query overloads against your actual dependencies:

~~~java
NativeQueryBuilder builder = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .withSort(SortOptions.of(s -> s.field(f -> f
        .field("price")
        .order(SortOrder.Asc)
    )))
    .withSort(SortOptions.of(s -> s.field(f -> f
        .field("productId")
        .order(SortOrder.Asc)
    )))
    .withPageable(PageRequest.of(0, 50));

if (searchAfterValues != null && !searchAfterValues.isEmpty()) {
    builder.withSearchAfter(searchAfterValues);
}

NativeQuery query = builder.build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

The first request passes `null` or an empty list for `searchAfterValues`. Subsequent requests use the sort values taken from the last hit of the previous response.

A helper method can isolate cursor extraction:

~~~java
private List<Object> nextSearchAfter(SearchHits<Product> hits) {
    List<SearchHit<Product>> page = hits.getSearchHits();

    if (page.isEmpty()) {
        return List.of();
    }

    return page.get(page.size() - 1).getSortValues();
}
~~~

If using `Pageable`, keep the page number at `0` for `search_after` requests and update the cursor between calls. In this case, `Pageable` mainly serves to supply page size and API-supported paging information; do not use page number to increment the offset.

### Do Not Arbitrarily Mix Pageable Sort with NativeQuery Sort

A query can receive sort definitions from multiple sources. If you both configure sort in `NativeQuery` and pass another sort via `Pageable`, you must understand the merge order of your Spring Data version. It is best to have a single source of truth defining the sort for the cursor and use that exact order on every request.

## 10. Designing a Cursor for the API

Do not force the frontend to construct `search_after` from displayed fields. The server should return an opaque cursor representing the continuation position.

Example API response:

~~~json
{
  "items": [
    {
      "id": "p-31",
      "name": "Wireless Mechanical Keyboard",
      "price": 69.0
    }
  ],
  "nextCursor": "opaque-cursor-token",
  "hasMore": true
}
~~~

Next request:

~~~http
GET /products/search?cursor=opaque-cursor-token
~~~

The server decodes the cursor, validates it, and builds the Elasticsearch request with the exact query, sort, PIT, and `search_after` values.

### What Can a Cursor Contain?

A server-generated cursor can store or reference:

- Sort values of the last hit on the page.
- PIT ID if PIT is in use.
- Query fingerprint or search session ID.
- Sort definition or its version.
- Target index or alias.
- Expiration timestamp.
- Cursor format version.

There are two common approaches:

**Self-contained cursor:** an encrypted or signed token carrying the required data. This reduces server-side session storage, though token size and payload protection must be managed.

**Server-side referenced cursor:** a random token pointing to a session stored in a cache or database. The server retains the PIT ID, sort values, and query state. This makes revocation easy and hides Elasticsearch metadata, at the cost of session management.

Base64 is merely encoding, not security. If a cursor contains a PIT ID or internal data, use an appropriately signed or encrypted token; never trust client-modified cursor data.

### Cursors Must Be Bound to the Original Query

If a client submits a cursor from a `"keyboard"` query while changing the keyword to `"mouse"`, the server should not continue using the old sort position. Similarly, do not allow changing filters or sort mid-session without starting a new cursor.

One approach is to store a query fingerprint inside the cursor. On the next request, the server computes the fingerprint from the current criteria and compares them. If they differ, reject the cursor or require starting a new search.

## 11. Distinguishing search_after and scroll

Both `search_after` and `scroll` support traversing large result sets, but they serve different types of workloads.

| Criterion | search_after | Scroll |
|---|---|---|
| Continuation mechanism | Sort values of the last hit | Scroll ID / search context |
| Result ordering | Requires a stable sort | Can use an order suited for batch export |
| Common use cases | Deep pagination, cursor APIs | Reading/exporting large volumes in batches |
| Stable snapshot | Combine with PIT | Scroll retains a search context for the scroll duration |
| Jump to arbitrary position | No | No |
| State management | Cursor and optionally PIT | Scroll ID |
| Ending the session | No more pages or close PIT | Clear scroll |

For interactive search experiences, `search_after` combined with PIT is usually the right choice when deep pagination and consistent results are required. For batch full-data exports, `scroll` remains an option for suitable use cases; PIT combined with `search_after` can also be used to traverse large datasets in order.

Avoid keeping a scroll context open for a long time simply because a user might open a page and return hours later. Both search contexts and PITs consume cluster resources and require explicit session lifecycle management.

## 12. When Should You Not Use search_after?

`search_after` is not suitable for every interface.

Do not choose it if:

- Users must jump directly to an arbitrary page number.
- The application only needs small, shallow offsets, such as the first few pages.
- The sort cannot guarantee a stable order.
- The client cannot retain or send a cursor between requests.
- The query or sort changes completely on every page transition.
- The use case calls for data export via a better-suited batch mechanism.

For small result sets, `from` and `size` are simpler. For sequential deep browsing, `search_after` is more efficient than offset pagination. For large data exports, compare `PIT + search_after` against `scroll` based on snapshot, ordering, and session lifecycle requirements.

## 13. Common Mistakes When Using search_after

| Symptom | Possible cause | Resolution |
|---|---|---|
| Duplicate results across two pages | Sort is not stable enough or cursor was not taken from the last hit | Add a tie-breaker and extract sort values from the last hit |
| Some hits are skipped | Only part of the sort values was passed or sort order changed | Pass the entire list in the exact order |
| Next request throws a sort error | Cursor value types do not match the sort fields | Preserve the exact types and values returned by the server |
| Later pages show data different from the initial set | Index changed between requests | Use PIT for a stable browsing session |
| Old cursor returns wrong results | Query, filter, or sort changed | Bind the cursor to a query fingerprint |
| No next cursor even though the page has data | Sort values read from the first hit or empty list mishandled | Read from the last hit and check size |
| Cursor works for one sort but breaks for another | Sort value structures differ | Include sort definition/version in the cursor |
| Still hitting the offset limit | Incrementing `from` alongside `search_after` | Keep `from` at `0` or omit it from the request |
| PIT expired | Keep-alive too short or session left idle too long | Handle expiry and start a new session |
| High resource usage from many open sessions | PIT not closed or TTL too long | Close sessions and bound session lifetimes |

### Building Sort Values from the Entity Instead of the Response

A common mistake is constructing the cursor manually:

~~~java
List<Object> cursor = List.of(
    lastProduct.getPrice(),
    lastProduct.getProductId()
);
~~~

This might work by coincidence when the query sorts strictly on those two properties. However, it easily breaks when the query uses formatting, missing-value handling, script sorts, nested sorts, or a PIT tie-breaker.

Extract them directly instead:

~~~java
List<Object> cursor =
    lastHit.getSortValues();
~~~

### Passing Incomplete Values

If the sort includes `updatedAt`, `price`, and `productId`, the cursor needs all three values. If using PIT and the response includes `_shard_doc`, retain that value as well. Never drop elements you do not recognize.

## 14. Testing Pagination and Cursors

An integration test should seed data with duplicate sort values to prove that the tie-breaker works.

Example dataset:

| productId | price |
|---|---:|
| p-01 | 50 |
| p-02 | 50 |
| p-03 | 50 |
| p-04 | 70 |
| p-05 | 70 |
| p-06 | 90 |

With page size 2 and sort `price asc, productId asc`, expected pages are:

| Page | Results |
|---|---|
| 1 | p-01, p-02 |
| 2 | p-03, p-04 |
| 3 | p-05, p-06 |

Tests should verify:

- No document appears twice.
- No document is skipped.
- Ordering among hits with equal price remains deterministic.
- The cursor is extracted from the last hit of each response.
- Subsequent requests preserve the query and sort.
- When a response is empty, the API does not generate a new cursor.
- A cursor cannot be reused with a different filter or sort.
- The PIT is closed or expires according to policy.

Test skeleton:

~~~java
@Test
void traversesAllHitsWithSearchAfter() {
    // Index six products, including multiple products with the same price.
    // Build a query sorted by price asc then productId asc.
    // Fetch the first page and record the IDs and sort values of the last hit.
    // Send subsequent requests using search_after.
    // Loop until the response is empty.
    // Assert that all six IDs appear exactly once and in the expected order.
}
~~~

This is a scenario skeleton. Elasticsearch test configuration and query-building APIs depend on the project's Spring Data Elasticsearch version.

With PIT, add a test where the index is updated between two requests. Results within the same PIT must reflect the opened snapshot; a new session can observe the newly indexed documents. Also test PIT expiration handling and context cleanup.

## 15. Pre-Release Checklist for search_after Pagination

- [ ] Queries and filters are normalized and kept identical across the browsing session.
- [ ] Sort has a deterministic order and a unique tie-breaker.
- [ ] Every sort field supports appropriate sorting/doc values.
- [ ] `_id` is not relied upon directly as a regular sort field.
- [ ] Subsequent requests pass all sort values of the last hit.
- [ ] Data types and ordering of sort values are preserved.
- [ ] `from` is not incremented when using `search_after`.
- [ ] Page size is bounded.
- [ ] Cursors are bound to the corresponding query, filter, sort, and index/alias.
- [ ] Cursors are signed, encrypted, or server-side referenced when protection is needed.
- [ ] PIT is used when a consistent snapshot across multiple requests is required.
- [ ] Latest PIT ID is retained and `keep_alive` is extended properly.
- [ ] PITs are closed or have an expiration mechanism.
- [ ] Empty responses are handled as end-of-data.
- [ ] Integration tests include duplicate sort values and verify no duplicates or missing hits.

`search_after` turns deep pagination into continuing from a position in the sort order. `SearchHit.getSortValues()` provides that position; the application preserves the values and resends them with the same query and sort in the next request. When you need a stable result set across calls, combine `search_after` with PIT and manage cursors with a clear lifecycle. This approach fits cursor-based search and sequential traversal workflows over large result sets.
