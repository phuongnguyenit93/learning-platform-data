# Designing Safe Filters, Pagination Limits, and Data Authorization

## Objectives

A secure search API must solve three problems simultaneously: which fields users are permitted to filter on, how much data each request is allowed to read, and which records a user is authorized to view. Limiting page size alone is insufficient if the query still reads another tenant's data; checking permissions only in the controller is also insufficient if repository queries, count queries, or exports fail to apply the same data scope.

This article uses Spring Data JPA, Specification, and Spring Security to build a controlled search flow from HTTP request to database. The core principles are:

- Accept filters via typed DTOs and validate inputs.
- Allow sorting only on a server-defined list of properties.
- Cap page size, offset, and search ranges.
- Always compose the tenant/owner scope obtained from the authenticated identity into server-side predicates.
- Apply the same authorization scope across list, count, exists, detail, update, delete, and export operations.
- Return DTOs containing only data the caller is authorized to see.
- Test both results and pagination metadata with multi-tenant/multi-owner data.

After this lesson, you will be able to design filters that do not bind entities directly from clients, prevent SQL/order injection, mitigate data enumeration risks, and avoid oversized queries.

Examples use Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence, and Spring Security 6. Corresponding JPA, Web, Validation, Security, and test support dependencies are required.

## 1. Three Control Layers Must Work Together

A search endpoint typically has three core layers:

| Layer | Question to answer | Example |
|---|---|---|
| Filter validation | What criteria may the user submit? | `name` at most 100 chars, `status` in enum |
| Resource/pagination control | How much data may a single request read? | max `size` 100, bounded offset depth |
| Data authorization | Which rows is the user allowed to view? | current tenant and current owner |

These three layers mitigate distinct risks:

- Validation prevents malformed, overly long, or out-of-domain inputs.
- Pagination bounds execution cost and response payload size.
- Authorization restricts which data is accessible.

For example, a request with page size 20 can still leak 20 records from another tenant if the query omits the tenant predicate. Likewise, an endpoint returning only allowed rows whose count query lacks the tenant scope can still leak the total employee count of another tenant.

Therefore, access scope must be enforced directly inside queries at the service/repository layer rather than relying on the UI hiding buttons or fields.

## 2. Do Not Bind Entities Directly from Requests

Do not accept a JPA entity as a search parameter:

```java
@GetMapping("/employees")
public Page<Employee> search(
        @ModelAttribute Employee employee,
        Pageable pageable
) {
    // Do not use this entity binding approach for public APIs.
}
```

Entities commonly contain internal fields such as `tenantId`, `ownerId`, `role`, `salary`, audit fields, or workflow states. Direct binding lets clients attempt to submit attributes they must not control.

Create a dedicated DTO containing only approved filters:

```java
public record EmployeeFilterRequest(
        @Size(max = 100)
        String name,

        EmployeeStatus status,

        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        Instant createdFrom,

        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        Instant createdTo
) {
    public EmployeeFilter toFilter() {
        return new EmployeeFilter(
                name,
                status,
                createdFrom,
                createdTo
        );
    }
}
```

Internal filter model:

```java
public record EmployeeFilter(
        String name,
        EmployeeStatus status,
        Instant createdFrom,
        Instant createdTo
) {
}
```

Status enum:

```java
public enum EmployeeStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
```

This DTO has no `tenantId`, `ownerId`, or access permissions. Those values must come from the server-verified principal/security context, never from client-supplied query strings or JSON bodies.

If a client sends extra undeclared fields, the framework may ignore or reject them depending on binding configuration. Regardless of which behavior is chosen, the service only reads attributes declared on the DTO and never auto-maps requests onto entities.

## 3. Validate Filters Before Building Queries

Validation must cover both individual field formats and relationships across multiple fields.

Example rules:

- `name` at most 100 characters.
- `status` must be a valid enum value.
- `createdFrom` must be earlier than `createdTo`.
- The search time range must not exceed the business limit.
- Whitespace-only strings are treated as not provided.
- Limit the number of criteria or require at least one filter when the search scope is too broad.

Checking time range in the service:

```java
private void validateFilter(EmployeeFilter filter) {
    if (filter.createdFrom() != null
            && filter.createdTo() != null
            && !filter.createdFrom().isBefore(filter.createdTo())) {
        throw new IllegalArgumentException(
                "createdFrom must be earlier than createdTo"
        );
    }

    if (filter.createdFrom() != null
            && filter.createdTo() != null
            && Duration.between(
                    filter.createdFrom(),
                    filter.createdTo()
            ).compareTo(Duration.ofDays(366)) > 0) {
        throw new IllegalArgumentException(
                "Search range must not exceed 366 days"
        );
    }
}
```

