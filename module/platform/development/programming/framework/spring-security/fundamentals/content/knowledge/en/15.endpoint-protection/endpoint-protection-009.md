# Access Matrix by Endpoint, Identity, Role, and Action

> **Topic:** Endpoint protection — Spring Security fundamentals (Java 17+, Spring Security 6.x). This lesson guides you through turning business requirements into a **testable authorization matrix**, implementing control layers at HTTP endpoints and at the record/operation level; clearly distinguishing identity, role, authority, ownership conditions, tenant, data state, and action.

## 1. What Is an Access Matrix and What Problem Does It Solve?

An **access matrix** is a specification table: **who** can perform **which action** on **which resource**, under **what conditions**, with **allow or deny outcome**. When applied to APIs, a decision must evaluate simultaneously:

- **Endpoint:** HTTP method + path pattern, e.g., `GET /api/orders/{id}` differs from `PATCH /api/orders/{id}`. Query strings, request bodies, and route variables may carry business data requiring further verification.
- **Identity / principal:** the user or client calling the API, whether authenticated, which `userId`, which `tenantId`, and whether the account is still valid. Never treat a client-supplied `userId` string as a trusted identity.
- **Role:** a group of responsibilities such as `MEMBER`, `REVIEWER`, `ADMIN`. In Spring Security, by default `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority.
- **Specific permission (authority/permission):** capability to perform an operation, e.g., `order:read`, `order:create`, `order:update`, `order:approve`. `hasAuthority("order:read")` matches the exact string.
- **Action:** `READ`, `CREATE`, `UPDATE`, `APPROVE`, `DELETE`; on the same resource, each action has different conditions. HTTP verb mapping is a starting point, not the full business meaning.
- **Context/resource:** record owner, tenant, state `DRAFT`/`PENDING`/`APPROVED`, limits, data locks, delegation relationships, or independent approval authority.
- **Decision:** `ALLOW` or `DENY`, with **default deny when no rule matches**; missing data, non-existent resources, and inability to load policy should also be defined.

Mental formula:

```text
Decision = Policy(
    trusted identity,
    roles + authorities,
    HTTP method + route,
    business action,
    resource owner + tenant + state,
    relevant conditions
)

