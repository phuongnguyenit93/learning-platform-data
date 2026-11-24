# Building an Inventory of Public, Protected, and Sensitive Endpoints

> **Context:** designing REST applications with **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet/Spring MVC)**. The focus is turning an actual API list into an **endpoint matrix with verifiable security policies**: which endpoints are truly public, which require login, who may act on which data, and which operations require extra defense layers due to high risk. The endpoint table must be reconciled against `SecurityFilterChain`, method security, data policies, and tests—never treated as decorative documentation.

## 1. Why build an inventory before writing security configuration?

Growing applications accumulate many routes: catalog reading, profile viewing, order updates, administration, registration, password changes, inbound webhooks, file uploads, and report generation. If developers only configure URLs they "remember need protection," a new endpoint can accidentally inherit `permitAll` or allow access simply for being "logged in" without checking resource ownership.

For example, both endpoints require login:

- `GET /api/orders/o-1`: views order data; users should usually see only **their own orders**.
- `DELETE /api/admin/orders/o-1`: deletes an order; this is a **sensitive** operation because it destroys data and may require an admin role, auditing, and approval.

An `anyRequest().authenticated()` rule can block anonymous callers, yet **fails to distinguish an owner's read access from an admin's delete permission**. Conversely, `permitAll()` only waives identity requirements and **does not mean an endpoint is low-sensitivity**: password-reset requests or webhooks may be public at the HTTP boundary while still requiring abuse throttling or signature verification.

**Learning goals:** you will learn to collect an endpoint list, classify risk, decide actors and data policies, translate the matrix into Spring Security rules, protect objects in services, apply CSRF where appropriate, use positive/negative tests to prevent exposed endpoints, and maintain the table as the API evolves.

## 2. Three classification axes to separate

### Axis A — Who may cross the authentication boundary?

| Suggested label | Meaning | Example |
| --- | --- | --- |
| **PUBLIC** | No session/user login required to call the feature | `GET /catalog`; `POST /auth/password-reset/request` |
| **AUTHENTICATED** | Must have a valid user `Authentication` | `GET /api/me` |
| **ROLE / AUTHORITY** | Beyond login, requires a designated role/scope/permission | `DELETE /api/admin/orders/{orderId}` requires `ROLE_ADMIN` |
| **RESOURCE-SCOPED** | Must check permission on a specific **object** such as order owner, tenant, or department | `GET /api/orders/{orderId}` owner or admin only |
| **MACHINE / WEBHOOK** | Typically no user session, yet must verify signature/token/mTLS or trust boundary | `POST /webhooks/payment` |

An endpoint can combine policies simultaneously, e.g., AUTHENTICATED + RESOURCE-SCOPED + tenant constraint. For JWT-based APIs, scopes like `SCOPE_orders.read` may be used instead of roles; never equate `hasRole("ADMIN")` with `hasAuthority("SCOPE_admin")`.

### Axis B — How sensitive is the capability?

Sensitivity depends on the **impact of abuse**, not merely the HTTP method:

- **Low:** reading public data without altering state; still needs reasonable load limits.
- **Medium:** reading or editing one's own personal data, viewing internal business info.
- **High:** changing permissions, bulk data exports, canceling/deleting transactions, refunds, changing passwords, changing emails, or locking accounts.
- **Very high / privileged:** managing authentication keys, secrets, granting admin rights, payments, or large-scale deletions; typically requires step-up MFA, multi-person approval, scope limits, auditing, and rollback where applicable.

**PUBLIC does not mean LOW RISK.** `POST /auth/password-reset/request` can be abused for spam or account enumeration even without login. `POST /webhooks/provider` may lack cookies yet must verify the request comes from a valid source and defend against replay. Marking "public" on the table must be paired with an **additional safeguards** column.

### Axis C — Does the operation have side effects?

- `GET`/`HEAD` are typically for reading without mutating business state. They can still return sensitive data.
- `POST`/`PUT`/`PATCH`/`DELETE` typically have side effects; beyond authorization, define **CSRF** per cookie/browser model, input validation, idempotency, replay defense, transactions, and auditing.
- Do not assume "POST is always sensitive" or "GET is always safe." `GET /admin/export?all=true` can return highly sensitive data; `POST /search` may be read-only yet still carry cost/abuse risk. Design should reflect actual semantics and policy.
- Never accidentally mutate state via `GET`, because preloading, crawlers, caches, link previews, or CSRF assumptions can trigger unintended execution.

