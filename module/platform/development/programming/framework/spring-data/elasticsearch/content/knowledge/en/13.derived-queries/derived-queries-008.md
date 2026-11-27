# `OrderBy`, `Sort`, and `Pageable` in Query Methods

When querying data with Spring Data Elasticsearch, applications often need to control result ordering and retrieve only a subset of documents per call. Spring Data supports three ways to express this in repository methods:

- `OrderBy` declares a fixed sort order directly in the method name.
- `Sort` lets the caller pass sorting criteria at runtime.
- `Pageable` describes the requested page, page size, and optionally includes `Sort`.

These mechanisms keep repository methods concise and readable. However, Elasticsearch can only sort efficiently on fields with appropriate mappings; offset-based pagination also has limits when paginating deep into large result sets.

## 1. Preparing the domain model and repository

Suppose an application stores product documents with category, name, price, and creation timestamp properties:

~~~java
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
    private String category;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructor, getters, and setters
}
~~~

The repository can extend `ElasticsearchRepository` and declare derived query methods:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryOrderByCreatedAtDesc(String category);

    List<ProductDocument> findByCategory(String category, Sort sort);

    Page<ProductDocument> findByCategory(String category, Pageable pageable);
}
~~~

All three methods share the same `category` filter condition while giving callers different ways to control ordering or pagination. Methods are parsed from their names and parameters; Spring Data builds the corresponding Elasticsearch query.

## 2. Fixed sorting with `OrderBy`

`OrderBy` is a suffix in a derived query method name. It specifies the field to sort by and ascending/descending direction.

General syntax:

~~~text
findBy<Condition>OrderBy<FieldName>Asc
findBy<Condition>OrderBy<FieldName>Desc
~~~

Examples:

~~~java
List<ProductDocument> findByCategoryOrderByCreatedAtDesc(String category);

List<ProductDocument> findByActiveTrueOrderByPriceAsc();
~~~

The first method filters by category and orders by newest creation timestamp first. The second filters documents with `active = true` and orders by ascending price.

### 2.1. Sorting by multiple fields

You can declare multiple fields in the `OrderBy` clause. For example, sorting by creation timestamp descending, then SKU ascending:

~~~java
List<ProductDocument> findByCategoryOrderByCreatedAtDescSkuAsc(String category);
~~~

Fields appearing earlier have higher sort priority. Elasticsearch compares `createdAt` first; if two documents share the same timestamp, it uses `sku` to break ties.

A secondary sort order is useful when many documents share identical values on the primary sort field. Sorting solely on a field with many duplicate values can leave the relative order of tied documents unstable across queries.

### 2.2. When to use `OrderBy`?

Use `OrderBy` when the ordering is a fixed business rule and callers do not need to change it. For example:

- Order history always displays newest first.
- Default leaderboards always sort scores from highest to lowest.
- Product catalogs always sort by ascending SKU.

The advantage is that the method name makes the order explicit and callers do not pass an extra `Sort` object. The limitation is that each distinct sort order may require a separate method; if the UI lets users change sorting, a `Sort` parameter is usually more flexible.

## 3. Dynamic sorting with `Sort`

`Sort` belongs to `org.springframework.data.domain.Sort`. Callers construct a `Sort` instance and pass it to a repository method accepting a `Sort` parameter.

Example method:

~~~java
List<ProductDocument> findByCategory(String category, Sort sort);
~~~

Calling with one criterion:

~~~java
Sort sort = Sort.by(Sort.Direction.DESC, "createdAt");
List<ProductDocument> products =
        productRepository.findByCategory("ACCESSORIES", sort);
~~~

Callers can switch ordering without creating new methods:

~~~java
Sort priceAscending = Sort.by(Sort.Direction.ASC, "price");
Sort priceDescending = Sort.by(Sort.Direction.DESC, "price");

List<ProductDocument> cheaperFirst =
        productRepository.findByCategory("ACCESSORIES", priceAscending);

List<ProductDocument> expensiveFirst =
        productRepository.findByCategory("ACCESSORIES", priceDescending);
~~~

