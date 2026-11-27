# Reusing Query Builders by Business Conditions

In a Spring Data Elasticsearch application, multiple screens or APIs often share the same group of search conditions: restricting data to the current tenant, returning only active products, or filtering by category, price range, or time window. If every service builds its own Query DSL from scratch, conditions become duplicated, diverge across endpoints, and become difficult to update consistently.

`NativeQuery` lets you build queries with the Elasticsearch Java API Client and execute them via Spring Data Elasticsearch. You can extract business conditions into small reusable parts, combine them into a `bool` query, and share those builders across multiple use cases.

The key principle is reusing **query-fragment builder functions and condition combination rules**, while still constructing a fresh query per request from the current parameters. This keeps conditions consistent without sharing mutable builder state across requests.

## 1. From Business Conditions to Query DSL

Suppose a catalog system has these search requirements:

- Search products by keyword in name or description.
- Return only products belonging to the logged-in user's tenant.
- Optionally filter by category and status.
- Optionally filter by price range or creation time range.
- Support sorting and pagination.

These are business conditions. They should not depend directly on how Elasticsearch represents `term`, `range`, `match`, or `bool` inside every service.

Responsibilities can be split into three layers:

1. **Search criteria**: input data describing what the user wants to search for, such as keyword, category, statuses, and price range.
2. **Query factory / query parts**: translates criteria into reusable query fragments.
3. **Search service or repository fragment**: calls the factory, attaches pagination/sorting, and executes the query via `ElasticsearchOperations`.

~~~mermaid
flowchart TD
    A["API / use case"] --> B["ProductSearchCriteria"]
    B --> C["ProductQueryFactory"]
    D["Tenant from security context"] --> C
    E["Shared query fragments"] --> C
    C --> F["NativeQuery / bool query"]
    F --> G["ElasticsearchOperations"]
    G --> H["SearchHits<ProductDocument>"]
~~~

This separation keeps services free of raw JSON clause details and lets a group of conditions be reused across many places.

## 2. `NativeQuery` and the Elasticsearch Java API Client

`NativeQuery` is Spring Data Elasticsearch's query type for carrying query objects built with the Elasticsearch Java API Client. It is well suited when you need explicit control over Query DSL structures such as `bool`, `must`, `filter`, `should`, nested queries, scripts, or other advanced features.

Example creating a simple query:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query activeFilter = Query.of(q -> q.term(t -> t
        .field("status")
        .value(FieldValue.of("ACTIVE"))));

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b.filter(activeFilter)))
        .build();
~~~

Two `Query` types must be distinguished here:

- `co.elastic.clients.elasticsearch._types.query_dsl.Query` is the Elasticsearch Java API Client's query object, representing a clause in Query DSL.
- `org.springframework.data.elasticsearch.client.elc.NativeQuery` is Spring Data Elasticsearch's query abstraction, wrapping the client query alongside options such as sort, pageable, aggregations, and source filters.

`NativeQuery` does not mean a native SQL query. It is a way to use the Elasticsearch Query DSL structure directly through the Java client.

## 3. Creating Reusable Query Fragments

A query fragment is a small condition that can be constructed independently—for example, filtering by tenant, category, or status. Write each fragment as a method whose name reflects its business intent.

Example shared fragments:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public final class ProductQueryParts {

    private ProductQueryParts() {
    }

    public static Query tenantFilter(String tenantId) {
        return Query.of(q -> q.term(t -> t
                .field("tenantId")
                .value(FieldValue.of(tenantId))));
    }

    public static Query activeFilter() {
        return Query.of(q -> q.term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))));
    }

    public static Query categoryFilter(String category) {
        return Query.of(q -> q.term(t -> t
                .field("category")
                .value(FieldValue.of(category))));
    }

    public static Query nameMatch(String text) {
        return Query.of(q -> q.match(m -> m
                .field("name")
                .query(text)));
    }
}
~~~

These methods construct a fresh query object from input parameters. They do not hold a mutable builder in a static field. As a result, concurrent requests can call the same methods with different tenants, categories, or keywords without sharing state.

Shared fragments can live in a dedicated query package/module, such as `search.query.ProductQueryParts`. If a fragment serves only one aggregate or use case, place it near the corresponding query factory to avoid creating an overly broad utility library.

## 4. Representing Search Criteria as a Business Object

Avoid passing long lists of loose parameters through multiple service layers. Creating an object representing search criteria makes validation, extension, and reuse much clearer.

Example using a Java record:

~~~java
import java.time.Instant;
import java.util.Set;

