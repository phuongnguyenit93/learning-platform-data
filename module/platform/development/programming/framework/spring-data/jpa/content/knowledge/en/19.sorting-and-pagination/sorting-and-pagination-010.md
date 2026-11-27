# Limiting Page Size and Controlling Allowed Sort Properties

Spring Data JPA supports accepting `Pageable` and `Sort` to paginate and sort results. When these values arrive from an HTTP request, the application needs to control two things: **how many records each request is allowed to fetch at most** and **which properties clients are allowed to sort by**.

Without a page size limit, a client can request a huge page, inflating memory usage, query latency, hydrated entity count, and serialization cost. Allowing arbitrary sort properties lets clients trigger expensive association paths, cause query errors, or expose internal fields that the API should not publish. Configure limits at the web layer and re-validate policies before the repository executes the query.

This lesson uses Spring Boot 3.x, Spring Data JPA 3.x, Jakarta Persistence, and Java 17+. Package names and resolver configurations should be checked against the release train in use.

## 1. Pageable and Sort from HTTP Requests

A controller can accept `Pageable` directly:

```java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping
    public Page<CustomerSummary> search(
            @PageableDefault(
                size = 20,
                sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC
            )
            Pageable pageable
    ) {
        return customerService.search(pageable);
    }
}
```

A typical request:

```http
GET /api/customers?page=0&size=20&sort=createdAt,desc&sort=id,desc
```

Spring Data Web parses the parameters:

- `page`: page index, starting at 0 by default.
- `size`: maximum number of records in a page.
- `sort`: property and sort direction; can be passed multiple times to build a multi-column sort.

For example, `sort=createdAt,desc&sort=id,desc` means sort by createdAt descending, then id descending.

`Pageable` holds the page number, page size, and Sort. The repository uses this information to generate a query with the corresponding limit and order. The controller does not need to manually concatenate SQL strings.

## 2. Default Page Size Is Not the Maximum Limit

These are two distinct concepts:

- **Fallback/default page size**: the size used when the request omits size.
- **Maximum page size**: the upper bound the resolver accepts when the client requests a large size.

For example, setting a default of 20 does not prevent a client from sending `size=50000`. Without a maximum limit configured, requests can still ask for a large page depending on resolver settings.

The `@PageableDefault(size = 20)` annotation only provides a default value for the method's Pageable parameter. It is not a mechanism for limiting request size.

Policies should be decided clearly:

| Policy | Example |
|---|---|
| Default page size | 20 |
| Maximum page size | 100 |
| Starting page | 0 |
| Default sort | createdAt DESC, id DESC |
| Maximum sort properties | 2 client-requested properties |
| Sort omitted | Use default sort |
| Disallowed sort | Return HTTP 400 |

These numbers are only examples. Choose values based on DTO size, query cost, actual load, and UI requirements.

## 3. Configuring the Resolver to Limit Page Size

In Spring Boot, you can declare a `PageableHandlerMethodArgumentResolverCustomizer` bean to configure the resolver that automatically converts request parameters into Pageable.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
public class PaginationWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setMaxPageSize(100);
            resolver.setFallbackPageable(
                PageRequest.of(
                    0,
                    20,
                    Sort.by(
                        Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id")
                    )
                )
            );
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

Meaning:

- `setMaxPageSize(100)`: limits page size at the resolver. For requests asking for more than this limit, the resolver clamps/caps the size to the maximum.
- `setFallbackPageable(...)`: sets the default Pageable when the request does not provide valid page/size parameters.
- `setOneIndexedParameters(false)`: the API uses zero-based page indexes.

The customizer's package is `org.springframework.data.web.config`. The bean is detected by Spring Boot when configuring Spring Data web pagination. If the project registers argument resolvers manually or does not use Boot's default web configuration, configure the actual resolver used by MVC.

Do not rely on framework defaults. Set the maximum page size explicitly so the API keeps a stable contract across Spring Data upgrades.

### 3.1. @PageableDefault and Global Configuration

You can set endpoint-specific defaults:

```java
@GetMapping
public Page<CustomerSummary> search(
    @PageableDefault(
        page = 0,
        size = 25,
        sort = {"createdAt", "id"},
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return customerService.search(pageable);
}
```

If the client omits parameters, the endpoint uses page 0, size 25, and the declared sort. If the client sends page, size, or sort, the request values can override the corresponding defaults.

`@PageableDefault` does not override `setMaxPageSize` and does not create a sort allowlist. Configure the max in the resolver and validate sorting separately.

If each column needs a different default direction, use `@SortDefault.SortDefaults`:

```java
@SortDefault.SortDefaults({
    @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
    @SortDefault(sort = "id", direction = Sort.Direction.DESC)
})
Pageable pageable
```

Use one clear source of defaults per endpoint to avoid confusing interactions between global fallback and method-level annotations.

## 4. Cap Page Size or Reject Over-Limit Requests?

The standard resolver normally caps the requested size to the configured maximum. For example, if a client sends `size=10000`, the application may treat it as size 100 rather than returning an error.

This is a valid policy, provided the API is consistent:

- **Cap**: easily protects resources; the client still receives results with a smaller page size than requested.
- **Reject**: makes the contract stricter when clients must be notified of out-of-bounds requests; requires validating the raw value before or inside a custom argument resolver.

Do not assume that placing `@Max(100)` on a Pageable parameter automatically validates the page size inside the object. Bean Validation does not automatically infer constraints on nested properties inside Pageable without a suitable validation mechanism.

If you want to reject, accept the size parameter separately and validate before constructing Pageable, or write a dedicated resolver/validator. Simple example with explicit parameters:

```java
@GetMapping("/strict")
public Page<CustomerSummary> searchStrict(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
) {
    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
    );

    return customerService.search(pageable);
}
```

This example fixes the sort to focus on page/size validation. If the endpoint also accepts dynamic sorting, parse sort through an allowlist before creating PageRequest. With `@RequestParam`, enable method validation according to your project's Spring MVC/Spring Framework configuration so constraints are enforced.

## 5. Limits Must Also Be Enforced at the Service Layer

The resolver only guards requests passing through MVC argument resolution. A service can be invoked from a scheduled job, message consumer, test, or another service with a manually constructed Pageable. Those call paths do not necessarily pass through the resolver.

Therefore, if the limit is a resource rule for the use case, re-validate it in the service or in a shared policy:

```java
@Component
public class CustomerPagePolicy {

    private static final int MAX_PAGE_SIZE = 100;

    public Pageable validate(Pageable requested) {
        if (requested == null || requested.isUnpaged()) {
            throw new IllegalArgumentException(
                "A paged request is required"
            );
        }

        int page = requested.getPageNumber();
        int size = requested.getPageSize();

        if (page < 0) {
            throw new IllegalArgumentException("Page must be non-negative");
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Page size must be between 1 and " + MAX_PAGE_SIZE
            );
        }

        return requested;
    }
}
```

The service calls the policy before the repository:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final CustomerPagePolicy pagePolicy;

    public CustomerService(
            CustomerRepository repository,
            CustomerPagePolicy pagePolicy
    ) {
        this.repository = repository;
        this.pagePolicy = pagePolicy;
    }

    @Transactional(readOnly = true)
    public Page<CustomerSummary> search(Pageable requested) {
        Pageable pageable = pagePolicy.validate(requested);
        return repository.findAllProjectedBy(pageable);
    }
}
```

The resolver protects the HTTP boundary; the service policy protects the use case when invoked through other paths. Share the same constant/configuration across both places so one does not allow 100 while the other allows 500.

If the resolver already capped the size, the service receives the capped value. If you want to reject the original requested value, validate before the resolver discards the raw size or use a custom resolver.

## 6. Sort from Requests Is Untrusted Input That Needs Control

Spring Data supports dynamic sorting via parameters:

```http
GET /api/customers?sort=name,asc
GET /api/customers?sort=createdAt,desc&sort=id,desc
```

A `Sort` contains one or more `Sort.Order` instances. Each order has a property and direction, and may include ignoreCase or null handling depending on the API.

Do not forward arbitrary sort strings sent by clients directly to the repository without a policy. Risks include:

- Clients requesting sorting on internal fields or fields that should not be public.
- Sorting across association paths that trigger expensive joins or queries.
- Sorting by nonexistent properties causing query failures.
- Many sort columns complicating queries and indexes.
- Unstable sorts causing records to repeat or vanish across pages when data changes.

Spring Data JPA validates/interprets sort properties against mappings and queries, but that does not replace a business allowlist. A property that is valid in JPA may still be disallowed by the API.

## 7. Building an Allowlist of Sort Properties

A safe approach maps public API sort names to permitted Java properties:

| Client-supplied name | Internal property |
|---|---|
| created | createdAt |
| name | name |
| status | status |

Do not put every entity property into the allowlist. Fields such as email, internalNote, passwordHash, or large associations may not be allowed for API sorting even though they exist on the entity.

The policy can validate each order and cap the number of columns:

```java
@Component
public class CustomerSortPolicy {

