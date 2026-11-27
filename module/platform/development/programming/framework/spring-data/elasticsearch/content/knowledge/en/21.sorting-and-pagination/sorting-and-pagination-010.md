# Controlling Sort Properties and Page Size from Input

In a Spring Data Elasticsearch application, search APIs typically accept parameters such as `page`, `size`, `sortBy`, and `direction` from requests. These values are converted into `Pageable` and `Sort` to control the result count, page position, and order of returned documents.

You should never pass every client-supplied sort value straight through as an Elasticsearch field name. The application must validate page, cap page size, allow sorting only on predefined fields, and validate `ASC`/`DESC` direction. This ensures predictable API behavior, avoids querying non-sortable fields, and keeps search costs under control.

In Spring Data Elasticsearch, `PageRequest` represents page and page size; `Sort` represents one or more sort criteria; `Pageable` combines the two. You can pass `Pageable` to a repository or attach it to `CriteriaQuery`/`NativeQuery` before invoking `ElasticsearchOperations`.

## 1. Pagination and Sorting in the Search API

The Elasticsearch Search API uses `from` and `size` for offset-based pagination:

- `from`: number of hits to skip before returning results.
- `size`: maximum number of hits to return.
- `sort`: list of sort criteria in priority order.

REST example:

```json
GET /products/_search
{
  "from": 20,
  "size": 10,
  "sort": [
    { "price": { "order": "asc" } },
    { "sku": { "order": "asc" } }
  ],
  "query": {
    "match_all": {}
  }
}
```

This request fetches 10 documents starting from offset 20, sorted by price ascending; if multiple documents share the same price, ascending SKU is used as the next criterion.

Spring Data uses `Pageable` to represent page/size and sort. With `PageRequest`, page numbers start at 0:

```java
Pageable pageable = PageRequest.of(
    2,
    10,
    Sort.by(Sort.Order.asc("price"), Sort.Order.asc("sku"))
);
```

This object represents the third page, with up to 10 results per page. Offset is computed from `page * size`, which is 20 in this example.

## 2. Search Input from the API

A request may declare the following fields:

```java
public record ProductSearchRequest(
    Integer page,
    Integer size,
    String sortBy,
    String direction,
    String keyword
) {
}
```

Example client request:

```http
GET /products?keyword=keyboard&page=0&size=20&sortBy=price&direction=ASC
```

The application must decide:

- Default values when the client omits page or size.
- Whether negative page or zero size is accepted.
- What the maximum page size is.
- Which fields are allowed for sorting.
- Which sort directions are permitted.
- Default sort and secondary criterion to keep order stable.
- Whether deep offset queries are permitted or must switch to cursor pagination.

These are API and business rules. Behavior should not depend accidentally on Elasticsearch exceptions or everything `Sort` can technically express.

## 3. Validating page and size

External page numbers and page sizes should be validated before building `PageRequest`.

### 3.1 Default Conventions

A typical convention:

| Parameter | Example default | Limit |
|---|---:|---|
| `page` | `0` | Non-negative |
| `size` | `20` | Between 1 and 100 |
| `sortBy` | `createdAt` | Must be in allowlist |
| `direction` | `DESC` | Only `ASC` or `DESC` |

The limit `100` is purely an example API policy. Choose based on document size, latency, cluster load, and UI needs. There is no single optimal page size for every system.

### 3.2 Rejecting Invalid page/size

Return validation errors if:

- `page` is less than 0.
- `size` is less than 1.
- `size` exceeds the application limit.
- `page * size` exceeds the allowed pagination window.

Do not silently turn a huge size into an unbounded request. If you choose to clamp size to a maximum, do so as an explicit API convention and return page metadata reflecting the actual size used. Rejecting invalid inputs usually makes client bugs easier to catch.

### 3.3 Checking Offset with a Sufficiently Large Numeric Type

Offset is the product `page * size`. Compute it using `long` to avoid overflow when multiplying two large `int` values:

```java
long from = (long) page * size;
long endExclusive = from + size;
```

Then compare against the `max_result_window` permitted by your system. Elasticsearch typically defaults `index.max_result_window` to 10,000, though the setting can be changed per index. Applications should configure pagination limits matching the index rather than assuming all clusters share identical settings.

## 4. Do Not Accept Arbitrary Sort Field Names from Clients

Sort field names directly affect Elasticsearch queries. Avoid writing:

```java
Sort sort = Sort.by(request.sortBy());
```

That code allows clients to send any field name. Issues can arise:

- Non-existent or non-sortable fields cause query errors.
- `text` fields lack doc values and cannot be sorted in the usual way.
- Clients may request sorting on very large fields or fields unsuitable for the endpoint.
- Internal field names leak via errors or API behavior.
- The API loses stability control when mappings evolve.

This is not SQL injection in the traditional sense, yet it remains query input requiring validation. Map a public set of sort keys to approved Elasticsearch fields.

### 4.1 Using a Sort Key Allowlist

Clients send an API-meaningful key such as `price`, `newest`, or `name`. The server maps that key to a supported property:

```java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "price", "price",
    "newest", "createdAt",
    "name", "nameSort",
    "sku", "sku"
);
```

Here `nameSort` is a keyword field dedicated to sorting. If the mapping uses a multi-field, you can map the `name` key to the corresponding keyword sub-field per your project's API. Crucially, clients only pick a key from the allowlist; clients do not dictate raw Elasticsearch field paths.

### 4.2 Mapping Must Support Sorting

Example mapping:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "nameSort": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
```

`keyword`, numeric, and date types are typically suited for sorting. `text` fields are analyzed into tokens and usually lack doc values; sorting directly on text fields may be rejected or require unsuitable configuration. If both full-text search and string sorting are needed, use a keyword multi-field or a separate sort field.

Multi-field example in mapping:

```json
"name": {
  "type": "text",
  "fields": {
    "raw": {
      "type": "keyword"
    }
  }
}
```

The `name` field is for full-text search; `name.raw` is for exact match, aggregations, or sorting. When using `Sort` via Spring Data, verify how your version maps property/sub-field names; for advanced native sorting, configure it directly in `NativeQuery` using the Elasticsearch Java Client.

## 5. Controlling Sort Direction

Clients typically pass `ASC` or `DESC`. Accept only these two values:

```java
Sort.Direction direction = Sort.Direction.fromString(inputDirection);
```

`fromString` throws `IllegalArgumentException` if the value is invalid. Translate that exception into an API validation error with a clear message.

Never concatenate direction strings into JSON Query DSL. Use the `Sort.Direction` enum to represent only the two valid directions.

Example default handling:

```java
private Sort.Direction parseDirection(String value) {
    if (value == null || value.isBlank()) {
        return Sort.Direction.DESC;
    }

    try {
        return Sort.Direction.fromString(value.trim());
    } catch (IllegalArgumentException exception) {
        throw new IllegalArgumentException(
            "direction must be ASC or DESC",
            exception
        );
    }
}
```

## 6. Multi-Criteria Sorting and Stable Ordering

A sort can consist of multiple criteria. Elasticsearch applies criteria in list order: the first criterion has highest priority; later criteria break ties when prior values are equal.

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("sku")
);
```

Example: newest products come first; if timestamps tie, ascending SKU breaks the tie.

### 6.1 Why Is a Tie-Breaker Needed?

If sorting only by `price`, many products may share the same price. When documents share equal prices, their relative order may be unstable across searches or pages.

Adding a unique, sortable field as a tie-breaker makes ordering deterministic:

```java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.asc("sku")
);
```

This example uses `sku` as a tie-breaker assuming SKU is unique and mapped as keyword. If SKU is not unique, choose another unique sort field stored in the document, such as `sortId`.

Do not assume `_id` is always an optimal sort field. If stable sorting by identifier is needed, store a copy of the ID in a keyword field with doc values for sorting. Design tie-breaker fields explicitly in the mapping.

### 6.2 Default Sort

If the user passes no sort, the API should have a clear default order. Example newest products list:

```java
Sort defaultSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("sku")
);
```

If an endpoint is a full-text search that should put highest relevance first, omit field sorting so Elasticsearch uses `_score` by default, or configure `_score` explicitly in a native query. Do not attach an arbitrary sort field that prevents relevance score from being the primary criterion.

## 7. Building a Controlled Pageable

The example below combines:

- Default page of 0.
- Default size of 20, max 100.
- Sort key selected from an allowlist.
- Direction accepting only ASC/DESC.
- Sort with tie-breaker `sku` if the primary field is not SKU.
- Offset staying within the configured pagination limit.

