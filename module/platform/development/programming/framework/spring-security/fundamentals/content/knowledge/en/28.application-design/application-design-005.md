# Separating Endpoint Rules, Business Policies, and Data Permissions

## 1. The core problem: three distinct authorization questions

In Spring Security, protecting a URL with `authenticated()` or `hasRole("USER")` **does not automatically prevent** a logged-in user from changing an ID in the URL to read someone else's data. Nor can an endpoint filter decide all business conditions such as "only approve DRAFT invoices," "never approve a request you created yourself," or "only access data in the same tenant."

Application design should separate three layers:

1. **Endpoint rules (HTTP/request authorization)**: who may call which HTTP method and URL? Uses `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `hasRole`/`hasAuthority`, authentication, and CSRF.
2. **Business policies (application/domain authorization)**: who may perform which action in the current business state? Uses application services, policy objects, `@PreAuthorize`, or `AuthorizationManager`; combines rules for roles, limits, timing, state, and separation of duties.
3. **Data permissions (object/tenant authorization)**: which **specific records** may the caller touch? Uses tenant/owner-scoped repository queries, ownership/relationship checks on the resource, field-level output control, and conditional/transactional updates.

Examples:

- Logged-in Alice calls `GET /api/invoices/101`. The endpoint allows authenticated requests, yet the service must still verify invoice 101 belongs to Alice's tenant and Alice is the owner or has special read permission.
- A manager with the APPROVER role calls `POST /api/invoices/101/approve`. The endpoint requires the role and a valid CSRF token; the service also checks that the invoice belongs to the same tenant, is in DRAFT status, and does not violate approval workflow rules.
- A manager in tenant A must not use the APPROVER role to approve an invoice in tenant B.

**These are three different kinds of checks, not three places to repeat the same `hasRole` call.** Learners must know which layer owns which invariant so security policy stays consistent when new REST endpoints, schedulers, message consumers, or batch jobs are added.

## 2. Responsibility table by boundary

| Layer | Question to answer | Typical tools | Should not be responsible for |
| --- | --- | --- | --- |
| **HTTP security** | Is the request public or protected? Minimum method/path/role? | `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `anyRequest().denyAll()` | Loading multiple tables and deciding business workflows |
| **Controller** | How to pass parsed HTTP input to the application service? | `@RestController`, `@PathVariable`, request DTO, `Authentication` | Persisting entities and duplicating all permission checks per endpoint |
| **Application service** | Can the actor perform this action in the current state? | `@PreAuthorize`, `@EnableMethodSecurity`, service/policy, transactions | Trusting client-supplied `ownerId`/`tenantId`/`isAdmin` |
| **Domain policy** | Which invariants do owner/tenant/action/state satisfy? | Pure Java policies, rule methods, unit tests | Depending on HTTP/cookies and status codes |
| **Repository/data** | Which scoped set of records may be queried/modified? | `findByIdAndTenantId`, `UPDATE ... WHERE tenant_id = ?`, database RLS if suitable | Inferring a trusted tenant from an unverified header |
| **Response boundary** | Which fields may be exposed to this audience? | Response DTOs, projections, field-level policies | Returning raw entities containing secrets or internal metadata |

### Examples of classifying defects accurately

- Calling a supposedly protected API without logging in: **endpoint policy** defect.
- A user with APPROVER approves an already closed invoice or exceeds an amount limit: **business policy** defect.
- Alice swaps an invoice ID to view Bob's invoice: **object-level authorization (BOLA/IDOR)** defect.
- The API checks the object yet returns `internalNote` or `paymentToken`: **property/data exposure** defect, requiring response DTOs and field authorization.

A team easily misses test cases if it uses a blanket label like "authorization is done" without specifying which object types and actions are protected.

## 3. Request-to-data processing flow

```text
HTTP request
    │
    ▼
Spring Security FilterChainProxy
    ├─ authentication (Basic / session / Bearer ...)
    ├─ CSRF if required by policy
    └─ authorizeHttpRequests
           │ Fails -> 401 / 403 / redirect
           ▼
Controller
    └─ receive id/DTO, pass Authentication to service
           ▼
Method security + application service
    ├─ @PreAuthorize for action/authority
    ├─ resolve actor and tenant from verified source
    ├─ repository: query by id + tenant
    ├─ owner/object policy, status, limit, separation of duties
    └─ conditional write inside transaction
           │ Fails -> 403 / 404 / 409 (per contract)
           ▼
Response DTO with sensitive fields stripped
           ▼
HTTP response
```

