# Combining @ParameterObject with Pagination Parameters

List APIs often need to accept both business filters and pagination/sorting parameters. For example, a client wants to find paid orders created within a date range, view the second page with 20 results, and sort by newest creation time.

Spring Data provides Pageable to group page, size, and sort information; Spring Data Web binds these values from Spring MVC requests. With springdoc-openapi, **@ParameterObject** allows Pageable properties to be described as individual query parameters in OpenAPI. Pageable can be combined with another query DTO to keep controller signatures clean and help Swagger UI show the full way to call the API.

This lesson explains how to combine a filter object with Pageable, set default values, configure parameter names and page size limits, describe paginated responses, and verify the generated documentation.

## 1. Pagination and Sorting in List APIs

Instead of returning all records in a single call, a paginated API splits results into smaller parts. Clients send the page and page size information:

- **page:** index of the page to retrieve.
- **size:** maximum number of items per page.
- **sort:** property and sort direction.

With the common default configuration of Spring Data Web, page indexing starts at 0. For example:

~~~http
GET /api/orders?page=0&size=20
~~~

This request fetches the first page with up to 20 items. To fetch the next page:

~~~http
GET /api/orders?page=1&size=20
~~~

The sort parameter allows sorting results:

~~~http
GET /api/orders?page=0&size=20&sort=createdAt,desc
~~~

Multiple criteria can be specified by repeating the sort parameter:

~~~http
GET /api/orders?page=0&size=20&sort=createdAt,desc&sort=id,asc
~~~

This example sorts by createdAt descending; if two records share the same creation time, id ascending is used as the next criterion.

Pagination helps limit the data transferred over the network and the processing work per request. However, you need to set a size limit and choose a pagination approach suited to your data scale.

## 2. Pageable Groups page, size, and sort

Spring Data defines the Pageable interface to represent pagination requests. In a controller, Spring can automatically build Pageable from query parameters through Spring Data Web.

Simple example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    public Page<OrderResponse> listOrders(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable
    ) {
        return orderService.findAll(pageable);
    }
}
~~~

Spring Data parses the query string and creates a Pageable containing:

- page number.
- page size.
- Sort consisting of one or more Order instances.

The controller passes Pageable down to the service and repository to query data by page. You do not need to declare page, size, and sort separately when using Pageable.

To make springdoc render Pageable as query parameters in OpenAPI, attach @ParameterObject:

~~~java
import org.springdoc.core.annotations.ParameterObject;

@GetMapping("/api/orders")
public Page<OrderResponse> listOrders(
    @ParameterObject Pageable pageable
) {
    return orderService.findAll(pageable);
}
~~~

In springdoc-openapi v2, @ParameterObject lives in the org.springdoc.core.annotations package. For other major versions, check the package and migration guide for the version in use.

## 3. What Role Does @ParameterObject Play?

@ParameterObject instructs springdoc to inspect an object's properties and turn them into individual parameters. When placed on Pageable, the documentation typically exposes these parameters:

| Query parameter | Meaning | Typical type |
|---|---|---|
| page | Page index | integer |
| size | Items per page | integer |
| sort | Sorting criteria | string or array of strings depending on modeling |

Given the controller:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> listOrders(
    @ParameterObject Pageable pageable
) {
    return orderService.findAll(pageable);
}
~~~

OpenAPI may describe the operation similarly to:

~~~yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
            format: int32
            default: 0
        - name: size
          in: query
          required: false
          schema:
            type: integer
            format: int32
            default: 20
        - name: sort
          in: query
          required: false
          schema:
            type: array
            items:
              type: string
      responses:
        '200':
          description: Page of orders
~~~

This is an illustrative shape. Defaults, the type of sort, and specific schema names may depend on annotations, Spring Data Web configuration, and the springdoc version. Always verify the actual JSON at /v3/api-docs.

@ParameterObject is only for documentation generation. Spring Data Web is what binds query parameters into Pageable at runtime. If Swagger UI shows page while the application's resolver uses another parameter name, requests can still fail to bind properly.

## 4. Combining a Query DTO with Pageable

In real APIs, clients often need to filter by status, keyword, or creation date while also paginating. You can use two separate object parameters:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ParameterObject @ModelAttribute OrderSearchCriteria criteria,
    @ParameterObject Pageable pageable
) {
    return orderService.search(criteria, pageable);
}
~~~

Query DTO:

~~~java
public class OrderSearchCriteria {

    private String keyword;
    private OrderStatus status;
    private LocalDate createdFrom;
    private LocalDate createdTo;

