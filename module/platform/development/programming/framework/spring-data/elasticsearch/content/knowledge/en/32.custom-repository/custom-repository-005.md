# Encapsulating Complex Search While Preserving Result Metadata

When an application uses Spring Data Elasticsearch, simple queries can be declared via repository methods. However, real-world search often needs to combine multiple conditions, pagination, sorting, highlighting, aggregations, inner hits, or other business rules. Putting all of that logic into a service makes the business layer overly aware of Elasticsearch details. On the other hand, returning only a list of entities can cause the application to lose the metadata Elasticsearch computed for each hit and for the overall search response.

A custom repository solves both problems at once:

- Encapsulates complex query construction inside a component with a clear responsibility.
- Returns a result type that preserves search metadata—typically `SearchHits<T>` or `SearchPage<T>`—instead of returning only `List<T>` or `Page<T>`.

The key is distinguishing entity content from the search information surrounding it. A single hit can carry the entity, ID, score, sort values, highlight fields, and inner hits. The overall response also includes total hits, whether the total hit count is exact or a lower bound, max score, aggregations, suggestions, or scroll information. When you extract only the content, that metadata is lost from the return type.

## 1. Why Do You Need a Custom Repository?

Declared repository methods work well for stable, simple queries:

~~~java
List<Product> findByStatus(String status);
Page<Product> findByCategory(String category, Pageable pageable);
~~~

When a query involves many dynamic conditions, multiple Query DSL types, and result metadata, derived method names become hard to read. Having a service build NativeQuery directly also scatters search logic across the codebase.

For example, a product search page might require:

- Keyword matching across name and description.
- Filtering by status, category, brand, and price range.
- Sorting by relevance or creation time.
- Pagination.
- Highlighting matched text snippets.
- Returning scores and sort values for each hit.
- Returning total hit counts and category aggregations.

This is an ideal use case for a custom repository fragment. The fragment receives search criteria, builds the query, calls `ElasticsearchOperations`, and returns a result type that preserves full metadata.

## 2. Distinguishing Entity Content from SearchHit

`Product` is the business data mapped from `_source`. `SearchHit<Product>` is a specific search hit containing both the content and metadata for that hit.

A hit can provide:

| Metadata | Meaning |
|---|---|
| `id` | Document ID |
| `index` | Index containing the document |
| `score` | Relevance score calculated by Elasticsearch |
| `sortValues` | Sort values for the hit, useful for sort-based / search_after pagination |
| `highlightFields` | Highlighted text snippets keyed by field |
| `innerHits` | Child hits from nested or parent-child queries |
| `content` | Entity mapped from the document source |

Conceptual example:

~~~text
SearchHit<Product>
    |
    +-- id: product-42
    +-- score: 8.7
    +-- sortValues: [8.7, "product-42"]
    +-- highlightFields:
    |      name -> ["Mechanical <em>Keyboard</em>"]
    +-- innerHits: ...
    +-- content: Product(...)
~~~

If you call `hit.getContent()` and return only `Product`, the application still gets the entity, but loses the score, highlights, sort values, and inner hits attached to that hit.

## 3. Metadata at the Whole SearchHits Level

`SearchHits<T>` is the container for the entire search result. In addition to the list of `SearchHit<T>`, it holds response-level metadata:

| Metadata | Meaning |
|---|---|
| `totalHits` | Total number of matching documents reported by Elasticsearch |
| `totalHitsRelation` | Indicates whether the total hit count is exact or a lower bound |
| `maxScore` | Highest score in the result set |
| `aggregations` | Aggregation results |
| `suggest` | Suggestion results if the query used suggesters |
| `scrollId` | Scroll context ID if the response comes from a scroll flow |

Do not always interpret totalHits as an exact count. Elasticsearch can return a relation of `EQUAL_TO` or `GREATER_THAN_OR_EQUAL_TO`, depending on how total hits are tracked and how the query is configured. The UI or API should preserve this relation when making pagination or display decisions based on count accuracy.

Example of reading results:

~~~java
SearchHits<Product> searchHits =
        operations.search(query, Product.class);

long totalHits = searchHits.getTotalHits();
float maxScore = searchHits.getMaxScore();