The 366-day limit is merely an illustrative policy. Applications should choose ranges matching business needs, data volume, and database capacity.

Avoid silently rewriting an invalid filter into another filter without a clear contract. For example, if a user sends `createdFrom` greater than `createdTo`, returning a 400 validation error is usually clearer than silently swapping the two dates.

### 3.1. String Normalization

Normalize strings in one consistent place:

```java
private String normalizeName(String name) {
    if (name == null || name.isBlank()) {
        return null;
    }
    return name.trim();
}
```

Do not arbitrarily alter Unicode or strip diacritics if business logic has not clearly defined Vietnamese search semantics. Case and diacritic matching also depends on database collation.

## 4. Designing the Entity and Repository

Example `Employee` entity with tenant and owner to illustrate row-level authorization:

```java
package com.example.demo.employee;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(
    name = "employees",
    indexes = {
        @Index(
            name = "ix_employee_tenant_created_id",
            columnList = "tenant_id, created_at, id"
        ),
        @Index(
            name = "ix_employee_tenant_owner_created_id",
            columnList = "tenant_id, owner_id, created_at, id"
        )
    }
)
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    @Column(nullable = false, length = 120)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private EmployeeStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Employee() {
    }

    public Employee(
            UUID tenantId,
            UUID ownerId,
            String name,
            EmployeeStatus status,
            Instant createdAt
    ) {
        this.tenantId = tenantId;
        this.ownerId = ownerId;
        this.name = name;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public UUID getTenantId() {
        return tenantId;
    }

    public UUID getOwnerId() {
        return ownerId;
    }

    public String getName() {
        return name;
    }

    public EmployeeStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

The two indexes illustrate two common access patterns: administrators reading across the tenant and users reading only their own records. Real indexes should be driven by filters, sorts, cardinality, and database execution plans; do not copy these indexes mechanically.

Repository:

```java
package com.example.demo.employee;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {

    Optional<Employee> findByIdAndTenantId(
            Long id,
            UUID tenantId
    );

    Optional<Employee> findByIdAndTenantIdAndOwnerId(
            Long id,
            UUID tenantId,
            UUID ownerId
    );
}
```

`JpaSpecificationExecutor` enables composing dynamic filters via Specifications. The ID-lookup methods also carry tenant/owner scope directly inside repository predicates, avoiding the risky pattern of fetching an entity globally by ID and checking permissions afterward.

## 5. Obtaining Access Scope from the Authenticated Principal

Tenant and owner scope must come from the authenticated identity. Suppose the application has a principal:

```java
public record AppPrincipal(
        UUID userId,
        UUID tenantId,
        Set<String> authorities
) {
}
```

Access scope model:

```java
public record AccessScope(
        UUID tenantId,
        UUID userId,
        boolean canReadAllInTenant
) {
}
```

Define an abstraction so services can obtain the scope:

```java
public interface AccessScopeProvider {
    AccessScope currentScope();
}
```

Implementation reading `SecurityContext`:

```java
@Component
public class SecurityContextAccessScopeProvider
        implements AccessScopeProvider {

    @Override
    public AccessScope currentScope() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof AppPrincipal p)) {
            throw new AccessDeniedException("Authenticated principal required");
        }

        if (p.tenantId() == null) {
            throw new AccessDeniedException("Tenant scope is missing");
        }

        boolean canReadAll =
                p.authorities().contains("employee:read:any");

        if (!canReadAll && p.userId() == null) {
            throw new AccessDeniedException("User scope is missing");
        }

        return new AccessScope(
                p.tenantId(),
                p.userId(),
                canReadAll
        );
    }
}
```

This is a custom principal example; if your application uses JWT, OAuth2, or another principal type, the implementation must map verified claims/authorities to `AccessScope`. Never trust `tenantId` or `userId` sent by the client in the request.

A critical principle: if a valid scope cannot be determined, deny access. Never treat `null` as a signal for "unrestricted across tenants".

## 6. Mandatory Predicates for Tenant and Owner

Create a Specification that always enforces access scope:

```java
public final class EmployeeSpecifications {

    private EmployeeSpecifications() {
    }

