# Organizing Search Services, Repositories, and Query Builders

In a Spring Data Elasticsearch application, search code often starts with a simple repository method. As requirements grow—multiple optional filters, multi-tenancy, sorting, pagination, highlighting, aggregations, and various response types—if controllers build Query DSL directly or services hold all query logic, the code quickly becomes hard to read and test.

A maintainable design requires a clear separation of responsibilities:

- **Controller/API** receives requests, validates inputs, and translates them into search criteria.
- **Search service** orchestrates the use case, enforces business policies, and applies query limits.
- **Repository or search adapter** performs Elasticsearch access.
- **Query builder** converts search criteria into a structured query without performing I/O.
- **Mapper/projection** converts search hits into an API-appropriate response model.

Not every query needs a dedicated builder class. Repository methods remain a great choice for simple operations. `ElasticsearchOperations` and `NativeQuery` fit when you need control over Query DSL, metadata, aggregations, or search hits. The goal is to put each kind of logic in the right place and keep the path from API to Elasticsearch understandable, testable, and observable.

## 1. The architectural picture

A typical search flow:

~~~mermaid
flowchart TD
    A["HTTP Search Request"] --> B["Search Controller"]
    B --> C["Request validation / DTO mapping"]
    C --> D["ProductSearchService"]
    D --> E["Search criteria + policy"]
    E --> F["ProductSearchQueryBuilder"]
    F --> G["ProductSearchRepository / Search Adapter"]
    G --> H["ElasticsearchOperations or Repository"]
    H --> I["Elasticsearch index / alias"]
    I --> H
    H --> J["SearchHits / entities"]
    J --> K["Result mapper"]
    K --> L["SearchResponse DTO"]
    L --> A
~~~

Each component answers a specific question:

| Component | Question it answers |
|---|---|
| Controller | What did the caller send and which use case are they allowed to invoke? |
| Criteria | What are the business-meaningful search conditions? |
| Search service | What scope can be searched and which policies must be applied? |
| Query builder | How are criteria expressed as Query DSL? |
| Repository/adapter | How is the request sent to Elasticsearch and how are results retrieved? |
| Mapper | What response contract do search hits become? |

Do not let controllers know Elasticsearch field names, analyzers, nested paths, or how to construct a bool query. Likewise, do not let query builders read `SecurityContext` directly, call repositories, or send requests themselves. Clear boundaries allow mappings or data access strategies to change with minimal impact on the rest of the codebase.

## 2. Distinguishing Repository, ElasticsearchOperations, and Query Builder

These three components are often merged into a single class, yet they play distinct roles.

### Repository

Repositories provide an abstraction for saving/reading documents and for named or declarative query methods.

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByStatus(String status);

    List<ProductDocument> findByStatusAndCategory(
            String status,
            String category
    );

    Optional<ProductDocument> findByProductId(String productId);
}
~~~

Fits when:

- Query conditions are simple and stable.
- Method names clearly describe query intent.
- Little metadata outside the entity is needed.
- The repository is a natural abstraction for the stored document.

### ElasticsearchOperations

`ElasticsearchOperations` is a lower-level API than repositories, giving the application control over queries, index coordinates, search hits, updates, bulk operations, and other Elasticsearch operations.

Example:

~~~java
SearchHits<ProductDocument> hits =
        operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products")
        );
~~~

Fits when:

- Queries have many optional filters.
- Complex bool/nested/function score/Query DSL is needed.
- Highlights, aggregations, suggestions, or search metadata are needed.
- `SearchHits<T>`, sort values, or scores are needed.
- Explicit control over a specific index/alias is needed.
- Building a custom repository fragment.

### Query builder

A query builder is solely responsible for transforming input criteria into a query object. It does not execute requests and does not know which repository is used.

Example:

~~~java
public class ProductSearchQueryBuilder {

    public Query build(ProductSearchCriteria criteria) {
        // Build Query DSL from validated criteria.
    }
}
~~~

A builder is suitable when there are multiple conditional branches, query-building logic needs reuse, or you want to unit-test query semantics independently.

Do not create a builder just to wrap a single `findByStatus(...)` call. Adding classes that merely forward one method creates unnecessary boilerplate without value.

## 3. Start from use cases, not from Query DSL

Describe what the user needs to do in business language:

- Find published products.
- Filter by category.
- Search by keyword across name and description.
- Restrict price range.
- View only products belonging to the current tenant.
- Sort by price or update timestamp.
- Paginate results.

An API request might look like:

