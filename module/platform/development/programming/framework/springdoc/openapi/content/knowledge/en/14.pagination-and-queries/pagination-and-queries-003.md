# Names of `page`, `size`, `sort` and Application Defaults

A paginated API needs a stable convention so clients can request the right slice of data. With Spring Data, `Pageable` groups three common pieces of information: page number, page size, and sort order. Spring MVC automatically binds query parameters into `Pageable`; springdoc-openapi can describe them as individual parameters in OpenAPI so Swagger UI displays the proper way to call the endpoint.

Query parameter names and default values can come from application-wide configuration or annotations on individual controller methods. It is important to distinguish between Spring Data's resolver configuration, the built-in defaults of `@PageableDefault`, and the schema published by springdoc. If these three parts are inconsistent, a client may follow Swagger UI while the server applies a different pagination behavior.

## 1. `Pageable` Groups page, size, and sort

Spring Data provides `Pageable` to represent a pagination request. Instead of declaring three separate parameters, a controller receives one object:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    Page<OrderResponse> list(Pageable pageable) {
        return orderService.findAll(pageable);
    }
}
```

Spring Data Web automatically converts query parameters into `Pageable`. With default names, clients can call:

```http
GET /api/orders?page=0&size=20&sort=createdAt,desc
```

Meaning:

- `page`: page index. Starts at `0` by default, so the first page is `page=0`.
- `size`: maximum number of items in a page.
- `sort`: property used for sorting and sort direction, usually `asc` or `desc`.

`Pageable` is a request object passed into the repository/service; it does not query data by itself. The service can pass it to a Spring Data repository to receive `Page<T>`, or use its information to call another data source.

## 2. Default Parameter Names and Application-Wide Configuration

In standard Spring Data Web configuration within Spring Boot, default parameter names are `page`, `size`, and `sort`. Names and limits can be changed at the application level in `application.yml`:

```yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
        prefix: ""
        qualifier-delimiter: _
      sort:
        sort-parameter: sort
```

Key properties:

| Property | Meaning | Common default value |
| --- | --- | --- |
| `spring.data.web.pageable.page-parameter` | Query parameter name for page index | `page` |
| `spring.data.web.pageable.size-parameter` | Query parameter name for page size | `size` |
| `spring.data.web.pageable.default-page-size` | Page size when client omits `size` | `20` |
| `spring.data.web.pageable.max-page-size` | Maximum page size accepted by the resolver | `2000` |
| `spring.data.web.pageable.one-indexed-parameters` | Whether URL page index starts at `1` | `false` |
| `spring.data.web.pageable.prefix` | Prefix added to pagination parameter names | Empty string |
| `spring.data.web.pageable.qualifier-delimiter` | Separator between qualifier and parameter name | `_` |
| `spring.data.web.sort.sort-parameter` | Query parameter name for sorting | `sort` |

The default values in the table are common defaults for Spring Boot/Spring Data Web; check the running configuration and version if the application uses a custom `PageableHandlerMethodArgumentResolver` or `SortHandlerMethodArgumentResolver`. `max-page-size` is a resource protection limit: even if a client requests `size=100000`, the resolver caps it at the configured maximum.

If parameter names are changed, for example to `p`, `limit`, and `orderBy`, clients must call using the new names. Ensure the OpenAPI specification also publishes those exact names. After changing properties, inspect `/v3/api-docs` and real HTTP requests; if the springdoc version does not reflect custom names as desired, customize the parameters in OpenAPI using annotations or an `OpenApiCustomizer`.

## 3. Changing Parameter Names

For example, suppose an application wants short names `p` for page, `limit` for item count, and `orderBy` for sorting:

```yaml
spring:
  data:
    web:
      pageable:
        page-parameter: p
        size-parameter: limit
        default-page-size: 25
        max-page-size: 100
      sort:
        sort-parameter: orderBy