### 3.1. Using `Sort.Order` for multiple criteria

`Sort.by` can take multiple `Sort.Order` instances. Each order specifies a field and sort direction:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku"));

List<ProductDocument> products =
        productRepository.findByCategory("ACCESSORIES", sort);
~~~

In this example, results are sorted by `createdAt` descending; documents with the same timestamp are sorted by `sku` ascending.

You can also compose `Sort` incrementally:

~~~java
Sort sort = Sort.unsorted()
        .and(Sort.by(Sort.Order.desc("createdAt")))
        .and(Sort.by(Sort.Order.asc("sku")));
~~~

When no sorting is needed, you can pass `Sort.unsorted()` if the method requires a `Sort` parameter.

### 3.2. Property names in Sort

In repository methods, prefer using the entity's Java property names, such as `createdAt` or `price`. Spring Data Elasticsearch uses mapping metadata to map Java properties to corresponding Elasticsearch field names when custom field names are configured.

Example where a Java property is stored in snake case:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

When using repository `Sort`, pass the domain model property `createdAt` so mapping metadata can resolve the field. For multi-field subfields, nested fields, or Elasticsearch fields without a matching Java property, verify the field-path syntax supported by your Spring Data version and inspect the generated request.

Do not pass user-supplied property names directly into `Sort.by` without validation. Map UI sort options to an allowlist of permitted fields to avoid arbitrary sorting on sensitive or unsortable fields.

## 4. Paginating with `Pageable`

`Pageable` represents pagination details for the requested page. It carries page number, page size, and optionally sort criteria.

Example repository method:

~~~java
Page<ProductDocument> findByCategory(String category, Pageable pageable);
~~~

Fetching the first page of 20 documents:

~~~java
Pageable pageable = PageRequest.of(0, 20);
Page<ProductDocument> page =
        productRepository.findByCategory("ACCESSORIES", pageable);
~~~

`PageRequest.of(pageNumber, pageSize)` uses zero-based page indices. Thus:

- `PageRequest.of(0, 20)` fetches the first page, up to 20 documents.
- `PageRequest.of(1, 20)` fetches the second page.
- `PageRequest.of(2, 20)` fetches the third page.

With page size 20, the second page starts after the first 20 results. Callers do not need to compute offsets manually when using `PageRequest`.

### 4.1. Reading metadata from `Page`

`Page<T>` contains the page content along with pagination metadata:

~~~java
Page<ProductDocument> page =
        productRepository.findByCategory(
                "ACCESSORIES",
                PageRequest.of(0, 20));

List<ProductDocument> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
boolean hasPrevious = page.hasPrevious();
~~~

Commonly used methods:

| Method | Meaning |
| --- | --- |
| `getContent()` | List of documents in the current page. |
| `getNumber()` | Current page number, starting from 0. |
| `getSize()` | Requested page size. |
| `getNumberOfElements()` | Actual number of elements in the current page. |
| `getTotalElements()` | Total matching elements according to total hit metadata returned by the backend. |
| `getTotalPages()` | Total pages computed from total elements and page size. |
| `hasNext()` | Whether a next page exists. |
| `hasPrevious()` | Whether a previous page exists. |

`Page` fits UIs that display total result counts or total page counts. Computing exact totals on large datasets can be resource-intensive; Elasticsearch has total-hit tracking limits/relations depending on query settings and version. If the UI only needs a "Load more" button, you do not necessarily need total page counts.

### 4.2. Using `List` with `Pageable`

If you only need a page's content without `Page` metadata, the repository method can return `List<T>` while accepting `Pageable`:

~~~java
List<ProductDocument> findByCategory(String category, Pageable pageable);
~~~

~~~java
List<ProductDocument> firstPage = productRepository.findByCategory(
        "ACCESSORIES",
        PageRequest.of(0, 20));
~~~

`List` returns only the documents in the requested result window. Callers do not receive `getTotalElements()` or `getTotalPages()` as with `Page`.

Choose return types based on your API contract:

