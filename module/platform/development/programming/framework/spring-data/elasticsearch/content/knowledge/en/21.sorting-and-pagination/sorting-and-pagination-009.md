# `track_total_hits` and Trade-Offs When Counting Total Results

When searching with Elasticsearch, an application often needs two different pieces of information: the list of documents to display and the total number of documents matching the search criteria. The result list serves the current page; the total hit count serves messages like "12,450 results found", computing total pages, or deciding whether a next page exists.

Computing the exact total number of documents can be resource-intensive, especially when a query matches hundreds of thousands or millions of documents. Elasticsearch provides the `track_total_hits` parameter to adjust the level of counting. Applications can request exact counts, count only up to a threshold, or disable counting altogether.

In Elasticsearch, total hits are tracked accurately up to 10,000 by default. When matching documents exceed that threshold, the response may report only a lower bound, such as "at least 10,000 results". This is an intentional trade-off so search can focus on retrieving top results without always counting every single matching document.

## 1. Distinguishing Returned Hit Count from Total Hit Count

In the Search API, `from` and `size` determine the window of results returned. `track_total_hits` determines how accurately Elasticsearch tracks the total number of documents matching the query.

For example:

```http
GET /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

The request asks for at most the first 20 documents. If there are 250,000 active products, `hits.hits` still contains at most 20 items, while `hits.total` describes the number of matching documents according to the tracking mode.

| Component | Meaning |
|---|---|
| `from` | Starting position in the sorted list. |
| `size` | Maximum number of documents returned in the response. |
| `track_total_hits` | Precision level to track for total documents matching the query. |
| `hits.hits` | Actual documents returned for the current page. |
| `hits.total` | Information about total matching documents, if tracking is requested. |

`size: 20` does not mean the total result count is 20. Conversely, `track_total_hits: true` does not make Elasticsearch return all documents; it only requests counting total hits accurately.

## 2. Structure of `hits.total`

In a Search API response, total hits usually take the form of an object:

```json
{
  "hits": {
    "total": {
      "value": 250000,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "P-100",
        "_source": {
          "name": "Mechanical Keyboard"
        }
      }
    ]
  }
}
```

Two key properties:

- `value`: reported hit count.
- `relation`: indicates whether `value` is an exact number or merely a lower bound.

`relation` has two primary values:

| Value | Meaning | Interpretation |
|---|---|---|
| `eq` | Exact count | `value` is the exact total number of matching documents. |
| `gte` | Greater than or equal | At least `value` documents match; the actual number may be larger. |

Example response:

```json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    },
    "hits": []
  }
}
```

This response means there are at least 10,000 matching documents, not that the exact total is 10,000. In reality there could be 12,000, 250,000, or more.

If `track_total_hits` is disabled, Elasticsearch omits the `hits.total` object. In that case, do not interpret the absence of `hits.total` as zero matching documents. The `hits.hits` list can still contain results.

## 3. Modes of `track_total_hits`

Elasticsearch accepts three types of values for `track_total_hits`: boolean `true`, boolean `false`, or a positive integer representing a counting threshold.

### 3.1. Omitted: Default 10,000

If a request does not specify `track_total_hits`, Elasticsearch tracks total hits accurately up to 10,000 by default:

```json
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

If 4,200 documents match, the response can return:

```json
"total": {
  "value": 4200,
  "relation": "eq"
}
```

If 250,000 documents match, the response can return:

```json
"total": {
  "value": 10000,
  "relation": "gte"
}
```

The application must read both `value` and `relation`, rather than taking the `value` number alone.

### 3.2. `track_total_hits: true`: Exact Counting

When set to `true`, Elasticsearch must accurately track all documents matching the query:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": true,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

The response will have `relation: "eq"` if the request completes normally:

```json
"total": {
  "value": 250000,
  "relation": "eq"
}
```

This mode fits when the UI or business logic genuinely requires an exact total, such as:

- Displaying "Total 250,000 results".
- Calculating exact total pages.
- Exporting reports needing exact record counts.
- Reconciling the number of documents matching a condition.

In return, Elasticsearch may have to perform extra work to count every matching document. For queries with large match counts, this can increase execution time and resource usage.

### 3.3. `track_total_hits: false`: Do Not Count Totals

If the application only needs the result list and not the total count, tracking can be disabled:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": false,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Elasticsearch still finds and returns up to 20 matching documents, but the response omits `hits.total`.

This mode suits:

- Infinite scroll that only needs to load more results.
- Recommendation pages or "you may also like" lists.
- APIs returning only the first items without showing a total count.
- Workflows needing only an initial batch of results to proceed to the next step.