    public OrderSearchCriteria() {
    }

    // Getters and setters.
}
~~~

Sample request:

~~~http
GET /api/orders?keyword=ORD&status=PAID&createdFrom=2026-01-01&createdTo=2026-01-31&page=0&size=20&sort=createdAt,desc
~~~

Spring MVC binds keyword, status, createdFrom, and createdTo into OrderSearchCriteria. Spring Data Web binds page, size, and sort into Pageable. springdoc uses the two @ParameterObject annotations to publish both parameter groups.

This combination separates two responsibilities:

- OrderSearchCriteria holds business filtering conditions.
- Pageable holds pagination slicing and sort order.

The service can accept both:

~~~java
public Page<OrderResponse> search(
    OrderSearchCriteria criteria,
    Pageable pageable
) {
    return orderRepository.search(criteria, pageable)
        .map(orderMapper::toResponse);
}
~~~

Repository querying depends on the implementation. Whether using JPQL, Criteria API, Specification, or a query builder, apply Pageable to the query so the database only returns the required slice of data.

## 5. Setting Defaults with @PageableDefault

@PageableDefault allows setting default page, size, sort, and direction when the client omits the corresponding parameters.

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> listOrders(
    @ParameterObject
    @PageableDefault(
        page = 0,
        size = 25,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.findAll(pageable);
}
~~~

Meaning:

- page = 0: start from the first page under default numbering.
- size = 25: fetch at most 25 items by default.
- sort = "createdAt": sort by creation time.
- direction = DESC: newer records appear first.

If the client sends page or size, the request values are typically used instead of the corresponding defaults. Limits configured on the resolver may still apply.

@PageableDefault has its own annotation default values. Therefore, when you want documentation and runtime to share a specific default, declare it explicitly and inspect the generated JSON. Do not rely solely on implicit framework defaults.

You can use @SortDefault when you want to describe a separate sorting default:

~~~java
@GetMapping("/api/products")
public Page<ProductResponse> listProducts(
    @ParameterObject
    @PageableDefault(size = 20)
    @SortDefault(
        sort = "name",
        direction = Sort.Direction.ASC
    )
    Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

When combining default annotations, check the actual Sort result in tests and OpenAPI metadata. If only a single simple default criterion is needed, declaring sort and direction directly in @PageableDefault is usually easier to read.

## 6. Configuring Pagination Parameter Names

Spring Data Web typically uses the names page, size, and sort. These can be renamed to match API conventions.

Example configuration:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: pageNumber
        size-parameter: pageSize
      sort:
        sort-parameter: orderBy
~~~

When this configuration is applied, the URL can look like:

~~~http
GET /api/orders?pageNumber=0&pageSize=20&orderBy=createdAt,desc
~~~

Common properties:

| Property | Purpose |
|---|---|
| spring.data.web.pageable.page-parameter | Name of query parameter holding page number |
| spring.data.web.pageable.size-parameter | Name of query parameter holding page size |
| spring.data.web.sort.sort-parameter | Name of query parameter holding sort criteria |
| spring.data.web.pageable.default-page-size | Default page size of the resolver |
| spring.data.web.pageable.max-page-size | Maximum page size accepted by the resolver |
| spring.data.web.pageable.one-indexed-parameters | Use 1-based page numbering in requests |
| spring.data.web.pageable.prefix | Prefix for Pageable parameters |
| spring.data.web.pageable.qualifier-delimiter | Delimiter between qualifier and parameter name |

Property names and configuration capabilities depend on the Spring Boot/Spring Data version. Cross-check the configuration metadata of the version in use. After renaming, verify both the Spring Data resolver and OpenAPI output; do not leave documentation showing page while runtime only accepts pageNumber.

## 7. Zero-Based vs. One-Based Page Numbering

Spring Data Pageable uses a 0-based page number in its internal model. For instance, PageRequest.of(0, 20) represents the first page.

Requests also typically use page=0 by default. If the API wants clients to send page=1 for the first page, you can enable:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

When enabled, the resolver converts the 1-based numbering in the query string into an internal 0-based index. For example:

~~~http
GET /api/orders?page=1&size=20
~~~

The client requests the first page; internally, Pageable still represents the page with index 0.

Publish this convention clearly in the parameter or operation description. Check the default in OpenAPI, as the schema may need customization to reflect page=1 as the first value on the public interface. Do not assume enabling the property automatically makes every generator and Swagger UI display the 1-based convention properly.

Unless there is a specific compatibility requirement, using zero-based numbering aligns with Spring Data defaults and reduces translation between the API and backend.

## 8. Limiting Page Size

Clients should not be allowed to request an arbitrary size. A request such as size=100000 can cause heavy queries, high memory usage, and oversized responses.

You can set a maximum limit:

~~~yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
~~~

With Spring Data Web's default resolver, a size exceeding the limit is typically capped at max-page-size rather than allowing an unbounded query. Specific behavior should be verified against your version and any custom resolver in the application.

In addition to global configuration, defaults can be set per endpoint with @PageableDefault. The max page size setting still needs to be enforced at the resolver or corresponding validation layer.

If the API wants to reject overly large sizes instead of silently capping them, implement explicit validation and document the error response. Do not simply write maximum in OpenAPI and expect Spring Data to automatically return 400 if runtime configuration does not do that.

## 9. How Sort Is Represented

Spring Data Web typically accepts sort as a property name and sort direction:

~~~http
GET /api/orders?sort=createdAt,desc
~~~

Multiple criteria can be sent by repeating the parameter:

~~~http
GET /api/orders?sort=status,asc&sort=createdAt,desc
~~~

In Pageable, these criteria are converted into Sort. For example:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("status"),
    Sort.Order.desc("createdAt")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Clients should not be allowed to sort arbitrarily by any entity property. Define a list of public sort keys, validate input, and map them to allowed query properties or expressions. This avoids errors from nonexistent property names and reduces the risk of clients driving unintended queries.

If the API uses sort names different from persistence field names, create a mapping, such as mapping the public key createdDate to createdAt. Document supported values in OpenAPI or the parameter description so clients know the valid choices.

Unstable sorting can cause records to appear repeatedly or be skipped between pages when data changes. Add a unique field as a tie-breaker, such as id, when the primary criterion can have duplicates.

## 10. Combining Pageable with @ParameterObject and Validated Filters

Filter DTOs can use Bean Validation to constrain inputs:

~~~java
public class OrderSearchCriteria {

    @Size(max = 100)
    private String keyword;

    private OrderStatus status;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdTo;

    // Getters and setters.
}
~~~

Controller:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @Valid
    @ParameterObject
    @ModelAttribute
    OrderSearchCriteria criteria,

    @ParameterObject
    @PageableDefault(
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.search(criteria, pageable);
}
~~~

Cross-field rules such as ensuring createdFrom is not after createdTo can be validated in the service or via a custom validator. @ParameterObject does not perform validation itself; it only guides springdoc in generating metadata. Spring MVC binding and Bean Validation still handle runtime data.

For query parameters, check data types and formats in OpenAPI. For instance, LocalDate is typically represented as a string with format date. Sending a malformed date can trigger a binding error before the service is called.

## 11. Distinguishing Page, Slice, and List

Spring Data provides several query return types:

| Type | Contents | Pagination metadata | Typical cost |
|---|---|---|---|
| Page<T> | Current page contents | Has totalElements and totalPages | Usually requires a total count query |
| Slice<T> | Slice of data contents | Has hasNext/hasPrevious, does not require total pages | Can avoid a count query |
| List<T> | List of results | No pagination metadata | Depends on query and data limit |

Page<T> is suitable when the UI needs the total record count or total page count. Slice<T> is suitable when the client only needs to know whether more data follows. List<T> is suitable for small datasets or endpoints that do not expose pagination metadata.

Choosing Page or Slice affects both performance and the response contract. Do not use Page just to get page/size parameters; if total item count is unnecessary, Slice may be a better fit.

## 12. Describing the Page<T> Response

A Page<T> contains the page contents and metadata, typically including:

- content: list of items on the page.
- number: current page index.
- size: page size.
- numberOfElements: actual number of items on the page.
- totalElements: total items matching the filter criteria.
- totalPages: total number of pages.
- first and last: whether it is the first or last page.
- empty: whether the page is empty.
- sort/pageable: pagination and sorting info, depending on serialization.

Illustrative JSON example:

~~~json
{
  "content": [
    {
      "id": "ORD-1001",
      "status": "PAID"
    }
  ],
  "number": 0,
  "size": 20,
  "numberOfElements": 1,
  "totalElements": 41,
  "totalPages": 3,
  "first": true,
  "last": false,
  "empty": false
}
~~~

The actual JSON shape depends on the return type, Spring Data serialization configuration, and how the application defines responses. springdoc may use model converters to describe Page, but do not assume the generated schema always matches the JSON of every version exactly.

Verify the actual response with a test request and compare it against components.schemas in /v3/api-docs. If a stable public contract is needed, consider a custom pagination DTO instead of directly exposing PageImpl's internal structure.

## 13. Using a Dedicated Pagination DTO for Public APIs

A dedicated DTO gives control over field names and avoids coupling to Spring Data's internal serialization structure:

~~~java
public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last
) {}
~~~

It can be converted from Page<T>:

~~~java
public final class PageResponses {

    private PageResponses() {
    }

    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast()
        );
    }
}
~~~

