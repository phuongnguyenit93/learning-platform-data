# Configuring Sort, Pagination, and Result Limits

`NativeQuery` lets you build Elasticsearch Query DSL using the Elasticsearch Java API Client while integrating Spring Data Elasticsearch options such as sort and pageable. When a query returns many documents, three essential tasks are determining the result order, limiting the number of hits fetched, and choosing how to page through the data.

Sort determines display order. Pagination specifies the position and size of a page. Result limit controls how many documents are returned in a single search request. These choices affect user experience, cluster load, application memory, and result stability when data changes.

## 1. Roles of Sort, Pagination, and Limit

### 1.1. Sort Determines Result Order

When no sort is specified, Elasticsearch typically ranks results by relevance score when the query computes scores. For non-scoring queries or certain other contexts, the default order should not be treated as a stable business order.

A product listing screen might need sorting by ascending price, newest creation date, or alphabetical name. Those requirements must be declared explicitly.

### 1.2. Pagination Splits Results into Pages

Instead of returning all matching documents, the application requests a slice of the results:

- Page 0: the first set of results.
- Page 1: the next group of results.
- Page 2: the following group of results.

Spring Data uses `Pageable` to represent page number, page size, and optionally sort. Page indices start at 0.

### 1.3. Limit Caps Hits in a Single Request

Limit is the maximum number of documents a single search call should return. In standard Spring Data usage, this limit is represented by the `Pageable` size.

For example, `PageRequest.of(0, 20)` requests the first page with at most 20 hits. This does not mean the entire query only has 20 matches; the query may still match thousands of documents.

| Concept | Question Answered | Example |
|---|---|---|
| Sort | Which results come first? | Lowest price first |
| Pagination | Which slice of the result set is being fetched? | Page 2 |
| Limit/page size | How many hits at most per request? | 20 hits |
| Total hits | How many documents match in total? | 1,250 hits |

## 2. Creating a Basic NativeQuery

### 2.1. Initializing a Query with Query DSL

`NativeQuery` is a good choice when you need Elasticsearch queries such as match, term, bool, range, nested, function score, or other DSL components.

Example searching products by name:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .build();
~~~

This query finds documents whose content matches the phrase according to the `name` field's analyzer. At execution time, pass the query and entity class to `ElasticsearchOperations`:

~~~java
SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

### 2.2. Field Names in NativeQuery

Query DSL operates on field names in the Elasticsearch mapping. If the Java entity declares:

~~~java
@Field(name = "product_name", type = FieldType.Text)
private String name;
~~~

then in NativeQuery, the field usually must be written as `product_name`:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("product_name")
        .query("wireless keyboard")
    ))
    .build();
~~~

Do not assume every string passed into NativeQuery is automatically translated by Spring from the Java property name to the mapping field name. Use the actual field name and check the index mapping.

### 2.3. Separating Query Conditions from Display Options

Query conditions answer which documents match. Sort, page, and limit determine how those matching documents are retrieved.

For example, the exact same product search condition can be used for:

- First page sorted by ascending price.
- First page sorted by newest products.
- Next page with the same ordering.
- A suggestions list needing only 5 results.

Separating condition building from display configuration helps reuse queries and prevents different screens from accidentally having inconsistent search conditions.

## 3. Sorting Results with Sort

### 3.1. Ascending and Descending Sort

Spring Data Elasticsearch supports Spring Data's `Sort` type. You can place sort directly inside `Pageable`:

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "price");

Pageable pageable = PageRequest.of(0, 20, sort);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(pageable)
    .build();
~~~

In this example, results are sorted by `price` ascending. To put higher prices first:

~~~java
Sort sort = Sort.by(Sort.Direction.DESC, "price");
~~~

Then execute using `operations.search(query, ProductDocument.class)`.

You can read content and scores from the results:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();
    System.out.println(product.getPrice());
}
~~~

### 3.2. Declaring Multiple Sort Criteria

When multiple documents share the same price, a second criterion can determine order:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.asc("name")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Elasticsearch applies sorting in the declared order:

1. Compare price ascending.
2. If prices are equal, compare name ascending.

For queries with relevance scores, if you need to prioritize relevance first and then use a field as a tie-breaker, declare the sort order to match that intent. When specifying an explicit field sort, do not assume score automatically remains the first criterion.

