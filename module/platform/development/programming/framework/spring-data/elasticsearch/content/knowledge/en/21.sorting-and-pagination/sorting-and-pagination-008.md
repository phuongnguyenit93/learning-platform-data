# Stable Ordering and Tie-Breaker Fields When Multiple Documents Share the Same Value

When Elasticsearch sorts results by a field such as creation date, price, relevance score, or name, multiple documents can share the exact same value. If sorting only by that field, the order among tied documents is not fully deterministic. This easily causes confusion when users paginate: a document can appear on two pages or be skipped if the index changes between requests.

For stable ordering, construct a total order: use the business field as the primary criterion, then add a tie-breaker field with a unique, stable value for every document. The tie-breaker field must be indexed with a type that supports sorting and must always have a value.

For deep pagination or when needing a consistent result set while writes continue, combine Point in Time (PIT) with search_after. PIT preserves a consistent view of the index during pagination; search_after continues from the sort values of the last hit of the previous page.

## 1. Why Do Equal Sort Values Cause Issues?

Suppose five articles share the same publication date 2026-11-01. The query only sorts by publishedAt descending:

~~~json
{
  "sort": [
    {
      "publishedAt": {
        "order": "desc"
      }
    }
  ]
}
~~~

Elasticsearch knows which articles have a newer date, but has no business rule to decide the order among articles on the same date. The order of tied hits can depend on data distribution, segments, shards, and index state. Do not rely on arbitrary order or an accidental order observed in a single run.

The issue becomes more obvious when using offset pagination:

~~~text
Page 1: from = 0, size = 2
Page 2: from = 2, size = 2
~~~

If multiple documents share the same sort value, the boundary between page 1 and page 2 has no explicit tie-breaking rule. When the index refreshes or new data is added, results can reorder and cause users to see duplicates or missing documents.

To solve this, add a unique field as the final sort criterion:

