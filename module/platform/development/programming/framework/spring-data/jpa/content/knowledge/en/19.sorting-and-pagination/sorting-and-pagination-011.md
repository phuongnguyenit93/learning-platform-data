# Integrating Pageable and Sort with Spring MVC and Configuration Rules

## 1. Why Integrate Pageable and Sort at the Web Layer?

Spring Data JPA provides `Pageable` and `Sort` to describe how to retrieve data in pages and sorted order. At the repository layer, an application can pass a `Pageable` into a method so the database returns only the needed portion of data.

In a Spring MVC application, clients typically send parameters in the URL, for example:

```http
GET /api/customers?page=0&size=20&sort=name,asc
```

Spring Data Web supports converting HTTP parameters into `Pageable` and `Sort` objects. The controller receives the parsed object and passes it down to the service/repository. As a result, the controller does not need to read each query parameter manually and construct `PageRequest` by hand.

Overall flow:

1. Client sends page, size, and sort in an HTTP request.
2. Spring MVC invokes Spring Data Web's argument resolver.
3. The resolver constructs `Pageable` and `Sort` from request parameters, applying defaults and configured limits.
4. The controller receives `Pageable` as a method argument.
5. The service forwards the pagination request to the repository.
6. Spring Data JPA / the JPA provider translates the request into a query with row limits and ordering suitable for the database.
7. The controller returns the content and pagination metadata to the client.

Keep two responsibilities separate:
- Spring Data Web parses requests and builds `Pageable`/`Sort`.
- Spring Data JPA uses those objects to query the database.

## 2. How Spring MVC Receives Pageable

### 2.1. Declaring Pageable in a Controller

Example controller:

```java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public Page<CustomerSummary> search(Pageable pageable) {
        return repository.findAllProjectedBy(pageable);
    }
}
```

When Spring Data Web is configured, the `Pageable` parameter is automatically resolved from query parameters. The controller does not need separate `@RequestParam` declarations for page, size, or sort.

Example request:

```http
GET /api/customers?page=1&size=10&sort=name,asc
```

By Spring Data Web's standard defaults:
- `page` is the page number, starting from 0.
- `size` is the maximum number of elements per page.
- `sort` describes the sort field and direction.
- Multiple `sort` parameters can be passed to create multi-level sorting.

Configuration can change parameter names, prefixes, delimiters, default page size, and page numbering. Therefore, verify your application configuration instead of assuming every project uses defaults.

### 2.2. Repository Accepting Pageable

A repository can declare:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
    );
}
```

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> findActiveCustomers(Pageable pageable) {
        return repository.findByStatus(
            CustomerStatus.ACTIVE,
            pageable
        );
    }
}
```

Controller:

```java
@GetMapping("/active")
public Page<Customer> activeCustomers(Pageable pageable) {
    return customerService.findActiveCustomers(pageable);
}
```

`Pageable` is passed straight through the layers. There is no need to unpack it into page number and size and reconstruct the object at every layer unless business rules require it.

If the API returns DTOs, the repository can use projections or the service can map results to DTOs. Avoid returning entities directly if serialization might trigger lazy loading or expose internal fields.

## 3. Default Query Parameters

### 3.1. page and size

Example:

```http
GET /api/orders?page=0&size=25
```

Corresponds to requesting the first page, up to 25 elements.

```http
GET /api/orders?page=2&size=25
```

Requests the third page in user-facing counting if the UI numbers from 1; in Spring Data, the page index is still 2. Offset is calculated as page index times page size.

Do not let clients send arbitrary sizes without a cap. A request with a huge size can increase memory usage, query latency, and response payload size. Set appropriate default and maximum page sizes.

### 3.2. sort

Common syntax:

```http
GET /api/customers?sort=name,asc
GET /api/customers?sort=createdAt,desc
```

The first part is the property to sort by; the second part is the direction `asc` or `desc`.

Property names in `Sort` are normally the entity's Java properties, e.g. `createdAt`, not necessarily the database column name `created_at`. With native queries or complex projections, sort support also depends on the query and Spring Data JPA version.