~~~http
GET /api/products/search?q=keyboard&category=ACCESSORIES&minPrice=100000&maxPrice=2000000&page=0&size=25&sort=price,asc
~~~

The controller should translate this request into a strongly typed criteria object:

~~~java
public record ProductSearchCriteria(
        String text,
        String category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        String status,
        int page,
        int size,
        ProductSort sort
) {
}
~~~

Criteria represent search intent. They should not contain an Elasticsearch `Query`, analyzer names, or raw JSON sent by the client.

If an API has many filter categories, use nested records or value objects to group related conditions. Avoid creating criteria with dozens of loose parameters belonging to unrelated concepts.

## 4. Separating request DTOs from search criteria

A request DTO is the HTTP contract. Search criteria represent use-case input. The two types may look similar initially, but they do not have to be identical.

Example:

~~~java
public record ProductSearchRequest(
        String q,
        String category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Integer page,
        Integer size,
        String sort
) {
}
~~~

The controller converts the request into criteria:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductSearchController {

    private final ProductSearchService searchService;

    public ProductSearchController(ProductSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/search")
    public ProductSearchResponse search(ProductSearchRequest request) {
        ProductSearchCriteria criteria =
                ProductSearchRequestMapper.toCriteria(request);

        return searchService.search(criteria);
    }
}
~~~

The mapper can normalize defaults and convert a sort string to an enum. However, user/tenant-dependent policies must be obtained from a verified security context inside the service or a trusted authorization component.

Do not accept raw Query DSL, index names, or arbitrary field names from clients and pass them straight to Elasticsearch. Doing so couples the API to the implementation and risks overly broad queries or unauthorized data access.

## 5. The search service orchestrates the use case

The service is responsible for enforcing business rules and orchestrating repositories/adapters.

Example:

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchRepository searchRepository;
    private final CurrentTenantProvider tenantProvider;

    public ProductSearchService(
            ProductSearchRepository searchRepository,
            CurrentTenantProvider tenantProvider
    ) {
        this.searchRepository = searchRepository;
        this.tenantProvider = tenantProvider;
    }

    public ProductSearchResponse search(ProductSearchCriteria criteria) {
        validate(criteria);

        String tenantId = tenantProvider.requiredTenantId();

        ProductSearchCriteria scopedCriteria =
                criteria.withTenantId(tenantId);

        ProductSearchResult result =
                searchRepository.search(scopedCriteria);

        return ProductSearchResponse.from(result);
    }

    private void validate(ProductSearchCriteria criteria) {
        if (criteria.minPrice() != null
                && criteria.maxPrice() != null
                && criteria.minPrice().compareTo(criteria.maxPrice()) > 0) {
            throw new InvalidProductSearchException(
                    "minPrice must not exceed maxPrice"
            );
        }
    }
}
~~~

This snippet illustrates a criteria record with a `withTenantId` method; you can implement it via a tenant-augmented record or a separate internal criteria type.

The service should:

- Validate relationships between filters.
- Enforce mandatory tenant/ownership scope.
- Bound page size and sort options.
- Select the use case/search mode.
- Invoke the appropriate adapter.
- Convert results into the response contract.
- Translate technical errors into application errors at the appropriate boundary.

The service should not contain hundreds of lines of Query DSL construction if query logic can be extracted. Nor should it become a pure pass-through proxy over a repository if there is no orchestration or policy.

## 6. When are derived repository methods enough?

Derived query methods suit simple, rarely changing conditions.

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByStatus(String status);

    List<ProductDocument> findByStatusAndCategory(
            String status,
            String category
    );

    List<ProductDocument> findByCategoryAndPriceBetween(
            String category,
            BigDecimal min,
            BigDecimal max
    );

    long countByStatus(String status);
}
~~~

Advantages:

- Minimal code.
- Method names express query conditions.
- Easy to understand for simple queries.
- Suitable for CRUD and attribute-based lookups.

Limitations:

- Long method names when many conditions exist.
- Hard to express nested OR branches.
- Hard to manage multiple optional filters.
- Not suitable for complex scoring, nested queries, or aggregations.
- Can be difficult to keep stable when queries require rich metadata.

A sign to move to a custom search adapter is when a method accumulates multiple conditional branches or its name no longer conveys intent clearly.

Do not create methods for every filter combination like `findByStatusAndCategoryAndMinPriceAndMaxPriceAndBrandAnd...`. As optional filters grow, a structured query builder is much easier to maintain.

## 7. Combining repository interfaces with custom fragments