### 3.3. Using Sort Standalone in NativeQuery

Some versions of Spring Data Elasticsearch allow setting sort directly on the NativeQuery builder:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withSort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("productId")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

If sort is already passed in `Pageable`, do not repeat the same sort on the builder. Pick one place as the single source of ordering configuration to avoid ambiguity or conflicts. Builder signatures can vary across Spring Data Elasticsearch versions; check your dependencies if the IDE does not recognize an overload.

### 3.4. Choosing Suitable Fields for Sorting

Not every field can be sorted efficiently.

| Field Type | Typical Sort Support | Notes |
|---|---|---|
| number | Yes | Suitable for price, quantity, score |
| date | Yes | Suitable for created/updated timestamps |
| keyword | Yes | Suitable for codes, statuses, normalized names |
| boolean | Yes | Can be used when business logic requires |
| text | Usually unsuitable by default | Field is analyzed; needs a keyword subfield or separate sort field |
| object/nested | Requires specific config | Sorting may require a nested sort path |

Entity example with multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

The `name` field is used for full-text search, while `name.keyword` is better suited for exact sorting. When using query DSL directly, you can specify the exact subfield name in the sort option. If using Spring `Sort`, confirm how your library version maps property paths to mapping fields; do not assume every subfield is inferred automatically.

### 3.5. Why Shouldn't text Fields Be Sorted Directly?

`text` fields are split into tokens by an analyzer. Elasticsearch does not store doc values for text fields in the way normally used for sorting. Enabling fielddata on text can consume significant heap and cause memory pressure.

For names or labels requiring both full-text search and sorting, multi-field is commonly used:

- `name` as text for match queries.
- `name.keyword` as keyword for sorting or exact matching.

For data sorted frequently, design a dedicated field from the start rather than enabling fielddata just to work around a sort error.

### 3.6. Sorting by Date and Number

Example sorting newest products first:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt")
);
~~~

Example sorting by ascending price, then descending stock quantity:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.desc("stockQuantity")
);
~~~

Date fields must have an appropriate date mapping. Numeric fields need numeric mappings rather than keywords storing numeric strings; if numbers are stored as strings, lexicographical order can differ from numeric order—for example, `"100"` can sort before `"20"` in string comparison.

## 4. Advanced Sorting in Elasticsearch Query DSL

### 4.1. Native Sort Options

Spring Data `Sort` covers common needs. When you need Elasticsearch-specific options like missing values, mode, nested sort, or unmapped types, you can use native sort options from the Elasticsearch Java API Client via the NativeQuery builder.

Conceptual example of a sort option:

~~~java
SortOptions priceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("price")
        .order(SortOrder.Asc)
        .missing("_last")
    )
);
~~~

Then pass the sort option into NativeQuery using the `withSort` overload matching your Elasticsearch Java API Client version:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withSort(priceSort)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Exact package/import names and overloads depend on the client version. Keep the configuration intent consistent: `price` ascending, documents missing price placed at the end of the list.

### 4.2. Handling Missing Fields

Some documents may lack the field being sorted on. Elasticsearch provides a missing option to place those documents at the beginning or end:

- `_first`: puts missing values first.
- `_last`: puts missing values last.
- Specific value: uses a fallback value as supported by the query option.

If sorting by creation date where legacy data lacks `createdAt`, decide where those documents should appear instead of letting default behavior make the order unpredictable.

### 4.3. Nested Sort

When sorting by a field inside a nested object, you must declare the nested path and the rule for picking a value among nested elements. For example, a product has multiple offers and you want to sort by the lowest offer price.

This is a case requiring native sort options, because passing a simple property name is usually insufficient to describe a nested sort. The field mapping must be `nested`; if it is merely `object`, query and sort semantics differ.

### 4.4. Sorting by Score

Relevance score is usually appropriate when users search content. If you need to prioritize high-scoring results, you can sort by `_score` descending and add a stable field as a secondary criterion.

Do not use price or name as the first criterion if the main goal is relevance ranking. Conversely, for a product category screen without a full-text query, sorting by business fields usually makes more sense.

### 4.5. Stable Sorting with Tie-Breakers

If multiple documents share the same price or timestamp, their relative order can shift between requests unless there is a unique secondary criterion.

