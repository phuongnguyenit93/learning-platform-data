# Conventions for Pagination, Sorting, and Filtering

## 1. Why Do APIs Need Consistent Query Conventions?

A list endpoint often serves multiple screens and workflows: an admin console needs to browse all products, a customer app needs to search by keyword, and reports need to filter by status and date range. If an endpoint returns all data in a single call, the response can become huge, queries consume excessive resources, and load times grow with data volume.

Pagination, sorting, and filtering let clients request the exact result set they need:

- **Pagination** limits the number of records returned in one call and allows clients to step through portions of the results.
- **Sorting** determines record order, keeping results stable and easy to read.
- **Filtering** narrows results by keyword, status, price range, time range, or business criteria.

These three capabilities are part of the HTTP API contract. Clients need to know query parameter names, data types, default values, limits, how conditions combine, and the metadata structure in the response. If every endpoint uses a different convention, clients must write custom logic and are prone to sending invalid requests.

In Spring Boot, Springdoc OpenAPI can document these query parameters and response schemas in the OpenAPI document. The goal is for API consumers to understand exactly how to query without reading controller or repository implementations.

## 2. Designing the Pagination Contract

### 2.1. Choosing Offset Pagination

Offset pagination divides results into pages based on a starting position and the number of records to fetch. A common convention uses two query parameters:

- **page**: page index, starting from 0.
- **size**: maximum number of records per page.

Example:

~~~http
GET /api/products?page=0&size=20
GET /api/products?page=1&size=20
GET /api/products?page=2&size=20
~~~

Under this convention, the first page has page equal to 0, and the next page has page equal to 1. If an API chooses 1-based numbering, the documentation must state it clearly and the backend must convert consistently. Do not leave clients guessing the numbering scheme.

Publish default values and limits for size. Example:

| Parameter | Default | Limit | Meaning |
|---|---:|---:|---|
| page | 0 | 0 or greater | Page to retrieve |
| size | 20 | 1 to 100 | Maximum number of records per page |

Size limits prevent requests asking for tens of thousands of records. The backend should validate input values and return appropriate validation errors when page or size is invalid. Never silently accept arbitrarily large values sent by clients.

### 2.2. Response Structure with Metadata

With offset pagination, the response should provide both the current page's data and metadata so clients can drive the UI:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Mechanical keyboard",
      "price": 1290000
    },
    {
      "id": 102,
      "name": "Wireless mouse",
      "price": 450000
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 137,
  "totalPages": 7,
  "first": true,
  "last": false
}
~~~

Field meanings:

| Field | Meaning |
|---|---|
| content | List of records in the current page |
| page | Current page number, following the API's convention |
| size | Applied page size |
| totalElements | Total number of records matching filter criteria |
| totalPages | Total number of pages at the current size |
| first | Whether this is the first page |
| last | Whether this is the last page |

The total record count must be calculated after applying filter conditions. For example, if a warehouse has 10,000 products but only 137 products are ACTIVE, then totalElements for the ACTIVE query must be 137.

If the system avoids counting total records due to query cost, you can design a response returning only content, hasNext, and the next cursor. In that case, do not fabricate a fake totalPages; the contract must reflect the exact pagination model in use.

### 2.3. When to Use Cursor Pagination?

Offset pagination is intuitive and suits moderately sized lists, UIs needing to jump to a specific page, or cases requiring total page counts. However, large offsets can make database queries expensive. Continuously changing data can also cause records to be duplicated or skipped between page loads.

Cursor pagination uses a cursor value to continue from the last read position. Example:

~~~http
GET /api/events?limit=50
GET /api/events?limit=50&cursor=eyJpZCI6MTAwNX0
~~~

The response may look like:

~~~json
{
  "content": [
    {
      "id": 1006,
      "type": "ORDER_CREATED"
    }
  ],
  "nextCursor": "eyJpZCI6MTA1NX0",
  "hasNext": true
}
~~~

Cursors are typically constructed from stable sort fields, such as creation timestamp and ID. Cursor values should be treated as opaque data: clients store and send them back without parsing or modifying them. Base64 is merely a representation encoding, not a security mechanism; if a cursor contains sensitive data or allows altering query positions, sign or protect it appropriately.