    private static final Map<String, String> ALLOWED = Map.of(
        "created", "createdAt",
        "name", "name",
        "status", "status"
    );

    private static final int MAX_SORT_FIELDS = 2;

    public Sort validate(Sort requested) {
        List<Sort.Order> accepted = new ArrayList<>();

        for (Sort.Order order : requested) {
            String property = ALLOWED.get(order.getProperty());

            if (property == null) {
                throw new IllegalArgumentException(
                    "Unsupported sort field: " + order.getProperty()
                );
            }

            if (accepted.size() >= MAX_SORT_FIELDS) {
                throw new IllegalArgumentException(
                    "Too many sort fields"
                );
            }

            accepted.add(
                new Sort.Order(order.getDirection(), property)
            );
        }

        if (accepted.isEmpty()) {
            accepted.add(Sort.Order.desc("createdAt"));
        }

        boolean hasId = accepted.stream()
            .anyMatch(order -> order.getProperty().equals("id"));

        if (!hasId) {
            accepted.add(Sort.Order.asc("id"));
        }

        return Sort.by(accepted);
    }
}
```

The example uses the public name `created` and maps it to the Java property `createdAt`. The client cannot pick arbitrary properties. The policy retains only ASC/DESC direction and drops other options so API behavior stays predictable.

Note: the example caps client-requested orders at two and then appends `id` as an internal tie-breaker. If you want to let clients sort by id directly, add id to the allowlist and adjust the limit accordingly.

## 8. Combining PagePolicy and SortPolicy

Both policies can be combined to produce a safe Pageable:

```java
@Component
public class CustomerPagePolicy {

    private static final int MAX_PAGE_SIZE = 100;

    private final CustomerSortPolicy sortPolicy;

    public CustomerPagePolicy(CustomerSortPolicy sortPolicy) {
        this.sortPolicy = sortPolicy;
    }