## 3. Which columns should an inventory table have?

Each row must describe **one combination of HTTP method + path + capability**, not a vague prefix. A useful template:

| Column | Meaning / question |
| --- | --- |
| **Method + path** | `GET /api/orders/{orderId}`, distinct from `POST /api/orders/{orderId}/cancel` |
| **Purpose** | What can the caller do, and what exact side effects occur? |
| **Public?** | PUBLIC, login required, machine-to-machine, or role required |
| **Principal / authority** | Who may call? `ROLE_ADMIN`, `SCOPE_orders.read`, which service identity? |
| **Object constraints** | Owner/tenant/unit, delegated relationship, account status? |
| **Sensitivity** | LOW / MEDIUM / HIGH / CRITICAL + rationale |
| **Input/output data** | PII, financial data, tokens; pagination limits, files, output fields |
| **Side effects** | Writes DB, sends email, triggers jobs, creates files, or alters permissions? |
| **CSRF / replay / idempotency** | Browser cookie CSRF? Does the request need an idempotency key or replay defense? |
| **Abuse controls** | Rate limits, quotas, CAPTCHA/challenges, audit events, MFA/step-up |
| **Enforcement layers** | Request matchers, `@PreAuthorize`, policy service, SQL queries, gateway |
| **Test evidence** | Anonymous, wrong permission, valid permission, cross-tenant, CSRF, business invariants |
| **Owner and review status** | Owning team, review date, reason for policy changes |

Not every project needs all columns in a massive horizontal table: you can use a summary matrix plus separate policy sheets/appendices. However, you **must record decisions**, owners, and how each entry is tested. Two endpoints sharing a path with different methods can have completely different risks, so never merge them.

## 4. Example inventory created before implementation

Context: a retail app with users `alice`/`bob`, administrator `admin`, and two sample orders. This is a **design matrix** covering both endpoints coded in the example and illustrative future endpoints.

### 4.1. Endpoints implemented in section 6 code

| Method & endpoint | Access level | Resource authorization | Sensitivity / side effects | Safeguards / primary checks |
| --- | --- | --- | --- | --- |
| `GET /catalog` | PUBLIC | No user required | LOW, read-only public catalog | Anonymous 200; returns no private data |
| `GET /api/me` | AUTHENTICATED | Returns only the **current request's** identity | MEDIUM, minimal personal data | Anonymous 401; user 200 |
| `GET /api/orders/{orderId}` | AUTHENTICATED | **Owner or ADMIN** in service | HIGH, reads private order/PII | Bob cannot read Alice's order (403); Alice 200 |
| `POST /api/orders/{orderId}/cancel` | AUTHENTICATED | **Owner or ADMIN** in service | HIGH, transitions order state | Check CSRF, OPEN status, audit, production transaction |
| `DELETE /api/admin/orders/{orderId}` | `ROLE_ADMIN` at HTTP **and** service | Admin permitted, still validates state/data | HIGH/CRITICAL, deletes record | 403 for user, 204 for admin; audit/approval/soft-delete in prod |
| **All other methods/paths** | DENY BY DEFAULT | Not applicable | No APIs opened automatically | Even authenticated callers are denied |

**Important note:** the `GET /api/orders/{orderId}` row requires login at `SecurityFilterChain`, yet the **owner/tenant check** runs in the service. Writing only `authenticated()` without an object check lets user B probe user A's order IDs (BOLA/IDOR). Row-level policy is part of the security policy, not an optional "if we have time" item.

### 4.2. Endpoints omitted from demo code that belong in a real inventory

| Planned method & endpoint | Why does it need attention? | Recommended policy |
| --- | --- | --- |
| `POST /auth/password-reset/request` | Public yet vulnerable to spam or username enumeration | Generic public response, multi-dimensional rate limits, one-time OTP/reset token, TTL, audit; never log tokens |
| `POST /auth/password-reset/confirm` | No user session yet carries reset proof | Verify high-entropy random token, TTL, one-time use, replay defense, rotate sessions/credentials as needed |
| `POST /webhooks/payment` | Receives requests from partners without user sessions | Verify signature/mTLS per contract, timestamp/replay window, idempotency, body limits, audit; `permitAll` alone is never enough |
| `POST /api/admin/users/{id}/grant-role` | Modifies privileges with broad blast radius | ADMIN + separation of duties, risk-based step-up MFA/approval, immutable audit, prevent excessive self-elevation |
| `GET /api/admin/exports` or `POST /api/admin/exports` | Bulk data export even though it is "read-only" | Restrict scopes, per-dataset authorization, rate/quotas, watermarking/audit, retention, and export file protection |
| `POST /api/payments/refunds` | Refunds/balance changes | Role + transaction limits + step-up/dual-control, idempotency key, replay defense, transactions, and audit |
| `GET /actuator/health` | Commonly used for monitoring | Expose only necessary health info; evaluate other actuator endpoints separately |
| `/swagger-ui/**` and `/v3/api-docs/**` | API docs can expose system structure | Decide public vs. internal-only and apply proper security in real environments |
| `/ws/**`, GraphQL, gRPC, background jobs | Not every entrypoint is an HTTP MVC controller | Separate inventory for handshake/subscription/operations, message consumers, actors, and policies |