for (SearchHit<Product> hit : searchHits.getSearchHits()) {
    Product product = hit.getContent();
    float score = hit.getScore();
    Map<String, List<String>> highlights = hit.getHighlightFields();
}
~~~

Specific metadata getters depend on the Spring Data Elasticsearch version, but the principle is to keep `SearchHits` or `SearchHit` until the application layer decides which metadata to expose.

## 4. How Do SearchHits, SearchHit, SearchPage, and Page Differ?

| Result type | Contents | Per-hit metadata | Overall search metadata | Pagination |
|---|---|---|---|---|
| `List<T>` | Entities | No | No | Does not carry page info itself |
| `Page<T>` | Entities | No | Mainly total count and page metadata | Yes |
| `SearchHits<T>` | `SearchHit<T>` | Yes | Yes | Follows query/pageable if configured |
| `SearchPage<T>` | `SearchHit<T>` within a page | Yes | Keeps link to `SearchHits` | Yes |

`Page<T>` fits if callers only need entities and basic pagination metadata. `SearchPage<T>` fits when callers need a page while still keeping score, highlights, sort values, or inner hits on each hit.

Example:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);
SearchPage<Product> searchPage =
        SearchHitSupport.searchPageFor(hits, pageable);
~~~

`SearchPage<Product>` is a page of `SearchHit<Product>` entries, so each element retains its search metadata. If you convert it into `Page<Product>` by extracting only each hit's content, per-hit metadata is discarded.

## 5. Designing Criteria Instead of Passing Query from the Controller

Controllers should accept business criteria rather than Elasticsearch Query DSL directly. Create a criteria object describing the conditions users are allowed to choose:

~~~java
public record ProductSearchCriteria(
        String keyword,
        String status,
        String category,
        String brand,
        Double minPrice,
        Double maxPrice
) {
}
~~~

The criteria object preserves business intent. The repository fragment translates criteria into Query DSL, validates conditions, and restricts which fields may be sorted or filtered.

Never let clients pass arbitrary field names to concatenate directly into queries. For dynamic sorting, use an enum or allowlist:

~~~java
public enum ProductSortField {
    RELEVANCE,
    CREATED_AT,
    PRICE
}
~~~

Services or controllers can accept `ProductSortField`, and the repository maps it to the corresponding `Sort`. This prevents clients from requesting sorts on internal or unindexed fields.

## 6. Custom Repository Fragment

Spring Data supports composing repositories from multiple fragments. One fragment can declare custom search behavior while the main repository continues to extend `ElasticsearchRepository`.

Fragment interface:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchPage;

public interface ProductSearchOperations {

    SearchPage<Product> searchProducts(
            ProductSearchCriteria criteria,
            Pageable pageable
    );
}
~~~

Main repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchOperations {
}
~~~

Fragment implementation:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchOperationsImpl
        implements ProductSearchOperations {

    private final ElasticsearchOperations operations;

    public ProductSearchOperationsImpl(
            ElasticsearchOperations operations
    ) {
        this.operations = operations;
    }

    @Override
    public SearchPage<Product> searchProducts(
            ProductSearchCriteria criteria,
            Pageable pageable
    ) {
        // Build query and preserve SearchHits metadata.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

The implementation name must follow the repository fragment discovery mechanism in your Spring Data version. The common convention is the fragment interface name plus the `Impl` suffix. If the application uses custom repository base package or bean naming configuration, verify that Spring Data detects the fragment implementation.

Benefits of fragments:

- The main repository retains standard CRUD operations.
- Complex search logic has a dedicated interface for testing.
- Additional fragments can be added without bloating the repository.
- Services invoke a business-meaningful method rather than knowing Query DSL details.

## 7. Building NativeQuery Inside a Fragment

`NativeQuery` fits when you need Elasticsearch DSL capabilities that simpler query abstractions cannot fully express. You can combine bool, match, term, range, sort, pageable, highlight, and aggregations.

Example query with a keyword and status filter:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(match -> match
                        .field("name")
                        .query(criteria.keyword())
                ))
                .filter(f -> f.term(term -> term
                        .field("status")
                        .value("ACTIVE")
                ))
        ))
        .withPageable(pageable)
        .withSort(Sort.by(Sort.Order.desc("createdAt")))
        .build();
~~~

