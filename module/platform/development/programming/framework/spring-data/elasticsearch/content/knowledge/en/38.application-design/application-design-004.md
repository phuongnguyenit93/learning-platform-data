# Request DTOs, Response DTOs, and Metadata Contracts

A search API powered by Spring Data Elasticsearch typically carries more information than a plain list of entities. Requests may contain keywords, filters, price ranges, sort order, and pagination. Responses may need to return products, relevance scores, highlights, total hit counts, facets, search duration, or a cursor for the next page.

If a controller returns Elasticsearch entities or `SearchHit`/`SearchHits` objects directly, the HTTP contract becomes tightly coupled to Spring Data's mappings and internal APIs. When an entity changes to accommodate indexing, the API response may also change unintentionally. Request DTOs, response DTOs, and an explicit metadata contract decouple the HTTP interface from the storage model while controlling precisely what search information is exposed.

This lesson covers designing DTOs for search APIs, translating requests into internal criteria, converting `SearchHit` into response models, defining pagination and relevance metadata, handling highlights/facets/cursors, managing contract compatibility, and testing the API.

## 1. Why are DTOs needed at the API boundary?

An Elasticsearch entity describes how data is stored and mapped in an index. A DTO describes what clients are allowed to send or receive over the API. The two models may share a few fields, yet they serve different purposes.

Example entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String internalSupplierCode;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // getters and setters
}
~~~

An entity may hold `tenantId` for data filtering, `internalSupplierCode` for internal processing, mapping metadata, and index-only fields. Not all of these fields should appear in responses.

If the controller returns `Product` directly, a mapping change such as adding an internal field can accidentally expose that field through JSON serialization. Moreover, clients can start depending on entity internals and make index changes difficult.

Maintain three clear layers:

~~~text
HTTP request
     |
     v
Request DTO
     |
     v
Validation + application criteria
     |
     v
Repository / ElasticsearchOperations
     |
     v
Entity + SearchHit metadata
     |
     v
Response mapper
     |
     v
Response DTO + metadata contract
     |
     v
HTTP response
~~~

Each layer has its own responsibility:

- Request DTO describes public inputs and valid value constraints.
- Application criteria express validated search intent.
- Entity models domain/index data.
- `SearchHit`/`SearchHits` hold entities alongside Elasticsearch metadata.
- Response DTO describes the data and metadata the API commits to providing.

DTOs are not just a way to rename fields. They form a boundary that keeps the API stable when indices, mappings, or libraries evolve.

## 2. Designing request DTOs for search

Request DTOs should express business needs, such as searching products by keyword, status, and price range. Avoid letting clients send raw Elasticsearch Query DSL structures or physical index names.

Example request:

~~~java
public record ProductSearchRequest(
    String query,
    ProductStatus status,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Integer page,
    Integer size,
    ProductSort sort,
    SortDirection direction,
    Boolean includeFacets
) {}
~~~

Public enums:

~~~java
public enum ProductStatus {
    ACTIVE,
    DISCONTINUED,
    DRAFT
}