### 3.3. Multi-Field Sorting

The `sort` parameter can be repeated:

```http
GET /api/customers?sort=lastName,asc&sort=firstName,asc&sort=id,asc
```

Priority order is:
1. lastName ascending.
2. If lastName ties, sort by firstName ascending.
3. If still tied, sort by id ascending.

An ordering with a unique key as a tie-breaker keeps results across pages more stable.

Do not combine multiple fields into an arbitrary single string if the application's resolver expects one parameter per order. Publish the request syntax clearly in API documentation.

## 4. Setting Defaults with @PageableDefault

### 4.1. Setting Endpoint Default Size and Sort

When the client omits page/size/sort, the controller can declare defaults:

```java
@GetMapping
public Page<CustomerSummary> list(
    @PageableDefault(
        page = 0,
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return customerService.findCustomers(pageable);
}
```

The `@PageableDefault` annotation defines endpoint-scoped defaults:
- `page`: default page.
- `size`: default page size.
- `sort`: one or more default properties.
- `direction`: default direction for the sorts declared in the annotation.

If the client sends the corresponding parameter, the request can override the default according to the resolver's rules. Test the behavior of your Spring Data version.

### 4.2. Multi-Field Default Sort with @SortDefault

When multiple sort orders need individual directions, use `@SortDefault`:

```java
@GetMapping
public Page<CustomerSummary> list(
    @PageableDefault(size = 20)
    @SortDefault.SortDefaults({
        @SortDefault(
            sort = "lastName",
            direction = Sort.Direction.ASC
        ),
        @SortDefault(
            sort = "firstName",
            direction = Sort.Direction.ASC
        ),
        @SortDefault(
            sort = "id",
            direction = Sort.Direction.ASC
        )
    })
    Pageable pageable
) {
    return customerService.findCustomers(pageable);
}
```

This expresses multi-level default sorting more clearly than trying to cram multiple properties into one annotation value.

If the request provides a Sort, the resolver applies the request's sort; default sort acts as a fallback when no sort is supplied. Test what happens when a client sends only a single sort order to confirm expected behavior and ensure tie-breakers are retained if required by the application.

## 5. Using Standalone Sort in a Controller

Not every endpoint needs pagination. You can accept `Sort` directly:

```java
@GetMapping("/export")
public List<CustomerSummary> export(
    @SortDefault(
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Sort sort
) {
    return customerService.exportCustomers(sort);
}
```

Repository:

```java
List<Customer> findByStatus(
    CustomerStatus status,
    Sort sort
);
```

Standalone Sort fits when the result set is bounded in another way or the use case does not use Page. However, never return an unbounded list simply because Pageable was omitted; large exports require streaming, chunking, or a dedicated export workflow.

## 6. Configuring Spring Data Web

### 6.1. Spring Boot Auto-Configuration

In a Spring Boot application with Spring Data Web on the classpath, Spring Boot automatically configures argument resolver support for `Pageable` and `Sort`. Properties are typically placed under the `spring.data.web.pageable` and `spring.data.web.sort` prefixes.

Example configuration:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        page-parameter: page
        size-parameter: size
        one-indexed-parameters: false
      sort:
        sort-parameter: sort
```

Meaning:
- `default-page-size`: page size used when the request omits size and no method-specific default exists.
- `max-page-size`: maximum size accepted by the resolver.
- `page-parameter`: query parameter name for page number.
- `size-parameter`: query parameter name for page size.
- `one-indexed-parameters`: when enabled, incoming page requests are interpreted as 1-based at the Web layer and converted to an internal zero-based index.
- `sort-parameter`: query parameter name for sorting.

Property names and configuration options can vary across Spring Boot versions. Check the configuration metadata/reference for your exact project version. If a property is unrecognized, the application may start without applying the value you expected.

### 6.2. Java Configuration with a Customizer

When customizing the resolver in Java, Spring Data Web provides a customizer interface. Example with Spring Data Commons:

```java
@Configuration
public class SpringDataWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setMaxPageSize(100);
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

