# Reusing Query Builders and DTO Mapping

In a Spring Data Elasticsearch application, multiple screens and services may need to search the same set of documents with different conditions, sort orders, and return payloads. If every repository method or service builds Query DSL manually and converts `SearchHit` results into responses on its own, search logic gets duplicated, mappings become hard to govern, and inconsistencies easily creep in across APIs.

A clean way to structure this is to separate three responsibilities:

1. **Application filter/criteria:** describes what the user wants to find using domain types, independent of Elasticsearch DSL.
2. **Query builder/factory:** translates filters into `CriteriaQuery` or `NativeQuery`, applying mandatory filters, sorting, and pagination under shared rules.
3. **DTO mapper:** converts `SearchHit`, entities, or aggregation results into DTOs for the API/UI, exposing only allowed fields.

These components can be reused across custom repository fragments. The main repository simply composes the search fragment, while the implementation receives the query factory and mapper via constructor injection.

```text
Controller / API
       |
       v
ProductSearchFilter (domain/application criteria)
       |
       v
ProductSearchFragment
       |
       +---- ProductQueryFactory
       |          |
       |          +---- CriteriaQuery / NativeQuery
       |
       +---- ElasticsearchOperations.search(...)
       |
       +---- ProductSearchMapper
                  |
                  +---- SearchHit<ProductDocument> -> ProductCardDto
       |
       v
ProductSearchResultDto
```

Separating these layers lets you evolve Query DSL without coupling controllers to Elasticsearch, while keeping DTO mapping rules consistent across multiple repositories and services.

## 1. Why Reuse Query Builders and DTO Mappers?

Suppose a system has these use cases:

- A product listing page filtering by status, category, and price range.
- An admin page searching by name, SKU, and status.
- A product suggestion API needing only ID, name, image, and price.
- A statistical report counting products by category.
- An internal service finding similar products by keyword and availability conditions.

If each use case builds queries and maps responses independently, shared rules get duplicated:

- Tenant filters or document access permissions.
- Conditions restricting results to visible products.
- Keyword and price-range normalization.
- Default sorting and page size limits.
- Mapping `SearchHit` into DTOs.
- How scores, highlights, and total hits are exposed.
- How missing/null fields are handled.

Duplication easily creates inconsistent bugs. For example, one endpoint forgets the tenant filter, another allows sorting by an unsupported field, or a DTO accidentally returns the entire entity containing internal fields.

Reuse pays off when it centers on genuinely shared rules. Do not build an overly complex generic query framework just to save a few lines of code. Start with a filter, a query builder, and a mapper with clear responsibilities.

## 2. Separating Application Filters from Elasticsearch DSL

Controllers should not accept `Criteria`, `NativeQuery`, `Query`, or JSON DSL as request models. Those are infrastructure details and couple the API directly to Elasticsearch libraries.

Instead, define filters using domain/application types:

```java
import java.math.BigDecimal;

public record ProductSearchFilter(
        String keyword,
        String status,
        String categoryId,
        BigDecimal minPrice,
        BigDecimal maxPrice
) {
}
```

This filter expresses search intent. It does not dictate whether the query uses `match`, `term`, `range`, `bool`, or `nested`.

### 2.1. Normalizing and Validating Filters

Before building a query, normalize inputs:

```java
import java.math.BigDecimal;

public record ProductSearchFilter(
        String keyword,
        String status,
        String categoryId,
        BigDecimal minPrice,
        BigDecimal maxPrice
) {

    public ProductSearchFilter normalized() {
        String normalizedKeyword = keyword == null || keyword.isBlank()
                ? null
                : keyword.trim();

        String normalizedStatus = status == null || status.isBlank()
                ? null
                : status.trim().toUpperCase();

        String normalizedCategory = categoryId == null || categoryId.isBlank()
                ? null
                : categoryId.trim();

        return new ProductSearchFilter(
                normalizedKeyword,
                normalizedStatus,
                normalizedCategory,
                minPrice,
                maxPrice
        );
    }

    public void validate() {
        if (minPrice != null && maxPrice != null
                && minPrice.compareTo(maxPrice) > 0) {
            throw new IllegalArgumentException(
                    "minPrice must be less than or equal to maxPrice");
        }
        if (minPrice != null && minPrice.signum() < 0) {
            throw new IllegalArgumentException("minPrice must not be negative");
        }
        if (maxPrice != null && maxPrice.signum() < 0) {
            throw new IllegalArgumentException("maxPrice must not be negative");
        }
    }
}
```