~~~json
{
  "sort": [
    {
      "publishedAt": {
        "order": "desc"
      }
    },
    {
      "sort_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

If publishedAt is equal, sort_id decides the order. Because sort_id is unique, no two distinct documents remain tied across the entire sort list.

## 2. Total Order and Tie-Breakers

A multi-criteria sort is applied in priority order:

1. Compare the first sort criterion.
2. If equal, compare the second criterion.
3. If still equal, proceed to the next criterion.
4. Use a unique tie-breaker at the end to distinguish all documents.

For example:

~~~text
publishedAt DESC, sort_id ASC
~~~

- Newer articles come first.
- If timestamps match, smaller sort_id comes first.
- Because sort_id is unique, every document has a distinct position in the order.

Such an ordering is called a total order over the considered document set. It eliminates ambiguity among documents sharing identical values on business criteria.

### 2.1. Properties of a Good Tie-Breaker

A tie-breaker field should satisfy these conditions:

- **Unique:** no two distinct documents in the search set share the same value.
- **Stable:** the value does not change between pagination requests.
- **Present:** every document has a value; avoid nulls or missing values.
- **Sortable:** the mapping supports efficient sorting, typically keyword or a numeric type with doc values.
- **Controlled:** the application or write pipeline ensures the value is generated properly.

A business ID can be a good choice if it is unique across the entire set of queried indices and copied into a sortable field. If it is only unique within each index, while queries run over an alias spanning multiple indices, build a globally unique key across that entire set.

### 2.2. Tie-Breaker Must Come Last

Business fields that determine primary order must precede the tie-breaker. For example:

~~~json
{
  "sort": [
    {"_score": "desc"},
    {"publishedAt": "desc"},
    {"sort_id": "asc"}
  ]
}
~~~

This order prioritizes relevance first, then newer articles, and finally uses sort_id to break ties when the first two criteria match.

If sort_id is placed before _score, the ID dictates order ahead of relevance and can cause results to diverge from search intent.

## 3. Why Should You Not Sort Directly by _id?

Elasticsearch has the _id metadata field to identify documents. However, _id is not designed as a general sort field and has restrictions when used for sorting or aggregations.

Do not assume that declaring:

~~~json
{
  "sort": [
    {"_id": "asc"}
  ]
}
~~~

is a suitable tie-breaker for all queries. Copy the ID into a separate data field with doc values, such as sort_id, and sort on that field instead.

### 3.1. Spring Data Elasticsearch Entity Example

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

import java.time.Instant;

@Document(indexName = "articles")
public class Article {

    @Id
    private String id;

    @Field(name = "sort_id", type = FieldType.Keyword)
    private String sortId;

    @Field(name = "published_at", type = FieldType.Date)
    private Instant publishedAt;

    @Field(type = FieldType.Text)
    private String title;

    // constructors, getters, and setters
}
~~~

When creating or updating an Article, assign sortId a unique, stable value. For instance, if id is a UUID, you can use the same UUID as sortId:

~~~java
public Article prepareForIndexing(Article article) {
    if (article.getSortId() == null) {
        article.setSortId(article.getId());
    }
    return article;
}
~~~

This snippet illustrates the synchronization rule. If IDs are generated after entity creation or by Elasticsearch, generate the ID in the application before saving so both id and sortId can be assigned. Never let the two fields drift out of sync or mutate sortId after documents have been paginated.

For the keyword type, doc values are enabled by default in Elasticsearch mappings. You can declare it explicitly in the mapping if needed to make the contract clear:

~~~json
{
  "properties": {
    "sort_id": {
      "type": "keyword",
      "doc_values": true
    }
  }
}
~~~

Do not use a standard text field as a tie-breaker. Text fields do not support doc values by default and are unsuitable for sorting without modifying fielddata. Keyword or numeric types are usually better choices.

### 3.2. Unique Keys When Searching Across Multiple Indices

Suppose alias articles-read points to articles-2025 and articles-2026. If each index independently generates IDs like 1001, 1002, both indices can contain documents with the same ID. A sort_id using only the local ID would not be unique across the alias.

You can construct a global key such as:

~~~text
articles-2025:1001
articles-2026:1001
~~~

Or use a global UUID generated at the data source. The goal is that tie-breaker values never collide between any two documents that can appear in the same query.

If the key is composed of tenant and ID, use an unambiguous, stable encoding. For example, concatenating strings with a delimiter is insufficient if components can contain that delimiter; use a UUID or an encoding with strict rules.

## 4. Multi-Field Sorting in Elasticsearch

Elasticsearch supports sorting by multiple fields. Sorts are applied in the declared order:

~~~json
{
  "sort": [
    {"published_at": {"order": "desc"}},
    {"priority": {"order": "desc"}},
    {"sort_id": {"order": "asc"}}
  ]
}
~~~

Meaning:

1. Newer articles come first.
2. On the same publication date, higher-priority articles come first.
3. If still tied, sort_id determines the final position.

Different sort types can be combined:

| Field type | Sort example | Notes |
|---|---|---|
| date | published_at desc | Standardize format and timezone |
| keyword | category asc | Usually uses doc values |
| numeric | price asc | Choose a numeric type with sufficient range |
| boolean | featured desc | Verify true/false ordering explicitly |
| geo_point | _geo_distance | Requires origin and unit |
| _score | _score desc | Used for relevance |

If sorting by business fields while still needing scores returned in SearchHit, check the track_scores option suitable for your API. Sorting by fields does not automatically imply scores are computed and returned the way the application expects.

### 4.1. asc and desc Order

The tie-breaker's direction must be chosen consistently:

- sort_id asc: smaller key comes first when preceding criteria tie.
- sort_id desc: larger key comes first.

Both establish a total order if keys are unique. Crucially, every request within the same pagination flow must use the same field and same sort direction.

### 4.2. Missing Values

Elasticsearch allows controlling the placement of missing values in sorting, such as _first or _last. However, if the tie-breaker itself is missing, multiple documents may all receive the same missing value and once again lack a final tie-breaking criterion.

Therefore:

- Always populate the tie-breaker on every document.
- Audit older data before rolling out a new sort.
- Use a missing policy for optional business fields when needed.
- Do not rely on a missing policy to substitute for tie-breaker uniqueness.

### 4.3. Sorting on Multi-Valued Fields

A field can hold multiple values. Elasticsearch needs a rule to pick a representative value for sorting, such as min, max, avg, or median depending on field type and API.

For example:

~~~json
{
  "sort": [
    {
      "ratings": {
        "order": "desc",
        "mode": "avg"
      }
    },
    {
      "sort_id": "asc"
    }
  ]
}
~~~

If multiple documents have the same avg rating, sort_id still breaks the tie. Choose mode according to business meaning; choosing min versus max can significantly alter rankings.

## 5. Stable Sorting in Spring Data Elasticsearch

Spring Data Elasticsearch lets you specify sorting via Spring Data Sort, Pageable, or query objects. For repository methods returning Page, you can pass multiple Orders into PageRequest:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public Page<Article> findLatestArticles(int page, int size) {
    Sort sort = Sort.by(
            Sort.Order.desc("publishedAt"),
            Sort.Order.asc("sortId")
    );

    Pageable pageable = PageRequest.of(page, size, sort);
    return articleRepository.findByStatus("published", pageable);
}
~~~

In this example, sorting uses Java properties publishedAt then sortId. Spring Data uses mapping metadata to translate properties to the corresponding Elasticsearch field names, such as published_at and sort_id per annotations.

Repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    Page<Article> findByStatus(String status, Pageable pageable);
}
~~~

This example follows the repository query method pattern; the entity must have the status property and corresponding mapping. Property names passed to Sort must be properties recognized by the Spring Data mapping context. Do not pass arbitrary JSON field names or metadata names if they do not match the mapping.

### 5.1. Using Sort with ElasticsearchOperations

When building queries with ElasticsearchOperations, you can attach Sort to the query object:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.asc("sortId")
);

Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("title")
                .query("elasticsearch")
        ))
        .withSort(sort)
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Article> hits =
        operations.search(query, Article.class);
