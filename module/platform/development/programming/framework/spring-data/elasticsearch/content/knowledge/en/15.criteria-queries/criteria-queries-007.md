# Combining `CriteriaQuery` with `Sort` and `Pageable`

In Spring Data Elasticsearch, `CriteriaQuery` lets you build search conditions using a Java API instead of writing the entire Query DSL as JSON. When combined with `Sort` and `Pageable`, an application can filter data by multiple conditions, sort results by one or more fields, and retrieve pages of a defined size.

Three components handle three distinct responsibilities:

- **Criteria** describes filter conditions, such as status equals `ACTIVE`, price greater than a threshold, or creation date within a range.
- **Sort** specifies result ordering, such as price descending then name ascending.
- **Pageable** specifies which page to retrieve and the maximum number of documents per page; it can also carry sort information.

`CriteriaQuery` combines Criteria conditions into a query, which is then sent through `ElasticsearchOperations` for Elasticsearch to execute.

```text
Criteria
  status = ACTIVE
  price >= 100
  category = KEYBOARD
      |
      v
CriteriaQuery
      |
      +---- Sort: createdAt DESC, sku ASC
      |
      +---- Pageable: page 0, size 20
      |
      v
ElasticsearchOperations.search(...)
      |
      v
Elasticsearch cluster
      |
      v
SearchHits / SearchPage
```

## 1. What Is `CriteriaQuery`?

`CriteriaQuery` is an implementation of Spring Data Elasticsearch's `Query`, constructed from a `Criteria` object. `Criteria` describes conditions such as comparisons, exact matches, field existence, or AND/OR combinations.

Example entity:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(name = "created_at", type = FieldType.Date)
    private Instant createdAt;

    // constructors, getters, setters
}
```

Creating basic conditions:

```java
Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("category").is("KEYBOARD")
        .and("price").greaterThanEqual(new BigDecimal("100"));

CriteriaQuery query = new CriteriaQuery(criteria);
```

The Criteria above requires documents to have `status` as `ACTIVE`, `category` as `KEYBOARD`, and `price` greater than or equal to 100. This is a filter condition; it does not yet specify result ordering or count.

Property names passed to Criteria are typically property names in the domain class so Spring Data can apply mapping metadata. If an entity uses `@Field(name = "created_at")` for property `createdAt`, prefer referencing the Java property `createdAt` when using Spring Data abstractions; with raw Query DSL sent directly to Elasticsearch, use the actual field name `created_at`.

## 2. Combining Multiple Criteria Conditions

You can chain conditions with AND using `and(...)`:

```java
Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("price").greaterThanEqual(100)
        .and("price").lessThan(500)
        .and("category").is("KEYBOARD");
```

This example finds active products in the keyboard category priced from 100 to under 500. You can use other comparison operations such as `greaterThan`, `lessThanEqual`, `between`, `in`, `notIn`, `contains`, `startsWith`, `endsWith`, or `exists` depending on field type and API version.

Combine with OR using Criteria groups:

```java
Criteria active = new Criteria("status").is("ACTIVE");
Criteria featured = new Criteria("featured").is(true);

Criteria criteria = new Criteria().or(active, featured);
CriteriaQuery query = new CriteriaQuery(criteria);
```

The condition above finds documents satisfying `status = ACTIVE` or `featured = true`. When a query has multiple AND/OR groups, declare separate Criteria variables named after their business meaning for readability.

Example of a compound condition group:

```java
Criteria statusCriteria = new Criteria("status").is("ACTIVE");

Criteria priceCriteria = new Criteria("price").lessThan(100)
        .or(new Criteria("price").greaterThan(1000));

Criteria criteria = statusCriteria.and(priceCriteria);
```

The results are active documents with prices below 100 or above 1000. For complex expressions, inspect the generated Query DSL to confirm AND/OR grouping matches intent.

## 3. Adding `Sort` to `CriteriaQuery`

Spring Data's `Sort` describes sort order. A `Sort` can contain multiple `Sort.Order` instances; the order of orders determines precedence.

Example sorting by price descending:

```java
Sort sort = Sort.by(Sort.Order.desc("price"));
```

Sorting by multiple fields:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);
```