This is an example of application-layer validation. In applications using Bean Validation, you can declare custom constraints for price ranges and validate at the controller or service layer. Do not force the query builder to guess how to handle invalid inputs.

### 2.2. Using Enums for Finite Value Sets

If status only has a handful of valid values, use an enum instead of an arbitrary string:

```java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
```

The filter can accept `ProductStatus status`. The query factory converts the enum to the value stored in the index. This reduces typos and clarifies the API contract.

### 2.3. Filters Are Not Access Control

Some conditions must come from the security context, such as a tenant ID or the scope of data a user is permitted to view. Never trust a client-supplied `tenantId` when it acts as a security boundary.

You can separate user filters from the security context:

```java
public record SearchScope(String tenantId, boolean includeArchived) {
}
```

The service obtains `SearchScope` from the authentication/authorization layer and passes it to the query factory. The query builder must always add the mandatory tenant filter, even when the search filter has no conditions set.

## 3. Designing a Reusable Query Factory

A query factory takes a filter and returns a Spring Data `Query`. Controllers and services do not need to know the underlying DSL.

```java
import org.springframework.data.elasticsearch.core.query.Query;

public interface ProductQueryFactory {
    Query build(ProductSearchFilter filter, SearchScope scope);
}
```

An implementation can use `CriteriaQuery`:

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public class CriteriaProductQueryFactory implements ProductQueryFactory {

    @Override
    public Query build(ProductSearchFilter rawFilter, SearchScope scope) {
        ProductSearchFilter filter = rawFilter.normalized();
        filter.validate();

        Criteria criteria = new Criteria("tenant_id").is(scope.tenantId());

        if (filter.status() != null) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.categoryId() != null) {
            criteria = criteria.and("category_id").is(filter.categoryId());
        }

        if (filter.keyword() != null) {
            criteria = criteria.and("name").matches(filter.keyword());
        }

        if (filter.minPrice() != null) {
            criteria = criteria.and("price").greaterThanEqual(filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            criteria = criteria.and("price").lessThanEqual(filter.maxPrice());
        }

        return new CriteriaQuery(criteria);
    }
}
```

Field names in this example are entity properties. Spring Data mapping translates property names to Elasticsearch field names according to `@Field` metadata. When queries are built with raw Elasticsearch Java API DSL, you generally need to use exact index field names.

The `Criteria` API and available methods can differ across Spring Data Elasticsearch versions. Use the API matching your project dependencies; the architectural goal is keeping condition-building logic in one place, not forcing every use case into a single DSL.

### 3.1. Applying Pagination and Sorting

You can pass `Pageable` from the service into the query factory or apply it in the repository fragment. An extended interface version:

```java
public interface ProductQueryFactory {
    Query build(ProductSearchFilter filter, SearchScope scope, Pageable pageable);
}
```

Implementation:

```java
@Override
public Query build(
        ProductSearchFilter rawFilter,
        SearchScope scope,
        Pageable pageable) {

    Criteria criteria = buildCriteria(rawFilter, scope);
    CriteriaQuery query = new CriteriaQuery(criteria);
    query.setPageable(pageable);
    return query;
}
```

`setPageable` applies page, size, and sort to the query. If your version uses a different builder API, create the `CriteriaQuery` and configure pagination with the corresponding API.

### 3.2. Whitelisting Sort Fields

Never pass arbitrary sort field names straight from a request into Elasticsearch. Use an allowlist:

```java
public enum ProductSortField {
    NAME("name"),
    PRICE("price"),
    CREATED_AT("createdAt");

    private final String property;

    ProductSortField(String property) {
        this.property = property;
    }

    public String property() {
        return property;
    }
}
```

The service translates the validated choice into a `Sort`:

```java
Sort sort = Sort.by(Sort.Direction.DESC, ProductSortField.PRICE.property());
Pageable pageable = PageRequest.of(page, size, sort);
```

Cap the maximum page size and allow sorting only on fields with appropriate mappings. Sorting on a `text` field typically requires a keyword subfield; sorting on numeric or date fields requires the proper mapping type.

## 4. Reusing Query Condition Pieces

When multiple queries share certain conditions, extract small helpers:

```java
private Criteria addStatus(Criteria criteria, ProductStatus status) {
    return status == null
            ? criteria
            : criteria.and("status").is(status.name());
}

private Criteria addTenant(Criteria criteria, String tenantId) {
    return criteria.and("tenant_id").is(tenantId);
}