This is an abbreviated example demonstrating how to combine query, filter, sort, and pageable with Elasticsearch Java Client builders. In a real implementation, only add must when the keyword has a value and only add each filter when the corresponding criterion is present. Never send a match condition with a null or empty string.

### 7.1. Extracting a Query-Building Helper

When there are many dynamic conditions, separate query construction from execution:

~~~java
private NativeQuery buildQuery(
        ProductSearchCriteria criteria,
        Pageable pageable
) {
    // Validate criteria.
    // Build bool query from non-empty conditions.
    // Add pageable, sort, highlight and aggregations.
    // Return a NativeQuery.
}
~~~

This method can be unit tested to check query-building branches or verified through integration tests against Elasticsearch. Avoid writing a repository method that validates requests, builds DSL, calls the client, and maps responses into multiple DTOs all inside one long block of code.

### 7.2. Combining must and filter

In a bool query:

- `must` is typically used for full-text conditions that contribute to relevance scoring.
- `filter` is used for mandatory conditions that do not need scoring, such as status, tenant, category, or price range.
- `must_not` excludes matching documents.
- `should` adds relevance-boosting conditions or optional clauses governed by minimum_should_match.

Putting each condition in the right clause keeps scores meaningful and queries efficient. Security or tenant-scoping filters must always be applied server-side regardless of whether the client supplied a filter.

## 8. Preserving Metadata When Executing the Query

After building the query, invoke `ElasticsearchOperations.search` and retain `SearchHits`:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

return SearchHitSupport.searchPageFor(hits, pageable);
~~~

Full structural implementation example:

~~~java
@Override
public SearchPage<Product> searchProducts(
        ProductSearchCriteria criteria,
        Pageable pageable
) {
    NativeQuery query = buildQuery(criteria, pageable);

    SearchHits<Product> hits =
            operations.search(query, Product.class);

    return SearchHitSupport.searchPageFor(hits, pageable);
}
~~~

`SearchHitSupport.searchPageFor` creates a `SearchPage` from `SearchHits` and `Pageable`. The result preserves each `SearchHit<Product>` so callers can still access both content and hit metadata.

If search-wide metadata such as aggregations, suggestions, or scroll IDs are needed, retain `SearchHits` or expose them through an appropriate response envelope. Do not immediately flatten to an entity list and discard the outer container.

## 9. Highlights and Inner Hits

### 9.1. Highlights

Highlighting helps the UI display text snippets that matched the query. Elasticsearch returns highlights per field inside each hit's metadata without modifying the original field values on the entity.

DSL example:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {},
      "description": {}
    }
  }
}
~~~

Highlight results can be read from `SearchHit.getHighlightFields()`. This returns a map from field name to a list of highlighted fragments. The UI should render fragments using safe HTML rules; do not treat highlight strings as trusted HTML if raw indexed data may contain markup.

### 9.2. Inner Hits

Inner hits are useful when querying nested documents or parent-child relationships and needing the specific child documents that matched. This metadata is attached to each parent hit:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "term": {
          "variants.color": "black"
        }
      },
      "inner_hits": {
        "name": "matching_variants"
      }
    }
  }
}
~~~

When reading results, inspect `SearchHit.getInnerHits()` rather than expecting non-matching nested objects to be stripped from entity content. Entity content generally reflects the source document; inner hits represent the separate result set from the sub-query.

## 10. Aggregations and Search-Level Metadata

A single query can return both hits and aggregations:

~~~json
{
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      }
    }
  }
}
~~~

Hits return ACTIVE products; the `by_category` aggregation counts documents per category across the queried document set. Aggregation results do not live inside each Product. They belong to SearchHits-level metadata.

When a repository returns `SearchPage<Product>`, make sure layers needing aggregations can still access the aggregation container from the underlying SearchHits or use a response envelope holding both the page and aggregations. Do not force aggregations into a list of Products, as they are completely different types of data.

## 11. Designing a Response Envelope When the API Needs DTOs

Not every API wants to return Spring Data types directly. You can create dedicated response DTOs, but you must decide which metadata needs to be preserved.

Example:

~~~java
public record ProductSearchItem(
        String id,
        Product product,
        float score,
        List<Object> sortValues,
        Map<String, List<String>> highlights
) {
}

public record ProductSearchResponse(
        List<ProductSearchItem> items,
        long totalHits,
        String totalHitsRelation,
        float maxScore,
        int page,
        int size
) {
}
~~~

