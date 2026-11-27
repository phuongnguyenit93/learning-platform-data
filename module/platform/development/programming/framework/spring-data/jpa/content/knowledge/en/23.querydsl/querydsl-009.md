# Controlling Exposed Properties When Accepting Web Predicates

## Objectives

After this lesson, you will be able to accept Querydsl predicates from HTTP request query parameters using `@QuerydslPredicate`; restrict bindable properties using `QuerydslBindings`; customize matching behavior via `QuerydslBinderCustomizer`; combine client-sent predicates with server-enforced security conditions; and test filtering, pagination, sorting, and sensitive data boundaries.

The examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence-compatible Querydsl. Querydsl requires an annotation processor to generate metamodel classes such as `QUser`. Use Querydsl artifacts and versions compatible with your project's Spring Data/Boot versions; for Boot 3, use the Jakarta variant rather than legacy `javax.persistence` artifacts.

## 1. Why Must Web-Received Predicates Be Controlled?

Spring Data supports turning query parameters into a Querydsl `Predicate`. This is convenient for search screens with many filters, but entities often contain internal properties such as `tenantId`, `passwordHash`, soft-delete flags, permissions, or operational fields.

If every entity property can be bound from requests, clients can attempt to filter on fields outside the API contract. That can leak internal structure, trigger heavy queries, or accidentally let clients control data scoping that ought to be derived from the authenticated identity.

Design principles:

- Expose only the filters that the use case actually needs.
- Use an allowlist for bindable properties; do not rely on remembering to exclude individual sensitive fields.
- Keep authorization, tenant, and data-scoping conditions on the server; always combine them with client-submitted predicates.
- Return DTOs/projections instead of persistence entities.
- Limit page size, sorting, and filter complexity.

`@QuerydslPredicate` is a mechanism for translating requests into query conditions. It is not an authorization layer and does not replace authorization.

## 2. Prerequisites for Querydsl Web Support

Spring Data JPA integrates with Querydsl via these core pieces:

- Querydsl JPA and a Jakarta Persistence-compatible annotation processor.
- Q classes generated from entities, such as `QUser` for the `User` entity.
- A repository extending `QuerydslPredicateExecutor<T>` to execute predicates.
- Spring Data web support to resolve `@QuerydslPredicate` parameters in controllers.

In Spring Boot, web support is typically auto-configured alongside Spring Data web auto-configuration. In Spring applications not using Boot auto-configuration, enable it with `@EnableSpringDataWebSupport`.

Conceptual annotation processing configuration:

```text
querydsl-jpa: Jakarta-compatible artifact
querydsl-apt: Jakarta-compatible annotation processor
annotation processing: enabled at compile time
```

Do not mix Querydsl artifacts built for `javax.persistence` with Jakarta (`jakarta.persistence`) entities. If `QUser` is not generated, check the annotation processor and generated-sources directory before troubleshooting repository code.

## 3. Sample Entity and Internal Fields

The sample entity contains both searchable fields and internal-only fields:

```java
package com.example.learning.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(nullable = false)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private UserStatus status;

    @Column(nullable = false)
    private Boolean active;

    protected User() {
    }

    public User(Long tenantId, String username, String displayName,
                String email, String passwordHash,
                UserStatus status, Boolean active) {
        this.tenantId = tenantId;
        this.username = username;
        this.displayName = displayName;
        this.email = email;
        this.passwordHash = passwordHash;
        this.status = status;
        this.active = active;
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getUsername() { return username; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public UserStatus getStatus() { return status; }
    public Boolean getActive() { return active; }
}
```

```java
package com.example.learning.user;

public enum UserStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
```

`tenantId` and `passwordHash` are examples of data clients must never control through public filters. `email` may also need to stay private depending on the API contract; never put a field on the allowlist simply because it exists on the entity.

## 4. Accepting Predicates in a Controller

Spring Data provides the `@QuerydslPredicate` annotation to turn query parameters into a Querydsl predicate:

```java
package com.example.learning.user;

import com.querydsl.core.types.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.querydsl.QuerydslPredicate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users")
public class UserController {
    private final UserSearchService searchService;

    public UserController(UserSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping
    public Page<UserSummary> search(
            @QuerydslPredicate(root = User.class) Predicate predicate,
            @PageableDefault(size = 20, sort = "username") Pageable pageable) {
        return searchService.search(predicate, pageable);
    }
}
```