- Use `Page<T>` if the UI needs total counts and page navigation state.
- Use `List<T>` with `Pageable` if you only need a slice of results without `Page` metadata.
- Use `List<T>` without `Pageable` only when result size is bounded elsewhere; avoid fetching unbounded documents from a large index.

## 5. Placing Sort inside Pageable

`Pageable` can carry `Sort`, allowing a single parameter to specify both pagination and result ordering.

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));

Page<ProductDocument> page =
        productRepository.findByCategory("ACCESSORIES", pageable);
~~~

You can create an unsorted `Pageable` or pass sorting on another call:

~~~java
Pageable firstPage = PageRequest.of(0, 20);
Pageable secondPage = PageRequest.of(
        1,
        20,
        Sort.by(Sort.Order.asc("price")));
~~~

When a method already takes `Pageable`, there is normally no need for a separate `Sort` parameter. Keeping sort inside `Pageable` keeps parameter lists clean and bundles page number, page size, and sort in one object.

## 6. Combining query conditions with sorting

Derived query conditions can be combined with `OrderBy`, `Sort`, or `Pageable`.

Example filtering active products by category and sorting by ascending price:

~~~java
List<ProductDocument> findByCategoryAndActiveTrueOrderByPriceAsc(
        String category);
~~~

Example letting the caller choose sort:

~~~java
Page<ProductDocument> findByCategoryAndActiveTrue(
        String category,
        Pageable pageable);
~~~

Calling the method with a sorted page:

~~~java
Pageable pageable = PageRequest.of(
        0,
        25,
        Sort.by(Sort.Order.desc("createdAt")));

Page<ProductDocument> page =
        productRepository.findByCategoryAndActiveTrue(
                "ACCESSORIES", pageable);
~~~

Filter conditions come from the method name and arguments; sorting/pagination come from the runtime object. This allows one repository method to serve multiple screens with different sort orders.

## 7. Which fields can be sorted?

Not every field is suitable for sorting. Elasticsearch needs sort-capable data structures, typically doc values for scalar types.

| Field type | Typical sort capability |
| --- | --- |
| `keyword` | Yes; commonly used for codes, statuses, normalized names, and exact values. |
| `long`, `integer`, `double`, `float` | Yes; suitable for numeric sorting. |
| `date` | Yes; suitable for chronological sorting. |
| `boolean` | Can sort by boolean value. |
| `text` | No doc values by default; direct sorting is normally unavailable. |

### 7.1. Using multi-fields for text

If you need both full-text search and string sorting, declare a `keyword` subfield:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "sort": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Field `name` serves `match` queries; subfield `name.sort` serves intact-string sorting. When sorting via repositories on a subfield, verify how your Spring Data Elasticsearch version handles multi-field paths; if direct control is needed, use a query API that allows specifying the sort field explicitly.

Do not enable `fielddata` on `text` solely for sorting without evaluating heap cost. For typical sorting needs, a `keyword` multi-field is usually better.

### 7.2. Sorting on nested fields

If a field lives inside a `nested` array, sorting requires configuring a nested path and possibly a nested filter to select which value participates in sorting. A simple `Sort.by("lines.price")` does not necessarily capture nested sort semantics.

For complex nested sorting, use Spring Data Elasticsearch query APIs or native Elasticsearch queries to declare `nested` sort options, rather than trying to express everything via derived method names.

## 8. Stable ordering during pagination

Offset pagination assumes a stable result ordering. If multiple documents share the same sort value, or data changes between page requests, documents may repeat or be skipped across pages.

Example sorting only by `createdAt`:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt")));
~~~

If multiple products share the same timestamp, Elasticsearch makes no business-level stability guarantee among them. Add a unique, sortable field as a secondary tie-breaker, such as `sku` if SKUs are truly unique:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));
~~~

Do not assume `_id` metadata is always an ideal sort field. If you need a deterministic tie-breaker, use an indexed unique business field with doc values, or use Elasticsearch-specific cursor/sort mechanisms.

Even with a tie-breaker, offset pagination can still shift if documents are inserted, deleted, or updated while a user browses pages. For rapidly changing data, choose a better suited pagination strategy.

## 9. Deep pagination limits in Elasticsearch