In current Spring Data versions, the customizer package is `org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer`. Confirm imports against actual project dependencies.

Customizers are useful when setting limits or rules that cannot be expressed in application properties. Avoid configuring the same setting in YAML and overriding it in a customizer without a clear convention; doing so makes finding the source of configuration harder.

### 6.3. @EnableSpringDataWebSupport in Non-Boot Applications

If a Spring MVC application does not use Spring Boot auto-configuration, register Spring Data Web support using:

```java
@Configuration
@EnableSpringDataWebSupport
public class WebConfiguration {
}
```

This annotation registers Spring Data's web support components, including resolvers for Pageable and Sort. If the application already uses Boot auto-configuration, do not add manual configuration mechanically; avoid registering duplicate resolvers or conflicting settings.

## 7. Protecting the API from Excessive Page Sizes

### 7.1. Setting a Maximum Limit

A client could send:

```http
GET /api/customers?size=1000000
```

Without a cap, a request can demand too much data, increasing:
- Rows the database must read and transfer over JDBC.
- Heap memory used to instantiate entities/DTOs.
- Mapping and serialization time.
- Response payload size.
- Connection and transaction hold time.

Configure `max-page-size` in web configuration and pick a value appropriate for the use case. Set default page size lower than max page size so the API performs reasonably even when clients omit parameters.

### 7.2. Validating page and size

The resolver may normalize or clamp certain input values depending on the version. Even so, the API should have a clear contract for negative page, size 0, negative size, or out-of-bounds values.

If you need to return a validation error instead of silently clamping, write a dedicated adapter/validation layer for the API. Do not assume every resolver responds with the same HTTP status code for invalid input.

### 7.3. Prevent Clients from Driving Unbounded Queries

Even with page size capped, a client can still request a very large page index. Large offsets can be expensive. For large datasets, consider keyset pagination or scrolling endpoints rather than allowing infinite offsets.

## 8. Sort from Requests Must Be Controlled

### 8.1. Permit Only Published Properties

A request might contain:

```http
GET /api/customers?sort=passwordHash,desc
```

Or request sorting across an inappropriate deep association. Sort is not a SQL parameter value; Spring Data uses the property path to build an order expression. Invalid properties can cause query errors, and allowing arbitrary sorting can leak domain structure or create heavy queries.

