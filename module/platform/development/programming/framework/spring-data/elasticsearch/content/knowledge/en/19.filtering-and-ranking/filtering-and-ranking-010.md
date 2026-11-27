# Explain API, Profile API, and Analyzing Unexpected Results

When an Elasticsearch query returns unexpected documents, you must distinguish two questions: **why was this document included or excluded**, and **which component made the query slow**. Elasticsearch provides dedicated tools for each question. The Explain API analyzes whether a document matches a query and how its relevance score is calculated. The Profile API measures execution time across parts of the query on each shard. Additionally, the Validate Query API checks whether a query is valid and what structure it rewrites into before running.

In Spring Data Elasticsearch, repositories, `ElasticsearchOperations`, `SearchHits`, and `NativeQuery` help construct queries and read search results. When you need deep diagnostics that the abstraction does not expose directly, you can invoke the Elasticsearch Java API Client or REST API. This article covers choosing the right tool, reading responses, and following a systematic process to pinpoint root causes when results or performance fall short of expectations.

## 1. Distinguishing Explain API, Profile API, and Validate Query API

These three APIs are often used together, yet answer distinct questions:

| Tool | Primary Question | Scope |
|---|---|---|
| Explain API (`_explain`) | Does a specific document match the query? Why did its relevance score get that value? | A single document by ID |
| Search API with `explain: true` | Why did each hit in the results receive its relevance score? | Hits of a search request |
| Profile API (`profile: true`) | Which execution steps did the query take and what is the relative time per part? | Shards and execution components of a search request |
| Validate Query API (`_validate/query`) | Is the query valid and how does Elasticsearch rewrite it? | Query structure; does not search documents |

You can apply them in sequence:

```text
Unexpected results
          |
          v
Check index, mapping, data, and query
          |
          v
Validate Query: is the query valid and rewritten properly?
          |
          v
Explain: how was a specific document matched or scored?
          |
          v
Profile: which execution part is taking time?
```

Explain focuses on matching and scoring logic. Profile focuses on execution time. A query can be logically right yet slow; conversely, a fast query can still return documents that violate business expectations.

## 2. Preparing an Example Query

Suppose the `products` index has these fields:

```json
PUT products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "description": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
      },
      "priceInCents": {
        "type": "long"
      },
      "featured": {
        "type": "boolean"
      }
    }
  }
}
```