public enum ProductSort {
    RELEVANCE,
    NAME,
    PRICE,
    CREATED_AT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

Clients choose a value from the API-supported enum set. The server maps the enum to the corresponding Elasticsearch field. This prevents clients from arbitrarily controlling fields used for sorting or querying.

### Validation at the request boundary

Use Bean Validation to reject invalid inputs before building a query:

~~~java
public record ProductSearchRequest(
    @Size(max = 120)
    String query,

    ProductStatus status,

    @DecimalMin("0.00")
    BigDecimal minPrice,

    @DecimalMin("0.00")
    BigDecimal maxPrice,

    @Min(0)
    Integer page,

    @Min(1)
    @Max(100)
    Integer size,

    ProductSort sort,

    SortDirection direction,

    Boolean includeFacets
) {}
~~~

These annotations require the corresponding validation dependency. With records and Bean Validation, verify your Spring Boot/Validation version configuration.

Ensuring `minPrice` does not exceed `maxPrice` requires an additional check because it relates two fields:

~~~java
private void validatePriceRange(ProductSearchRequest request) {
    if (request.minPrice() != null
            && request.maxPrice() != null
            && request.minPrice().compareTo(request.maxPrice()) > 0) {
        throw new InvalidSearchRequestException(
            "minPrice must not exceed maxPrice"
        );
    }
}
~~~

If this rule appears across multiple requests, create a class-level validator or centralize validation in a dedicated component.

### Default values

Do not let each controller pick its own defaults for page, size, and sort. Normalize them in one place:

~~~java
int page = request.page() == null ? 0 : request.page();
int size = request.size() == null ? 20 : request.size();

ProductSort sort = request.sort() == null
    ? ProductSort.RELEVANCE
    : request.sort();

SortDirection direction = request.direction() == null
    ? SortDirection.DESC
    : request.direction();
~~~

Bounding maximum size protects Elasticsearch from requests returning too many hits. Defaults and limits must match SLAs, document sizes, and service capacity.

### Never accept raw Elasticsearch queries from clients

Avoid requests like:

~~~json
{
  "index": "products-internal",
  "queryDsl": {
    "query": {
      "match_all": {}
    }
  },
  "sortField": "_script",
  "routing": "tenant-42"
}
~~~

Such inputs hand implementation control to clients and can open up overly expensive queries or access outside the intended API scope.

Public APIs should accept typed business vocabulary. The server is responsible for constructing Query DSL, selecting indices/aliases, tenant filters, routing, and sort fields.

## 3. Translating request DTOs into application criteria

Do not pass `ProductSearchRequest` deep into every repository or query builder. Creating a normalized internal type decouples the HTTP contract from search logic.

~~~java
public record ProductSearchCriteria(
    String query,
    ProductStatus status,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    int page,
    int size,
    ProductSort sort,
    SortDirection direction,
    boolean includeFacets
) {}
~~~

A factory or mapper converts the request into criteria:

~~~java
@Component
public class ProductSearchCriteriaMapper {

    public ProductSearchCriteria toCriteria(
            ProductSearchRequest request) {

        validatePriceRange(request);

        return new ProductSearchCriteria(
            normalizeQuery(request.query()),
            request.status(),
            request.minPrice(),
            request.maxPrice(),
            request.page() == null ? 0 : request.page(),
            request.size() == null ? 20 : request.size(),
            request.sort() == null
                ? ProductSort.RELEVANCE
                : request.sort(),
            request.direction() == null
                ? SortDirection.DESC
                : request.direction(),
            Boolean.TRUE.equals(request.includeFacets())
        );
    }

    private String normalizeQuery(String query) {
        if (query == null || query.isBlank()) {
            return null;
        }
        return query.trim();
    }

    private void validatePriceRange(ProductSearchRequest request) {
        if (request.minPrice() != null
                && request.maxPrice() != null
                && request.minPrice().compareTo(request.maxPrice()) > 0) {
            throw new InvalidSearchRequestException(
                "minPrice must not exceed maxPrice"
            );
        }
    }
}
~~~

Criteria can include a tenant ID or scope obtained from the authenticated context inside the service. Never put a client-supplied tenant ID into criteria and treat it as trusted.

A service flow can accept criteria and a separate tenant context:

~~~java
public ProductSearchResponse search(
        ProductSearchCriteria criteria,
        String trustedTenantId) {
    // Build query with mandatory tenant filter.
    // Execute search and map results.
}
~~~

If the tenant is resolved from the security principal, the service should call an abstraction like `CurrentTenant` instead of accepting an arbitrary string from the controller.

## 4. Designing response DTOs for domain content

Response items should include only fields the client needs. Example:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    ProductStatus status,
    BigDecimal price,
    String currency
) {}
~~~

Mapper converting entities to DTOs:

~~~java
@Component
public class ProductResponseMapper {

    public ProductSearchItem toItem(Product product) {
        return new ProductSearchItem(
            product.getId(),
            product.getName(),
            ProductStatus.valueOf(product.getStatus()),
            product.getPrice(),
            "VND"
        );
    }
}
~~~

In production code, avoid calling `valueOf` if the source might contain legacy or null values without a handling policy. Write an explicit status mapper and turn invalid data into a contextual mapping error.

### Do not serialize entities directly

A response should not automatically include:

- Internal tenant IDs if the API does not need to expose them.
- Fields used for indexing/debugging.
- Internal supplier codes.
- Elasticsearch versions, sequence numbers, or primary terms unless the API commits to providing them.
- Raw source documents.
- Fields purely for migration or analyzers.
- Undefined internal scoring/debug metadata.

DTOs allow intentional selection of which fields are published and which data types remain stable for clients.

### DTOs can differ structurally from entities

An entity might store `firstName` and `lastName`, while the response returns `displayName`. A nested structure can be condensed into a variant summary. Some fields can be combined or unit-converted.