Cursor pagination fits event streams, timelines, or large lists with frequently changing data. Offset pagination fits UIs requiring page numbers and jumping to known pages. This choice must be clearly reflected in parameter names and response schemas.

## 3. Data Sorting Conventions

### 3.1. Name and Syntax of the sort Parameter

A common convention uses the **sort** query parameter with a field name and sort direction:

~~~http
GET /api/products?sort=name,asc
GET /api/products?sort=price,desc
~~~

Where:

- **asc** is ascending.
- **desc** is descending.
- The field name must belong to the set of fields permitted for sorting by the API.

APIs supporting multiple criteria can allow repeating the query parameter:

~~~http
GET /api/products?sort=status,asc&sort=createdAt,desc
~~~

The request above sorts by status first, then by createdAt among records sharing the same status. In OpenAPI, an array query parameter can be documented with style=form and explode=true to represent repeated values. If the API uses another syntax, such as a comma-separated string, document the exact parsing rules.

A contract must publish:

- The default sort field when the client omits sort.
- The default direction when the client passes only the field name.
- Whether multiple criteria or only a single criterion are supported.
- How disallowed fields or invalid sort directions are handled.
- How null values and special data types are handled if that affects ordering.

### 3.2. Ensuring Deterministic Ordering

If multiple records share the same value in the sort field, their relative order may shift between requests. This causes pagination bugs: a record may appear on two pages or on no page at all.

To avoid this issue, add a unique tie-breaker field, usually ID. For example, when sorting by createdAt descending, the backend can append id descending as a secondary criterion:

~~~text
createdAt DESC, id DESC
~~~

Deterministic ordering is especially critical for cursor pagination because the cursor must uniquely identify the continuation point.

### 3.3. Allow Sorting Only on Published Fields

Do not take client-submitted property names directly and concatenate them into SQL statements or query expressions. Doing so can cause query errors and open injection risks if field names are handled unsafely.

The backend should use an allowlist, such as allowing only **name**, **price**, **createdAt**, and **status**. If a client sends **sort=passwordHash,desc**, the API should return 400 with a message stating that the sort field is invalid.

Also distinguish field names in the API contract from database column names. A client might send createdAt while the backend maps it to a different property or expression. Never let database structure become a mandatory part of the public contract.

## 4. Data Filtering Conventions

Filtering typically uses dedicated query parameters for each condition. Examples:

~~~http
GET /api/products?status=ACTIVE
GET /api/products?keyword=keyboard
GET /api/products?minPrice=100000&maxPrice=2000000
GET /api/products?createdFrom=2026-01-01T00:00:00Z&createdTo=2026-02-01T00:00:00Z
~~~

Parameter names should reflect business meaning. Use consistent names across similar endpoints, such as status, createdFrom, createdTo, minPrice, and maxPrice.

### 4.1. Exact Filtering and Keyword Filtering

Exact filtering fits enums, identifiers, or statuses:

~~~http
GET /api/orders?status=PAID
GET /api/products?categoryId=12
~~~

Keyword filtering commonly uses keyword or q:

~~~http
GET /api/products?keyword=mechanical%20keyboard
~~~

Documentation must state clearly which fields keyword searches, whether it is case-sensitive, whether leading/trailing whitespace is trimmed, and whether it matches via contains, starts-with, or exact match.

Do not let clients assume keyword always searches every text field. For example, the API may search only product names and codes, not long descriptions.

### 4.2. Range Filtering for Prices or Numbers

For numeric data, a pair of min and max parameters can be used:

~~~http
GET /api/products?minPrice=100000&maxPrice=2000000
~~~

The contract must clarify whether bounds are inclusive. An intuitive convention is that both minPrice and maxPrice are inclusive. If minPrice exceeds maxPrice, the API should return 400 with a consistent error code.

For date-time fields, standardize on ISO 8601 format and timezone handling. For instance, use OffsetDateTime to carry an offset or Instant for UTC instants. Publish whether the time range is inclusive on its bounds.