Ordering is applied as follows:

1. `createdAt` descending, so newer documents come first.
2. If multiple documents share the same `createdAt`, `sku` ascending breaks ties.

You can attach sort directly to the query:

```java
CriteriaQuery query = new CriteriaQuery(criteria);
query.addSort(sort);
```

In Spring Data Elasticsearch versions with the `Query.addSort` API, you can also add individual orders using corresponding overloads. Check the exact syntax against your project's dependency version.

### Ascending and Descending Sort

```java
Sort ascending = Sort.by(Sort.Order.asc("price"));
Sort descending = Sort.by(Sort.Order.desc("price"));
```

`asc` sorts ascending; `desc` sorts descending. With multiple orders, orders declared earlier take higher priority.

### Sorting by a Field Whose Name Differs from the Java Property

If the entity declares:

```java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
```

When using Spring Data `Sort` on a domain type, typically reference the Java property:

```java
Sort sort = Sort.by(Sort.Order.desc("createdAt"));
```

Mapping metadata lets Spring Data map the property to the actual field. When writing native Elasticsearch sorting or raw requests manually, use `created_at`. Do not mix Java property names and Elasticsearch field names at the same abstraction layer without confirming which naming convention the API expects.

## 4. Which Fields Can Be Sorted?

Elasticsearch only sorts efficiently on fields with compatible types and configurations. Commonly sorted fields include:

- `keyword`: codes, statuses, normalized names, or categorical values.
- Numeric types: `integer`, `long`, `float`, `double`, `scaled_float`.
- `date`: creation timestamps, update dates, or deadlines.
- Boolean and certain other scalar types supported for sorting by Elasticsearch.

`text` fields generally lack doc values and are unsuitable for direct sorting. If you need both full-text search and whole-string sorting, declare a `keyword` multi-field:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
```

Then sort by `name.keyword` in native Elasticsearch queries. With Spring Data mappings, check how properties/subfields are expressed in `Sort` for your version; you can use the sub-field name when the API expects an Elasticsearch field path.

Do not enable `fielddata` on a `text` field just for sorting when a `keyword` subfield works instead. Fielddata can consume significant heap and increase memory pressure.

### Stable Sorting When Multiple Documents Share the Same Value

If you only sort by `createdAt`, documents with identical timestamps may appear in unstable order across queries. During pagination, this can cause documents to repeat or be skipped between pages if order shifts.

Add a secondary field that has unique values and is sortable, such as a `keyword` `sku`:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);
```

`sku` serves as a tie-breaker to determine order among documents with the same timestamp. Do not rely on `_id` as a sort field by default: `_id` is special metadata without doc values configured for normal sorting. Store a sortable identifier field if stable ordering is required.

## 5. Adding `Pageable` for Pagination

`Pageable` defines the page and page size. With `PageRequest`, page numbering starts at 0:

```java
Pageable pageable = PageRequest.of(0, 20);
```

Meaning:

- `0`: the first page.
- `20`: at most 20 documents per page.

Second page:

```java
Pageable pageable = PageRequest.of(1, 20);
```

Spring Data translates this into the corresponding offset/limit pagination when building the search request. Conceptually:

```text
Page 0, size 20  -> from = 0,  size = 20
Page 1, size 20  -> from = 20, size = 20
Page 2, size 20  -> from = 40, size = 20
```

`PageRequest.of(page, size)` requires a non-negative `page` and a `size` greater than 0. Cap page size in the API service to prevent clients from requesting overly large pages that strain cluster and application memory.

## 6. Putting Sort Inside Pageable

A common pattern is passing `Sort` into `PageRequest`. A single `Pageable` object then carries page number, page size, and sort order:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);