A query searching for products related to `wireless keyboard`, requiring `active` and category `keyboards`, with matching names influencing relevance score:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ],
      "should": [
        { "match": { "description": "wireless" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

In this example, `must` requires `name` to match both analyzed terms. The two filters are mandatory conditions that contribute no score. The two `should` clauses act purely as boosts because the `bool` query has `must`/`filter` and `minimum_should_match` set to 0.

This query is used throughout the examples. When diagnosing a real system, substitute your application's actual index, fields, analyzers, and query.

## 3. Explain API for a Single Document

The Explain API checks whether a specific document by ID in an index matches the submitted query. Endpoint:

```http
GET products/_explain/p-100
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ],
      "should": [
        { "match": { "description": "wireless" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Important response fields:

- `matched`: `true` if the document matches the query, `false` otherwise.
- `explanation.value`: calculated score value if matched.
- `explanation.description`: description of the calculation or condition evaluated.
- `explanation.details`: sub-components explaining scores/logic at lower levels.

Abbreviated illustrative response:

```json
{
  "_index": "products",
  "_id": "p-100",
  "matched": true,
  "explanation": {
    "value": 2.41,
    "description": "sum of:",
    "details": [
      {
        "value": 1.72,
        "description": "weight(name:wireless in 0) ..."
      },
      {
        "value": 0.69,
        "description": "weight(name:keyboard in 0) ..."
      }
    ]
  }
}
```

The numbers and descriptions above illustrate structure only; real scores depend on data, index statistics, analyzers, query, and Elasticsearch version.

### 3.1. Explain When a Document Does Not Match

If `matched` is `false`, the response still contains an `explanation` helping pinpoint which condition eliminated the document. For example:

- The document does not contain the terms `wireless` or `keyboard` in `name` after analysis.
- One of the filters fails, e.g., `active` is `false`.
- The query has `minimum_should_match` requiring more clauses than the document satisfies.
- The document does not live in the index/routing scope being checked.

The Explain API is useful because you can inspect a document even when it does not appear in normal search results. You need to know the document ID and its index.

### 3.2. Explain Only Explains the Query Sent

Explain does not automatically figure out the right query for your business logic. If the request sends the wrong field, analyzer, filter, or index, the API simply explains how Elasticsearch evaluated that query. Always compare the query in the Explain request against the actual query sent by the application.

Explain also does not replace checking `_source` and mappings. A document may hold a value in `_source` while the field is unindexed or mapped under a different name or type.

## 4. Search API with `explain: true`

If you need explanations for every hit in search results, enable `explain` in the Search API:

```http
GET products/_search
{
  "explain": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ]
    }
  }
}
```

Each hit can contain an `_explanation` field with the score breakdown tree. This is convenient when comparing why product A ranked above product B.

Unlike the `_explain/{id}` endpoint, the Search API only returns explanations for hits returned by the search query. If a document did not match and is therefore absent from `hits`, call the Explain API for that specific ID.

### 4.1. When to Enable `explain`?

Enable it only when investigating specific results or in development/testing environments. Explanations can be very verbose, inflating response sizes and processing cost. Avoid enabling it on all user search requests when the application does not need this diagnostic output.

### 4.2. Score Is Not a Probability

`_score` is the relevance score computed by the query and similarity. It is not a percentage probability that the document is correct, nor is it bounded between 0 and 1. Do not display scores as "92% accuracy" without a dedicated calibration model.

Scores are meaningful primarily in relative comparisons within the same query and search context. Never directly compare scores from two different queries to decide which query is better.

## 5. Profile API for Analyzing Execution Time

The Profile API is enabled via `profile: true` in the Search API:

```http
GET products/_search
{
  "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ]
    }
  }
}
```

The response includes a `profile` section broken down by shard. Inside each shard, Elasticsearch can return search contexts, query trees, timing breakdowns, and collector details. If the request includes aggregations or other profileable components, corresponding sections are included.

Profile is useful for identifying:

- Which query clause consumes the most time.
- Which Lucene query structure the query was rewritten into.
- What execution tree a multi-branch `bool` or `nested` query produces.
- Time spent in phases like scorer creation, advancing to the next document, `advance`, and scoring.
- Which collector or aggregation consumes heavy processing effort.

## 6. Reading the Profile Response Structure

A profile response typically has this general layout:

```json
{
  "profile": {
    "shards": [
      {
        "id": "...",
        "searches": [
          {
            "query": [
              {
                "type": "BooleanQuery",
                "description": "...",
                "time_in_nanos": 123456,
                "breakdown": {
                  "create_weight": 1000,
                  "build_scorer": 2000,
                  "next_doc": 3000,
                  "score": 4000
                },
                "children": []
              }
            ],
            "collector": []
          }
        ]
      }
    ]
  }
}
```

This is a simplified illustrative structure; real responses contain many more fields and query names depending on Lucene/Elasticsearch version.

Key components to inspect:

| Field | Meaning |
|---|---|
| `shards` | Profile results per shard participating in the search |
| `searches` | Search contexts/phases profiled on the shard |
| `query` | Execution query tree and child queries |
| `type` | Actual Lucene query class |
| `description` | Rewritten query or Lucene query string representation |
| `time_in_nanos` | Total time of the node in the profile tree |
| `breakdown` | Detailed timings across execution operations |
| `children` | Child queries in the execution tree |
| `collector` | Collector details used to gather hits |
| `aggregations` | Aggregation profile details if the request included aggregations |

`time_in_nanos` is measured in nanoseconds. Divide by 1,000,000 to convert to milliseconds for readability.

### 6.1. Metrics Inside `breakdown`

Common keys:

- `create_weight`: time spent building the `Weight` for the query.
- `build_scorer`: time spent creating the scorer to evaluate documents.
- `next_doc`: time spent finding the next matching document.
- `advance`: time spent skipping forward to a specific or later document ID.
- `score`: time spent computing scores for documents.
- `match`: time spent checking match conditions in certain queries.
- `shallow_advance`: an optimized advance operation at the scorer level.
- `compute_max_score`: time spent computing max scores in certain optimized queries.

Not every query reports every key. Some operations are inapplicable or zero depending on the query implementation.

### 6.2. Reading the Query Tree

Profile shows the query after Elasticsearch/Lucene rewrites it. A `bool` Query DSL can turn into a `BooleanQuery` with child nodes like term, phrase, range, or point queries. Consequently, node names in Profile do not necessarily match the original JSON DSL names.

When a query node has `children`, inspect timings and breakdowns of both the parent node and child nodes. Do not sum `time_in_nanos` across parent and children as independent costs; a parent node's time typically includes its children's time.

### 6.3. Comparing Timings Across Shards

Each shard may have different document counts, segments, cache states, and load. One slow shard can raise overall latency even when all other shards finish quickly.

Profile helps spot shard disparities, though you should cross-check:

- Document count and segment sizes per shard.
- Data distribution and routing.
- CPU load, disk I/O, and heap pressure on nodes.
- Warm/cold cache states and ongoing segment merges.
- Search thread pools and queues.

Do not draw conclusions from a single profile run because cache state and cluster load vary across executions.

## 7. Limitations and Cost of the Profile API

The Profile API introduces significant overhead. Because it instruments low-level query operations, profiled queries can run slower than normal queries. Never use Profile to benchmark throughput or directly measure production performance.

Profile is also not an end-to-end stopwatch for the entire request. It does not capture client request serialization, network transit, queuing before query execution starts, coordinating-node merging, or overhead outside the profiled execution phases. Do not sum Profile timings expecting them to equal `took`.

Key points to remember:

- `took` is the search request time reported by Elasticsearch at the request level; Profile is a detailed per-shard/query breakdown.
- Shards execute in parallel, so summing times across shards is not end-to-end latency.
- Parent and child node timings in the query tree can overlap/include one another.
- Profile responses can become huge, especially with complex query trees or aggregations.
- Enable it only for specific queries, sample data, and brief investigation windows.

To measure real user-facing latency, combine client/server APM and metrics, slow search logs, cluster monitoring, and controlled benchmarks. Use Profile to zoom inside a query once an interesting slow request has been identified.

## 8. Validate Query API

Before analyzing documents or profiling, you can verify query validity using the Validate Query API:

```http
GET products/_validate/query?explain=true
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless keyboard" } }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ]
    }
  }
}
```

The response includes `valid`, indicating whether the query is syntactically and semantically valid. With `explain=true`, Elasticsearch also returns how the query rewrites into the representation the engine understands.

The Validate Query API does not run a normal search and returns no documents. It catches malformed query syntax, invalid fields/queries, and shows rewrites; it does not prove the query returns the right business data.

You can pass `all_shards=true` if you need validation across all shards rather than one default shard. This helps when mappings or shard states behave abnormally, though keep cost in mind on large indexes.

## 9. Analyzing Queries Returning Zero Results

When search returns 0 hits, check the fundamentals before trying to optimize the query.

### 9.1. Confirm the Right Index, Alias, or Data Stream

Verify which target index the request hits:

```http
GET _resolve/index/products
```

Inspect aliases:

```http
GET _alias/products
```

An alias can point to multiple indexes or carry its own filter. Running a query against an alias can return different results than querying an index directly.

### 9.2. Check Whether the Document Exists

Fetch the document by ID:

```http
GET products/_doc/p-100
```

If the document does not exist in the queried index, the Explain API cannot explain it in that index either. Check the ID, target index, routing, and ingestion pipeline.

### 9.3. Inspect the Mapping

```http
GET products/_mapping
```

Verify:

- Does the queried field exist in the mapping?
- Is the field `text`, `keyword`, `numeric`, `date`, or another type?
- Is there a multi-field such as `name.keyword`?
- Are `analyzer` and `search_analyzer` configured properly?
- Is the field inside a `nested` object requiring a `nested` query?
- Is the field configured with `index: false` or `enabled: false`?

Using `term` on a `text` field rarely produces expected semantics; `match` on a `keyword` field behaves differently from a full-text analyzer as well. A syntactically valid query can still return zero matches if the query type mismatches the mapping.

### 9.4. Check the Analyzer with the Analyze API

Use `_analyze` to inspect which tokens the query text generates:

```http
POST products/_analyze
{
  "field": "name",
  "text": "Wireless Keyboard"
}
```

Compare tokens from the search string with tokens generated at index time. Check lowercasing, stemming, stop words, synonyms, asciifolding, and tokenizers. When index-time and search-time analyzers differ, confirm whether that difference is intentional or a misconfiguration.

### 9.5. Check Bool Logic

Review each clause:

- Is a `must` clause overly restrictive so no document matches?
- Are filters using the right values and field types?
- Is `must_not` accidentally excluding all results?
- Are `should` clauses treated as optional because `bool` has `must`/`filter`?
- Is `minimum_should_match` higher than the number of satisfiable clauses?
- Are nested `bool` queries setting thresholds at the right level?

To isolate the culprit, start with a minimal query and add filters or clauses one by one. Avoid removing all conditions simultaneously, which obscures which condition caused empty results.

### 9.6. Check `post_filter`, `min_score`, and Result Limits

Search requests can include parts outside `query`:

- `post_filter`: filters hits after aggregations run; can leave `hits` empty even when aggregations still show buckets.
- `min_score`: drops hits scoring below the cutoff.
- `terminate_after`: limits how many documents are collected per shard.
- `size`: limits returned hit count only, not match criteria.
- `from`: skips initial hits for pagination; large offsets can hit result-window limits.
- `routing`: restricts queried shards; wrong routing can exclude the document from evaluation.
- Alias filters or security filters: can add hidden filter constraints beyond what application code sees.

If the bare query returns results while the full request returns none, inspect these components.

## 10. Analyzing Results Present in the Wrong Order

If documents appear but in an unexpected order, separate matching rules from scoring and sorting.

### 10.1. Check Sort

If the search request specifies a field `sort`, results can be ordered by that field instead of `_score`. Example:

```json
{
  "sort": [
    { "priceInCents": { "order": "asc" } }
  ]
}
```

Cheaper products appear first even with lower scores. If you want relevance sorting, remove the field sort or order `_score` first with appropriate priority.

When sorting by a field while still needing scores, enable `track_scores` so Elasticsearch computes/returns scores in field-sort scenarios. Do not assume returned scores always govern hit order.

### 10.2. Check `must`, `filter`, and `should`

Conditions in `filter` add no score. If all search content accidentally lands in `filter`, documents may all get score 0 or lack intended relevance ordering.

`should` clauses may only boost scores when `bool` has `must`/`filter` and a threshold of 0. If they must act as matching requirements, set `minimum_should_match` appropriately.

### 10.3. Check Boosts and Query Structure

Relevance scores can be altered by:

- `boost` on queries or fields.
- `function_score` or `script_score`.
- `dis_max` and `tie_breaker`.
- `multi_match` and field boosts such as `name^3`.
- `rescore` in a second stage.
- Similarity configured on the index or field.

Run the Explain API on a few representative documents to see which components add or reduce points. Compare two documents under the same query, index, and context rather than comparing scores across different queries.

### 10.4. BM25 and Term Statistics

Elasticsearch typically uses BM25 as default similarity for `text`. Scores are influenced by term frequency in the document, term rarity in the dataset, and field length. Therefore, two documents containing the same keywords can still earn different scores.

When ranking feels counterintuitive, Explain shows factors such as term frequency, inverse document frequency, and field length normalization. Avoid interpreting scores as simple word-match counts.

## 11. Analyzing Slow Queries with the Profile API

When a query returns correct results slowly, start by recording:

- `took` of the search request.
- Number of shards queried and failed shards.
- Hit count and pagination setup.
- Full Query DSL, sort, aggregations, and filters.
- Timestamp, cluster load, and coordinating node.

Then enable `profile: true` for the same query against representative data. Inspect which shards are slow and which query nodes show large breakdowns.

Common causes:

- `wildcard`, `regexp`, or `prefix` on high-cardinality fields with unselective patterns.
- `script` queries or script scoring running across many documents.
- `nested` queries with many child documents.
- `terms` queries with huge value lists.
- Complex queries with many `should`/`must` branches.
- Aggregations with many buckets or high cardinality.
- Sorting on fields without suitable doc values or requiring large candidate evaluation.
- Querying too many small shards or skewed data distribution.

Profile reveals where execution time is spent, though it does not automatically prescribe a better query. Combine it with your understanding of mappings, data, and business requirements to choose optimizations.

## 12. Combining Explain and Profile

Both APIs can be used on the same query while serving distinct goals:

1. Run a normal search to confirm outputs and record `took`.
2. Run Explain on a high-ranking document and a low-ranking document to understand scoring.
3. Enable Profile on that query to locate expensive query nodes or shards.
4. Change one factor at a time—such as analyzer, filter, query structure, or sort.
5. Re-run functional tests and measure performance under equivalent conditions.

Never use profile timings or explain scores to judge query speed vs. relevance interchangeably. Profile measures execution time; Explain analyzes matching and relevance.

## 13. Using Spring Data Elasticsearch to Read Search Results

Repository methods can return `SearchHits<T>` or `SearchHit<T>` to retain result metadata:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0"
            }
          }
        }
        """)
    SearchHits<Product> searchWithMetadata(String text);
}
```

