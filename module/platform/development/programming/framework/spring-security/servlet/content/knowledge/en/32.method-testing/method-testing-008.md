# Testing `@PreFilter`, `@PostFilter`, and Non-Owned Data — Spring Security Servlet

## 1. Objectives

A multi-user system typically stores data belonging to **Alice, Bob**, and multiple tenants in the same database. Checking only `authenticated()` on an HTTP endpoint is not enough: a logged-in user can still request another user's records by changing an ID in the URL or in a list submitted to the API. This class of flaws is **Broken Object Level Authorization (BOLA/IDOR)**.

In **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**, method security provides related annotations:

- **`@PreFilter`**: filters each element of a collection argument before the method executes.
- **`@PostFilter`**: filters each element of a returned collection after the method executes but before the result is returned to the caller.
- **`@PreAuthorize`**: decides whether to allow or deny **the entire method invocation** before running.
- **`@PostAuthorize`**: checks after the method runs (commonly used with a single return object; requires understanding side-effect risks).

The goal of this lesson is to **understand precisely when an element is silently dropped, when the entire operation must be rejected, how to write tests so no other owner's records leak, and the limits of filtering when protecting real data**.

By the end of this lesson, you will be able to:

1. Set up a Spring Security Servlet project with `@EnableMethodSecurity`.
2. Use `filterObject` and `authentication.name` in SpEL to process collections.
3. Distinguish data **coming from the client** from data **fetched from a trusted repository**.
4. Use JUnit 5, `@WithMockUser`, `MockMvc`, and assertions to test Alice/Bob scenarios, missing permissions, and non-existent objects.
5. Recognize scenarios where you **should not** use `@PreFilter` or `@PostFilter` in place of ownership checks at the persistence/service layer.

The Java examples use **in-memory data to clarify the annotations**. In production, enforce permission checks where the database is queried/updated, along with tenant isolation, transactional integrity, and proper auditing.

## 2. Method Security Mechanism and Where Filters Execute

Spring Security protects methods through interceptors/advisors in Spring AOP. With a typical configuration:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` in Spring Security 6 enables `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` support by default (`prePostEnabled=true`), unless the application changes that option. In older Spring Security versions, the mechanism and syntax for enabling global method security may differ.

General flow:

```text
HTTP request -> Spring Security filter chain authenticates principal
    -> Controller calls Spring-managed Service bean through proxy
        -> @PreAuthorize checks permission to invoke method
        -> @PreFilter filters input collection (if present)
        -> Business method executes
        -> @PostFilter filters output collection (if present)
        -> @PostAuthorize checks result condition (if present)
    -> Controller sends response