ALLOW only when all required conditions are satisfied.
No matching rule or insufficient data → DENY.
```

The matrix lets designers, controller/service authors, permission administrators, and testers read **a single business policy** together. It prevents two common mistakes: checking only "logged in" and letting users edit any record; or locking an endpoint by role while forgetting that users with that role still must not act on another tenant's data.

## 2. Distinguishing Identity, Role, Authority, and Object-Level Permissions

| Concept | Example | Meaning | What should NOT be inferred |
|---|---|---|---|
| Identity | `alice`, `tenant=A` | Who is making the request | Parameter `?user=alice` is the identity |
| Authentication | Valid `Authentication` | Authentication result from a trusted mechanism | Logged in means having all permissions |
| Role | `ROLE_REVIEWER` | Responsibility of the actor | Reviewer can approve any order |
| Authority | `order:approve` | Specific capability | Having this permission allows approving orders in another tenant |
| Ownership | `order.ownerId == alice.id` | Relationship to a record | Owner can perform every action |
| Tenant scope | `order.tenantId == principal.tenantId` | Organizational boundary | ADMIN implicitly crosses all tenants |
| Resource state | `PENDING`, `DRAFT` | Business condition | Having UPDATE permission allows editing approved orders |
| Action | `APPROVE`, `UPDATE` | Intended effect on resource | Every `POST` means CREATE |

Roles are usually mapped into a set of authorities at login or token conversion. Spring Security does not automatically treat every JWT claim as a role/permission: you must configure a mapper/converter to create `GrantedAuthority` instances following convention. With resource server tokens, scopes may be mapped to authorities like `SCOPE_...`; **do not assume** `roles` or `permissions` claims automatically become `ROLE_ADMIN` or `order:read` unless configured.

**RBAC (role-based access control)** addresses role-based policies. **ABAC (attribute-based access control)** adds attributes such as owner, tenant, state, and access time. Permissions on a specific object usually combine both: role/authority at the route level, then owner/tenant/state checks in the service or a dedicated policy.

## 3. Sample Scenario: Multi-Tenant Order Management System

Suppose an order management system has two tenants `A` and `B`. Each authenticated request carries a trusted identity and tenant from a user store/session or verified token. Actor roles and authorities are defined as:

| Actor | Identity/tenant | Role | Authority |
|---|---|---|---|
| Unauthenticated guest | `anonymous` | none | none |
| Alice | `alice / A` | `ROLE_MEMBER` | `order:read`, `order:create`, `order:update` |
| Bob | `bob / A` | `ROLE_MEMBER` | `order:read`, `order:create`, `order:update` |
| Ray | `ray / A` | `ROLE_REVIEWER` | `order:read`, `order:approve` |
| Ada | `ada / A` | `ROLE_ADMIN` | `order:read`, `order:create`, `order:update`, `order:approve`, `order:delete` |
| Mai | `mai / B` | `ROLE_MEMBER` | `order:read`, `order:create`, `order:update` |

**These are business assumptions of the example**, not a set of roles Spring Security creates automatically. Define three additional records:

| Order | Owner | Tenant | Status |
|---|---|---|---|
| `101` | `alice` | `A` | `DRAFT` |
| `102` | `bob` | `A` | `PENDING` |
| `201` | `mai` | `B` | `DRAFT` |

Example policy:

- Everyone can call `GET /public/ping` and `GET /api/catalog`.
- Members with `order:read` can **view their own orders** within the same tenant. Reviewers with `order:read` can view orders in the same tenant to process them; admins in the same tenant can view orders by administrative privilege. No access to other tenants' data just for holding the ADMIN role.
- Users with `order:create` can create new orders in their own tenant; the backend must **derive owner/tenant from the identity**, never trusting `ownerId`/`tenantId` in client-sent JSON.
- The member owning the order or an admin in the same tenant with `order:update` can edit it while `DRAFT`. Once moved to `PENDING`, it cannot be edited via this action.
- A reviewer or admin in the same tenant with `order:approve` can approve a `PENDING` order, **and may not self-approve an order they own**.
- Only an admin in the same tenant with `order:delete` can delete a `DRAFT` order; deleting submitted/approved orders must follow a separate workflow if business needs it.
- Only role `ADMIN` views the administrative endpoint `GET /api/admin/audit`; audit query results are still scoped to Ada's tenant `A` in the example.
- All unlisted endpoints/methods are denied via `denyAll`.

## 4. Matrix of Endpoint × Action × Condition

This is the **canonical policy matrix** used for review and writing tests. The "HTTP gate" column is the baseline check in the filter chain; the "Business gate" column must be checked in the service/policy when real data is loaded.

| HTTP endpoint | Action | HTTP gate | Business gate before execution | If unsatisfied |
|---|---|---|---|---|
| `GET /public/ping` | PUBLIC_READ | `permitAll` | None | Denied only if another mechanism requires it |
| `GET /api/catalog` | PUBLIC_READ | `permitAll` | None | Denied only if another mechanism requires it |
| `GET /api/orders/{id}` | READ | `order:read` | Same tenant; owner or REVIEWER or ADMIN | DENY |
| `POST /api/orders` | CREATE | `order:create` | Owner = caller; tenant = caller's tenant | DENY |
| `PATCH /api/orders/{id}` | UPDATE | `order:update` | Same tenant; `DRAFT`; owner or ADMIN | DENY |
| `POST /api/orders/{id}/approve` | APPROVE | `order:approve` | Same tenant; `PENDING`; REVIEWER or ADMIN; no self-approval | DENY |
| `DELETE /api/orders/{id}` | DELETE | `order:delete` | Same tenant; `DRAFT`; ADMIN | DENY |
| `GET /api/admin/audit` | AUDIT_READ | `ROLE_ADMIN` | Results filtered to caller's tenant | DENY |
| Other endpoints/methods | UNKNOWN | `denyAll` | Business logic does not run | DENY |

**Important:** For READ, UPDATE, APPROVE, and DELETE rows, checking the authority on the route **is not enough for a complete ALLOW**. Only after loading the record and verifying owner/tenant/state does the service permit execution. Missing data needed for a decision must be handled deliberately; never default to allow when querying owner/tenant fails.

`POST /api/orders/{id}/approve` uses HTTP `POST`, yet the business action is **APPROVE**, not CREATE. Thus, derive the action from the route specification rather than blindly mapping "POST = CREATE."

## 5. Matrix of Actor × Resource × Action: Expected Outcomes

Assume tokens, authentication, and other protection layers are valid; for state-changing requests from browsers, a valid CSRF token is provided when configured. The table below describes **authorization outcomes**, without promising every HTTP response is 200.

| Actor | Request / order | Authorization outcome | Why |
|---|---|---|---|
| Anonymous | `GET /api/catalog` | ALLOW | Public endpoint |
| Anonymous | `GET /api/orders/101` | DENY | Unauthenticated / lacks `order:read` |
| Alice | `GET /api/orders/101` | ALLOW | Owner, tenant A, has `order:read` |
| Alice | `GET /api/orders/102` | DENY | Not owner, and neither REVIEWER nor ADMIN |
| Bob | `GET /api/orders/102` | ALLOW | Owner in same tenant and has `order:read` |
| Ray | `GET /api/orders/102` | ALLOW | Reviewer in same tenant with `order:read` |
| Ray | `PATCH /api/orders/102` | DENY | Lacks `order:update`; order is also not in `DRAFT` |
| Alice | `PATCH /api/orders/101` | ALLOW | Owner, same tenant, `DRAFT`, has `order:update` |
| Alice | `PATCH /api/orders/102` | DENY | Not owner and order is `PENDING` |
| Ray | `POST /api/orders/102/approve` | ALLOW | Reviewer in same tenant, `PENDING`, not self-approval |
| Ray | `POST /api/orders/101/approve` | DENY | Not in `PENDING` yet |
| Alice | `POST /api/orders/102/approve` | DENY | Lacks approve authority |
| Ada | `DELETE /api/orders/101` | ALLOW | ADMIN in same tenant, has `order:delete`, order is `DRAFT` |
| Ada | `DELETE /api/orders/102` | DENY | Order is already `PENDING` |
| Ada | `GET /api/orders/201` | DENY | Tenant A ADMIN cannot cross into tenant B |
| Mai | `GET /api/orders/201` | ALLOW | Owner, tenant B, has `order:read` |
| Ada | `GET /api/admin/audit` | ALLOW | ROLE_ADMIN, returned data scoped to tenant A |
| Alice | `GET /api/admin/audit` | DENY | Lacks ROLE_ADMIN |
| Ada | `DELETE /api/catalog` | DENY | Method/endpoint not declared |

The same identity can receive ALLOW for `GET` yet DENY for `PATCH` or `APPROVE`. The same role can receive ALLOW on order 101 yet DENY on order 201 due to a different **tenant**. Negative cases (DENY) are just as valuable to test as ALLOW cases.

## 6. Turning the Matrix into Ordered Decision Rules

For each request, separate two "gates":

```text
1. Request → determine the applicable security filter chain
2. Authentication → build trusted identity + GrantedAuthority set
3. HTTP rule → are method + path allowed into this action?
4. Load resource (if the action requires a record)
5. Resource policy → tenant + owner + role + permission + state
6. ALLOW → execute business logic; DENY → stop
```

If a rule requires conditions **simultaneously**, combine them with AND logic:

```text
allowUpdate(actor, order) =
    actor is authenticated
    AND actor has "order:update"
    AND actor.tenantId == order.tenantId
    AND order.status == DRAFT
    AND (actor.id == order.ownerId OR actor has ROLE_ADMIN)