```java
import java.util.Map;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public class ProductPageableFactory {

    private static final int DEFAULT_PAGE = 0;
    private static final int DEFAULT_SIZE = 20;
    private static final int MAX_SIZE = 100;
    private static final long MAX_RESULT_WINDOW = 10_000L;

    private static final Map<String, String> SORT_FIELDS = Map.of(
        "price", "price",
        "newest", "createdAt",
        "name", "nameSort",
        "sku", "sku"
    );

    public Pageable create(ProductSearchRequest request) {
        int page = request.page() == null
            ? DEFAULT_PAGE
            : request.page();

        int size = request.size() == null
            ? DEFAULT_SIZE
            : request.size();

        if (page < 0) {
            throw new IllegalArgumentException("page must be zero or greater");
        }

        if (size < 1 || size > MAX_SIZE) {
            throw new IllegalArgumentException(
                "size must be between 1 and " + MAX_SIZE
            );
        }

        long from = (long) page * size;
        long endExclusive = from + size;
        if (endExclusive > MAX_RESULT_WINDOW) {
            throw new IllegalArgumentException(
                "requested page exceeds the supported result window"
            );
        }

        String sortKey = request.sortBy() == null || request.sortBy().isBlank()
            ? "newest"
            : request.sortBy().trim();

        String sortField = SORT_FIELDS.get(sortKey);
        if (sortField == null) {
            throw new IllegalArgumentException("unsupported sortBy: " + sortKey);
        }

        Sort.Direction direction = parseDirection(request.direction());

        Sort sort = Sort.by(new Sort.Order(direction, sortField));
        if (!"sku".equals(sortField)) {
            sort = sort.and(Sort.by(Sort.Order.asc("sku")));
        }

        return PageRequest.of(page, size, sort);
    }

    private Sort.Direction parseDirection(String value) {
        if (value == null || value.isBlank()) {
            return Sort.Direction.DESC;
        }

        try {
            return Sort.Direction.fromString(value.trim());
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                "direction must be ASC or DESC",
                exception
            );
        }
    }
}
```

`MAX_RESULT_WINDOW` in the example is an assumed application policy matching the active index limit. In production, synchronize this value with the actual Elasticsearch setting. Do not raise `index.max_result_window` solely to let clients request very deep pages.

`sku` is used as a tie-breaker assuming the field is unique and typed as keyword. If the system cannot guarantee that, substitute a unique sort ID field.

## 8. Using Pageable with ElasticsearchRepository

Spring Data Elasticsearch repositories can accept `Pageable` in read operations:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Service:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;
    private final ProductPageableFactory pageableFactory;

    public ProductService(
            ProductRepository repository,
            ProductPageableFactory pageableFactory) {
        this.repository = repository;
        this.pageableFactory = pageableFactory;
    }

    public Page<Product> findAll(ProductSearchRequest request) {
        Pageable pageable = pageableFactory.create(request);
        return repository.findAll(pageable);
    }
}
```

The repository uses `Pageable` to execute the paginated/sorted query. `Page<Product>` contains the page content along with metadata such as page number, page size, and total elements as returned by the repository.

If filtering by category or status is needed, declare query methods accepting `Pageable`:

```java
Page<Product> findByStatus(String status, Pageable pageable);
```

Or use `ElasticsearchOperations` with `CriteriaQuery`/`NativeQuery` when search conditions are more complex.

## 9. Using Pageable with CriteriaQuery

CriteriaQuery can combine Criteria and Pageable:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("status").is("ACTIVE");
CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(pageable);
```

Execution:

```java
SearchHits<Product> hits = operations.search(query, Product.class);
```

`Pageable` carries page, size, and sort. Criteria defines the document matching conditions; Pageable determines the result slice and order.

## 10. Using Pageable with NativeQuery

For flexible Query DSL, attach `Pageable` to `NativeQuery`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
    ))
    .withPageable(pageable)
    .build();