```

This diagram is a **conceptual mental model** and does not guarantee a fixed ordering among every advice if you stack multiple annotations on one method or customize advisor ordering. When combining multiple annotations, test the real filter chain and real method rather than inferring ordering from the diagram.

`SecurityContextHolder` holds the request's `Authentication`; method security retrieves authentication from the active context. `authentication.name` is usually the principal name, though in JWT/OIDC or custom principals it may be a subject/identifier different from a UI username. Define a **trusted stable identifier** for ownership policies.

**Important:** Spring AOP proxies only intercept calls going through the proxy. If you write `this.visibleOrders()` inside the same service containing the annotated method, or manually instantiate `new OrderService(...)` instead of using the Spring bean, security advice can be bypassed. That is why tests must obtain the service from `ApplicationContext`.

## 3. How Does `@PreFilter` Differ from `@PostFilter`?

| Comparison Point | `@PreFilter` | `@PostFilter` |
| --- | --- | --- |
| Filtered target | Argument passed into the method | Value returned by the method |
| Timing | Before business logic | After business logic completes |
| Per-element expression | `filterObject` | `filterObject` |
| Example | Pass only IDs with the right owner into the method | Return only records with the right owner |
| Policy mismatch | Element is removed | Element is removed from the result |
| Automatically throws 403 for one bad element? | **No**, normally just filters | **No**, normally just filters |
| Automatically stops queries reading others' data? | No | No — the method may already have queried everything |
| Best suited for | Selecting allowed items when business logic allows dropping extras | Demos/small collections, filtering display results |
| When atomic operation & full rejection are required | Use `@PreAuthorize`/another guard | Not sufficient |

### 3.1. `filterObject` and `filterTarget`

When a filter evaluates a collection, each element is bound in turn to the SpEL variable **`filterObject`**.

```java
@PreFilter("filterObject.owner() == authentication.name")
public List<OrderView> keepOnlyOwned(List<OrderView> orders) {
    return List.copyOf(orders);
}
```

The example above *illustrates the expression*, not a standalone runnable class. **If the collection holds client-created objects with an `owner` field, that field is not proof of ownership.** A client can submit `owner="alice"` for Bob's ID. Never use this snippet as-is for authorizing a real write operation.

If a method takes multiple filterable arguments, declare **`filterTarget`** to select the exact parameter:

```java
@PreFilter(
    filterTarget = "ids",
    value = "@ownershipPolicy.isOwner(filterObject, authentication.name)"
)
public List<Long> keepOwnedIds(List<Long> ids) {
    return List.copyOf(ids);
}
```

Here `ownershipPolicy.isOwner(id, username)` **reads true ownership from the server/repository**, never trusting an `owner` field sent by the client. `filterObject` is a `Long` ID. For the expression to invoke the helper, `ownershipPolicy` must be a Spring bean and the helper method must be accessible.

### 3.2. Using `@PostFilter` on Returned Collections

```java
@PostFilter("filterObject.owner() == authentication.name")
public List<OrderView> visibleOrders() {
    return new ArrayList<>(repository.findAll());
}
```

The method fetches data from the server first, and Spring Security filters the result afterwards. In this learning example, `repository.findAll()` returns a tiny set and the method returns a **mutable list**. Avoid returning an immutable `List.of(...)` when the framework/filter needs to remove elements from the collection; for types like `Page<T>` or reactive publishers, do not assume the same annotation works directly.

**`@PostFilter` is not an optimal mechanism for large tables**: all objects may already have been fetched, serialized internally, logged, or touched in memory before removal from the return value. With pagination, post-query filtering also makes page counts and totals inconsistent. In production, filter by owner/tenant **directly in the repository query**.

### 3.3. What About Returning a Single Object?

For a single order `GET /orders/{id}`, `@PostFilter` is the wrong tool because the method returns `OrderView`, not a collection. You can use:

```java
@PostAuthorize("returnObject.owner() == authentication.name")
public OrderView getOne(long id) {
    return repository.getById(id);
}
```

This is an **illustrative snippet**, not a complete implementation. `@PostAuthorize` blocks returning the object if the condition fails, yet the business method **has already run**; never use this pattern to protect sensitive side effects like transferring funds, approving orders, or deleting data. For ID-based operations, use **`@PreAuthorize` + repository owner check** before taking action, or an explicit transactional policy guard.

## 4. Non-Owned Data: Scenarios That Must Be Tested

Suppose the repository holds:

| ID | Owner | Tenant | Title |
| --- | --- | --- | --- |
| 1 | alice | team-a | Order A1 |
| 2 | bob | team-b | Order B1 |
| 3 | alice | team-a | Order A2 |

The logged-in actor is **alice**. Expectations:

- `visibleOrders()` returns only IDs **1, 3**; ID 2 must not leak in the response.
- `keepOwnedIds([1,2,3])` passes **[1,3]** into the business method.
- If the API contract is **"all-or-nothing"**, `requireAllOwned([1,2,3])` must throw `AccessDeniedException`/return 403, **never silently execute [1,3]**.
- `getOwnedById(2)` must be denied before the service returns Bob's record.
- If a request fakes `owner=alice` with `id=2`, the policy still checks the owner in the database and denies it.
- When Bob logs in, results flip: Bob sees only ID **2**.
- For non-existent data, the policy fails closed; whether to return 403 or 404 must follow an anti-ID-enumeration design.
- With multi-tenancy, `owner` alone may not suffice: a username could collide across tenants, or the same user could hold different permissions per organization. Check **owner + tenant + resource relationship**.

**Records sent by the client are not the truth about ownership.** Never trust `owner`, `tenantId`, `role`, `isAdmin`, or `approvedBy` from a request body or query string; the server must verify these attributes against protected data.

## 5. Runnable Spring Boot 3.x Example: Classes to Create

Create a project with Spring Initializr choosing Java 17+, Spring Boot 3.x, Gradle (Groovy), and starters: Spring Web, Spring Security. Source layout in the example:

```text
src/main/java/com/example/ownership/
  OwnershipApplication.java
  SecurityConfig.java
  OrderView.java
  OrderRepository.java
  OwnershipPolicy.java
  OrderService.java
  OrderController.java