Example:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.asc("productId")
);
~~~

`productId` should be a keyword field with unique values that supports sorting. This keeps result ordering deterministic when paging through results.

Do not rely on Elasticsearch's `_id` as a general-purpose sort field by default. Store a unique business field with doc values if you need a stable tie-breaker.

## 5. Pagination with Pageable

### 5.1. PageRequest

`PageRequest` is the standard implementation of `Pageable`:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Parameters:

- The first parameter is page number, starting from 0.
- The second parameter is page size, the maximum number of items per page.

Example:

~~~java
Pageable firstPage = PageRequest.of(0, 20);
Pageable secondPage = PageRequest.of(1, 20);
Pageable thirdPage = PageRequest.of(2, 20);
~~~

With page size 20, the corresponding offsets are 0, 20, and 40. Spring Data translates pageable details into `from/size` in the search request according to the API in use.

### 5.2. Combining Pageable and Sort

You can pass sort right when creating PageRequest:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"))
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(pageable)
    .build();
~~~

This is concise when sorting and pagination belong to the same display requirement. If complex sorting requires native options, configure sort using the corresponding Elasticsearch API and use Pageable solely for page/size.

### 5.3. Creating Pageable from API Parameters

Suppose a controller receives page and size from a request. Do not pass arbitrary client values directly into PageRequest.

~~~java
public Pageable createPageable(int page, int size) {
    int safePage = Math.max(page, 0);
    int safeSize = Math.min(Math.max(size, 1), 100);

    return PageRequest.of(
        safePage,
        safeSize,
        Sort.by(Sort.Order.desc("createdAt"))
    );
}
~~~

This code guarantees page is non-negative and size stays within 1–100. Specific bounds should be based on document size and cluster load. Public search APIs typically need a size cap so a single request cannot ask for thousands of documents.

### 5.4. Reading Paginated Results

Execute the query:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(query, ProductDocument.class);
~~~

If you need Spring Data's page structure:

~~~java
SearchPage<ProductDocument> searchPage =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

You can extract details such as:

~~~java
List<SearchHit<ProductDocument>> content =
    searchPage.getContent().getSearchHits();

long totalHits = searchPage.getTotalElements();
int pageNumber = searchPage.getNumber();
int pageSize = searchPage.getSize();
int totalPages = searchPage.getTotalPages();
boolean hasNext = searchPage.hasNext();
~~~

Exact method names on `SearchPage`/`SearchHits` may differ by version. If you only need the data, you can read `searchHits.getSearchHits()` and map `SearchHit::getContent`.

### 5.5. Distinguishing Page, SearchHits, and SearchPage

| Type | Contents |
|---|---|
| `SearchHit<T>` | One document plus hit metadata |
| `SearchHits<T>` | Hit list and overall response metadata |
| `SearchPage<T>` | SearchHit content combined with pagination metadata |
| `Page<T>` | Standard Spring Data page abstraction |

`SearchHits` is helpful when you need score, ID, highlights, or sort values. `SearchPage` preserves that metadata while also offering page metadata. `Page` usually suits application APIs that only need content and totals.

Do not strip metadata too early if the UI needs relevance scores or highlights.

## 6. Limiting Results via Page Size

### 6.1. Fetching the First N Results

If you only need 5 suggestions, create a first page with size 5:

~~~java
Pageable topFive = PageRequest.of(0, 5);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless")
    ))
    .withPageable(topFive)
    .build();
~~~

This limits how many hits the request returns. Elasticsearch still evaluates the query across matching data to determine the top results by sort/relevance.

### 6.2. Limit Is Not Total Hits

Suppose a query matches 3,000 documents, while page size is 10:

- The current response contains at most 10 hits.
- Total hits can be 3,000 if total-hit tracking provides the full count.
- Remaining documents are retrieved on subsequent pages.

Do not treat the returned list's size as the total match count. Conversely, do not load all 3,000 documents just to display the total count.

### 6.3. Fetching Only One Hit to Check Existence

If you only need to know whether a query has any matches, do not fetch a large page:

~~~java
Pageable oneResult = PageRequest.of(0, 1);

Query query = NativeQuery.builder()
    .withQuery(q -> q.term(t -> t
        .field("category")
        .value("ACCESSORY")
    ))
    .withPageable(oneResult)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);