Pageable pageable = PageRequest.of(0, 20, sort);

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(pageable);
```

This is convenient when sorting is tied to endpoint pagination. When advancing pages, create a new `PageRequest` with a different page index while keeping the same sort.

Service method example:

```java
public SearchHits<ProductDocument> searchProducts(
        String status,
        int page,
        int size) {

    Criteria criteria = new Criteria("status").is(status);

    Sort sort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("sku")
    );

    Pageable pageable = PageRequest.of(page, size, sort);

    CriteriaQuery query = new CriteriaQuery(criteria);
    query.setPageable(pageable);

    return operations.search(query, ProductDocument.class);
}
```

The service takes page and size from the caller, builds conditions, creates sort, attaches pageable, and calls `ElasticsearchOperations.search`. The snippet assumes `operations` is an injected `ElasticsearchOperations` bean.

## 7. Adding Pageable and Sort Separately on Query

Spring Data Elasticsearch's `Query` can manage pageable and sort independently. You can set an unsorted pageable and then add sort to the query:

```java
CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));
query.addSort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
));
```

This is helpful when sorting is constructed independently from paging parameters. However, avoid declaring sort on both `Pageable` and `Query` unless intentionally desired. When two sort sources exist, how orders are merged or deduplicated depends on the query implementation in your Spring Data version.

Choose a single source to define sort:

- Sort is part of the pagination API: use `PageRequest.of(page, size, sort)`.
- Pageable only defines offset/size, and sort is built separately: use `query.addSort(...)`.

## 8. Complete Example: CriteriaQuery + Sort + Pageable

Suppose we need active products in the `KEYBOARD` category priced from 100 to under 500; results sorted by newest creation date then ascending SKU, 20 products per page.

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> search(int page, int size) {
        Criteria criteria = new Criteria("status").is("ACTIVE")
                .and("category").is("KEYBOARD")
                .and("price").greaterThanEqual(new BigDecimal("100"))
                .and("price").lessThan(new BigDecimal("500"));

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")
        );

        Pageable pageable = PageRequest.of(page, size, sort);

        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(pageable);

        SearchHits<ProductDocument> hits =
                operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
```

In this example:

1. Criteria defines the document filter set.
2. Sort defines result ordering.
3. Pageable selects the page and page size.
4. `CriteriaQuery` passes all three to `ElasticsearchOperations`.
5. `SearchHits` holds the returned hits; `SearchHit::getContent` extracts the entity from each hit.

The `.toList()` method requires Java 16 or later. If your project uses an older Java version, replace it with `collect(Collectors.toList())`.

## 9. Reading Paginated Results from `SearchHits`

`ElasticsearchOperations.search(...)` returns `SearchHits<T>`, not directly `Page<T>`. `SearchHits` contains each hit's data, total hits per tracking configuration, execution time, aggregations, and other search metadata.

Example:

```java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

long totalHits = searchHits.getTotalHits();
List<ProductDocument> content = searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
```

`totalHits` is the hit count reported by Elasticsearch. Depending on `track_total_hits` configuration and the server's default threshold, total hits may be an exact count or a lower bound. If business rules require an exact total, configure tracking accordingly and weigh the performance cost.

### Converting to `SearchPage`

Spring Data Elasticsearch provides `SearchHitSupport.searchPageFor(...)` to create a `SearchPage` from `SearchHits` and `Pageable`:

```java
SearchPage<ProductDocument> searchPage =
        SearchHitSupport.searchPageFor(searchHits, pageable);

long total = searchPage.getTotalElements();
int number = searchPage.getNumber();
int size = searchPage.getSize();
List<SearchHit<ProductDocument>> pageHits = searchPage.getContent();

List<ProductDocument> products = pageHits.stream()
        .map(SearchHit::getContent)
        .toList();
```

`SearchPage` preserves pagination metadata alongside `SearchHit` objects; each `SearchHit` still contains the entity in `getContent()`, score, and other hit details. Import classes from `org.springframework.data.elasticsearch.core` per your library version.

If the application only needs the entity list and total hits, return a dedicated DTO instead of leaking `SearchHit` outside the repository/service layer.

## 10. Building Safe APIs Accepting page, size, and sort

Do not let clients pass arbitrary sort field names directly to Elasticsearch. Allowlist the permitted sort fields:

```java
public enum ProductSortField {
    CREATED_AT,
    PRICE,
    SKU
}
```

The service translates the choice into `Sort`:

```java
private Sort resolveSort(ProductSortField field, boolean descending) {
    Sort.Direction direction = descending
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    return switch (field) {
        case CREATED_AT -> Sort.by(direction, "createdAt");
        case PRICE -> Sort.by(direction, "price");
        case SKU -> Sort.by(direction, "sku");
    };
}
```

Allowlisting prevents accidentally sorting on unmapped/incompatible fields, overly expensive fields, or internal fields that the API should not expose. Also validate `page >= 0` and cap `size` per API policy.

When sorting on strings, clearly decide whether to sort by exact keyword or a normalized value. Sorting on `text` is usually inappropriate; use a `keyword` subfield or a dedicated sort field.

## 11. Multiple Sort Criteria and Precedence

Example:

```java
Sort sort = Sort.by(
        Sort.Order.desc("statusPriority"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);
```

Elasticsearch prioritizes `statusPriority` first. If two documents share the same priority, it compares `createdAt`; if still equal, it compares `sku`.

This ordering reflects business meaning. For instance, a listing page might want:

1. Prioritized products displayed first.
2. Within the same priority group, most recently updated products first.
3. With identical update timestamps, ascending SKU for deterministic ordering.

Sort fields should have clear mappings and appropriate values. If a field can be null/missing, decide how documents missing values should be handled and check Elasticsearch's null sort behavior.

## 12. Offset Pagination Has Limits

`Pageable` is typically translated into offset/limit pagination (`from`/`size`). This is simple for early pages, but the deeper you go, the more hits Elasticsearch must process and discard before the offset.

For example, page 500 with size 20 must skip 10,000 hits before returning the next 20 hits. Elasticsearch's default result window limit is typically 10,000 (`index.max_result_window`), so deep queries may be rejected if they exceed the threshold.

Do not arbitrarily raise `index.max_result_window` to support very deep pages. Increasing the limit can raise memory usage and processing cost on the cluster.

### When Deep Retrieval Is Needed: `search_after`

For streams iterating over many results, Elasticsearch recommends `search_after` combined with a stable sort. Instead of requesting page 500, the next request sends the sort values of the last hit from the previous page to retrieve subsequent documents.

Conceptual example:

```json
GET /products/_search
{
  "size": 100,
  "sort": [
    { "created_at": "desc" },
    { "sku": "asc" }
  ],
  "search_after": [
    "2026-11-13T10:15:00Z",
    "SKU-500"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Values in `search_after` must match the exact order and types of the sort fields on the previous page's last hit. For traversal requiring a consistent data view, combine with Point in Time (PIT) so pages read from the same search snapshot while valid.

`Pageable` with page numbers does not automatically turn into a `search_after` cursor. If deep pagination is needed, use the search-after/PIT API of the Elasticsearch Java API Client or the corresponding abstraction in your Spring Data version, rather than trying to force every case into `PageRequest`.

## 13. Sort and Pageable Can Impact Performance

Practical guidelines:

- Sort only on necessary fields; sorting can consume shard resources and memory.
- Prefer `keyword`, numeric, and date fields with appropriate doc values.
- Do not sort directly on `text` without supporting mappings.
- Use moderate page sizes; avoid returning thousands of documents for a single UI request.
- Use stable sorting with a unique tie-breaker when paging.
- Do not use offset pagination for very deep traversal flows.
- If you only need to check whether results exist, use a small page size rather than loading full data.
- If an exact total hit count is unnecessary, consider reducing total-hit tracking overhead per supported APIs and versions.

A query with highly selective Criteria can still be expensive if it sorts on an unsuitable field. Inspect mappings and benchmark with production-scale data.

## 14. Testing CriteriaQuery, Sort, and Pageable

Test each part individually and then in combination:

1. Criteria filters documents accurately per condition.
2. AND/OR groups match business requirements.
3. Sort uses the right ascending/descending directions and multi-field priority.
4. Page 0 and page 1 do not duplicate documents when data is stable.
5. Page size does not exceed service limits.
6. Sort fields have compatible mappings, especially with text/keyword.
7. Java property names and Elasticsearch field names map properly.
8. Total hits are interpreted correctly according to tracking mode.
9. Deep queries use a `search_after`/PIT strategy when needed.

Example integration test verifying order:

```java
@Test
void shouldReturnProductsSortedByCreatedAtDescending() {
    // Arrange: index products with different createdAt values.
    // Act: call service with page 0, size 10, and sort createdAt DESC.
    // Assert: the first element has the latest createdAt.
}
```

In tests that search immediately after indexing documents, refresh the index or use an appropriate refresh mechanism. Do not rely on `Thread.sleep` for test stability.

## 15. Common Pitfalls

| Symptom | Possible cause | How to fix |
|---|---|---|
| Results are not in expected order | Sort uses wrong property/field or incorrect mapping. | Check entity mapping and actual sort field. |
| Sorting on text throws error or uses excessive memory | `text` field lacks doc values for standard sorting. | Use a `keyword` multi-field or dedicated sort field. |
| Page 1 lacks expected data | Page index passed as 1-based instead of 0-based. | Use `PageRequest.of(0, size)` for the first page. |
| Two pages have duplicate or missing documents | Unstable sort when documents share sort values or data changes between requests. | Add a unique tie-breaker; consider PIT and `search_after`. |
| Deep page query rejected | Exceeded `index.max_result_window`. | Use cursor pagination/`search_after` instead of raising the limit arbitrarily. |
| Sort does not apply as expected | Sort declared on both `Pageable` and query, or API uses a different sort source. | Pick one place to define sort and inspect the request. |
| Total hits differs from actual document count | Total-hit tracking has a threshold or relation is a lower bound. | Configure exact tracking when truly needed and assess cost. |
| Query method behaves differently from CriteriaQuery | Derived queries and the Criteria API have distinct representations. | Check actual Query DSL and test on the exact version. |

## 16. Design Rules

- Use `Criteria` for filter conditions and `CriteriaQuery` to assemble the query.
- Use `Sort` for ordering; the first order has highest priority.
- Use `PageRequest.of(page, size)` with zero-based page indices.
- Put sort inside `Pageable` when sorting is part of the pagination API; or add sort separately to the query, avoiding ambiguous dual sort sources.
- Use fields with suitable mappings for sorting; prefer keyword, numeric, and date.
- With Spring Data mappings, reference Java properties when the API accepts domain properties; with raw Query DSL/native requests, use Elasticsearch field names.
- Add a unique tie-breaker for stable pagination; do not default to sorting by `_id`.
- Understand that `SearchHits` is not `Page<T>`; convert to `SearchPage` when pagination metadata is needed or build a custom response DTO.
- Consider total-hit tracking if exact totals are required.
- Use `search_after` and PIT for deep pagination or large traversal flows.

## 17. Key Takeaways

- `CriteriaQuery` combines Criteria conditions with query options such as sort and pageable.
- `Sort` defines ordering across one or more fields; earlier orders take precedence.
- `Pageable` defines page and size, and can also carry Sort.
- `PageRequest` uses zero-based page indices.
- `ElasticsearchOperations.search` returns `SearchHits`; use `SearchHitSupport.searchPageFor` to build a `SearchPage` when needed.
- Sorting on `text` fields is usually inappropriate; use a `keyword` subfield or dedicated sort field.
- Use a unique tie-breaker to reduce duplicate/skipped documents across pages.
- Offset pagination has limits and rising cost on deep pages; use `search_after`/PIT when traversing many results.
- Inspect mappings, property/field names, and actual requests when sorting or pagination misbehaves.

Combining `CriteriaQuery`, `Sort`, and `Pageable` properly keeps Spring Data Elasticsearch queries clear, ordered, and easy to integrate into listing APIs. Design filter conditions, stable sorting, and pagination limits together; and choose a cursor strategy when large result counts outgrow offset pagination.