Spring Data lets you extend a repository with a custom fragment. This is a clean way to keep the familiar repository API while placing complex queries in a dedicated implementation.

Declare the fragment:

~~~java
public interface ProductSearchRepository {

    ProductSearchResult search(ProductSearchCriteria criteria);
}
~~~

Main repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchRepository {
}
~~~

Fragment implementation:

~~~java
@Repository
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;
    private final ProductSearchQueryBuilder queryBuilder;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations,
            ProductSearchQueryBuilder queryBuilder
    ) {
        this.operations = operations;
        this.queryBuilder = queryBuilder;
    }

    @Override
    public ProductSearchResult search(ProductSearchCriteria criteria) {
        Query query = queryBuilder.build(criteria);

        SearchHits<ProductDocument> hits =
                operations.search(
                        query,
                        ProductDocument.class,
                        IndexCoordinates.of("products")
                );

        return ProductSearchResult.from(hits);
    }
}
~~~

The implementation name must follow Spring Data's fragment discovery convention and the project's repository configuration. For a fragment named `ProductSearchRepository`, the implementation is typically `ProductSearchRepositoryImpl`. If the project uses a custom repository postfix or package configuration, align the naming with that convention.

This structure helps:

- The repository interface exposes the search use case.
- The implementation owns Elasticsearch specifics.
- The builder can be unit-tested independently.
- The service does not need to know about `NativeQuery` or Query DSL.

If custom fragments are attached to the main repository, avoid creating multiple similarly named fragments responsible for the same query.

## 8. Separating search repositories from write repositories when justified

Not every application needs two repositories. However, when the search projection has many specialized queries and the write path has a different lifecycle, splitting interfaces clarifies boundaries.

Example:

~~~java
public interface ProductDocumentWriter {

    void index(ProductDocument document);

    void delete(String productId);
}
~~~

~~~java
public interface ProductSearchReader {

    ProductSearchResult search(ProductSearchCriteria criteria);

    Optional<ProductSearchView> findViewById(String productId);
}
~~~

Implementations can share `ElasticsearchOperations` while exposing distinct capabilities to services.

Benefits:

- The search service cannot accidentally invoke delete/index.
- The writer does not depend on search APIs.
- Different credentials or clients can be wired if required by the security model.
- Test doubles are smaller and accurately reflect use-case needs.

Do not split interfaces purely for the sake of having more interfaces. If the system is small and one `ProductRepository` is clear enough, extra abstractions add unnecessary indirection.

## 9. Query builders should be pure components

A good query builder takes criteria and returns a query. It does not:

- Read HTTP requests.
- Read `SecurityContext` directly.
- Call Elasticsearch.
- Log full sensitive sources/queries.
- Decide on its own which tenant a user can access.
- Retain state across invocations.

Example:

~~~java
@Component
public class ProductSearchQueryBuilder {

    public Query build(ProductSearchCriteria criteria) {
        return Query.of(query -> query.bool(bool -> {
            bool.filter(filter -> filter.term(term -> term
                    .field("status")
                    .value("PUBLISHED")
            ));

            if (criteria.category() != null) {
                bool.filter(filter -> filter.term(term -> term
                        .field("category")
                        .value(criteria.category())
                ));
            }

            if (criteria.minPrice() != null
                    || criteria.maxPrice() != null) {
                bool.filter(filter -> filter.range(range -> range
                        .number(number -> {
                            number.field("price");

                            if (criteria.minPrice() != null) {
                                number.gte(
                                        criteria.minPrice().doubleValue()
                                );
                            }

                            if (criteria.maxPrice() != null) {
                                number.lte(
                                        criteria.maxPrice().doubleValue()
                                );
                            }

                            return number;
                        })
                ));
            }

            return bool;
        }));
    }
}
~~~

This illustrates a query builder using the Elasticsearch Java API Client integrated with modern versions of Spring Data Elasticsearch. Lambda builders may need adjustment for your specific client version.

Several principles:

- Mandatory non-scoring conditions belong in `filter`.
- Full-text conditions typically use `must` or `should` depending on semantics.
- Add clauses only when criteria have values.
- Do not add empty ranges or term clauses with blank strings.
- Field names must be server-controlled.
- The query builder must not inject a tenant scope unless the tenant has been verified and reliably supplied via criteria.

## 10. Mandatory tenant scope in queries

In a multi-tenant application sharing an index, the tenant filter is a security condition. Never make this filter an optional condition that a controller might forget to pass.

Internal criteria should contain the authenticated tenant:

~~~java
public record ProductSearchCriteria(
        String tenantId,
        String text,
        String category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        int page,
        int size,
        ProductSort sort
) {
}
~~~

The builder always adds the tenant filter:

~~~java
bool.filter(filter -> filter.term(term -> term
        .field("tenantId")
        .value(criteria.tenantId())
));
~~~

Do not take a tenant ID from a query parameter without verifying permission to access that tenant. Preferably, `SearchService` obtains the tenant from a principal/authorization service and builds the internal criteria.

For queries spanning multiple indices or aliases, verify that the tenant field is present and consistently mapped across every searched index. An alias pointing to an older index missing the tenant mapping can break queries or authorization.

## 11. Distinguishing must, filter, and should

A query builder should reflect search semantics, not just dump every condition into one bool clause.

| Clause | Use when | Affects score |
|---|---|---|
| `must` | Condition is required and relevant to scoring | Yes |
| `filter` | Condition is required and scoring is not needed | No |
| `should` | Condition boosts relevance or forms an OR branch via minimum_should_match | Yes |
| `must_not` | Excludes unwanted documents | No |

Example searching by keyword and filtering by status/category:

~~~java
Query query = Query.of(q -> q.bool(bool -> bool
        .must(must -> must.multiMatch(multi -> multi
                .query(criteria.text())
                .fields("name^3", "description")
        ))
        .filter(filter -> filter.term(term -> term
                .field("status")
                .value("PUBLISHED")
        ))
        .filter(filter -> filter.term(term -> term
                .field("tenantId")
                .value(criteria.tenantId())
        ))
));
~~~

`name^3` boosts the weight of the `name` field relative to `description`. Status/tenant conditions go inside `filter` because they are constraints, not ranking signals.

If `text` can be null or blank, the builder should omit the full-text clause rather than sending an empty query. If the API requires a keyword, validate it in the service before calling the builder.

## 12. Never let raw field names and sort fields from clients enter queries

A client might send:

~~~http
GET /api/products/search?sort=internalCost,desc
~~~

If the code passes `internalCost` straight into the sort builder, the API exposes mapping details to client control. This can trigger expensive queries or leak internal data structure through behavior.

Use an enum/allowlist:

~~~java
public enum ProductSort {
    RELEVANCE,
    NAME_ASC,
    PRICE_ASC,
    PRICE_DESC,
    UPDATED_DESC
}
~~~

Map the enum to a server-side sort:

~~~java
private Sort toSort(ProductSort sort) {
    return switch (sort) {
        case NAME_ASC -> Sort.by(
                Sort.Order.asc("name.keyword"),
                Sort.Order.asc("productId")
        );
        case PRICE_ASC -> Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.asc("productId")
        );
        case PRICE_DESC -> Sort.by(
                Sort.Order.desc("price"),
                Sort.Order.asc("productId")
        );
        case UPDATED_DESC -> Sort.by(
                Sort.Order.desc("updatedAt"),
                Sort.Order.asc("productId")
        );
        case RELEVANCE -> Sort.unsorted();
    };
}
~~~

With relevance, Elasticsearch scores normally determine default ordering per query; if using an explicit score sort or tie-breaker, configure it according to use-case semantics.

Sort fields must exist and have sortable mappings, typically keyword/numeric/date. Do not sort directly on a `text` field without an appropriate field.

## 13. Centralize pagination normalization

Page number and size are client inputs, but limits are service policy.

~~~java
public record SearchPage(int page, int size) {

    public static SearchPage normalize(
            Integer requestedPage,
            Integer requestedSize
    ) {
        int page = requestedPage == null
                ? 0
                : Math.max(0, requestedPage);

        int requested = requestedSize == null
                ? 25
                : requestedSize;

        int size = Math.min(Math.max(requested, 1), 100);

        return new SearchPage(page, size);
    }

    public Pageable toPageable(Sort sort) {
        return PageRequest.of(page, size, sort);
    }
}
~~~

Use a single normalization component so endpoints do not pick inconsistent defaults and max sizes.

With `from/size` pagination, bound the depth and account for `max_result_window`. For deep exports, use `search_after` and PIT instead of letting clients pass huge page numbers.

Sorts should be stable with a unique tie-breaker. If data changes while the user pages through results, offset pagination can still duplicate or skip documents; PIT/`search_after` are needed when consistent snapshots are required.

## 14. Builders for both query and pageable

You can split query filters and page/sort into two components:

- `ProductSearchQueryBuilder`: constructs query conditions.
- `ProductSearchPageFactory`: normalizes page size and sort.