Example request:

```http
GET /users?username=ada&status=ACTIVE&active=true&page=0&size=20&sort=username,asc
```

With the binder configuration in the next section, `username` can be matched with contains-ignore-case, while `status` and `active` use type-appropriate comparisons. Query parameters `tenantId` and `passwordHash` will not be included in the predicate.

In applications without Spring Boot auto-configuration, enable Spring Data web support with `@EnableSpringDataWebSupport`. `@QuerydslPredicate` only creates a predicate from the request; a repository executor or service must still execute it.

## 5. Allowlisting with QuerydslBinderCustomizer

The most important way to control exposed properties is to exclude all properties first, then explicitly add only allowed paths:

```java
package com.example.learning.user;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface UserRepository
        extends JpaRepository<User, Long>,
                QuerydslPredicateExecutor<User>,
                QuerydslBinderCustomizer<QUser> {

    @Override
    default void customize(QuerydslBindings bindings, QUser user) {
        bindings.excludeUnlistedProperties(true);

        bindings.including(
            user.username,
            user.displayName,
            user.status,
            user.active
        );

        bindings.bind(user.username)
            .first((path, value) -> path.containsIgnoreCase(value.trim()));

        bindings.bind(user.displayName)
            .first((path, value) -> path.containsIgnoreCase(value.trim()));

        bindings.excluding(user.tenantId, user.passwordHash);
    }
}
```

Meaning:

- `excludeUnlistedProperties(true)` sets the default mode to reject binding properties not explicitly exposed.
- `including(...)` creates an allowlist of fields supported by the search API.
- `bind(...).first(...)` defines the matching operation for each path.
- `excluding(...)` explicitly calls out sensitive fields to block; in the example the allowlist already blocks them, yet explicit exclusions also signal security boundaries to readers.

Spring Data web support automatically picks up the `QuerydslBinderCustomizer` declared on the repository for the root entity. As a result, the controller does not need to rebuild binding rules manually.

Do not use `bindings.bind(String.class)` to open a global rule for all strings if the entity contains internal string fields. Binding path by path ensures the API exposes only the exact chosen fields.

## 6. Customizing Matching and Multi-Value Parameters

Default binding may not deliver the intended search experience. For username, exact matching can be too strict; contains-ignore-case fits a username search box better:

```java
bindings.bind(user.username)
    .first((path, value) -> path.containsIgnoreCase(value.trim()));
```

For status, equality is usually clear:

```java
bindings.bind(user.status)
    .first((path, value) -> path.eq(value));
```

If the API wants to support multiple statuses in a single request, you can define a collection-accepting binding:

```java
import java.util.Optional;

bindings.bind(user.status)
    .all((path, values) -> Optional.of(path.in(values)));
```

For example, requests can supply multiple `status` values via repeated query parameters:

```http
GET /users?status=ACTIVE&status=NEW
```

The `.all(...)` binding converts the collection of values into an `IN` condition. Test how clients send multiple values and verify enum conversion works in your Spring Data/Querydsl version. For a single value, the collection still yields a single-element `IN`; if you want equality for one value and IN for multiple, implement explicit rules and test the empty collection case.

Do not accept arbitrary filter strings and pass them straight into Querydsl expressions. Clients should only choose from properties and matchers defined by the server.

## 7. Client Predicates Must Never Decide Authorization Scope

An allowlist stops clients from filtering on unexposed fields, but it does not ensure users see only their own data. Tenant, owner, organization, or access-permission scopes must be constructed from the server-side security context.

Example service always enforcing the tenant condition:

```java
package com.example.learning.user;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserSearchService {
    private final UserRepository users;
    private final TenantContext tenantContext;

    public UserSearchService(UserRepository users, TenantContext tenantContext) {
        this.users = users;
        this.tenantContext = tenantContext;
    }

    @Transactional(readOnly = true)
    public Page<UserSummary> search(Predicate clientPredicate, Pageable pageable) {
        BooleanBuilder scoped = new BooleanBuilder(
            QUser.user.tenantId.eq(tenantContext.requiredTenantId())
        );

        if (clientPredicate != null) {
            scoped.and(clientPredicate);
        }

        return users.findAll(scoped, pageable).map(UserSummary::from);
    }
}
```

