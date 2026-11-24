# Object-Level Authorization, Ownership, and Tenant Isolation in Spring Boot Security Testing

## 1. Why is checking roles alone not enough?

In a multi-tenant SaaS application, a user may have permission to call `GET /api/orders/{id}` yet **must not be allowed to view every order with a valid ID**. User Alice in tenant A may read orders owned by Alice; Bob in the same tenant A may be barred from viewing Alice's private orders; Mallory in tenant B must definitely never view tenant A's orders; and an administrator for **tenant A** may view Alice's and Bob's orders yet **must not cross over into tenant B**.

If an application writes only:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public OrderView get(long orderId) {
    return repository.findById(orderId).orElseThrow();
}
~~~

then anyone holding `ORDER_READ` can try substituting `{id}` in the URL to view someone else's resources. That is **Broken Object Level Authorization (BOLA)**, often referred to as **IDOR (Insecure Direct Object Reference)**. API IDs can be auto-increment integers, UUIDs, or unpredictable strings: **unpredictable IDs do not replace authorization**.

**Main topic:** “Object-level authorization, ownership, and tenant isolation”, under **Security** in Spring Boot testing. The focus goes beyond role-based access control (RBAC) to **access decisions over specific records and verified identities**, proven with both positive and negative test cases.

**Target outcomes:**

1. Distinguish **authentication**, **function-level authorization**, **object-level authorization**, **ownership**, and **tenant isolation**.
2. Draft a clear permission matrix across **tenant + owner + authority + operation** before writing code.
3. Understand why IDs, `X-Tenant-Id`, and `ownerId` in request bodies or query params are all **untrusted input** unless checked against trusted identity/claims.
4. Use **`SecurityFilterChain`, `@EnableMethodSecurity`, and `@PreAuthorize`** in Spring Boot 3.3.5.
5. Keep object-level permissions inside **service policy** and scope queries via a **tenant-aware repository**, not just in controllers.
6. Test **same tenant, different owner**, **cross-tenant**, **tenant admin within own tenant**, and **tenant admin across tenants**.
7. Test `GET` single object, `GET` list, `PATCH` mutation, missing permissions, unauthenticated requests, and CSRF.
8. Use **`MockMvc` + `spring-security-test`** with a custom `UserDetails` carrying a trusted `tenantId`, rather than accepting tenant from an HTTP header.
9. Distinguish `401`, `403`, and `404` per policy and prevent cross-tenant object existence leaks.
10. Test **mass assignment**: client JSON supplying `ownerId` or `tenantId` must never transfer ownership.
11. Build a **Java 17 / Spring Boot 3.3.5 / Gradle** example runnable with `@SpringBootTest` + `@AutoConfigureMockMvc`, containing **21 JUnit Jupiter `@Test` methods**.
12. Understand the limits of an in-memory repository and upgrade to **JDBC/JPA tenant predicates, PostgreSQL RLS, database integration tests, and transaction/TOCTOU controls**.
13. Know why permissions must be checked across **every object access path**: detail, list, update, delete, export, batch, async jobs, file downloads, and subresources.

**Fixed versions:** Java 17, Spring Boot **3.3.5**, Spring Security **6.3.x** under Boot 3.3 dependency management, JUnit Jupiter, and Spring MVC MockMvc. The sample uses in-memory data to clarify policy, **not as proof that a production database is isolated**. Later SQL/RLS sections specify the additional verification layers.

## 2. Definitions: how does authentication differ from authorization?

| Concept | Question it must answer | Example |
|---|---|---|
| **Authentication** | Who is sending the request? Is the identity verified? | Principal is Alice, `userId=alice`, `tenantId=tenant-a` |
| **Function-level authorization** | May the principal perform this action? | Needs `ORDER_READ` to call read/list |
| **Object-level authorization** | For a **specific record**, may the principal access it? | Alice cannot open Bob's order |
| **Ownership** | Which user/group owns the record? | `ownerId=alice` |
| **Tenant isolation** | Which organization owns the record? | `tenantId=tenant-a`, always scoped by tenant |
| **Tenant admin scope** | Within which boundary may an admin override ownership? | Admin A views orders in tenant A, never tenant B |
| **Field-level authorization** | Within an allowed object, which fields can be read/edited? | `title` is editable; client cannot alter `ownerId`/`tenantId` |
| **Audit/monitoring** | Who attempted to access which data and with what outcome? | Log request ID, principal ID, outcome; avoid PII |

**Recognizing the flaw:** If an API blocks callers lacking `ORDER_READ` yet callers with `ORDER_READ` can fetch anyone's ID, you verified **function** access without verifying **object** access. OWASP API Security Top 10 2023 ranks Broken Object Level Authorization as **API1:2023**; unauthorized function actions fall under Broken Function Level Authorization (API5:2023).

A secure API does not ask only “does the user have role USER?”; it combines:

~~~text
allow(action, principal, object) =
    authenticated(principal)
    AND hasAuthority(principal, action)
    AND principal.tenantId == object.tenantId
    AND (
          principal.userId == object.ownerId
          OR hasRoleWithinThisTenant(principal, TENANT_ADMIN)
        )
    AND passesBusinessRestrictions(action, object)
~~~

This lesson chooses a straightforward policy: owners or tenant admins can read/edit within **their own tenant**; others in the same tenant are denied; everyone in other tenants sees nothing. Real systems may add team memberships, data classification, share grants, lock states, delegated access, or time-limited permissions. When policies grow complex, extract a **Policy Decision Point / authorization service** with dedicated tests instead of scattering inconsistent checks across controllers.

## 3. Permission matrix as the source of truth for tests

Fixture data:

| Order ID | Tenant | Owner | Title |
|---|---|---|---|
| **100** | `tenant-a` | `alice` | `Alice draft` |
| **101** | `tenant-a` | `bob` | `Bob draft` |
| **200** | `tenant-b` | `mallory` | `Mallory draft` |

Simulated test principals:

- Alice: `userId=alice`, `tenantId=tenant-a`, `ORDER_READ`, `ORDER_WRITE`.
- Bob: `userId=bob`, `tenantId=tenant-a`, `ORDER_READ`, `ORDER_WRITE`.
- Mallory: `userId=mallory`, `tenantId=tenant-b`, `ORDER_READ`, `ORDER_WRITE`.
- Admin A: `tenant-a`, `ROLE_TENANT_ADMIN`, `ORDER_READ`, `ORDER_WRITE`.
- Admin B: `tenant-b`, `ROLE_TENANT_ADMIN`, `ORDER_READ`, `ORDER_WRITE`.
- Read-only Alice: `tenant-a`, `ORDER_READ`, **no `ORDER_WRITE`**.
- Write-only Alice: `tenant-a`, `ORDER_WRITE`, **no `ORDER_READ`**.
- Anonymous: no verified identity.

Matrix for **order 100 (`tenant-a`, Alice)**:

| Caller | GET 100 | PATCH 100 | Reason |
|---|---|---|---|
| Anonymous | **401** | **401** when request carries valid CSRF; otherwise CSRF may block with 403 earlier | Unauthenticated |
| Alice | **200** | **200** with CSRF | Owner in matching tenant |
| Bob | **403** | **403** | Same tenant, neither owner nor admin |
| Mallory | **404** | **404** | Different tenant; do not leak ID existence |
| Admin A | **200** | **200** | Tenant admin in tenant A |
| Admin B | **404** | **404** | Tenant admin must not cross into tenant A |
| Write-only Alice | **403** | Follows `ORDER_WRITE` + ownership | Missing `ORDER_READ` |
| Read-only Alice | **200** | **403** | Missing `ORDER_WRITE` |