~~~

Builder APIs and how sort combines with pageable can vary across Spring Data Elasticsearch release trains. Use a single source of sort configuration, avoiding accidentally declaring sorts in both the query DSL and Pageable with unclear precedence.

For native queries requiring Elasticsearch-specific sorts, you can create SortOptions from the Elasticsearch Java Client and pass them through the NativeQuery API supported by your version.

## 6. Tie-Breakers and Offset Pagination (from/size)

Offset pagination uses from and size:

~~~json
{
  "from": 20,
  "size": 10,
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ],
  "query": {
    "term": {
      "status": "published"
    }
  }
}
~~~

The request fetches 10 results starting at position 20. Sorting with a tie-breaker gives each document a deterministic position within a given data state.

Offset pagination is straightforward to implement and suits early pages or data that changes infrequently. However, Elasticsearch must process hits from the start up to the offset before returning the desired page. Cost rises as from grows.

Elasticsearch typically caps from + size using index.max_result_window, commonly 10,000 by default. Raising the limit does not fundamentally solve deep pagination cost and can increase memory pressure.

### 6.1. Why Is a Tie-Breaker Still Not Enough When Data Changes?

Suppose the first page is read when 100 articles exist. Then a new article with a larger published_at is inserted at the top of the list. If the second page request uses from = 20 against the new state, article positions have shifted. Even with a unique sort_id, page two can repeat or skip an article relative to page one.

A tie-breaker guarantees a total order for a given data state. It does not freeze the index across multiple requests. To traverse a consistent result set while data changes, PIT is needed.

## 7. search_after for Deep Pagination

search_after continues searching from the sort values of the last hit on the previous page, instead of jumping to a large offset.

Suppose the sort is:

~~~json
{
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ]
}
~~~

Each hit returns a sort array containing the values used for sorting. For example:

~~~json
{
  "_id": "article-42",
  "_source": {
    "published_at": "2026-11-13T08:00:00Z",
    "sort_id": "article-42"
  },
  "sort": [
    "2026-11-13T08:00:00.000Z",
    "article-42"
  ]
}
~~~

To fetch the next page, pass the exact sort array of the last hit into search_after:

~~~json
{
  "size": 20,
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ],
  "search_after": [
    "2026-11-13T08:00:00.000Z",
    "article-42"
  ],
  "query": {
    "term": {
      "status": "published"
    }
  }
}
~~~

Do not recompute sort values yourself or pass only the first field's value. search_after requires values for the entire sort list and must keep the exact order, data types, sort directions, and query across requests.

### 7.1. search_after Pagination Flow

~~~text
First page request
   |
   v
Search with query + sort
   |
   v
Receive hits and sort values
   |
   v
Extract sort values of last hit
   |
   v
Next request with search_after
   |
   v
Receive next page
   |
   +---- repeat until results exhausted
~~~