allowApprove(actor, order) =
    actor is authenticated
    AND actor has "order:approve"
    AND actor.tenantId == order.tenantId
    AND order.status == PENDING
    AND (ROLE_REVIEWER OR ROLE_ADMIN)
    AND actor.id != order.ownerId
```

Do not confuse `(isOwner OR isAdmin)` with `isOwner OR (isAdmin AND sameTenant)`. The latter could let an owner with an unusual role/identity cross tenant boundaries. Keep `sameTenant` outside the OR group so it applies to **all branches**.

If there is an "ADMIN may bypass tenant" rule, that is a high-risk cross-organization privilege; it must be specified separately, audited, and tested, never inferred from the role name alone.

### 6.1. Matcher Order

Inside a security filter chain, authorization DSLs normally evaluate matchers in declaration order and apply the **first matching rule**. Specific cases must precede `anyRequest()`/`anyExchange()`. For example, placing `requestMatchers("/**").permitAll()` before admin routes renders later rules ineffective.

**Selecting a chain** is a different step from **selecting a rule inside a chain**. A `SecurityFilterChain` matching only `/api/**` does not protect paths outside that scope; when multiple chains exist, review `securityMatcher`, `@Order`, and the fallback chain. Do not confuse a narrow chain's `anyRequest().denyAll()` with "denying the entire application."

### 6.2. Never Derive Permissions from Client-Editable Data

Do not trust `X-Tenant-Id`, `?userId=alice`, or `ownerId` in JSON as proof of permission. They can only serve as input parameters/identifiers to be checked against the authenticated identity and trusted data store. If the request body carries `tenantId=B` while a valid token carries tenant A, the backend must never silently operate on tenant B's data.

## 7. Servlet Spring Security Example: Protecting the HTTP "Gate"

Below is a **complete configuration class** for a Spring Boot **MVC/Servlet** app, Java 17+, Spring Security 6.x. Place it in `ServletAccessSecurityConfig.java` inside an application package with `spring-boot-starter-web` and `spring-boot-starter-security`. Users and authorities must be supplied by application authentication; this class only configures the **HTTP gate**, without performing owner/tenant/state checks yet.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletAccessSecurityConfig {

    @Bean
    SecurityFilterChain accessSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/public/ping", "/api/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST,
                        "/api/orders/*/approve")
                    .hasAuthority("order:approve")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("order:create")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("order:update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("order:delete")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Reading the configuration class:**

- `requestMatchers(HttpMethod.GET, ...)` separates GET from PATCH/DELETE on the same URL group. Because there is no rule for `DELETE /api/catalog`, it falls into `denyAll`.
- `.hasRole("ADMIN")` checks `ROLE_ADMIN` per the default prefix; `.hasAuthority("order:approve")` checks the exact permission string.
- `.anyRequest().denyAll()` ensures unmodeled routes/methods are not accidentally opened.
- `.httpBasic(...)` provides an example authentication entry point. Real applications may use session login or a JWT resource server instead of Basic. To evaluate the matrix, configure your user store/token-to-authority mapping to match the actor table.
- `POST`, `PATCH`, and `DELETE` can still be blocked by **CSRF** if CSRF is enabled. Granting permission at the authorization gate does not bypass CSRF; design CSRF according to how clients authenticate (session/cookie vs. stateless bearer).
- `/api/orders/**` still matches extra path segments depending on the matcher; this HTTP layer **does not yet know** whether the order ID exists or which tenant it belongs to. To protect objects, a resource policy is required behind it.

This is a policy-based authorization example for study, not a complete production API design. When mixing Servlet MVC and WebFlux dependencies in the same project, never arbitrarily register both kinds of security chains as if they share one web runtime.

## 8. WebFlux Example: Same Matrix, Different Reactive DSL

A **Spring WebFlux** application uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `authorizeExchange`. The `ReactiveAccessSecurityConfig.java` class below belongs in a **separate application** with `spring-boot-starter-webflux` and `spring-boot-starter-security`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveAccessSecurityConfig {

    @Bean
    SecurityWebFilterChain accessSecurityWebFilterChain(ServerHttpSecurity http) {
        http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET,
                        "/public/ping", "/api/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST,
                        "/api/orders/*/approve")
                    .hasAuthority("order:approve")
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("order:create")
                .pathMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("order:update")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("order:delete")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

These two configuration classes express the **same HTTP gate intent**, yet their builders/beans/matchers are not interchangeable:

| Servlet/MVC | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` | `pathMatchers` |
| `anyRequest()` | `anyExchange()` |
| `HttpServletRequest` | `ServerWebExchange` |
| `SecurityContextHolder` in Servlet | `ReactiveSecurityContextHolder` via Reactor Context |

In WebFlux, asynchronous policies must compose with `Mono`/`Flux`; do not call `block()` to wait for the database and do not `subscribe()` manually for "background permission checks." The check result must stay inside the Publisher awaited by the HTTP request to preserve ordering, errors, cancellation, and security context.

**Limitation of both examples:** `order:read` on the route does not imply permission to view every order. It only lets the request past the first gate; **a resource policy must be invoked** when handling records.

## 9. Representing the Resource Policy as Standalone Runnable Java 17

To see how a matrix turns into deterministic decisions, part of the business policy can be modeled in plain Java without Spring. **`AccessMatrixDemo.java`** below illustrates READ, UPDATE, APPROVE, and DELETE. This is a teaching model; real applications must use authenticated identities and order data from trusted sources.

```java
import java.util.Set;

public class AccessMatrixDemo {

    record Actor(String id, String tenant, Set<String> authorities) {}
    record Order(String owner, String tenant, String status) {}

    enum Action { READ, UPDATE, APPROVE, DELETE }

    static boolean allowed(Actor actor, Action action, Order order) {
        if (actor == null || order == null) {
            return false;
        }
        if (!actor.tenant().equals(order.tenant())) {
            return false; // Even ADMIN cannot cross tenants.
        }

        boolean owner = actor.id().equals(order.owner());
        boolean admin = actor.authorities().contains("ROLE_ADMIN");
        boolean reviewer = actor.authorities().contains("ROLE_REVIEWER");

        return switch (action) {
            case READ ->
                actor.authorities().contains("order:read")
                    && (owner || reviewer || admin);

            case UPDATE ->
                actor.authorities().contains("order:update")
                    && order.status().equals("DRAFT")
                    && (owner || admin);

            case APPROVE ->
                actor.authorities().contains("order:approve")
                    && order.status().equals("PENDING")
                    && (reviewer || admin)
                    && !owner;

            case DELETE ->
                actor.authorities().contains("order:delete")
                    && order.status().equals("DRAFT")
                    && admin;
        };
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "A", Set.of(
            "ROLE_MEMBER", "order:read", "order:create", "order:update"
        ));
        Actor ray = new Actor("ray", "A", Set.of(
            "ROLE_REVIEWER", "order:read", "order:approve"
        ));
        Actor ada = new Actor("ada", "A", Set.of(
            "ROLE_ADMIN", "order:read", "order:create",
            "order:update", "order:approve", "order:delete"
        ));
        Order order101 = new Order("alice", "A", "DRAFT");
        Order order102 = new Order("bob", "A", "PENDING");
        Order order201 = new Order("mai", "B", "DRAFT");

        System.out.println("Alice READ #101: "
            + allowed(alice, Action.READ, order101));
        System.out.println("Alice READ #102: "
            + allowed(alice, Action.READ, order102));
        System.out.println("Ray READ #102: "
            + allowed(ray, Action.READ, order102));
        System.out.println("Ray APPROVE #102: "
            + allowed(ray, Action.APPROVE, order102));
        System.out.println("Ada DELETE #101: "
            + allowed(ada, Action.DELETE, order101));
        System.out.println("Ada READ #201: "
            + allowed(ada, Action.READ, order201));
    }
}
```

Compile and run on **JDK 17+**:

```bash
javac AccessMatrixDemo.java
java AccessMatrixDemo
```

Expected standard output for the exact class above:

```text
Alice READ #101: true
Alice READ #102: false
Ray READ #102: true
Ray APPROVE #102: true
Ada DELETE #101: true
Ada READ #201: false
```

Lessons from the example:

1. Having `ROLE_ADMIN` alone is **not** enough to cross `tenant`, because the tenant check runs before every action.
2. `READ` allows owner, reviewer, or admin in the same tenant; `UPDATE` also requires `DRAFT`; `APPROVE` requires `PENDING` and no self-approval.
3. `Set<String> authorities` holds both role-prefixed authorities (`ROLE_...`) and business permissions. In Spring Security, this set comes from authentication/mapping, never directly from the request body.
4. The plain Java class illustrates **resource-level policy**; it does not handle HTTP authentication, CSRF, database loading, status mapping, or race conditions if an order changes state between check and write.

## 10. Where Should Checks Live So the Matrix Takes Effect?

### 10.1. HTTP Gate: Coarse Filtering by Action/Permission

The filter chain can reject requests missing an authority early—for example, a user without `order:update` cannot touch `PATCH /api/orders/{id}`. However, the filter **does not know** whether the order is `DRAFT` or who owns it. That is why a policy layer at the service level, where real order data is available, is required.

### 10.2. Service Gate: Checking Tenant, Owner, and State Before Acting

Example **excerpt** from a service in a Servlet/MVC application (`OrderEntity`, `OrderRepository`, `OrderDto`, and `OrderPolicy` are application-defined types; the excerpt is not a standalone class):

```java
public OrderDto updateOrder(
        long orderId,
        UpdateOrderCommand command,
        Authentication authentication) {

    OrderEntity order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    if (!orderPolicy.canUpdate(authentication, order)) {
        throw new AccessDeniedException("Not allowed to update order");
    }

    order.applyAllowedChanges(command);
    return toDto(orderRepository.save(order));
}
```

Here `canUpdate` must verify **order:update + tenant + (owner or ADMIN) + DRAFT** per the agreed table. Returning 404 vs. 403 for records outside a tenant is a choice to prevent information leakage that requires a consistent policy; never return record details before permissions are verified.

**Race condition / TOCTOU note:** if an order changes from `DRAFT` to `APPROVED` between read and save, the initial check is no longer sufficient. For critical actions, use transactions/locking/optimistic versioning or conditional updates directly in the database (e.g., `WHERE tenant_id = ? AND status = 'DRAFT' AND version = ?`) and verify the updated row count. Do not treat an in-memory `if` as the final guarantee under concurrent requests.

### 10.3. Reactive Service Gate: Composing Publishers, Preserving Identity

In WebFlux, asynchronous record-access logic must stay inside a Publisher. Illustrative excerpt using `reactiveOrderRepository.findById` returning `Mono<OrderEntity>` and `orderPolicy.canRead` as a fast synchronous check on already-loaded values:

```java
return reactiveOrderRepository.findById(orderId)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)))
    .flatMap(order ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(authentication -> {
                if (!orderPolicy.canRead(authentication, order)) {
                    return Mono.error(
                        new AccessDeniedException("Forbidden"));
                }
                return Mono.just(toDto(order));
            })
    );