Define an allowlist per endpoint, e.g.:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "id",
    "name",
    "createdAt"
);
```

Then validate the sort received from the request before passing it down to the repository. If invalid, return HTTP 400 with a clear message or fall back to the default sort per API contract.

### 8.2. Map Public Sort Names to Internal Properties

The API can publish `created` while the entity uses `createdAt`. Map through an allowlist:

```java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "name", "name",
    "created", "createdAt",
    "id", "id"
);
```

The service/controller adapter builds `Sort.Order` exclusively from validated values. Never concatenate raw query parameters into SQL or JPQL strings.

When using native SQL queries, dynamic sort support has limitations depending on Spring Data version and query enhancer/parser. For complex native queries, a custom repository should select a column expression from an allowlist and append a validated sort direction; never allow clients to send arbitrary SQL column names.

### 8.3. Not Every Property Is Sortable

Some properties:
- Are collections or associations that can introduce expensive joins.
- Are not selected in a projection.
- Are computed/transient properties not present in the query.
- Are incompatible with the native SQL in use.
- Have types or collations whose ordering does not fit business rules.

Publish only sort fields that are meaningful and tested against real queries.

## 9. Multiple Pageables in the Same Controller

An endpoint sometimes needs two independent lists, such as a page of customers and a page of orders:

```java
@GetMapping("/dashboard")
public DashboardResponse dashboard(
    @Qualifier("customers")
    Pageable customerPageable,
    @Qualifier("orders")
    Pageable orderPageable
) {
    Page<CustomerSummary> customers =
        customerService.findCustomers(customerPageable);

    Page<OrderSummary> orders =
        orderService.findOrders(orderPageable);

    return new DashboardResponse(customers, orders);
}
```

Use `@Qualifier` to distinguish parameters. With the default underscore delimiter, a request looks like:

```http
GET /api/dashboard?customers_page=0&customers_size=10&customers_sort=name,asc&orders_page=0&orders_size=5&orders_sort=createdAt,desc
```

Prefix names and delimiters can be customized via Spring Data Web configuration. Document conventions clearly in API docs so clients know which parameters belong to which list.

If an endpoint requires multiple independent paginations, consider splitting them into separate endpoints when responses and data load grow large. A single dashboard request can trigger multiple content and count queries at once.

## 10. Returning Paginated Responses to Clients

### 10.1. Page Object

You can return Page directly from the controller:

```java
@GetMapping
public Page<CustomerSummary> list(Pageable pageable) {
    return customerService.findCustomers(pageable);
}
```

Spring serializes Page properties in a structure that depends on the implementation. However, avoid letting clients depend directly on every internal field of the Page implementation if the API needs long-term stability.

### 10.2. Creating a Dedicated Response Envelope

A response DTO defines a clear API contract:

```java
public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean hasNext
) {
    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.hasNext()
        );
    }
}
```

Controller:

```java
@GetMapping
public PageResponse<CustomerSummary> list(Pageable pageable) {
    Page<CustomerSummary> page =
        customerService.findCustomers(pageable);

    return PageResponse.from(page);
}
```

A response envelope decouples the API contract from Spring Data serialization details. You can add next/previous links or current sort details if clients need them.

### 10.3. Distinguishing Internal Page Index from Display Page Number

If the resolver uses `one-indexed-parameters=true`, an incoming `page=1` request is converted to internal page index 0. When the response returns `Page.getNumber()`, that value is still the internal zero-based index.

If the API wants to return 1-based page numbers, convert explicitly inside the response DTO. Do not silently mismatch request and response conventions, as clients will easily request the wrong page.

## 11. Stable Sorting and Changing Data

Offset-based pagination requires deterministic ordering. Example:

```http
GET /api/orders?page=0&size=20&sort=createdAt,desc
```

If multiple orders share the same `createdAt`, the database does not guarantee order among rows with identical values. When switching pages, results can duplicate or skip if order is unstable or data changes.

Add a unique tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Pageable pageable = PageRequest.of(0, 20, sort);
```

When using default sort, include the tie-breaker in `@SortDefault` or build the default sort in the resolver/service per endpoint contract.

With continuously changing data, even stable ordering does not guarantee a consistent snapshot across multiple HTTP requests. If the use case requires traversing an entire dataset without duplicates, consider snapshots/versioning or keyset pagination on the sort keys.

## 12. Pageable with Page, Slice, and List

A repository can return different types:

```java
Page<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);

Slice<Customer> findSliceByStatus(
    CustomerStatus status,
    Pageable pageable
);

List<Customer> findTop100ByStatusOrderByCreatedAtDesc(
    CustomerStatus status,
    Pageable pageable
);
```

Meaning:
- `Page<T>` provides total element count and total page count; usually requires a count query.
- `Slice<T>` only needs to know whether a next element exists; can avoid the count query.
- `List<T>` combined with Pageable can limit content but provides no total metadata like Page.

Derived method names and return types must match what your project's Spring Data JPA version supports. Do not use Page when the UI does not need total pages, as count queries can be expensive.

## 13. Integration Testing Pageable and Sort

### 13.1. Testing the Repository