boolean hasAny = !hits.getSearchHits().isEmpty();
~~~

If you only need an exact count or an existence check by condition, you can use the count API instead of search; this avoids loading source documents.

### 6.4. Avoid Unbounded Results for Regular Screens

`Pageable.unpaged()` or queries with no page size limit can cause the application to pull excessive data. On large indices, this increases memory usage, serialization time, and network load.

Enforce default and maximum page sizes at the service layer. For full data export tasks, use a dedicated batch traversal mechanism instead of removing limits in a single search request.

## 7. from/size Limits and Deep Pagination

### 7.1. The from/size Mechanism

Traditional Elasticsearch pagination uses two values:

- `from`: number of hits to skip before returning results.
- `size`: maximum number of hits to return.

For example, page 3 with size 20 has offset 60 and size 20. Each shard may need to hold and process intermediate results so the coordinator can merge global ordering.

As offsets grow large, memory and processing costs increase accordingly. For this reason Elasticsearch enforces a result window limit; a common default is 10,000 hits for `from + size`.

### 7.2. Do Not Increase max_result_window Arbitrarily

`index.max_result_window` can be changed at the index level, but raising the limit does not make deep pagination cheap. It can cause each request to consume more resources and put pressure on heap and the cluster.

Before raising the limit, verify:

- Do users genuinely need to jump to very deep pages?
- Can results be narrowed with stricter filters?
- Can you sort by a stable criterion and use `search_after`?
- Can you use an export/batch API instead of UI pagination?

For user-facing screens, it is usually better to cap page numbers or encourage more specific filtering.

### 7.3. Using search_after for Large Datasets

`search_after` lets you continue searching after the sort values of the last hit on the previous page. This avoids large offsets and suits sequential traversal flows.

Elasticsearch request example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 100,
  "sort": [
    { "createdAt": "asc" },
    { "productId": "asc" }
  ],
  "query": {
    "match_all": {}
  },
  "search_after": [
    "2026-01-15T10:00:00Z",
    "P1001"
  ]
}
~~~

Values in `search_after` must come from the sort values of the last hit on the previous page, in the exact order of the sort fields. Do not compute or guess the cursor from application data.

Sort must define a stable order. If two documents share the same sort values without a unique tie-breaker, results may be skipped or duplicated across pages.

### 7.4. Point-in-Time to Maintain a Stable View

If data changes while the application traverses multiple pages, the result set can shift between requests. Point-in-time (PIT) keeps a consistent view over a period of time.

Conceptual flow:

1. Open a PIT for the target index/alias.
2. Send the first search with the PIT and a stable sort.
3. Capture the sort values from the last hit.
4. Send the next page using the same PIT and `search_after`.
5. Continue until all results are exhausted.
6. Close the PIT when finished or let it expire per the retention policy.

PIT consumes resources and requires a reasonable keep-alive. Do not open a PIT and keep it indefinitely. Handle PIT expiration and recreate the search session according to your application strategy.

### 7.5. Search After and NativeQuery

Spring Data Elasticsearch versions supporting query cursors may provide APIs to attach search-after values to NativeQuery. Exact method names and value types depend on the version. When using it, make sure to:

- Keep sort options identical between pages.
- Pass the exact sort values from the last hit of the previous page.
- Keep the same query conditions.
- Use PIT when a stable snapshot is required.
- Avoid mixing offset pagination and cursor pagination in the same flow without a clear design.

If your project's library version abstraction does not yet fully support PIT/`search_after`, you can use the Elasticsearch Java API Client directly for deep data traversal.

## 8. Relevance Score and Business Sorting

### 8.1. Default Sorting by Relevance

With a match query, Elasticsearch typically uses the relevance score to rank results. Better-matching documents generally receive higher scores, depending on the algorithm and configuration.

If you add sorting by price, the order may switch to price first instead of relevance. This is a change in product semantics, not just a technical optimization.

### 8.2. Combining Score with Fields

If you want to prioritize relevance and then use price as a tie-breaker, configure the sort order accordingly. With native sort options, you can sort by `_score` descending and then by business fields.

DSL example:

~~~json
{
  "sort": [
    { "_score": "desc" },
    { "price": "asc" },
    { "productId": "asc" }
  ]
}
~~~