`TenantContext` is an application abstraction for retrieving the tenant from the authenticated principal or security context:

```java
package com.example.learning.user;

public interface TenantContext {
    long requiredTenantId();
}
```

The tenant condition is constructed on the server and combined with AND alongside the client-submitted predicate. Sending `tenantId=...` in the request cannot replace this condition because `tenantId` is not on the allowlist; even if someone accidentally adds a binding later, the server condition remains enforced.

Never read a tenant ID or owner ID from query parameters to make access control decisions. If an endpoint serves multi-tenant administrators, enforce a dedicated authorization policy, check roles/permissions on the server, and log accesses per security requirements.

## 8. Returning DTOs Instead of Entities

Do not return the `User` entity directly from a controller just because the repository returns entities. Entities can contain internal fields, lazy relationships, or persistence structures unsuitable for the API.

Response DTO:

```java
package com.example.learning.user;

public record UserSummary(
    Long id,
    String username,
    String displayName,
    UserStatus status,
    Boolean active
) {
    public static UserSummary from(User user) {
        return new UserSummary(
            user.getId(),
            user.getUsername(),
            user.getDisplayName(),
            user.getStatus(),
            user.getActive()
        );
    }
}
```

The DTO contains only fields the endpoint is permitted to return. `passwordHash`, `tenantId`, and internal associations do not appear in the response. If the query demands high read throughput, consider direct DTO/projection queries instead of loading entities and mapping afterward; either way, the response allowlist must be controlled.

## 9. Controlling Pageable and Sort Separately from Predicates

`@QuerydslPredicate` controls filter conditions. `Pageable` and `Sort` use a separate web binding mechanism, so `QuerydslBindings` allowlists do not automatically restrict sort columns.

Cap page size in Spring Boot:

```properties
spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
```

Allow sorting only on selected properties. Validation example in a service or controller:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "username", "displayName", "status"
);

private static void validateSort(Pageable pageable) {
    boolean invalid = pageable.getSort().stream()
        .anyMatch(order -> !ALLOWED_SORTS.contains(order.getProperty()));

    if (invalid) {
        throw new IllegalArgumentException("Unsupported sort property");
    }
}
```

In real applications, translate this validation error into HTTP 400 via an exception handler. Do not allow sorting by `passwordHash`, `tenantId`, or arbitrary associations simply because the entity has those properties.

Excessively large page sizes can trigger resource-heavy queries and huge responses. Set limits appropriate for the use case, database, and system load capacity.

## 10. Behavior for Non-Allowlisted Properties

When `excludeUnlistedProperties(true)` is enabled, unlisted properties are not bound into the predicate. Depending on the argument resolver and validation configuration, unsupported query parameters may be silently ignored instead of automatically returning HTTP 400.

Therefore, if the API requires rejecting every unknown parameter, add HTTP-layer validation: compare received query parameter names against the allowed list, return 400 for invalid keys, and test that behavior. Do not assume `excludeUnlistedProperties(true)` automatically rejects requests.

Example classification:

| Query parameter | Policy |
| --- | --- |
| `username` | Allowed, contains-ignore-case |
| `displayName` | Allowed, contains-ignore-case |
| `status` | Allowed, equality or IN per binding |
| `active` | Allowed, boolean equality |
| `tenantId` | Not bound; tenant determined by server |
| `passwordHash` | Not bound; sensitive data |
| `email` | Not bound unless approved in API contract |
| `sort=passwordHash` | Rejected by sort allowlist |

## 11. Performance and Query Limits

Public filters are also a resource-consumption surface. Considerations:

- `containsIgnoreCase` typically creates `%value%` searches; standard B-tree indexes may not support them efficiently on many databases.
- Cap filter string length and the number of repeated values for collection fields.
- Do not expose filters on deep associations or large collections without evaluating joins and cardinality.
- Inspect execution plans, indexes, and count queries when endpoints return `Page<T>`.
- Use `Slice<T>` or limit result counts if the UI does not need the total record count.
- Avoid letting clients combine dozens of simultaneous filters if the combined query can produce a very expensive plan.

For name searches, you can choose `startsWithIgnoreCase` over `containsIgnoreCase` if product UX permits and you want better index utilization. That decision should be measured against the real database rather than treated as a universal rule for every DBMS.

## 12. Testing Web Binding and Security Boundaries

Tests should cover both filter binding and server-side data scoping:

1. Request with `username=ada` returns only users matching case-insensitive substring search.
2. Request with `status=ACTIVE` returns only the selected status.
3. Query parameter `passwordHash` generates no predicate and does not appear in responses.
4. Query parameter `tenantId` cannot switch the request's tenant.
5. Users in other tenants do not appear even if the client sends valid filters.
6. Sort fields outside the allowlist are rejected; oversized page sizes are capped or rejected per API contract.
7. Invalid enum or boolean values are handled consistently, typically as HTTP 400.
8. Repeated multi-values behave strictly according to the binder's defined semantics.

Example integration test skeleton using MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserSearchWebTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void doesNotExposeInternalFields() throws Exception {
        mvc.perform(get("/users")
                .param("username", "ada")
                .param("passwordHash", "guess")
                .param("page", "0")
                .param("size", "20"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$..passwordHash").doesNotExist())
            .andExpect(jsonPath("$..tenantId").doesNotExist());
    }
}
```