`Pageable` is typically translated into offset/size (`from`/`size`) parameters. Elasticsearch limits the default result window via `index.max_result_window`, commonly 10,000 documents per index.

For example, with page size 100 and requesting page 120, the offset is 11,900. The query can exceed the default limit and be rejected by Elasticsearch.

Do not raise `index.max_result_window` to huge values just to let users jump to very deep pages. Elasticsearch must retain and sort results from the start of the window up to the requested offset; memory and CPU costs grow with depth.

### 9.1. Using `search_after` for deep pagination

For large result sets, Elasticsearch recommends `search_after` instead of deep offset pagination. This mechanism uses the sort values of the last hit on the current page as a cursor to fetch the next page.

General flow:

1. Run the query with a deterministic sort and fetch the first page.
2. Read the `sort` array from the last hit.
3. Send the next query with the same conditions and sort, adding `search_after` set to those sort values.
4. Repeat until no results remain.

Illustrative REST API example:

~~~http
GET /products/_search
Content-Type: application/json

{
  "size": 100,
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ],
  "query": {
    "term": {
      "category": "ACCESSORIES"
    }
  }
}
~~~

Take the sort values from the last hit and pass them into the next request:

~~~json
{
  "size": 100,
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ],
  "search_after": [
    "2026-11-13T09:30:00Z",
    "KB-001"
  ],
  "query": {
    "term": {
      "category": "ACCESSORIES"
    }
  }
}
~~~

Values in `search_after` must match the order and format of the sort clause in the previous request. The sort must be deterministic; where appropriate, combine with Point in Time (PIT) to preserve a consistent view of data throughout pagination.

Offset-based `Pageable` does not automatically convert into a `search_after` cursor. If your use case needs deep pagination, use Spring Data Elasticsearch query/client APIs that support `search_after`/PIT in your version, or build a dedicated cursor endpoint. Do not represent cursors with huge page numbers.

### 9.2. Scroll for batch processing

For exports or batch jobs reading many documents sequentially, the scroll API was historically used to iterate through batches. In modern Elasticsearch versions, PIT combined with `search_after` is usually the recommended choice for ordered deep pagination. Pick the API by use case: user interfaces, batch exports, and background processing have different requirements.

## 10. `Page`, total counts, and counting cost

`Page<T>` is useful because it supplies `totalElements` and `totalPages`. However, exact total hit counts can be expensive for complex queries or large datasets.

Elasticsearch uses `track_total_hits` to control total hit counting. Depending on the request and version, total hits may be returned with an exact relation (`eq`) or merely a lower bound (`gte`). When building public APIs, do not assume every query returns an exact total if search settings cap hit tracking.

If the UI only needs to know whether a next page exists, you can fetch one extra item to determine `hasNext`, or use cursor-based pagination. This avoids depending on total page counts on very large datasets.

## 11. Validating Pageable and Sort inputs from APIs

Do not pass raw HTTP parameters directly into `PageRequest` or `Sort` without validation. APIs should cap page sizes and restrict sortable fields.

Example service receiving page number and size:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public Page<ProductDocument> searchByCategory(
        String category, int page, int size, String sortBy, String direction) {

    int safePage = Math.max(page, 0);
    int safeSize = Math.min(Math.max(size, 1), 100);

    Sort sort = switch (sortBy) {
        case "price" -> Sort.by("price");
        case "createdAt" -> Sort.by("createdAt");
        case "name" -> Sort.by("name");
        default -> Sort.by("createdAt");
    };

    if ("desc".equalsIgnoreCase(direction)) {
        sort = sort.descending();
    } else {
        sort = sort.ascending();
    }

    Pageable pageable = PageRequest.of(safePage, safeSize, sort);
    return productRepository.findByCategory(category, pageable);
}
~~~

This snippet illustrates clamping page size and allowlisting sort fields. In a real application, confirm `name` has a sortable mapping; if `name` is `text`, target its `keyword` subfield via suitable query mapping or remove that option.

Never accept arbitrary field names directly from clients, as this can lead to runtime errors, expensive queries, or sorting on unintended fields.