    public static Specification<Employee> visibleTo(AccessScope scope) {
        if (scope == null || scope.tenantId() == null) {
            throw new IllegalArgumentException(
                    "A trusted tenant scope is required"
            );
        }

        if (!scope.canReadAllInTenant() && scope.userId() == null) {
            throw new IllegalArgumentException(
                    "A trusted user scope is required"
            );
        }

        return (root, query, cb) -> {
            Predicate tenantPredicate =
                    cb.equal(root.get("tenantId"), scope.tenantId());

            if (scope.canReadAllInTenant()) {
                return tenantPredicate;
            }

            Predicate ownerPredicate =
                    cb.equal(root.get("ownerId"), scope.userId());

            return cb.and(tenantPredicate, ownerPredicate);
        };
    }

    public static Specification<Employee> hasStatus(
            EmployeeStatus status
    ) {
        return (root, query, cb) -> status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }
}
```

For regular users, the predicate is always equivalent to:

```sql
WHERE tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId
```

For users permitted to read across the entire tenant:

```sql
WHERE tenant_id = :trustedTenantId
```

`trustedTenantId` and `trustedUserId` originate from the server-constructed `AccessScope`. They never come from query parameters.

Never place the tenant predicate inside an optional filter branch. It is a mandatory condition for every tenant-scoped data query.

## 7. Building Safe Search Filters

Next, add Specifications for name and time range:

```java
public static Specification<Employee> nameContains(String input) {
    return (root, query, cb) -> {
        if (input == null || input.isBlank()) {
            return cb.conjunction();
        }

        String normalized = input.trim().toLowerCase(Locale.ROOT);
        String escaped = normalized
                .replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");

        String pattern = "%" + escaped + "%";

        return cb.like(
                cb.lower(root.<String>get("name")),
                pattern,
                '!'
        );
    };
}

public static Specification<Employee> createdAtFrom(Instant from) {
    return (root, query, cb) -> from == null
            ? cb.conjunction()
            : cb.greaterThanOrEqualTo(
                    root.<Instant>get("createdAt"),
                    from
            );
}

public static Specification<Employee> createdAtBefore(Instant to) {
    return (root, query, cb) -> to == null
            ? cb.conjunction()
            : cb.lessThan(
                    root.<Instant>get("createdAt"),
                    to
            );
}
```

These methods can live in the same `EmployeeSpecifications` class. They return an always-true predicate when the corresponding filter is omitted; when combined with AND, that filter does not narrow the result set.

### 7.1. Escaping Wildcards in LIKE

In SQL `LIKE`, `%` matches any sequence and `_` matches a single character. If business rules want literal substring matching on user input, those characters must be escaped.

Suppose a user enters `A_1%`. Without escaping, the database interprets `_` and `%` as wildcards rather than literal characters.

The code uses `!` as the escape character:

- `!` becomes `!!`.
- `%` becomes `!%`.
- `_` becomes `!_`.

Then `cb.like(expression, pattern, '!')` instructs the Criteria API to use `!` as the escape character. Test semantics against your real database and collation if searches require special Unicode or Vietnamese diacritic handling.

The Criteria API and Querydsl generate queries with bind parameters; never concatenate input into SQL/JPQL strings.

## 8. Combining User Filters with Access Scope

The service is where optional user filters are combined with mandatory permission predicates:

```java
@Service
@Transactional(readOnly = true)
public class EmployeeSearchService {

    private final EmployeeRepository repository;
    private final AccessScopeProvider scopeProvider;
    private final EmployeePageRequestFactory pageRequestFactory;

    public EmployeeSearchService(
            EmployeeRepository repository,
            AccessScopeProvider scopeProvider,
            EmployeePageRequestFactory pageRequestFactory
    ) {
        this.repository = repository;
        this.scopeProvider = scopeProvider;
        this.pageRequestFactory = pageRequestFactory;
    }

    @PreAuthorize("hasAuthority('employee:read')")
    public Page<EmployeeResponse> search(
            EmployeeFilter filter,
            int page,
            int size,
            EmployeeSortField sortBy,
            Sort.Direction direction
    ) {
        validateFilter(filter);

        AccessScope scope = scopeProvider.currentScope();

        Specification<Employee> specification =
                EmployeeSpecifications.visibleTo(scope)
                        .and(EmployeeSpecifications.nameContains(filter.name()))
                        .and(EmployeeSpecifications.hasStatus(filter.status()))
                        .and(EmployeeSpecifications.createdAtFrom(
                                filter.createdFrom()
                        ))
                        .and(EmployeeSpecifications.createdAtBefore(
                                filter.createdTo()
                        ));

        Pageable pageable = pageRequestFactory.create(
                page,
                size,
                sortBy,
                direction
        );

        return repository.findAll(specification, pageable)
                .map(EmployeeResponse::from);
    }