src/test/java/com/example/ownership/
  OwnershipMethodSecurityTests.java
```

In `build.gradle` (dependencies section; plugins/dependency management generated by Spring Initializr):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This project intentionally uses an in-memory `List` to test Spring AOP behavior without setting up a DB, migrations, or JPA. **Do not treat this as a production pattern for order management**: real services need database-level ownership/tenant policies and concurrency control.

### 5.1. Application Entrypoint

File `src/main/java/com/example/ownership/OwnershipApplication.java`:

```java
package com.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
```

### 5.2. Model with a Java `record`

File `src/main/java/com/example/ownership/OrderView.java`:

```java
package com.example.ownership;

public record OrderView(
    long id,
    String owner,
    String tenantId,
    String title
) {
}
```

The record is an immutable presentation view; actual resource ownership must come from a trusted data source.

### 5.3. In-Memory Repository Returning a Mutable Copy

File `src/main/java/com/example/ownership/OrderRepository.java`:

```java
package com.example.ownership;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final List<OrderView> data = List.of(
        new OrderView(1L, "alice", "team-a", "Order A1"),
        new OrderView(2L, "bob", "team-b", "Order B1"),
        new OrderView(3L, "alice", "team-a", "Order A2")
    );

    public List<OrderView> findAll() {
        return new ArrayList<>(data);
    }

    public Optional<OrderView> findById(long id) {
        return data.stream().filter(order -> order.id() == id).findFirst();
    }
}
```

`List.of(...)` in field `data` is immutable, yet **`findAll()` returns a separate `ArrayList`** so `@PostFilter` can filter the collection without mutating the source list. Directly returning an ORM-managed collection and letting a filter remove items can cause unintended side effects; in production, choose query-level filtering.

### 5.4. Policy Bean: Checking IDs Against Repository Truth

File `src/main/java/com/example/ownership/OwnershipPolicy.java`:

```java
package com.example.ownership;

import java.util.List;

import org.springframework.stereotype.Component;

@Component("ownershipPolicy")
public class OwnershipPolicy {

    private final OrderRepository repository;

    public OwnershipPolicy(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(Long id, String username) {
        if (id == null || username == null) {
            return false;
        }

        return repository.findById(id)
            .map(order -> username.equals(order.owner()))
            .orElse(false);
    }

    public boolean allOwned(List<Long> ids, String username) {
        return ids != null
            && !ids.isEmpty()
            && ids.stream().allMatch(id -> isOwner(id, username));
    }
}
```

- `isOwner` looks up the record **on the server**, rather than comparing an owner field supplied by the client.
- Missing ID, non-existent ID, or missing username all yield **false**.
- `allOwned` requires **every** ID to be valid; there is no "pass through the subset of owned IDs" logic.
- If production has tenants, the method must take a **trusted tenant** and verify it in the owner/tenant lookup. `username` alone only suffices for a small demo user set.
- If an ID is authorized and the resource changes owner before the operation runs, design transactions, versioning, or `WHERE owner_id = ...` queries to avoid **TOCTOU (time-of-check/time-of-use)**.

The pattern above queries the repository per ID; for large lists that costs N queries. In production, replace it with set/join queries, policy guards checking allowed counts, and conditional updates.

### 5.5. Service Applying Three Different Policies

File `src/main/java/com/example/ownership/OrderService.java`:

```java
package com.example.ownership;

import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    // Before calling the method: pass only IDs truly owned by the caller into the method.
    @PreFilter(
        filterTarget = "ids",
        value = "@ownershipPolicy.isOwner(filterObject, authentication.name)"
    )
    public List<Long> keepOwnedIds(List<Long> ids) {
        return List.copyOf(ids);
    }

    // After the method returns: show only records owned by the caller.
    @PostFilter("filterObject.owner() == authentication.name")
    public List<OrderView> visibleOrders() {
        return new ArrayList<>(repository.findAll());
    }

    // Atomic contract: any ID not owned by the caller => deny.
    @PreAuthorize(
        "@ownershipPolicy.allOwned(#p0, authentication.name)"
    )
    public List<Long> requireAllOwned(List<Long> ids) {
        return List.copyOf(ids);
    }