This is why mappers should be explicit, unit-tested components rather than relying on a JSON serializer to turn entities into responses.

## 5. What do SearchHit and SearchHits contain?

Spring Data Elasticsearch provides metadata-rich result types.

- `SearchHit<T>` represents a single hit and contains entity content alongside hit metadata.
- `SearchHits<T>` represents a collection of hits and contains aggregate information about the search result.
- `SearchPage<T>` can combine paging abstractions with search hit metadata in supported APIs.

A `SearchHit` can provide:

- Document ID.
- Index containing the document.
- Entity content.
- Relevance score.
- Highlight fields.
- Sort values.
- Inner hits if used by the query.
- Other hit metadata depending on version.

`SearchHits` can provide:

- List of `SearchHit`.
- Total hit count and total hits relation.
- Max score.
- Aggregations.
- Suggest metadata.
- Scroll ID or other details depending on the operation.

Do not return raw `SearchHit` or `SearchHits` over REST. These are framework types containing implementation details that rarely belong in an API contract. Map only what is genuinely needed into response DTOs.

### SearchHit is more than just the entity

If code calls:

~~~java
SearchHit<Product> hit = ...;
Product product = hit.getContent();
~~~

then score, highlights, and sort values remain on the hit. If you map to `Product` immediately and discard the hit, that metadata is unavailable downstream.

When the response requires scores or highlights, preserve `SearchHit` until the response mapper.

## 6. Defining a metadata envelope

A search response typically has two parts: the list of items and metadata describing the result.

Example contract:

~~~json
{
  "items": [
    {
      "id": "P-100",
      "name": "Wireless Keyboard",
      "status": "ACTIVE",
      "price": 790000,
      "currency": "VND"
    }
  ],
  "metadata": {
    "pagination": {
      "page": 0,
      "size": 20,
      "returned": 1,
      "totalHits": 1,
      "totalHitsRelation": "EXACT",
      "hasNext": false
    },
    "sort": {
      "field": "RELEVANCE",
      "direction": "DESC"
    },
    "execution": {
      "tookMillis": 12
    }
  }
}
~~~

The response can be modeled using records:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    SearchMetadata metadata
) {}

public record SearchMetadata(
    PaginationMetadata pagination,
    SortMetadata sort,
    ExecutionMetadata execution,
    List<FacetMetadata> facets
) {}

public record PaginationMetadata(
    int page,
    int size,
    int returned,
    Long totalHits,
    TotalHitsAccuracy totalHitsAccuracy,
    Boolean hasNext
) {}

public enum TotalHitsAccuracy {
    EXACT,
    LOWER_BOUND,
    NOT_REQUESTED
}

public record SortMetadata(
    ProductSort field,
    SortDirection direction
) {}

public record ExecutionMetadata(
    Long tookMillis,
    Float maxScore
) {}

public record FacetMetadata(
    String name,
    List<FacetBucket> buckets
) {}

public record FacetBucket(
    String key,
    long count
) {}
~~~

A structured envelope ensures clients never have to guess where metadata lives. Metadata fields may vary by query type, but semantics must remain consistent.

### Metadata is part of the public contract

Once clients rely on `page`, `totalHits`, `score`, or `facets`, those fields become part of the API contract. Never silently rename them, change their types, or alter their meaning simply because Spring Data or Elasticsearch changes.

Define clearly:

- Whether `totalHits` is exact or a lower bound.
- Whether `page` is 0-based or 1-based.
- Whether `size` is the requested max items or actual returned count.
- `returned` as the actual number of items in the response.
- Whether `hasNext` is derived from an exact total or a fetch strategy.
- What `tookMillis` measures.
- Under what conditions `score` may be null.
- Whether `facets` can be absent, empty, or unrequested.

## 7. Pagination and total hits

A paginated response usually needs:

- `page`: page number.
- `size`: maximum items per page.
- `returned`: actual number of items returned.
- `totalHits`: number of matching hits.
- `totalHitsAccuracy`: accuracy of the total count.
- `hasNext`: whether a next page may exist.

Do not assume `totalHits` is always exact. Elasticsearch may cap total hit counting to save cost, depending on query options and version. Search responses can indicate total hits relation as equal-to or greater-than-or-equal-to.

Therefore, do not name a field `exactTotal` if the query does not request exact counting.

### Mapping metadata from SearchHits

Example:

~~~java
private PaginationMetadata toPagination(
        SearchHits<Product> hits,
        int page,
        int size) {

    long totalHits = hits.getTotalHits();

    TotalHitsAccuracy accuracy =
        mapAccuracy(hits.getTotalHitsRelation());

    int returned = hits.getSearchHits().size();

    return new PaginationMetadata(
        page,
        size,
        returned,
        totalHits,
        accuracy,
        accuracy == TotalHitsAccuracy.EXACT
            ? (long) (page + 1) * size < totalHits
            : null
    );
}
~~~

Enum names, `getTotalHitsRelation` methods, and return types depend on the Spring Data Elasticsearch version. This snippet illustrates mapping the relation to an internal contract. If the relation is unavailable in the current API, do not blindly assign `EXACT`; use `NOT_REQUESTED` or an appropriate status.

With a lower-bound total, `hasNext` cannot be computed accurately from `totalHits` alone. You can use a fetch-one-extra strategy, cursor pagination, or return `hasNext` according to defined semantics.

### Page numbers and offsets

`PageRequest.of(page, size)` uses a 0-based page index. If the HTTP API exposes 1-based pages, translate them in both the request mapper and the response mapper. Never let controllers, services, and clients each follow a different convention.

Offset pagination suits initial and shallow pages. For deep pages, Elasticsearch imposes limits and costs on `from/size`. `search_after` or cursor pagination may be better suited.

## 8. Sort metadata should reflect public choices

Requests should not send arbitrary field names. Use an enum:

~~~java
public enum ProductSort {
    RELEVANCE,
    NAME,
    PRICE,
    CREATED_AT
}
~~~

The server maps the enum to allowlisted fields:

~~~java
private String toSortField(ProductSort sort) {
    return switch (sort) {
        case NAME -> "name.keyword";
        case PRICE -> "price";
        case CREATED_AT -> "createdAt";
        case RELEVANCE -> "_score";
    };
}
~~~

The field name `name.keyword` is valid only if the actual mapping defines that multi-field. Mappings and sort fields must stay aligned when creating indices.

Responses should return the sort field using API vocabulary, such as `PRICE`, rather than necessarily returning the Elasticsearch field name `price`. This keeps the API decoupled from mapping details.

### Stable sorts

If multiple documents share the same price or name, sorting solely on that field can produce unstable ordering across pages. Add a deterministic tie-breaker, such as document ID or a unique-valued field compatible with your Elasticsearch version and sort semantics.

Response metadata can expose the primary sort choice requested by the client while keeping the tie-breaker as an internal implementation detail. If clients use cursors, the cursor must retain enough sort values to resume at the exact position.

## 9. Score and relevance metadata

Relevance score is metadata of a search hit, not a domain attribute of `Product`. Do not add `score` to the entity just to return it in a response.

DTOs may include a `score` field depending on the API:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Float score
) {}
~~~

The mapper receives `SearchHit`:

~~~java
private ProductSearchItem toItem(SearchHit<Product> hit) {
    Product product = hit.getContent();

    return new ProductSearchItem(
        product.getId(),
        product.getName(),
        product.getPrice(),
        hit.getScore()
    );
}
~~~

Scores may be null or meaningless for certain query/sort types, such as queries that do not compute relevance or sort purely by field. Do not let clients assume `score` is always populated or comparable across different queries.

If scores are only used internally for sorting, you may omit them from the response. Only include `score` in responses when clients actually need it and its semantics are documented.

Do not treat `score` as a probability or percentage relevance without a separate calibration model.

## 10. Highlight metadata

Highlights return fragments containing query-matching text segments. This is hit metadata, not original entity content.

A response may include:

~~~json
{
  "id": "P-100",
  "name": "Wireless Keyboard",
  "highlights": {
    "name": [
      "Wireless <em>Keyboard</em>"
    ]
  }
}
~~~

A DTO can define:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    Map<String, List<String>> highlights
) {}
~~~

The mapper retrieves highlights from `SearchHit`:

~~~java
private Map<String, List<String>> toHighlights(
        SearchHit<Product> hit) {

    return hit.getHighlightFields();
}
~~~

Return types and methods for retrieving highlights may vary by Spring Data version. If highlighting is not enabled in the query, the map may be empty.

### HTML in highlights

Some highlighters emit fragments with tags like `em` or `strong`. Never render fragments as arbitrary HTML if the underlying content could contain untrusted markup.

You can choose one of these contracts:

- Return plain-text fragments and offset/position metadata.
- Return markup sanitized against an allowlist.
- Return fragments with explicit marker tokens so the frontend can render safely.

Do not implicitly promise that every fragment is safe HTML.

## 11. Facet and aggregation metadata

Facets let clients display filters such as product counts by status, brand, or category. In Elasticsearch, facets are typically built from aggregations.

Example response:

~~~json
{
  "facets": [
    {
      "name": "status",
      "buckets": [
        { "key": "ACTIVE", "count": 120 },
        { "key": "DISCONTINUED", "count": 8 }
      ]
    }
  ]
}
~~~

DTOs:

~~~java
public record FacetMetadata(
    String name,
    List<FacetBucket> buckets
) {}

public record FacetBucket(
    String key,
    long count
) {}
~~~

Never return raw Elasticsearch aggregation objects. Map aggregations into a stable business structure.

### Facet and bucket names

Public facet names can be `status`, `brand`, or `category`. They do not need to match internal aggregation names like `status_facet_v2`. This lets you rename aggregations without breaking the API.

Bucket keys should have clear data types. If a facet has numeric or date-range keys, consider specialized DTOs instead of coercing everything into `String` without documenting semantics.

### Aggregation counts are not always exact

Some distributed aggregations may return approximate results or have error bounds depending on aggregation type and settings. If clients rely on facet counts for exact decisions, understand the aggregation semantics and expose accuracy information where appropriate.

Do not promise every facet count is exact if the aggregation can be approximate.

## 12. Cursor metadata for search_after

For large result sets, cursor pagination can be better suited than offset pagination. Elasticsearch `search_after` uses the sort values of the last hit to continue to the next page.

Do not expose a raw array of sort values as a public API if you want to keep implementation flexibility. Return an opaque cursor:

~~~json
{
  "items": [],
  "metadata": {
    "cursor": {
      "next": "eyJ2IjoxLCJzIjpbNzkwMDAwLCJQLTEwMF19"
    }
  }
}
~~~

A cursor is a server-generated token containing the data needed to resume the query. The server can encode a versioned payload and sign the token to prevent client tampering. If the cursor encodes tenant, filter, or sort state, verify that it still matches the current request and principal upon use.

### A cursor is not an access grant

A cursor merely resumes a read position. It does not replace authorization, tenant filters, or request-scope checks. A client-submitted cursor must never be allowed to widen data scope.

### Keep cursor contracts stable

Cursors should carry an internal version so the server can evolve payload structure. Clients simply store and send back the token without needing to know internal sort values or field mappings.

If the index changes significantly or a search context snapshot expires, the server should return a clear expired/invalid cursor error per contract.

## 13. Execution duration and technical metadata

A response can expose `tookMillis`, but you must define what it measures.

An Elasticsearch response may report cluster-side processing time. Elapsed time measured in the application service includes network, mapping, and server-side code. The two numbers are not the same.

You can separate names clearly:

- `elasticsearchTookMillis`: time Elasticsearch reported for the search operation.
- `serviceElapsedMillis`: time measured by the service from start to finish.
- `returned`: number of items produced by the response mapper.

Do not lump multiple measurements into one `took` field if clients might misinterpret it.

### Do not expose all debug metadata

Do not return node names, shard IDs, raw Query DSL, cluster endpoints, or internal index names in public responses unless a genuine use case demands it. Such information can leak infrastructure details or create client coupling to implementation internals.

Log them into structured logs or internal tracing with appropriate access controls instead.

## 14. Mapping SearchHits to the response envelope

A mapper can accept `SearchHits` and criteria:

~~~java
@Component
public class ProductSearchResponseMapper {

    private final ProductResponseMapper productMapper;

    public ProductSearchResponseMapper(
            ProductResponseMapper productMapper) {
        this.productMapper = productMapper;
    }

    public ProductSearchResponse toResponse(
            SearchHits<Product> hits,
            ProductSearchCriteria criteria) {

        List<ProductSearchItem> items =
            hits.getSearchHits().stream()
                .map(this::toSearchItem)
                .toList();

        SearchMetadata metadata = new SearchMetadata(
            toPagination(hits, criteria.page(), criteria.size()),
            new SortMetadata(
                criteria.sort(),
                criteria.direction()
            ),
            new ExecutionMetadata(
                null,
                hits.getMaxScore()
            ),
            List.of()
        );

        return new ProductSearchResponse(items, metadata);
    }