If the requirement is cheapest products first regardless of relevance, sort by price. If the requirement is most relevant results first, keep score in the primary position. Align this behavior with UX and test with representative queries.

### 8.3. Sorting by Computed Values

Some applications need to sort by script values or formulas combining multiple fields. Elasticsearch supports script sorting, though this can be expensive and requires careful script control.

Before using script sorting, evaluate whether the field can be precomputed when writing the document. A pre-stored field is usually easier to sort and faster than computing on every hit.

## 9. Sorting, Pagination, and Multi-Index

### 9.1. Sorting Across Multiple Indices

When searching across an alias or multiple indices, sort fields must have compatible mappings. If an older index declares `price` as keyword while a newer index declares it numeric, sorting may fail or produce unexpected ordering.

During versioned schema migrations, unify field types or configure an appropriate unmapped type if a field is missing in one index. Never assume identical field names mean identical mappings.

### 9.2. Fields Missing in Some Indices

An alias can point to multiple indices with different schemas. If a sort field does not exist in one index, decide how to handle missing/unmapped fields via the appropriate query option.

The sustainable solution is keeping mappings compatible across indices targeted by the same query. Use unmapped types only when you clearly understand the data and sort type.

### 9.3. Sort and Refresh

When new documents are indexed or sort fields updated, search results reflect changes after refresh. If a user paginates while data is changing, ordering and positions can shift.

For standard UIs, this is usually acceptable. For exports or sequential processing requiring consistency, using PIT with `search_after` is more suitable.

## 10. Complete Service Example

### 10.1. Building a Query with Sort and Pagination

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchPage<ProductDocument> search(
            String keyword,
            int requestedPage,
            int requestedSize) {

        int page = Math.max(requestedPage, 0);
        int size = Math.min(Math.max(requestedSize, 1), 50);

        Sort sort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("productId")
        );

        Pageable pageable = PageRequest.of(page, size, sort);

        Query query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                    .field("name")
                    .query(keyword)
                ))
                .filter(f -> f.term(t -> t
                    .field("available")
                    .value(true)
                ))
            ))
            .withPageable(pageable)
            .build();

        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        return SearchHitSupport.searchPageFor(hits, pageable);
    }
}
~~~

This example illustrates the overall flow. The entity must have `createdAt` and `productId` mapped to sortable types. If Elasticsearch uses different field names, adjust the sort fields to match the actual mapping and your version's converter behavior.

### 10.2. Mapping Results to DTOs

~~~java
public record ProductResult(
    String id,
    String name,
    float score
) {
}

public record ProductPageResponse(
    List<ProductResult> items,
    long totalHits,
    int page,
    int size,
    int totalPages
) {
}
~~~

Conversion:

~~~java
public ProductPageResponse toResponse(
        SearchPage<ProductDocument> searchPage) {

    List<ProductResult> items = searchPage.getContent()
        .getSearchHits()
        .stream()
        .map(hit -> new ProductResult(
            hit.getId(),
            hit.getContent().getName(),
            hit.getScore()
        ))
        .toList();

    return new ProductPageResponse(
        items,
        searchPage.getTotalElements(),
        searchPage.getNumber(),
        searchPage.getSize(),
        searchPage.getTotalPages()
    );
}
~~~

DTOs prevent controllers from depending directly on Spring Data's internal result types. If only content is needed, you can omit score from the DTO.

### 10.3. Endpoints Must Enforce Page Size Limits

When receiving parameters from clients, the service should enforce an upper bound as shown above. Controllers can also validate inputs to return 400 when page/size is invalid rather than silently clamping values. This choice depends on your API contract; the key rule is never letting clients request an arbitrary number of results.