SearchHits<Product> hits = operations.search(query, Product.class);
```

In this example, the filter selects ACTIVE products, while `pageable` limits the page and applies the server-validated sort. If specialized sort options such as nested sort or missing-value policy are needed, configure sorting directly using the native Elasticsearch Java Client API for your version.

## 11. Creating an API Accepting page/size/sort

A controller can accept query parameters:

```java
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products")
    public Page<Product> search(@ModelAttribute ProductSearchRequest request) {
        return service.findAll(request);
    }
}
```

The controller receives input, while the service/factory validates bounds and constructs `Pageable`. You can use `@Validated` with Bean Validation to check page/size on the request DTO, but the sort field allowlist still must be enforced on the server layer.

### 11.1 Using Automatic Pageable Binding from Spring MVC

Spring Data Web supports binding `page`, `size`, and `sort` parameters into `Pageable` when enabled:

```java
@GetMapping("/products")
public Page<Product> search(
        @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC)
        Pageable pageable) {
    return service.findAll(pageable);
}
```

`@PageableDefault` sets default values, but does not automatically replace all input validation policies. The application must still cap page size and validate allowed sort properties. You can configure `PageableHandlerMethodArgumentResolver` to set a max page size, while still enforcing a sort allowlist at the service layer.

If using the automatic resolver, inspect how multiple `sort` parameters are parsed and ensure clients cannot request internal fields outside API policy.

## 12. Sorting by text, keyword, Number, and Date

Not all fields sort in the same way.

| Mapping | Typical sort support | Notes |
|---|---|---|
| `keyword` | Yes | Sorts by exact value, usually via doc values |
| `integer`, `long`, `double` | Yes | Sorts by numeric value |
| `date` | Yes | Sorts chronologically |
| `boolean` | Yes | Sorts by boolean value |
| `text` | Usually not directly | Use a keyword multi-field or dedicated sort field |
| `nested` | Conditionally | Requires nested sort context and possibly a filter |

If `name` is a `text` field, sorting by `name` may fail because the field lacks doc values. Configure a multi-field:

```json
"name": {
  "type": "text",
  "fields": {
    "sort": {
      "type": "keyword",
      "normalizer": "lowercase_normalizer"
    }
  }
}
```

Then use the corresponding sort sub-field according to the mapping mechanism supported by Spring Data/Java Client. A normalizer can provide case-insensitive sorting per configured rules. If language-specific sorting or complex collation is needed, design the analyzer/normalizer and test actual results.

### 12.1 Sorting on Nested Fields

If products have a list of variants and you want to sort by variant price, you must specify the nested path. A simple sort like `Sort.by("variants.price")` may be insufficient because Elasticsearch needs to know which nested documents participate in sorting and how to aggregate multiple values (min/max/avg).

Query DSL example:

```json
GET /products/_search
{
  "sort": [
    {
      "variants.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "variants",
          "filter": {
            "term": {
              "variants.available": true
            }
          }
        }
      }
    }
  ],
  "query": {
    "match_all": {}
  }
}
```

This sort selects the lowest price among in-stock variants. This is an advanced sort; use the native sort builder or query API supporting nested sorts in your active Spring Data Elasticsearch version.

## 13. Deep Pagination and `max_result_window`

Offset pagination is convenient for the first page and early pages. However, Elasticsearch must process results prior to the offset to return the requested page. As pages grow deeper, cost rises.

The `index.max_result_window` setting defaults to 10,000. If a request has `from + size` exceeding the limit, Elasticsearch may reject the request. For example, `from = 9900`, `size = 100` reaches the 10,000 limit; `from = 10000`, `size = 20` exceeds it.

Do not solve this by raising the limit to a huge number without evaluating heap, shard count, and workload. For regular UIs, capping page depth is sensible. For exports or traversing hundreds of thousands of documents, use cursor pagination.

### 13.1 `search_after`

`search_after` uses sort values from the last hit of the current page to request the next page. It avoids skipping all preceding documents as offset pagination does.

First page example:

```json
GET /products/_search
{
  "size": 100,
  "query": {
    "match_all": {}
  },
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ]
}
```

Suppose the last hit has sort values:

```json
"sort": ["2025-03-12T10:30:00.000Z", "SKU-1001"]
```

Next page sends:

```json
GET /products/_search
{
  "size": 100,
  "query": {
    "match_all": {}
  },
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ],
  "search_after": ["2025-03-12T10:30:00.000Z", "SKU-1001"]
}
```

Sort order must remain identical across requests. Sort values must establish a sufficiently deterministic order; add a unique tie-breaker so two documents do not share identical sort values.

### 13.2 Point in Time (PIT)

If the index continues receiving writes while a client traverses many pages, the result set can change. Point in time (PIT) creates a stable view of the index for a period of time. Combining PIT with `search_after` fits large, consistent data traversals better.

General workflow:

1. Open a PIT for the index.
2. Search with the PIT ID, stable sort, and bounded page size.
3. Save the sort values of the last hit as a cursor.
4. Send the next request with the same sort and `search_after`.
5. Renew keep-alive as needed and close the PIT when done.

PIT consumes resources on the Elasticsearch side. Set a reasonable lifetime, close the PIT when finished, and do not keep cursors indefinitely. The `Pageable`/`PageRequest` API mainly serves offset pagination; `search_after`/PIT usually requires native query/client APIs depending on version.

## 14. Page Metadata and Total Hit Count

Repositories returning `Page<T>` typically provide:

- `getContent()`: elements on the page.
- `getNumber()`: zero-based current page index.
- `getSize()`: page size.
- `getNumberOfElements()`: actual number of elements on the page.
- `getTotalElements()`: total elements per query results.
- `getTotalPages()`: total number of pages.
- `hasNext()` / `hasPrevious()`: navigation state.

With `ElasticsearchOperations.search(...)`, `SearchHits<T>` contains `getTotalHits()` and a list of `SearchHit<T>`. If an API needs `Page`, you can create a response model holding content, page, size, total, and sort, or use `SearchHitSupport`/`SearchPage` helpers supported by your Spring Data version.

Exact total hit counts can be resource-intensive. With the Elasticsearch Search API, `track_total_hits` can limit exact counting. If the API displays exact total pages, weigh the cost. For infinite scroll, knowing only whether more results exist is usually enough.

## 15. Common Pitfalls

### 15.1 Allowing Unbounded Size

A client can send `size=100000`. This produces huge responses and spikes cluster/client load. Enforce a max size in the API and configure the resolver if using automatic Pageable binding.

### 15.2 Accepting Arbitrary Sort Fields

Non-existent or non-sortable fields can cause Elasticsearch errors. Use an allowlist of public keys mapped to verified fields.

### 15.3 Sorting Directly on a text Field

`text` fields usually lack doc values. Use a keyword multi-field or dedicated sort field. Verify mappings before permitting sorting.

### 15.4 Sorting Only by a Field with Many Duplicate Values

When multiple documents share the same sort value, relative order is unstable. Add a unique, sortable tie-breaker.

### 15.5 Overly Deep Page Numbers

Large offsets increase cost and can exceed `max_result_window`. Cap offsets or switch to `search_after`/PIT.

### 15.6 Failing to Validate Direction

Accept only `ASC`/`DESC`; convert invalid values into clear request errors.

### 15.7 Inconsistent Sort Field Names Between API and Mapping

API key `newest` can map to `createdAt`; client keys do not have to match field names. Maintain a centralized allowlist and review it whenever mappings change.

### 15.8 Confusing Sorting with Relevance Boosting

Field sorting can override relevance order. If results should be prioritized by score, do not accidentally sort by another field; if strict ordering by price/date is required, use sorting rather than inflating boosts.

## 16. Testing Pagination and Sorting

With test data containing duplicate values, verify:

1. Default page and default size are correct.
2. Negative page is rejected.
3. Zero size or size exceeding max is rejected.
4. Sort keys outside the allowlist are rejected.
5. Directions other than ASC/DESC are rejected.
6. Keyword, numeric, and date sorts return the right order.
7. Multi-field sorts apply the right priority order.
8. Tie-breaker keeps order stable when primary field values tie.
9. Offsets exceeding the result window are blocked or redirected to cursor flow.
10. Queries without explicit sort still have clear default behavior.

You should have integration tests against a compatible Elasticsearch instance to verify actual mappings and sorting. Unit tests for the factory can confirm allowlists, validation, and `Pageable` construction; only integration tests verify that fields are sortable and actual results arrive in the right order.

## 17. Implementation Principles

- Use `PageRequest`/`Pageable` to represent page, size, and sort.
- Choose default page and default size intentionally.
- Enforce a maximum page size at the API layer.
- Compute `from` using `long` and check result window bounds.
- Allow only sort keys present in a server-side allowlist.
- Accept only `ASC` or `DESC` directions.
- Select fields with sortable mappings; use keyword for sortable strings.
- Add a unique tie-breaker to keep ordering stable.
- Define a clear default sort or preserve relevance when the endpoint is full-text search.
- Use `Pageable` with repositories, CriteriaQuery, or NativeQuery depending on query style.
- Use `search_after` and PIT when deep/large traversal is needed.
- Do not treat source filtering, boosting, and sorting as substitutes for one another; each mechanism has its own purpose.

## 18. Summary

To control sort properties and page size from input, convert query parameters into `Pageable` only after validation. Pages should start at 0, size needs a default and maximum cap, and offset must stay within the supported result window. Never pass client-supplied sort field names straight through; use an allowlist to map API keys to mapped and verified fields. Direction should accept only ASC or DESC.

`Sort` supports multiple criteria and should include a unique tie-breaker for stable ordering. Sort fields must match mapping capabilities: keyword, numeric, and date fields are generally well-supported; text fields usually need a keyword sub-field or separate sort field; nested sorts need advanced configuration. You can pass `Pageable` to ElasticsearchRepository or attach it to `CriteriaQuery`/`NativeQuery` when using `ElasticsearchOperations`.

Offset pagination fits early pages but grows costly when going deep and is limited by `index.max_result_window`. For large datasets, switch to `search_after` paired with PIT and stable sorting. Controlling inputs with these rules makes search APIs predictable, operationally safe, and aligned with Elasticsearch mappings.

## References

- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch — Sort search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