**About 403 and 404:** Both must be defined in the contract. The example chooses **404** when an ID does not exist inside the principal's tenant, avoiding revealing whether resources exist in other tenants; it chooses **403** when the object is in the same tenant yet the principal lacks owner/admin rights. Some systems return 404 for both to reduce enumeration; keep the policy consistent, especially regarding response bodies and latency. Never return 200 with empty data to mask an authorization error unless the contract explicitly mandates it.

**Never treat a URL/header tenant as the source of truth.** With URLs like `/tenants/{tenantId}/orders/{id}`, `tenantId` in the path is the **requested scope**, which must be checked against the authenticated identity and granted memberships; it is not an access grant on its own.

## 4. Defense layers in a single request

~~~text
Client
  |
  | GET /api/orders/100
  | Header X-Tenant-Id: tenant-b    <-- untrusted input
  v
Spring Security filter chain
  |  Authentication verified by trusted mechanism
  |  Principal carries userId + tenantId + authorities
  v
Controller
  |  Accepts objectId and updatable fields
  |  NEVER uses client tenant/owner to grant access
  v
Service (@PreAuthorize: ORDER_READ / ORDER_WRITE)
  |  Checks function-level authority
  |  Reads tenant from authenticated principal
  |  Loads object within matching tenant
  |  Checks owner or ROLE_TENANT_ADMIN of that tenant
  v
Repository
  |  SELECT ... WHERE tenant_id = :trustedTenantId AND id = :id
  |  UPDATE ... WHERE tenant_id = :trustedTenantId ...
  v
Database
  |
  | (production) RLS/constraints/tenant-scoped joins
  v
DTO returns only permitted fields
~~~

**Defense in depth:** URL-level authentication blocks unauthenticated callers; method-level authorities block unauthorized actions; service/repository guards protect objects; database tenant predicates/RLS limit blast radius if another code path forgets scoping. No single layer replaces all others.

### 4.1. Anti-patterns to avoid

**Anti-pattern A: check role only, then query by global ID**

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public OrderView read(long id) {
    return repository.findById(id) // May fetch another tenant's object.
            .map(this::view)
            .orElseThrow();
}
~~~

**Anti-pattern B: trust client-sent `X-Tenant-Id`**

~~~java
@GetMapping("/{id}")
OrderView read(
        @PathVariable long id,
        @RequestHeader("X-Tenant-Id") String tenantId) {
    return service.read(id, tenantId); // Can be spoofed.
}
~~~

**Anti-pattern C: trust `ownerId` from client JSON**

~~~java
// Client-sent JSON:
// {"title":"Changed", "ownerId":"alice", "tenantId":"tenant-a"}

// Wrong if the service uses ownerId/tenantId from the body
// to decide whether the user owns the object.
~~~

**Anti-pattern D: list API filtering after reading everything**

~~~java
List<Order> all = repository.findAll();
return all.stream()
        .filter(order -> order.tenantId().equals(tenant))
        .toList();
~~~

Filtering in Java *might* yield the right output, yet all cross-tenant records were loaded into memory/caches and could surface in logs, metrics, or intermediate object mappings. Prefer **tenant-scoped DB queries** right at the data-access layer combined with required domain checks.

**Anti-pattern E: tenant admin treated as global admin**

~~~java
boolean allowed = hasRole("TENANT_ADMIN")
        || order.ownerId().equals(userId);
~~~

Omitting the `order.tenantId == principal.tenantId` constraint lets a tenant B admin access tenant A data. **The tenant constraint must sit outside and run before the admin branch.**

## 5. Choosing test type: unit, method security, MVC, or database

| Type | Has Spring Security filters? | Real DB? | What it verifies |
|---|---|---|---|
| Pure Java unit test of `OrderPolicy` | No | No | Principal/object/action matrix, branch logic |
| `@WithMockUser` calling service bean with `@EnableMethodSecurity` | Method proxy | Not required | `@PreAuthorize`, role/authority |
| **`@SpringBootTest` + `@AutoConfigureMockMvc`** | **Yes (with default `addFilters=true`)** | Not required | 401/403/404, CSRF, controller + method policy + repository |
| `@WebMvcTest` | Yes, MVC slice only | No | Endpoints/security filters; needs `@MockBean/@Import` for policy |
| `@JdbcTest` / `@DataJpaTest` + DB | Depends on context | **Yes** | Tenant predicates, query joins, UPDATE row counts |
| `@SpringBootTest` + Testcontainers PostgreSQL | Optional | **Yes, real vendor** | RLS, DB roles, connection/session context, isolation |
| Real HTTP server + OAuth2 test IdP | Yes | Optional | JWT/issuer/audience verification, full auth chain |

Because this lesson focuses on testing permissions through HTTP and services, the runnable example uses **MockMvc with full Spring Boot context** and an in-memory repository so every test is fast and isolated. Add real DB integration tests whenever SQL/JPA repositories are used, because an in-memory fake can enforce policy while a production query omits `tenant_id`.

### 5.1. @WithMockUser or custom principal?

`@WithMockUser` builds a Spring Security `User` principal with username/roles/authorities. It works well for simple role tests, yet **does not automatically carry a verified `tenantId` field**. When production code relies on `TenantUser.tenantId`, a plain `@WithMockUser(username="alice")` cannot test tenant scoping.

In our example, we use Spring Security Test's **`SecurityMockMvcRequestPostProcessors.user(customUserDetails)`** to inject a test identity carrying `userId`, `tenantId`, and authorities per request. This is a **test shortcut simulating authentication results**, not proof that real tokens or logins were validated.

**Never construct a tenant principal from a caller-chosen `X-Tenant-Id` header.** In production, the tenant must come from a login session/JWT claims whose **signature, issuer, audience, expiry, and membership were verified**, or from a trusted identity/authorization directory. When a user belongs to multiple tenants, a client-selected active tenant must still be checked against their membership list; never trust raw headers.

## 6. Runnable project: Java 17 + Spring Boot 3.3.5 + MockMvc

This project has 3 orders and 5 test principal types, one REST controller, one `@PreAuthorize`-guarded service, one tenant-scoping in-memory repository, and a JUnit class testing every branch. The sample **has no production login accounts/passwords**; tests use `user(customUserDetails)` to supply simulated principals into `MockMvc`. To turn this into a real SaaS system, replace that with JWT/OIDC/session authentication and a tenant-scoped database.

### 6.1. Directory tree

~~~text
settings.gradle
build.gradle
src/main/java/demo/tenant/TenantSecurityApplication.java
src/main/java/demo/tenant/SecurityConfiguration.java
src/main/java/demo/tenant/TenantUser.java
src/main/java/demo/tenant/OrderData.java
src/main/java/demo/tenant/OrderView.java
src/main/java/demo/tenant/RenameOrderRequest.java
src/main/java/demo/tenant/InMemoryOrderStore.java
src/main/java/demo/tenant/OrderService.java
src/main/java/demo/tenant/OrderController.java
src/test/java/demo/tenant/TenantAuthorizationIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tenant-authorization-test'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Explanation:** `starter-web` provides Spring MVC, Jackson JSON, and MockMvc support with `starter-test`. `starter-security` provides `SecurityFilterChain`, `@PreAuthorize`, and the authentication context. `spring-security-test` provides `user(...)`, `csrf()`, and `@WithMockUser`. Specifically, **do not assume `starter-test` includes `spring-security-test`** — declare it explicitly. The Spring Boot BOM manages Spring Security versions so you do not pin Spring Security 6.3.x manually.