    private void validateFilter(EmployeeFilter filter) {
        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && !filter.createdFrom().isBefore(filter.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must be earlier than createdTo"
            );
        }

        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && Duration.between(
                        filter.createdFrom(),
                        filter.createdTo()
                ).compareTo(Duration.ofDays(366)) > 0) {
            throw new IllegalArgumentException(
                    "Search range must not exceed 366 days"
            );
        }
    }
}
```

`@PreAuthorize` verifies functional permission to invoke the use case. `visibleTo(scope)` controls which rows are readable. Both layers serve distinct purposes and should be applied together.

Method security configuration:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Response DTO:

```java
public record EmployeeResponse(
        Long id,
        String name,
        EmployeeStatus status,
        Instant createdAt
) {
    public static EmployeeResponse from(Employee employee) {
        return new EmployeeResponse(
                employee.getId(),
                employee.getName(),
                employee.getStatus(),
                employee.getCreatedAt()
        );
    }
}
```

Do not return the entity directly if the API only needs a subset of fields. DTOs prevent accidentally exposing `tenantId`, `ownerId`, internal details, or associations not meant for the caller.

## 9. Allow-Listing Sort Fields

Never pass a client-supplied sort string directly into a query:

```java
Sort sort = Sort.by(request.getParameter("sort"));
```

Sort fields are not data values that can be bound like normal SQL parameters. They affect the structure of `ORDER BY`. Therefore, map from a fixed set of choices to entity properties.

Public API enum:

```java
public enum EmployeeSortField {
    NAME,
    CREATED_AT,
    STATUS
}
```

Mapping factory:

```java
@Component
public class EmployeePageRequestFactory {

    private static final int MAX_PAGE_SIZE = 100;
    private static final long MAX_OFFSET = 100_000L;

    public Pageable create(
            int page,
            int size,
            EmployeeSortField sortBy,
            Sort.Direction direction
    ) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be non-negative");
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                    "size must be between 1 and " + MAX_PAGE_SIZE
            );
        }

        long offset = (long) page * size;
        if (offset > MAX_OFFSET) {
            throw new IllegalArgumentException(
                    "Requested offset is too deep; use cursor pagination"
            );
        }

        EmployeeSortField safeField =
                sortBy == null ? EmployeeSortField.CREATED_AT : sortBy;

        Sort.Direction safeDirection =
                direction == null ? Sort.Direction.DESC : direction;

        String property = switch (safeField) {
            case NAME -> "name";
            case CREATED_AT -> "createdAt";
            case STATUS -> "status";
        };

        Sort sort = Sort.by(
                new Sort.Order(safeDirection, property),
                Sort.Order.asc("id")
        );

        return PageRequest.of(page, size, sort);
    }
}
```

Clients may only choose `NAME`, `CREATED_AT`, or `STATUS`. The server maps them to valid properties. `id` is added as a tie-breaker to guarantee deterministic ordering when multiple rows share the same sort value.

Do not accept arbitrary property names, association paths, SQL expressions, or database functions from clients. Never use `JpaSort.unsafe` with external input.

## 10. Controller and HTTP Validation

The Controller receives the filter DTO, page, size, sort enum, and direction enum:

```java
@RestController
@RequestMapping("/api/employees")
@Validated
public class EmployeeController {

    private final EmployeeSearchService searchService;