search_after does not use page numbers like from/size. Clients must retain the cursor, which is the sort values of the last hit from the previous page. Therefore, UIs like "go to page 37" are less natural than next/previous or load-more interfaces.

### 7.2. Tie-Breakers Remain Essential

If the sort list only has published_at, multiple hits may share the same value. search_after may fail to establish a unique continuation point among tied hits. Adding a unique sort_id helps the cursor identify the exact boundary:

~~~json
{
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ]
}
~~~

With equal published_at, sort_id determines which documents come before and after the cursor.

## 8. PIT Combined with search_after to Preserve a Consistent View

Point in Time (PIT) creates a consistent view of an index for a period of time. When new data is written or the index refreshes while a user paginates, requests using the same PIT continue seeing the same data state.

PIT is commonly combined with search_after for deep pagination:

1. Open a PIT on the index or alias.
2. Send the first request with the PIT, query, and sort.
3. Read the sort values of the last hit.
4. Send the next request with the same PIT and search_after.
5. Extend keep_alive as needed to continue.
6. Close the PIT when finished.

### 8.1. Opening a PIT

~~~http
POST /articles-read/_pit?keep_alive=1m
~~~

The response returns the PIT ID. Store this ID on the client or in a server session as appropriate for your application.

### 8.2. First Request

~~~http
POST /_search
Content-Type: application/json

{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "status": "published"
    }
  },
  "sort": [
    {
      "published_at": {
        "order": "desc",
        "format": "strict_date_optional_time_nanos"
      }
    },
    {
      "sort_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

When using PIT, do not specify the index in the _search path because the PIT already defines the index set. Elasticsearch automatically appends _shard_doc as an internal tie-breaker for PIT searches, guaranteeing unique ordering within the PIT scope. A sort_id field remains useful for explicit, stable business ordering across independent searches.

### 8.3. Next Request

Suppose the last hit of the first page has sort values:

~~~json
[
  "2026-11-12T15:30:00.000Z",
  "article-0099"
]
~~~

Next request:

~~~http
POST /_search
Content-Type: application/json

{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "status": "published"
    }
  },
  "sort": [
    {
      "published_at": {
        "order": "desc",
        "format": "strict_date_optional_time_nanos"
      }
    },
    {
      "sort_id": {
        "order": "asc"
      }
    }
  ],
  "search_after": [
    "2026-11-12T15:30:00.000Z",
    "article-0099"
  ]
}
~~~

Take sort values from the actual response rather than reconstructing them from _source. For numeric, date/time, or geo sorts, returned values may differ in format from how the application stores them in entities.

If the response returns a new PIT ID, use the latest ID for the next request. keep_alive is how long the PIT should remain alive after a request; it is not a permanent retention limit.

### 8.4. Closing the PIT

When further pagination is no longer needed, close the PIT:

~~~http
DELETE /_pit
Content-Type: application/json

{
  "id": "PIT_ID"
}
~~~

PIT consumes resources because Elasticsearch must retain the segments required for the consistent view. Set a reasonable keep_alive, close the PIT when done, and avoid creating unnecessary long-lived PITs.

## 9. Internal _shard_doc Tie-Breaker and Business Fields

When using PIT, Elasticsearch appends _shard_doc as an internal tie-breaker if needed. _shard_doc combines the shard and the Lucene document order, establishing a unique order within the PIT scope.

There are two different goals:

| Mechanism | Goal |
|---|---|
| Unique business field like sort_id | Produces meaningful, explainable ordering usable across search sessions |
| _shard_doc in PIT | Produces unique, efficient ordering for traversing results within the same PIT |

_shard_doc is not a business ID. Do not persist this value in entities or use it as a durable key across separate PIT sessions. Internal document positions can change when indices are rebuilt or modified.

If the application only needs to iterate rapidly through all results within a single PIT, sorting by _shard_doc can be very efficient. If business priority order by date, price, or relevance is needed, keep your business criteria and let PIT supply the final internal tie-breaker or add sort_id explicitly.

## 10. Integrating Pagination with Spring Data Elasticsearch

### 10.1. Offset Pagination via Pageable

With standard repository methods:

~~~java
Page<Article> findByStatus(String status, Pageable pageable);
~~~

Service:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.asc("sortId")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Page<Article> page =
        articleRepository.findByStatus("published", pageable);