    public Pageable validate(Pageable requested) {
        if (requested == null || requested.isUnpaged()) {
            throw new IllegalArgumentException(
                "A paged request is required"
            );
        }

        int page = requested.getPageNumber();
        int size = requested.getPageSize();

        if (page < 0) {
            throw new IllegalArgumentException("Invalid page number");
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Invalid page size");
        }

        Sort safeSort = sortPolicy.validate(requested.getSort());

        return PageRequest.of(page, size, safeSort);
    }
}
```

The service uses only the validated Pageable:

```java
@Transactional(readOnly = true)
public Page<CustomerSummary> search(Pageable requested) {
    return repository.findAllProjectedBy(
        pagePolicy.validate(requested)
    );
}
```

If a client sends `sort=created,desc&sort=name,asc`, the policy converts it to sorting by `createdAt DESC`, then `name ASC`, then appends `id ASC` for stability. If a client sends `sort=passwordHash,asc`, the policy rejects it before the repository builds any query.

At the web layer, translate validation errors into HTTP 400 using a consistent exception handler. Never return SQL errors or internal stack traces to the client.

## 9. Why Is a Stable Sort Needed?

Suppose multiple Customers share the same createdAt. If you sort only by createdAt, the order among records with identical timestamps is not uniquely determined. When the client fetches page 0 and then page 1, new data may be inserted or updated; records can repeat or be skipped between the two requests.

Append a unique key as the final criterion:

```java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);
```

When createdAt values tie, id determines the order. This acts as a tie-breaker to make ordering more deterministic.

A stable sort does not create a consistent snapshot across multiple HTTP requests. If data changes continuously, offset pagination can still shift. For deep browsing or volatile data, consider keyset/seek pagination and cursors built on the sort fields plus a unique key.

## 10. Multi-Column Sorting and Request Syntax

Spring Data Web typically accepts multiple sort parameters:

```http
GET /api/customers?page=0&size=25&sort=created,desc&sort=id,asc
```

The order of sort parameters represents priority order:

1. created DESC.
2. id ASC.

A single sort parameter can contain a property and direction; the default direction syntax can be ASC if omitted. Document the API syntax clearly in OpenAPI and test how the resolver parses commas, dots, and property names.

Do not accept SQL expressions like `LOWER(name)` from clients. If the API needs case-insensitive sorting or expression-based sorting, provide a fixed named sort option and map it to a developer-controlled expression.

## 11. Be Careful with JpaSort.unsafe

Spring Data JPA provides `JpaSort.unsafe(...)` for cases requiring sorting by an expression not permitted by standard property sorting. This advanced API allows putting an expression into ORDER BY without regular property path validation.

Illustrative example for developer-controlled code:

```java
Sort expressionSort = JpaSort.unsafe("LENGTH(name)");
```

Never pass a user-supplied sort string directly into `JpaSort.unsafe`. Doing so breaks the boundary between permitted sort options and query structure. If expression sorting is needed, map a fixed enum/alias such as `nameLength` to a prewritten expression in code—never accept raw expressions over HTTP.

With native SQL queries, how Spring Data applies dynamic Sort depends on query type and version. Do not assume every native query safely supports dynamic sorting. For complex native SQL, declare explicit queries/ORDER BY clauses or construct queries from a controlled identifier allowlist.

## 12. Limiting Number of Sort Properties and Sort Types

Beyond an allowlist, an API can restrict:

- Maximum number of sort columns, e.g. 2.
- Direction limited to ASC or DESC only.
- Disallowing sorting by nested associations without a clear use case.
- Disallowing sorting by LOB, JSON, secret fields, or heavy computed expressions.
- Disallowing client control of null precedence if the database/provider has not been tested.
- Accepting only predefined sort combinations if the query relies on specific indexes.

Even when each property is in the allowlist, not every combination is equally efficient. For example, sorting by status then createdAt may need a different composite index than sorting by createdAt then status.

If an API needs several fixed sorting modes, an enum works well:

```java
public enum CustomerOrder {
    NEWEST,
    NAME_ASC,
    STATUS_ASC
}
```

The service maps each option to a fixed Sort:

```java
private Sort toSort(CustomerOrder order) {
    return switch (order) {
        case NEWEST -> Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
        );
        case NAME_ASC -> Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id")
        );
        case STATUS_ASC -> Sort.by(
            Sort.Order.asc("status"),
            Sort.Order.asc("id")
        );
    };
}
```

Enums are often easier to document and test than letting clients send arbitrary property paths.

## 13. Page, Slice, and Resource Limits

Pageable controls the number of rows per page, while the result type determines query count and cost:

| Return Type | Content | Cost Considerations |
|---|---|---|
| Page<T> | Content, page metadata, and total record/page counts | Usually requires a count query |
| Slice<T> | Content and whether a next page exists | Usually avoids full count |
| List<T> with Pageable | Bounded content only | No total metadata |
| Window<T> | A result window using the Scroll API | Fits scrolling/keyset when supported by provider/query |

If the UI needs total pages, use Page. If it only needs a "Load more" button, Slice generally avoids the count query. For sequential processing of large datasets, consider the Scroll API/keyset instead of deep offset pages.

A page size of 100 does not guarantee a lightweight query: entities with eager associations, fetch joins, or large DTOs can still yield heavy payloads. Pair page limits with projections/DTOs, explicit fetch plans, and suitable indexes.

## 14. Large Offsets and Page Number Limits

PageRequest uses page number and page size to calculate the offset. The deeper the page, the more rows the database may have to skip before returning results.

Example:

```java
PageRequest.of(
    10000,
    100,
    Sort.by("id").ascending()
);
```

The corresponding offset is one million rows. On large tables, using a large OFFSET can be slow even when page size is capped.

You can also enforce a maximum page index or offset limit on endpoints if the business does not need access to extremely deep pages. When traversing an entire dataset, use keyset pagination or the Scroll API with cursors instead of incrementing page numbers indefinitely.

A page size cap limits rows returned per call; it does not limit offset by itself. These two limits address two separate problems.

## 15. Indexes and Sorting

The database may have to sort many rows if no matching index exists. For the query:

```sql
SELECT id, name, status, created_at
FROM customers
WHERE status = ?
ORDER BY created_at DESC, id ASC
LIMIT ? OFFSET ?;
```

A composite index can help depending on the database and selectivity:

```sql
CREATE INDEX idx_customers_status_created_id
    ON customers (status, created_at DESC, id ASC);
```

This is a directional example, not a default index for every schema. Use execution plans and workload patterns to decide column order, sort direction, and whether a covering index is needed. Different databases vary in how well they exploit mixed-direction indexes.

Do not create indexes for every allowlisted property. Every index increases insert/update/delete overhead and storage size. Select a common set of high-value business sorts.

## 16. Translating Input Errors into Clear HTTP Responses

If the policy rejects a page size or sort field, the API should return HTTP 400 with a consistent message:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> handleInvalidQuery(
            IllegalArgumentException exception
    ) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST
        );
        problem.setTitle("Invalid pagination or sort parameter");
        problem.setDetail(exception.getMessage());

        return ResponseEntity.badRequest().body(problem);
    }
}
```