These endpoints are **design guidance**, **not automatically present** in the demo application. When implementing them, determine actual methods/paths, data formats, authentication mechanisms, gateway/service protections, and corresponding tests.

## 5. Turning the inventory into Spring Security rules

### 5.1. HTTP protection by method + path

In Spring Security 6, `HttpSecurity.authorizeHttpRequests(...)` declares the rules:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/catalog").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
        .requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
                .authenticated()
        .requestMatchers(HttpMethod.POST,
                "/api/orders/{orderId}/cancel").authenticated()
        .requestMatchers(HttpMethod.DELETE,
                "/api/admin/orders/{orderId}").hasRole("ADMIN")
        .anyRequest().denyAll())
```

This is a **configuration fragment**; the full runnable code is in section 6. Several mandatory caveats:

- `requestMatchers(HttpMethod.GET, ...)` matches **GET only** and does not implicitly open POST/DELETE on the same URL. Specific rules should precede fallbacks.
- `hasRole("ADMIN")` expects the `ROLE_ADMIN` authority under the default prefix; `hasAuthority("SCOPE_orders.write")` matches the exact authority string. Never prepend `ROLE_` manually when calling `hasRole`.
- `anyRequest().denyAll()` ensures unlisted endpoints/methods do not open automatically just because a caller logged in. This creates healthy pressure to review and update the inventory whenever new routes appear.
- `permitAll()` is an **authorization decision**, not a switch disabling all filters. Sending a bad HTTP Basic header even to a public endpoint can be rejected by the authentication filter before reaching `permitAll`.
- With **multiple `SecurityFilterChain` beans**, `@Order` + `securityMatcher` select the chain first, and then `requestMatchers` inside the **selected chain** are evaluated. Any route matching no chain risks bypassing Spring Security altogether, so review overall coverage.
- A complete inventory table also accounts for context path, servlet mappings, trailing slashes, HTTP methods, CORS/preflight, `ERROR`/`FORWARD` dispatchers, and framework/actuator endpoints when relevant.

### 5.2. Request-level checks are insufficient for owner/tenant

The `authenticated()` rule on `GET /api/orders/{orderId}` only verifies an identity exists. It **does not know** whether order `o-1` belongs to Alice or Bob. You need method-level policy in the service or data constraints checked on every call path.

With Spring Security 6, you can enable `@EnableMethodSecurity` and use:

```java
@PreAuthorize("hasRole('ADMIN') or "
        + "@orderPolicy.isOwner(authentication, #orderId)")