~~~

This is a straightforward approach when the application needs page numbers and total result counts. Keep the tie-breaker in every request so order is unambiguous when multiple articles share the same publication date.

### 10.2. search_after via ElasticsearchOperations

For deep pagination, Spring Data Elasticsearch provides query APIs for working with search_after and PIT in supported versions. You can visualize the workflow:

~~~java
// Pseudocode: exact API names depend on the Spring Data Elasticsearch version.
Query query = NativeQuery.builder()
        .withQuery(queryDsl)
        .withSort(sortOptions)
        .withPointInTime(pointInTime)
        .withSearchAfter(previousSortValues)
        .withMaxResults(20)
        .build();

SearchHits<Article> hits =
        operations.search(query, Article.class);
~~~

Where:

- pointInTime is the active PIT.
- previousSortValues is the array of sort values taken from the last hit of the previous page.
- sortOptions is the exact same sort list across all requests.
- max results is the number of hits to fetch for the page.

This is pseudocode illustrating the components to maintain. Builder method names, PointInTime types, how sort values are retrieved, and how PITs are opened/closed have evolved across release trains. Check the Javadoc for the exact version in your project before implementing.

### 10.3. Retrieving the Cursor from SearchHit

With search_after, the application needs to read the sort values of the last hit. Spring Data's SearchHit and SearchHits expose hit information, though APIs for accessing sort values can vary across versions. If your abstraction does not expose all needed data, you can use the Elasticsearch Java Client directly for cursor flows or add an adapter in the repository layer.

Do not retain only the ID of the last hit if the sort list contains multiple fields. The cursor must hold all sort values in order so Elasticsearch resumes accurately.

## 11. Considerations When Paginating Across Multiple Indices or Aliases

When querying through a multi-index alias, ensure:

- Sort fields exist on every involved index.
- Mapping types of sort fields are compatible across indices.
- Tie-breakers are unique across the entire document set, not only within each individual index.
- Field names and sort directions do not change between pages.
- The PIT is opened on the appropriate alias or index pattern.

If an older index lacks sort_id, documents from that index may receive a missing value and lose uniqueness. Backfill the field before enabling the new sort or use a controlled transition strategy.

When sort fields differ in type across indices, Elasticsearch may require numeric_type or format to unify sorting; exact support and syntax depend on the field type. It is best to standardize mappings across indices from the start using index templates.

## 12. Data Changes That Affect Sorting

Even with a tie-breaker, sorting is only stable if the values being sorted do not change within the traversal scope.

For example:

- publishedAt is updated after the first page is returned.
- popularity changes continuously while being used as the primary sort criterion.
- sort_id is modified or reused.
- Documents are deleted or inserted between offset requests.

PIT addresses index mutations during pagination by maintaining a consistent view. However, PIT does not make a mutating business sort field immutable in newly opened PITs. If stable ordering across multiple search sessions is required, business sort fields must follow clear update rules.

With continuously changing popularity, decide whether users need a stable result snapshot for the current session or continuously updated rankings. You cannot simultaneously preserve a stable cursor and continuously reshuffle order without explicit page-transition rules.

## 13. Testing Stable Ordering

A test suite should create multiple documents with the same primary criterion value to prove the tie-breaker works:

~~~json
[
  {"published_at": "2026-11-01T10:00:00Z", "sort_id": "a-003"},
  {"published_at": "2026-11-01T10:00:00Z", "sort_id": "a-001"},
  {"published_at": "2026-11-01T10:00:00Z", "sort_id": "a-002"},
  {"published_at": "2026-10-31T10:00:00Z", "sort_id": "a-004"}
]
~~~

With sort published_at desc and sort_id asc, the expected order is:

~~~text
1. a-001 (2026-11-01)
2. a-002 (2026-11-01)
3. a-003 (2026-11-01)
4. a-004 (2026-10-31)
~~~

Scenarios to test:

1. Multiple documents sharing the same primary sort value.
2. Tie-breaker is unique and present on every document.
3. Two repeated requests against the same index state return the same order.
4. Splitting results into multiple pages without duplicates or skipped documents.
5. Adding a new document between two offset requests to observe refresh effects.
6. Adding a new document between two PIT + search_after requests to verify PIT preserves the result set.
7. Missing or null sort fields.
8. An alias spanning multiple indices with locally colliding IDs.
9. Multi-field sorts with mixed asc/desc directions.
10. Sort fields having consistent mapping types across indices.