private Criteria addPriceRange(
        Criteria criteria,
        BigDecimal min,
        BigDecimal max) {

    if (min != null) {
        criteria = criteria.and("price").greaterThanEqual(min);
    }
    if (max != null) {
        criteria = criteria.and("price").lessThanEqual(max);
    }
    return criteria;
}
```

The query factory calls these helpers in sequence. Only extract a helper when a condition has clear standalone meaning or is genuinely reused. Avoid creating a generic method like `addAnyFieldOperator(String field, String operator, Object value)` if it makes queries harder to read and opens the door to arbitrary fields or operators.

### 4.1. Reusing Mandatory Filters

Tenant filters, visibility filters, or soft-delete filters usually must appear in every query within a data scope. Put them inside the query factory or a shared policy class to reduce the risk of an endpoint forgetting to apply them.

Example:

```java
private Criteria baseCriteria(SearchScope scope) {
    return new Criteria("tenant_id").is(scope.tenantId())
            .and("deleted").is(false);
}
```

Security filters must apply even to queries with no keyword, status, or price filters. Never let an empty filter accidentally become a match-all query across every tenant.

### 4.2. Avoid Reusing Mutable Query Objects

Do not create a mutable `Criteria`, `CriteriaQuery`, or `NativeQuery` as a singleton and mutate it per request. Under concurrent requests, conditions can leak across requests or the query can be modified mid-execution.

Instantiate fresh objects on every factory call. Only reuse immutable configuration such as allowlists, field mapping constants, or pure helpers.

## 5. Using `NativeQuery` for Complex Queries

`CriteriaQuery` fits standard conditions. When you need `nested`, `geo_distance`, `function_score`, `script`, aggregations, or specialized Query DSL, write a factory that returns `NativeQuery`.

The abstraction can still return `Query`:

```java
public interface ProductQueryFactory {
    Query build(ProductSearchFilter filter, SearchScope scope, Pageable pageable);
}
```

A `NativeQuery` implementation using the Elasticsearch Java API Client:

A clearer example:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

public org.springframework.data.elasticsearch.core.query.Query buildNative(
        ProductSearchFilter filter,
        SearchScope scope,
        Pageable pageable) {

    List<Query> filters = new ArrayList<>();

    filters.add(Query.of(q -> q
            .term(t -> t
                    .field("tenant_id")
                    .value(FieldValue.of(scope.tenantId()))
            )
    ));

    if (filter.status() != null) {
        filters.add(Query.of(q -> q
                .term(t -> t
                        .field("status")
                        .value(FieldValue.of(filter.status()))
                )
        ));
    }

    Query boolQuery = Query.of(q -> q
            .bool(b -> b.filter(filters))
    );

    return NativeQuery.builder()
            .withQuery(boolQuery)
            .withPageable(pageable)
            .build();
}
```

This is a minimal dynamic query example. Exact Java API Client builder methods depend on the client version; for `range` queries, value types and generated DSL can vary across client releases. Keep imports explicit because both the Elasticsearch Java API Client and Spring Data define a type named `Query`.

### 5.1. Choosing CriteriaQuery vs. NativeQuery

| Requirement | Usually appropriate choice |
|---|---|
| Exact filters, ranges, simple AND/OR conditions | `CriteriaQuery`. |
| Queries varying across many optional filters | Query factory with `CriteriaQuery` or `NativeQuery`. |
| Complex nested queries | `NativeQuery`. |
| Geo distance / function score / scripts | `NativeQuery`. |
| Complex aggregations | `NativeQuery`. |
| Short static query tied to one repository method | `@Query`. |
| Common conditions well expressed by method names | Derived query. |

You do not have to force every query onto one API. Multiple specialized factories can implement the same interface when the response contract is identical.

## 6. Repository Fragments Using Query Factories

To reuse a builder in a custom repository, declare a fragment:

```java
public interface ProductSearchFragment {
    ProductSearchResult search(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable);
}
```

The main repository composes the fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchFragment {
}
```

Implementation following the fragment naming convention:

```java
public class ProductSearchFragmentImpl implements ProductSearchFragment {

    private final ElasticsearchOperations operations;
    private final ProductQueryFactory queryFactory;
    private final ProductSearchMapper mapper;

    public ProductSearchFragmentImpl(
            ElasticsearchOperations operations,
            ProductQueryFactory queryFactory,
            ProductSearchMapper mapper) {
        this.operations = operations;
        this.queryFactory = queryFactory;
        this.mapper = mapper;
    }