public OrderView get(@P("orderId") String orderId) {
    return store.find(orderId).orElseThrow(OrderMissing::new);
}
```

This is an illustrative snippet inside `OrderService`; the full class and imports appear in section 6. `@P("orderId")` supplies the parameter name to SpEL, avoiding full reliance on compiler flags. `orderPolicy` returns an **access decision**, never trusting client-supplied owner IDs.

**Critical issue:** method security uses proxies. Protected methods must be invoked through the Spring bean/proxy; calling `this.get(...)` inside the same instance may skip the interceptor. Add tests from controller through service to prove the policy executes, and protect other entry points calling the service from jobs/message listeners as needed.

### 5.3. High sensitivity requires more than one role

An order-deletion endpoint using `hasRole("ADMIN")` is only the **front gate**. A real system may also need:

- The admin must belong to the appropriate tenant/unit; a global role does not automatically apply across every tenant.
- High-value actions require step-up MFA, identity re-confirmation, or peer approval.
- Rules like "never delete a paid order" are **business rules**, not substitutes for authorization.
- Audit events containing actor, operation, policy-sanitized resource ID, outcome, timestamp, and correlation ID; never log passwords/tokens.
- Soft deletes, retention/legal hold, idempotency, transactional/locking writes, recovery, and appropriate error responses.
- Rate limits, anomaly detection, and abuse alerts.

**The runnable example illustrates only role + method security + CSRF + one simple invariant.** It does **not** implement MFA, two-person approval, durable audit logs, or persistence. Never deploy the demo app to production simply because tests pass.

## 6. Complete Java 17+ example: matrix -> code

### 6.1. Dependencies

Create a Spring Boot 3.x project with Java 17+ and Spring MVC. In `build.gradle` with the Spring Boot plugin applied, add this block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the `dependencies` block, **not a complete Gradle file**. The example uses `InMemoryUserDetailsManager` and `ConcurrentHashMap` to avoid database dependencies. All users/passwords and orders are learning fixtures.

### 6.2. Runnable single-file application code

Create **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/catalog")
                                .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                                .authenticated()
                        .requestMatchers(HttpMethod.GET,
                                "/api/orders/{orderId}")
                                .authenticated()
                        .requestMatchers(HttpMethod.POST,
                                "/api/orders/{orderId}/cancel")
                                .authenticated()
                        .requestMatchers(HttpMethod.DELETE,
                                "/api/admin/orders/{orderId}")
                                .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

enum OrderStatus {
    OPEN, SHIPPED, CANCELLED
}

record OrderView(String id, String owner, OrderStatus status) {
}

class OrderMissing extends RuntimeException {
}

class OrderConflict extends RuntimeException {
}

@Repository
class OrderStore {
    private final Map<String, OrderView> orders =
            new ConcurrentHashMap<>();

    OrderStore() {
        reset();
    }

    synchronized void reset() {
        orders.clear();
        orders.put("o-1", new OrderView(
                "o-1", "alice", OrderStatus.OPEN));
        orders.put("o-2", new OrderView(
                "o-2", "bob", OrderStatus.SHIPPED));
    }

    Optional<OrderView> find(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    synchronized OrderView cancel(String id) {
        OrderView order = orders.get(id);
        if (order == null) {
            throw new OrderMissing();
        }
        if (order.status() != OrderStatus.OPEN) {
            throw new OrderConflict();
        }
        OrderView changed = new OrderView(
                order.id(), order.owner(), OrderStatus.CANCELLED);
        orders.put(id, changed);
        return changed;
    }

    synchronized void delete(String id) {
        if (orders.remove(id) == null) {
            throw new OrderMissing();
        }
    }
}

@Component("orderPolicy")
class OrderPolicy {
    private final OrderStore store;

    OrderPolicy(OrderStore store) {
        this.store = store;
    }

    public boolean isOwner(Authentication authentication, String orderId) {
        return authentication != null
                && store.find(orderId)
                        .map(order ->
                                order.owner().equals(authentication.getName()))
                        .orElse(false);
    }
}

@Service
class OrderService {
    private final OrderStore store;

    OrderService(OrderStore store) {
        this.store = store;
    }

    @PreAuthorize("hasRole('ADMIN') or "
            + "@orderPolicy.isOwner(authentication, #orderId)")
    public OrderView get(@P("orderId") String orderId) {
        return store.find(orderId).orElseThrow(OrderMissing::new);
    }

    @PreAuthorize("hasRole('ADMIN') or "
            + "@orderPolicy.isOwner(authentication, #orderId)")
    public OrderView cancel(@P("orderId") String orderId) {
        return store.cancel(orderId);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void delete(@P("orderId") String orderId) {
        store.delete(orderId);
    }
}

@RestController
class DemoController {
    private final OrderService orderService;

    DemoController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/catalog")
    public String catalog() {
        return "public-catalog";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/orders/{orderId}")
    public OrderView get(@PathVariable String orderId) {
        return orderService.get(orderId);
    }

    @PostMapping("/api/orders/{orderId}/cancel")
    public OrderView cancel(@PathVariable String orderId) {
        return orderService.cancel(orderId);
    }

    @DeleteMapping("/api/admin/orders/{orderId}")
    public ResponseEntity<Void> delete(@PathVariable String orderId) {
        orderService.delete(orderId);
        return ResponseEntity.noContent().build();
    }
}

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(OrderMissing.class)
    ResponseEntity<Map<String, String>> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "order_not_found"));
    }

    @ExceptionHandler(OrderConflict.class)
    ResponseEntity<Map<String, String>> conflict() {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("code", "invalid_order_state"));
    }
}
```