### 13.1. Comparing the Two Pagination Approaches

| Criterion | from/size + tie-breaker | PIT + search_after |
|---|---|---|
| Ease of implementation | Easy | More complex |
| First page and shallow pages | Suitable | Suitable |
| Deep pagination | Cost grows with offset | Better suited |
| Result window limit | Bounded by max_result_window | Does not use large offsets |
| Stability when index changes | Not guaranteed across requests | Keeps consistent view within PIT |
| Requires storing cursor | No | Yes, sort values of last hit |
| Lifecycle management | Simple | Must renew and close PIT |

Tie-breakers are beneficial in both approaches. PIT + search_after additionally solves cross-request consistency and deep pagination efficiency.

## 14. Common Pitfalls

### 14.1. Sorting Only by a Non-Unique Field

Multiple documents share the same date, price, or score. Append a unique tie-breaker field at the end of the sort list.

### 14.2. Using _id as a Sort Tie-Breaker

_id is an identification metadata field and not a general-purpose sort field. Copy the ID into a keyword or numeric field with doc values.

### 14.3. Tie-Breaker Only Unique Within One Index

Aliases can query multiple indices. Ensure the key is unique across the entire result set.

### 14.4. Tie-Breaker Missing on Older Documents

Missing values do not guarantee a total order. Backfill legacy data or use a migration strategy.

### 14.5. Using search_after While Passing Only the First Sort Value

The cursor must contain all sort values of the last hit in the exact order of the sort list.

### 14.6. Changing Query or Sort Between Pages

Every subsequent request must keep the same query and sort within a search_after flow. If criteria change, the old cursor is no longer meaningful.

### 14.7. Using search_after Without PIT While the Index Changes

A tie-breaker establishes a total order but does not hold a data snapshot. If consistent traversal is required, use PIT.

### 14.8. Keeping PIT Open Too Long

PIT retains resources and necessary segments. Use an adequate keep_alive, renew as progress is made, and close the PIT when done.

### 14.9. Increasing max_result_window to Solve Every Case

Raising the from/size limit increases memory load and does not solve page drift when the index changes. For deep pagination, consider search_after.

## 15. Workflow for Designing Sorting and Pagination

When building a paginated search API:

1. Identify the primary business order, such as relevance, newest date, or lowest price.
2. Identify a unique, immutable tie-breaker field.
3. Ensure the tie-breaker has a sortable mapping and a value on every document.
4. If searching across multiple indices, ensure globally unique keys and compatible mappings.
5. Declare all sort fields in priority order.
6. Choose from/size for shallow pages or PIT + search_after for deep pagination.
7. With PIT, maintain the PIT ID and sort values in the request coordinator.
8. Do not alter the query/sort within a single cursor session.
9. Set an appropriate keep_alive and close the PIT upon completion.
10. Test ties, missing data, index refreshes, and multi-index aliases.

Decision examples:

| Need | Design |
|---|---|
| Latest articles list, first pages | published_at desc, sort_id asc |
| Relevance scores can tie | _score desc, sort_id asc |
| Lowest price first | price asc, sort_id asc |
| Shallow pagination with page numbers | Pageable/from-size and tie-breaker |
| Traversing hundreds of thousands of results | PIT + search_after |
| Searching across multi-index alias | Globally unique tie-breaker and consistent mappings |

## 16. Conclusion

When multiple documents share the same value on a primary sort field, Elasticsearch needs an additional criterion to determine the order among them. A unique, stable, always-present, and sortable tie-breaker establishes a total order. Typically, the application copies the ID into a keyword or numeric field with doc values rather than relying on _id for sorting.

Multi-field sorting lets you combine business criteria such as date, price, or score with a tie-breaker at the end. This makes ordering deterministic within a given index state and makes pagination more predictable.

With offset pagination, a tie-breaker cannot prevent pages from shifting when the index changes between requests. For deep pagination or when a consistent result set is needed, use PIT with search_after, keep the query and sort unchanged, pass the complete sort values of the last hit, and close the PIT after completion. In Spring Data Elasticsearch, use Pageable for standard pagination and the NativeQuery/search_after/PIT APIs of your exact version for cursor flows.