A common convention for time ranges is a half-open interval: createdFrom is inclusive, while createdTo is exclusive. The request:

~~~http
GET /api/orders?createdFrom=2026-01-01T00:00:00Z&createdTo=2026-02-01T00:00:00Z
~~~

retrieves records created from the start of January 1 up to just before the start of February 1 in UTC. This makes it easy to chain consecutive intervals without double-counting boundary records.

### 4.3. Multi-Value Filtering

Some APIs need to accept multiple statuses or categories. This can be expressed with repeated query parameters:

~~~http
GET /api/orders?status=PAID&status=SHIPPED
~~~

Or using a comma-separated list:

~~~http
GET /api/orders?status=PAID,SHIPPED
~~~

These two options are two different contracts. When using repeated parameters, the OpenAPI document should show the parameter as an array with matching serialization. When using commas, publish the delimiter and how values containing the delimiter are handled.

For long lists, cap the number of elements to prevent oversized requests. Also define how conditions combine: multiple values for the same field usually mean OR, whereas different filter fields combine with AND. For example, status in PAID or SHIPPED and createdFrom within the time range.

### 4.4. Defining Missing, Empty, and Null Values

The following cases do not necessarily share the same meaning:

- Parameter omitted: do not apply that filter condition.
- Empty string passed: may be rejected or normalized to no condition.
- Literal null passed: this is a literal character string in the query string, not automatically a Java null value.
- Invalid value passed: return a validation error.

The API contract must specify behavior for these cases, especially when clients build URLs from search forms. Never let empty-value handling vary arbitrarily across endpoints.

## 5. Combining Pagination, Sorting, and Filtering

A list endpoint can support all three parameter groups simultaneously:

~~~http
GET /api/products?page=0&size=20&sort=createdAt,desc&status=ACTIVE&keyword=keyboard&minPrice=100000&maxPrice=2000000
~~~

The backend should apply filters first, then sort, and finally slice the page of data. The total record count in metadata is the number of records after filtering but before pagination slicing.

Logical processing order:

1. Validate syntax and bounds of query parameters.
2. Build filter conditions according to business rules.
3. Apply the default or client-requested sort order.
4. Fetch the page or batch by page/size or cursor/limit.
5. Build a response containing data and consistent metadata.

If a client changes filters, reset page to 0 when using offset pagination because the current page may exceed the new total page count. Clients also need to resend all filter and sort criteria when switching pages; each GET request should carry enough information to reproduce the results.

## 6. Implementation with Spring Data and Spring Boot

Spring Data provides data types supporting pagination and sorting:

- **Pageable** describes page number, size, and sort order.
- **PageRequest** constructs a specific pagination request.
- **Sort** represents one or more sort criteria.
- **Page<T>** holds page data along with metadata such as total elements and total pages.
- **Slice<T>** provides page data and whether a next page exists without requiring a total record count.

Example creating a pagination request:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Page index in PageRequest starts at 0. If an API publishes 1-based pages, convert explicitly before constructing PageRequest and validate cases where page is less than 1.

In a repository, a method can return Page:

~~~java
Page<Product> findByStatus(
    ProductStatus status,
    Pageable pageable
);
~~~

Spring Data uses Pageable to apply limits and sorting appropriate to the persistence store. For complex filters, Specification, Querydsl, or custom queries can be used, provided the total-count condition matches the content-retrieval condition.

Not every endpoint needs a total record count. If count queries are expensive, Slice may fit better. Choose the result type according to product needs and reflect it clearly in the API response.

## 7. Documenting Query Parameters with Springdoc OpenAPI

Springdoc can infer partial details from controller signatures, yet explicit descriptions make documentation much easier to use. Commonly used annotations include:

| Annotation | Role |
|---|---|
| **@Operation** | Describes the endpoint's purpose |
| **@Parameter** | Describes each query parameter, examples, and constraints |
| **@Parameters** | Groups multiple parameter descriptions |
| **@Schema** | Describes data types and response schemas |
| **@ApiResponse** | Describes response codes and error or success payloads |
| **@ParameterObject** | Expands an object into separate query parameters in docs, often used with Pageable |