public record ProductSearchCriteria(
        String text,
        String category,
        Set<String> statuses,
        Long minPrice,
        Long maxPrice,
        Instant createdFrom,
        Instant createdTo) {
}
~~~

This object describes only product criteria. `tenantId` is passed separately from the security context or an authentication service, because tenant scope is a mandatory access condition rather than an optional filter chosen by the client.

If a project does not yet use Java records, replace it with an immutable class with a constructor, getters, and corresponding validation.

## 5. Building a Query Factory from Fragments

A query factory takes business criteria, builds lists of query clauses, and combines them with `bool`. A useful convention is:

- Content search conditions such as `match` go into `must` so they contribute to relevance scores.
- Mandatory conditions that do not need scoring such as tenant, status, category, and ranges go into `filter`.
- Optional or result-broadening conditions can go into `should` with an explicitly defined `minimum_should_match`.

Example factory:

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public class ProductQueryFactory {

    public Query buildQuery(ProductSearchCriteria criteria, String tenantId) {
        List<Query> must = new ArrayList<>();
        List<Query> filters = new ArrayList<>();

        // Tenant scope is always enforced.
        filters.add(ProductQueryParts.tenantFilter(tenantId));

        if (criteria.text() != null && !criteria.text().isBlank()) {
            must.add(ProductQueryParts.nameMatch(criteria.text().trim()));
        }

        if (criteria.category() != null && !criteria.category().isBlank()) {
            filters.add(ProductQueryParts.categoryFilter(criteria.category()));
        }

        if (criteria.statuses() != null && !criteria.statuses().isEmpty()) {
            filters.add(statusesFilter(criteria.statuses()));
        }

        if (criteria.minPrice() != null || criteria.maxPrice() != null) {
            filters.add(priceRangeFilter(
                    criteria.minPrice(), criteria.maxPrice()));
        }

        if (criteria.createdFrom() != null || criteria.createdTo() != null) {
            filters.add(createdAtRangeFilter(
                    criteria.createdFrom(), criteria.createdTo()));
        }

        return Query.of(q -> q.bool(b -> {
            if (!must.isEmpty()) {
                b.must(must);
            }
            if (!filters.isEmpty()) {
                b.filter(filters);
            }
            return b;
        }));
    }

    private Query statusesFilter(java.util.Set<String> statuses) {
        List<FieldValue> values = statuses.stream()
                .map(FieldValue::of)
                .toList();

        return Query.of(q -> q.terms(t -> t
                .field("status")
                .terms(v -> v.value(values))));
    }

    private Query priceRangeFilter(Long min, Long max) {
        return Query.of(q -> q.range(r -> r.number(n -> {
            n.field("priceInCents");
            if (min != null) {
                n.gte(min.doubleValue());
            }
            if (max != null) {
                n.lte(max.doubleValue());
            }
            return n;
        })));
    }

    private Query createdAtRangeFilter(
            java.time.Instant from, java.time.Instant to) {
        return Query.of(q -> q.range(r -> r.date(d -> {
            d.field("createdAt");
            if (from != null) {
                d.gte(from.toString());
            }
            if (to != null) {
                d.lt(to.toString());
            }
            return d;
        })));
    }
}
~~~

This factory can be shared by multiple services or repository fragments. Each call to `buildQuery` creates its own clause lists and returns a fresh query object.

### 5.1. Why Must the Tenant Filter Always Be Present?

In the example, the tenant filter is added before optional conditions. Callers cannot bypass this filter by sending an empty category or omitting statuses.

`tenantId` must come from a server-verified identity—for example, a security principal or a service resolving the current tenant. Do not take tenant ID directly from a query parameter and trust that the client only asks for its own data.

This is a data protection rule. If every endpoint adds tenant filters differently, one endpoint forgetting the condition could return documents from another tenant. Placing the rule in a shared factory reduces drift, though the service must still ensure only an authenticated tenant is passed in.

### 5.2. Handling Empty Conditions

Not every condition needs to appear in the query:

- Null or blank keyword: omit the `match` clause.
- Null or blank category: do not add a category filter.
- Null or empty status set: do not add a terms filter.
- Only min or max provided: create a range with one bound.
- No search conditions other than tenant: still restrict by tenant; use `match_all` combined with filters or a `bool` containing only `filter`.

Do not build a `terms` query with an empty list. Depending on construction and client version, an empty list may be rejected or yield unexpected results. Check collections before adding the clause.

## 6. Creating NativeQuery with Sort and Pageable

The query factory can stay focused on building Query DSL, while another class wraps it into a `NativeQuery` with pagination and sorting:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

public class ProductNativeQueryFactory {