The order is intentional: **HTTP rules block early**, the service enforces invariants that hold even outside HTTP, the repository narrows data scope from the start, and the response DTO limits what leaves the system. Never rely on unguessable IDs/UUIDs as a substitute for authorization.

## 4. HTTP layer: configure standard mechanisms without stuffing data logic into filters

An `HttpSecurity` pattern:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/invoices/*")
        .authenticated()
    .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
        .hasRole("APPROVER")
    .anyRequest().denyAll())
```

This is a **fragment inside `SecurityFilterChain`**, not standalone runnable code. It decides:

- Public GET `/public` is allowed.
- GET on an invoice requires an authenticated user.
- POST approve requires the `ROLE_APPROVER` authority (via `hasRole("APPROVER")`).
- Other URLs are denied by the `denyAll()` fallback.

It **does not know** whether the invoice ID exists, which tenant owns it, who the owner is, or whether it is already APPROVED. Thus using `hasRole("APPROVER")` here is a **coarse-grained permission**, not final clearance to modify any arbitrary record.

With Spring MVC, matchers can evaluate HTTP method, pattern, and rule order. In an app with multiple `SecurityFilterChain` beans, `securityMatcher` selects the applicable chain while `requestMatchers` selects rules within that chain. Avoid configuring chains without a fallback that leave requests unprotected.

**Important misconception:** `permitAll()` removes the authorization requirement for that matcher; it does **not** mean all CSRF, security headers, or authentication filters in the chain are skipped. Meanwhile `web.ignoring()` can cause requests to bypass the entire security filter chain; never use ignoring carelessly to work around 401/403 errors.

## 5. Business layer: authorize the action, not just the URL call

Example requirement: "A user with the APPROVER permission may approve an invoice in the same tenant if its status is DRAFT." The condition can be expressed as:

```text
canApprove =
    actor is authenticated
    AND actor has APPROVER role/permission
    AND invoice belongs to actor's authorized tenant
    AND invoice.status == DRAFT
    AND does not violate separation-of-duties/limit rules
```

Using `@EnableMethodSecurity` and annotations on the service is one option:

```java
@PreAuthorize("hasRole('APPROVER')")
public InvoiceView approve(long invoiceId, Authentication actor) {
    // Body must still check tenant, state, and perform conditional update.
}
```

This snippet is a **fragment**, not a standalone runnable file. `@PreAuthorize` requires the authority before the method executes via the Spring AOP proxy; it does not automatically know whether the invoice is DRAFT or which tenant owns it. When the service is called from another controller, `@PreAuthorize` still helps; however, **self-invocation** (a method on the same bean calling `this.approve(...)`) can bypass the proxy. Never rely solely on annotations to protect invariants when calls may bypass the proxy.

Other business policies include: monetary limits, frequency caps, preventing creators from approving their own requests, restricting actions to email-verified users, state-machine-valid transitions, write-time permission checks, and "two-person approval" rules. For complex cases, extract the policy into a Java object with unit tests; avoid long SpEL expressions performing multiple DB queries inside HTTP filters.

## 6. Data layer: BOLA/IDOR, tenant, owner, and query scope

**Broken Object Level Authorization (BOLA)** occurs when an API accepts a client-controlled object ID without verifying that the actor has permission for **that specific ID**. Alice can call a valid endpoint, change `/101` to `/102`, and receive Bob's data.

An essential defense is constraining repositories with a **verified tenant scope**:

```java
// Illustrative signature for a Spring Data JPA repository.
Optional<InvoiceEntity> findByIdAndTenantId(
        Long id, String tenantId);
```

This is only a fragment: `InvoiceEntity` must be a real entity in a JPA application. Among users within the same tenant, you still need **owner or equivalent permission**. Tenant scoping isolates organizations, whereas owner/access policies isolate resources belonging to users within the same organization.

**Tenant source must not be self-asserted by the client:** an `X-Tenant-Id` header or `tenantId` JSON field may indicate the requested tenant, yet the server must verify the user's membership and role in that tenant. For JWTs, claims must come from a trusted issuer and pass signature/issuer/audience validation per policy; never Base64-decode and trust values blindly.

**404 vs. 403:** you may choose 404 for records outside the tenant so existence is not leaked, and 403 for same-tenant records lacking owner/role permission. This is an API contract decision that must remain consistent across error bodies and timing. Unguessable IDs never replace authorization checks.

## 7. Runnable Java 17+ example: separating three layers in an invoice API

The project uses **Spring Boot 3.5.7, Spring Security 6.x, Spring MVC, Java 17+**. An in-memory repository stands in for a database to keep focus on layering. HTTP Basic enables quick testing; CSRF stays enabled for `POST`. Never use demo accounts or plain-text HTTP in production.

### 7.1. Actors and sample data

| Principal / demo password | Authority | Tenant |
| --- | --- | --- |
| `alice / alice-pass` | `ROLE_USER` | tenant-a |
| `clara / clara-pass` | `ROLE_USER` | tenant-a |
| `bob / bob-pass` | `ROLE_USER` | tenant-b |
| `manager / manager-pass` | `ROLE_APPROVER` | tenant-a |

| Invoice ID | Owner | Tenant | Status |
| --- | --- | --- | --- |
| 101 | alice | tenant-a | DRAFT |
| 102 | bob | tenant-b | DRAFT |
| 103 | clara | tenant-a | DRAFT |
| 104 | clara | tenant-a | APPROVED |

Demo policy:

- `GET /public` requires no login.
- `GET /api/invoices/{id}` requires login. Owners may read invoices in their tenant; APPROVERs may read invoices in the same tenant.
- `POST /api/invoices/{id}/approve` requires APPROVER, same tenant, DRAFT invoice, and a valid CSRF token.
- `anyRequest().denyAll()` acts as fallback.

Alice can read 101, **cannot** read 103 despite sharing the same tenant, and certainly cannot read 102 in tenant-b. Manager can read/approve invoices in tenant-a but cannot cross into tenant-b.

### 7.2. File structure

```text
security-layers/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── SecurityLayersApplication.java
    │   └── InvoiceAccessPolicy.java
    └── test/java/demo/
        ├── InvoiceAccessPolicyTest.java
        └── SecurityLayersIntegrationTest.java
```

### 7.3. `pom.xml` — complete with plugin wrapper

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-layers</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.4. Pure Java policy: `InvoiceAccessPolicy.java`

```java
package demo;

public final class InvoiceAccessPolicy {

    private InvoiceAccessPolicy() {}

    public static boolean canRead(
            String actorTenant,
            String invoiceTenant,
            String actorUsername,
            String invoiceOwner,
            boolean approverRole) {

        if (actorTenant == null || invoiceTenant == null
                || actorUsername == null || invoiceOwner == null) {
            return false;
        }

        return actorTenant.equals(invoiceTenant)
                && (actorUsername.equals(invoiceOwner) || approverRole);
    }
}
```

The policy **has no Spring or HTTP dependencies**, making it easy to unit test. `approverRole` must be derived by the service from the Spring Security–verified `Authentication`, never accepted from client JSON.

### 7.5. Main application: `SecurityLayersApplication.java`

```java
package demo;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityLayersApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLayersApplication.class, args);
    }

    // Endpoint policy: do not query invoice/tenant here.
    @Bean
    SecurityFilterChain httpRules(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/invoices/*")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/invoices/*/approve")
                            .hasRole("APPROVER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER").build(),
                User.withUsername("clara")
                        .password(encoder.encode("clara-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER").build(),
                User.withUsername("manager")
                        .password(encoder.encode("manager-pass"))
                        .roles("APPROVER").build());
    }

    public record Actor(String username, String tenantId) {}
    public enum InvoiceStatus { DRAFT, APPROVED }
    public record Invoice(
            long id, String tenantId, String ownerUsername,
            long amountCents, InvoiceStatus status) {}
    public record InvoiceView(
            long id, long amountCents, String status) {}

    @Service
    public static class ActorDirectory {
        // Demo: server-managed tenant map.
        public Actor require(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()) {
                throw new AccessDeniedException("Not authenticated");
            }
            String name = auth.getName();
            String tenant = switch (name) {
                case "alice", "clara", "manager" -> "tenant-a";
                case "bob" -> "tenant-b";
                default -> throw new AccessDeniedException(
                        "Unknown tenant membership");
            };
            return new Actor(name, tenant);
        }
    }

    @Repository
    public static class InvoiceRepository {
        private final ConcurrentHashMap<Long, Invoice> rows =
                new ConcurrentHashMap<>();

        public InvoiceRepository() {
            rows.put(101L, new Invoice(
                    101L, "tenant-a", "alice", 10000L,
                    InvoiceStatus.DRAFT));
            rows.put(102L, new Invoice(
                    102L, "tenant-b", "bob", 20000L,
                    InvoiceStatus.DRAFT));
            rows.put(103L, new Invoice(
                    103L, "tenant-a", "clara", 30000L,
                    InvoiceStatus.DRAFT));
            rows.put(104L, new Invoice(
                    104L, "tenant-a", "clara", 40000L,
                    InvoiceStatus.APPROVED));
        }

        public Optional<Invoice> findByIdInTenant(
                long id, String tenant) {
            return Optional.ofNullable(rows.get(id))
                    .filter(inv -> inv.tenantId().equals(tenant));
        }

        public boolean approveDraftInTenant(
                long id, String tenant) {
            AtomicBoolean changed = new AtomicBoolean(false);
            rows.computeIfPresent(id, (key, previous) -> {
                if (!previous.tenantId().equals(tenant)
                        || previous.status() != InvoiceStatus.DRAFT) {
                    return previous;
                }
                changed.set(true);
                return new Invoice(
                        previous.id(),
                        previous.tenantId(),
                        previous.ownerUsername(),
                        previous.amountCents(),
                        InvoiceStatus.APPROVED);
            });
            return changed.get();
        }
    }

    @Service
    public static class InvoiceService {
        private final InvoiceRepository repo;
        private final ActorDirectory directory;

        public InvoiceService(
                InvoiceRepository repo, ActorDirectory directory) {
            this.repo = repo;
            this.directory = directory;
        }

        @PreAuthorize("isAuthenticated()")
        public InvoiceView read(
                long id, Authentication auth) {
            Actor actor = directory.require(auth);
            Invoice invoice = repo.findByIdInTenant(
                    id, actor.tenantId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND));

            boolean approver = auth.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_APPROVER".equals(
                            a.getAuthority()));

            if (!InvoiceAccessPolicy.canRead(
                    actor.tenantId(), invoice.tenantId(),
                    actor.username(), invoice.ownerUsername(),
                    approver)) {
                throw new AccessDeniedException(
                        "Access denied to invoice");
            }
            return toView(invoice);
        }

        @PreAuthorize("hasRole('APPROVER')")
        public InvoiceView approve(
                long id, Authentication auth) {
            Actor actor = directory.require(auth);
            Invoice current = repo.findByIdInTenant(
                    id, actor.tenantId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND));

            if (current.status() != InvoiceStatus.DRAFT) {
                throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Invoice is not in DRAFT state");
            }

            if (!repo.approveDraftInTenant(
                    id, actor.tenantId())) {
                throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Invoice changed concurrently");
            }

            Invoice updated = repo.findByIdInTenant(
                    id, actor.tenantId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND));
            return toView(updated);
        }

        private static InvoiceView toView(Invoice invoice) {
            return new InvoiceView(
                    invoice.id(),
                    invoice.amountCents(),
                    invoice.status().name());
        }
    }

    @RestController
    public static class InvoiceController {
        private final InvoiceService service;

        public InvoiceController(InvoiceService service) {
            this.service = service;
        }

        @GetMapping("/public")
        public String publicPage() {
            return "public";
        }

        @GetMapping("/api/invoices/{id}")
        public InvoiceView read(
                @PathVariable long id,
                Authentication auth) {
            return service.read(id, auth);
        }

        @PostMapping("/api/invoices/{id}/approve")
        public InvoiceView approve(
                @PathVariable long id,
                Authentication auth) {
            return service.approve(id, auth);
        }
    }
}
```

### 7.6. Layer-by-layer explanation

**HTTP filter:** `httpRules` applies coarse method/path/role checks without ever reading tenants or invoices. `httpBasic` uses the standard provider and encoder; demo users are encoded in `UserDetailsService`. `formLogin` is explicitly disabled so curl API tests receive a Basic challenge; CSRF remains enabled.

**Business service:** `@EnableMethodSecurity` activates `@PreAuthorize` on the Spring-managed `InvoiceService`. `approve` requires APPROVER, checks DRAFT status, and only updates while the repository still holds that state, returning 409 if the state has changed. Service policies do not depend on a single controller.

**Data scope:** `ActorDirectory` resolves the tenant from the authenticated principal and server-side mapping. The repository filters by `id + tenant`. `InvoiceAccessPolicy` further enforces same-tenant and (owner or APPROVER). A tenant-A approver cannot cross into tenant-B.

**Concurrent updates:** `ConcurrentHashMap.computeIfPresent` checks tenant/status inside the map's atomic update operation. This simulates the spirit of *check and write atomically*; real databases require transactions, conditional SQL, or optimistic locking—never use a map as production persistence.

**Output DTO:** `InvoiceView` exposes only ID, amount, and status. Never automatically return internal entities or tenant/owner fields.

**Passwords and CSRF:** demo passwords are for learning only; production must use TLS and an appropriate secret store. When browsers use Basic or cookie sessions, CSRF cannot be skipped casually; this lesson keeps CSRF enabled and tests POSTs with Spring Security Test.

## 8. Unit test: policy before writing the controller

`src/test/java/demo/InvoiceAccessPolicyTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class InvoiceAccessPolicyTest {

    @Test
    void ownerMayReadSameTenant() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                "alice", "alice", false)).isTrue();
    }

    @Test
    void sameTenantDoesNotGrantAllObjects() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                "alice", "clara", false)).isFalse();
    }

    @Test
    void approverCanReadWithinTenant() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                "manager", "clara", true)).isTrue();
    }

    @Test
    void approverCannotCrossTenantBoundary() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-b",
                "manager", "bob", true)).isFalse();
    }

    @Test
    void missingPrincipalFailsClosed() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                null, "alice", true)).isFalse();
    }
}
```

With pure Java `InvoiceAccessPolicy`, unit tests immediately catch mistakes like writing `sameTenant || approver`, which would allow cross-tenant access. However, they **do not** prove the controller/service actually calls the policy or that security filters are wired; integration tests are needed.

## 9. Integration test: testing HTTP, service methods, and object scope

`src/test/java/demo/SecurityLayersIntegrationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityLayersIntegrationTest {

    @Autowired MockMvc mvc;

    @Autowired
    SecurityLayersApplication.InvoiceService service;

    @Test
    void publicEndpointAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadInvoice() throws Exception {
        mvc.perform(get("/api/invoices/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordRejected() throws Exception {
        mvc.perform(get("/api/invoices/101")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerInvoice() throws Exception {
        mvc.perform(get("/api/invoices/101")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101));
    }

    @Test
    void aliceCannotReadClarasInvoiceInSameTenant()
            throws Exception {
        mvc.perform(get("/api/invoices/103")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotAccessAnotherTenant() throws Exception {
        mvc.perform(get("/api/invoices/102")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void managerCanReadWithinTenant() throws Exception {
        mvc.perform(get("/api/invoices/103")
                        .with(httpBasic("manager", "manager-pass")))
                .andExpect(status().isOk());
    }

    @Test
    void managerCannotCrossTenant() throws Exception {
        mvc.perform(get("/api/invoices/102")
                        .with(httpBasic("manager", "manager-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void ordinaryUserCannotApprove() throws Exception {
        mvc.perform(post("/api/invoices/103/approve")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void csrfStillProtectsStateChange() throws Exception {
        mvc.perform(post("/api/invoices/103/approve")
                        .with(httpBasic("manager", "manager-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void managerCannotApproveOtherTenant() throws Exception {
        mvc.perform(post("/api/invoices/102/approve")
                        .with(httpBasic("manager", "manager-pass"))
                        .with(csrf()))
                .andExpect(status().isNotFound());
    }

    @Test
    void alreadyApprovedInvoiceReturnsConflict() throws Exception {
        mvc.perform(post("/api/invoices/104/approve")
                        .with(httpBasic("manager", "manager-pass"))
                        .with(csrf()))
                .andExpect(status().isConflict());
    }

    @Test
    void managerMayApproveDraftWithinTenant() throws Exception {
        mvc.perform(post("/api/invoices/101/approve")
                        .with(httpBasic("manager", "manager-pass"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directServiceInvocationAlsoNeedsApproverRole() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

        assertThatThrownBy(() -> service.approve(103L, auth))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Meaning of the results:**

- 401 on anonymous or wrong password: handled by the HTTP Basic authentication filter/provider.
- 403 for Alice reading invoice 103: same tenant yet not owner/approver; **data object policy** denies access.
- 404 for invoice 102 when caller is in tenant-a: repository does not leak tenant-b data.
- 403 for Alice POST approve: coarse endpoint role check blocks upfront.
- 403 for Manager POST missing CSRF: `CsrfFilter` protects unsafe methods.
- 409 for invoice 104: business workflow forbids re-approving.
- 200 for manager approving invoice 101: role + tenant + DRAFT + CSRF all pass.
- Direct call test to `service.approve` with `@WithMockUser` USER throws `AccessDeniedException`: method security on the Spring bean is enforced even outside the controller.

`@WithMockUser` does not verify passwords; requests using `httpBasic()` test authentication through the filters. `MockMvc` tests do not open a port, yet because the Spring context and filter chain are loaded they remain integration tests. If real sockets must be checked, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an HTTP client—that is not a browser test unless a real browser engine runs.

Only the test approving invoice 101 mutates state; the remaining tests do not assume 101 stays DRAFT. With a real DB or parallel test runs, use fixtures/data reset, transactions, and concurrency tests.

## 10. Running and comparing statuses

Requires Java 17+ and Maven; run in the directory containing `pom.xml`:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/security-layers-0.0.1-SNAPSHOT.jar
```

In a second terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/invoices/101
curl -i -u alice:alice-pass http://localhost:8080/api/invoices/101
curl -i -u alice:alice-pass http://localhost:8080/api/invoices/103
curl -i -u alice:alice-pass http://localhost:8080/api/invoices/102
curl -i -u manager:manager-pass http://localhost:8080/api/invoices/103
curl -i -u manager:manager-pass http://localhost:8080/api/invoices/102
```

Expected statuses: **200, 401, 200, 403, 404, 200, 404**. JSON when reading invoice 101 before approval looks like:

```json
{
  "id": 101,
  "amountCents": 10000,
  "status": "DRAFT"
}
```

If you run POST approve with `curl` using only Basic credentials **without a CSRF token**, the result is 403. Do not disable CSRF just because the demo command omits a token; `.with(csrf())` in Spring Security Test simulates a valid token. Real applications need a CSRF strategy tailored to their authentication mechanism, cookie vs. Bearer-only clients, and browser auto-send risks.

**Runtime limitation:** the example stores state in `ConcurrentHashMap`, which is lost on restart and lacks DB migrations, lockouts, or auditing. It is an architectural illustration, not a production-deployable application.

## 11. Moving to a real database: conditional queries and updates

Queries must filter by tenant right from the start:

```sql
SELECT id, tenant_id, owner_username, amount_cents, status
FROM invoice
WHERE id = :invoice_id
  AND tenant_id = :tenant_id;
```

For the DRAFT → APPROVED workflow, updates should enforce the condition inside the database:

```sql
UPDATE invoice
SET status = 'APPROVED'
WHERE id = :invoice_id
  AND tenant_id = :tenant_id
  AND status = 'DRAFT';
```

These SQL snippets are **conceptual templates**, not DB connection code from the demo above. The `tenant_id` value must be resolved from a verified actor/issuer. Check the updated row count: 0 may mean the ID does not exist, the wrong tenant, or the state already changed; the service returns 404 or 409 accordingly.

Why enforce the condition inside the `UPDATE`? Because one request may read DRAFT, and another request may approve it before the first writes. **TOCTOU/race conditions** will break invariants if checked only in memory. Use transactions, optimistic locking `@Version`, or conditional updates as required, and test concurrency.

With Spring Data JPA, repositories can provide `findByIdAndTenantId(...)`, projections, and `@Modifying`/`@Query` update methods. Check list, search, export, delete, batch update, and nested sub-resources as well: **filtering only GET by ID is not enough** if export returns records across other tenants. For multi-tenant systems, database Row-Level Security adds valuable defense-in-depth, provided session/database context is set safely and never leaks across pooled connections.

## 12. Actor, tenant, role: where do permissions come from?

- **Form/HTTP Basic:** the provider verifies the password and builds `Authentication`. The service can look up user IDs and tenant memberships from a server-side database.
- **JWT Resource Server:** `JwtDecoder` must verify signature, issuer, timestamps, and audience as required by policy; the converter maps allowed `scope`, `roles`, or claims into `GrantedAuthority`. Never Base64-decode and assume a token is valid.
- **OIDC Login:** `issuer + sub` and user details/permissions must be linked to an internal app account. Display email is not always a stable unique key.
- **Multi-tenant:** if the client selects a target tenant via URL/header, the backend must still verify the actor's membership and roles in that tenant. Headers are not proof of permission.
- **Service accounts/jobs:** require dedicated principals and scopes; never auto-grant system-wide ADMIN when requests do not arrive over HTTP.

**A role does not automatically carry every permission:** `ROLE_APPROVER` only means what application policy defines; it does not imply `ROLE_USER` or access to every tenant. If the system wants role hierarchies or combined scopes, declare and test them explicitly. Never automatically union all roles from the database and IdP claims without defining the authoritative source.

## 13. Method security: strengths and limitations

Spring Security provides `@EnableMethodSecurity` to activate `@PreAuthorize`, `@PostAuthorize`, and related method authorization mechanisms. When calling a method on a Spring-managed bean through its proxy, rules are evaluated independently of the HTTP route.

**Strengths:** a service called from multiple controllers/adapters still enforces a security boundary; policy unit tests and Spring method tests pair cleanly; custom annotations or authorization managers can be built if needed.

**Limitations:**

- `@PreAuthorize("hasRole('APPROVER')")` only knows authorities, not whether an invoice is DRAFT or its tenant unless policy logic is supplied.
- Same-bean self-invocation can bypass the proxy; private methods or objects instantiated with `new` do not automatically receive Spring method security.
- When expressions call databases or external services in overly complex ways, performance and exception handling become hard to manage; consider extracting a dedicated policy/service.
- Method security does not handle CSRF/CORS/security headers or HTTP challenges; you still need the filter chain.
- A service exception may map to 403 through security filters, whereas in pure unit tests you must assert the corresponding exception/decision.

Choose a **pure Java policy service** when business conditions are rich and need independent unit tests; choose **`AuthorizationManager`** when deeper integration with Spring's shared authorization framework is desired. Never write a custom HTTP filter just to query owners from the DB: that pulls domain state/transactions into filters, increasing risk and hurting reusability.

## 14. Status matrix and how to debug

| Case | Common result | Decision layer |
| --- | --- | --- |
| Anonymous GET invoice (HTTP Basic) | **401** | Authentication entry point |
| Valid user missing APPROVER on POST | **403** | Request/method authorization |
| Manager POST missing CSRF | **403** | CSRF filter |
| Invoice absent in tenant or belongs to another tenant | **404** | Tenant-scoped lookup |
| Same tenant, yet user lacks read permission for that invoice | **403** | Object policy |
| Approving an already APPROVED invoice | **409** | Business state |
| Valid role, tenant, state, and CSRF | **200** | All layers allow |

In form-login apps, anonymous requests may get a **302 redirect** instead of 401; Bearer token APIs have `WWW-Authenticate` and their own semantics. Never guess "403 must mean missing role": CSRF or object permissions can also return 403. When debugging, identify which layer denied first and write a test reproducing the cause.

## 15. Common architectural mistakes

1. Using only `authenticated()` and then `findById(id)` → BOLA.
2. Using only `hasRole("ADMIN")` and returning records across all tenants → over-scoped access.
3. Trusting `role`, `ownerId`, or `tenantId` from the request → callers can elevate their own permissions.
4. Cramming permissions, domain state, and SQL into servlet filters → hard to test, hard to manage transactions.
5. Copy-pasting policy into every controller → new endpoints easily forget checks.
6. Forgetting `@EnableMethodSecurity` while assuming annotations are enforced.
7. Self-invocation bypassing the proxy → `@PreAuthorize` never runs.
8. Writing `sameTenant || approver` instead of `sameTenant && (owner || approver)`.
9. Checking DRAFT status upfront while running an `UPDATE` without `WHERE status` → race/TOCTOU.
10. Filtering by tenant only on GET while forgetting list/export/batch/delete.
11. Relying on unguessable IDs instead of object authorization.
12. Returning raw JPA entities containing PII, internal notes, or secrets.
13. Using an overly broad `permitAll` fallback for new APIs.
14. Confusing `hasRole("APPROVER")` with `hasAuthority("SCOPE_invoice.approve")`.
15. Testing only 200 success cases without testing different owners/tenants/missing CSRF.
16. "Fixing" a 403 by disabling CSRF or removing the security chain.
17. Using mock principals and claiming password or JWT cryptography was tested.
18. Logging full Bearer tokens, passwords, and session cookies to debug authorization.

## 16. Code review checklist and exercises

Before merging, verify:

- [ ] Endpoints have method/path rules and an appropriate deny-by-default fallback.
- [ ] Identity/roles/tenants originate from trusted authentication or a server-side directory.
- [ ] Business actions enforce invariants in the service, not only in UI/controllers.
- [ ] Method security is properly enabled, invoked through proxies, and tested directly.
- [ ] Queries enforce tenant/object scope; owner/permission is verified on the exact record.
- [ ] List, export, update, delete, batch, and nested objects are filtered as well.
- [ ] POST/PUT/DELETE have CSRF matching the client type and expose no sensitive data.
- [ ] State-changing operations use transactions and conditional updates to handle races.
- [ ] Response DTOs expose only intended fields, never raw entities/secrets automatically.
- [ ] Tests cover 401, 403, 404, 409, bad tokens/passwords, and cross-tenant/cross-owner access.
- [ ] Audit logs record actor/action/object/result without leaking credentials.
- [ ] When roles/tenant memberships are revoked, sessions/caches/tokens are refreshed or revoked per design.

**Self-practice questions:**

1. Why can `GET /api/invoices/102` create a BOLA vulnerability even when the endpoint uses `authenticated()`?
2. Why is a tenant-scoped query still insufficient when Alice and Clara share a tenant but do not own the same invoice?
3. Should a tenant-a APPROVER role be allowed to read tenant-b? Write the correct AND/OR expression.
4. When does `@PreAuthorize` add value beyond `requestMatchers`?
5. Give one vulnerability caused by self-invocation bypassing a Spring AOP proxy and how to structure services to avoid it.
6. Why can checking DRAFT in Java without constraining status in the SQL `UPDATE` fail under two concurrent requests?
7. Can an `X-Tenant-Id` header serve as proof of membership?
8. Why must export/list APIs be checked in addition to GET by ID?
9. Identify which test proves 403 due to a missing role and which test proves 403 due to a different object owner.
10. When should you choose 404 over 403, and what is the risk of object-existence enumeration?
11. Why must services preserve invariants even if the controller already checks the same rule?
12. If switching from HTTP Basic to OAuth2 JWT, what must be verified before trusting tenant/role claims?

## 17. Official documentation

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security — MockMvc HTTP Basic Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API5:2023 — Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

**Takeaway:** endpoint policies decide **which requests may enter a feature**; business policies decide **whether an action is valid in the current business state**; object/data policies decide **which records/tenants the actor may view or modify**. You must design and test all three rather than collapsing them into a single URL role check.