Example orchestration inside the adapter:

~~~java
public ProductSearchResult search(ProductSearchCriteria criteria) {
    Query query = queryBuilder.build(criteria);

    Pageable pageable = pageFactory.create(
            criteria.page(),
            criteria.size(),
            criteria.sort()
    );

    NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .withPageable(pageable)
            .build();

    SearchHits<ProductDocument> hits =
            operations.search(
                    nativeQuery,
                    ProductDocument.class,
                    IndexCoordinates.of("products")
            );

    return ProductSearchResult.from(hits);
}
~~~

This separation pays off when pagination/sorting is shared across multiple search use cases. If there is only one small query, keeping them in one builder avoids over-fragmenting classes.

Do not let two builders mutate a shared mutable `NativeQuery.Builder`. Create a fresh query object for each search rather than holding a builder inside a singleton bean.

## 15. SearchHit, SearchHits, and response DTOs

Search results often carry much more metadata beyond the entity:

- Document content.
- ID, index.
- Score.
- Sort values.
- Highlight fields.
- Matched queries.
- Total hits and relation.
- Result-level aggregations.

If the service only returns `List<ProductDocument>`, some metadata is discarded. When the API needs score/highlights/total hits, the adapter should retain `SearchHits<T>` long enough to map them.

Example response:

~~~java
public record ProductSearchItem(
        String productId,
        String name,
        BigDecimal price,
        Float score,
        Map<String, List<String>> highlights
) {
}
~~~

~~~java
public record ProductSearchResponse(
        List<ProductSearchItem> items,
        long totalHits,
        int page,
        int size,
        boolean hasMore
) {
}
~~~

Mapper:

~~~java
private ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
    ProductDocument source = hit.getContent();

    return new ProductSearchItem(
            source.getProductId(),
            source.getName(),
            source.getPrice(),
            hit.getScore(),
            hit.getHighlightFields()
    );
}
~~~

Highlight/score types and conversion methods must match your Spring Data Elasticsearch version. Do not return persistence entities directly if the API needs a stable contract or must hide internal fields.

## 16. Separate projections for search results

Search results may need fewer fields than the document used for writing.

Example:

~~~java
public class ProductDocument {

    @Id
    private String id;

    private String productId;
    private String tenantId;
    private String name;
    private String description;
    private BigDecimal price;
    private String status;
    private String internalNotes;
    private Instant updatedAt;
}
~~~

Result projection:

~~~java
public record ProductSearchView(
        String productId,
        String name,
        BigDecimal price
) {
}
~~~

You can use projection/DTO mapping or source filtering to retrieve only the needed fields. An application-side DTO alone does not reduce network payload if Elasticsearch still transmits the entire `_source`; use source filtering when the goal is reducing bytes transferred.

Keep document mappings and API responses decoupled so changing analyzers, index fields, or source structures does not force changes to the public API.

## 17. When to use NativeQuery?

`NativeQuery` is the right choice when queries require Elasticsearch features or Query DSL more complex than derived methods can cleanly express.

For example, use cases with:

- Full-text multi-match.
- Multiple optional filters.
- Nested queries.
- Function scores.
- Highlights.
- Aggregations.
- Source filtering.
- Search after.
- Explicit sort and track total hits.

A query can be assembled from parts:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(queryBuilder.build(criteria))
        .withPageable(pageFactory.create(criteria))
        .withSourceFilter(sourceFilterFactory.forProductList())
        .withTrackTotalHits(true)
        .build();
~~~

Builder method names and types may vary by version. Check the API of Spring Data Elasticsearch/Elasticsearch Java API Client in your actual dependencies.

Do not use `NativeQuery` for every query merely because it is flexible. Simple repository methods are usually easier to read and require less code.

## 18. Query specifications and composition

When many filters are reusable, you can extract small functions to construct clauses.

Example:

~~~java
private Query statusFilter(String status) {
    return Query.of(q -> q.term(t -> t
            .field("status")
            .value(status)
    ));
}

private Query categoryFilter(String category) {
    return Query.of(q -> q.term(t -> t
            .field("category")
            .value(category)
    ));
}
~~~

Or each specification returns a bool clause and the builder combines them. This lets you test individual filters in isolation.

Do not build an overly generic abstraction like a homegrown DSL covering all of Elasticsearch Query DSL. Good abstractions reflect meaningful business concepts: published products, tenant scope, price range, text relevance.

If each filter is used only once and is very short, keeping it inline inside the builder may be clearer than creating dozens of specification classes.