**Runnability check:** only `DemoApplication` is `public`; the other classes/enums/records share package `demo` and are not declared `public`. Spring Boot scans `@Configuration`, `@Repository`, `@Component`, `@Service`, and `@RestController` under package `demo`. `record`, `ConcurrentHashMap`, and Java syntax are Java 17 compatible. All endpoints using `HttpMethod` and Spring MVC annotations have complete imports in the file.

### 6.3. Role of each layer compared to the table

**`SecurityConfig`** decides initial protection by HTTP method + path:

- `GET /catalog` has `permitAll`.
- `GET /api/me` and user order routes require an identity.
- `DELETE /api/admin/orders/{orderId}` requires the admin role at the URL.
- Paths not listed in the inventory fall into `denyAll`.

**`OrderPolicy` and `OrderService`** decide per-object permissions:

- `OrderPolicy.isOwner(...)` looks up the owner from server-side data. Clients cannot supply another owner to hijack access.
- `@PreAuthorize` allows admin **or** owner on `get`/`cancel`, and admin only on `delete`. If callers invoke the service via another path, method policy still enforces when called through the Spring-managed proxy.
- `OrderStore.cancel(...)` protects the `OPEN -> CANCELLED` invariant. A `SHIPPED` order cannot be canceled by this operation: returns 409 even when the owner/admin has permission to call it.
- `OrderStore.delete(...)` actually removes from memory to illustrate side effects; it does **not** represent a production data deletion design. Real systems need auditing, recovery/soft delete, transactions/locking, and domain/retention checks.

**`DemoController`** only forwards requests to the service and returns required data. **`ApiErrors`** maps domain errors (404/409) without catching all `AccessDeniedException` or `AuthenticationException` instances to alter security filter statuses.

**CSRF protection:** configuration keeps Spring Security defaults with no `csrf.disable()`. For unsafe HTTP methods such as POST/DELETE, tests must send a CSRF token via helper. HTTP Basic in browser environments can still involve CSRF; deciding to disable/keep it for a stateless machine-to-machine API requires evaluating the credential model and trust boundary separately. Never use a "disable all CSRF so curl works" snippet as default guidance.

## 7. Testing from the table: every row gets positive + negative cases

### 7.1. Setting up tests