    private ProductSearchItem toSearchItem(
            SearchHit<Product> hit) {
        Product product = hit.getContent();

        return new ProductSearchItem(
            product.getId(),
            product.getName(),
            product.getStatus(),
            product.getPrice(),
            "VND",
            hit.getScore(),
            hit.getHighlightFields()
        );
    }
}
~~~

This is an illustrative skeleton; `ProductSearchItem` and `SearchMetadata` constructors must align with the DTOs chosen in your project. `SearchHits` methods and relation types must match your Spring Data version.

A separate mapper helps:

- Keep controllers thin.
- Decouple framework metadata from public contracts.
- Unit-test score/highlight/total-hits mapping.
- Evolve entities with minimal impact on responses.
- Normalize different query types into a consistent envelope.

### Avoid mapping metadata in the controller

Controllers should receive requests, call services, and return DTOs. If controllers directly read `SearchHits`, calculate total pages, extract highlights, and convert entities, different endpoints will easily diverge in semantics.

## 15. Complete controller and service

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductSearchController {

    private final ProductSearchService searchService;

    public ProductSearchController(
            ProductSearchService searchService) {
        this.searchService = searchService;
    }

    @PostMapping("/search")
    public ProductSearchResponse search(
            @Valid @RequestBody ProductSearchRequest request) {
        return searchService.search(request);
    }
}
~~~

Service:

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchCriteriaMapper criteriaMapper;
    private final ProductQueryFactory queryFactory;
    private final ElasticsearchOperations operations;
    private final ProductSearchResponseMapper responseMapper;
    private final CurrentTenant currentTenant;

    public ProductSearchService(
            ProductSearchCriteriaMapper criteriaMapper,
            ProductQueryFactory queryFactory,
            ElasticsearchOperations operations,
            ProductSearchResponseMapper responseMapper,
            CurrentTenant currentTenant) {
        this.criteriaMapper = criteriaMapper;
        this.queryFactory = queryFactory;
        this.operations = operations;
        this.responseMapper = responseMapper;
        this.currentTenant = currentTenant;
    }

    public ProductSearchResponse search(
            ProductSearchRequest request) {

        ProductSearchCriteria criteria =
            criteriaMapper.toCriteria(request);

        String tenantId = currentTenant.requireTenantId();

        Query query = queryFactory.create(criteria, tenantId);

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return responseMapper.toResponse(hits, criteria);
    }
}
~~~

`ProductQueryFactory` is responsible for creating the query from criteria and tenant context. It can use `NativeQuery` to combine match, filter, range, sort, pageable, and aggregations.

The service does not return entities or `SearchHits` directly. The response mapper transforms results into the HTTP contract.

### Do not put ElasticsearchOperations into controllers

Controllers should not know how to choose indices, construct Query DSL, or read `SearchHit` metadata. Those responsibilities belong in the application/service layer.

## 16. Error responses are also a DTO contract

Invalid requests, expired cursors, Elasticsearch timeouts, or mapping errors should be represented by a stable error response.

Example:

~~~json
{
  "error": {
    "code": "INVALID_SEARCH_RANGE",
    "message": "minPrice must not exceed maxPrice",
    "details": [
      {
        "field": "minPrice",
        "reason": "must be less than or equal to maxPrice"
      }
    ],
    "traceId": "c2b5e3a1"
  }
}
~~~

DTOs:

~~~java
public record ApiErrorResponse(
    ApiError error
) {}

public record ApiError(
    String code,
    String message,
    List<ApiErrorDetail> details,
    String traceId
) {}

public record ApiErrorDetail(
    String field,
    String reason
) {}
~~~

Use `ControllerAdvice` to convert exceptions into responses:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidSearchRequestException.class)
    ResponseEntity<ApiErrorResponse> handleInvalidSearch(
            InvalidSearchRequestException ex) {

        ApiError error = new ApiError(
            "INVALID_SEARCH_REQUEST",
            ex.getMessage(),
            List.of(),
            null
        );

        return ResponseEntity.badRequest()
            .body(new ApiErrorResponse(error));
    }
}
~~~

Never return stack traces, raw Elasticsearch exceptions, internal index names, or Query DSL to clients. Log full technical details internally per security policy, and return error codes that clients can handle.

### Error classification

Errors can be mapped to:

- 400: invalid input.
- 404: domain resource does not exist per contract.
- 409: conflict or version conflict if the API defines these semantics.
- 429: rate limit or overload per policy.
- 503: Elasticsearch dependency temporarily unavailable.
- 500: mapping errors or unexpected internal failures.