Do not use `track_total_hits: false` if the client depends on exact totals to render page counts or total result banners.

### 3.4. `track_total_hits: N`: Count Up to a Threshold

You can pass an integer to ask Elasticsearch to count accurately up to that threshold:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": 2000,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

If matching documents do not exceed 2,000, the response returns the exact count with `relation: "eq"`. If documents exceed the threshold, the response reports a lower bound with `relation: "gte"`.

For example:

| Actual documents | Threshold | `hits.total.value` | `relation` |
|---:|---:|---:|---|
| 320 | 2,000 | 320 | `eq` |
| 2,000 | 2,000 | 2,000 | `eq` |
| 8,500 | 2,000 | 2,000 | `gte` |
| 250,000 | 2,000 | 2,000 | `gte` |

This is a balanced choice for UIs needing a moderate total count without paying to count massive result sets. For instance, displaying "2,000+ results" in the UI is sufficient.

## 4. Performance Trade-Offs of Counting Totals

Elasticsearch is typically optimized to find the top most relevant documents. When a query matches very many documents, accurately counting all matches can force the system to do extra work the UI does not genuinely need.

For relevance-ranked queries, Elasticsearch can apply optimizations such as Max WAND to skip documents that cannot enter the top results. When exact total counting is requested, some of these optimizations cannot be used in the same way, potentially making queries slower.

The difference depends on:

- Number of documents matching the query.
- Query complexity and shard count.
- Whether sorting by `_score` or by fields.
- Number of clauses and bool/nested query structure.
- Whether aggregations or other features require scanning many documents.
- Cluster resources, caches, and concurrent load.

There is no fixed multiplier stating how many times slower `track_total_hits: true` is. Measure with representative queries and production-like data.

### Comparing the Three Options

| Configuration | Total count accuracy | Counting cost | Best suited for |
|---|---|---|---|
| `false` | No total count | Lowest tracking cost | Not displaying a total count. |
| Integer `N` | Exact up to N; above N only `>= N` is known | Bounded | Only needing a threshold or "N+" label. |
| `true` | Fully exact | Can be high on large match sets | Mandatory exact count display/reconciliation. |

Normally, if a product does not require an exact number, avoid turning on `true` for every request just to show a number in the corner of the UI.

## 5. `track_total_hits` Does Not Affect Document Count per Page

A common misconception is thinking that setting `track_total_hits: 100` limits the search to returning at most 100 documents. That is incorrect.

For example:

```json
GET /products/_search
{
  "from": 20,
  "size": 50,
  "track_total_hits": 100,
  "query": {
    "match_all": {}
  }
}
```

The request can still return 50 documents starting at offset 20. The value 100 is solely the total-hit tracking threshold. It does not change `size`, does not cap total data in the index, and does not limit how many documents can match.

Conversely, `size: 0` only asks not to return documents in `hits.hits`; it does not automatically disable total counting. If you want only to count without retrieving documents, use `size: 0` with an appropriate tracking mode.

## 6. Configuring `track_total_hits` in Spring Data Elasticsearch

Spring Data Elasticsearch exposes this option on the `Query` abstraction. Thus it can be configured on `CriteriaQuery`, `NativeQuery`, or other query objects implementing `Query`.

Two methods to know:

- `setTrackTotalHits(Boolean)`: enables or disables tracking.
- `setTrackTotalHitsUpTo(Integer)`: sets the tracking threshold.

Per the Spring Data Elasticsearch API, `setTrackTotalHits` has been available since version 4.0 and `setTrackTotalHitsUpTo` since 4.1. The threshold parameter takes effect only when `getTrackTotalHits()` is `null`; if boolean `true` or `false` is already set, the boolean takes precedence.

### 6.1. Requesting Exact Counting

Example with `NativeQuery`:

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();

query.setTrackTotalHits(true);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

The query still returns at most 20 documents on the page, while requesting exact tracking of total matches.

### 6.2. Disabling Tracking

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();

query.setTrackTotalHits(false);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

When tracking is disabled, do not use `hits.getTotalHits()` to infer the number of matching documents. Check the relation or design responses that do not require a total count.

### 6.3. Counting Accurately Up to a Threshold

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();

query.setTrackTotalHitsUpTo(2000);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Do not call `setTrackTotalHits(true)` or `false` on the same query if you want the `2000` threshold to take effect, because the boolean takes precedence. If the query was configured elsewhere, inspect `getTrackTotalHits()` before sending the request.

### 6.4. Using CriteriaQuery

This option is not exclusive to NativeQuery. For example:

```java
Criteria criteria = new Criteria("status").is("ACTIVE");
CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));
query.setTrackTotalHitsUpTo(1000);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Both CriteriaQuery and NativeQuery can use common `Query` options. If queries are created by custom builders or helpers, centralize tracking configuration so different endpoints do not behave inconsistently.

## 7. Reading Accuracy from `SearchHits`

Spring Data Elasticsearch does not just return a bare total hits number. `SearchHits<T>` provides both the total count and its relation:

- `getTotalHits()` returns the reported total value.
- `getTotalHitsRelation()` indicates whether that value is exact, a lower bound, or tracking was disabled.

For example:

```java
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

long total = hits.getTotalHits();
TotalHitsRelation relation = hits.getTotalHitsRelation();

switch (relation) {
    case EQUAL_TO -> log.info("Exact total hits: {}", total);
    case GREATER_THAN_OR_EQUAL_TO ->
            log.info("At least {} documents matched", total);
    case OFF -> log.info("Total hit tracking is disabled");
}
```

`TotalHitsRelation` has the following values:

| Spring Data value | Meaning |
|---|---|
| `EQUAL_TO` | Exact total count, corresponding to Elasticsearch `eq`. |
| `GREATER_THAN_OR_EQUAL_TO` | Lower bound total count, corresponding to Elasticsearch `gte`. |
| `OFF` | Total hit tracking is disabled. |

Do not simply call `getTotalHits()` and display it as an exact count. For instance, `total = 10000` with relation `GREATER_THAN_OR_EQUAL_TO` should be displayed as "10,000+", not "10,000 results".

If tracking is disabled, any numeric value returned by the abstraction cannot be treated as an actual total. Rely on relation `OFF` to know that the count was not tracked.

## 8. Impact on `Page`, `SearchPage`, and API Responses

A standard `Page<T>` assumes a total element count to compute `getTotalElements()` and `getTotalPages()`. When total hits is only a lower bound or tracking is off, overall page totals are no longer exact.

For example:

```java
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

SearchPage<ProductDocument> page =
        SearchHitSupport.searchPageFor(hits, pageable);
```

`SearchPage` retains `SearchHits` and pagination details, but if the total hit relation is `GREATER_THAN_OR_EQUAL_TO`, do not present `getTotalElements()` as an exact total. If the relation is `OFF`, the total count is meaningless.

### When the UI Needs Exact Total Pages

If the UI displays:

```text
Page 3 / 125
Total 2,498 results
```

then an exact total or a different page-counting strategy is needed. You can enable `track_total_hits: true`, or call a separate Count API if appropriate.

### When the UI Only Needs a "Load More" Button

If the UI only needs to know whether more results remain, no total count is required. You can return a structure like:

```json
{
  "items": [
    { "id": "P-100", "name": "Mechanical Keyboard" }
  ],
  "hasMore": true
}
```

In this case, tracking can be disabled and an over-fetch-by-one strategy can determine `hasMore`.

## 9. Using `size + 1` to Determine Whether a Next Page Exists

A simple way to avoid counting total results is requesting one extra document beyond the display count.

For example, when the UI displays 20 products:

1. Send a request with `size = 21` and `track_total_hits = false`.
2. If 21 documents are returned, return the first 20 documents and set `hasMore = true`.
3. If at most 20 documents are returned, return all of them and set `hasMore = false`.

Code example:

```java
int pageSize = 20;
// This example fetches the first page. For later offset pages,
// keep from = page * pageSize while requesting size = pageSize + 1.
Pageable pageable = PageRequest.of(0, pageSize + 1, sort);

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(pageable)
        .build();
query.setTrackTotalHits(false);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

List<ProductDocument> fetched = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();

boolean hasMore = fetched.size() > pageSize;
List<ProductDocument> items = fetched.stream()
        .limit(pageSize)
        .toList();
```

This example covers the first page of offset pagination. For subsequent pages, keep the offset aligned to the display page size (`from = page * pageSize`) while requesting one extra hit; do not mechanically call `PageRequest.of(page, pageSize + 1)`, as that advances offset by `pageSize + 1` and skips documents at page boundaries. You can use a request with explicit `from`/`size` or a custom `Pageable`. When data changes between calls or users reach very deep pages, offset pagination still has its own issues. For large traversal flows, consider `search_after` combined with stable sorting and Point in Time.

`size + 1` answers "are there more results?" without needing the total number of documents in the index.

## 10. When an Exact Total Is Needed: Count API

If a search request must be optimized for top results while another component needs an exact count, you can split into two requests:

1. Search API fetches the result list with `track_total_hits: false` or a low threshold.
2. Count API calculates the total number of documents matching the query.

REST API:

```http
POST /products/_count
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Response:

```json
{
  "count": 250000,
  "_shards": {
    "total": 5,
    "successful": 5,
    "skipped": 0,
    "failed": 0
  }
}
```

Spring Data Elasticsearch provides `ElasticsearchOperations.count(...)`:

```java
Criteria countCriteria = new Criteria("status").is("ACTIVE");
CriteriaQuery countQuery = new CriteriaQuery(countCriteria);
long exactCount = operations.count(countQuery, ProductDocument.class);
```

The Count API does not return document lists and does not need to sort results, yet it still must execute the query to count matching documents. In the example, `countQuery` must carry the same business conditions as the search query, without needing pageable or sort. It is not free and can take time for queries matching many documents. Splitting requests is useful when top-hits search and counting have different requirements or frequencies, though total system cost may rise if both are always called.

If the query filters by tenant, status, or access permissions, ensure the count query includes the exact same filters as the search query. Missing filters can cause the count to exceed the result set the user is permitted to see.

## 11. Distinguishing `track_total_hits` from `terminate_after`

Both options can prevent an application from receiving a full total count, yet their purposes and semantics differ.

| Option | Purpose | Effect |
|---|---|---|
| `track_total_hits` | Controls total hit counting precision. | May return exact count, lower bound, or omit total. |
| `terminate_after` | Stops collecting documents early after a per-shard limit. | Search may terminate early and not fully represent the matching document set. |

Example `terminate_after`:

```json
GET /products/_search
{
  "size": 0,
  "terminate_after": 1,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

This is a technique useful when merely checking quickly whether any matching document exists. `terminate_after` applies per shard and can terminate a query early; the response may indicate `terminated_early`.

Do not use `terminate_after` in place of `track_total_hits` to produce a meaningful lower bound for the UI. If the goal is counting up to a threshold, use an integer `track_total_hits`. If the goal is not counting, use `false`.

## 12. `track_total_hits` Does Not Solve Deep Pagination

`track_total_hits` only controls total hit counting. It does not raise `from`/`size` limits and does not make deep pagination cheaper.

For example, page 500 with size 20 must skip the first 10,000 results. Elasticsearch has a default result window limit usually set to 10,000. Even with total-hit tracking disabled, a very deep offset request can still consume heavy resources or exceed `index.max_result_window`.

For lists requiring deep traversal, consider:

- `search_after` to fetch subsequent results using sort values of the last hit from the previous page.
- Point in Time (PIT) if a stable data view across requests is needed.
- Scroll for appropriate batch-processing pipelines, not for general UI pagination.

These mechanisms address large-result traversal; `track_total_hits` is strictly a separate choice regarding total counts.

## 13. Impact When Aggregations Are Present

A search request can both return top documents and compute aggregations/facets. Aggregations usually must examine matching documents to compute buckets or metrics. In that case, turning off exact total hits does not mean Elasticsearch can skip documents outside the top results, because aggregations still need data across the broad match set.

For example:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": false,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand"
      }
    }
  }
}
```

The request disables total hit tracking, yet still requests the `by_brand` aggregation. Therefore, the real performance benefit of turning off tracking may differ from a top-hits-only query. Benchmark the actual production requests, including aggregations and sorting.

## 14. Designing API Responses Based on UI Needs

Not every endpoint needs to return `totalElements`.