`SearchHits<Product>` holds overall search response metadata; each `SearchHit<Product>` provides the entity alongside metadata such as ID, index, score, sort values, and highlight fields when requested. Example reading the score:

```java
SearchHits<Product> hits = repository.searchWithMetadata("wireless keyboard");

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    float score = hit.getScore();

    System.out.println(product.getName() + " -> " + score);
}
```

`SearchHits` gives access to hit scores and metadata. It does not mean the full Explain tree or Profile output is mapped onto entities. For detailed diagnostics, enable explain/profile via the corresponding request API and read the Elasticsearch Java API Client or REST API response.

## 14. Calling Explain and Profile with the Elasticsearch Java API Client

In modern release trains, Spring Data Elasticsearch integrates with the Elasticsearch Java API Client. If your application already configures an `ElasticsearchClient` bean, you can send Search API requests with `explain` and `profile`:

```java
import java.io.IOException;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public class ProductDiagnostics {

    private final ElasticsearchClient client;

    public ProductDiagnostics(ElasticsearchClient client) {
        this.client = client;
    }

    public SearchResponse<Product> explainAndProfile() throws IOException {
        Query query = Query.of(q -> q
                .match(m -> m
                        .field("name")
                        .query("wireless keyboard")));

        SearchRequest request = SearchRequest.of(s -> s
                .index("products")
                .query(query)
                .size(20)
                .explain(true)
                .profile(true));

        return client.search(request, Product.class);
    }
}
```