    @Override
    public ProductSearchResult search(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable) {

        Query query = queryFactory.build(filter, scope, pageable);
        SearchHits<ProductDocument> hits =
                operations.search(query, ProductDocument.class);

        List<ProductCardDto> content = hits.getSearchHits().stream()
                .map(mapper::toCard)
                .toList();

        return new ProductSearchResult(
                content,
                hits.getTotalHits(),
                hits.getTotalHitsRelation().name(),
                pageable.getPageNumber(),
                pageable.getPageSize()
        );
    }
}
```

The name `ProductSearchFragmentImpl` defaults to the fragment interface name plus `Impl`. If the project configures a different repository implementation postfix, the class name must follow that postfix.

`ElasticsearchOperations.search` returns `SearchHits<T>`, preserving both entities and per-hit metadata. The mapper can consume that metadata before returning DTOs.

## 7. Designing DTOs for Search Results

Do not return Elasticsearch entities directly from an API if the entity contains internal fields or mapping-specific metadata.

Example DTO for a product card:

```java
import java.math.BigDecimal;
import java.util.List;

public record ProductCardDto(
        String id,
        String name,
        BigDecimal price,
        String status,
        Float score,
        List<String> highlights
) {
}
```

Aggregated result DTO:

```java
import java.util.List;

public record ProductSearchResult(
        List<ProductCardDto> items,
        long totalHits,
        String totalHitsRelation,
        int page,
        int size
) {
}
```

`totalHitsRelation` indicates whether total hits is exact or only a lower bound per Elasticsearch semantics. If an API returns only `totalHits` without the relation, clients may mistakenly assume the count is always exact.

If the API contract does not need scores or highlights, omit them from the DTO. Do not expose Elasticsearch metadata simply because `SearchHit` happens to provide it.

## 8. Mapping `SearchHit<T>` to DTOs

Spring Data Elasticsearch defines these result types:

- `SearchHit<T>`: a single hit containing content and metadata such as ID, score, sort values, and highlight fields.
- `SearchHits<T>`: a collection of hits plus overall metadata such as total hits, relation, and aggregations.
- `SearchPage<T>`: a pagination abstraction backed by search hits in supporting APIs.

When working directly with `SearchHits<T>.getSearchHits()`, the mapper accepts each `SearchHit<ProductDocument>`.

```java
import org.springframework.data.elasticsearch.core.SearchHit;

public interface ProductSearchMapper {
    ProductCardDto toCard(SearchHit<ProductDocument> hit);
}
```

Manual implementation:

```java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.elasticsearch.core.SearchHit;

public class ProductSearchMapperImpl implements ProductSearchMapper {

    @Override
    public ProductCardDto toCard(SearchHit<ProductDocument> hit) {
        ProductDocument document = hit.getContent();

        List<String> highlights = hit.getHighlightFields()
                .getOrDefault("name", List.of());

        return new ProductCardDto(
                hit.getId(),
                document.getName(),
                BigDecimal.valueOf(document.getPrice()),
                document.getStatus(),
                hit.getScore(),
                List.copyOf(highlights)
        );
    }
}
```

This example assumes `price` in the entity is a `double`. For monetary values, consider storing amounts in the smallest currency unit (such as cents) or using `scaled_float` with explicit scaling rules to avoid floating-point rounding errors. If the entity uses `BigDecimal`, the mapper should transfer it directly under defined precision/scale policies.

### 8.1. Why Accept `SearchHit` Instead of Only the Entity?

If a mapper only accepts `ProductDocument`, it cannot read scores, highlights, or sort values. Accepting `SearchHit<ProductDocument>` lets the DTO selectively include search metadata.

Conversely, for use cases needing only entity content, use a simpler mapper method:

```java
ProductCardDto toCard(ProductDocument document);
```

Do not force a mapper to depend on `SearchHit` when the DTO needs none of that metadata. Pick the smallest abstraction that fits the response.

### 8.2. Do Not Return Raw Highlights Blindly

Highlight fragments may contain HTML tags produced by Elasticsearch's highlight configuration. If an API or UI renders them directly, define safe rendering rules and content escaping. Never treat highlight strings as trusted HTML.

Extract only explicitly allowed highlight fields, such as `name`. Do not dump the entire `getHighlightFields()` map if queries could highlight internal fields.

## 9. Separating Mappers by Response Type

A single entity can have multiple DTOs:

```text
ProductDocument
    |
    +---- ProductCardDto       (listing/search)
    |
    +---- ProductDetailDto     (detail page)
    |
    +---- ProductAdminDto      (administration)
    |
    +---- ProductExportRow     (data export)