Do not map every Elasticsearch exception to 500 or every empty result to 404. Classify by cause and expected API behavior.

## 17. Versioning and response compatibility

API DTOs are contracts with clients. When adding fields, changing enums, or altering metadata semantics, evaluate the impact on existing clients.

Principles:

- Adding optional response fields is generally less breaking than changing existing fields.
- Do not change a number type to a string without versioning.
- Do not silently switch page indexing from 0 to 1.
- Do not change `totalHits` from exact to lower-bound without updating the contract.
- Do not alter enum values already stored or compared by clients.
- Define policies for `null`, absent, and empty lists.
- Keep error codes stable.
- Use API versioning or migration plans for breaking changes.

### Null and absent fields

There are three distinct states:

- The field is omitted.
- The field appears with `null`.
- The field appears with an empty value such as `[]` or `""`.

Clients may interpret these differently. For example, absent `facets` might mean not requested; empty `facets` might mean computed with zero buckets. Choose one convention and apply it consistently.

### Do not expose internal enums directly

If an entity enum changes because of a legacy index, do not let the persistence enum dictate the JSON contract automatically. Use separate API enums or mappers to control public names and values.

## 18. Metadata contracts for multiple result types

Not every query has the same metadata. You can define a shared envelope alongside optional sections with clear semantics.

| Metadata | When used | Notes |
|---|---|---|
| pagination | Results are paginated | Document page/size/returned and total accuracy |
| sort | Client selects ordering | Return public choice, not necessarily raw field |
| score | Relevance is meaningful to client | Can be null and is not a probability |
| highlights | Query enables highlighting | Render fragments safely |
| facets | Query includes aggregations | Clarify whether bucket counts can be approximate |
| cursor | `search_after` or cursor paging | Opaque token bound to filter/sort/tenant |
| execution | Latency observability needed | Distinguish Elasticsearch time from service elapsed |
| warnings | Results are capped or partial | Use stable codes and explain semantics |

You can define specialized responses for search, autocomplete, geo search, or aggregation-only endpoints. Avoid stuffing every result type into a single overly generic DTO with dozens of nullable fields.

If endpoints have different item structures but share pagination metadata, reuse a small metadata record rather than a monolithic response class.

## 19. Testing request DTOs and validation

Unit tests for criteria mappers should verify:

- Default `page`, `size`, and `sort` values.
- Query strings are normalized per policy.
- `minPrice` greater than `maxPrice` is rejected.
- `size` exceeding the limit is rejected.
- Invalid enums are rejected by validation.
- Null/blank values are handled properly.
- No public input can override the tenant context.

Controller tests can use `MockMvc` or `WebTestClient` depending on stack to verify JSON requests are validated before the service is invoked.

Example mapper test:

~~~java
@Test
void rejectsInvalidPriceRange() {
    ProductSearchRequest request =
        new ProductSearchRequest(
            "keyboard",
            ProductStatus.ACTIVE,
            new BigDecimal("200"),
            new BigDecimal("100"),
            0,
            20,
            ProductSort.RELEVANCE,
            SortDirection.DESC,
            false
        );

    assertThatThrownBy(() -> mapper.toCriteria(request))
        .isInstanceOf(InvalidSearchRequestException.class);
}
~~~

Test both field-level validation errors and cross-field relationship errors. Do not test only the happy path.

## 20. Testing response mappers and metadata contracts

Response mapper unit tests should construct sample `SearchHit`/`SearchHits` or use suitable fixtures, and verify:

- Entity content maps accurately to DTOs.
- Internal fields do not appear.
- Scores map according to policy.
- Highlights map to the right fields.
- Total hits and relations transfer accurately.
- `page`, `size`, and `returned` have consistent semantics.
- Facets convert to bucket DTOs.
- Optional metadata is handled clearly.
- No raw `SearchHit` or `SearchHits` leak into the response object.

Contract tests checking JSON serialization can catch unintended field renames or type changes.

Example JSON assertion:

~~~java
mockMvc.perform(post("/api/products/search")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "query": "keyboard",
              "page": 0,
              "size": 20,
              "sort": "RELEVANCE"
            }
            """))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.metadata.pagination.page").value(0))
    .andExpect(jsonPath("$.metadata.pagination.size").value(20));
~~~

This is an illustrative structure; endpoints, fixtures, and JSON paths must match your actual API.

### Testing that internal fields are not exposed

You can serialize response DTOs and assert they do not contain `tenantId`, `internalSupplierCode`, or raw query metadata unless part of the public contract.

This test is especially valuable when fields are added to an entity. Because responses use dedicated DTOs, entity additions will not automatically alter JSON responses.

## 21. Integration tests for SearchHits metadata

Unit-testing mappers does not prove Elasticsearch returns the right scores, highlights, total hits, or aggregations. When such metadata is a core feature, write integration tests against a compatible Elasticsearch version.

For example:

- Seed documents containing keywords to match.
- Run a match query with highlights.
- Verify `SearchHit` contains highlight fragments.
- Verify scores exist when the query computes relevance.
- Run aggregations and verify bucket keys/counts.
- Configure appropriate total-hits tracking and verify the relation.
- Verify sort values when using cursors.
- Verify DTO mapping preserves required metadata.

Do not assert exact absolute score values without strong reason, because scores shift when analyzers, corpora, or queries change. Typically assert that hits are ordered by relevance or that scores have valid values.

## 22. Common design mistakes

| Symptom | Cause | Solution |
|---|---|---|
| Response changes when adding entity field | Controller serializes entity directly | Use response DTOs and mappers |
| Clients send arbitrary sort field names | Request DTO accepts raw field names | Use enums and allowlists |
| Clients send raw Query DSL | API exposes Elasticsearch implementation | Use typed request criteria |
| Scores/highlights get lost | Mapping `SearchHit` to entity too early | Keep `SearchHit` until response mapper |
| Wrong total pages | Assuming `totalHits` is always exact | Expose total relation/accuracy |
| Wrong `hasNext` with lower-bound total | Computing next page from inaccurate count | Use cursors or fetch one extra hit |
| Next page has duplicate/missing items | Unstable sort | Add deterministic tie-breaker |
| Clients depend on index field names | Response returns raw mapping fields | Return enums/business names |
| Highlights cause XSS | Rendering unsanitized HTML fragments | Return plain text or allowlist-sanitized HTML |
| Facet counts assumed exact | Aggregation semantics undisclosed | Document accuracy/error bounds properly |
| Cursors tampered or used cross-tenant | Token not bound to request context | Sign token and verify tenant/filters |
| Error responses leak infrastructure | Returning raw exceptions or queries | Use error DTOs and internal logging |
| Null and empty list used interchangeably | No defined contract | Specify absent/null/empty policies |
| Unintended breaking API changes | No contract tests/versioning | Add serialization and compatibility tests |

## 23. DTO and metadata design checklist

- [ ] Request DTOs express business needs, not Query DSL.
- [ ] Validate query length, ranges, page, and size at the boundary.
- [ ] Use enums/allowlists for sort fields and directions.
- [ ] Do not accept arbitrary index, routing, or tenant scope from clients.
- [ ] Translate requests into internal application criteria.
- [ ] Elasticsearch entities are never returned directly from controllers.
- [ ] Response DTOs contain only necessary public fields.
- [ ] Retain `SearchHit` when scores, highlights, or sort values are needed.
- [ ] Map `SearchHits` metadata into dedicated DTOs.
- [ ] Define page index, size, returned count, and `totalHits` accuracy.
- [ ] Do not promise exact `totalHits` if Elasticsearch returns a lower bound.
- [ ] Use stable sorting for pagination.
- [ ] Use opaque cursors for `search_after` when appropriate.
- [ ] Expose `score` only when its semantics are clear.
- [ ] Sanitize or safely structure highlight fragments.
- [ ] Map aggregations into stable facet DTOs.
- [ ] Distinguish Elasticsearch `took` from service elapsed time.
- [ ] Error responses have stable codes and never leak raw exceptions.
- [ ] Unit tests cover criteria mappers and response mappers.
- [ ] Controller/serialization contract tests exist.
- [ ] Elasticsearch integration tests verify real metadata.
- [ ] A versioning strategy exists for breaking changes.

Request DTOs, response DTOs, and metadata envelopes create a stable boundary between the API and Elasticsearch. Request DTOs accept only validated business selections; application criteria convert them into controlled queries; response mappers turn entities and `SearchHit` metadata into a clear public contract. By precisely defining pagination, total-hit accuracy, sorting, scores, highlights, facets, cursors, and error responses, clients do not depend on `SearchHits` or internal mappings. This lets applications evolve indices and query strategies while keeping the API consistent.