Mapper:

~~~java
List<ProductSearchItem> items = searchHits.getSearchHits().stream()
        .map(hit -> new ProductSearchItem(
                hit.getId(),
                hit.getContent(),
                hit.getScore(),
                hit.getSortValues(),
                hit.getHighlightFields()
        ))
        .toList();
~~~

The response envelope should also retain aggregations or suggestions if the API requires them. Exact aggregation container and total hits relation types depend on the Spring Data Elasticsearch version, so map them into stable application DTOs instead of leaking internal client types if your API contract should remain library-independent.

Not all metadata needs to be exposed to clients. Choose based on the use case:

- Search UIs typically need score, highlights, paging, and total hits.
- Cursor-based APIs may need sort values.
- Nested result views may need inner hits.
- Dashboards may need aggregations.
- Backend scroll/batch jobs may need a scroll ID or point-in-time context.

## 12. Why You Should Not Unwrap Results Too Early

A common mistake:

~~~java
List<Product> products = searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();

return products;
~~~

This snippet is fine if the caller only needs entities. However, once unwrapped, each item loses its score, sort values, highlights, and inner hits. The SearchHits container is also gone from the response, making totalHits, aggregations, and other metadata inaccessible.

If one layer needs plain entities and another needs metadata, define two explicit methods or two clear response types:

- `searchProducts(...)` returning `SearchPage<Product>` for search use cases.
- `findProductsForExport(...)` returning entities or a stream for export use cases where search metadata is unnecessary.

Do not force a single `List<T>` return type for every use case and then try to patch missing metadata with extra queries.

## 13. Pagination and Sorting Must Preserve Metadata

`Pageable` describes page number, size, and sort order. The query must apply pageable so Elasticsearch returns the right result window. Afterward, `SearchHitSupport.searchPageFor` pairs `SearchHits` with pageable.

Example:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
);

SearchPage<Product> result =
        productRepository.searchProducts(criteria, pageable);
~~~

When paginating by score or multi-field sorting, `SearchHit.getSortValues()` can be essential for continuing traversal with search_after. Do not try to reconstruct sort values from the entity, since they are query-result metadata returned by Elasticsearch.

For very large datasets or cursor requirements, offset pagination may be unsuitable. Consider `search_after` or PIT as supported by your Elasticsearch version. When using cursors, retain sort values and required context in the response or service state rather than keeping only entity content.

## 14. Total Hits and Result Count Accuracy

Elasticsearch can cap exact hit counting to reduce query cost. Therefore, total hits should always be paired with its relation:

- `EQUAL_TO`: the total hit count is exact.
- `GREATER_THAN_OR_EQUAL_TO`: the returned number is a lower bound.

If the UI displays "1,000 results", it needs to know whether that number is exact or at least 1,000. If business requirements demand exact totals, configure the query to track total hits accordingly, while understanding the added performance cost.

Never calculate the total using `content.size()`, as that is only the number of hits on the current page, not the overall total.

## 15. Controlling the Responsibilities of a Custom Repository

A well-designed custom repository encapsulates queries without becoming a monolithic class that handles everything.

Separate concerns cleanly:

- Criteria validation: checking price ranges, keywords, page sizes, and sort fields.
- Query builder: converting criteria into Query DSL.
- Search executor: invoking ElasticsearchOperations.
- Result mapper: preserving or transforming metadata according to the response contract.

If a query has many branches, extract helpers for full-text clauses, filters, sorting, highlights, and aggregations. Still, avoid creating abstractions for every tiny clause; keep the structure readable enough that a developer can clearly trace the final query.

### 15.1. Security and Tenant Filters

Tenant or access-control conditions must be enforced server-side so clients cannot bypass them by omitting a filter. A custom repository is an appropriate place to attach mandatory filters derived from the security context or service-controlled parameters.

Do not allow clients to pass arbitrary field paths or raw Query DSL unless the API is intentionally built as a trusted search console. Use allowlisted criteria to constrain permissible search capabilities.

## 16. Testing a Custom Search Repository

Tests should verify both content and metadata.

### 16.1. Testing Query Criteria

Verify each condition:

- Null or blank keywords do not produce meaningless match queries.
- Status/category/brand filters are only added when values are present.
- Min price is not greater than max price.
- Sort fields belong to the allowlist.
- Page size stays within limits.
- Tenant/security filters are always applied.

### 16.2. Testing Per-Hit Metadata

Seed documents with matching text and execute queries with highlighting and sorting. Verify that content maps accurately to Product, SearchHit IDs match document IDs, scores are preserved, sort values are present when sorting is requested, highlight fields contain expected fragments, and inner hits appear when nested/parent-child queries request them.

### 16.3. Testing Search-Wide Metadata

Verify that total hits and total hits relation are accurate, max score has the expected value, aggregations are preserved, SearchPage reflects the right page/size/total elements, and empty result pages still carry valid response metadata.

### 16.4. Testing Unwrapping

If the API uses a DTO mapper, verify the mapper retains every metadata field required by the response contract. If an API returns entities only, confirm that discarding metadata is intentional and does not affect other use cases.

Mocking ElasticsearchOperations can verify that the repository builds the expected query and transforms results properly. Integration tests against a compatible Elasticsearch instance are still essential to confirm DSL, highlights, aggregations, and inner hits behave properly in practice.

## 17. Common Pitfalls

### 17.1. Returning List<Entity> for a Use Case That Needs Score or Highlights

An entity list contains no per-hit metadata. Return SearchHits or SearchPage when callers need that information.

### 17.2. Using Page<Entity> and Assuming All Search Metadata Is Preserved

Page preserves basic pagination info, not per-item scores, highlights, or inner hits. Use SearchPage.

### 17.3. Unwrapping SearchHit Too Early

Extracting only getContent() discards hit metadata. Unwrap only at the boundary where the application has decided metadata is no longer needed.

### 17.4. Ignoring totalHitsRelation

Total hits may be a lower bound. Do not unconditionally display it as an exact count.

### 17.5. Reading Aggregations from Entities

Aggregations belong to SearchHits, not inside content entities. Keep the container or map aggregations separately.

### 17.6. Recomputing Sort Values Manually

Sort values are query-result metadata. Do not infer them from entities when accurate search_after or cursor pagination is needed.

### 17.7. Putting DSL Directly in Services

Services become tightly coupled to Elasticsearch and harder to test. Encapsulate queries in repository fragments.

### 17.8. Misnaming the Repository Implementation

Spring Data will not find a fragment implementation if its name or discovery configuration does not match. Follow your version's naming convention and confirm the bean is registered.

### 17.9. Exposing Client-Specific Query Types in Public APIs

Leaking Elasticsearch query/aggregation types out to controllers makes APIs rigid and hard to evolve. Accept business criteria and map results to response DTOs when needed.

## 18. Workflow for Building a Custom Search Method

1. Identify the use case and the metadata callers require.
2. Create a criteria object containing only permitted business conditions.
3. Declare a custom repository fragment.
4. Implement the fragment using ElasticsearchOperations.
5. Build Query DSL from criteria, adding security and tenant filters.
6. Attach pageable, sort, highlights, aggregations, or inner hits as needed.
7. Execute the search and retain SearchHits<T>.
8. Convert to SearchPage<T> if a page abstraction is needed while preserving SearchHit metadata.
9. If DTOs are required, intentionally map each piece of metadata into a response envelope.
10. Test content, per-hit metadata, search-wide metadata, and empty-result cases.

## 19. Conclusion

Custom repositories encapsulate complex Elasticsearch query construction behind a clean, business-oriented method. Criteria objects decouple APIs from Query DSL; repository fragments build queries, enforce mandatory filters, sorting, pagination, highlights, and aggregations, and execute them via ElasticsearchOperations.

To preserve result metadata, avoid converting SearchHits<T> to List<T> prematurely. SearchHit<T> holds the content alongside ID, score, sort values, highlight fields, and inner hits; SearchHits<T> holds total hits, count accuracy relation, max score, and search-level metadata. SearchPage<T> combines pagination with SearchHit<T> items, making it ideal when callers need paged results without losing per-hit metadata.

If your API requires custom DTOs, design a response envelope that preserves the exact metadata needed. Only unwrap into plain entities when a use case genuinely does not require scores, highlights, inner hits, aggregations, or sort values. A well-structured custom repository both hides query complexity and preserves enough information for upper layers to present and process results accurately.
