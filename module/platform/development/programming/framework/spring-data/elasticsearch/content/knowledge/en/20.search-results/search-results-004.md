# Total Hits, Total Hits Relation, and Exact Counting Threshold

## 1. What Is Total Hits?

When Elasticsearch performs a search, the response can contain two different types of information:

- **Returned hits:** the documents included in the current page, typically located under `hits.hits`.
- **Total hits:** the total number of documents matching the search criteria, represented in `hits.total` when the request tracks this count.

For example, a user searches for products in the `audio` category. There are 2,450 matching documents, but the UI only requests the first 20 documents to display.

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "from": 0,
  "size": 20
}
~~~

The response may have the following structure:

~~~json
{
  "hits": {
    "total": {
      "value": 2450,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "p-001",
        "_source": {
          "name": "Wireless Headphones",
          "category": "audio"
        }
      }
    ]
  }
}
~~~

Where:

- `hits.hits` contains the documents returned for the current page.
- `hits.total.value` indicates the total number of matching documents or a lower bound of that count.
- `hits.total.relation` indicates whether `value` is an exact figure or only a lower bound.

`size: 20` only limits the number of documents returned on the page. It does not mean the total number of matching documents is only 20.

Total hits is commonly used to display the result count, calculate the number of pages, determine whether the user can continue viewing data, and provide overview information for the search screen.

## 2. Total Hits Relation: eq and gte

Elasticsearch does not always count every matching document accurately. To balance accuracy and speed, the response includes a `relation` field.

Two common values:

| Relation | Meaning | How to interpret `value` |
|---|---|---|
| `eq` | Equal, exact count | There are exactly `value` matching documents |
| `gte` | Greater than or equal, lower bound | There are at least `value` matching documents |

### relation = eq

Example:

~~~json
{
  "hits": {
    "total": {
      "value": 2450,
      "relation": "eq"
    }
  }
}
~~~

There are exactly 2,450 documents matching the query.

The UI can display:

~~~text
2,450 results
~~~

### relation = gte

Example:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    }
  }
}
~~~

The response indicates that at least 10,000 documents match. The actual total could be 10,001, 50,000, or much higher.

You must not display `10,000 results` as an exact number in this case. You can display:

~~~text
At least 10,000 results
~~~

Or if the UI does not need a specific number:

~~~text
10,000+ results
~~~

### Why Read Both value and relation?

Reading `value` alone is not enough. For example, the following two responses have the same `value` but different meanings:

~~~json
{
  "value": 5000,
  "relation": "eq"
}
~~~

~~~json
{
  "value": 5000,
  "relation": "gte"
}
~~~

The first response confirms exactly 5,000 results. The second response only confirms at least 5,000 results. If the application ignores `relation`, the UI can report an inaccurate count.

## 3. The Default Threshold of 10,000

By default, Elasticsearch tracks total hits accurately up to a threshold of 10,000. This is a trade-off between counting cost and search speed.

General rule:

- If the number of matching documents does not exceed 10,000, Elasticsearch can return the exact count with `relation: "eq"`.
- If the number of matching documents exceeds the threshold, Elasticsearch can stop exact counting at the threshold and return `value: 10000` with `relation: "gte"`.

Example:

| Actual matching documents | Default tracking threshold | Response total |
|---:|---:|---|
| 125 | 10,000 | `value: 125, relation: eq` |
| 8,500 | 10,000 | `value: 8500, relation: eq` |
| 10,000 | 10,000 | `value: 10000, relation: eq` |
| 12,000 | 10,000 | `value: 10000, relation: gte` |
| 2,000,000 | 10,000 | `value: 10000, relation: gte` |

This threshold is not a limit on the number of returned documents. Nor is it a limit on the number of pages. It only determines up to what point Elasticsearch tracks the exact total hit count.

If the application only needs to know whether there are more than 10,000 results, the default threshold is usually sufficient. If the UI strictly requires displaying the exact number, exact total-hit tracking must be configured.

## 4. How Does track_total_hits Control Counting?

The `track_total_hits` parameter in the Search API allows the application to decide how Elasticsearch tracks the number of matching documents.

There are three main configuration approaches:

| Value | Behavior | Response total |
|---|---|---|
| `true` | Track the exact count across the entire result set | `relation: "eq"` if the request completes fully |
| `false` | Do not track total hits | No `hits.total` |
| Integer `N` | Track accurately up to threshold N | `eq` if total does not exceed N; `gte` if it exceeds N |

### track_total_hits = true

~~~http
GET /products/_search
{
  "track_total_hits": true,
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Elasticsearch counts the exact total number of matching documents, even when the count exceeds 10,000.

Example response:

~~~json
{
  "hits": {
    "total": {
      "value": 125430,
      "relation": "eq"
    },
    "hits": []
  }
}
~~~

There are exactly 125,430 matching documents. The `hits` list in the example is omitted to focus on total hits.

### track_total_hits = false

~~~http
GET /products/_search
{
  "track_total_hits": false,
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Elasticsearch does not return the total number of matching documents in `hits.total`. The response can still contain the documents on the current page.

This approach is suitable when the UI only needs to display a list of results and does not need the total count.

In Spring Data Elasticsearch, the corresponding total hits relation can be represented by `TotalHitsRelation.OFF`. The application must recognize this state and not treat a numeric value as an exact total.

### track_total_hits = N

An integer can be passed to set a counting threshold:

~~~http
GET /products/_search
{
  "track_total_hits": 5000,
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Elasticsearch tracks accurately up to 5,000 hits:

- If there are 3,200 matching documents, the response returns `value: 3200` and `relation: "eq"`.
- If there are 8,000 matching documents, the response may return `value: 5000` and `relation: "gte"`.

This is a useful option when the application needs an exact number within a small range, without needing to count up to hundreds of thousands or millions of documents.

## 5. Why Can Exact Counting Be Expensive?

A search query and an exact count operation can have different processing requirements.

Elasticsearch can optimize finding and ranking matching documents without needing to determine the exact total number of matching documents. When forced to count accurately, the system must continue tracking match counts across the relevant shards.

Enabling `track_total_hits: true` can reduce the effectiveness of certain search optimizations, including Max WAND. Therefore, exact counting can increase CPU usage, processing time, and latency, especially for queries matching many documents.

Usage comparison:

| UI requirement | Appropriate configuration |
|---|---|
| Only display documents on the current page | `track_total_hits: false` |
| Display result count up to a threshold, e.g. 5,000+ | `track_total_hits: 5000` |
| Display exact total number of results | `track_total_hits: true` |
| Only need to know if more results exist to load more | Can use pagination and check for a next page, not necessarily requiring an exact count |

Do not enable exact counting by default for all queries just because the UI has a place to show a total count. Determine whether that number truly needs to be exact.

## 6. Distinguishing the Total Hits Threshold and max_result_window

These two settings are often confused because both commonly default to 10,000, yet they control two different concerns.

| Setting | What does it control? | Effect |
|---|---|---|
| `track_total_hits` | Degree of exact counting of total matching documents | `eq` or `gte` in total hits |
| `index.max_result_window` | Depth of pagination using `from` and `size` | Limits document position that can be requested in a page |

Example:

~~~http
GET /products/_search
{
  "track_total_hits": true,
  "from": 0,
  "size": 20,
  "query": {
    "match_all": {}
  }
}
~~~

The query can accurately count hundreds of thousands of documents while returning only the first 20 documents.

Conversely, increasing `index.max_result_window` does not automatically make total hits accurately counted. To change counting behavior, `track_total_hits` must be configured.

If deep traversal across many pages is needed, consider `search_after` and Point in Time instead of arbitrarily increasing the result window. This is a pagination concern, independent of total hits accuracy.

## 7. Configuring track_total_hits in Spring Data Elasticsearch

Spring Data Elasticsearch represents search options through the `Query` interface. Implementations such as `CriteriaQuery`, `StringQuery`, and `NativeQuery` can all be passed to `ElasticsearchOperations`.

In the current Spring Data Elasticsearch API:

- `setTrackTotalHits(Boolean)` sets whether total hit tracking is enabled or disabled.
- `setTrackTotalHitsUpTo(Integer)` sets the maximum tracking threshold.
- `setTrackTotalHitsUpTo` only takes effect when `getTrackTotalHits()` is `null`.

Therefore, when using an integer threshold, set `setTrackTotalHitsUpTo(N)` and do not override the mode with `setTrackTotalHits(true/false)`.

### Exact Counting

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

CriteriaQuery query = new CriteriaQuery(
    new Criteria("category").is("audio")
);

query.setTrackTotalHits(true);

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

`setTrackTotalHits(true)` instructs Elasticsearch to track the exact total count.

### No Total Needed

~~~java
CriteriaQuery query = new CriteriaQuery(
    new Criteria("category").is("audio")
);

query.setTrackTotalHits(false);

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

When tracking is disabled, the application still receives the hits on the page, but should not rely on total hits to display a total count.

### Counting Accurately Only Up to a Threshold

~~~java
CriteriaQuery query = new CriteriaQuery(
    new Criteria("category").is("audio")
);

query.setTrackTotalHitsUpTo(5_000);

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

In this example, the query leaves the `trackTotalHits` mode unspecified and sets a threshold of 5,000. This corresponds to the integer value in the Search API.

The methods above belong to Spring Data Elasticsearch 4.0/4.1 and later. If the project uses an older version, check the API of the actual dependency before applying.

## 8. Reading Total Hits Relation in SearchHits

Spring Data Elasticsearch provides not only the count via `SearchHits.getTotalHits()`, but also the relation via `SearchHits.getTotalHitsRelation()`.

The `TotalHitsRelation` enum has the following values:

| Enum | Meaning |
|---|---|
| `EQUAL_TO` | Exact total hits, corresponding to `eq` |
| `GREATER_THAN_OR_EQUAL_TO` | Total hits is a lower bound, corresponding to `gte` |
| `OFF` | Total hits are not tracked |

Example of reading the result:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.TotalHitsRelation;

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);

long total = hits.getTotalHits();
TotalHitsRelation relation = hits.getTotalHitsRelation();

switch (relation) {
    case EQUAL_TO ->
        System.out.println("Exactly " + total + " results");

    case GREATER_THAN_OR_EQUAL_TO ->
        System.out.println("At least " + total + " results");

    case OFF ->
        System.out.println("Total result count is not tracked");
}
~~~

Do not just call `getTotalHits()` and display the result as an exact number. Check `getTotalHitsRelation()` first.

If the system spans multiple Spring Data Elasticsearch versions, verify the corresponding enum and API. `TotalHitsRelation` was introduced in Spring Data Elasticsearch 4.0; the `OFF` value was added in 4.1.

## 9. Building API Responses for the UI

A search API can return total count information along with the relation so the frontend can display it accurately:

~~~java
public record SearchResult<T>(
    List<T> items,
    long totalHits,
    String totalHitsRelation
) {
}
~~~

Example conversion from `SearchHits`:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;

public SearchResult<Product> toSearchResult(SearchHits<Product> hits) {

    List<Product> items = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

    return new SearchResult<>(
        items,
        hits.getTotalHits(),
        hits.getTotalHitsRelation().name()
    );
}
~~~

The JSON response might look like:

~~~json
{
  "items": [
    {
      "id": "p-001",
      "name": "Wireless Headphones"
    }
  ],
  "totalHits": 10000,
  "totalHitsRelation": "GREATER_THAN_OR_EQUAL_TO"
}
~~~

The frontend can rely on the relation to display:

~~~text
EQUAL_TO                  → 10,000 results
GREATER_THAN_OR_EQUAL_TO  → At least 10,000 results
OFF                       → Do not display total count
~~~

Another option is converting the relation into a display state on the backend, such as `exact`, `at_least`, or `not_tracked`. If doing so, keep semantics clear in the API contract so the frontend does not misinterpret it.

For public APIs, avoid returning a standalone `totalHits` field without relation information if the system may return a capped count.

## 10. When Should You Use the Count API?

If business logic only needs to know how many documents match without retrieving documents or search metadata, consider the Elasticsearch Count API.

Example:

~~~http
GET /products/_count
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Response:

~~~json
{
  "count": 2450,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
~~~

The Count API returns the number of documents matching the query. This is a separate request, useful when only a count is needed without retrieving a list of hits.

Distinguish among:

- The Search API returns documents along with search metadata; total hits can be exact, capped, or disabled via `track_total_hits`.
- The Count API focuses solely on counting matching documents.
- The `value_count` aggregation counts the number of values in a field, which is not synonymous with the number of matching documents.
- The `cardinality` aggregation approximates the number of unique values and may not be strictly exact.

Do not use an aggregation or the number of items on the current page as a substitute for total hits when the goal is to count documents matching the query.

## 11. Total Hits in Pagination Scenarios

Suppose there are 18,000 matching documents and the page size is 20.

If using the default threshold of 10,000, the response may indicate:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    },
    "hits": [
      "... 20 documents on current page ..."
    ]
  }
}
~~~

