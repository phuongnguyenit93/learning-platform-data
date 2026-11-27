# Reducing Returned Data with Source Filtering and Page Size

An Elasticsearch query can find the right documents and still return more data than the application needs. For example, a product listing screen only displays name, price, and category, while each document also holds a long description, supplier details, change history, and internal fields. Returning the entire `_source` for hundreds of results makes responses larger than necessary, increasing network transfer, deserialization cost, and memory retention for objects.

There are two ways to control the amount of returned data:

- **Source filtering** selects which fields in `_source` are sent back to the client using `_source.includes` and `_source.excludes`.
- **Page size** limits the number of hits Elasticsearch returns in a single search request using `size`, typically configured in Spring Data via `Pageable`.

These two mechanisms address two different dimensions: source filtering reduces the fields per hit; page size reduces the number of hits per response. Combining both properly keeps responses lean and bounds memory usage, though it does not replace query, mapping, sort, or aggregation optimization.

## 1. Why limit returned data?

Suppose a product document has this structure:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORIES",
  "price": 1299000,
  "description": "A long product description ...",
  "supplier": {
    "name": "Example Supplier",
    "contact": {
      "email": "private@example.com",
      "phone": "+84..."
    }
  },
  "internalNotes": "Internal purchasing notes ...",
  "changeHistory": [
    {
      "changedBy": "admin-01",
      "changedAt": "2026-11-13T08:00:00Z"
    }
  ]
}
~~~

The listing screen only needs:

- productId
- name
- category
- price

Without a source filter, Elasticsearch usually returns the entire source of each hit. With a page size of 100, the response can carry 100 copies of descriptions, supplier information, and change history even though the UI does not use them.

Common impacts:

- Larger JSON responses.
- Higher bandwidth usage between Elasticsearch and the application.
- Client must parse and deserialize many fields.
- Entities retain large amounts of unused data.
- Downstream APIs or serializers may continue copying large payloads.
- Internal information may unintentionally propagate deeper into processing or responses if mappings are not controlled.

Source filtering and page size are two straightforward limits that can be applied directly to search requests.

## 2. What is source filtering?

Elasticsearch stores document content in the `_source` metadata field (if the index is configured to store source). Source filtering lets you choose which fields in `_source` appear in search results.

Example fetching only name and price:

~~~http
GET /products/_search
{
  "_source": [
    "name",
    "price"
  ],
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Each hit in the result contains only the selected source portion:

~~~json
{
  "_index": "products",
  "_id": "P-1001",
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

The original document in the index still contains the other fields. Source filtering only controls the portion of source returned in the search response.

You can specify includes and excludes explicitly:

~~~json
{
  "_source": {
    "includes": [
      "name",
      "price",
      "category"
    ],
    "excludes": [
      "internalNotes",
      "supplier.contact.*"
    ]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Meaning:

- `includes`: specifies the fields allowed to appear in the returned source.
- `excludes`: removes fields that should not be returned.
- Wildcards can be used for field names and nested paths.
- If `includes` is omitted, source is treated as including all fields except excluded ones.

When both `includes` and `excludes` are present, design a clear include set and use excludes for subtrees that must be removed. Avoid relying on overlapping rules that are hard to read.

## 3. Includes and excludes for nested fields

Source filtering supports nested field paths:

~~~json
{
  "_source": {
    "includes": [
      "name",
      "price",
      "supplier.name"
    ],
    "excludes": [
      "supplier.contact",
      "changeHistory"
    ]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Wildcards can be used:

~~~json
{
  "_source": {
    "includes": [
      "name",
      "attributes.*"
    ],
    "excludes": [
      "attributes.internal*"
    ]
  }
}
~~~

For example, if source contains:

~~~json
{
  "name": "Wireless Keyboard",
  "attributes": {
    "color": "Black",
    "layout": "US",
    "internalSupplierCode": "SUP-SECRET"
  }
}
~~~

The response can keep the included attributes and drop the excluded branch.

Prefer explicit paths over broad wildcards if the data has sensitive branches or evolves over time. A newly added field under a wildcard branch can automatically appear in future responses.

## 4. Distinguishing source filtering from query filtering

These two concepts have similar names but completely different purposes:

| Mechanism | Effect | Changes matching document set? |
|---|---|---|
| Query/filter | Selects which documents are found | Yes |
| Source filtering | Selects which fields in each document are returned | No |
| Page size | Limits how many hits are returned in the request | Limits response hit count |
| Sort | Determines hit ordering | Does not filter documents by itself |

Example query filtering published products with source filtering for three fields:

~~~json
{
  "_source": {
    "includes": [
      "productId",
      "name",
      "price"
    ]
  },
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  },
  "size": 25
}
~~~

The query still finds documents with `status = PUBLISHED`. Source filtering does not make Elasticsearch skip documents with other statuses; the query handles that.

Conversely, excluding the `status` field from returned source does not mean the query condition is not applied. A field can be used for filtering or sorting without appearing in the returned `_source`.

## 5. Using FetchSourceFilter in Spring Data Elasticsearch

Spring Data Elasticsearch provides `FetchSourceFilter` to configure source includes and excludes.

Example returning only name, price, and category:

~~~java
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

String[] includes = {
        "productId",
        "name",
        "category",
        "price"
};

String[] excludes = {
        "internalNotes",
        "supplier.contact",
        "changeHistory"
};

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(
                new FetchSourceFilter(includes, excludes)
        )
        .build();
~~~

Components:

- The `includes` array lists fields to return.
- The `excludes` array lists fields to omit.
- `FetchSourceFilter` translates this configuration into a source filter for the request.
- `withSourceFilter(...)` attaches the filter to `NativeQuery`.

When using `includes`, only the selected fields are expected in source. When using `excludes`, excluded fields do not appear in the returned source.

If you only want to exclude a few fields while keeping the rest, you can leave `includes` empty:

~~~java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
        new String[] {},
        new String[] {
                "internalNotes",
                "supplier.contact",
                "changeHistory"
        }
);
~~~

Use the correct Spring Data Elasticsearch import: `org.springframework.data.elasticsearch.core.query.FetchSourceFilter`. Do not confuse it with source filter classes from the Elasticsearch Java API Client.

## 6. Combining source filtering and Pageable

Page size limits the number of hits Elasticsearch returns in a single request. In Spring Data Elasticsearch, this can be set via `PageRequest` and `withPageable(...)`.

Example fetching the first 50 products with only the required fields:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(
                new FetchSourceFilter(
                        new String[] {
                                "productId",
                                "name",
                                "category",
                                "price"
                        },
                        new String[] {
                                "internalNotes",
                                "changeHistory"
                        }
                )
        )
        .withPageable(PageRequest.of(0, 50))
        .build();
~~~

In this example:

- `PageRequest.of(0, 50)`: first page, at most 50 hits.
- `FetchSourceFilter`: limits the fields per hit.
- `withQuery(...)`: preserves the business search criteria.

You can think of response size as depending on both factors:

~~~text
Max hits in response          = page size
Fields in each hit            = source filter
~~~

If each document has a large source, reducing page size alone may not be enough. If each document is small but tens of thousands of hits are fetched, source filtering alone is also insufficient.

## 7. Building queries with API-validated page size

Do not pass a client-supplied page size directly without bounding it. An API can normalize `page` and `size`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

private Pageable createPageable(
        int requestedPage,
        int requestedSize
) {
    int page = Math.max(requestedPage, 0);

    int defaultSize = 25;
    int maxSize = 200;

    int size = requestedSize <= 0
            ? defaultSize
            : Math.min(requestedSize, maxSize);

    return PageRequest.of(
            page,
            size,
            Sort.by(
                    Sort.Order.asc("name"),
                    Sort.Order.asc("productId")
            )
    );
}
~~~

Rules:

- Page index starts at 0.
- Size must be greater than 0.
- Size must not exceed the service's allowed maximum.
- Sort should be stable, with a unique tie-breaker.
- Do not let clients choose arbitrary sort fields if doing so could trigger expensive queries or access unintended fields.

Then:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(sourceFilter)
        .withPageable(createPageable(page, size))
        .build();
~~~

Service limits should be based on document size, latency, heap, and UI requirements. There is no single optimal page size for every index.

## 8. Reading results with ElasticsearchOperations

Once the query has a source filter and page size, it can be executed via `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> searchHits =
        operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products")
        );
~~~

`SearchHits<T>` holds the hits returned by the request. You can read each hit:

~~~java
searchHits.getSearchHits().forEach(hit -> {
    ProductDocument product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(product.getPrice());
});
~~~

Or map them to a list:

~~~java
List<ProductDocument> products =
        searchHits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
~~~

Source filtering affects the source that gets deserialized. Properties not returned will have no data from the response; for standard object fields they may receive `null` or defaults depending on how constructors and property mapping are implemented.

Do not call methods that rely on a field excluded by the source filter and assume it still has a value.

## 9. Using small projections/DTOs for search screens

A clean pattern is to create a data type containing only the fields needed for the listing screen:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductSearchView {

    @Id
    private String id;

    private String productId;

    private String name;

    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructor, getters and setters
}
~~~

Searching with this result type:

~~~java
SearchHits<ProductSearchView> hits =
        operations.search(
                query,
                ProductSearchView.class,
                IndexCoordinates.of("products")
        );
~~~

Advantages:

- The return type clearly expresses the data the UI needs.
- Services cannot accidentally depend on internal fields.
- Easy to control the API response.
- Can be combined with a source filter to reduce network payload and deserialization work.

Note: a DTO does not perform source filtering automatically. If no source filter is added, Elasticsearch may still return the entire source; the converter simply maps the fields the DTO knows about. To reduce data transferred over the network, you still need to configure a source filter on the query.

If the DTO has `@Id`, the ID value can be populated from the hit's `_id` metadata. `_id` is not a regular field inside `_source`; you do not need to include a source field named `_id` unless the application actually stores such a field in source.

## 10. Which fields should be kept in the response?

Choose fields based on the endpoint's purpose.

Examples:

| Use case | Fields that may be needed |
|---|---|
| Product listing | productId, name, thumbnail, price |
| Product detail | name, description, attributes, images, price |
| Autocomplete suggestions | name, productId |
| Category report | Possibly aggregations only, no document hits needed |
| Status check | productId, status, updatedAt |
| Data export | Only columns included in the export file |

There is no fixed field list for every application. Each endpoint should define a specific response contract.

In particular, do not return the entire persistence object just because the UI might need more fields in the future. When the contract changes, update the source filter and DTO deliberately.

## 11. Does source filtering reduce query execution cost?

Source filtering primarily reduces the source data returned in the search response. It can reduce:

- JSON response size.
- Network transfer.
- Client-side parse/deserialization cost.
- Number of fields retained in application objects.
- Risk of unintentionally forwarding unnecessary data.

However, source filtering **does not by itself reduce**:

- The number of documents Elasticsearch must match.
- Query/filter evaluation cost.
- Scoring cost.
- Sorting cost.
- The number of aggregation buckets to compute.
- The number of shards queried.
- Stored source size in the index.

Elasticsearch still has to execute the search and retrieve source to apply the source filter during the fetch phase. Thus, source filtering optimizes response/fetch payload, not query optimization or mapping/index design.

If a query needs to filter by `status`, index the field appropriately and use a query/filter. Excluding `status` from the returned source does not make the query cheaper by changing the dataset scanned.

## 12. Source filtering vs. doc values/fields API

Applications do not always need JSON source. If you only need values of properly mapped fields, Elasticsearch also provides the Fields API or `docvalue_fields` for certain field types.

Distinctions:

| Retrieval method | Origin | When suitable |
|---|---|---|
| `_source.includes/excludes` | Stored JSON source | Need part of the original document, including object structures |
| `fields` | Field values per mapping/format | Need field values processed by Elasticsearch according to mapping |
| `docvalue_fields` | Doc values of supported fields | Need columnar values, typically for sort/aggregation-friendly fields |
| `stored_fields` | Fields separately configured with store | Only when mapping and use case intentionally use stored fields |

Example `docvalue_fields`:

~~~json
{
  "query": {
    "match_all": {}
  },
  "docvalue_fields": [
    "price",
    "createdAt"
  ],
  "_source": false
}
~~~

Not every field has doc values. `text` fields typically lack doc values by default, whereas `keyword`, numeric, and `date` usually support them. Verify mapping and response format.

`stored_fields` also does not automatically work for every field; the field must be mapped with `store: true`. Do not enable `store` on every field just to replace source filtering.

For most document-returning APIs, source filtering is the simplest choice. Only use `fields`/`docvalue_fields` when the application specifically needs the semantics and formatting of those APIs.

## 13. When _source is disabled

Source filtering relies on `_source`. If an index is created with `_source.enabled: false`, the application cannot request partial source in the usual way.

Example mapping:

~~~json
{
  "mappings": {
    "_source": {
      "enabled": false
    },
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

When source is disabled:

- Original JSON source cannot be retrieved via search hits.
- Source filtering has no source to filter.
- You must rely on stored fields or appropriate `fields`/doc values.
- Features requiring reindexing/updating from source can be impacted.

Do not disable `_source` just to make responses smaller. Keeping `_source` and selecting returned fields per query is usually far more flexible. Disabling `_source` is a mapping/storage decision with wide impact, requiring consideration of updates, reindexing, debugging, and recovery.

## 14. Limiting page size and from/size

`PageRequest.of(page, size)` is typically translated into offset pagination using `from` and `size`.

Formula:

\[
from = page \times size
\]

For example, `page = 20`, `size = 50` starts at offset 1,000.

Elasticsearch enforces `index.max_result_window`; a common default is 10,000. Requests where `from + size` exceeds the limit can be rejected.

Increasing page size or `max_result_window` is not an appropriate way to read an entire large index. Deep offset pagination forces Elasticsearch to process results preceding the returned slice.

Use `from/size` for moderate UI pagination depth. For exports or reading hundreds of thousands of documents, consider `search_after` combined with Point in Time (PIT).

## 15. Stable sorting during pagination

To prevent the next page from duplicating or skipping results when hits share identical sort values, use a stable sort order.

Example:

~~~java
Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("productId")
        )
);
~~~

`productId` should be a `keyword` field with unique values across the paginated dataset.

If you sort only by `createdAt`, multiple documents with the same timestamp may have unstable relative ordering across requests. A tie-breaker provides deterministic ordering.

Stable sorting does not create a data snapshot. If documents are added/deleted between offset requests, page positions can still shift. If you need a consistent snapshot across pages, use PIT with `search_after`.

## 16. Source filtering when using search_after

Source filters are independent of the pagination mechanism. You can keep the same filter when using `search_after`:

~~~java
NativeQuery firstPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(sourceFilter)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .build();
~~~

After receiving the first page, extract the sort values of the last hit:

~~~java
List<SearchHit<ProductSearchView>> hits =
        searchHits.getSearchHits();

List<Object> cursor = hits
        .get(hits.size() - 1)
        .getSortValues();
~~~

The next query keeps the same source filter, query, and sort:

~~~java
NativeQuery nextPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(sourceFilter)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withSearchAfter(cursor)
        .build();
~~~

The source filter trims fields returned per hit. `search_after` determines the continuation point. Both features are independent and composable.

When using PIT, attach the PIT to each request per your client version's API, update to the latest PIT ID if returned in the response, and close the PIT when finished.

## 17. Fetching aggregations only when document source is not needed

If an endpoint only displays statistics, there is no need to return a document list. You can request `size = 0` and fetch only aggregations.

Example:

~~~java
NativeQuery aggregationQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withAggregation("by_category", categoryAggregation)
        .withMaxResults(0)
        .build();
~~~

When no hits are returned:

- No source filter is needed for document hits.
- The response focuses on aggregation results.
- There is no need to deserialize an unused list of entities.

This is a suitable optimization for dashboards, category counts, or metrics. If a query needs aggregations along with a few sample documents, set a small page size accordingly.

## 18. Measuring response size and impact

Do not merely assume a source filter always yields significant gains. Measure on data of production-like size.

A comparison you can run:

1. Run the query without a source filter using the same query, sort, and page size.
2. Record response bytes and duration.
3. Rerun with source includes/excludes.
4. Compare response bytes, latency, CPU, and client-side heap allocation.
5. Keep query conditions identical for a fair comparison.
6. Repeat with small/large page sizes to isolate the effect of hit count.

Metrics to observe:

| Metric | What to learn |
|---|---|
| Response bytes | How much network payload decreased |
| Elasticsearch took | Request processing time on Elasticsearch |
| Client latency | Total time from the application |
| Deserialize time | Cost of converting JSON into objects |
| Heap allocation | Memory used when processing results |
| Hit count | Number of documents returned |
| Page count | Number of requests needed to read the full dataset |
| Error/timeout rate | Impact when page size is too large |

`hits.total` is the total number of matching documents according to tracking semantics, whereas actual hits in `hits.hits` are bounded by page size. Do not use the hit count in a response to infer the index's total document count.

## 19. Common mistakes

### Reducing page size while still returning full source

Responses remain large if each document has many fields or nested arrays. Add a source filter matching the endpoint's needs.

### Using a source filter with an overly large page size

Each hit is smaller, yet tens of thousands of hits still produce a huge response and consume memory. Bound page size as well.

### Thinking source filtering reduces query execution cost

Source filtering does not replace query/filter, sort, or aggregation optimization. It primarily reduces returned source data.

### Excluding sensitive fields while including a broad wildcard

Wildcards can expose new fields in responses when the schema changes. Prefer an allowlist of `includes` for public endpoints.

### Assuming a DTO automatically shrinks network payload

A DTO only limits mapped fields on the client. If the request lacks a source filter, the full source may still travel over the network.

### Calling getters on filtered-out fields

Fields omitted from source may be null or hold default values. Only access fields requested by the query.

### Confusing _id with a field inside _source

Document ID is hit metadata. You do not need to include a source field named `_id` to receive the document ID.

### Increasing max_result_window to export the entire index

Deep offsets consume substantial resources. Use `search_after` and PIT for deep reads.

### Sorting on a non-unique field

Multiple documents sharing the same sort value can make page order unstable. Add a unique tie-breaker.

### Disabling _source just to shrink responses

Disabling `_source` affects updates, reindexing, and retrieving original documents. Use per-request source filtering when selecting fields.

### Forgetting to bound client-provided page size

Clients can pass very large sizes, straining the cluster and heap. Normalize page and size on the server.

## 20. Implementation workflow

When optimizing search responses with source filtering and page size:

1. Identify which fields the endpoint needs in each hit.
2. Prefer an allowlist of `includes` for clearly structured responses.
3. Use `excludes` to drop large or internal subtrees where appropriate.
4. Create a `FetchSourceFilter` and attach it to `NativeQuery`.
5. Choose a default page size and maximum cap in the service.
6. Use `Pageable` to control paging and sorting.
7. Use small DTOs/projections to represent the response contract.
8. Avoid logic depending on filtered-out fields.
9. For deep exports, use `search_after` and PIT instead of large offsets.
10. For aggregation-only reports, set max results to 0.
11. Measure response bytes, latency, deserialization, and heap allocation.
12. Test nested fields, wildcards, empty sources, and mapping changes.
13. Verify access controls and ensure sensitive fields never appear in responses.
14. Monitor page sizes, page counts, timeouts, and result-window limit errors.

## References

- [Elasticsearch — Retrieve selected fields from a search](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-fields.html)
- [Elasticsearch — The _source field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch — Point in time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — FetchSourceFilter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/FetchSourceFilter.html)
- [Spring Data Elasticsearch — Pageable search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

## Conclusion

Source filtering selects which fields are returned per hit via `includes`/`excludes`; page size limits how many hits are returned in a single search request. In Spring Data Elasticsearch, combine `FetchSourceFilter` with `NativeQuery.withPageable(PageRequest.of(...))` to reduce payload along both width and count. Use small DTOs to express the response contract, while still configuring source filters if you want to reduce network transfer. Source filtering does not make queries cheaper in every phase and does not replace mapping, filter, or sort optimization. For deep pagination, use `search_after` with a stable sort and PIT; for statistics-only queries, return no hits.