### Endpoint Using Exact Page Numbers

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 250000,
  "totalPages": 12500,
  "totalExact": true
}
```

To return this response shape, the endpoint must have an exact count. You can use `track_total_hits: true` or a separate count query depending on workload.

### Endpoint Needing Only a Lower Bound

```json
{
  "items": [],
  "minimumTotal": 10000,
  "totalRelation": "gte",
  "displayLabel": "10,000+ results"
}
```

This response preserves Elasticsearch's exact semantics. Do not turn a lower bound into an exact total figure.

### Infinite Scroll Endpoint

```json
{
  "items": [],
  "nextCursor": "opaque-sort-cursor",
  "hasMore": true
}
```

The endpoint needs no total count; it only provides a cursor or flag to fetch the next page.

### Choosing Mode by UX

| UX | Suggested tracking | Response |
|---|---|---|
| Display exact total pages | `true` or separate count | `totalElements`, `totalPages`. |
| Only need "10,000+ results" | Integer threshold | `minimumTotal`, relation. |
| "Load more" button | `false` and over-fetch by one hit | `hasMore`. |
| Cursor-based infinite scroll | `false` | `nextCursor`, `hasMore`. |
| Only return a few suggestions | `false` | List of items. |

## 15. Measuring Before Choosing a Threshold

There is no single optimal threshold for all systems. You can start with the 10,000 default, then measure representative query groups:

1. Low-match queries, e.g., under 100 documents.
2. Medium-match queries, e.g., a few thousand documents.
3. Common queries matching hundreds of thousands of documents.
4. Queries with multi-condition filters.
5. Queries sorting by `_score`.
6. Queries with aggregations/facets.
7. Queries under production-like concurrent load.

Compare at least these configurations:

- Omitted (default).
- `track_total_hits: false`.
- A UX-appropriate threshold, such as 1,000 or 5,000.
- `track_total_hits: true`.

Record:

- p50, p95, and p99 latency.
- Node CPU and heap.
- Throughput and error rate.
- Returned total hits and relation.
- Impact on other queries on the cluster.

Do not benchmark only once. Warm/cold caches, refreshes, merges, and concurrent load can skew numbers. Run multiple iterations under comparable conditions and inspect both latency and resource usage.

## 16. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| UI shows 10,000 results even when more exist | Reading `hits.total.value` while ignoring `relation: gte`. | Display "10,000+" or request an exact count. |
| `hits.total` missing from response | `track_total_hits` was disabled. | Do not interpret as zero hits; check `hits.hits` and Spring Data relation. |
| Page has only 20 items while total is 100,000 | `size` is returned item count; total is matching item count. | Handle the two values independently. |
| Query slows down when `true` is enabled | Elasticsearch must count all matches accurately and may lose some top-k optimizations. | Enable exact count only when UX requires it; try thresholds or separate count. |
| `setTrackTotalHitsUpTo` has no effect | `setTrackTotalHits(true/false)` was also set. | Leave the boolean `null` when using a threshold. |
| `Page.getTotalPages()` is inaccurate | Total hits is only a lower bound or tracking is disabled. | Do not compute page counts from inexact totals; change response/strategy. |
| Using `terminate_after` as a counting threshold | Queries can terminate early per shard rather than counting to a standard lower bound. | Use an integer `track_total_hits`. |
| Raising `index.max_result_window` for deep pages | Confusing offset pagination limits with total hit tracking. | Use `search_after`/PIT for deep traversal. |
| Disabling total tracking while aggregations stay slow | Aggregations still process matching documents. | Benchmark requests with aggregations separately and optimize them. |

## 17. Checklist for Choosing a Tracking Mode

Before enabling exact counting, verify:

1. Does the UI genuinely require an exact result count?
2. Do users need the final page number, or only to know if more results exist?
3. When counts are large, does an "N+" label satisfy the UX?
4. Can `size + 1` be used to determine `hasMore`?
5. Should the Count API be separated from the Search API?
6. Does the API response preserve `eq`, `gte`, or `OFF` semantics?
7. Does the query include aggregations that diminish the benefit of skipping exact counts?
8. Have p95/p99 and resources been measured with production-like data?
9. Is `track_total_hits` being confused with `size`, `from`, `terminate_after`, or `index.max_result_window`?

## 18. Key Takeaways

- `size` controls how many documents are returned; `track_total_hits` controls how accurately total matching documents are counted.
- By default, Elasticsearch tracks accurately up to 10,000 hits; above the threshold, it may return `relation: "gte"`.
- `track_total_hits: true` requests an exact total and can make queries more expensive.
- `track_total_hits: false` disables tracking; responses omit `hits.total` while still returning documents in `hits.hits`.
- An integer value requests exact counting up to that threshold; above it, only at least N hits is known.
- `eq` means exact; `gte` means lower bound.
- Spring Data Elasticsearch provides `setTrackTotalHits` and `setTrackTotalHitsUpTo` on Query; the threshold only takes effect when the boolean is unset.
- `SearchHits` provides both `getTotalHits()` and `getTotalHitsRelation()`; read both.
- Do not use lower-bound or disabled totals to compute exact `totalPages`.
- Use Count API or `ElasticsearchOperations.count(...)` when a separate exact count is needed, while still measuring cost.
- Use `size + 1` for `hasMore` or `search_after`/PIT for cursor pagination when totals are unnecessary.
- `terminate_after` and `track_total_hits` solve two distinct problems.
- Turning off exact totals does not guarantee queries with aggregations will speed up significantly; benchmark real requests.

`track_total_hits` is a tool for tuning search cost to UI needs. Decide upfront whether users need an exact figure, a lower bound, or no total at all; then pass that choice through Spring Data Elasticsearch and preserve accuracy semantics in the response to avoid displaying misleading numbers.

## References

- [Elasticsearch Search API — Track total hits](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/SearchOperations.html)
