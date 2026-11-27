# The index.max_result_window Limit and Deep Pagination Cost

Elasticsearch supports pagination using two familiar parameters: **from** and **size**. This approach suits lists with a moderate number of pages, but cost grows when users request a very deep offset. To prevent a single query from forcing every shard to retain too many intermediate results, Elasticsearch enforces the **index.max_result_window** limit, typically 10,000 by default.

When a request exceeds this limit, Elasticsearch rejects the query with a result window too large error. Raising the setting can let the request succeed, but it does not eliminate the CPU, heap, merge, and network cost of deep pagination. For large datasets, reconsider how results are navigated: use search_after combined with Point in Time (PIT) for stable cursor pagination, or use scroll for appropriate batch workflows.

This lesson explains how from/size works, why deep pagination is resource-intensive, how to configure and test max_result_window, how to use Spring Data Elasticsearch, and how to choose an alternative strategy based on product requirements.

## 1. How Do from and size Work?

A search request uses from and size to skip an initial number of hits and return the subsequent hits:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    { "createdAt": "desc" }
  ]
}
~~~

- **from** is the number of hits to skip before starting to return results.
- **size** is the maximum number of hits to return.
- The first page of 20 items uses from = 0, size = 20.
- The second page uses from = 20, size = 20.
- The third page uses from = 40, size = 20.

Offset formula for page-based pagination:

\[
from = pageNumber \times pageSize
\]

Here pageNumber starts at 0. For example, page 50 with page size 20 has from = 1,000.

Elasticsearch does not merely locate the final 20 hits. To return results at offset 1,000, shards must find and hold enough candidates up to position from + size, after which the coordinator merges results from shards and discards the skipped portion.

## 2. What Is index.max_result_window?

index.max_result_window is an index setting that limits the sum of from + size in a single search request. The common default value is **10,000**.

Condition:

\[
from + size \leq index.max\_result\_window
\]

Example with a limit of 10,000:

| from | size | from + size | Result |
|---:|---:|---:|---|
| 0 | 20 | 20 | Valid |
| 980 | 20 | 1,000 | Valid |
| 9,980 | 20 | 10,000 | Valid |
| 10,000 | 20 | 10,020 | Exceeds limit |
| 50,000 | 100 | 50,100 | Exceeds limit |

This limit applies to an index's search result window. It does not mean an index can only hold 10,000 documents or only find 10,000 matches. Elasticsearch can still index and search much larger datasets; the limit governs retrieving a slice of results by offset.

The setting is configured per index, so different indices can have different values. With an alias pointing to multiple indices, check the settings of the target indices and ensure requests behave consistently.

## 3. Why Does Elasticsearch Set a 10,000 Limit?

Deep pagination increases the workload on every shard. Suppose an index has 5 primary shards and the application requests:

~~~text
from = 90,000
size = 100
from + size = 90,100
~~~

To determine the 100 hits at that position, each shard must collect a candidate set large enough for the requested result slice. The coordinator must receive, merge, and sort candidates from all shards and then discard the first 90,000 hits.

Costs can grow in multiple areas:

- **CPU:** each shard must process and select more hits.
- **Heap:** structures holding top hits and sort values require memory.
- **Network:** shards transmit more candidates back to the coordinating node.
- **Coordinator:** must merge large result sets across multiple shards.
- **Latency:** requests perform more work before returning deep pages.
- **Concurrency:** multiple simultaneous deep queries can compete for resources with indexing and other searches.

The default limit acts as a guardrail to prevent a request from accidentally requesting too many intermediate results. Raising the limit does not eliminate the cost; it only permits requests to ask for a larger window.

## 4. Cost Grows with from + size, Not Just Returned Hit Count

Two requests can both return 20 hits yet differ dramatically in cost:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20
}
~~~

and:

~~~http
POST /products/_search
{
  "from": 50000,
  "size": 20
}
~~~

The second request still returns only 20 hits to the client, but requires processing a much deeper position. The number of hits in the response does not reflect the total work Elasticsearch performed.

That is why pagination performance should not be judged solely by JSON response size. Measure query latency, CPU, heap, shard workload, network, and coordinating node overhead as offset grows.

## 5. Example Result Window Too Large Error

If an index has max_result_window = 10,000, the following request exceeds the limit:

~~~http
POST /products/_search
{
  "from": 10000,
  "size": 50,
  "query": {
    "match_all": {}
  }
}
~~~