### 6.2. Application and HTTP security

**src/main/java/demo/tenant/TenantSecurityApplication.java**

~~~java
package demo.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantSecurityApplication.class, args);
    }
}
~~~

**src/main/java/demo/tenant/SecurityConfiguration.java**

~~~java
package demo.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Key points:**
1. `.anyRequest().authenticated()` blocks unauthenticated callers in the filter chain.
2. `.httpBasic(...)` triggers HTTP 401 challenges for unauthenticated requests in this example. Basic Auth is merely a mechanism to exercise HTTP auth status in this lesson, **not a recommendation that SaaS production use password Basic Auth**.
3. **`@EnableMethodSecurity` is mandatory** for `@PreAuthorize` on services to take effect; Spring Boot Starter Security does not enable method security automatically.
4. CSRF is left enabled in the sample: `PATCH` must supply a valid token per Spring Security's session/CSRF mechanics. Tests use `.with(csrf())`.
5. Every endpoint still requires an authenticated user; **authentication does not mean permission to read every object**.
6. Method security uses Spring AOP proxies: avoid calling a `@PreAuthorize` method from another method in the same instance expecting the proxy to intercept. Controllers here invoke the Spring-managed service bean through its proxy.

**Practical note:** When deploying a stateless Bearer JWT API using `Authorization` headers, configure `oauth2ResourceServer(...).jwt(...)` or an equivalent validator; CSRF policy depends on how credentials are stored. **Never disable CSRF by rote** just because a project uses REST: if browsers attach cookie/session credentials automatically, CSRF remains a threat. This lesson keeps CSRF enabled to test an independent defense layer alongside ownership/tenant authorization.

### 6.3. Principal carrying tenant and authorities

**src/main/java/demo/tenant/TenantUser.java**

~~~java
package demo.tenant;

import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public record TenantUser(
        String userId,
        String tenantId,
        List<GrantedAuthority> authorities) implements UserDetails {

    public TenantUser {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(tenantId);
        authorities = List.copyOf(authorities);
    }

    public static TenantUser regular(String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(
                        new SimpleGrantedAuthority("ORDER_READ"),
                        new SimpleGrantedAuthority("ORDER_WRITE")));
    }

    public static TenantUser tenantAdmin(
            String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(
                        new SimpleGrantedAuthority("ORDER_READ"),
                        new SimpleGrantedAuthority("ORDER_WRITE"),
                        new SimpleGrantedAuthority(
                                "ROLE_TENANT_ADMIN")));
    }

    public static TenantUser readOnly(
            String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(new SimpleGrantedAuthority("ORDER_READ")));
    }

    public static TenantUser writeOnly(
            String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(new SimpleGrantedAuthority("ORDER_WRITE")));
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return "NOT_USED_FOR_LOGIN";
    }

    @Override
    public String getUsername() {
        return userId;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

`TenantUser` is **a Java 17 record that Spring Security Test can attach as a principal via `UserDetails`**. `getPassword()` is intentionally a dummy value: this class has no `UserDetailsService` authenticating real requests, and tests skip password verification. In production, use a validated JWT principal/`Authentication` token or a secure directory-backed `UserDetailsService`. **Never assign `tenantId` from request headers**, and never serialize dummy passwords to responses or logs.

**Role rule:** `hasRole('TENANT_ADMIN')` checks authority `ROLE_TENANT_ADMIN`; `hasAuthority('ORDER_READ')` checks the exact string `ORDER_READ`. The lesson grants both role and action authorities explicitly; admins belong to **their own tenant** rather than becoming cross-tenant superusers.

### 6.4. Domain data, response DTO, and request DTO

**src/main/java/demo/tenant/OrderData.java**

~~~java
package demo.tenant;

public record OrderData(
        long id,
        String tenantId,
        String ownerId,
        String title) {
}
~~~

**src/main/java/demo/tenant/OrderView.java**

~~~java
package demo.tenant;

public record OrderView(long id, String title) {
    public static OrderView from(OrderData value) {
        return new OrderView(value.id(), value.title());
    }
}
~~~

**src/main/java/demo/tenant/RenameOrderRequest.java**

~~~java
package demo.tenant;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record RenameOrderRequest(String title) {
}
~~~

**Why three types?**
- **`OrderData`** is internal domain data: holds `tenantId`/`ownerId` for access enforcement.
- **`OrderView`** is the public response: exposes only `id` and `title`, avoiding returning authorization fields or internal notes unnecessarily.
- **`RenameOrderRequest`** accepts only `title`, with no setters for tenant or owner. `@JsonIgnoreProperties(ignoreUnknown=true)` intentionally ignores extra JSON keys **without applying** them. The mass-assignment test below proves extra `tenantId`/`ownerId` keys cannot reassign ownership. In production, you may enable **fail on unknown properties** to reject unexpected input explicitly; ignoring unknown DTO keys is not mandatory input validation for every API.

Binding a JPA entity directly as `@RequestBody` and calling `repository.save(entity)` lets clients overwrite unintended fields like `tenantId`, `ownerId`, `isAdmin`, or `status`; that is **mass assignment**, a risk distinct from BOLA yet often exposed on update endpoints. Separate allowlisted request DTOs as shown here.

### 6.5. Repository: every read/list/update is tenant-scoped

**src/main/java/demo/tenant/InMemoryOrderStore.java**

~~~java
package demo.tenant;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

@Repository
public class InMemoryOrderStore {

    private final ConcurrentMap<Long, OrderData> rows =
            new ConcurrentHashMap<>();

    public InMemoryOrderStore() {
        reset();
    }

    public void reset() {
        rows.clear();
        rows.put(100L,
                new OrderData(100L,
                        "tenant-a", "alice", "Alice draft"));
        rows.put(101L,
                new OrderData(101L,
                        "tenant-a", "bob", "Bob draft"));
        rows.put(200L,
                new OrderData(200L,
                        "tenant-b", "mallory", "Mallory draft"));
    }

    public Optional<OrderData> findInTenant(
            long id, String tenantId) {
        return Optional.ofNullable(rows.get(id))
                .filter(row -> row.tenantId().equals(tenantId));
    }

    public List<OrderData> listInTenant(String tenantId) {
        return rows.values().stream()
                .filter(row -> row.tenantId().equals(tenantId))
                .sorted(Comparator.comparingLong(OrderData::id))
                .toList();
    }

    public OrderData renameInTenant(
            long id, String tenantId, String title) {

        OrderData updated = rows.computeIfPresent(
                id,
                (key, row) -> row.tenantId().equals(tenantId)
                        ? new OrderData(
                                row.id(), row.tenantId(),
                                row.ownerId(), title)
                        : row);

        if (updated == null
                || !updated.tenantId().equals(tenantId)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }

        return updated;
    }
}
~~~

Every read/list/update method receives the tenant scope **obtained by the service from the authenticated principal**, never arbitrarily from a header. `findInTenant` returns empty when the ID does not exist or belongs to another tenant, keeping the HTTP 404 policy uniform.

**This is a fake repository for instructional use.** `reset()` runs before each test; tests share one `ApplicationContext` and do not run in parallel within the class. `ConcurrentHashMap` provides atomic per-key map updates, yet `clear`/`put` resets are not database transactions and can race if a larger suite shares the store across classes. Production must use PostgreSQL/JPA tenant-aware predicates, row-level permissions, transactions, and constraints rather than a singleton map.

**Defense in depth:** `renameInTenant` re-verifies the tenant inside the update operation itself. Even after the service verified the object, the storage layer refuses to update another tenant's record. In a real database, do this with **a single `UPDATE` carrying a tenant predicate and checking affected row count** to prevent time-of-check/time-of-use races.

### 6.6. Service: permissions by action + owner + tenant

**src/main/java/demo/tenant/OrderService.java**

~~~java
package demo.tenant;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final InMemoryOrderStore store;

    public OrderService(InMemoryOrderStore store) {
        this.store = store;
    }

    private TenantUser trustedPrincipal() {
        Authentication authentication =
                SecurityContextHolder.getContext()
                        .getAuthentication();

        if (authentication == null
                || !(authentication.getPrincipal()
                        instanceof TenantUser user)) {
            throw new AccessDeniedException(
                    "Trusted tenant principal required");
        }

        return user;
    }

    private boolean isTenantAdmin(TenantUser user) {
        return user.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_TENANT_ADMIN"::equals);
    }

    private OrderData authorizedOrder(
            long id, TenantUser principal) {

        // Tenant scope IS CHECKED BEFORE owner/admin.
        OrderData row = store
                .findInTenant(id, principal.tenantId())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Order not found"));

        if (!row.ownerId().equals(principal.userId())
                && !isTenantAdmin(principal)) {
            throw new AccessDeniedException(
                    "Object ownership permission required");
        }

        return row;
    }

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public OrderView read(long id) {
        TenantUser principal = trustedPrincipal();
        return OrderView.from(authorizedOrder(id, principal));
    }

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public List<OrderView> listMineOrTenantAdmin() {
        TenantUser principal = trustedPrincipal();

        return store.listInTenant(principal.tenantId())
                .stream()
                .filter(row -> isTenantAdmin(principal)
                        || row.ownerId().equals(principal.userId()))
                .map(OrderView::from)
                .toList();
    }

    @PreAuthorize("hasAuthority('ORDER_WRITE')")
    public OrderView rename(long id, String newTitle) {
        TenantUser principal = trustedPrincipal();

        OrderData current = authorizedOrder(id, principal);

        if (newTitle == null || newTitle.isBlank()
                || newTitle.strip().length() > 80) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Title must contain 1 to 80 characters");
        }

        // Storage layer still scopes by tenant.
        OrderData updated = store.renameInTenant(
                current.id(),
                principal.tenantId(),
                newTitle.strip());

        return OrderView.from(updated);
    }
}
~~~