## 19. Queries with multiple OR branches

For example, find products if:

- Name matches the keyword; or
- SKU matches exactly; while simultaneously
- Status must be PUBLISHED and tenant must match.

Use `should` for the OR branch and `filter` for mandatory conditions:

~~~java
Query query = Query.of(q -> q.bool(bool -> bool
        .filter(filter -> filter.term(term -> term
                .field("status")
                .value("PUBLISHED")
        ))
        .filter(filter -> filter.term(term -> term
                .field("tenantId")
                .value(criteria.tenantId())
        ))
        .should(should -> should.match(match -> match
                .field("name")
                .query(criteria.text())
        ))
        .should(should -> should.term(term -> term
                .field("sku")
                .value(criteria.text())
        ))
        .minimumShouldMatch("1")
));
~~~

`minimumShouldMatch("1")` requires at least one `should` branch to match in this bool context. If unconfigured, default `should` semantics depend on whether the bool has `must`/`filter`; do not rely on defaults when OR semantics are mandatory.

This illustrates query composition. Confirm that `sku` is mapped as `keyword` and `name` has an appropriate analyzer.

## 20. Nested queries and mappings must match

If a document contains an array of objects that must be queried independently per element, the mapping may need `nested`. For example, a product with variants:

~~~json
{
  "variants": [
    {
      "color": "black",
      "size": "M",
      "stock": 10
    },
    {
      "color": "white",
      "size": "L",
      "stock": 0
    }
  ]
}
~~~

If you need a variant that both is black and has stock greater than 0, a nested query keeps both conditions within the same object:

~~~java
Query nestedQuery = Query.of(q -> q.nested(nested -> nested
        .path("variants")
        .query(inner -> inner.bool(bool -> bool
                .filter(filter -> filter.term(term -> term
                        .field("variants.color")
                        .value("black")
                ))
                .filter(filter -> filter.range(range -> range
                        .number(number -> number
                                .field("variants.stock")
                                .gt(0.0)
                        )
                ))
        ))
));
~~~

If the mapping is a regular `object` instead of `nested`, Elasticsearch flattens values and queries can cross-match across elements. A query builder cannot fix a broken mapping; mapping and semantics must be designed together.

## 21. Highlights and aggregations belong in the search adapter

When an endpoint requires highlights, aggregations, or suggestions, the adapter can use `NativeQuery` and return a metadata-rich result model.

Do not cram aggregation parsing into the controller. A mapper or dedicated component should convert aggregation responses into business DTOs.

Example aggregation response:

~~~java
public record CategoryCount(
        String category,
        long count
) {
}
~~~

The search result can include:

- List of products.
- Total hit count.
- Counts per category.
- Highlight snippets.
- Min/max price.

If an endpoint only needs aggregations, set the hit size to 0 or skip fetching hit sources. If both hits and aggregations are needed, keep page size small and intentional.

## 22. Choosing IndexCoordinates and aliases in the adapter

Physical index names are implementation details. Applications should typically query through an alias like `products` rather than hardcoding `products-v1` across services.

~~~java
private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");
~~~

The adapter uses the alias:

~~~java
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class, PRODUCTS);
~~~

Aliases let deployments switch from `products-v1` to `products-v2` without code changes in services.

If there are multiple tenant indices or regions, index resolution must live in a component with explicit policy. Never let clients supply arbitrary index names.

## 23. Do not turn the query builder into hidden authorization

The query builder can add tenant filters, soft-delete filters, or mandatory status constraints, but there must be a clear contract regarding where criteria come from.

An understandable design:

~~~text
Authenticated principal
       |
       v
Authorization / Tenant provider
       |
       v
Search service creates scoped criteria
       |
       v
Query builder adds mandatory scope filters
       |
       v
Search adapter executes query
~~~

Rules:

- Tenant ID comes from the authenticated identity.
- Permissions are checked in the service/policy layer.
- Builders do not read HTTP requests or thread-local security contexts themselves.
- Every call path into the builder must supply a valid scope.
- There is no "search all tenants" overload for normal user endpoints.
- Tests verify that the tenant filter is always present.

If administrative tasks need to search across multiple tenants, create a separate use case with explicit authorization rather than treating `null` tenant as an implicit filter bypass.

## 24. Caching searches at the service boundary

Some read queries can be cached, but the cache key must include every condition affecting the result:

- Tenant ID.
- Normalized query text.
- Category/status/price filters.
- Sort.
- Page/cursor.
- Locale or analyzer mode, if applicable.
- Permission/visibility scope if it affects data.