```

Types and imports in the excerpt: Reactor's `Mono`, plus Spring's `ReactiveSecurityContextHolder`, `SecurityContext`, `AccessDeniedException`, `ResponseStatusException`, and `HttpStatus`. If permission evaluation also needs to call another data store, `orderPolicy` should return `Mono<Boolean>` to compose with `flatMap`; never `block()` or `subscribe()` manually inside a security chain.

### 10.4. Method Security Adds a Safety Layer When Services Are Called Elsewhere

- In Servlet, enable `@EnableMethodSecurity` and use `@PreAuthorize`/`@PostAuthorize` where conditions fit. For instance, `@PreAuthorize("hasAuthority('order:read')")` restricts a method to callers with the permission; concrete owner/tenant checks still must run where the resource is available.
- In Reactive, use `@EnableReactiveMethodSecurity` (matching your Spring Security version configuration); checks integrate with Reactor `Context`. Methods/services returning `Mono`/`Flux` must preserve the subscription context.
- An unannotated service does not automatically become safe just by enabling method security. HTTP catch-alls are still needed; non-HTTP entry points (message consumers, scheduled jobs) need their own access rules.
- Do not hide an essential check solely inside a controller; if the same service is called by batch jobs, event listeners, or another API, it can bypass that controller. Placing policies in the service or a reusable domain/authorization layer prevents permission drift across entry points.

## 11. Turning Each Matrix Row into Tests

For each rule, test at minimum **one allowed case and one denied case**, then add context branches. Test data should instantiate **specific** actors and orders 101/102/201; avoid using an all-powerful token as the default test fixture.

Example flow-based test suite:

| Group | Case to verify | What it proves |
|---|---|---|
| Public | Anonymous GET catalog → allowed | `permitAll` properly scoped |
| Authentication | Anonymous GET order → denied | Route is not public |
| Authority | Alice PATCH own DRAFT allowed; Ray PATCH denied | `order:update` enforced |
| Role | Ada views audit; Alice denied | `ROLE_ADMIN` works |
| Ownership | Alice GET own 101, cannot GET Bob's 102 | IDOR/BOLA blocked |
| Tenant isolation | Ada (tenant A) cannot GET order 201 (tenant B) | ADMIN does not cross tenants |
| Resource state | Alice PATCH DRAFT allowed, PENDING denied | State condition enforced |
| Separation of duties | Reviewer cannot self-approve own order | Self-approval blocked |
| Action mapping | Ray APPROVE PENDING allowed, UPDATE denied | APPROVE distinguished from UPDATE |
| Unknown route/method | DELETE catalog, PATCH audit → denied | Catch-all works |
| CSRF | Browser session POST/PATCH with/without token | CSRF distinguished from permission |
| Concurrency | Two requests concurrently changing state/version | Policy not bypassed via race condition |

**With Spring MVC:** use `MockMvc` and `spring-security-test`, supporting `with(user(...))` and `with(csrf())`; with Spring WebFlux, use `WebTestClient` and configurers such as `mockUser()` and `csrf()`. When testing tenant/owner, build a custom principal or authentication fixture with the right tenant—merely mocking a role with `mockUser("alice")` is insufficient to prove owner policies.

MVC excerpt for the route layer assuming a matching test endpoint exists (not a standalone test class):

```java
mockMvc.perform(get("/api/orders/101")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("order:read"))))
    .andExpect(status().isOk());