Repository tests verify that the database actually applies paging and sorting:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void appliesPageAndSort() {
        repository.saveAll(List.of(
            new Customer("Minh"),
            new Customer("An"),
            new Customer("Binh")
        ));

        Pageable pageable = PageRequest.of(
            0,
            2,
            Sort.by("name").ascending()
        );

        Page<Customer> page =
            repository.findAll(pageable);

        assertThat(page.getContent())
            .extracting(Customer::getName)
            .containsExactly("An", "Binh");

        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.hasNext()).isTrue();
    }
}
```

The example assumes matching Customer constructors and mappings. In real tests, if the repository contains other fixture data, clean up or filter by status/tenant so results do not depend on other tests.

### 13.2. Testing the MVC Argument Resolver

Use `@WebMvcTest` or `MockMvc` to send requests with page, size, and sort, and verify the controller receives the expected Pageable or the repository is called with the corresponding arguments.

Cases to test:

- Omitting parameters: receives default page/size/sort.
- Sending valid page and size.
- Sending multiple sort orders.
- Sending ASC and DESC directions.
- Sending size above max.
- Sending negative page, size 0, or negative size.
- Sending a sort property outside the allowlist.
- Using one-indexed requests if configured.
- Using multiple qualified Pageables.
- Verifying custom parameter names, prefixes, and delimiters.

### 13.3. Testing on the Exact Project Version

Spring Data Web resolvers and Spring Boot configuration properties can vary across versions. Integration tests against real dependencies verify:
- YAML properties bind properly.
- The resolver is registered exactly once.
- Default annotations behave as expected.
- Sort requests parse properly.
- Maximum page size is enforced.
- Response metadata matches request conventions.

Do not test the service solely by constructing PageRequest directly; that skips Spring MVC HTTP request parsing.

## 14. Common Pitfalls and Fixes

| Symptom | Cause | Resolution |
|---|---|---|
| Controller fails to resolve Pageable | Spring Data Web support not configured or dependency missing | Check Boot auto-configuration or @EnableSpringDataWebSupport |
| Client sends page=1 but gets the second page | Resolver uses zero-based by default | Align on convention or enable one-indexed parameters |
| Request size is huge | No max page size configured | Configure max-page-size and enforce API limits |
| Sort reports nonexistent property | Using SQL column name instead of Java property or wrong property | Use valid property paths and test |
| Native query ignores sort as expected | Parser/dialect/version limitations | Use fixed ORDER BY or custom repository with allowlist |
| Pages duplicate or miss records | Unstable sort or data changing | Add unique tie-breaker; consider keyset/snapshots |
| Unnecessary count queries | Using Page when UI only needs next/previous | Use Slice when appropriate |
| Default sort is lost | Request sort overrides defaults per resolver rules | Test requests both with and without sort |
| Two Pageables read the same parameter | Missing @Qualifier or wrong prefix | Add qualifiers and use the proper delimiter |
| Endpoint returns oversized payload | Unbounded page size or returning entities with many relations | Cap page size, use DTO projections and suitable fetch plans |

## 15. Pagination API Design Checklist

- [ ] Endpoint declares `Pageable` or `Sort` according to requirements.
- [ ] Clients know whether page index starts at 0 or 1.
- [ ] Default page size and max page size are configured.
- [ ] Parameter names `page`, `size`, `sort` are documented.
- [ ] Default sort includes a unique tie-breaker when needed.
- [ ] Sort fields are validated against an allowlist.
- [ ] Raw sort parameters are never concatenated into SQL/JPQL.
- [ ] Native queries have a dedicated, tested sorting strategy.
- [ ] Choose Page, Slice, or List based on metadata needs.
- [ ] Multiple Pageables are distinguished using qualifiers/prefixes.
- [ ] Response metadata follows a consistent page convention.
- [ ] Both MVC resolver and repository are tested on actual project dependencies.
- [ ] Large offsets, keyset pagination, and continuous data changes have been considered.

## 16. Conclusion

Spring Data Web integrates `Pageable` and `Sort` with Spring MVC via argument resolvers. Clients send page, size, and sort; the controller receives the parsed object and passes it down to the service/repository. `@PageableDefault` and `@SortDefault` define endpoint-level defaults, while Spring Boot properties or resolver customizers govern application-wide rules.

APIs must cap page sizes, standardize page numbering, publish sort names, and accept only validated properties. Stable sorting should include a unique tie-breaker; for large or fast-changing datasets, consider keyset pagination. Choose Page when totals are needed, Slice when only checking if more data exists, and test both the MVC argument resolver and repository to ensure configuration works properly on your target version.