This request asks the Search API to return explanations for hits and execution profile details. Those sections are accessed through the accessors generated by the Elasticsearch Java API Client, such as hit metadata and the profile section. Exact class names and response types depend on the client version.

When you only need Explain for a single document, call the `_explain/{id}` endpoint via REST or the corresponding client API. When you need Profile, the Search API request must set `profile(true)`.

### 14.1. Dependency Compatibility Note

Spring Boot manages compatible versions of Spring Data Elasticsearch and the Elasticsearch Java API Client. Do not independently upgrade the client to a different major version without checking the release train. Builders, response types, and accessors can change across versions.

If the project does not directly expose `ElasticsearchClient`, use the client bean configured per Spring Boot/Spring Data documentation or call the REST API through administrative tooling. Avoid spinning up ad-hoc clients with separate credentials/connections that bypass the application's TLS, authentication, timeout, and lifecycle settings.

## 15. Common Causes of Unexpected Results

### Querying the Wrong Field or Field Type

Using `term` on `text`, using Java property names instead of mapped field names, or forgetting a `.keyword` subfield. Check `_mapping` and use a query suited to the field type.

### Analyzer Behaving Unexpectedly

Keywords transformed by lowercasing, stemming, stop words, or synonyms. Use `_analyze` on the target field to inspect actual tokens.