This is a test skeleton; the project must seed data, configure authentication/tenant context, and import MockMvc/JSONPath static matchers. Add assertions on `totalElements` or page content to confirm internal parameters do not influence results. Tenant security tests must include fixtures from at least two tenants and assert responses contain only the current principal's tenant.

Do not test the repository directly with `Predicate` alone; HTTP-level integration tests are essential to confirm the argument resolver, binder customizer, Pageable, and controller work together as expected.

## 13. Common Pitfalls

- **Leaving all properties bindable by default.** Enable `excludeUnlistedProperties(true)` and allowlist using `including(...)`.
- **Excluding only password while forgetting tenant or internal flags.** An allowlist ensures newly added entity fields do not automatically become public filters.
- **Assuming the binder is authorization.** Always combine predicates with server-generated tenant/owner/permission conditions.
- **Returning entities directly in responses.** Use DTOs/projections to control returned fields.
- **Assuming the filter allowlist restricts sorting.** Validate `Sort` separately.
- **Assuming unknown properties always return HTTP 400.** If rejection is needed, validate query parameter names at the HTTP layer.
- **Using a global binding for every String path.** Prefer explicit per-field bindings for exposed fields.
- **Allowing unbounded nested associations.** Control joins, cardinality, and related data.
- **Not capping page size or repeated value counts.** Enforce limits and monitor query costs.
- **Testing only repositories and not endpoints.** Test both the web argument resolver and security boundaries.

## 14. Secure Implementation Workflow

1. Identify which filters an endpoint needs; write an explicit query parameter contract.
2. Configure compatible Querydsl Jakarta artifacts and the annotation processor to generate Q classes.
3. Have the repository extend `QuerydslPredicateExecutor<T>` and `QuerydslBinderCustomizer<QEntity>`.
4. Enable `excludeUnlistedProperties(true)` and `including(...)` only approved paths.
5. Define explicit matchers per path; never accept arbitrary Querydsl expressions from clients.
6. Use `@QuerydslPredicate(root = Entity.class)` in the controller.
7. Combine client predicates with mandatory server-side tenant/owner/authorization predicates in the service.
8. Return DTOs/projections; never expose internal entities.
9. Validate sort, page size, string length, and repeated value counts.
10. Test over HTTP with valid filters, blocked properties, cross-tenant attempts, and invalid inputs.

## Conclusion

`@QuerydslPredicate` translates query parameters into Querydsl predicates, while `QuerydslBinderCustomizer` and `QuerydslBindings` define which properties are exposed and how they match. Enable unlisted-property exclusion, allowlist only necessary fields, enforce server-generated tenant/authorization conditions, return DTOs, and govern Pageable/Sort independently. Web-supplied predicates are untrusted input; allowlists and HTTP integration tests give search APIs a clear, safe, and maintainable contract.