Elasticsearch may return an error like:

~~~json
{
  "error": {
    "root_cause": [
      {
        "type": "illegal_argument_exception",
        "reason": "Result window is too large, from + size must be less than or equal to: [10000] but was [10050]."
      }
    ],
    "type": "search_phase_execution_exception"
  },
  "status": 400
}
~~~

The exact error reason text may vary across versions and configurations, but the cause is from + size exceeding the limit.

In the application, do not turn this error into an automatic retry. Resending the same request cannot make the window valid. Handle it at the API layer: cap the page number, ask users to narrow filters, or switch to cursor pagination.

## 6. Inspecting and Changing the Setting

Read an index setting:

~~~http
GET /products/_settings?include_defaults=true
~~~

You can filter results by setting name:

~~~http
GET /products/_settings/index.max_result_window
~~~

Change the setting for an index:

~~~http
PUT /products/_settings
{
  "index": {
    "max_result_window": 20000
  }
}
~~~

index.max_result_window is a dynamic index setting in current Elasticsearch versions. Check the documentation and exact cluster version before modifying it in production.

Increasing it to 20,000 does not mean the system can serve deep pagination for free. Only raise it after measuring load, confirming the actually needed page depth, and evaluating cluster resources.

## 7. Why Should You Not Set max_result_window Very High?

A quick workaround when hitting the error is setting the limit to 100,000 or 1,000,000. This stops the limit error, but it also allows clients to request huge amounts of intermediate results.

Risks:

- A single user can send deep pagination requests causing heavy load.
- Concurrent requests can spike heap and CPU usage.
- Coordinating nodes must merge far more hits.
- Search latency for other endpoints can degrade.
- The cluster can hit circuit breakers or run out of memory.
- Raising the limit masks an inappropriate pagination design.

Do not raise max_result_window just to make a very distant page reachable. Determine whether users genuinely need to jump straight to that page or merely step forward through results.

If the UI only needs Next/Previous buttons, cursor pagination is usually a better fit. If exporting all data is required, use a batch workflow instead of simulating a massive page.

## 8. Application API Limits

Even if Elasticsearch allows a window of 10,000, the application can enforce lower limits to control load.

For example:

- Maximum pageSize of 100.
- Non-negative pageNumber.
- pageNumber × pageSize does not exceed a business limit.
- Only specific roles are allowed large page sizes.
- Searches must include filtering conditions or timeouts.
- Export endpoints use a dedicated API rather than incrementing page numbers.

A helper validating Pageable:

~~~java
public Pageable validatePageRequest(int page, int size) {
    int maxPageSize = 100;
    long maxWindow = 10_000L;

    if (page < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }

    if (size < 1 || size > maxPageSize) {
        throw new IllegalArgumentException("Invalid page size");
    }

    long from = (long) page * size;
    if (from + size > maxWindow) {
        throw new DeepPaginationNotSupportedException();
    }

    return PageRequest.of(page, size);
}
~~~

Use long when calculating offset to prevent integer overflow when page or size is large. Do not merely check page < an arbitrary number; check from + size against the endpoint's configured limit.

If the application has multiple indices with different max_result_window values, you do not have to expose raw settings to clients. It is usually best to set a stable API policy with explicit bounds independent of internal Elasticsearch settings.

## 9. PageRequest in Spring Data Elasticsearch

With repositories supporting Pageable, Spring Data can translate PageRequest into from/size and sort in the search request.

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("productId")
        )
);

Page<Product> page =
        productRepository.findByStatus("ACTIVE", pageable);
~~~

Second page:

~~~java
Pageable pageable = PageRequest.of(1, 20);
~~~

Spring Data computes offset from page number and page size. Therefore, a large page number can produce a from that exceeds max_result_window.

APIs returning Page normally include totalElements and totalPages. To compute the total element count, the implementation may need to run a count or retrieve total hits according to version semantics. Requesting exact totals also carries its own cost; the UI does not always need an exact figure.

## 10. SearchHits, SearchPage, and Pageable

When using ElasticsearchOperations, the application can receive SearchHits<T> or convert results into SearchPage<T> depending on the API.

General example:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

SearchHits provides hit metadata and total hits. If the Spring Data Page abstraction is needed, use the SearchPage conversion method appropriate to your version.

Do not assume every overload executes the same count request or follows the same total hits policy. Inspect actual queries and how the API computes totalElements when pages are deep or track_total_hits is limited.