    public EmployeeController(EmployeeSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping
    public Page<EmployeeResponse> search(
            @Valid @ModelAttribute EmployeeFilterRequest filters,

            @RequestParam(defaultValue = "0")
            @Min(0)
            int page,

            @RequestParam(defaultValue = "20")
            @Min(1)
            @Max(100)
            int size,

            @RequestParam(defaultValue = "CREATED_AT")
            EmployeeSortField sortBy,

            @RequestParam(defaultValue = "DESC")
            Sort.Direction direction
    ) {
        return searchService.search(
                filters.toFilter(),
                page,
                size,
                sortBy,
                direction
        );
    }
}
```

A Bean Validation provider is required, such as the Spring Boot Validation starter dependency. When method validation is enabled, negative page indices or sizes exceeding the maximum are rejected. The service factory still validates again because the service may be called from places other than the controller.

Sort values outside the enum or invalid directions fail conversion and the request typically receives HTTP 400. This provides a typed allow-list that is easy to test and decoupled from database column naming.

### 10.1. Example Valid Request

```http
GET /api/employees?name=An&status=ACTIVE&page=0&size=20&sortBy=CREATED_AT&direction=DESC
```

The client chooses filters and sorting within the allow-list. Tenant and owner do not appear in the request; the server derives scope from the principal.

### 10.2. Example Rejected Requests

```http
GET /api/employees?page=-1
GET /api/employees?size=100000
GET /api/employees?sortBy=tenantId
GET /api/employees?sortBy=createdAt desc, (select ...)
```

These requests must be rejected by validation or enum binding before any query executes. Do not silently coerce invalid sort inputs to a default sort if doing so could hide bugs or mislead clients about results.

## 11. Page Size, Offset, and Count Query Cost

`Pageable` is convenient, but it does not automatically solve every performance issue.

### 11.1. Limiting Page Size

An overly large page size can:

- Increase query execution and serialization times.
- Put pressure on heap memory and garbage collection.
- Hold database connections longer.
- Produce large responses consuming excessive bandwidth.
- Increase entity hydration and association loading overhead.

Set a small default size, such as 20, and an explicit max size, such as 100. Actual limits depend on the endpoint and DTO weight.

If using Spring Data's web resolver directly with `Pageable`, limits can be configured on the resolver or via Spring Boot properties. However, when constructing `PageRequest` manually as above, you must enforce the max size in the factory because resolver configuration does not constrain programmatically created `PageRequest` instances.

### 11.2. Limiting Deep Offsets

Large page numbers create very deep OFFSETs. The database often still has to locate and scan past many rows before returning the next page. For example, page 10,000 with size 100 corresponds to an offset of nearly one million rows.

Enforce an offset limit matching data characteristics. If users must navigate deeply through large datasets, switch to keyset/cursor pagination instead of allowing unbounded offsets.

### 11.3. Page and Count Queries

`Page<T>` provides `totalElements` and `totalPages`; Spring Data usually runs a count query to compute this metadata.

The count query must also enforce the exact same access scope. If the content query restricts by tenant while the count query omits tenant filtering, metadata can leak the data volume of unauthorized tenants.

If the UI only needs to know whether a next page exists, use a query returning `Slice<T>` or an appropriate custom query to avoid requiring total row counts. `JpaSpecificationExecutor.findAll(spec, pageable)` returns `Page`; if `Slice` is needed, write a custom repository or dedicated query.

## 12. Keyset/Cursor Pagination for Large Datasets

Keyset pagination uses values from the last row of the previous page to locate the next slice. When sorting descending by `createdAt` then `id`:

```sql
SELECT id, name, status, created_at
FROM employees
WHERE tenant_id = :tenantId
  AND owner_id = :ownerId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSizePlusOne
```

The cursor predicate compares sort keys from left to right. `id` serves as a tie-breaker to avoid skipping or duplicating rows sharing the same timestamp.

For users authorized to read across the tenant, drop the owner predicate per server scope while retaining the mandatory tenant predicate. Never let clients decide whether to omit owner or tenant filters.

### 12.1. Cursors Must Be Bound to Filters and Access Scope

A cursor should not contain only `lastId` when ordering uses multiple fields. A cursor can include:

- The last values of the sort fields.
- Sort direction.
- Cursor version.
- Filter signature or hash of active filters.
- Expiration timestamp and tamper-proof signature.

Base64-encoding a cursor is merely encoding, not protection. Sign cursors with HMAC or use opaque server-side tokens. Upon receiving a cursor, the server must verify the signature, validate the version, and still enforce access scope from the current principal.

Never treat a `tenantId` inside a cursor as a source of authorization. Even if a cursor generated by user A is presented by user B, user B's scope must still apply; better yet, bind the cursor to the tenant/user scope and filter hash to prevent cross-context reuse.

## 13. Enforcing Permissions Across Lists, Details, and Writes

Protecting the list endpoint alone is not enough. The exact same rules must apply to:

- Search and pagination.
- Count and exists checks.
- Detail lookups by ID.
- Updates and deletes.
- CSV/Excel/PDF exports.
- Reports, dashboards, and statistics.
- Background jobs running on behalf of a tenant/user.
- Caches holding search results.

Example scoped detail lookup:

```java
@Service
@Transactional(readOnly = true)
public class EmployeeReadService {

    private final EmployeeRepository repository;
    private final AccessScopeProvider scopeProvider;

    public EmployeeReadService(
            EmployeeRepository repository,
            AccessScopeProvider scopeProvider
    ) {
        this.repository = repository;
        this.scopeProvider = scopeProvider;
    }