```

Client request:

```http
GET /api/orders?p=0&limit=25&orderBy=createdAt,desc
```

Parameter names are part of the API contract. When changing from `page` to `p`, existing clients still sending `page` may no longer paginate as expected. If a non-breaking transition is required, maintain aliases temporarily via a custom resolver or design a new endpoint version; do not rename public parameters without notifying clients.

## 4. Page Index Starting from 0 or 1

Spring Data `Pageable` uses an internal index starting from `0`. The `one-indexed-parameters` setting changes how clients number pages in the URL:

```yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
```

When enabled, clients send `page=1` to request the first page and `page=2` for the second page. The resolver converts the external index to the appropriate internal index before creating `Pageable`.

This does not mean `Page.getNumber()` switches to one-based. `Page` metadata remains based on the internal zero-based index. If the response body returns `number`, clearly document this convention so clients do not add or subtract one incorrectly.

Do not enable `one-indexed-parameters` just to make Swagger UI look friendlier if existing clients already use zero-based numbering. This changes how the API is called and must be reflected consistently in documentation, tests, and example requests.

## 5. Application-Wide Defaults and `@PageableDefault`

`default-page-size` in Spring Data Web configuration serves as the application-wide default when a controller does not declare its own default. A method can override it with `@PageableDefault`:

```java
@GetMapping("/recent")
Page<OrderResponse> recent(
    @ParameterObject
    @PageableDefault(
        page = 0,
        size = 25,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.findRecent(pageable);
}
```

Common attributes of `@PageableDefault`:

| Attribute | Meaning |
| --- | --- |
| `page` | Default page index. |
| `size` | Default page size. |
| `sort` | One or more default sort properties. |
| `direction` | Default sort direction for properties in the annotation. |

Note: `@PageableDefault` has its own default attribute values, typically `page=0` and `size=10`. When the annotation is present on a parameter, its values can override the application-wide `default-page-size`. Therefore, if you want to use the application's configured default, do not add `@PageableDefault` merely as a marker on the parameter.

Query parameters sent by the client can still override method defaults. For example, if a method defaults to `size=25` but the request passes `size=10`, the resolver uses size 10, provided the value is within allowed limits.

## 6. Setting Default Sorting with `@SortDefault`

When you want to separate sorting rules from page/size, you can use `@SortDefault`:

```java
@GetMapping
Page<OrderResponse> list(
    @ParameterObject
    @PageableDefault(size = 25)
    @SortDefault(
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.findAll(pageable);
}
```

If default sorting by multiple properties is needed, declare the `@SortDefault.SortDefaults` container:

```java
@GetMapping
Page<OrderResponse> list(
    @ParameterObject
    @PageableDefault(size = 25)
    @SortDefault.SortDefaults({
        @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
        @SortDefault(sort = "id", direction = Sort.Direction.ASC)
    })
    Pageable pageable
) {
    return orderService.findAll(pageable);
}
```

The default result is equivalent to sorting by `createdAt DESC`, then `id ASC`. The secondary order keeps results stable when multiple records share the same creation timestamp. This is a good practice to prevent random order changes across paginated calls.

`@PageableDefault(sort = ...)` can also declare sorting directly. Choose one readable and consistent approach; avoid declaring overlapping default sources without verifying precedence in the Spring Data version in use.

## 7. `sort` Query Parameter Syntax

Spring Data typically accepts each sort criterion in the form:

```text
sort=property,direction
```

Example:

```http
GET /api/orders?sort=createdAt,desc
```

To sort by multiple criteria, repeat the parameter:

```http
GET /api/orders?sort=createdAt,desc&sort=id,asc
```

The result is `createdAt DESC`, then `id ASC`. You can sort by nested properties if that property path is valid in the data model, such as `customer.name,asc`. Property names and syntax must match what the entity or repository supports.

Do not confuse `sort` with SQL column names. Clients send model property names recognized by Spring Data; the repository is responsible for mapping them to the query. If the API wants friendly names like `created` while the entity has field `createdAt`, map the public value to the internal property in the service or resolver.

## 8. Restricting and Controlling Sort Properties

Clients should not be allowed to sort arbitrarily by every entity field. Some fields may be unsuitable for querying, expose internal structure, or trigger expensive queries. Publish the list of supported sort keys and validate before building `Pageable` or `Sort`.

Example of mapping public sort names:

```java
private static final Map<String, String> ALLOWED_SORTS = Map.of(
    "created", "createdAt",
    "status", "status",
    "customer", "customer.name"
);

Sort toAllowedSort(List<String> requestedSorts) {
    List<Sort.Order> orders = requestedSorts.stream()
        .map(value -> {
            String[] parts = value.split(",", 2);
            String property = ALLOWED_SORTS.get(parts[0]);
            if (property == null) {
                throw new IllegalArgumentException("Unsupported sort field: " + parts[0]);
            }
            Sort.Direction direction = parts.length == 2
                ? Sort.Direction.fromString(parts[1])
                : Sort.Direction.ASC;
            return new Sort.Order(direction, property);
        })
        .toList();

    return Sort.by(orders);
}
```

This illustrates allowlist mapping; in an actual controller, a dedicated request model or custom argument resolver can accept the sort list. When using `Pageable` directly, inspect each `Sort.Order` before passing it down to the repository. Do not rely on nonexistent field names automatically failing in every query type.

Limiting `max-page-size` is equally important. Overly large page sizes increase database load, memory usage, and serialization time. Choose a limit based on response payload weight, database indexes, and system capacity; do not allow unbounded client requests.

## 9. Using Multiple `Pageable` Parameters in One Operation

Some composite endpoints may need independent pagination for multiple datasets. Spring Data supports qualifiers to distinguish parameter names:

```java
@GetMapping("/dashboard")
DashboardResponse dashboard(
    @Qualifier("orders") @ParameterObject Pageable orders,
    @Qualifier("customers") @ParameterObject Pageable customers
) {
    return dashboardService.load(orders, customers);
}
```

With the default `_` delimiter, query parameters can look like:

```http
GET /api/dashboard?orders_page=0&orders_size=10&orders_sort=createdAt,desc&customers_page=0&customers_size=5
```

`@Qualifier("orders")` and `@Qualifier("customers")` create separate namespaces for each group. `qualifier-delimiter` lets you change the separator character. This structure prevents two `Pageable` parameters from reading the same `page`, `size`, and `sort` set.

If springdoc does not automatically render qualified parameter names accurately in your version, inspect `/v3/api-docs` and declare/customize OpenAPI parameters explicitly. Do not leave documentation showing only one set of `page`, `size`, and `sort` while runtime requires two prefixed sets.

## 10. Describing `Pageable` with springdoc-openapi

To have springdoc decompose `Pageable` into individual query parameters, place `@ParameterObject` on the parameter:

```java
@GetMapping
@Operation(summary = "Search orders with pagination")
Page<OrderResponse> search(
    @ParameterObject
    @PageableDefault(size = 25, sort = "createdAt", direction = Sort.Direction.DESC)
    Pageable pageable
) {
    return orderService.search(pageable);
}
```

Springdoc recognizes `Pageable` and documents the pagination fields as operation parameters. Swagger UI can display `page`, `size`, and `sort` inputs instead of a Java object without clear query formatting.

Check `/v3/api-docs` to confirm:

- `page`, `size`, and `sort` appear in the operation's `parameters` with `in: query`.
- The schemas for `page` and `size` are integers.
- Descriptions state the starting index, maximum size, and sort syntax.
- Default values reflect `@PageableDefault` or runtime configuration.
- If parameters were renamed, the spec uses the exact names accepted by the resolver.

`@ParameterObject` is a springdoc annotation for decomposing an object into parameters; it does not alter how Spring Data binds queries. Conversely, `@PageableDefault` controls resolver behavior; it does not automatically ensure custom OpenAPI descriptions are updated.

## 11. Verifying Defaults and Parameter Names in the Application

Whenever pagination configuration changes, verify all three layers:

1. **Configuration:** inspect `spring.data.web.pageable.*` and `spring.data.web.sort.sort-parameter` in config files for the active profile.
2. **Runtime binding:** call the endpoint with no query parameters to verify default page, size, and sort; call again with custom parameter names to verify the resolver binds them properly.
3. **OpenAPI:** open `/v3/api-docs`, locate the operation, and compare parameter names, types, defaults, and descriptions against runtime.
4. **Limits:** test a `size` larger than `max-page-size` and confirm the resolver enforces the cap.
5. **Sort:** test multiple criteria, asc/desc directions, and unsupported fields; confirm the allowlist or validation rejects appropriately.
6. **One-based:** if `one-indexed-parameters` is enabled, verify `page=1` returns the first page and clearly explain that `Page.number` metadata remains zero-based.

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Swagger UI sends `page` but server expects `p` | OpenAPI parameter name out of sync with resolver | Check properties and customize springdoc schema/parameter. |
| Omitting `size` produces unexpected page size | `@PageableDefault` overrides application-wide default | Check method annotation and `default-page-size`. |
| `size=10000` does not return 10,000 records | Resolver caps at `max-page-size` | Check limit and document it clearly. |
| First page is `page=1` but metadata returns `number=0` | One-indexed request parameters are enabled | Clearly document URL convention vs. internal index. |
| Multiple `sort` values lose order | Client sends single value or custom conversion drops order | Use repeated parameters and preserve `Sort.Order` sequence. |
| Sorting by unknown field causes query error | Client sends unsupported property | Use allowlist and map public sort keys. |
| Two `Pageable` params share page/size | Missing `@Qualifier` or mismatched delimiter | Add qualifiers to each parameter and check query names. |

## 12. Guiding Principles

- Use `Pageable` instead of declaring separate page, size, and sort parameters when the service uses Spring Data.
- Keep parameter names stable and publish them accurately in OpenAPI.
- Use `spring.data.web.pageable.*` configuration for application-wide defaults and limits.
- Use `@PageableDefault` or `@SortDefault` when an operation requires specific defaults.
- Decide clearly whether URLs are zero-based or one-based and keep response metadata consistent.
- Use repeated sort syntax for multiple criteria; validate fields against an allowlist.
- Use `@ParameterObject` so springdoc documents `Pageable` as query parameters.
- Verify runtime binding, resolver limits, and `/v3/api-docs` after every change.

The names `page`, `size`, `sort`, and their defaults are part of the contract clients rely on daily. Spring Data provides binding and limits; `@PageableDefault` tunes individual operations; springdoc documents parameters for API consumers. When these three layers stay aligned, clients can paginate and sort predictably while the server keeps query load under control.

## References

- [Spring Data – Web Support and Pageable Handler](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Boot – Application Properties: Spring Data Web](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Springdoc OpenAPI – official documentation](https://springdoc.org/)
- [Spring Data Commons – `PageableDefault`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html)
- [Spring Data Commons – `SortDefault`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/SortDefault.html)