Never cache by query text alone if different tenants share the same keyword. That can leak data across tenants.

Cache invalidation should align with document/index update events. Because Elasticsearch is typically an eventually consistent projection, cache TTLs and invalidation must account for synchronization lag.

Do not cache full `SearchHits` objects if they retain internal data or unneeded metadata. Prefer caching small authorization-scoped response DTOs.

## 25. Error handling at the adapter boundary

The adapter can encapsulate Elasticsearch details and translate failures into meaningful technical/application errors:

- Invalid query due to programming bug: bug to fix, do not retry.
- 401/403: credential/role misconfiguration.
- 429/503: bounded retries per policy.
- Timeout: handling depends on operation type and idempotency.
- Mapping error: incompatible data or index mapping.
- Partial shard failure: decide whether partial results are acceptable.

Controllers should not catch every `Exception` and return an empty list. A failed search is different from a successful search with zero matches.

Services can return an empty response when a valid query matches no documents; the adapter should raise an error when an Elasticsearch request fails. Never swallow transport errors into `List.of()`.

## 26. Organizing packages by feature

Example package structure:

~~~text
com.example.catalog
├── product
│   ├── api
│   │   ├── ProductSearchController.java
│   │   ├── ProductSearchRequest.java
│   │   └── ProductSearchResponse.java
│   ├── application
│   │   ├── ProductSearchService.java
│   │   ├── ProductSearchCriteria.java
│   │   └── ProductSort.java
│   ├── search
│   │   ├── ProductSearchRepository.java
│   │   ├── ProductSearchRepositoryImpl.java
│   │   ├── ProductSearchQueryBuilder.java
│   │   ├── ProductSearchPageFactory.java
│   │   └── ProductSearchResultMapper.java
│   ├── persistence
│   │   ├── ProductRepository.java
│   │   └── ProductDocument.java
│   └── domain
│       └── Product.java
└── shared
    ├── security
    └── observability
~~~

You do not need every package/class upfront. When a feature is small, the query builder and custom repository can sit side by side. As use cases grow, organizing by responsibility and feature makes navigation easier than dumping the whole application into giant `controller`, `service`, and `repository` folders.

Crucially, avoid inverted dependencies:

- API does not depend on the Elasticsearch client.
- Domain does not depend on Query DSL.
- Query builder does not depend on controllers.
- The search adapter is where Elasticsearch-specific APIs live.
- Services depend on abstractions tailored to their use cases.

## 27. Testing each layer

### Unit tests for request/criteria mappers

Verify default page, size, sort enums, price ranges, and invalid inputs. No Elasticsearch instance is needed for pure Java rules.

### Unit tests for query builders

Verify that criteria produce the right semantics:

- Tenant filter is always present.
- Status is mandatory.
- Category is added only when present.
- Ranges add only provided bounds.
- Blank text produces no full-text clause.
- OR branches have the appropriate `minimum_should_match`.
- Sort fields belong to the allowlist.

In tests, you can serialize query objects to JSON per client API version to assert DSL, or inspect object structures with suitable helpers.

### Unit tests for search services

Mock the search port/repository and tenant provider to verify:

- Tenant comes from the principal, not the request body.
- Page size is normalized.
- Validation is applied.
- The service invokes the adapter with scoped criteria.
- Adapter errors are not turned into empty results.

### Integration tests with Elasticsearch

Use Testcontainers or a compatible test cluster to verify:

- Actual mappings and analyzers.
- Derived repository methods.
- Query builder produces accurate results.
- Sorting/pagination.
- Highlights/aggregations if used.
- Alias/index coordinates.
- Source filtering/projections.
- Tenant isolation.
- Index version/mapping compatibility.

Unit tests prove the builder constructs the expected object; integration tests prove Elasticsearch actually understands that query and mapping.

## 28. Testing tenant isolation and sort allowlists

An essential test must prove two tenants cannot see each other's data:

~~~java
@Test
void searchOnlyReturnsDocumentsFromAuthenticatedTenant() {
    // Arrange:
    // - Index product A belonging to tenant-1.
    // - Index product B belonging to tenant-2.
    // - CurrentTenantProvider returns tenant-1.
    //
    // Act:
    // - Call ProductSearchService.search(criteria).
    //
    // Assert:
    // - Only product A appears.
}
~~~

Sort test:

~~~java
@Test
void rejectsUnsupportedSortField() {
    // Client sends a sort field not in ProductSort allowlist.
    // Request mapper returns a validation error or applies default per API contract.
}
~~~