    @PreAuthorize("hasAuthority('employee:read')")
    public EmployeeResponse getVisible(Long id) {
        AccessScope scope = scopeProvider.currentScope();

        Employee employee = scope.canReadAllInTenant()
                ? repository.findByIdAndTenantId(
                        id,
                        scope.tenantId()
                ).orElseThrow(
                        () -> new ResponseStatusException(HttpStatus.NOT_FOUND)
                )
                : repository.findByIdAndTenantIdAndOwnerId(
                        id,
                        scope.tenantId(),
                        scope.userId()
                ).orElseThrow(
                        () -> new ResponseStatusException(HttpStatus.NOT_FOUND)
                );

        return EmployeeResponse.from(employee);
    }
}
```

Returning 404 for both nonexistent IDs and out-of-scope IDs avoids leaking the existence of unauthorized records. Some systems choose 403; what matters is keeping the policy consistent and avoiding sensitive data disclosure.

For updates/deletes, perform a scoped load inside the transaction and modify the managed entity. Do not call global `findById(id)` and check tenant afterward once the data has already been loaded. If optimistic locking is used, keep `@Version` to handle concurrent updates.

### 13.1. Count and Exists Are Also Data

APIs such as `/employees/count`, `/employees/exists?email=...`, or status breakdown counts can leak data even without returning entities.

Every count/exists query must include the scope:

```java
Specification<Employee> scoped =
        EmployeeSpecifications.visibleTo(scope)
                .and(EmployeeSpecifications.hasStatus(status));

long count = repository.count(scoped);
```

Do not call `repository.count()` or `repository.existsById(id)` for tenant-scoped data without a predicate or derived method enforcing the same permission scope.

## 14. RBAC, Row-Level Authorization, and Default Deny

Two authorization decisions can be distinguished:

- RBAC: which operations may the user invoke? E.g., `employee:read`, `employee:update`.
- Row-level/attribute-based authorization: which rows may the user read? E.g., same tenant and owned by the user, or tenant-wide read permission.

Example:

| Role/authority | Scope |
|---|---|
| `employee:read` | Allowed to call the read API within personal ownership scope |
| `employee:read:any` | Allowed to read all employees within the current tenant |
| `employee:update` | Allowed to request updates; row scope must still be verified |
| `system:admin` | May have a distinct administrative scope, which must be explicitly defined |

Do not infer that someone holding `employee:read:any` may read across all tenants. In this example, that authority only broadens owner scope within the authenticated tenant.

Default-deny principles:

- No valid principal: deny.
- Missing tenant scope: deny.
- Regular user missing user ID: deny.
- Missing endpoint authority: deny.
- No row found within scope: return nothing.
- Unclear whether a role bypasses tenant restrictions: keep tenant restrictions enforced until a special policy is explicitly defined and tested.

Do not use `@PostFilter` over a large `Page` as your primary data protection mechanism. Filtering after query execution breaks total counts, loads unauthorized rows into memory, and introduces side channels. Push predicates into the query before data is fetched.

## 15. Preventing SQL Injection and Sort Injection

The Criteria API, JPQL parameter binding, and Querydsl bind filter values safely. However, that does not mean every client-supplied string is safe in every position.

Never concatenate input into JPQL:

```java
String jpql = "select e from Employee e order by " + requestSort;
```

Never concatenate strings to build WHERE clauses:

```java
String sql = "where name like '%" + userInput + "%'";
```

Use Criteria/Specifications or parameter binding. For parts of a query that cannot be bound—such as property names, directions, functions, or column names—use a server-side allow-list.

Never let clients pass:

- Arbitrary property names for sorting.
- JPQL fragments or SQL expressions.
- Function names, join paths, or aliases.
- Entity/table/column names.
- `JpaSort.unsafe` expressions.

The sort field enum and switch mapping in this article are a straightforward way to constrain query structure.

## 16. Preventing Enumeration, Abuse, and Leakage via Responses

A search endpoint can still be abused even when filters and SQL are safe.

Additional safeguards:

**Bound broad queries.** If a tenant holds millions of records, require at least one selective filter or a bounded time range for wide-scoped roles.

**Rate limiting.** Throttle request rates per user, tenant, client, or API key. Tighten limits for exports and expensive queries.

**Bound responses.** Enforce max page size, cap total exported rows, and run large exports via permission-checked background jobs.

**Timeouts.** Configure appropriate query timeouts, cancellation, and slow-query monitoring.

**Hide sensitive fields.** DTOs return only necessary fields; never arbitrarily serialize entity graphs.

**Consistent error messages.** Never expose SQL, table names, tenant existence, or stack traces to clients. Log details internally under access controls.

**Scope-aware caching.** Cache keys must include tenant, user/role scope, and filter/sort/page parameters. Never share cache keys across different tenants. Be careful with shared caches and invalidation when permissions change.

**Selective logging.** Avoid logging PII or sensitive filter inputs verbatim. Log request IDs, duration, page size, sort fields, masked scope identifiers, and summary outcomes per policy.

## 17. Testing Filters and Access Scope

Tests must prove that out-of-scope data appears neither in content nor in metadata.

Example repository integration test:

```java
@DataJpaTest
class EmployeeSearchRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EmployeeRepository repository;