**Sequence analysis:**

1. `@PreAuthorize("hasAuthority('ORDER_READ')")` or `ORDER_WRITE` is the **function-level guard** before entering the method (when `@EnableMethodSecurity` is active and calls pass through the Spring proxy).
2. `trustedPrincipal()` reads identity from the **authenticated request's `SecurityContextHolder`**, never accepting tenant from controller/client method arguments.
3. `authorizedOrder` queries inside the exact tenant **before** checking owner or tenant admin. For another tenant's ID, it finds no object and returns **404**.
4. For an object in the same tenant, if the caller is neither owner nor `ROLE_TENANT_ADMIN`, it throws `AccessDeniedException`, which Spring Security translates to **403**.
5. Tenant admins also read only `store.listInTenant(principal.tenantId())`, so the role never turns into a global admin.
6. When renaming, only a valid `title` is accepted and passed to the tenant-scoped storage method. No `ownerId`/`tenantId` is accepted from the body.
7. `@PreAuthorize` also protects service calls from other entry points such as other controllers or scheduled jobs going through the Spring proxy. Still, **self-invocation can bypass the method-security proxy**, so never rely solely on annotations when writing internal calls.
8. `SecurityContextHolder` is normally thread-local. For `@Async`, `CompletableFuture`, and thread pools, design context propagation and re-verify authorization; never fall back to a default tenant or copy a user ID from headers.

**On order checks and 403/404:** The lab intentionally returns 404 for cross-tenant IDs and 403 for same-tenant non-owners. If security requirements forbid revealing even owner existence within a tenant, returning 404 consistently is also valid. Test that policy across **all operations**. Avoid returning mismatched error codes between GET and PATCH that let clients probe resource existence.

**On direct DB SQL:** Fake `authorizedOrder` + `renameInTenant` shows two check layers without providing serializable isolation against a real DB. When an object's owner/tenant can change concurrently, use an `UPDATE` with `WHERE tenant_id AND owner_id/permission predicate` or transactional locking with rechecks. See Section 10.

### 6.7. Controller does not accept client-asserted tenant/owner

**src/main/java/demo/tenant/OrderController.java**

~~~java
package demo.tenant;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping
    public List<OrderView> list() {
        return service.listMineOrTenantAdmin();
    }

    @GetMapping("/{id}")
    public OrderView read(@PathVariable long id) {
        return service.read(id);
    }

    @PatchMapping("/{id}")
    public OrderView rename(
            @PathVariable long id,
            @RequestBody RenameOrderRequest request) {
        return service.rename(id, request.title());
    }
}
~~~

The controller accepts the resource ID and `title`, with **no `tenantId`/`ownerId` parameters** for clients to assert. If an API needs a tenant segment in the URL, validate that segment against permitted tenants from the identity. Never substitute `?tenantId=tenant-b` for `trustedPrincipal()`.

Returning `OrderView` instead of `OrderData` also limits internal field leakage. Still, DTOs may need additional field-level authorization when objects hold sensitive attributes; **permission to read an object does not mean permission to view every field**.

## 7. Complete integration test class: 21 JUnit Jupiter tests

**src/test/java/demo/tenant/TenantAuthorizationIntegrationTest.java**