Controller example documenting pagination, sorting, and filtering:

~~~java
@RestController
@RequestMapping("/api/products")
@Validated
@Tag(name = "Products", description = "Product lookup API")
public class ProductController {

    @GetMapping
    @Operation(
        summary = "Search products",
        description = "Filter products, sort, and return one page of results."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Returns a page of matching products"
    )
    @ApiResponse(
        responseCode = "400",
        description = "Invalid pagination or filter parameter"
    )
    public ProductPageResponse search(
        @Parameter(
            description = "Page number, starting from 0",
            example = "0"
        )
        @RequestParam(defaultValue = "0")
        @Min(0) int page,

        @Parameter(
            description = "Items per page, from 1 to 100",
            example = "20"
        )
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int size,

        @Parameter(
            description = "Repeatable parameter; each value has form field,asc or field,desc",
            example = "createdAt,desc"
        )
        @RequestParam(required = false)
        List<String> sort,

        @Parameter(
            description = "Keyword searched in product name and code",
            example = "keyboard"
        )
        @RequestParam(required = false)
        String keyword,

        @Parameter(
            description = "Product status",
            example = "ACTIVE"
        )
        @RequestParam(required = false)
        ProductStatus status,

        @Parameter(
            description = "Minimum price, inclusive",
            example = "100000"
        )
        @RequestParam(required = false)
        @DecimalMin("0") BigDecimal minPrice,

        @Parameter(
            description = "Maximum price, inclusive",
            example = "2000000"
        )
        @RequestParam(required = false)
        @DecimalMin("0") BigDecimal maxPrice
    ) {
        Sort requestedSort = ProductSorts.parse(sort);
        Pageable pageable = PageRequest.of(page, size, requestedSort);

        Page<Product> result = productService.search(
            keyword, status, minPrice, maxPrice, pageable
        );

        return ProductPageResponse.from(result);
    }
}
~~~

The example illustrates declaring parameters and calling the service. In a real application, also handle cases where minPrice exceeds maxPrice, validate sort fields against an allowlist, and map validation exceptions to a unified error response. Imports and classes ProductSorts, ProductService, and ProductPageResponse are omitted to focus on the endpoint contract.

With Spring Data Pageable, you can use **@ParameterObject** with **@PageableDefault** so Springdoc expands page, size, and sort into query parameters:

~~~java
@GetMapping
public Page<ProductResponse> search(
    @ParameterObject
    @PageableDefault(
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return productService.search(pageable);
}
~~~

This approach is concise when using Spring Data's default Pageable conventions. If the API has size limits, non-default page numbering, or custom sort syntax, verify the generated OpenAPI document and add clear descriptions for those limits. Pageable inference can depend on the Springdoc version and application configuration.

## 8. Documenting Paginated Response Schemas

You do not have to expose Spring Data's Page object directly. A dedicated response DTO keeps the API contract more stable across framework or internal structure changes.

Example:

~~~java
@Schema(description = "Page of product search results")
public record ProductPageResponse(
    @Schema(description = "Products in the current page")
    List<ProductResponse> content,

    @Schema(description = "Page number starting from 0", example = "0")
    int page,

    @Schema(description = "Page size", example = "20")
    int size,

    @Schema(description = "Total number of products after filtering", example = "137")
    long totalElements,

    @Schema(description = "Total number of pages", example = "7")
    int totalPages,

    @Schema(description = "Whether this is the first page", example = "true")
    boolean first,

    @Schema(description = "Whether this is the last page", example = "false")
    boolean last
) {
    public static ProductPageResponse from(Page<Product> result) {
        return new ProductPageResponse(
            result.getContent().stream()
                .map(ProductResponse::from)
                .toList(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast()
        );
    }
}
~~~

Schema fields must match backend behavior. If the API does not return totalElements or totalPages, do not document those two fields in OpenAPI. When using cursors, create a separate schema with nextCursor and hasNext rather than forcing cursors into a page/totalPages structure.

## 9. Documenting Validation Errors and Edge Cases

Query parameters are client input, so the API must define responses when values are invalid.

Common scenarios:

| Scenario | Behavior to define |
|---|---|
| page less than 0 | Return 400 or normalize per published rule |
| size equal to 0 or exceeding limit | Return 400 or apply published maximum cap |
| sort uses a disallowed field | Return 400 with a clear error code |
| Invalid sort direction | Return 400 |
| minPrice greater than maxPrice | Return 400 |
| createdFrom after createdTo | Return 400 |
| Nonexistent enum filter value | Return 400 |
| No matching records | Return 200 with empty content and matching metadata |

Finding no matching records is normally not an HTTP 404 error for a list endpoint. The endpoint still exists and the query is valid; the result is simply an empty list. This convention lets clients handle lists uniformly.

Error responses can be documented using a shared schema, such as code, message, details, and timestamp. Use **@ApiResponse** or shared OpenAPI configuration so endpoints publish a consistent error structure. Also ensure the exception handler actually returns the documented status codes and schemas.

## 10. Testing Pagination, Sorting, and Filtering Contracts

OpenAPI documentation is only valuable when it reflects actual endpoint behavior. Test the following case groups:

**Pagination:**
- First page, middle page, and last page.
- Empty page when page exceeds range.
- Default size, minimum size, and maximum size.
- Negative page values or out-of-range size.
- totalElements and totalPages metadata when filters are active.

**Sorting:**
- Ascending and descending.
- Multiple sort criteria.
- Multiple records sharing the same sort value to verify the tie-breaker.
- Fields outside the allowlist and invalid directions.
- Stability of result order across consecutive page loads.

**Filtering:**
- Each condition individually and multiple conditions combined.
- Valid and invalid enum values.
- Numeric and time ranges right on the boundaries.
- Multiple values for the same parameter.
- Missing, empty, or whitespace-containing parameters.
- Empty results for a valid request.

Use integration tests to invoke the endpoint with real query strings and verify both JSON responses and status codes. Contract tests can verify that the OpenAPI document contains the right parameter names, data types, defaults, bounds, and response schemas. When the contract changes, diff the document across versions to identify client-impacting changes.

## 11. Complete API Contract Example

A product search request can be standardized as follows:

~~~http
GET /api/products?page=0&size=20&sort=createdAt,desc&sort=id,desc&status=ACTIVE&keyword=keyboard&minPrice=100000&maxPrice=2000000
~~~

The endpoint contract should document:

- page starts at 0, defaulting to 0.
- size defaults to 20, capped at a maximum of 100.
- sort is repeatable; each value consists of an allowed field name and asc or desc direction.
- status only accepts values from the ProductStatus enum.
- keyword searches within product name and code according to published rules.
- minPrice and maxPrice have inclusive bounds.
- Different filter conditions combine with AND.
- Results are deterministically ordered, optionally using id as a secondary tie-breaker.
- The response returns content plus pagination metadata; if no records match, content is an empty array.

Example response:

~~~json
{
  "content": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0,
  "first": true,
  "last": true
}
~~~

This is a valid response when no products match the criteria. Clients can still display an empty-results state while preserving the user's selected filters.

## 12. Principles for Maintaining Long-Term Contracts

Pagination, sorting, and filtering conventions should be applied uniformly across endpoints sharing the same purpose. When an endpoint changes parameter names, page numbering, defaults, or response structure, that can be a breaking change for existing clients.

Principles for maintaining the contract:

- Use clear and consistent parameter names.
- Publish defaults, limits, and list serialization behavior.
- Use deterministic ordering to avoid duplicate or skipped records across pages.
- Permit sorting only on published fields.
- Clearly define bounds for numeric and time filters.
- Choose offset or cursor based on data characteristics and UI needs.
- Document query parameters, response schemas, and errors with Springdoc OpenAPI.
- Verify generated documentation alongside integration tests and contract tests.

When these conventions are captured in the OpenAPI document, clients can construct requests consistently, backends can safely control queries, and development teams have a clear baseline for testing, versioning, and distributing the API contract.