    private final ProductQueryFactory queryFactory;

    public ProductNativeQueryFactory(ProductQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    public NativeQuery build(
            ProductSearchCriteria criteria,
            String tenantId,
            Pageable pageable) {

        return NativeQuery.builder()
                .withQuery(queryFactory.buildQuery(criteria, tenantId))
                .withPageable(pageable)
                .build();
    }
}
~~~

`Pageable` can carry page number, page size, and `Sort`. For default sorting, the service can construct a `PageRequest` before calling the factory:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));
~~~

Sort fields must have mappings that support sorting—typically `keyword`, numeric, date, or scalar types with doc values. Do not sort directly on a regular `text` field; use a `keyword` subfield when sorting strings.

## 7. Executing Queries via ElasticsearchOperations

The service receives business criteria, obtains the authenticated tenant, creates a `NativeQuery`, and executes it:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;
    private final ProductNativeQueryFactory queryFactory;
    private final CurrentTenantProvider currentTenantProvider;

    public ProductSearchService(
            ElasticsearchOperations operations,
            ProductNativeQueryFactory queryFactory,
            CurrentTenantProvider currentTenantProvider) {
        this.operations = operations;
        this.queryFactory = queryFactory;
        this.currentTenantProvider = currentTenantProvider;
    }

    public SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria, Pageable pageable) {

        String tenantId = currentTenantProvider.requireTenantId();
        NativeQuery query = queryFactory.build(criteria, tenantId, pageable);

        return operations.search(query, ProductDocument.class);
    }
}
~~~

`CurrentTenantProvider` is an application abstraction to resolve the tenant from the security context. Exact naming and implementation depend on the authentication mechanism in use.

`SearchHits<T>` contains search hits and metadata from Elasticsearch. If the API needs only a list of documents, extract contents from `hits`; if scores or total hits are needed, keep `SearchHits` to process metadata.

## 8. Reusing Queries Across Multiple Use Cases

One set of fragments can participate in multiple queries combined for different purposes.

Example:

| Use Case | Query Context (`must`) | Filter Context (`filter`) |
| --- | --- | --- |
| Catalog search | `match` on name or description. | Tenant, status, category, price. |
| Active product listing | Content query may not be needed. | Tenant and status `ACTIVE`. |
| Price-range lookup | Optional `match` on keyword if entered. | Tenant, category, and price range. |
| Newly created products | Content query may not be needed. | Tenant and `createdAt` range. |
| Multi-status lookup | Optional `match` by keyword. | Tenant and status `terms` filter. |

Example use case fetching only active products:

~~~java
Query query = Query.of(q -> q.bool(b -> b
        .filter(ProductQueryParts.tenantFilter(tenantId))
        .filter(ProductQueryParts.activeFilter())));

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(query)
        .build();
~~~

A category search use case can reuse the same tenant and category fragments:

~~~java
Query query = Query.of(q -> q.bool(b -> b
        .filter(ProductQueryParts.tenantFilter(tenantId))
        .filter(ProductQueryParts.categoryFilter("ACCESSORIES"))));
~~~

Fragments are small, context-composable pieces. Avoid building one giant factory containing conditions for an entire domain when those conditions belong to different aggregates or mappings.

## 9. Reusing via Repository Fragments

When business queries grow complex, custom search methods can be placed in a repository fragment so callers do not need to deal with `NativeQuery` or `ElasticsearchOperations` directly.

Fragment interface:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface ProductSearchOperations {

    SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria, Pageable pageable);
}
~~~

Main repository combining the CRUD repository and fragment:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchOperations {
}
~~~

Fragment implementation:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public class ProductSearchOperationsImpl implements ProductSearchOperations {

    private final ElasticsearchOperations operations;
    private final ProductNativeQueryFactory queryFactory;
    private final CurrentTenantProvider currentTenantProvider;

    public ProductSearchOperationsImpl(
            ElasticsearchOperations operations,
            ProductNativeQueryFactory queryFactory,
            CurrentTenantProvider currentTenantProvider) {
        this.operations = operations;
        this.queryFactory = queryFactory;
        this.currentTenantProvider = currentTenantProvider;
    }

    @Override
    public SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria, Pageable pageable) {

        String tenantId = currentTenantProvider.requireTenantId();
        NativeQuery query = queryFactory.build(criteria, tenantId, pageable);
        return operations.search(query, ProductDocument.class);
    }
}
~~~

Spring Data repository fragment composition lets you plug custom implementations into a repository. The implementation class name must follow the fragment naming convention of your Spring Data version or be explicitly registered in repository configuration.