```

Avoid using one massive DTO containing every field and letting individual endpoints strip fields out. Creating per-use-case DTOs clarifies what data may be exposed and reduces coupling between the index schema and API contracts.

Example:

```java
public record ProductDetailDto(
        String id,
        String sku,
        String name,
        String description,
        BigDecimal price,
        String status
) {
}

public record ProductAdminDto(
        String id,
        String sku,
        String name,
        String status,
        String internalReviewState
) {
}
```

Mappers can use MapStruct for straightforward entity-to-DTO conversion. However, mapping `SearchHit` metadata, highlights, and aggregations generally calls for explicit custom methods.

## 10. Mapping `SearchHits` to Page Responses

A straightforward approach is mapping the hit list while preserving pagination metadata:

```java
public ProductSearchResult toResult(
        SearchHits<ProductDocument> hits,
        Pageable pageable) {

    List<ProductCardDto> items = hits.getSearchHits().stream()
            .map(this::toCard)
            .toList();

    return new ProductSearchResult(
            items,
            hits.getTotalHits(),
            hits.getTotalHitsRelation().name(),
            pageable.getPageNumber(),
            pageable.getPageSize()
    );
}
```

If using Spring Data `Page<T>`, you can convert `SearchHits` into a page response using your version's API or construct `PageImpl` when total hits are exact. In Elasticsearch, total hits can be `GREATER_THAN_OR_EQUAL_TO` unless the query requests exact tracking across all matches; therefore, preserve the relation or design response contracts that do not assume totals are exact.

### 10.1. Do Not Confuse `totalHits` with the Item Count on the Page

`hits.getSearchHits().size()` is the number of items on the current page. `hits.getTotalHits()` is the overall hit count according to the request's total-hit tracking. These two numbers differ whenever pagination is active.

If a query caps total-hit tracking or limits hits, never treat total hits as an exact absolute count when the relation reports a lower bound.

### 10.2. Capping Page Size

APIs should enforce a maximum page size:

```java
int safeSize = Math.min(Math.max(requestedSize, 1), 100);
Pageable pageable = PageRequest.of(page, safeSize, sort);
```

This cap prevents requests from accidentally loading tens of thousands of documents and mapping them all onto the heap. For large datasets, consider `search_after`/PIT instead of deep page numbers.

## 11. DTOs for Cursor Pagination and `search_after`

Offset pagination suits moderate result sets. For large datasets or deep paging, Elasticsearch generally works better with `search_after` paired with Point in Time (PIT) for stable traversal.

A cursor response might look like:

```java
public record ProductCursorPage(
        List<ProductCardDto> items,
        String nextCursor,
        boolean hasMore
) {
}
```

Cursors should be server-generated opaque tokens containing or referencing sort values and the PIT context in a protected manner. Never allow clients to tamper with sort values or submit a cursor pointing to another tenant.

High-level flow:

1. Open a PIT for the appropriate index/alias.
2. Execute the query with a deterministic sort and a unique tie-breaker.
3. Capture the sort values of the final hit.
4. Build a cursor holding the signed/encrypted or server-stored PIT ID and sort values.
5. Use the cursor on the next request to invoke `search_after`.
6. Close the PIT when finished or let it expire.

`SearchHit` provides sort values metadata in supporting APIs. How PIT and `search_after` are configured in Spring Data / the Java API Client depends on version; encapsulate this logic inside a dedicated cursor query adapter rather than letting controllers assemble DSL.

### 11.1. Sorting Must Be Deterministic

If you sort only by `price`, multiple documents can share the same price and ordering between pages becomes unstable. Add a unique tie-breaker such as `_id` or another unique sortable field suited to your API/version. PIT keeps a consistent point-in-time view of data during pagination, but it does not fix an underspecified sort.

### 11.2. Cursors Must Bind to Query Scope

A cursor must be bound to:

- Tenant/security scope.
- Normalized filters.
- Sort order.
- PIT ID/expiry.
- Cursor schema version.

If a client submits a cursor belonging to a different filter or tenant, the server must reject it or start a fresh query per policy. Never let cursors become a way to bypass authorization filters.

## 12. DTOs for Aggregation Results

Aggregations do not necessarily return a `ProductDocument` per bucket. For instance, a dashboard might need product counts per category:

```java
public record CategoryCountDto(
        String categoryId,
        long productCount
) {
}

public record ProductCategorySummaryDto(
        List<CategoryCountDto> categories
) {
}
```

Separate aggregation mappers from document mappers:

```text
SearchHits<ProductDocument>
       -> ProductSearchMapper
       -> ProductCardDto

SearchHits aggregations
       -> ProductAggregationMapper
       -> CategoryCountDto