Controller returning the DTO:

~~~java
@GetMapping("/api/orders")
public PageResponse<OrderResponse> listOrders(
    @ParameterObject Pageable pageable
) {
    Page<OrderResponse> result = orderService.findAll(pageable);
    return PageResponse.from(result);
}
~~~

This is an illustrative example; in real code, place the factory method in a mapper or appropriate class and handle generic schemas as needed. If using record, a Java version supporting records is required.

A pagination DTO lets the team change internal querying without necessarily changing the public contract. However, if Page<T> has already been published directly, switching to a new DTO can be a breaking contract change and its client impact should be evaluated.

## 14. Multiple Pageables in the Same Operation

Some endpoints may need pagination for multiple independent datasets, though controller signatures become harder to read without distinguishing parameters. Spring Data supports qualifiers to namespace each Pageable.

Example:

~~~java
@GetMapping("/api/dashboard")
public DashboardResponse dashboard(
    @Qualifier("orders")
    @ParameterObject
    Pageable ordersPage,

    @Qualifier("payments")
    @ParameterObject
    Pageable paymentsPage
) {
    return dashboardService.load(ordersPage, paymentsPage);
}
~~~

With qualifiers and the default delimiter, parameters may look like:

~~~http
GET /api/dashboard?orders_page=0&orders_size=10&orders_sort=createdAt,desc&payments_page=0&payments_size=5
~~~