    @Test
    void restrictsRowsAndCountToCurrentTenantAndOwner() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        UUID userA = UUID.randomUUID();
        UUID userB = UUID.randomUUID();

        entityManager.persist(new Employee(
                tenantA, userA, "An", EmployeeStatus.ACTIVE,
                Instant.parse("2026-01-10T00:00:00Z")
        ));
        entityManager.persist(new Employee(
                tenantA, userB, "Binh", EmployeeStatus.ACTIVE,
                Instant.parse("2026-01-11T00:00:00Z")
        ));
        entityManager.persist(new Employee(
                tenantB, userA, "Chi", EmployeeStatus.ACTIVE,
                Instant.parse("2026-01-12T00:00:00Z")
        ));

        entityManager.flush();
        entityManager.clear();

        AccessScope scope =
                new AccessScope(tenantA, userA, false);

        Specification<Employee> specification =
                EmployeeSpecifications.visibleTo(scope)
                        .and(EmployeeSpecifications.hasStatus(
                                EmployeeStatus.ACTIVE
                        ));

        Page<Employee> page = repository.findAll(
                specification,
                PageRequest.of(
                        0,
                        10,
                        Sort.by(Sort.Direction.ASC, "id")
                )
        );

        assertThat(page.getContent())
                .extracting(Employee::getName)
                .containsExactly("An");

        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getTotalPages()).isEqualTo(1);
    }
}
```

This test inserts three rows: same tenant/same owner, same tenant/different owner, and different tenant. Results must contain only the first row. More importantly, `totalElements` must also be 1, not 2 or 3.

### 17.1. Testing Tenant-Wide Read Permissions

Add a test with:

```java
AccessScope tenantAdmin =
        new AccessScope(tenantA, adminUserId, true);

Specification<Employee> specification =
        EmployeeSpecifications.visibleTo(tenantAdmin);