```

Spring Data Elasticsearch wraps aggregation responses in a version-dependent abstraction, typically `AggregationsContainer<?>` on `SearchHits`. When accessing specific aggregation types, an adapter can inspect the native response or aggregation container and convert it to DTOs. Accessors and bucket types vary across versions, so keep that conversion in a dedicated class and verify against your exact API version.

Do not expose raw Elasticsearch aggregation responses in your API contract. Map only the bucket keys, counts, and metrics that clients actually need.

## 13. MapStruct or Manual Mappers?

MapStruct fits pure mappings between Java beans/records with matching fields:

```java
@Mapper(componentModel = "spring")
public interface ProductDocumentMapper {
    ProductDetailDto toDetail(ProductDocument document);
}
```

Advantages:

- Mappings are generated at compile time.
- Many field name/type mismatches are caught early.
- Mappers can be shared across services.
- No runtime reflection needed for basic mappings.

Manual mappers fit when:

- Reading `SearchHit` scores, highlights, or sort values.
- Handling complex null/default logic.
- Computing derived aggregate values.
- Masking or omitting fields based on security context.
- Converting client-version-dependent aggregation responses.

You can combine both: let MapStruct map `ProductDocument` to base DTOs, while an adapter accepting `SearchHit` attaches extra metadata. Do not force MapStruct to handle complex Elasticsearch wrappers when custom methods are clearer.

## 14. Reusing Mappers Without Exposing Internal Fields

Elasticsearch entities may hold fields meant strictly for internal use:

```java
@Document(indexName = "products")
public class ProductDocument {
    @Id
    private String id;
    private String name;
    private String status;
    private String internalModerationNote;
    private String sourceSystem;
}
```

Never return entities directly as responses. Define allowlisted DTOs:

```java
public record ProductPublicDto(
        String id,
        String name,
        String status
) {
}
```

The mapper populates only the three permitted fields. If admins are allowed to see more data, define a separate DTO and separate authorization rules.

Reusing mappers does not mean every endpoint returns the exact same DTO. Reuse small mapping components and policies, while keeping response models tailored to each use case.

## 15. Mapping Missing Fields, Nulls, and Default Values

Older Elasticsearch documents may lack newer fields added after schema evolution. Mappers need clear rules for how to handle them:

- Preserve `null` so clients know data is absent.
- Apply defaults when the domain defines a valid default.
- Use optional fields in DTOs.
- Track a schema/projection version if distinguishing older and newer documents is necessary.

Do not blindly convert every null to `0`, `false`, or an empty string. For example, `price = 0` can mean something very different from "price not set".

Example explicit mapper:

```java
String displayName = document.getName() == null
        ? "Unnamed product"
        : document.getName();
```

Apply display defaults only when acceptable to the business. Never write defaults back into the index merely to mask missing data before identifying its root cause.

## 16. Reusing Query Builders Across Multiple Repository Fragments

A query factory can be injected into multiple fragments when entity/index semantics align:

```text
ProductRepository
   +-- ProductSearchFragmentImpl
   |       +-- ProductQueryFactory
   |       +-- ProductSearchMapper
   |
   +-- ProductAdminFragmentImpl
           +-- ProductAdminQueryFactory
           +-- ProductAdminMapper
```

Do not share one factory across queries with different security policies. For example, public search and admin search have different scopes; make that explicit in types or methods to prevent accidentally dropping a filter.

If two repositories share a fragment but target different entities, consider a generic abstraction or small composition. Only generalize when mapping and query contracts genuinely match; otherwise, two specialized factories are safer and easier to follow.

## 17. Reusing a Query Builder Across Multiple Use Cases

Example where public search and admin search share certain conditions:

```java
public class ProductQueryFactory {

    public Query buildPublicSearch(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable) {
        Criteria criteria = baseVisibleCriteria(scope);
        criteria = addCommonFilters(criteria, filter);
        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(pageable);
        return query;
    }

    public Query buildAdminSearch(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable) {
        Criteria criteria = baseTenantCriteria(scope);
        criteria = addCommonFilters(criteria, filter);
        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(pageable);
        return query;
    }

    private Criteria baseVisibleCriteria(SearchScope scope) {
        return new Criteria("tenant_id").is(scope.tenantId())
                .and("visible").is(true)
                .and("deleted").is(false);
    }

    private Criteria baseTenantCriteria(SearchScope scope) {
        return new Criteria("tenant_id").is(scope.tenantId())
                .and("deleted").is(false);
    }