Prefix names and delimiters depend on Spring Data Web configuration. Verify both how the resolver binds them and the parameter names springdoc publishes. Multiple Pageables in one operation complicate the API; use them only when clients truly need independent pagination across multiple datasets.

## 15. Cursor Pagination Is Not Pageable

Pageable models pagination by page number and page size (offset/page-number pagination). For very large or frequently changing datasets, cursor pagination may be more suitable.

Example cursor API:

~~~http
GET /api/orders?limit=20&after=eyJpZCI6Ik9SRC0xMDAxIn0
~~~

In this case, after is a server-issued cursor, not a page number. Clients send the cursor from the previous response to fetch the next slice.

Do not use @ParameterObject Pageable and rename page to after if the backend actually uses cursors. Define a dedicated query DTO instead:

~~~java
public class OrderCursorQuery {
    @Min(1)
    @Max(100)
    private Integer limit = 20;

    private String after;

    // Getters and setters.
}
~~~

Cursor pagination helps avoid large offset overhead and reduces position-shifting issues when new data is inserted, but requires designing stable, opaque, and validated cursors. OpenAPI documentation should describe limit, after, nextCursor, and end-of-dataset rules.

## 16. Checking Query Parameters in OpenAPI JSON

After the application is running, download the spec:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the operation's parameters:

~~~bash
jq '.paths["/api/orders"].get.parameters' openapi.json
~~~

List names, locations, and schemas:

~~~bash
jq -r '
  .paths["/api/orders"].get.parameters[]
  | [
      .name,
      .in,
      (.required // false | tostring),
      (.schema.type // ""),
      (.schema.default // "")
    ]
  | @tsv
' openapi.json
~~~

Check the following points:

- Are all filter parameters as well as page, size, and sort present?
- Do parameter names match Spring Data Web configuration?
- Do default page and size match @PageableDefault?
- Can sort represent multiple criteria?
- Does the description explain zero-based vs. one-based numbering?
- Is the size limit published if needed?
- Is the query DTO mistakenly rendered as an unwanted request body?

If OpenAPI shows only a single generic object parameter, check @ParameterObject and the springdoc version. If the documentation shows wrong default page/size values, check annotations, global config, and the resolver.

## 17. Verifying Binding and Pagination Results at Runtime

OpenAPI JSON verifies metadata. Send actual requests to verify Spring Data Web binds properly and the service returns correct data.

Example:

~~~bash
curl -i "http://localhost:8080/api/orders?status=PAID&page=0&size=20&sort=createdAt,desc"
~~~

In a MockMvc test, you can verify the Pageable passed down to the service:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void bindsPageSizeAndSort() throws Exception {
        given(orderService.findAll(any(Pageable.class)))
            .willReturn(Page.empty());

        mockMvc.perform(get("/api/orders")
                .param("page", "1")
                .param("size", "10")
                .param("sort", "createdAt,desc"))
            .andExpect(status().isOk());

        ArgumentCaptor<Pageable> captor =
            ArgumentCaptor.forClass(Pageable.class);

        then(orderService).should().findAll(captor.capture());

        Pageable actual = captor.getValue();
        assertThat(actual.getPageNumber()).isEqualTo(1);
        assertThat(actual.getPageSize()).isEqualTo(10);
        assertThat(actual.getSort().getOrderFor("createdAt").getDirection())
            .isEqualTo(Sort.Direction.DESC);
    }
}
~~~

This test illustrates how to verify binding. Add imports, mock setup, and null-safe assertions as needed for your project. If one-indexed-parameters is enabled, a request with page=1 translates into internal page number 0; adjust expectations accordingly.

Tests should cover:

- Omitting page/size to verify defaults.
- Passing page and size explicitly.
- Sending multiple sort parameters.
- Sending size above the limit.
- Sending negative page or invalid size.
- Combining filters and Pageable.
- Checking response metadata and item ordering.

## 18. Common Issues

| Symptom | Cause to check |
|---|---|
| Swagger UI does not display page/size/sort | Missing @ParameterObject or springdoc does not decompose Pageable under current config |
| Documentation shows page but request fails to bind | Parameter name changed in Spring Data Web but spec does not reflect it |
| First page skipped or off by one page | Confusing zero-based with one-based numbering |
| Clients request a very large size | Missing max-page-size or limit not enforced by resolver |
| Sort in Swagger UI does not match backend format | Schema or sort description does not reflect repeatable parameter syntax |
| Records shift positions across pages | Unstable sort or data mutating while client paginates |
| Page response contains many internal fields | Serializing PageImpl directly or schema converter generating a structure unsuited for public contract |
| API is slow when fetching Page | Count query is expensive; consider Slice or cursor pagination |
| Sorting by nonexistent field causes errors | Public sort keys are not allowlisted |
| Filter object and Pageable have duplicate parameters | Filter property name conflicts with page, size, or sort |
| @PageableDefault not reflected in Swagger UI | Check annotations, converters, and JSON output of the version in use |

## 19. Pagination API Design Conventions

An easy-to-integrate list API should standardize:

- Parameter names page, size, and sort.
- Whether page numbering starts at 0 or 1.
- Default and maximum page size.
- Syntax for passing multiple sort criteria.
- List of supported sort keys.
- Handling of invalid page/size values.
- Metadata structure in responses.
- Filter conditions applied before pagination.
- Stable sorting when multiple records share the same values.
- When to use Page, Slice, or cursor.

Do not let each endpoint choose a different convention without a business reason. Consistency lets clients share pagination components and reduces integration errors.

## 20. Checklist for Combining @ParameterObject and Pageable

- [ ] Controller accepts Pageable instead of declaring page, size, and sort separately.
- [ ] @ParameterObject is attached to Pageable so springdoc documents query parameters.
- [ ] Filter DTO is separated from Pageable and annotated with @ParameterObject as appropriate.
- [ ] @PageableDefault reflects the intended default page, size, and sort.
- [ ] Parameter names in OpenAPI match Spring Data Web configuration.
- [ ] Zero-based/one-based convention is explicitly documented.
- [ ] Appropriate default-page-size and max-page-size are configured.
- [ ] Sort keys are restricted to an allowlist.
- [ ] Multiple sort criteria have clear syntax.
- [ ] Page/Slice responses have accurate schemas and metadata.
- [ ] A dedicated pagination DTO has been considered for the public API.
- [ ] /v3/api-docs has been inspected.
- [ ] Binding, limits, and query results have been verified with runtime tests.
- [ ] Cursor pagination has been considered when offset is no longer suitable.

## 21. References

- [springdoc-openapi – official documentation](https://springdoc.org/)
- [Spring Data – Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data – Pageable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html)
- [Spring Data – PageableDefault API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)

@ParameterObject helps springdoc publish Pageable as query parameters, while Spring Data Web handles binding page, size, and sort when requests arrive. Combining Pageable with a query DTO gives the API both business filters and consistent pagination. After any change to annotations or Spring Data configuration, verify both the OpenAPI JSON and runtime requests to ensure clients send the right parameters and receive the expected data pages.