### `should` Becoming Optional

`bool` queries containing `must` or `filter` default `should` threshold to 0. Set `minimum_should_match` if those clauses must match.

### Filters Excluding Documents

An exact match or range filter can be overly tight, mismatched in type, or affected by timezone differences. Test each filter independently and verify values in `_source`.

### Querying a Nested Field Without a `nested` Query

If the mapping uses `nested`, querying directly like a normal object can fail to match properly. Wrap it in a `nested` query with the appropriate path.

### Sort Overriding Score Order

Searches specifying a field `sort` order by that field. Check `sort`, `track_scores`, and `_score` ordering.

### Aliases or Routing Altering Scope

Aliases may embed filters; routing may restrict shards. Verify target indexes, aliases, and active routing.

### Truncated Results or Approximate Total Hits

`size`, `from`, `search_after`, `terminate_after`, and `track_total_hits` affect returned hit counts and total-hit accuracy. Inspect `hits.total.relation` to see whether the total is exact (`eq`) or a lower bound (`gte`).

### Refresh Not Yet Completed

Elasticsearch is near-real-time; newly indexed documents may not appear in searches until a refresh occurs. Check write responses and refresh policy before concluding a document is lost.

## 16. Systematic Investigation Workflow

When receiving reports that "search is wrong" or "the query is too slow," follow this workflow:

1. Capture the complete request: index/alias, query, sort, filters, routing, pagination, and search options.
2. Check `_mapping`, `_settings`, aliases, and the document's `_source` to verify baseline data.
3. Run `_analyze` when full-text fields are involved; confirm tokens and analyzers.
4. Run `_validate/query?explain=true` to check structure and query rewrites.
5. If documents are missing or extra, check `bool` logic, `minimum_should_match`, `post_filter`, `min_score`, routing, and security/alias filters.
6. Run `_explain/{id}` for a specific document to see whether it matched and how its score was computed.
7. If hits appear in the wrong order, inspect `sort`, boosts, similarity, `function_score`, `rescore`, and scoring clauses.
8. If the query is accurate yet slow, enable `profile: true` on a representative request to find costly query nodes or shards.
9. Change one factor at a time, re-run functional tests, and measure performance under equivalent conditions.
10. Turn off `explain`/`profile` after investigation; keep only appropriate operational metrics and logging active.

## 17. Summary

The Explain API answers why a specific document matched or failed to match and how its relevance score was calculated. You can call `_explain/{id}` for a single document or set `explain: true` in the Search API to receive explanations for each hit. The Profile API is enabled with `profile: true` and reveals how a query executed across shards, including the query tree and timing breakdowns. The Validate Query API checks query structure and shows the rewritten query without executing a search.

When results do not match expectations, inspect indexes, mappings, data, analyzers, `bool` logic, filters, routing, aliases, sorting, and search limits before optimizing. Use Explain to understand matching/scoring, Profile to locate execution bottlenecks, and Validate to inspect queries. In Spring Data Elasticsearch, `SearchHits` exposes hit scores and metadata; for deep diagnostics, use the Elasticsearch Java API Client or REST API at compatible versions. These tools complement one another and separate search logic bugs from performance issues.

## References

- [Elasticsearch – Explain API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-explain)
- [Elasticsearch – Profile search requests](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-profile)
- [Elasticsearch – Validate query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-validate-query)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Analyze API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-analyze)
- [Spring Data Elasticsearch – Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – SearchHit API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html)