## 11. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Sorting by name throws an error or consumes heap | Field is `text` without suitable doc values | Use a keyword subfield or a dedicated sort field |
| Numeric sort yields wrong order | Values stored as keyword/string | Change mapping to numeric and reindex when needed |
| Next page duplicates or skips documents | Unstable sort order with duplicate values | Add a unique tie-breaker |
| Cannot fetch deep pages | Exceeds `index.max_result_window` | Use `search_after`/PIT or cap page depth |
| Large page size causes slowness | Request loads too many documents/sources | Reduce limit, use source filtering, or batch |
| Total hits differs from hits in page | Total hits is the overall match count; the list is one page | Use total metadata and page content properly |
| Results shift order across pages | Data changes or unstable sort | Add a tie-breaker; use PIT if a snapshot is needed |
| Sorting by nested field behaves wrongly | Missing nested path or nested sort mode | Use native sort options and nested mapping |
| Alias across multiple indices causes sort error | Incompatible field mappings | Align schemas or intentionally configure unmapped type |
| Score is no longer prioritized | Business sort placed ahead of `_score` | Review sort order against relevance requirements |
| Search rejected due to heavy query | Script sort or expensive query blocked by cluster policy | Measure load and consider precomputing the sort field |

When debugging, inspect the final request DSL and actual mapping on the cluster. Do not look solely at the Java `Pageable` object and assume Elasticsearch received the expected sort/offset/size.

## 12. Testing Sort, Pagination, and Limit

### 12.1. Create Data with Duplicate Values

To verify sorting, include multiple documents with the same price or timestamp. If all sample data has distinct values, tests will not catch tie-breaker issues.

Example:

| ID | Price | Created Date |
|---|---:|---|
| P1001 | 49.90 | 2026-01-10 |
| P1002 | 49.90 | 2026-01-10 |
| P1003 | 29.90 | 2026-01-12 |
| P1004 | 79.90 | 2026-01-09 |

Verify ascending price and ascending `productId` when prices are equal.

### 12.2. Verify Result Limits

With page size 2, verify:

- The first page has at most 2 hits.
- The next page contains the next IDs under the same sort.
- No IDs repeat across pages on an unchanged dataset.
- Total hits is not confused with the current page's item count.

### 12.3. Test Sort Fields

Test sorting on:

- Numeric fields.
- Date fields.
- Keyword fields.
- Text fields and their keyword subfields.
- Missing fields.
- Nested fields if used by the application.

Tests should run against a compatible Elasticsearch instance to verify real mappings and queries. Mocking `ElasticsearchOperations` only checks how the service calls the API; it does not prove sorting works on the cluster.

### 12.4. Test Deep Pagination

If the application uses `search_after`, verify:

1. The first page reads sort values from the last hit.
2. The next page passes those exact sort values.
3. Query and sort stay unchanged between pages.
4. Cursor expiration is handled.
5. PIT is closed or expires as planned.
6. No documents are duplicated or skipped on a stable dataset.

## 13. Workflow for Choosing a Pagination Strategy

Choose a strategy based on scale and the user experience required:

| Scenario | Approach |
|---|---|
| Short list, a few pages | `Pageable` with `from/size` |
| First page / autocomplete | Small page size, appropriate sort |
| User needs total page count | `SearchPage`/`Page` or tracked total hits |
| Exact total is not needed | Fetch only content and next-page indicator if supported |
| Traversing very large datasets | `search_after` and stable sort |
| Export needing a consistent view | PIT combined with `search_after` |
| Special sorting needs | Native sort options |
| Content search needing relevance | Keep sorting by score or combine score with tie-breaker |

Do not force one mechanism for every case. `Pageable` is simple and easy to integrate with UIs, while `search_after` is better suited for sequential traversal over large datasets.

## 14. Key Takeaways

- `NativeQuery` lets you combine Query DSL with Spring Data's sort and pagination options.
- `Sort` describes ordering on one or more fields; criterion order defines priority.
- Sort fields need compatible mappings: numeric, date, and keyword usually work well; text usually requires a keyword subfield.
- `Pageable` represents page number, page size, and optionally sort.
- Page indices start at 0; page size is the maximum hits for the current page.
- Limit is not the total number of documents matching the query.
- Sorting needs a stable tie-breaker when primary values can collide.
- `from/size` fits shallow pagination; deep pagination should consider `search_after` and PIT.
- Do not arbitrarily raise `max_result_window` or page sizes to handle large datasets.
- Always verify Query DSL, mappings, and behavior against a real Elasticsearch instance or test container.
- Builder/native sort signatures can change across Spring Data Elasticsearch and Elasticsearch Java API Client versions; check project dependencies before applying.

When sort, pagination, and limits are configured properly, the application can return results in business order, keep response sizes bounded, and traverse large datasets in a way suited to Elasticsearch's capabilities.