In large applications, prefer a dedicated exception such as `InvalidPageRequestException` rather than catching every IllegalArgumentException, since generic exceptions can stem from unrelated programming bugs. Return only necessary input error details; never return SQL, internal entity mappings, or stack traces.

If the resolver caps size, the response may need to expose the actual applied page size in metadata so the client knows the server applied a limit. With Spring Data Page, `getSize()` reflects the page's Pageable size; test your response serializer.

## 17. Testing Pagination Configuration and Allowlists

Test both the MVC resolver and the policies:

- Omitting size: uses fallback size.
- Passing valid size: preserves requested size.
- Passing size above max: resolver caps or endpoint rejects per contract.
- Passing size 0/negative: handled per policy and resolver version.
- Passing negative page: normalized or rejected per API contract.
- Passing allowed sort: maps to the right Java property.
- Passing disallowed sort: returns HTTP 400 before reaching repository.
- Passing too many sort orders: rejected.
- Omitting sort: uses default sort.
- Ties in sort values: id tie-breaker keeps output stable.
- Pageable.unpaged(): rejected by service policy if use case requires bounds.
- Calling service directly with a large Pageable: policy still enforces limits.

Example unit test for sort policy:

```java
class CustomerSortPolicyTest {

    private final CustomerSortPolicy policy =
        new CustomerSortPolicy();

    @Test
    void mapsPublicSortAliasToEntityProperty() {
        Sort result = policy.validate(
            Sort.by(Sort.Order.desc("created"))
        );

        List<Sort.Order> orders =
            StreamSupport.stream(result.spliterator(), false).toList();

        assertThat(orders)
            .extracting(Sort.Order::getProperty)
            .containsExactly("createdAt", "id");
    }

    @Test
    void rejectsUnsupportedProperty() {
        assertThatThrownBy(() ->
            policy.validate(Sort.by("passwordHash"))
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
```

This is a test skeleton; add imports and MVC resolver tests matching your Spring Boot version. For integration tests, verify both SQL and result order on the same database family as production.

## 18. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Client requests huge size | Only default size configured, no max configured | Use setMaxPageSize |
| @PageableDefault does not limit size | Annotation only sets default values | Configure resolver max |
| Scheduled job bypasses max size | Calls service directly, skipping MVC resolver | Validate Pageable inside service policy |
| Sorting by unknown property fails query | Sort names are not validated | Use an allowlist |
| Sorting across relationships slows query | Arbitrary nested properties permitted | Allow only cost-evaluated fields |
| Unstable sort across pages | Missing unique tie-breaker | Append id or unique key at the end |
| Deep pages are very slow | Large offset | Cap offset or use keyset/Scroll API |
| Page query slow despite small content | Expensive count query | Use Slice if total is not needed |
| Native query does not apply sort as expected | Dynamic sort support depends on query/provider | Declare ORDER BY or whitelist dedicated queries |
| Sort expression creates risk | Raw input passed to JpaSort.unsafe | Only use fixed expressions in code |
| Too many sort fields | Order count is uncapped | Limit allowed columns and combinations |
| Valid page size but heavy response | Large entity graph/associations/payload | Use projections, DTOs, and fetch plans |
| API leaks SQL errors to client | Unstandardized validation error handling | Exception handler returns safe HTTP 400 |

## 19. Practice Exercises

1. Create a GET /api/customers endpoint accepting Pageable and inspect page, size, and sort query parameters.
2. Configure fallback page size 20 and max page size 100 using a resolver customizer.
3. Send a size=10000 request and verify the resolver caps it per contract.
4. Use @PageableDefault to set default sort to createdAt DESC, id DESC.
5. Write CustomerSortPolicy allowing only created, name, and status.
6. Try sending sort=passwordHash,asc and verify the API returns HTTP 400 before hitting the repository.
7. Cap client-requested sort orders at two and automatically append the id tie-breaker.
8. Compare Page and Slice to observe count queries.
9. Test large page numbers and measure offset query execution time.
10. Create an appropriate index for a common filter + sort and compare execution plans.
11. Call the service directly with a large/unpaged Pageable to confirm the service policy still protects it.
12. Write MVC tests verifying defaults, max size, sort allowlist, and error messages.

**Guiding principle:** default page size and maximum page size are two separate settings. Use the resolver to guard HTTP requests, re-validate Pageable in the service when other call paths exist, and map sort aliases exclusively through an allowlist of permitted properties. Append a unique key as a tie-breaker, pick Page/Slice/keyset to fit the use case, and measure queries and indexes on a real database.