With this design, controllers or services call `productRepository.search(criteria, pageable)`; query construction remains encapsulated inside the fragment and query factory.

## 10. Separating Query Conditions from Sorting, Paging, and Projections

Condition builders should focus on filtering and search criteria. Sorting, paging, source filtering, and aggregations are orthogonal concerns of the request.

You can structure them into distinct components:

- `ProductQueryFactory`: builds `bool`, `must`, `filter`, `should`.
- `ProductSortPolicy`: maps valid API sort choices to `Sort`.
- `Pageable` from the API/service layer: defines the result window.
- Projection/source filter: specifies which fields to return.
- Aggregation builder: creates summary stats when use cases need facets or dashboards.

This separation allows the same set of conditions to serve listing pages, exports, autocomplete, or dashboards while each use case picks its own sorting, page size, and aggregations.

When using `Pageable`, enforce page size limits and allowlist sort fields. Never accept arbitrary field names directly from clients and pass them straight into `Sort.by`.

## 11. AND, OR Rules and Optional Condition Groups

The query factory should express business logic clearly. For instance, suppose a user wants products belonging to one of two categories while still requiring `ACTIVE` status:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } },
        {
          "bool": {
            "should": [
              { "term": { "category": "ACCESSORIES" } },
              { "term": { "category": "OFFICE" } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
~~~

Both the status condition and the category group sit in `filter`. Inside the category group, `should` expresses OR and `minimum_should_match: 1` guarantees at least one branch matches.

Using the Java API Client, you can construct the OR group as a query fragment and add it to `filter`:

~~~java
private Query categoryAnyOf(java.util.Set<String> categories) {
    List<Query> choices = categories.stream()
            .map(category -> Query.of(q -> q.term(t -> t
                    .field("category")
                    .value(FieldValue.of(category)))))
            .toList();

    return Query.of(q -> q.bool(b -> b
            .should(choices)
            .minimumShouldMatch("1")));
}
~~~

When the category set is empty, callers must decide the business meaning: omit the condition, return no results, or reject the request. Never let an empty `should` group silently dictate behavior on the application's behalf.

## 12. Validating Criteria Before Building the Query

The query factory converts inputs into DSL, while business validation should run beforehand or right in the criteria object's constructor.

Typical checks include:

- `minPrice` must not exceed `maxPrice`.
- `createdFrom` must be earlier than `createdTo`.
- Keywords must fall within reasonable min/max lengths.
- Status sets must contain only valid business values.
- Category must belong to allowed categories if the domain has a fixed list.
- Tenant ID must come from server-side identity.
- Page size and sort fields must conform to API limits.

Example validation in a service:

~~~java
private void validate(ProductSearchCriteria criteria) {
    if (criteria.minPrice() != null
            && criteria.maxPrice() != null
            && criteria.minPrice() > criteria.maxPrice()) {
        throw new IllegalArgumentException(
                "minPrice must not exceed maxPrice");
    }

    if (criteria.createdFrom() != null
            && criteria.createdTo() != null
            && !criteria.createdFrom().isBefore(criteria.createdTo())) {
        throw new IllegalArgumentException(
                "createdFrom must be earlier than createdTo");
    }
}
~~~

Do not let the factory silently fix invalid input or drop malformed conditions. Raising clear validation errors helps callers understand why a request was invalid.

## 13. Organizing Reusable Query Parts by Scope

Not every condition belongs in a single shared class. Organize parts by scope:

| Fragment Group | Examples | Reuse Scope |
| --- | --- | --- |
| Shared access conditions | Tenant, visibility permissions, soft-delete status. | Multiple use cases within the same data domain. |
| Entity-specific conditions | Category, price, SKU, brand. | Product queries. |
| Content search conditions | Name/description match, synonym-aware queries. | Product search endpoints. |
| Use-case-specific conditions | Low-stock items, featured items. | A few specific business flows. |

You may maintain a `CommonQueryParts` class for genuinely shared conditions, but avoid creating a single generic builder that knows field names for every index. Field names, mappings, and semantics belong to specific document domains.

## 14. Practices to Avoid

| Practice | Problem | Better Organization |
| --- | --- | --- |
| Keeping a static `BoolQuery.Builder` and appending clauses per request. | Mutable builders can retain old conditions or cause race conditions across requests. | Create a new builder per build call; reuse fragment-factory methods. |
| Sharing a `NativeQuery` holding dynamic criteria across users. | The query can carry tenant/filter/page/sort from a previous request. | Construct a fresh `NativeQuery` per request. |
| Putting tenant ID into a client-supplied DTO. | Clients could alter the tenant to access out-of-scope data. | Resolve tenant from the security context and add mandatory filters server-side. |
| Writing one method with dozens of boolean flags. | Hard to tell which combinations are valid and hard to test. | Use meaningful criteria objects and small fragments. |
| Concatenating JSON via string concatenation. | Prone to escaping, type, and DSL structure errors. | Use Java API Client builders or controlled JSON DSL. |
| Using query context for every condition out of habit. | Non-relevance conditions can affect `_score`. | Use `bool.filter` for boolean true/false conditions. |
| Building one generic query factory for all indices. | Fields and semantics differ across domains. | Build per-document/domain factories and share only truly common fragments. |
| Not checking empty lists or inverted ranges. | Can produce meaningless queries or runtime errors. | Validate criteria before building. |

## 15. Testing Query Builders

Query builders can be tested at two levels:

### 15.1. Unit Tests for Business Conditions

Test the factory against different input cases:

- Only tenant supplied: query must still include the tenant filter.
- Text supplied: query must include the match clause.
- Category/statuses supplied: matching clauses appear under `filter`.
- Single price bound supplied: range contains only `gte` or `lte` as appropriate.
- Empty status set: no empty `terms` query is generated.
- Invalid price or time range: validation rejects it.
- Missing tenant: requests cannot produce queries capable of accessing all data.

### 15.2. Integration Tests with Elasticsearch

Unit tests verify the factory builds the expected structure; integration tests confirm Elasticsearch interprets the mapping and query as intended. Seed data for at least two tenants to verify tenant filtering never leaks cross-tenant documents.

Also verify:

- `keyword` mapping for status/category and numeric/date mappings for ranges.
- Analyzer-based `match` results on `text` fields.
- AND/OR combinations and `minimum_should_match`.
- Sorting and pagination on sortable fields.
- Results when criteria contain no search text.
- Aggregations if the query factory serves dashboards or faceted search.

You can inspect sent Query DSL via client logging in development or use the Profile API for performance analysis. Never enable request body or sensitive data logging in production without proper filtering/redaction.

## 16. Complete Usage Example

An endpoint execution flow can look like this:

~~~java
public SearchHits<ProductDocument> searchProducts(
        ProductSearchCriteria criteria,
        Pageable pageable) {

    validate(criteria);

    String tenantId = currentTenantProvider.requireTenantId();
    NativeQuery query = nativeQueryFactory.build(
            criteria, tenantId, pageable);

    return elasticsearchOperations.search(query, ProductDocument.class);
}
~~~

Data flow:

~~~mermaid
sequenceDiagram
    participant API
    participant Service
    participant Tenant as TenantProvider
    participant Factory as QueryFactory
    participant ES as Elasticsearch
    API->>Service: criteria + pageable
    Service->>Service: validate(criteria)
    Service->>Tenant: requireTenantId()
    Tenant-->>Service: authenticated tenant
    Service->>Factory: build(criteria, tenant, pageable)
    Factory->>Factory: create reusable fragments
    Factory->>Factory: combine bool must/filter
    Factory-->>Service: NativeQuery
    Service->>ES: operations.search(query)
    ES-->>Service: SearchHits
    Service-->>API: search result
~~~

With this organization, tenant conditions and product filters apply consistently everywhere the factory is used. Individual use cases can still attach custom text queries, sorting, pagination, or aggregations without duplicating the entire Query DSL structure.

## 17. Workflow for Designing Reusable Query Builders

When building a query factory for a domain, follow these steps:

1. List business conditions and separate mandatory conditions from optional ones.
2. Identify corresponding field mappings: `text`, `keyword`, numeric, date, geo, or nested.
3. Decide which conditions need relevance scoring and which only filter.
4. Create a criteria object independent of Elasticsearch DSL.
5. Write small, parameterized fragment methods named after business intent.
6. Create a fresh factory build per request, combining fragments with `bool.must`, `filter`, or `should`.
7. Add tenant/authorization filters from server-side identity, never trusting access scope from client input.
8. Wrap the query in `NativeQuery` along with appropriate pageable/sort options.
9. Execute via `ElasticsearchOperations` or a repository fragment.
10. Test criteria combinations, mappings, real results, and tenant boundaries.

`NativeQuery` lets Spring Data Elasticsearch use Elasticsearch Java API Client query objects directly. Separating domain-specific query fragments and factories enables reusing business conditions, reducing Query DSL duplication, and keeping access rules consistent. Each request must still build a fresh query from validated criteria, apply mandatory server-side filters, and place conditions in query context vs. filter context according to search semantics.