This means:

- The current page contains up to 20 documents.
- The total number of matching documents is at least 10,000.
- The exact total number of pages cannot be derived from the number 10,000.
- You cannot conclude there are only 500 pages, because the actual total could be much larger.

If the UI uses `Page<T>` to display page numbers, consider the semantics of total hits. When counting is capped, the total pages derived from a lower bound is only an estimate or lower bound, not an exact total page count.

If the UI only needs a `Load more` button, you can fetch the next page using `Pageable` or `search_after`. Counting the entire index accurately is not strictly necessary.

For deep pagination, `from` and `size` have their own limits. `search_after` allows continuing from the sort values of the last hit of the previous page, but it does not automatically make total hits exact. Pagination and total counting are two separate decisions.

## 12. Considerations About Count Accuracy

The total hits relation describes the accuracy of the counter in the response. When processing results, keep several additional points in mind:

**Do not confuse total hits with the number of hits on a page.** A page with 20 elements does not mean the query matched only 20 documents.

**Do not treat gte as eq.** `gte` means at least equal to the value, not strictly equal to the value.

**Do not treat OFF as 0 results.** When tracking is disabled, the total count is not provided. That does not mean there are no matching documents.

**Do not use capped total hits to calculate an exact page count.** If the relation is `gte`, the page count derived from value is only a lower bound.