    // Single resource: check permission on ID before reading to return.
    @PreAuthorize(
        "@ownershipPolicy.isOwner(#p0, authentication.name)"
    )
    public OrderView getOwnedById(long id) {
        return repository.findById(id)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
```

**Important point about `@PreFilter`:** the service receives an **already-filtered** collection. If the API implicitly requires processing every item in the batch, this can be a business bug: the caller assumes the whole batch was processed while some items were skipped. Hence `requireAllOwned` uses `@PreAuthorize` to deny the entire call if any ID is not owned by the user.

**Important point about `@PostFilter`:** `visibleOrders()` still invokes `findAll()` before filtering. This is an annotation demo, **not a recommendation to fetch every order and filter in the JVM**. The service must also avoid side effects, logging secret data, or sending notifications containing Bob's records during the read before `PostFilter` runs.

**Important point about `#p0`:** this expression references the first argument by **position**, independent of whether the Java class retains compiler parameter names. With multiple parameters where clear names are desired, use Spring Security's parameter-name discovery or parameter annotations, and test with the real build.

### 5.6. Enabling Method Security and HTTP Authentication

File `src/main/java/com/example/ownership/SecurityConfig.java`:

```java
package com.example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Here `authenticated()` only requires the caller to be logged in at the HTTP layer; **ownership is enforced inside `OrderService`**. The example uses Basic Auth for simplicity, yet **does not disable CSRF** by default. Spring Security still protects state-changing operations in appropriate browser contexts; the HTTP demo only has GET routes so no CSRF token is needed. In production, configure sessions, Basic/Bearer, CSRF, CORS, and logging to fit the real application.

### 5.7. Controller Calling the Spring-Managed Service

File `src/main/java/com/example/ownership/OrderController.java`:

```java
package com.example.ownership;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    public List<OrderView> list() {
        return orders.visibleOrders();
    }

    @GetMapping("/api/orders/{id}")
    public OrderView one(@PathVariable long id) {
        return orders.getOwnedById(id);
    }
}
```

The controller invokes the Spring-injected `OrderService` bean, so calls pass through the method-security proxy and annotations execute. **Never call `new OrderService(...)` or `this.visibleOrders()` to bypass the proxy.**

These GET APIs do not accept an `owner` query parameter to choose which data to display; they rely solely on the authenticated principal and server-side policy.

## 6. Real Testing with JUnit 5 + `@WithMockUser`

File **`src/test/java/com/example/ownership/OwnershipMethodSecurityTests.java`**:

```java
package com.example.ownership;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipMethodSecurityTests {

    @Autowired
    OrderService service;

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void postFilterReturnsOnlyAliceOrders() {
        List<Long> ids = service.visibleOrders().stream()
            .map(OrderView::id).toList();

        assertEquals(List.of(1L, 3L), ids);
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilterReturnsOnlyBobOrder() {
        List<Long> ids = service.visibleOrders().stream()
            .map(OrderView::id).toList();

        assertEquals(List.of(2L), ids);
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilterRemovesForeignIdsBeforeMethodRuns() {
        // MUST use a mutable collection for the filter in this example.
        List<Long> mixed = new ArrayList<>(List.of(1L, 2L, 3L));

        List<Long> result = service.keepOwnedIds(mixed);

        assertEquals(List.of(1L, 3L), result);
    }

    @Test
    @WithMockUser(username = "alice")
    void strictBatchRejectsEvenOneForeignId() {
        assertThrows(AccessDeniedException.class,
            () -> service.requireAllOwned(List.of(1L, 2L, 3L)));

        assertEquals(List.of(1L, 3L),
            service.requireAllOwned(List.of(1L, 3L)));
    }

    @Test
    @WithMockUser(username = "alice")
    void singleForeignRecordDeniedBeforeServiceReturnsIt() {
        assertThrows(AccessDeniedException.class,
            () -> service.getOwnedById(2L));

        assertEquals(1L, service.getOwnedById(1L).id());
    }

    @Test
    void mvcListNeverSerializesForeignOrder() throws Exception {
        mvc.perform(get("/api/orders").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[*].id",
                containsInAnyOrder(1, 3)));

        mvc.perform(get("/api/orders").with(user("bob")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(2));
    }

    @Test
    void mvcSingleResourceEnforcesOwner() throws Exception {
        mvc.perform(get("/api/orders/2").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders/2").with(user("bob")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void unauthenticatedCallerCannotListOrders() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
```

### 6.1. What Do These Tests Prove?

- `service` calls execute through a **proxied Spring bean**, not a manually constructed object.
- `@WithMockUser(username = "alice")` sets a simulated `Authentication` on the test thread so `authentication.name` in SpEL evaluates properly.
- `@PreFilter` receives a mutable `ArrayList` and drops Bob's ID before the service processes it.
- `@PostFilter` scopes results per principal Alice/Bob, keeping record ID 2 out of Alice's response.
- `@PreAuthorize` acts as a **strict guard**, disallowing a batch containing even one unowned element.
- `MockMvc` verifies **HTTP** outcomes and 403 on another user's ID, rather than only reading the service return value.
- Missing credentials yield 401 in the Basic Auth demo config; real token/session systems may use different entry points.

The tests use an **in-memory repository and mock security principal**, and do not verify JWTs, real session login, or database queries. For applications using JWTs, add matching Resource Server tests (`JwtDecoder`, issuer/audience, subject mapping); `@WithMockUser` alone does not prove JWT claims were validated.

### 6.2. Running Tests and Expected Outcomes

In the Gradle Wrapper project generated by Spring Initializr:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Expectation:** all tests in section 6 pass if the project and dependencies are correct and method security is actually enabled. Do not cite exact log line counts or `BUILD SUCCESSFUL` as fixed stdout, since Gradle versions, logging, and plugins vary.

When running the app with:

```bash
./gradlew bootRun
```

You must configure test accounts/real Identity Provider if calling HTTP Basic outside `MockMvc`; Spring Boot Security may generate a default user with a generated password in development. **Never use the console generated password as a production auth mechanism**, and never leave sample IDs 1–3 in place of real database data.

## 7. Why Can `@PreFilter` Tests Pass While Authorization Is Still Broken?

### 7.1. Clients Can Tamper with the Owner Field

Common mistake:

```java
@PreFilter("filterObject.owner() == authentication.name")
public void approveOrders(List<OrderDto> submittedOrders) {
    // Use DTO records from the client to decide approval.
}
```

**This snippet only illustrates an anti-pattern**, lacks a complete `OrderDto` definition, and must never be implemented in production. If Alice submits a DTO for Bob's order with `owner="alice"`, the filter treats the object as Alice's. Therefore the runnable example in section 5 **takes IDs and queries the server-side repository**, never trusting an `owner` supplied in the request.

For order approval operations, a production API should fetch the real entity by ID, check principal/tenant/role/ownership from trusted sources, and update inside a transaction. Under concurrent updates, combining permission checks and conditional updates (e.g., `owner_id`/`tenant_id` predicates) is safer than two separate query-then-update steps.

### 7.2. Silent Filtering Can Violate Business Requirements

If a user submits `[1,2,3]` for a batch operation and the app silently drops ID 2, the caller may mistakenly believe all three were processed. Even without leaking data, this can be a **business integrity bug**. Choose an explicit contract:

- **Partial allowed:** process only valid IDs, return matching counts/mappings, and audit skipped items without leaking sensitive data.
- **Atomic reject:** if one ID is unauthorized, return 403/exception and **touch zero items**; use `@PreAuthorize` or a policy guard before mutating data.
- **Per-item errors:** return per-item status when the product genuinely requires it, without exposing the owner/title of items the user does not own.

`@PreFilter` by itself **does not** guarantee atomicity and does not choose response codes per product contract.

### 7.3. Post-Filtering Can Still Leak via Side Effects

Bad code:

```java
@PostFilter("filterObject.owner() == authentication.name")
public List<OrderView> visible() {
    List<OrderView> all = repository.findAll();
    sendNotificationsFor(all); // Side effect already ran before filtering!
    return all;
}
```

This example is an **illustrative anti-pattern**, not a standalone runnable class. `@PostFilter` filters **the return value** and cannot undo prior side effects. If the method logs payloads, calls third-party APIs, or writes data over `all`, unauthorized info may already be exposed before the annotation runs.

**Rule:** use repository queries already scoped by principal/tenant from the start, and enforce service policies at each action. `@PostFilter` is a defense-in-depth layer or convenience for small collections, never the sole data boundary.

### 7.4. `Page<T>` and Large Result Sets

`Page<OrderView>` carries metadata such as `totalElements`, `totalPages`, sorting, and offsets. Filtering contents only after querying lets page sizes and total counts leak other tenants' data or become inconsistent with reality; `@PostFilter` should also not be assumed to support arbitrary wrapper return types.

For pagination, place owner/tenant conditions directly in **SQL/JPQL/Specification**:

```sql
SELECT id, owner_id, tenant_id, title
FROM orders
WHERE owner_id = :authenticated_owner
  AND tenant_id = :authenticated_tenant
ORDER BY id
LIMIT :page_size OFFSET :offset;
```

This is a general SQL scoping example, not a query that solves every authorization concern on its own. Parameters must be bound safely; `authenticated_owner` and `authenticated_tenant` come from server-side authentication/policy, **never directly from the client**. `COUNT(*)` queries need the exact same predicates.

### 7.5. Ownership May Differ from Creator

Not every system uses `resource.owner == principal.name`. A document might be shared with a team, an account might delegate authority, or resources might belong to an organization rather than an individual. Real policies may evaluate:

- Owner ID, tenant ID, and resource status.
- Roles/permissions within the tenant.
- ACLs or owning-group membership.
- Delegation, approval, or time-bounded grant rules.
- **Service account** identity and explicit delegation scope.

When permissions depend on multiple sources, put the logic in a dedicated service/`AuthorizationManager` and test with a `principal × resource × action` matrix instead of writing long, hard-to-audit SpEL expressions in annotations.

## 8. Negative Tests That Cannot Be Skipped

### 8.1. Minimum Policy Matrix

| Caller | Input | Method | Expected Outcome |
| --- | --- | --- | --- |
| alice | IDs [1,3] | `keepOwnedIds` | Keeps [1,3] |
| alice | IDs [1,2,3] | `keepOwnedIds` | Only [1,3] (partial filtering) |
| alice | IDs [1,2,3] | `requireAllOwned` | Denies entire batch |
| alice | ID 2 | `getOwnedById` | AccessDenied/HTTP 403 |
| bob | ID 2 | `getOwnedById` | Allowed |
| bob | Full list | `visibleOrders` | Only ID 2 |
| Unauthenticated | GET /api/orders | HTTP | 401 in demo config |
| alice | Non-existent ID | `getOwnedById` | Denied per fail-closed policy |
| alice in tenant A | ID in tenant B with same username | Real protection | Denied |
| alice | Fake DTO `owner=alice`, Bob's ID | Server-source check | Not granted permission |
| alice | Immutable list containing foreign ID | `@PreFilter` | Verify contract/mutability, do not skip filter |

### 8.2. Tests Fail If Method Security Is Disabled

An important check in CI pipelines is that **tests fail when `@EnableMethodSecurity` is turned off**. Without advice, `visibleOrders()` would return Bob's order too, `keepOwnedIds` would keep ID 2, and `requireAllOwned` would not throw an exception.

This explains why using Mockito with `new OrderService(mockRepository)` to test Java logic **cannot test annotations**. Testing method security requires a **Spring `ApplicationContext`** and real bean proxies.

### 8.3. Self-Invocation and Non-Proxied Methods

```java
@Service
public class ExampleService {

    public void run() {
        // Internal call: may not pass through the method-security proxy.
        visibleOrders();
    }

    @PostFilter("filterObject.owner() == authentication.name")
    public List<OrderView> visibleOrders() {
        return List.of();
    }
}
```

This snippet illustrates the proxy problem; because it returns an immutable list when the filter needs to remove items, it also would not work as a real example. Do not use it as a template service; the complete service in section 5 returns an `ArrayList`.

When protecting business operations, place annotations on **public methods of a Spring-managed bean called from another bean**, and write tests proving calls pass through advice. Depending on proxy type and config, final/private methods or internal calls may not be intercepted as expected.

## 9. HTTP Permission Tests vs. Method Tests

Three test levels serve different goals:

| Level | Example | What It Catches | What It Does Not Prove |
| --- | --- | --- | --- |
| Converter/Policy unit | `OwnershipPolicy.isOwner(2L,"alice")` | Owner-matching logic against repo | Whether Spring AOP/advice runs |
| Method security integration | `@SpringBootTest`, `@WithMockUser`, calling service bean | `@PreFilter`, `@PostFilter`, `@PreAuthorize` take effect on method | Full HTTP filters, cookies, real JWTs |
| HTTP integration | `MockMvc` + Spring Security | 401/403/200, mapping/serialization does not leak records | DB RLS, real IdP token validation, production proxies |

If using a JWT Resource Server instead of the Basic demo, `@WithMockUser` sets a mock principal and does not test signature/audience/claim mapping. Add tests with JWTs signed by a test key or a controlled fake `JwtDecoder`, then verify authorities/subject/tenant match production format. **`with(jwt())` can bypass the real decoder** in `MockMvc`; do not mistake a passing test for verified token signing.

### 9.1. Testing Cross-Tenant Protection

If the application has multiple tenants, prepare at least two records with the same owner name in different tenants:

```text
id=41; owner=alex; tenant=tenant-a
id=42; owner=alex; tenant=tenant-b
```

For caller `alex@tenant-a`, expect only ID 41, never ID 42. The policy must resolve the tenant **from a valid `Authentication` or server-side membership**, never trusting an unverified `tenant` header. The simplified example in section 5 **does not implement** this tenant check; cross-tenant tests are mandatory before shipping a real multi-tenant service.

### 9.2. Testing Missing or Abnormal Data

- Inputs with `null`, negative IDs, non-existent IDs, duplicate IDs, empty lists.
- Client sending forged `owner`, `role`, or `tenantId` attempting bypass.
- Caller losing permissions between **check** and **update**.
- Locked/revoked user whose session/token is still valid.
- Multiple concurrent batch requests accessing the same resource.
- Repository/query returning only a subset; does `@PostFilter` still align with pagination?
- Filter removing all elements: should the response be an empty list or 403 per contract?
- Does `@PreFilter` with an unmodifiable collection throw an exception? If so, fix the data type/design rather than disabling method security.
- One service method calling an annotated service method internally: does it bypass the proxy?

Negative tests matter even more than testing "Alice sees Alice's orders", because IDOR vulnerabilities occur on **IDs belonging to other users or other tenants**.

## 10. Production Design: Filtering in SQL and Protecting Updates

In production, treat **security-constrained queries** as the primary defense for lists/pagination:

```java
// Illustrative interface; requires real Spring Data JPA, entity, and mapping.
Page<OrderEntity> findByOwnerIdAndTenantId(
    String ownerId,
    String tenantId,
    Pageable pageable
);
```

This is a **Spring Data repository snippet**, not standalone compilable code because `OrderEntity` and `Pageable` belong to a project with Spring Data JPA. `ownerId` and `tenantId` must come from the security principal/trusted membership.

For updates by ID, place the permission predicate directly in the SQL statement:

```sql
UPDATE orders
SET state = 'APPROVED'
WHERE id = :id
  AND owner_id = :authenticated_owner
  AND tenant_id = :authenticated_tenant
  AND state = 'PENDING';
```

Then inspect the **affected row count**; if 0, return the appropriate error (not found, forbidden, or invalid state per contract). This handles races better than an unconstrained `SELECT` followed by `UPDATE`. For complex domains, use transaction locks/versioning, database RLS, or centralized `AuthorizationManager` policies.

`@PreFilter`/`@PostFilter` still have a role in testing and guarding certain collections, yet **never replace** data access control: a request could hit another endpoint, an async task, or a repository directly. Enforce permissions at **every necessary point** (HTTP, service, DB) instead of relying on a single annotation.

## 11. Common Errors and Fixes

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `@PreFilter` does not filter anything | `@EnableMethodSecurity` not enabled, call bypasses proxy | Call Spring bean from another bean; test `ApplicationContext` |
| `@PostFilter` returns another user's data | Method not proxied, wrong owner expression, missing annotation | Test method directly via Spring bean and `MockMvc` response |
| Spring throws error while filtering list | Immutable list (`List.of`) or incompatible collection | Use mutable collection at filter boundary, or filter in query |
| SpEL cannot find bean `ownershipPolicy` | Missing `@Component` or mismatched bean name | Register bean and verify name in expression |
| SpEL `#ids` evaluates to null | Missing runtime parameter names / annotation support | Specify `filterTarget`; use `#p0` for positional method argument |
| Caller has no `Authentication` | Test lacks `@WithMockUser`, request unauthenticated | Set `SecurityContext` properly; do not disable advice |
| `@WithMockUser` test passes yet HTTP returns 403 | HTTP auth, CSRF, filter matcher, or JWT claims differ | Test with `MockMvc` and proper filter configuration |
| Right username yet wrong tenant | Policy does not constrain tenant | Read trusted tenant and check row-level match |
| User fakes owner in JSON to read/edit record | Policy trusts client DTO instead of repository | Verify ID, owner, and tenant on the server |
| Partial batch silently drops items | `@PreFilter` used for an atomic business operation | Use `@PreAuthorize` `allOwned` or fail-fast service guard |
| `Page` returned with wrong total count | Filtering after query instead of in `WHERE` | Filter in repository and matching count query |
| `@PostFilter` fails to stop side effects | Method ran before output was filtered | Guard before acting, using policy guard/query |
| Reading single object with `@PostFilter` | Wrong mechanism for non-collection | Use `@PreAuthorize` or `@PostAuthorize` per risk profile |
| Passes in tests without proxy | Test calls `new` class instead of bean | Integration test with Spring context to verify advice |
| `@PreFilter` hits DB per element slowly | Each ID triggers a lookup | Batch ownership query + combined guard |
| Same owner yet cross-tenant record leaks | Username not unique across tenants | Guard by subject + tenant/resource |
| `@PreAuthorize` allows yet update races | Permissions changed after check | Transaction/conditional `UPDATE`/optimistic locking |

## 12. A Small Java 17 Program to Contrast "Filtering" vs. "Denying"

This is a **plain Java example without Spring Security**. It only illustrates the difference between **filtering element-by-element** and **denying the entire set**; real implementations still require annotations/security proxies like the project in section 5.

File **`OwnershipRuleDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class OwnershipRuleDemo {
    public static void main(String[] args) {
        Map<Long, String> ownerById =
            Map.of(1L, "alice", 2L, "bob", 3L, "alice");

        List<Long> requested = List.of(1L, 2L, 3L);

        List<Long> filtered = requested.stream()
            .filter(id -> "alice".equals(ownerById.get(id)))
            .toList();

        boolean allOwned = requested.stream()
            .allMatch(id -> "alice".equals(ownerById.get(id)));

        System.out.println("requested=" + requested);
        System.out.println("filtered=" + filtered);
        System.out.println("strictAllowed=" + allOwned);
    }
}
```

Run:

```bash
javac OwnershipRuleDemo.java
java OwnershipRuleDemo
```

**Exact stdout:**

```text
requested=[1, 2, 3]
filtered=[1, 3]
strictAllowed=false
```

This simulates `@PreFilter` versus an atomic `allOwned` policy. Never copy this `Map.of` logic into production as a source of truth; owner maps and access rights must be verified against a database/authorization service.

## 13. Checklist Before Completing Method-Security Tests

- [ ] Enable `@EnableMethodSecurity` and verify service methods are invoked through Spring-managed proxies.
- [ ] Clearly distinguish **element filtering** (`@PreFilter`, `@PostFilter`) from **operation denial** (`@PreAuthorize`).
- [ ] SpEL expressions use `filterObject` of the right element type, `authentication` is the verified principal, and `filterTarget` names the right parameter.
- [ ] Never trust client-supplied `owner`/`tenantId`; verify IDs in the repository and use valid tenant claims/membership.
- [ ] For `@PreFilter`, ensure the collection is appropriately mutable rather than passing an immutable list that breaks filtering.
- [ ] For `@PostFilter`, ensure the method returns a compatible collection and performs no side effects or logging of unauthorized data.
- [ ] For large lists/pagination, use **repository queries filtered by owner/tenant** instead of load-all followed by post-filtering.
- [ ] For updates/sensitive data, enforce guards before side effects, with transactions and conditional updates.
- [ ] Test Alice and Bob, mixed IDs, forged owners, forbidden IDs, empty/missing IDs, unauthenticated callers, and cross-tenant cases.
- [ ] Test both the service proxy with `@WithMockUser` and HTTP `MockMvc`; never confuse mock authentication tests with real token verification.
- [ ] Assert 401/403/200 and verify others' data **never appears in JSON**, logs, counters, side effects, or exceptions.
- [ ] When using `@PostAuthorize`, analyze side effects that ran before the check; never use it to protect non-rollbackable writes.

**Conclusion:** `@PreFilter` only passes permitted elements into the method; `@PostFilter` only lets the caller see permitted elements in the returned result. Neither **automatically ensures a batch containing a foreign ID is rejected**, nor stops a service from querying another user's data before filtering. Proper tests must prove both **no leakage of other owners' data** and **no execution of unauthorized actions**, with policies checking owner/tenant from the server rather than client-declared fields.