## 12. How to combine `OrderBy`, `Sort`, and `Pageable`

The three mechanisms serve related goals with differing levels of flexibility:

| Mechanism | Where declared? | Changeable at runtime? | When to use? |
| --- | --- | --- | --- |
| `OrderBy` | Inside repository method name. | No; fixed in the method. | Default business sort rules. |
| `Sort` | Repository method parameter. | Yes. | Callers choose sort order without pagination. |
| `Pageable` | Repository method parameter. | Yes; holds page, size, and optionally Sort. | UI needs pagination and possibly dynamic sorting. |

Selection rules:

1. If all callers always use the same ordering, choose `OrderBy` so the method name is self-documenting.
2. If callers choose sorting while retrieving a differently bounded result set, use `Sort`.
3. If callers fetch results page by page, use `Pageable`; place sort inside `Pageable` when needed.
4. If deep traversal over large datasets or constantly changing data is required, consider `search_after` and PIT instead of large page numbers.

Avoid creating too many methods differing only by sort order if sorting is a UI choice. Conversely, avoid exposing every fixed business ordering as an arbitrary parameter when the application needs a clear query contract.

## 13. Complete example

Repository:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryOrderByCreatedAtDesc(String category);

    List<ProductDocument> findByCategory(String category, Sort sort);

    Page<ProductDocument> findByCategory(String category, Pageable pageable);
}
~~~

Service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<ProductDocument> newestProducts(String category) {
        return repository.findByCategoryOrderByCreatedAtDesc(category);
    }

    public List<ProductDocument> sortedProducts(String category) {
        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku"));
        return repository.findByCategory(category, sort);
    }

    public Page<ProductDocument> productPage(
            String category, int pageNumber, int pageSize) {

        Pageable pageable = PageRequest.of(
                pageNumber,
                pageSize,
                Sort.by(Sort.Order.desc("createdAt"),
                        Sort.Order.asc("sku")));

        return repository.findByCategory(category, pageable);
    }
}
~~~

In this example, `newestProducts` has a fixed order. `sortedProducts` accepts dynamic sort criteria. `productPage` takes both paging and sorting, returning `Page<ProductDocument>` so callers can read both content and metadata.

## 14. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `OrderBy` method fails to parse | Field name or suffix syntax does not match domain property. | Check spelling, camel case, and entity property names. |
| Sorting fails on text field | `text` fields lack doc values by default. | Use a `keyword` subfield or a separate sortable field. |
| Sorting by field produces unexpected results | Elasticsearch field name mismatches mapping or confuses Java property with stored name. | Check `@Field(name = ...)` and inspect generated queries. |
| Deep pages rejected | Offset exceeds `index.max_result_window`. | Use `search_after`/PIT or redesign the data traversal flow. |
| Duplicate or missing documents across pages | Sort lacks a unique tie-breaker or data changes during pagination. | Use deterministic sorting and consider PIT/cursor pagination. |
| Unexpected total page count | Total hits may be capped or data changed between requests. | Check `track_total_hits` and API metadata requirements. |
| Sort API throws runtime errors | Client passed nonexistent or unsortable field. | Allowlist sort fields and validate mappings. |

## 15. Workflow for choosing and validating query methods

When designing repository methods with sorting or pagination, determine:

1. Which filter conditions belong in the method name and parameters?
2. Is sort order fixed by business rules or chosen by the caller?
3. Does the sort field have an appropriate mapping supporting doc values?
4. Is a unique secondary sort needed to maintain stable ordering?
5. Does the caller need `Page` with total counts or only a `List` for the current page?
6. What is the maximum page size, and can offsets hit the result window limit?
7. Does data change continuously while users paginate?
8. If deep pagination is needed, does your Spring Data version's query/client API support cursor/PIT as required?

`OrderBy` expresses fixed ordering in the method name, `Sort` lets callers choose ordering at runtime, and `Pageable` combines page number, page size, and optional sorting. Using sortable fields, capping page sizes, and choosing cursor strategies for large result sets keeps repository queries clean and avoids pagination performance and stability pitfalls.