**Check request status.** When the response reports a timeout or shard failure, search results may be incomplete. If the UI requires reliable counts, inspect execution status and shard information alongside total hits.

**Do not increase the threshold arbitrarily.** A larger threshold can make counts more accurate, but it also increases processing cost.

**Do not use count for every operation.** If the UI only needs to know whether a next page exists, consider a pagination mechanism instead of requesting an exact count.

## 13. Workflow for Choosing a Counting Threshold

Configuration can be determined based on product requirements:

1. Determine whether the UI genuinely needs to display the total result count.
2. If not needed, set `track_total_hits: false`.
3. If only displaying up to a threshold, choose `track_total_hits: N`.
4. If an exact total is required for business logic, set `track_total_hits: true`.
5. In Spring Data, use `setTrackTotalHits` or `setTrackTotalHitsUpTo` according to the chosen mode.
6. Read both `getTotalHits()` and `getTotalHitsRelation()` from `SearchHits`.
7. Display `eq` as an exact count, `gte` as a lower bound, and `OFF` as no count available.
8. Evaluate latency and cluster resources on queries with many results.
9. Check for timeouts and shard failures before using total hits for critical reports.

## Conclusion

Total hits indicates the total number of documents matching the query, while `hits.hits` only contains the documents returned on the current page. Elasticsearch uses `relation` to communicate the accuracy of `value`: `eq` is an exact count, `gte` is a lower bound, and when tracking is disabled there is no total count.

By default, Elasticsearch tracks accurately up to 10,000 hits. You can set `track_total_hits: true` to count everything accurately, `false` to skip total counting, or an integer to set a custom threshold. Exact counting can increase search cost, so choose according to UI and business requirements.

In Spring Data Elasticsearch, configure via `Query.setTrackTotalHits` or `Query.setTrackTotalHitsUpTo`, then read `SearchHits.getTotalHits()` along with `SearchHits.getTotalHitsRelation()`. Always preserve relation information when passing results to an API so the frontend can distinguish exact counts, lower bounds, and untracked states.

## References

- [Elasticsearch — The Search API: Track total hits](https://www.elastic.co/docs/solutions/search/the-search-api#track-total-hits)
- [Elasticsearch — Search API reference](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch — Count API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-count)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — TotalHitsRelation API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/TotalHitsRelation.html)