Do not test the builder with arbitrary tenant IDs alone. Test the service pulling the tenant from the security context/provider to catch wiring mistakes that bypass scoping.

## 29. When do you need CQRS or a separate read model?

An application may start with the same document for both writes and searches. As search use cases grow more complex, you can separate:

- Write model: authoritative business model in the database.
- Search projection: query-optimized Elasticsearch document.
- Search API: reads only the projection.
- Event/CDC pipeline: synchronizes changes into the projection.

This fits when search requires denormalizing data across tables, specialized analyzers, nested structures, or custom aggregations.

Do not adopt CQRS solely because Elasticsearch is present. If a simple repository document satisfies the use case, keep the architecture lean. Split out a read model when there are clear gains in querying, scaling, ownership, or release cycles.

## 30. Common design mistakes

### Controller builds Query DSL directly

The controller knows field names, nested paths, and Elasticsearch APIs. This tightly couples the API to mappings and hampers testing. Move query construction to a builder/adapter.

### Service contains all query construction

The service grows huge and mixes business policy with Elasticsearch syntax. Extract a builder when queries have multiple branches or need reuse.

### Creating builders for every repository method

A simple method like `findByStatus` needs no extra forwarding layers. Use derived methods when they are expressive enough.

### Repository methods with too many filter combinations

Method names get long and hard to evolve. Use criteria objects and custom search implementations for optional filters.

### Query builder reads SecurityContext itself

The builder becomes harder to test and hides dependencies. Have the service/policy layer resolve the authenticated tenant and pass it in criteria.

### Letting clients pass arbitrary sort fields or index names

This can produce unsafe or expensive queries. Use enums/allowlists and server-managed aliases.

### Forgetting tie-breakers when sorting

Results sharing the same sort value can shift order across pages. Add a unique tie-breaker field and use PIT/`search_after` when snapshots are needed.

### Assuming DTOs automatically reduce source payloads

DTOs only limit mapped fields. Reducing network bytes requires source filtering.

### Returning entities directly from APIs

The API becomes coupled to document mappings and risks leaking internal fields. Use response DTOs.

### Swallowing Elasticsearch errors into empty results

Clients cannot distinguish "no results" from "search failed". Preserve clear error semantics.

### Using alias/index names inconsistently

Some services call an alias while others hardcode an index version. Centralize index coordinates in adapters/configuration.

### Over-splitting abstractions

Having interfaces/classes that merely forward a single call makes code harder to trace. Split only when responsibilities, policies, or testability genuinely differ.

## 31. Process for designing a search use case

When adding a new search endpoint:

1. Write down the use case and response contract clearly.
2. Identify filter fields, full-text search fields, sort options, pagination, and required response metadata.
3. Separate mandatory business constraints from optional filters.
4. Determine tenant/ownership scope from the authenticated principal.
5. If the query is simple, use a derived repository method.
6. If the query has multiple branches or metadata, use a custom repository fragment and `ElasticsearchOperations`.
7. Create a criteria object independent of HTTP and Query DSL.
8. Create a pure query builder with no I/O and no security-context reads.
9. Normalize page sizes and enforce sort allowlists.
10. Use server-managed aliases/`IndexCoordinates`.
11. Retain `SearchHits` when scores, highlights, sort values, or total-hit metadata are needed.
12. Map to response DTOs; apply source filtering if payload size needs reduction.
13. Classify errors at the adapter and preserve error semantics.
14. Unit-test criteria, policies, and query builders.
15. Integration-test mapping/query semantics against real Elasticsearch.
16. Test tenant isolation, sort validation, pagination, and error behavior.
17. Add logs/metrics with request IDs without logging sensitive raw queries or sources.

## References

- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Elasticsearch — Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Elasticsearch — Bool query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
- [Elasticsearch — Pagination](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Spring Framework — Application architecture](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)

## Conclusion

Organize search sustainably by having controllers handle HTTP, services enforce use cases and policies, repositories/search adapters perform I/O, query builders translate criteria into Query DSL, and mappers build response DTOs. Use derived repository methods for simple queries; switch to custom fragments with `ElasticsearchOperations`/`NativeQuery` when dynamic filters, nested queries, scoring, highlights, or aggregations are needed. Criteria should remain independent of HTTP and Query DSL; tenant scope must come from authenticated identity; sort fields must use an allowlist; and pagination needs bounds and stable ordering. Separate layers when responsibilities truly diverge, avoiding both controllers containing Query DSL and abstractions that merely forward a single call.