    private Criteria addCommonFilters(
            Criteria criteria,
            ProductSearchFilter filter) {
        // Add validated status/category/price/keyword filters.
        return criteria;
    }
}
```

This example shows reusing common filter logic while keeping two distinct base policies. In real code, pass scopes/permissions explicitly and write tests confirming public queries never return hidden documents.

## 18. Unit Testing Query Factories

Query factories can be unit tested at the input logic level:

- Are blank keywords ignored?
- Is status normalized?
- Are invalid min/max price ranges rejected?
- Is tenant scope mandatory?
- Are sort fields outside the allowlist rejected?
- Is page size capped?

Example testing filter validation:

```java
@Test
void rejectsInvalidPriceRange() {
    ProductSearchFilter filter = new ProductSearchFilter(
            null,
            "ACTIVE",
            null,
            new BigDecimal("200"),
            new BigDecimal("100")
    );

    assertThatThrownBy(filter::validate)
            .isInstanceOf(IllegalArgumentException.class);
}
```

For query objects, avoid asserting purely against `toString()` because internal formatting can change. Test builder branches via small methods or verify query execution via integration tests.

## 19. Testing Mappers in Isolation

Pure mappers can be unit tested without Elasticsearch:

```java
@Test
void mapsSearchHitContentAndMetadata() {
    ProductDocument document = new ProductDocument(
            "P-100", "Mechanical Keyboard", "ACTIVE", 250.0
    );

    SearchHit<ProductDocument> hit = createSearchHitFixture(
            document,
            1.25f,
            Map.of("name", List.of("Mechanical <em>Keyboard</em>"))
    );

    ProductCardDto dto = mapper.toCard(hit);

    assertThat(dto.id()).isEqualTo("P-100");
    assertThat(dto.name()).isEqualTo("Mechanical Keyboard");
    assertThat(dto.score()).isEqualTo(1.25f);
    assertThat(dto.highlights()).containsExactly("Mechanical <em>Keyboard</em>");
}
```

`createSearchHitFixture` is a test helper creating a `SearchHit` using constructors/builders available in your project's Spring Data version. Because internal constructors can vary, you can test mappers through a small adapter interface or integration tests producing real SearchHits if constructing fixtures becomes cumbersome.

Cases worth testing:

- Null/missing fields.
- Absent highlights.
- Present vs. absent scores depending on query type.
- Empty sort values.
- Internal fields omitted from DTOs.
- Monetary prices preserving precision per policy.
- No field leakage between public and admin DTOs.

## 20. Testing Query Factories and Mappers via Repository Integration Tests

Unit testing factories and mappers does not prove queries work against Elasticsearch mappings. Write integration tests for key flows:

1. Create the index with production mappings or equivalent test mappings.
2. Index representative documents.
3. Refresh the index.
4. Invoke the repository fragment with filters and scope.
5. Verify the right documents are selected.
6. Verify DTOs expose only intended fields plus scores/highlights when applicable.
7. Verify pagination, sorting, and total-hit relation.
8. Verify tenant filters cannot be bypassed.

Testcontainers can provide a real pinned version of Elasticsearch. Do not rely on mocked `ElasticsearchOperations` to conclude that `CriteriaQuery`/`NativeQuery` semantics are correct.

## 21. Separate DTOs for Aggregations and Suggestions

Not every search result is a list of entities. An autocomplete API might need only:

```java
public record ProductSuggestionDto(
        String id,
        String label
) {
}
```

A dashboard API might need:

```java
public record PriceStatsDto(
        BigDecimal minimum,
        BigDecimal maximum,
        BigDecimal average,
        long count
) {
}
```

Choosing DTOs per result type avoids coupling to one bloated DTO. Aggregation mappers convert buckets/metrics from Elasticsearch responses into domain numbers/DTOs, while document mappers convert `SearchHit<T>`.

If aggregation responses vary by Java API Client version, introduce an adapter translating the native aggregation container into a stable internal model before mapping to API DTOs.

## 22. Performance: Source Filtering and Mapping Only Necessary Data

If a listing only needs `id`, `name`, and `price`, there is no need to transfer entire `_source` documents containing long descriptions, internal metadata, or large arrays.

You can use source filtering (includes/excludes) on the query to shrink payloads. Exact APIs vary by `Query`/`NativeQuery` version, but the goal is fetching only the fields needed for the DTO.

However, source filtering does not replace DTO allowlisting. A field might still come back from Elasticsearch while the mapper omits it from the response; conversely, excluding a field from source that the mapper expects will leave the DTO with missing data.

Optimize in order:

1. Identify the exact fields the DTO needs.
2. Choose appropriate mappings and queries.
3. Restrict `_source` if payloads are large.
4. Map directly while streaming results instead of holding both entity and DTO collections unnecessarily.
5. Cap page sizes or use cursor pagination.

## 23. Common Design Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Controller depends on `CriteriaQuery`/`NativeQuery` | Query DSL constructed directly in the web layer. | Use filter DTOs and a query factory in the repository/application layer. |
| Services build different queries for the same filter | Query logic is duplicated. | Extract a shared query factory or fragment. |
| Queries leak across tenants | Security filters added manually per endpoint. | Enforce mandatory scope in the factory/policy and test it explicitly. |
| Requests can sort by arbitrary fields | Client strings passed straight into sorting. | Whitelist sort properties and directions. |
| One request's query affects another | Mutable Criteria/Query singleton reused across calls. | Create fresh query objects on every build. |
| DTO leaks internal fields | Returning entities directly or mappers copying all fields. | Use per-use-case allowlisted DTOs. |
| Scores/highlights lost | Mapper accepts only entity content. | Accept `SearchHit<T>` when metadata is needed. |
| Total count misinterpreted | Ignoring total hits relation. | Preserve relation or design response contracts representing approximate totals. |
| Price precision errors | Arbitrary mapping from `double` to `BigDecimal`. | Use scaled integers / `scaled_float` or an explicit BigDecimal policy. |
| Highlights break rendering | Treating highlight strings as trusted HTML. | Escape/render safely on clients or sanitize per policy. |
| Overly generic query builder | Abstraction takes arbitrary fields/operators. | Build use-case-specific factories and small typed helpers. |
| Builder tests pass but queries fail | Only unit testing object construction. | Add integration tests against real Elasticsearch. |
| DTO/mapper tied to client version | Mapping native aggregation responses directly in many places. | Introduce an adapter converting to a stable internal model. |

## 24. Workflow for Building Query Factories and DTO Mappers

1. **Define the use case:** list filters, scope, sorting, pagination, and response fields.
2. **Create the filter model:** use domain/application types, validate, and normalize inputs.
3. **Separate security scope:** obtain tenant/permissions from a trusted context, never arbitrarily from clients.
4. **Build the query factory:** translate filters into `CriteriaQuery` or `NativeQuery` and apply mandatory filters.
5. **Constrain sorting/paging:** allowlist fields, cap page sizes, and choose offset or cursor pagination.
6. **Define use-case DTOs:** public card, detail, admin, suggestion, or aggregation models.
7. **Implement mappers:** map entities or `SearchHit` metadata into allowlisted DTOs.
8. **Wire into repository fragments:** inject the factory, `ElasticsearchOperations`, and mapper.
9. **Unit test:** verify validation, filter normalization, query factory branches, and mappers.
10. **Integration test:** execute queries on real Elasticsearch with representative mappings and data.
11. **Review performance:** source filtering, page size limits, total hits tracking, highlights, and cursor pagination.

## 25. Key Takeaways

- Application filters should remain independent of Elasticsearch DSL.
- Query factories translate filters into `CriteriaQuery` or `NativeQuery` and centralize shared query rules.
- Tenant/authorization filters must come from a trusted security context and always be enforced.
- Create fresh query objects per request; never share mutable objects across threads.
- Whitelist sort fields and cap page sizes.
- Repository fragments can inject query factories and mappers for reuse across multiple use cases.
- `SearchHit<T>` holds entity content alongside scores, highlights, and metadata; `SearchHits<T>` holds overall search results.
- Mappers should return allowlisted DTOs rather than exposing Elasticsearch entities directly in APIs.
- Separate DTOs by use case, such as cards, details, admin views, suggestions, and aggregations.
- Preserve `totalHitsRelation` whenever total hits may be a lower bound.
- For large datasets, consider PIT + `search_after` and opaque cursors bound to filters and scope.
- MapStruct works well for basic bean mapping; manual mappers suit SearchHit metadata and aggregations.
- Unit tests verify builder/mapper logic; integration tests validate queries and mappings against real Elasticsearch.
- Source filtering reduces payload size but does not replace DTO allowlisting.

Reusing query builders and DTO mapping gives custom repositories a single consistent place to express filters, enforce data scopes, and turn Elasticsearch results into stable responses. Keeping filters decoupled from DSL, building fresh queries per request, mapping through allowlisted DTOs, and testing both pure logic and real Elasticsearch behavior keeps code extensible without leaking infrastructure details into APIs.

## References

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — Elasticsearch Operations and Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — SearchHit API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Commons — Repository Composition](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