~~~java
package demo.tenant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Execution(ExecutionMode.SAME_THREAD)
class TenantAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryOrderStore store;

    @BeforeEach
    void resetFixture() {
        store.reset();
    }

    @Test
    void anonymousCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/100"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(100))
                .andExpect(jsonPath("$.title").value("Alice draft"))
                .andExpect(jsonPath("$.tenantId").doesNotExist())
                .andExpect(jsonPath("$.ownerId").doesNotExist());
    }

    @Test
    void sameTenantOtherOwnerIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "bob", "tenant-a"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void crossTenantOrderLooksNotFound() throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isNotFound());
    }

    @Test
    void tenantAdminCanReadAnotherOwnerInSameTenant()
            throws Exception {
        mvc.perform(get("/api/orders/101")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.title").value("Bob draft"));
    }

    @Test
    void tenantAdminCannotCrossTenantBoundary()
            throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-b", "tenant-b"))))
                .andExpect(status().isNotFound());
    }

    @Test
    void ownerListContainsOnlyOwnOrders()
            throws Exception {
        mvc.perform(get("/api/orders")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value(100));
    }

    @Test
    void tenantAdminListContainsOnlyItsTenant()
            throws Exception {
        mvc.perform(get("/api/orders")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].id").value(100))
                .andExpect(jsonPath("$[1].id").value(101));
    }

    @Test
    void secondTenantListDoesNotContainFirstTenant()
            throws Exception {
        mvc.perform(get("/api/orders")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value(200));
    }

    @Test
    void forgedTenantHeaderDoesNotGrantAccess()
            throws Exception {
        mvc.perform(get("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .header("X-Tenant-Id", "tenant-b"))
                .andExpect(status().isNotFound());
    }

    @Test
    void writeOnlyPrincipalCannotRead()
            throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.writeOnly(
                                "alice", "tenant-a"))))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ORDER_READ")
    void genericMockUserLacksTrustedTenantPrincipal()
            throws Exception {
        mvc.perform(get("/api/orders/100"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanPatchTitleWithCsrf()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Updated title\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated title"));

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated title"));
    }

    @Test
    void sameTenantOtherOwnerCannotPatch()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "bob", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Hijacked\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Alice draft"));
    }

    @Test
    void crossTenantPatchIsNotFoundAndUnchanged()
            throws Exception {
        mvc.perform(patch("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Cross-tenant rewrite\"}"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Mallory draft"));
    }

    @Test
    void patchWithoutCsrfIsRejected()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .contentType("application/json")
                        .content("{\"title\":\"No csrf\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(jsonPath("$.title").value("Alice draft"));
    }

    @Test
    void readOnlyPrincipalCannotPatch()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.readOnly(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Write forbidden\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void tenantAdminCanPatchWithinSameTenant()
            throws Exception {
        mvc.perform(patch("/api/orders/101")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Admin reviewed\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Admin reviewed"));

        mvc.perform(get("/api/orders/101")
                        .with(user(TenantUser.regular(
                                "bob", "tenant-a"))))
                .andExpect(jsonPath("$.title").value("Admin reviewed"));
    }

    @Test
    void tenantAdminCannotPatchAnotherTenant()
            throws Exception {
        mvc.perform(patch("/api/orders/200")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Global admin mistake\"}"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(jsonPath("$.title").value("Mallory draft"));
    }

    @Test
    void jsonOwnerAndTenantFieldsCannotReassignOrder()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("""
                                {
                                  "title":"Safe title",
                                  "ownerId":"mallory",
                                  "tenantId":"tenant-b"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Safe title"));

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Safe title"));
    }

    @Test
    void blankTitleIsRejectedWithoutMutation()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(jsonPath("$.title").value("Alice draft"));
    }
}
~~~

**Exact count: 21 `@Test` methods**; `@BeforeEach` fixture reset does not count as a test. Methods that mutate data always start with a fresh fixture on the next test. `@Execution(SAME_THREAD)` prevents methods within this class from running concurrently against one another; a larger suite still requires isolating `ApplicationContext`/DB state if multiple classes share a store or enable global parallelism.

**Why each assertion matters:**
- `401`: anonymous caller failed authentication. This is not proof of object-level authorization.
- `403`: authenticated caller lacked action authority or was neither owner nor admin within the tenant.
- `404`: object does not exist in the principal's tenant; even if the ID exists in another tenant, its existence is not revealed.
- `200`: only authorized callers receive the DTO; the DTO omits `ownerId`/`tenantId`.
- `GET /api/orders`: checks **list scoping**, because guarding only the detail endpoint leaks records via list/search.
- `PATCH`: tests **write** rights separately from **read** rights, blocking same-tenant Bob and cross-tenant admins from unauthorized edits.
- Forged `X-Tenant-Id`: header cannot override the tenant from the trusted principal.
- Forged JSON `ownerId`/`tenantId`: request DTO has no writable fields for them; persisted record owner and tenant remain untouched.
- CSRF: state-changing requests missing a token are blocked. This is **another defense layer**, not proof of ownership policy; tests validating ownership must include `.with(csrf())` so they are not blocked early.
- `@WithMockUser`: demonstrates that a simple mock user lacks `TenantUser` tenant fields; method-level read authority passes yet the service rejects a principal lacking a trusted tenant.

**Do not claim this is a real JWT test.** `.with(user(...))` puts a *simulated* trusted principal directly onto the mock request. It does not test token verification, issuer/audience, IdP role mapping, or tenant membership refresh. Those require dedicated authentication-layer tests.

### 7.1. Why reset the fixture before each test?

`InMemoryOrderStore` is a Spring singleton retained in `ApplicationContext` by `@SpringBootTest`. If a `PATCH` test changes `Alice draft` to `Updated title`, a later test checking the original title can fail or pass depending on execution order unless reset. Hence:

~~~java
@Autowired
InMemoryOrderStore store;

@BeforeEach
void resetFixture() {
    store.reset();
}
~~~

When moving to JPA/JDBC, prefer **test-managed transactions + rollback**, `@Sql` setup/cleanup, disposable databases, or isolated Testcontainers fixtures. Never treat an in-memory reset as proof of database transaction isolation; and avoid `@DirtiesContext` on every test when lighter data resets exist.

### 7.2. Why are negative tests for *same tenant, different owner* essential?

Many teams test only Alice and Mallory across different tenants and assume ownership is enforced. A buggy implementation:

~~~java
if (record.tenantId().equals(principal.tenantId())) {
    return record; // Exposes every object in the same tenant!
}
~~~

will **pass** cross-tenant tests yet **fail** Bob reading Alice's order when policy permits only the owner or tenant admin. If business rules intentionally let all users within a tenant share orders, update the permission matrix and assertions deliberately. Never assume ownership checks are mandatory in every B2B app; derive them from the real permission contract.

### 7.3. Why must tenant admins be tested cross-tenant separately?

A flawed check:

~~~java
if (principal.hasAuthority("ROLE_TENANT_ADMIN")) {
    return repository.findById(id).orElseThrow();
}
~~~

lets tenant A's admin access tenant B. **`tenantAdminCannotCrossTenantBoundary`** and **`tenantAdminCannotPatchAnotherTenant`** catch this. The proper pattern is **filtering by tenant first**, then checking whether the role overrides ownership *within that tenant*.

### 7.4. Why omit owner/tenant from the response DTO unless contracted?

Authorized clients sometimes need `tenantId`/`ownerId` for display; when contracted, expose fields matching field-level access rules. In this lesson, `OrderView` exposes only `id`/`title` to avoid returning the full domain entity accidentally. If a response exposes `isAdmin`, internal costs, passwords, recovery keys, or private info, passing object-level authorization still leaves field-level authorization broken.

## 8. Run commands, preconditions, and expected results

The project uses Java 17, Gradle, the files in Section 6, and the tests in Section 7. With a Gradle Wrapper created:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run this class alone:

~~~bash
./gradlew test --tests demo.tenant.TenantAuthorizationIntegrationTest
~~~

Spring Boot is expected to locate `@SpringBootApplication` in package `demo.tenant`, initialize the Spring Security filter chain, method-security proxy, controller/service/repository, and MockMvc. `spring-security-test` supplies `.with(user(...))` and `.with(csrf())`. **All 21 test methods are designed to PASS** when source is created accurately and no external config alters authorization policy. These are **expected results from source**, not confirmation that Gradle ran in your environment.

Gradle reports are typically located at:

~~~text
build/reports/tests/test/index.html
~~~

| Test group | `@Test` count | Goal |
|---|---|---|
| Authentication / GET detail / owner & tenant | 6 | 401, owner 200, same-tenant 403, cross-tenant 404, admin same-tenant 200, admin cross-tenant 404 |
| GET list / forged header / missing authority / principal type | 6 | 3 list-scoping cases, forged header, missing `ORDER_READ`, generic `@WithMockUser` |
| PATCH update / CSRF / authority / admin / mass assignment / validation | 9 | Owner write, same-tenant denied, cross-tenant denied, no CSRF, readOnly, admin allow/deny, JSON spoof, blank title |
| **Total** | **21** | Zero `@Disabled` or intentionally failing tests |

**Exact group breakdown:** 6 + 6 + 9 = 21. Methods performing multiple `mvc.perform` calls remain **one JUnit test**; each request inside a test executes in clear assertion order.

**Conditions that could diverge outside the sample code:** If `spring-security-test` is missing, static imports will not compile. If `@AutoConfigureMockMvc(addFilters=false)` disables Spring Security filters, 401/CSRF tests can misbehave. If `@EnableMethodSecurity` is omitted, missing `ORDER_READ`/`ORDER_WRITE` may go unblocked. If the DTO is swapped for a raw entity body, the JSON owner/tenant test catches mass assignment. If the server validates real tokens, add dedicated token validation tests and never use dummy `TenantUser` as production authentication.

## 9. Mutation matrix: intentionally injecting bugs to verify test sensitivity

| Hypothetical mutation | Expected failing test(s) |
|---|---|
| Remove `@EnableMethodSecurity` | `MissingReadAuthority` and `ReadOnlyCannotPatch` fail due to missing function guard |
| Change `@PreAuthorize("ORDER_READ")` to `permitAll()` | `WriteOnlyPrincipalCannotRead` |
| Repository uses `findById` without tenant scope | `CrossTenantOrderLooksNotFound` and `AdminCannotCrossTenantBoundary` |
| Remove owner check in `authorizedOrder` | `SameTenantOtherOwnerIsForbidden`, `BobCannotPatch` |
| Let admin bypass tenant | `AdminCannotCrossTenantBoundary`, `AdminCannotPatchAnotherTenant` |
| Trust `X-Tenant-Id` header | `ForgedTenantHeaderDoesNotGrantAccess` |
| Return raw `OrderData` instead of `OrderView` | `OwnerCanReadOwnOrder` catches exposed `ownerId`/`tenantId` |
| PATCH binds full `OrderData` and saves | `JsonOwnerAndTenantFieldsCannotReassignOrder` |
| Remove `@PreAuthorize("ORDER_WRITE")` | `ReadOnlyPrincipalCannotPatch` |
| Disable CSRF in security config | `PatchWithoutCsrfIsRejected` |
| Use global `findAll()` and return DTOs unfiltered | List scoping tests fail |
| Allow same-tenant `bob` to rename Alice's order | `SameTenantOtherOwnerCannotPatch` |
| Change cross-tenant 404 to 403 | Cross-tenant tests fail, flagging the policy shift |
| Omit resetting fixture before each test | PATCH tests introduce order dependency |
| Skip checking trusted tenant principal | Generic `MockUser` test detects insufficient principal acceptance |
| Remove blank-title validation | `BlankTitleIsRejectedWithoutMutation` |

**Goal of mutation testing:** Confirm the test suite catches **the exact intended permission flaws**. Do not test only happy paths or unauthenticated requests; BOLA typically strikes **logged-in users who hold valid functional permissions** yet operate on unauthorized objects.

## 10. Replacing the fake with a real database: tenant scope must live in SQL

### 10.1. Single-record queries

**Anti-pattern:**

~~~sql
SELECT id, tenant_id, owner_id, title
FROM orders
WHERE id = :id;
~~~

With global IDs, this query loads another tenant's record into the application layer. Application code might still block it, yet if anything logs or returns early before the check, data leaks. In multi-tenant systems, prefer:

~~~sql
SELECT id, tenant_id, owner_id, title
FROM orders
WHERE id = :id
  AND tenant_id = :trusted_tenant_id;
~~~

`trusted_tenant_id` must originate from the **validated principal/tenant membership**, never directly from `X-Tenant-Id` or JSON bodies. With Spring JDBC, use **`NamedParameterJdbcTemplate`** with bound parameters; never concatenate raw strings into SQL. With Spring Data JPA, methods like `findByIdAndTenantId` or Criteria/Specifications with tenant predicates establish clear contracts, though you must test the **real SQL** and guard against other repository methods lacking the filter.

### 10.2. UPDATE/DELETE must be scoped atomically

Checking ownership in Java followed by `WHERE id=:id` creates a **time-of-check/time-of-use (TOCTOU)** race if the record's owner/tenant changes in between. An atomic conditional update:

~~~sql
UPDATE orders
SET title = :new_title
WHERE id = :id
  AND tenant_id = :trusted_tenant_id
  AND (
        owner_id = :trusted_user_id
        OR :trusted_is_tenant_admin = TRUE
      );
~~~

For PostgreSQL boolean parameters, the condition above illustrates the pattern; named placeholders belong to **`NamedParameterJdbcTemplate`**, not plain `psql` syntax. `trusted_is_tenant_admin` **must only be computed backend-side from verified permissions in that tenant**. Check the affected row count:
- 1: update succeeded.
- 0: nonexistent or unauthorized; return 404/403 per policy without revealing other tenants.

If you must distinguish 403 from 404, query existence **within the tenant** to locate the object without leaking cross-tenant records, then recheck/lock inside the same transaction. Never separate read and update while ignoring concurrency. `DELETE` and batch updates follow the same rule: every statement needs a tenant predicate or proper RLS.

### 10.3. LIST and pagination must scope directly at the DB

~~~sql
SELECT id, title
FROM orders
WHERE tenant_id = :trusted_tenant_id
  AND (
       owner_id = :trusted_user_id
       OR :trusted_is_tenant_admin = TRUE
  )
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

The **`COUNT` query** supporting pagination must apply the exact same tenant/ownership predicate, or JSON metadata `totalElements` will leak other tenants' record counts even when list items are filtered. The same holds for search indexes, caches, exports, and aggregates: tenant scope must live inside **keys/queries/cache namespaces**, not just the HTTP list endpoint.

### 10.4. Composite keys and foreign keys

In designs where IDs can repeat across tenants, consider:

~~~sql
CREATE TABLE orders (
    tenant_id VARCHAR(80) NOT NULL,
    id BIGINT NOT NULL,
    owner_id VARCHAR(80) NOT NULL,
    title VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
~~~

For child tables, include the tenant dimension in foreign keys so a tenant A row can never reference a tenant B parent:

~~~sql
CREATE TABLE order_lines (
    tenant_id VARCHAR(80) NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, id)
);
~~~

This is **architectural reference SQL**, not part of the in-memory Gradle project. It shows how composite PK/FK constraints stop cross-tenant references at the data layer. Global UUIDs can also work, paired with tenant predicates and matching constraints. Unique indexes on email/external IDs must likewise be evaluated for `(tenant_id, external_id)` scoping when uniqueness is per-tenant.

## 11. PostgreSQL Row-Level Security (RLS) as an extra defense layer

With **shared database/shared schema** on PostgreSQL, RLS reduces the impact of an application query missing `WHERE tenant_id = ?`. Still, enabling RLS does not make a system secure automatically; policies, DB roles, and transaction context must be configured properly.

Conceptual example on PostgreSQL table `orders` with `VARCHAR` `tenant_id`:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON orders
    FOR ALL
    USING (
        tenant_id = current_setting(
            'app.current_tenant', true)
    )
    WITH CHECK (
        tenant_id = current_setting(
            'app.current_tenant', true)
    );

ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

**Meaning:**
- `USING` restricts which rows are visible/updatable/deletable.
- `WITH CHECK` ensures inserted/updated rows belong to the permitted tenant.
- `current_setting(..., true)` returns `NULL` when unset; comparisons against `NULL` do not evaluate to true, so RLS returns no rows under that policy.
- `FORCE ROW LEVEL SECURITY` subjects the table owner to the policy; however, **superusers or DB roles with `BYPASSRLS` still bypass RLS**, so the application must connect as a least-privilege role.
- Production tables need proper indexes, migrations, operation-specific policies, and careful verification of owner/admin exceptions.

**Important limitation:** RLS does not replace same-tenant object ownership if the policy only compares tenants. When ownership is required, enforce owner checks in policies or in service/SQL predicates. Also audit **views, `SECURITY DEFINER` functions, background jobs, and migrations**, where privileges can differ from the application role.

**Setting tenant context safely:** With connection pooling, never run session-level `SET app.current_tenant` and return the connection to the pool; the old tenant can leak into the next request. Inside the transaction wrapping queries, use **`SET LOCAL`** or `set_config(..., true)` with the value from the verified identity and strict transaction boundaries. Example:

~~~sql
BEGIN;
SET LOCAL app.current_tenant = 'tenant-a';
SELECT id, title FROM orders;
COMMIT;
~~~

This is SQL inside **a PostgreSQL transaction**, not an H2 default command or an automatic Spring Boot setting. In JDBC, bind the tenant safely or invoke `SELECT set_config('app.current_tenant', :tenant, true)` via a prepared statement inside the right transaction/connection; never interpolate user strings into `SET LOCAL`.

**Mandatory RLS testing:** Test using the **actual production DB role**, never a superuser or un-FORCED owner assuming the policy is active. Test tenant A -> B -> A across reused pooled connections, concurrent requests, and thread pools; if `tenantId` is missing or invalid, fail closed. PostgreSQL RLS is defense-in-depth, not a switch that guarantees application-level policy on its own.

## 12. Writing real database and JWT tests

### 12.1. Tests with @JdbcTest / @DataJpaTest

When replacing the in-memory store with a database:
1. Seed at least **2 tenants, 2 owners per tenant**, using overlapping predictable IDs if schema permits.
2. Test repository `findByIdAndTenantId` with matching ID / different tenant returning empty; test joins and pagination counts.
3. Test `UPDATE`/`DELETE` with tenant/owner predicates, checking affected rows and **confirming other tenants' data stays untouched**.
4. Test business side effects like audit records, file references, payments, and notifications carry independent tenant scope.
5. Verify `@Sql` scripts respect transactions/cleanup so one test's tenant data never leaks into the next test.
6. With Testcontainers PostgreSQL, run with the same DB role, connection pool, and RLS as production. H2 does not fully emulate PostgreSQL RLS.
7. Test concurrency: two transactions simultaneously modifying ownership/orders; verify no TOCTOU window.
8. Test cache keys/search indexes: lookups include `(tenantId, id)` or matching partitions.
9. Test migrations to ensure foreign keys/indexes/policies on new tables preserve tenant scope.
10. For async jobs or scheduled workers, confirm they receive explicit identity/authorization context rather than falling back to a global default tenant.

Example using `NamedParameterJdbcTemplate` in a repository:

~~~java
// Snippet inside a repository holding NamedParameterJdbcTemplate jdbc.
var params = new MapSqlParameterSource()
        .addValue("id", requestedId)
        .addValue("tenant", authenticatedTenantId);

List<OrderData> rows = jdbc.query(
        """
        SELECT id, tenant_id, owner_id, title
        FROM orders
        WHERE id = :id AND tenant_id = :tenant
        """,
        params,
        (rs, n) -> new OrderData(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getString("owner_id"),
                rs.getString("title")));
~~~

This is a **snippet**, not part of the runnable in-memory project. It uses named parameter placeholders rather than SQL string concatenation; it requires imports for `NamedParameterJdbcTemplate`, `MapSqlParameterSource`, `List`, and `OrderData`.

### 12.2. JWT and token validation must be tested separately

A token carrying `tenant_id=tenant-a` is trustworthy only when the authentication layer has:
- Verified the signature via trusted keys/JWKS.
- Verified issuer (`iss`), audience (`aud`), expiry (`exp`), not-before if used, and token type/scopes.
- Bound subject (`sub`) to permitted user/tenant memberships.
- Mapped roles/scopes to authorities with proper prefixes (e.g., `ORDER_READ`, `ROLE_TENANT_ADMIN`).
- Resolved multi-tenant users: an active tenant is valid only if permitted for that membership.
- Prevented clients from swapping `X-Tenant-Id` and treating it as IdP-verified.

With Spring Security OAuth2 Resource Server, `jwt()` from `spring-security-test` helps test claim mapping in controllers, yet **does not verify JWT signatures** because it is mock authentication; add dedicated tests for `JwtDecoder`/issuer/JWKS when authentication itself is in scope. Tests in this lesson use `user(TenantUser...)` to avoid pretending security tokens were verified.

### 12.3. Method security and self-invocation

`@PreAuthorize` uses proxies on Spring-managed beans. If another method in the same class calls `this.read(id)`, that invocation may **bypass the method-security interceptor**, skipping `@PreAuthorize`. Therefore:
- Place authorization at clear service boundaries.
- Ensure controllers/callers invoke through Spring-managed proxies.
- Test non-HTTP entry points (message listeners, scheduled jobs, batch).
- Never rely solely on annotations if a repository permits unscoped global queries.

Some projects use `@PostAuthorize` to check `returnObject.ownerId == authentication.name` **after** fetching the object. That helps in suitable read cases, yet fails to prevent side effects that already ran, and the object was already loaded/possibly logged before denial. For mutations, verify **before side effects** and push tenant scoping into queries/`UPDATE`s as early as possible.

## 13. Design bugs and diagnosis

| Symptom | Cause | How to test/fix |
|---|---|---|
| Alice reads Bob's order | Checked tenant only, skipped owner | Same-tenant non-owner negative test |
| Tenant B reads Tenant A's order | Global `findById` repository or role bypass | Cross-tenant GET/PATCH/list assertions |
| Tenant A admin reads every tenant | Admin OR owner checked before tenant | Enforce tenant scope outside admin branch |
| List query is right yet `totalCount` leaks | `COUNT` query not tenant-scoped | Assert pagination metadata |
| `@WithMockUser` test lacks `tenantId` | Default principal is `User` | Custom test `UserDetails`/`Authentication` |
| `X-Tenant-Id` header alters returned data | Used client-supplied tenant as authority | Spoofed-header test; derive tenant from auth |
| PATCH edits `ownerId`/`tenantId` | Bound JPA entity directly / overly broad DTO | Allowlist request DTO + mass-assignment test |
| Missing ID returns 500 instead of 404 | Unhandled missing repository row | `ResponseStatusException(NOT_FOUND)` or exception mapper |
| `@PreAuthorize` does nothing | Forgot `@EnableMethodSecurity` | Missing-authority tests |
| Anonymous HTTP reaches controller | `SecurityFilterChain` does not apply to URL | MockMvc 401 test, filter integration |
| CSRF 403 masks owner test | PATCH omitted `.with(csrf())` | Supply CSRF to test policy; test CSRF separately |
| PATCH test passes yet DB updates wrong tenant | Service checks then runs `UPDATE ... WHERE id` | SQL affected rows + cross-tenant DB test |
| Test passes alone, fails in full suite | Shared singleton fixture/state | `@BeforeEach` reset, isolation, no parallel writes |
| Every test uses admin so all pass | Missing user/owner/other-tenant cases | Positive and negative permission matrix |
| 404 differs across tenants | Policy returns mismatched responses | Uniform not-found policy with non-leaking body |
| Cache returns another tenant's object | Cache key uses only `id` | Tenant-aware cache keys and tests |
| SQL JOIN pulls cross-tenant child | FK/join omits tenant | Composite foreign keys, scoped joins |
| RLS has no effect | Connected as superuser/un-forced owner | Least-privilege role + `FORCE RLS` + policy tests |
| PgBouncer tenant context mixes up | Session `SET` on pooled connection | `SET LOCAL` inside transaction |
| Async worker sees empty/stale tenant | `SecurityContext` `ThreadLocal` not propagated | Explicit trusted context/tenant scope, fail closed |
| Direct service call bypasses guard | Self-invocation skips proxy | Test direct/indirect paths, service policy |

### 13.1. Practical debugging workflow

1. Confirm the request **authenticated** with the right principal, never confusing role with `userId`.
2. Confirm the action authority grants `READ`/`WRITE` accordingly.
3. Confirm `tenantId` comes from a **verified source**, not arbitrary paths/headers/bodies.
4. Check which tenant and owner the target row belongs to, and the admin role's scope.
5. Inspect whether repository queries enforce `WHERE tenant_id=?` or active RLS.
6. Verify GET detail, list/search/pagination, PATCH/DELETE, export, and batch APIs share the same policy.
7. On 403, check missing authority/owner; on 404, check tenant-scoped lookup and existence inside that tenant.
8. When using `@PreAuthorize`, verify `@EnableMethodSecurity`, Spring proxies, and absence of self-invocation bypasses.
9. When using `MockMvc`, verify security filters are enabled and requests carry `.with(user(customPrincipal))`.
10. When CSRF applies to state-changing requests, supply `.with(csrf())` in tests checking ownership.
11. Verify **no update occurred** after 403/404 via a follow-up authorized GET or DB query.
12. With a real DB, test transactions/concurrency and cache isolation rather than HTTP status alone.
13. Emit security audit logs without exposing bodies, JWTs, secrets, or cross-tenant data.
14. Whenever policies change, update the permission matrix before adjusting assertions.

## 14. Hands-on exercises

**Exercise 1 — BOLA:** Remove `.filter(row -> row.tenantId().equals(tenantId))` in `findInTenant`, then have Mallory GET order 100. Which tests fail? Point out where tenant scope was lost.

**Exercise 2 — Ownership:** Remove the `row.ownerId()` check and keep only the tenant check. Do Bob's GET/PATCH tests on Alice's order remain safe?

**Exercise 3 — Tenant admin:** Let the admin role bypass the tenant check; run the two cross-tenant admin tests. Why does “admin” not mean global by default?

**Exercise 4 — List:** Change `listMineOrTenantAdmin` to return all orders in the tenant. For regular Alice, how many records return? When would a policy actually permit shared orders?

**Exercise 5 — 401/403/404:** Exercise anonymous, user lacking `ORDER_READ`, same-tenant non-owner Bob, cross-tenant Mallory, and nonexistent ID 999. Pick consistent statuses/bodies per contract.

**Exercise 6 — Header spoof:** Send `X-Tenant-Id: tenant-b` with tenant-a principal Alice. Why is this header untrusted input? Design active-tenant selection when a legitimate user belongs to multiple tenants.

**Exercise 7 — Mass assignment:** Send JSON containing `ownerId`, `tenantId`, `isAdmin`, and `title`, verifying only `title` changes per policy. If Jackson fail-on-unknown is enabled, which status fits?

**Exercise 8 — PATCH:** Run Bob with valid CSRF, Alice without CSRF, and read-only Alice with CSRF. Why can all three receive 403 for completely different reasons?

**Exercise 9 — JDBC:** Write `UPDATE ... WHERE id=:id AND tenant_id=:tenantId AND (owner_id=:user OR :isAdmin=true)` and assert affected row counts across actors.

**Exercise 10 — JPA:** Write tenant-scoped Spring Data repository methods for findOne and list. Inspect generated SQL and verify the `COUNT` query applies the same filter.

**Exercise 11 — PostgreSQL RLS:** Enable + `FORCE` RLS, run tests with a non-`BYPASSRLS` role; run `SET LOCAL` for tenant A then B across transactions. Does data leak when connections are reused?

**Exercise 12 — Cache:** Add `@Cacheable`. If the cache key is just `id`, why can a tenant B user receive tenant A's cached result? Design a `(tenantId, id)` key.

**Exercise 13 — Background jobs:** A scheduled task lacks an HTTP `SecurityContext`. Design a service account explicitly scoped to a tenant rather than falling back to a global default tenant.

**Exercise 14 — Export & batch:** For requests accepting multiple order IDs, resolve each ID with a tenant-aware query or verify permissions for the entire set before exporting. Never leak partial unauthorized data from client-side filtering.

**Exercise 15 — Token verification:** Write a JWT converter extracting `tenantId`/permissions from validated claims; test wrong issuer, expired token, and missing tenant membership. Separate claim-mapping unit tests from real-signature integration tests.

**Exercise 16 — Property-based authorization:** Generate random `(principal, tenant, owner)` combinations and assert `crossTenantAccessAlwaysDenied`; carve out only explicit scoped exception roles.

**Exercise 17 — Concurrency:** Simulate two transactions racing to reassign ownership vs update title between check and write; ensure ownership/tenant conditions are evaluated at `UPDATE` commit time.

**Exercise 18 — Security review:** Audit all routes accepting IDs/paths/queries/bodies, build a permission matrix and negative tests before release; test actual denied objects, not just route reachability.

## 15. Official references

- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): IDOR/BOLA, verifying permissions on every object access.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege, and authorization checks.
- [OWASP Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): tenant-scoped queries, isolation, cache keys, and RLS.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and proxy behavior.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `SecurityFilterChain`, authenticated request rules.
- [Spring Security — MockMvc test authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user(UserDetails)` and `@WithMockUser`.
- [Spring Security — MockMvc CSRF testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `.with(csrf())`, CSRF failure tests.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, Spring Security test integration.
- [Spring Data JPA — Repository Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): tenant-aware query patterns.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, policies, owner/superuser bypass, `USING`/`WITH CHECK`.
- [PostgreSQL — SET](https://www.postgresql.org/docs/current/sql-set.html): session/transaction configuration and `SET LOCAL`.

**Remember:** **Permission to call an endpoint does not mean permission to open every ID.** Always check **action authority + matching tenant + owner or tenant-scoped admin**; tenant scope must be enforced before any admin branch. Derive identity from a trusted authentication source rather than granting permissions from raw headers or bodies. Write tests covering **same tenant different owner, cross-tenant, cross-tenant admin, GET list, PATCH, mass assignment, and negative cases**; after 403/404, verify data remained unchanged. For production safety, back up checks with **tenant-scoped SQL `UPDATE`/`SELECT`, database constraints, properly scoped RLS roles, JWT validation, and cross-tenant isolation tests**.