```

To test the owner/tenant layer, the service fixture must know `alice` belongs to tenant A and order 101 belongs to alice and A; without that fixture, you only prove the route gate. For POST/PATCH/DELETE requests when CSRF is enabled, pass `with(csrf())` when testing business authorization, plus a separate test confirming missing CSRF is blocked.

WebFlux excerpt illustrating the route gate:

```java
webTestClient
    .mutateWith(mockUser("ray").authorities(
        new SimpleGrantedAuthority("order:approve")))
    .post().uri("/api/orders/102/approve")
    .exchange()
    .expectStatus().is2xxSuccessful();
```

The snippet above assumes `WebTestClient`, the endpoint, test authentication fixture, and CSRF are configured appropriately; it does not mean Spring Security automatically knows order 102 is `PENDING`. Under default CSRF configuration, a POST request may require `mutateWith(csrf())`. If the endpoint returns a different 2xx code in real business logic, adjust the assertion to match the contract. Complete tests must verify that **denial produces no side effects** (order unchanged, no wrong approval audit created, no event published). A 403 response where data still gets updated remains a critical bug.

Keep the matrix in YAML/CSV or code fixtures so tests can generate cases. Example YAML specifying a few cases (illustrative schema, not a format consumed directly by Spring Security):

```yaml
cases:
  - actor: alice
    tenant: A
    method: GET
    path: /api/orders/101
    expected: ALLOW
  - actor: alice
    tenant: A
    method: GET
    path: /api/orders/102
    expected: DENY
  - actor: ada
    tenant: A
    method: GET
    path: /api/orders/201
    expected: DENY
  - actor: ray
    tenant: A
    method: POST
    path: /api/orders/102/approve
    expected: ALLOW