assertThat(repository.count(specification)).isEqualTo(2);
```

Tenant-wide read permission returns only the two rows of `tenantA`, excluding `tenantB`. This test prevents conflating tenant admin privileges with system-wide access.

### 17.2. Testing HTTP Validation and Security

In addition to repository tests, use MockMvc or appropriate integration tests to verify:

- Unauthenticated: 401 or response matching security configuration.
- Missing read authority: 403.
- Sort field outside enum: 400.
- Negative page: 400.
- Size 0 or exceeding max: 400.
- Offset exceeding threshold: 400.
- `createdFrom` greater than `createdTo`: 400.
- User A cannot view User B's ID.
- Tenant A cannot view Tenant B's ID.
- Count, export, and detail endpoints enforce the same scope.
- Requests submitting forged `tenantId`/`ownerId` cannot alter access scope.

Do not test only that the controller returns a status code. Assert actual response payloads and metadata.

## 18. Indexes and Execution Plans

Indexes should support the scope predicates and common sort orders. If queries consistently filter by tenant, then owner, and sort by `createdAt`/`id`, a composite index can be considered:

```sql
CREATE INDEX ix_employee_tenant_owner_created_id
ON employees (tenant_id, owner_id, created_at, id);
```

For tenant-admin queries without an owner predicate, a second index can be helpful:

```sql
CREATE INDEX ix_employee_tenant_created_id
ON employees (tenant_id, created_at, id);
```

These DDL statements are common SQL examples; syntax, index direction, and covering capabilities vary across databases. Never create an index solely because a column appears in `WHERE`. Evaluate:

- Selectivity/cardinality of `tenantId`, `ownerId`, and `status`.
- Column ordering in composite indexes.
- Sort direction and the database's ability to use the index for `ORDER BY`.
- Whether `LIKE` has a leading wildcard.
- Count queries and common filter combinations.
- Increased write overhead from having too many indexes.

Use `EXPLAIN` or `EXPLAIN ANALYZE` on the target database. Test with data volumes and distributions close to production; a tiny test table can cause the optimizer to pick a different plan.

## 19. Database Row-Level Security as Defense in Depth

Some databases support Row-Level Security (RLS), such as PostgreSQL. RLS adds a database-layer control so even a query missing a tenant predicate is constrained by session policies.

RLS does not replace application-level authorization. Design it carefully:

- Set the tenant/session context from the authenticated server.
- Ensure connection pools do not leak session variables from one request into the next.
- Set/reset context inside transactions or using an appropriate safe mechanism.
- Test policies using the actual application database user.
- Do not grant RLS bypass privileges to the regular application database user.
- Check background jobs, migration users, and admin connections separately.

When using connection pooling, session state must be managed precisely. An unreset session variable can cause the subsequent request to run under the wrong tenant context. RLS should be deployed as defense in depth alongside scope predicates in services/repositories.

## 20. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| User sees another tenant's records | Query lacks tenant predicate | Always attach mandatory scope from `SecurityContext` |
| List is right but `totalElements` is wrong | Count query omits scope or joins multiply rows | Test count with same predicates; handle `DISTINCT` when needed |
| User alters `ownerId` to read others' data | Scope taken from request | Derive owner/tenant from principal |
| API accepts arbitrary sort fields | Raw sort string used from client | Use enum allow-list and switch mapping |
| Page size too large | Size not capped on server | Enforce max in resolver and service factory |
| Deep pages make queries slow | Large OFFSET | Cap offset; switch to keyset/cursor pagination |
| Wildcard search matches too many rows | `%` and `_` not escaped for literal semantics | Escape wildcards and specify escape character |
| Invalid filters silently ignored | Missing input validation | Return 400 with clear errors |
| Detail API vulnerable to IDOR | Global `findById` followed by incomplete checks | Query by ID + tenant + owner scope |
| Export leaks more data than list | Export uses a different unscoped query | Reuse the same authorization policy |
| Cache serves another tenant's data | Cache key omits tenant/user scope | Include scope in cache key and control invalidation |
| `@PostFilter` slows down and leaks data in memory | Filtering after query runs | Push predicates into SQL before reading |
| Safe query still overloads DB | Missing rate limits, timeouts, and range caps | Apply resource controls per endpoint |
| Tests check only content | `count`/`totalPages` or other tenants not verified | Build multi-tenant fixtures and assert metadata too |

## 21. Pre-Production Checklist for Search APIs

- [ ] Use dedicated search DTOs; never bind entities directly.
- [ ] DTOs contain only permitted filters.
- [ ] Validate lengths, enums, time ranges, and null/blank states.
- [ ] Tenant/owner scope comes from the authenticated principal.
- [ ] Mandatory scope is composed into every query.
- [ ] RBAC endpoint permissions and row-level authorization are tested separately.
- [ ] Detail/update/delete queries also filter by scope.
- [ ] Count/exists/export/report endpoints apply the same scope.
- [ ] Responses use DTOs; never serialize entities arbitrarily.
- [ ] Sort fields and directions belong to an allow-list.
- [ ] Never accept SQL/JPQL fragments or `JpaSort.unsafe` from clients.
- [ ] Page size has explicit default and maximum limits.
- [ ] Deep offsets are capped or replaced by cursor pagination.
- [ ] Sorting includes a unique tie-breaker.
- [ ] Cursors are authenticated and bound to appropriate filters/scope.
- [ ] LIKE queries escape wildcards according to business semantics.
- [ ] Rate limits, query timeouts, and export caps are configured.
- [ ] Cache keys include tenant/user/role scope.
- [ ] Integration tests prove content and counts never exceed scope.
- [ ] HTTP tests cover authentication, authority, sort, page, and size.
- [ ] Indexes are verified via execution plans on the target database.
- [ ] RLS, if enabled, acts as defense in depth with safe connection pool session handling.

## Conclusion

A secure filter combines input validation, resource limits, and record-level authorization. Use DTOs to restrict client-controllable fields; use enum allow-lists for sorting; cap page sizes and offsets; add a unique tie-breaker for deterministic ordering. For large datasets, keyset pagination avoids deep OFFSETs.

Most importantly, tenant/owner scope must come from the authenticated principal and be enforced inside server-side predicates for every read path. Lists, counts, exists checks, details, updates, deletes, exports, and caches must all follow the same policy. Test with fixtures containing multiple tenants and owners, assert both content and `totalElements`, and inspect execution plans and request limits on a production-equivalent database.