## 11. When Is from/size Still a Good Choice?

from/size is simple and works well in these cases:

- Small or medium lists.
- Users mostly view the first few pages.
- Direct jumping to a specific page number is required.
- Results change infrequently while users paginate.
- The API must integrate with a traditional page-number UI.
- from + size always stays within the allowed window.

You do not need to replace all pagination in an application just because Elasticsearch has a 10,000 limit. Choose based on actual product behavior.

For example, an admin list with 300 results and page size 25 can reasonably use Pageable. A dataset with millions of documents requiring sequential traversal should use cursors or batch processing.

## 12. What Is search_after?

search_after is a mechanism to continue searching based on the sort values of the last hit from the previous page. Rather than asking Elasticsearch to skip tens of thousands of initial hits, the client sends a cursor representing the continuation point.

First page:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Suppose the last hit on the page has sort values:

~~~json
[
  "2026-11-13T08:30:00Z",
  "p-020"
]
~~~

Next page:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Elasticsearch starts right after that sort position. Cost does not grow linearly with the number of traversed pages like deep offset from/size.

search_after requires a deterministic sort. All sort values of the last hit must be preserved in the exact order and data types. If sorting by two fields, the cursor must contain two corresponding values.

## 13. Why Does search_after Need a Stable Sort?

If multiple documents share the same sort value, the boundary between two pages can be ambiguous. A hit can be duplicated or skipped when sort values cannot distinguish documents.

Add a unique tie-breaker:

~~~json
"sort": [
  { "createdAt": "desc" },
  { "productId": "asc" }
]
~~~

Here productId is a keyword field and unique within the query scope. If a query runs across multiple tenants, ensure the final key is unique across the entire result set.

Do not use an unstable field like random score for cursor sorting when sequential traversal is desired. Do not change the sort between page requests.

You can use PIT for a stable snapshot; with PIT, Elasticsearch has an internal tie-breaker such as _shard_doc in current versions. Even so, the application must retain the exact sort values returned in the response and follow the documentation for its version.

## 14. Point in Time Combined with search_after

If documents are inserted, updated, or deleted while users paginate, results across multiple requests may no longer belong to the same snapshot. PIT keeps a consistent view for a specified duration.

Flow:

1. Open a PIT for the index or alias.
2. Send the first page with the PIT, sort, and size.
3. Read the sort values of the last hit.
4. Send the next page with the latest PIT ID and search_after.
5. Repeat until results are exhausted.
6. Close the PIT when finished.

Open PIT:

~~~http
POST /products/_pit?keep_alive=1m
~~~

First search:

~~~http
POST /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

The next page adds the sort values from the last hit into search_after. If the response returns a new PIT ID, use the latest ID for the subsequent request.

Close PIT:

~~~http
DELETE /_pit
{
  "id": "PIT_ID"
}
~~~

PIT retains a search context and consumes resources during its lifetime. Set an appropriate keep_alive, close it when finished, and handle cases where the client stops paginating. Do not open a new PIT for every page if the goal is maintaining a consistent snapshot.

## 15. search_after Is Not Page-Number Pagination

search_after suits sequential navigation:

- First page.
- Next page.
- Following page.
- Going back to a previous page if the application saves cursors or caches needed results.

It does not support jumping straight to page 5,000 the way from/size does. The client must have the cursor from the last hit of the previous page to proceed.

| UI/API need | Appropriate strategy |
|---|---|
| Jump to an arbitrary page number | from/size within limits |
| Next/Load more | search_after |
| Traverse large data needing a snapshot | PIT + search_after |
| Batch data export | PIT + search_after or appropriate scroll |
| Counts and statistics, no hits needed | Aggregation with size = 0 |

If the current UI strictly requires showing total pages and a button to jump to the last page, cursor pagination may require UX adjustments. Do not simulate page numbers by sending a huge from.

## 16. Using search_after with the Elasticsearch Java API Client

The Java API Client allows configuring sort and search_after in SearchRequest. Skeleton example for two sort fields:

~~~java
SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .size(20)
        .sort(sort -> sort.field(f -> f
                .field("createdAt")
                .order(SortOrder.Desc)
        ))
        .sort(sort -> sort.field(f -> f
                .field("productId")
                .order(SortOrder.Asc)
        ))
        .query(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
);

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);
~~~

Getting the cursor from the last hit:

~~~java
List<FieldValue> cursor =
        response.hits().hits().get(response.hits().hits().size() - 1).sort();
~~~

Sending the next request:

~~~java
SearchRequest nextRequest = SearchRequest.of(s -> s
        .index("products")
        .size(20)
        .sort(sort -> sort.field(f -> f
                .field("createdAt")
                .order(SortOrder.Desc)
        ))
        .sort(sort -> sort.field(f -> f
                .field("productId")
                .order(SortOrder.Asc)
        ))
        .searchAfter(cursor)
        .query(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
);
~~~

This example illustrates the modern client API; imports and return types must match your version. Before accessing the last hit, check whether the response has any hits. When using PIT, requests must pass the PIT ID and keep_alive per the client API without letting the query switch to a different search context.

## 17. search_after with Spring Data Elasticsearch

Spring Data Elasticsearch provides NativeQuery for configuring advanced queries. Modern versions support search-after via the corresponding NativeQuery/SearchHits APIs, though exact signatures may vary.

General flow:

1. Create NativeQuery with query and sort.
2. Send the first request.
3. Read sort values from the last SearchHit.
4. Pass those values as search-after for the next NativeQuery.
5. Keep the same query, sort, and PIT if using a snapshot.

Example retrieving sort values:

~~~java
SearchHits<Product> hits =
        operations.search(firstPageQuery, Product.class);

List<Object> searchAfter =
        hits.getSearchHit(hits.getSearchHits().size() - 1)
                .getSortValues();
~~~

Some APIs expose hit lists via iterators or other accessors; use the last-hit retrieval pattern suitable for your version. Also handle empty pages before accessing the last element.

If the NativeQuery builder in your project version has withSearchAfter, pass that list of sort values into the next query. If PIT or features not yet supported by the abstraction are needed, use the Java API Client directly in a repository adapter layer.

Do not serialize sort values into strings and guess when parsing them back. Preserve original data types or convert to the exact types expected by the Java API Client.

## 18. Scroll API and Batch Use Cases

The Scroll API was historically widely used to iterate through large numbers of documents in batches. It maintains a search context on the cluster and lets clients retrieve subsequent batches via a scroll ID.

Scroll fits certain batch/export jobs needing to read large result sets, but it is not the default choice for interactive UI pagination. For new workflows needing deep pagination and snapshots, Elasticsearch recommends considering PIT + search_after.

If using scroll:

- Set an appropriate scroll keep_alive.
- Process batches until the response returns no more hits.
- Retain the latest scroll ID if the response changes it.
- Clear the scroll when finished.
- Do not hold scroll contexts longer than necessary.
- Limit the number of concurrent jobs.
- Do not use scroll as a permanent cursor for end users.

Scroll contexts consume resources. If a client disconnects mid-stream without clearing, the context may remain until its keep_alive expires.

## 19. How Does Scroll Differ from search_after?

| Criterion | from/size | search_after | Scroll |
|---|---|---|---|
| Purpose | Page-number pagination | Cursor/next-page | Batch iteration |
| Deep pagination | Expensive, window-limited | Suitable | Suitable for batches |
| Jump to arbitrary page | Yes, within limits | Not directly | No |
| Stable snapshot | Not guaranteed automatically | Use PIT when needed | Holds search context |
| Resources | Grows with offset | Per batch and sort | Holds scroll context |
| Interactive UX | Good for early pages | Good for next/load more | Generally unsuitable |
| Resource cleanup | No cursor context needed | Close PIT if used | Clear scroll |

Choose according to your goal. Do not mechanically replace every Pageable with scroll or search_after.

## 20. track_total_hits and the Cost of Counting Totals

A search page may need the exact total hit count to display "1–20 of 125,432 results". However, computing exact total hits can increase Elasticsearch's workload.

You can control track_total_hits:

~~~http
POST /products/_search
{
  "track_total_hits": false,
  "from": 0,
  "size": 20,
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Or set a threshold:

~~~json
"track_total_hits": 10000
~~~

When using false or a threshold, the response may not provide an exact total; the total relation may indicate gte instead of eq.

This does not replace max_result_window. track_total_hits controls how total results are counted; max_result_window limits from + size.

If the UI only needs to know whether more results remain, fetch size + 1 hits or use a cursor flow instead of requesting an exact total. Design depends on your API and the capabilities of your abstraction.

## 21. Aggregations Do Not Need Hit Pagination

If an endpoint only needs statistics, do not request thousands of hits only to discard them. Use size = 0 and aggregations:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

In this case, the aggregation returns buckets without loading hit documents. max_result_window is not a bucket-pagination mechanism; terms size and composite aggregations have their own rules.

If you need to iterate over a very large number of buckets, consider a composite aggregation with after_key instead of raising terms size indefinitely.

## 22. Other Limits Not to Confuse with max_result_window

Elasticsearch has several settings related to results and resources:

- **index.max_result_window:** limits from + size for search hits.
- **index.max_inner_result_window:** limits result window for inner hits and corresponding cases.
- **search.max_buckets:** limits the number of aggregation buckets in a single search response.
- **index.max_rescore_window:** limits the rescore window where applicable.
- **track_total_hits:** controls the level of total hit counting.
- **scroll keep_alive:** duration a scroll context is retained.
- **PIT keep_alive:** duration a Point in Time is retained.

Do not raise max_result_window to solve search.max_buckets or inner hits errors. Read the exact error type and related setting.

## 23. Designing a Cursor Pagination API

A cursor API can return:

~~~json
{
  "items": [
    {
      "id": "p-001",
      "name": "Mechanical Keyboard"
    }
  ],
  "nextCursor": "opaque-cursor-token",
  "hasNext": true
}
~~~

The cursor can encode sort values and query context, or be a token referencing state stored on the server.

Do not let clients arbitrarily tamper with sort values, tenant filters, or indices inside a cursor. Sign the token or store state server-side. If the cursor contains sensitive details, do not send a plaintext payload in the URL.

A cursor should be bound to:

- Normalized query/filter.
- Sort order.
- Tenant or permission scope, if applicable.
- PIT ID if PIT is used.
- Sort values of the last hit.
- Schema/API version if needed.
- Expiration timestamp.

On each subsequent request, verify the current principal and ensure the cursor belongs to the same access scope. Do not treat a cursor as a credential replacing authorization.

## 24. Testing max_result_window

An integration test should verify behavior at the setting boundary:

1. Create a test index with a small max_result_window, such as 100.
2. Send a request with from = 80, size = 20: must succeed.
3. Send a request with from = 81, size = 20: must be rejected.
4. Send a request with size = 101 from 0: must be rejected.
5. Verify the application translates window-exceeded errors into an appropriate API error.
6. Verify valid requests still return the right order and count.

Using a small setting in tests lets you verify the logic without indexing tens of thousands of documents. Ensure the test actually sets the option on the test index and does not accidentally hit an alias pointing to another index.

REST example:

~~~http
PUT /products-pagination-test/_settings
{
  "index": {
    "max_result_window": 100
  }
}
~~~

Then create enough fixtures to verify pagination. The window error is determined by from + size; the index does not necessarily need that exact number of documents for a request to exceed the setting.

## 25. Testing Pagination via Spring Data

With repositories and Pageable, test both valid pages and out-of-window pages:

~~~java
@Test
void acceptsPageWithinResultWindow() {
    Pageable pageable = PageRequest.of(4, 20);

    StepVerifier.create(
            reactiveRepository.findByStatus("ACTIVE", pageable)
    )
    .expectNextCount(20)
    .verifyComplete();
}
~~~

The snippet above only illustrates a Flux repository method. For a Page returning Mono<Page<T>>, use StepVerifier to assert the Mono and content. Exact repository signatures depend on your declaration.

For pages exceeding the limit, the API may throw an exception when the subscription executes the request. Tests should assert that the exception is translated into a business/API error rather than automatically retried or returning a misleading empty list.

Do not test only the validatePageRequest helper. Have at least one integration test confirming that the actual request sent to Elasticsearch carries the right from/size.

## 26. Testing That search_after Neither Duplicates Nor Drops Documents

Create a fixture with many more documents than a page size, such as 257 documents. Sort by createdAt and productId.

Test:

1. Open PIT.
2. Fetch the first page with size 50.
3. Save all IDs.
4. Read sort values of the last hit.
5. Send the next request using search_after.
6. Loop until results are exhausted.
7. Close PIT.
8. Assert total IDs equal 257.
9. Assert all IDs are unique.
10. Assert sort order is correct.

If not using PIT, the test can run on a fixture that does not change during pagination. However, do not use those results to claim behavior under concurrent writes.

## 27. Testing When Data Changes Between Pages

A useful test simulates an insert or update after the first page has been retrieved.

With from/size, data changes can shift offsets and cause duplicates or omissions. This is expected behavior to understand, not necessarily an Elasticsearch bug.

With PIT + search_after, requests within the same PIT continue viewing the opened snapshot. A test can:

1. Open PIT and fetch the first page.
2. Insert a new document into the index.
3. Continue paginating with the old PIT.
4. Assert the new document does not intrude into the current snapshot.
5. Close the PIT and open a new PIT.
6. Assert new queries can see the new document.

This demonstrates why PIT is used when stable result traversal is needed.

## 28. Performance Testing for Deep Pagination

Do not test only correctness. Measure latency and resources across multiple depths.

| from | size | Goal |
|---:|---:|---|
| 0 | 20 | First page |
| 1,000 | 20 | Moderate offset |
| 5,000 | 20 | Deep offset |
| 9,980 | 20 | Near default limit |
| 10,000 | 20 | Verify exceeding limit |

Measure:

- p50, p95, p99 latency.
- CPU of data nodes and coordinating nodes.
- Heap usage and GC.
- Search thread pool queue/rejections.
- Network bytes between shards and coordinator.
- Concurrent request throughput.
- Impact on indexing and other queries.

Compare from/size against search_after/PIT on the same dataset, mapping, shard count, and sort. Do not draw conclusions from a single run; warm-up, caches, and background load can alter measurements.

## 29. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Deep page returns 400 | from + size exceeds max_result_window | Limit pages or change strategy |
| Raised max_result_window but search is slow | Deep pagination cost still exists | Use search_after/PIT |
| Subsequent page duplicates documents | Sort lacks a stable tie-breaker | Add a unique sort field |
| Subsequent page skips documents | Data changed between offset requests | PIT + search_after if snapshot is needed |
| search_after returns wrong position | Cursor missing sort value or wrong type/order | Use complete sort values from the last hit |
| Unstable search_after | Duplicated or changing sort field | Add a tie-breaker and use PIT |
| Page count is slow | Exact total hits/count is costly | Review track_total_hits and UX |
| Export uses excessive heap | Using collectList or large page offsets | Process in batches/cursor |
| Scroll contexts retained too long | Failing to clear scroll | Clear and bound keep_alive |
| Changed setting on wrong index | Alias points to multiple indices or wrong target edited | Check backing indices and settings |
| Confusing max_result_window with max_buckets | Settings apply to different result types | Read exact error and setting |
| API allows huge page numbers | Offset not validated at application layer | Validate from + size before querying |

## 30. Workflow for Choosing a Pagination Strategy

You can choose based on requirements:

1. **Small list, page numbers and page jumping needed:** use from/size with bounded page size and page depth.
2. **Long list, only next/load more needed:** use search_after with stable sorting.
3. **Data changes while needing consistent traversal:** use PIT + search_after.
4. **Export or batch processing:** use PIT + search_after; consider scroll when appropriate for the API and workload.
5. **Only statistics needed:** use aggregations with size = 0.
6. **Exact total count needed:** evaluate track_total_hits and count cost; only require exact when the UI genuinely needs it.
7. **Clients want to jump to very deep pages:** reconsider UX or provide narrower search/filtering conditions instead of raising offset without limit.

## 31. Operational Principles

- Keep max_result_window at an intentional level.
- Validate from + size before sending requests if the API uses page numbers.
- Do not raise the setting massively just to bypass deep pagination errors.
- Configure stable sorting with a unique tie-breaker.
- Use search_after for cursor pagination.
- Use PIT when a consistent snapshot across multiple requests is needed.
- Close PIT and scroll contexts when done.
- Cap page size, concurrency, and timeouts.
- Only request exact total hits when there is a product requirement.
- Use size = 0 for aggregation-only requests.
- Distinguish max_result_window, max_inner_result_window, and search.max_buckets.
- Test setting boundaries and actual behavior against Elasticsearch.
- Benchmark latency and resources rather than measuring response size alone.

index.max_result_window protects Elasticsearch from from/size requests asking for overly large result windows. With the default of 10,000, a request is only valid when from + size does not exceed the limit. Deep pagination consumes CPU, heap, network, and merge work because shards must collect far more candidates than the hits ultimately returned. Raising the setting widens the window but does not remove the cost. For UIs needing page jumping within a small range, Pageable remains suitable; for large datasets needing sequential progression, search_after and PIT are usually better choices; and export/batch jobs need a controlled data-traversal strategy.