Create **`src/test/java/demo/EndpointInventoryTest.java`**. Uses the declared `spring-boot-starter-test` and `spring-security-test`.

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointInventoryTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderStore store;

    @BeforeEach
    void resetData() {
        store.reset();
    }

    @Test
    void catalogIsPublic() throws Exception {
        mvc.perform(get("/catalog"))
                .andExpect(status().isOk())
                .andExpect(content().string("public-catalog"));
    }

    @Test
    void profileRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongCredentialsCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserCanReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void ownerCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"))
                .andExpect(jsonPath("$.status").value("OPEN"));
    }

    @Test
    void otherUserCannotReadOrderByGuessingId() throws Exception {
        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadOrderWhenPolicyAllows() throws Exception {
        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void stateChangeWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/orders/o-1/cancel")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanCancelOpenOrderWithCsrf() throws Exception {
        mvc.perform(post("/api/orders/o-1/cancel")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("CANCELLED"));
    }

    @Test
    void otherUserCannotCancelOrderEvenWithCsrf() throws Exception {
        mvc.perform(post("/api/orders/o-1/cancel")
                        .with(httpBasic("bob", "bob-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCannotCancelShippedOrder() throws Exception {
        mvc.perform(post("/api/orders/o-2/cancel")
                        .with(httpBasic("bob", "bob-pass"))
                        .with(csrf()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("invalid_order_state"));
    }

    @Test
    void normalUserCannotUseAdminDelete() throws Exception {
        mvc.perform(delete("/api/admin/orders/o-1")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanDeleteOrderWithCsrf() throws Exception {
        mvc.perform(delete("/api/admin/orders/o-1")
                        .with(httpBasic("admin", "admin-pass"))
                        .with(csrf()))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/orders/o-1")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void unknownEndpointIsDeniedEvenWhenAuthenticated()
            throws Exception {
        mvc.perform(get("/unlisted")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }
}
```

This is a **complete test class**. `@BeforeEach` resets the data so POST/DELETE tests do not make subsequent test results order-dependent. This is a demo in-memory reset, not a transaction strategy for a production database. If a project runs tests in parallel sharing an application context, isolate storage/context appropriately rather than relying on global resets.

Run tests with the Gradle Wrapper:

```bash
./gradlew test
```

Run a specific class:

```bash
./gradlew test --tests demo.EndpointInventoryTest
```

On PowerShell:

```powershell
.\gradlew.bat test --tests demo.EndpointInventoryTest
```

There is no fixed stdout because Gradle/JUnit output formats vary; with **matching code and dependencies**, all assertions are expected to pass.

### 7.2. Mapping coverage to each inventory row

| Inventory row | Allow test | Deny / edge-case test |
| --- | --- | --- |
| `GET /catalog` | `catalogIsPublic` | Ensure body contains no private data; test other methods if needed |
| `GET /api/me` | `authenticatedUserCanReadOwnProfile` | `profileRequiresAuthentication`, `wrongCredentialsCannotReadProfile` |
| `GET /api/orders/{orderId}` | `ownerCanReadOwnOrder`, `adminCanReadOrderWhenPolicyAllows` | `otherUserCannotReadOrderByGuessingId` |
| `POST /api/orders/{orderId}/cancel` | `ownerCanCancelOpenOrderWithCsrf` | Missing CSRF, wrong owner, `SHIPPED` state |
| `DELETE /api/admin/orders/{orderId}` | `adminCanDeleteOrderWithCsrf` | `normalUserCannotUseAdminDelete` |
| `anyRequest().denyAll()` | No positive case needed for fallback | `unknownEndpointIsDeniedEvenWhenAuthenticated` |

**Object-level permissions must be tested**: testing only that admin succeeds and anonymous fails can miss user A reading user B's order. IDOR/BOLA tests are vital for systems with owner/tenant-bound resources.

**CSRF must be tested separately**: `stateChangeWithoutCsrfIsRejected` shows requests are blocked even with valid user credentials; `ownerCanCancelOpenOrderWithCsrf` acts as the control proving business logic runs when the token is valid. HTTP 403 from CSRF **does not prove** role or object policy denied the request.

**Do not rely solely on `@WithMockUser` to test passwords**: it helps test authorization yet bypasses actual credential verification. This example uses `httpBasic(...)` to pass through the HTTP Basic authentication filter; test login/password separately whenever authentication mechanisms change.

## 8. Reading HTTP behavior from the matrix

In this example, expected responses:

| Request | HTTP | Why? |
| --- | --- | --- |
| Anonymous `GET /catalog` | 200 | PUBLIC |
| Anonymous `GET /api/me` | 401 | HTTP Basic requires authentication |
| Alice wrong password `GET /api/me` | 401 | Authentication failed |
| Alice right password `GET /api/me` | 200 | Authenticated |
| Alice `GET /api/orders/o-1` | 200 | Owner |
| Bob `GET /api/orders/o-1` | 403 | Authenticated, lacks permission on resource |
| Admin `GET /api/orders/o-1` | 200 | Policy allows admin |
| Alice `POST /api/orders/o-1/cancel` **missing CSRF** | 403 | `CsrfFilter` rejects before calling service |
| Alice `POST .../cancel` **with CSRF** | 200 | Owner + OPEN -> CANCELLED |
| Bob `POST /api/orders/o-1/cancel` with CSRF | 403 | Not owner |
| Bob `POST /api/orders/o-2/cancel` with CSRF | 409 | Authorized, yet order is `SHIPPED` |
| Alice `DELETE /api/admin/orders/o-1` with CSRF | 403 | Missing `ROLE_ADMIN` |
| Admin `DELETE /api/admin/orders/o-1` with CSRF | 204 | Permitted; deletes demo record |
| Alice `GET /unlisted` | 403 | Fallback denyAll |

Codes 401/403 here are **expected under HTTP Basic and this sample configuration**. With form login, anonymous requests may redirect to `/login` instead of 401; JWT/Bearer uses different challenges. Custom handlers may alter HTTP responses. Never use a status code alone to classify the error type: 403 may come from CSRF or authorization, while 409 usually reflects a domain conflict.

### 8.1. Quick GET checks with curl

After starting:

```bash
./gradlew bootRun
```

By default the app runs at `http://localhost:8080` if the port is free.

```bash
curl -i http://localhost:8080/catalog
curl -i http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/orders/o-1
curl -i -u bob:bob-pass http://localhost:8080/api/orders/o-1
curl -i -u admin:admin-pass http://localhost:8080/api/orders/o-1
```

On PowerShell use `curl.exe` if `curl` is aliased to `Invoke-WebRequest`. **Do not expect POST/DELETE via curl with Basic credentials alone to succeed:** this example also requires a CSRF token, so those operations are tested via MockMvc `.with(csrf())`. For real UI/browser clients, integrate CSRF tokens properly; for machine-to-machine APIs using non-auto-sent tokens, CSRF policy may differ after threat-model analysis—never disable it arbitrarily.

## 9. Process for building and maintaining the matrix on real projects

### Step 1 — Collect endpoints from multiple sources

- Spring MVC code: `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping`, `@RequestMapping` on both classes and methods; remember to include controller prefixes.
- `RequestMappingHandlerMapping` or Spring Actuator mappings when enabled and properly secured; reconcile against OpenAPI/Swagger, gateway routes, reverse proxies, and servlet mappings.
- Spring Security `SecurityFilterChain`, `securityMatcher`, `requestMatchers`, method security, custom `AuthorizationManager`, and role/scope policies.
- Non-MVC entrypoints: GraphQL, gRPC, WebSockets, webhook handlers, scheduled jobs, message consumers, file uploads/downloads, static files, and monitoring endpoints.

Never treat OpenAPI as absolute truth: an endpoint may exist in code without being documented yet, or docs may still list deleted routes. An official inventory needs a **continuous reconciliation process** against routing/runtime.

### Step 2 — Classify data and side effects

For each method + path, document the data read/written, who owns it, sensitivity level, external systems affected (email, payments, exports, jobs), what higher roles may override, and which invariants **must never be bypassed**. Distinguish "view transaction" from "refund" even when both share `/payments/{id}`.

### Step 3 — Model principals and permission scope

Identify actors: anonymous, end user, tenant admin, support, system client. Define roles/scopes/permissions and **resource ownership**. Check sharing relationships, on-behalf-of delegation, tenant data scoping, and locked or suspended account states. Never treat client-sent `tenantId`/`ownerId` as truth when the verified principal indicates another scope.

### Step 4 — Build layered defenses

1. `SecurityFilterChain`: choose authentication mechanisms, apply request-level method/path policies, deny by default, and configure CSRF/CORS/sessions per architecture.
2. Method/Service: object/tenant authorization, verifying proper Spring-managed proxy invocation or entry-point service policies.
3. Domain: invariants on state, limits, and transaction rules; do not collapse every error into 403.
4. Data access: queries pre-filtered by tenant/ownership where appropriate, parameterized SQL, transactions/locking to avoid TOCTOU.
5. Infrastructure: rate limits, MFA/step-up, signature verification, audit logging, retention, secret handling, and monitoring.

**No single annotation solves all layers.** Having `@PreAuthorize` does not guarantee valid request bodies; having a JWT does not mean the caller may view every object; having CSRF does not prevent BOLA.

### Step 5 — Design tests from the matrix, not ad hoc

For each row, document at minimum:

- **Positive:** valid actor with valid data is permitted.
- **Anonymous:** no credentials; must reject properly on private endpoints.
- **Wrong role/scope:** logged-in user lacking the authority.
- **Wrong owner/tenant:** has broad role yet accesses another user's object.
- **Wrong HTTP method:** right path with an unlisted method; must fail closed.
- **Invalid input/state:** passes security yet violates domain rules, returning the proper error.
- **CSRF/replay:** on unsafe endpoints with required protections, missing tokens/signatures/idempotency are rejected.
- **Data minimization:** responses exclude extra fields/documents; public APIs leak no PII.
- **Audit/abuse:** high-sensitivity operations emit events, enforce rate limits, step-up, or approvals per policy.

Automate CI checks for "new controller mapping without an inventory row" if your tooling supports it. You do not necessarily need to auto-generate all policies from a semantically thin table; the table still requires review by someone who understands the risks.

### Step 6 — Review whenever the system changes

Update the table whenever adding endpoints, changing HTTP methods/paths, widening roles, changing returned data, changing owner/tenant rules, adding clients, changing gateways, or enabling Actuator. Re-verify both positive and negative tests before release.

In code reviews, changes from `denyAll` to `permitAll`, from a specific role to `authenticated()`, or from owner-scoped to unrestricted data access must be **reviewed as security changes**, not mere syntax edits.

## 10. Mistakes to avoid

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Writing only "`/api/**` — login required" | Unclear which endpoints are admin-only or owner-only | List method + path + object policy + sensitivity |
| Treating every `GET` as public | GETs can also export PII, reports, or secrets | Classify by data and actor, not by method alone |
| Treating `permitAll` = safe | Public reset/webhook endpoints can still be abused | Rate limits, tokens/signatures, replay defense, proper auditing |
| Using only `authenticated()` on private routes | Any valid user can read others' resources | Enforce owner/tenant checks in service/data layers |
| Using `hasRole("ADMIN")` and skipping domain validation | Admins can still act on invalid states | Enforce invariants in service/domain layers |
| Placing `/**.permitAll()` before sensitive rules | The first matching authorization rule can open all URLs | Put specific rules first and `anyRequest().denyAll()` |
| Missing catch-all chain with multiple `SecurityFilterChain`s | Requests matching no chain may go unprotected | Check chain coverage and safe fallbacks |
| Adding endpoints without negative tests | Overly permissive rules go unnoticed | Maintain test matrix in CI |
| Testing only with `@WithMockUser` | Does not prove Basic/JWT/form login actually works | Test filters/managers with HTTP credentials/tokens |
| Forgetting CSRF on browser POST/DELETE | Requests can be forged via browser | Keep CSRF or design risk-assessed stateless token policies |
| Putting `@PreAuthorize` on methods called via `this.method()` | Self-invocation can bypass the proxy | Split services/proxies and run integration tests |
| Picking 404 to "guarantee zero leaks" while leaking via timing/body | Information disclosure can still occur | Design consistent 403/404 policies minimizing oracles |
| Leaving Actuator/Swagger/webhooks off the inventory | Actual attack surface exceeds main controllers | Inventory every enabled entrypoint |
| Logging passwords/tokens in audit logs | Audit logs become a data leak source | Log actor/action/result/code using a safe schema |
| Lacking owners/reviewers | The table quickly goes stale | Assign ownership, PR/release gates, automate checks if suitable |

## 11. Practice questions and guided answers

1. `GET /catalog` and `POST /auth/password-reset/request` are both public. Do they carry the same sensitivity? What extra controls does reset need?
2. Why is `authenticated()` alone insufficient on `GET /api/orders/{id}`? If Bob guesses Alice's ID, which layer catches it?
3. How can `POST /api/orders/o-1/cancel` and `GET /api/orders/o-1` have different policies despite sharing one resource?
4. An admin is authenticated and allowed to call `DELETE`, yet paid orders cannot be deleted per product policy. Is this authorization or a business rule?
5. Why shouldn't unknown paths fall into `authenticated()` by default in tightly controlled apps? How does `denyAll` help?
6. If a state-changing POST lacks a CSRF token and returns 403, can you conclude `@PreAuthorize` rejected it?
7. What can happen when a service method has `@PreAuthorize` yet is called directly via `this.cancel(...)`?
8. An export API does not modify the database. Why can it still be HIGH/CRITICAL?
9. Is a webhook without username/password truly "unprotected" just because it is marked PUBLIC at the gateway?
10. In a multi-tenant system, if a user sends `tenantId=other` in a request, what data must the server rely on to decide permissions?
11. Name three negative tests besides "anonymous is blocked" to catch authorization bugs on the cancel-order endpoint.
12. When a developer adds `PATCH /api/orders/{id}`, which components and evidence must be updated before release?
13. When an API returns only HTTP 401/403 and it is unclear which rule applied, what should you inspect?
14. If switching from user roles to JWT scopes, what changes in the inventory and what stays the same?

**Answer hints:** (1) no, reset needs anti-enumeration/rate limits/token TTLs; (2) BOLA/IDOR, object policy; (3) GET is read-only, POST has side effects + CSRF/domain rules; (4) domain invariant; (5) fail-closed for unreviewed routes; (6) no, `CsrfFilter` may reject first; (7) self-invocation bypasses proxy; (8) large-scale data leak risk; (9) requires request signing and replay defense; (10) trusted principal/tenant binding; (11) wrong owner, wrong role, missing CSRF, invalid state; (12) policy, owner/tenant, CSRF, validation, test matrix, audit; (13) chain matchers, filters, authentication, and authorization rules; (14) scope syntax changes, resource ownership and risk classification remain mandatory.

## Official security documentation

- [Spring Security 6.5 — Authorize HTTP Requests: method/path matchers, denyAll, permitAll](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security: @EnableMethodSecurity and @PreAuthorize](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Multiple SecurityFilterChain, securityMatcher](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)