```

Every runnable test case needs mapping to a user/tenant/order fixture and an expected HTTP response matching the auth mechanism (401, 403, redirect, or 404 when hiding resource existence). Do not equate `DENY` in the matrix with a single immutable HTTP status code.

## 12. Denial Outcomes and Other Protection Layers

**401 Unauthorized** is usually returned when a request lacks valid authentication under mechanisms like HTTP Basic/JWT; **403 Forbidden** usually occurs when authenticated but lacking permission, or rejected by CSRF. With form login, it may redirect to the login page. `404 Not Found` may be chosen for out-of-scope resources to avoid leaking existence, provided there is a consistent policy. Spring Security also handles entry points, exception translation, and CSRF; therefore never infer authorization solely from status codes while ignoring logs and fixtures.

Across different web stacks:

- **Servlet/MVC:** `authorizeHttpRequests` checks in the filter chain; method security via `@EnableMethodSecurity`; watch Servlet `FORWARD`/`ERROR` dispatches when error pages exist. Paths and methods must be tested against actual request matchers.
- **WebFlux:** `authorizeExchange` checks on `ServerWebExchange`; receives identity via Reactor context; custom policies must never call `block()`/`subscribe()`.
- **Multiple chains:** Matchers selecting `SecurityFilterChain`/`SecurityWebFilterChain` differ from matchers selecting rules inside a chain. Do not let paths matching no chain become a protection gap.
- **JWT OAuth2:** If using scopes/claims as authorities, mappers must define exact prefixes/formats; an actor with scope `SCOPE_order.read` does not implicitly have `order:read`. The matrix must specify the exact authority string Spring Security checks.

## 13. Common Matrix Design Mistakes

1. **Listing only roles per endpoint** without HTTP method, owner, tenant, or state → prone to IDOR/BOLA and action-level privilege escalation.
2. **Assuming ADMIN role is implicitly system-wide** → cross-tenant data leaks. Explicitly specify global permissions if genuinely intended.
3. **Defaulting to ALLOW** on new routes, undefined actions, null owners, or empty policy service results → new endpoints open themselves.
4. **Using `hasRole` with mismatched authorities:** `hasRole("ADMIN")` usually checks `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` checks exact `ADMIN`. Never mix conventions carelessly.
5. **Treating query/body/HTTP headers as trusted tenant or owner** → callers can swap object IDs to access others' data.
6. **Blocking only in the UI** (hiding Approve/Delete buttons) → attackers still send direct HTTP requests.
7. **Blocking only in the controller** → services invoked from other entry points may lack policy enforcement.
8. **Putting an overly broad rule first** like `/**.permitAll()` or omitting a catch-all → specific rules lose effect.
9. **Checking first and updating later without concurrency protection** → order state changes between check and write, causing improper approval/edit.
10. **Skipping negative tests:** having a few 2xx tests for admin without tests for under-privileged users, wrong tenant, wrong status, or wrong HTTP method.
11. **Relying on a single status code as sole proof:** missing CSRF, unauthenticated access, missing handlers, and deny policies can produce different responses.
12. **Copying rules between Servlet/WebFlux by renaming methods** while ignoring chain types, matchers, context, and reactive requirements.
13. **Not tracking permission changes:** adding `EXPORT`/`REFUND`/`CANCEL` actions without updating the matrix and tests leaves missing rules or broken consistency.
14. **Unclear audit rules:** who views logs, which tenant's logs, and what sensitive data is logged; ADMIN role does not remove the duty to protect sensitive data in logs.

## 14. Implementing and Maintaining the Matrix in a Real Project

1. **Inventory endpoints** by method + route; record business action, resource, resource ID, and owner.
2. **Lock the identity contract**: `userId`, `tenantId`, roles, and authorities come from trusted authentication; permission naming conventions are published consistently.
3. **Fill in both policy layers**: HTTP gate to block early, resource gate to check tenant/owner/state; specify handling for missing data and errors.
4. **Enforce default deny** and matcher order; verify every route is governed by an appropriate security chain.
5. **Generate test fixtures from the matrix** for anonymous, member, reviewer, admin, multiple tenants, and data states. Each ALLOW has its nearest DENY variants.
6. **Review concurrency, transactions, and side effects** on state-changing actions; verify audits/events fire only when permitted.
7. **Document response behavior**: 401/403/404/redirect, CSRF, logging, and how to avoid data leaks in errors.
8. **Keep synchronized with API changes**: PRs adding endpoints/actions must add or update matrix rows, policies, and tests; avoid documentation tables drifting from code.
9. **Review high privileges**: ADMIN, super-admin, cross-tenant support, and destructive actions require strict oversight under least privilege.

## 15. Self-Check Questions

**Question 1.** Alice has `order:read` and `ROLE_MEMBER` and tries `GET /api/orders/102` (owned by Bob, same tenant). Is it allowed?

**Answer:** No. The request passes the HTTP gate because she has the authority, but the resource gate denies it because Alice is neither the owner nor REVIEWER/ADMIN. The matrix must enforce both layers.

**Question 2.** Ada is ADMIN for tenant A and wants to view order 201 in tenant B. Is the ADMIN role enough?

**Answer:** No. The example policy requires `actor.tenantId == order.tenantId` for every actor, including ADMIN. Cross-tenant access requires an explicit separate policy if business genuinely permits it.

**Question 3.** Ray has `order:approve` and wants to approve order 101, which is in `DRAFT`. Does the HTTP layer let it pass, and what is the final result?

**Answer:** The HTTP gate may pass based on authority, but the resource policy denies because the order is not `PENDING`. The approval action must not execute.

**Question 4.** The API just added `POST /api/orders/{id}/cancel`. What happens if no rule or action is declared?

**Answer:** Under the `denyAll` catch-all, the new route is denied until the CANCEL action, role/permission, state/owner/tenant conditions, and tests are specified. This is safe behavior.

**Question 5.** After adding `@EnableMethodSecurity`, are all services automatically protected?

**Answer:** No. Only methods/classes carrying properly declared method-security rules have enforcement at that level. You still must design the HTTP gate and service policies; unannotated methods may not be blocked by method security.

## 16. References

- [Spring Security – Servlet: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet: Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [OWASP – API Security Top 10: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)

**Key takeaway:** A solid access matrix simultaneously answers **which endpoint, who is calling, with what authorities, performing which action on which record, in which tenant and state**. `permitAll`, `hasRole`, `hasAuthority`, and `denyAll` are only the HTTP control gate; correctness of authorization also depends on service policies over owner/tenant/state and an ALLOW/DENY test suite covering all cases.