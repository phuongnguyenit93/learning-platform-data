# Keeping Authentication, Authorization, and Business Logic in the Right Components

> Scope: designing Java 17+ applications with Spring Boot 3.x and Spring Security 6.x on Servlet/Spring MVC. This lesson explains how to separate responsibilities between **authentication** (verifying identity), **authorization** (checking permissions), and **business rules**; and demonstrates an API with per-object permission checks and pricing-rule checks. Do not assume every user-related decision is a security decision.

## 1. Three Different Questions

Suppose an application has an API to view an order quote. User `alice` requests the quote for order `A-100` with a 10% discount applied. The system must answer:

1. **Authentication:** Who is sending the request? Do the password/token/session prove it is `alice`?
2. **Authorization:** Does that identity have permission to **view the quote for order `A-100`**? The owner or an administrator may be allowed; other users are blocked.
3. **Business rules:** For an order the caller is allowed to view, can a 10% discount be applied? For example, the max discount is 20% and shipped orders cannot be repriced with a discount.

All three questions can arise in a single request, yet they **must have separate owners**. Never return "wrong password" to an authenticated user lacking permissions; and never turn "order already shipped, discount disallowed" into a missing-role error.

| Decision type | Primary data/conditions | Where it belongs | Typical response |
| --- | --- | --- | --- |
| Authentication | Username/password, token, signature, account status | Filter and `AuthenticationManager` / `AuthenticationProvider` / `UserDetailsService` per mechanism | HTTP 401 for HTTP Basic/Bearer; form login may redirect |
| HTTP-level authorization | Which endpoints require login? Which paths are admin-only? | `SecurityFilterChain`, `authorizeHttpRequests`, `AuthorizationManager` | Usually 401 if unauthenticated, 403 if authenticated but disallowed |
| Method/resource-level authorization | Does the user have the matching role/scope? Do they own the object? | `@PreAuthorize`, `@PostAuthorize`, `AuthorizationManager`/policy bean | Usually 403 when authenticated but lacking permission |
| Business validation | Order status, discount cap, inventory, contract value, payment deadline | Domain/service and domain objects | 400, 409, 422, or matching business code; not 401/403 by default |
| Data access | Query and persist requested data | Repository/data access, transactions, and data-policy enforcement | Depends on business outcome; queries do not replace permission checks |
| Mapping exceptions to HTTP | Formatting security responses or domain errors | `AuthenticationEntryPoint`, `AccessDeniedHandler`; `@RestControllerAdvice` for MVC/domain errors | Consistent without leaking sensitive data |

**Rule of thumb when classifying:** "If the caller's identity changed, would this decision change?" If yes, it is likely authorization. "If everyone had permission, would this transaction state still forbid the action?" If yes, it is usually a business rule. Combined cases exist (role-based limits, multi-level approval rules); model access policies and domain constraints cleanly instead of mixing them in controllers.

## 2. What Should Each Spring Security Component Do?

### Authentication: verifying identity

In a Servlet application, an authentication filter reads the appropriate HTTP mechanism, builds an unauthenticated `Authentication` object, and asks `AuthenticationManager` to verify it. `ProviderManager` can coordinate one or more `AuthenticationProvider` instances. For standard username/password, `DaoAuthenticationProvider` combined with `UserDetailsService` and `PasswordEncoder` is built in.

- `UserDetailsService`: loads account details from a trusted data source.
- `PasswordEncoder`: compares raw passwords against hashes; never compare plaintext passwords manually.
- `AuthenticationProvider`: verifies credentials for supported `Authentication` types.
- `SecurityContextHolder`: supplies the context holding the established `Authentication` for the execution flow; normally managed by filters/framework.
- `AuthenticationEntryPoint` and failure handlers: decide responses when authentication is required or fails.

When an app only changes where users are stored, **prefer writing `UserDetailsService`** and leveraging `DaoAuthenticationProvider`. Only write a custom provider/filter if the credential type or authentication process genuinely demands it. A pricing service does not need to know how to decode HTTP Basic or verify JWT signatures.

### Authorization: deciding who can do what

Two common levels:

1. **Request-level security** in `HttpSecurity.authorizeHttpRequests(...)`: e.g., all `/admin/**` paths require `ROLE_ADMIN`; other APIs require being logged in.
2. **Method/object-level security**: protect service calls with `@PreAuthorize`, policy beans, or `AuthorizationManager`, e.g., "only the order owner or admin may calculate a quote for this order".

Spring Security 6 supports `@EnableMethodSecurity` to enable annotations like `@PreAuthorize`. Spring Boot's security starter **does not enable method security by default**. Service-level policies protect calls coming from REST controllers, scheduled jobs, message listeners, and other callers—not only a single URL.

A policy can read needed data such as ownerId, tenantId, or visibility state, yet it should return an **authorization decision**, rather than calculating prices, mutating orders, or running business workflows. When rules grow complex, extract them into a named, unit-testable bean.

### Business logic: enforcing domain invariants

Services/domain objects check conditions that hold even when the actor is authorized: non-negative amounts, max discount limits, finalized orders cannot be edited, sufficient stock, valid state transitions.

These errors usually warrant domain exceptions and distinct HTTP mappings; for instance, an order that cannot be repriced because it already shipped maps to `409 Conflict` in the sample API. **Admins do not automatically bypass every business rule**: being allowed to invoke an operation does not mean the operation is valid for every data state.

## 3. Check Order and Processing Flow

Simplified flow of the example:

```text
HTTP GET /orders/A-100/quote?discountPercent=10
      |
      v
SecurityFilterChain / HTTP Basic
  - Missing or bad credentials -> challenge / 401
  - Valid credentials -> authenticated Authentication
      |
      v
URL-level authorization: anyRequest().authenticated()
      |
      v
@RestController: receives orderId, discountPercent; calls service
      |
      v
@PreAuthorize proxy on QuoteService
  - ADMIN or order owner -> proceed
  - Unauthorized -> AccessDeniedException -> usually 403
      |
      v
QuoteService: checks business constraints
  - Discount outside 0..20 -> 400
  - SHIPPED order with discount > 0 -> 409
  - Order not found (authorized caller) -> 404
  - Valid -> calculates price, returns Quote -> 200
```

`ExceptionTranslationFilter` translates security exceptions such as `AuthenticationException` and `AccessDeniedException` in the protected chain into proper responses via entry points/denied handlers; **it is not the permission checker**. Domain errors from controllers/services are normally mapped to responses by `@RestControllerAdvice`. Do not use a generic `@ControllerAdvice` to replace all security exception handling, because many security errors happen before Spring MVC.

The HTTP codes shown here are **expected behavior for the example's HTTP Basic configuration**; form login, sessions, OAuth2 Resource Server, or custom handlers may respond differently.

## 4. Runnable Example: Viewing a Quote Only When Authorized

### 4.1. Requirements

A test order store with two records:

| Order | Owner | Status | Subtotal |
| --- | --- | --- | --- |
| `A-100` | `alice` | `OPEN` | 100.00 |
| `B-200` | `bob` | `SHIPPED` | 80.00 |

Demo accounts:

| User | Demo password | Role |
| --- | --- | --- |
| `alice` | `alice-pass` | `ROLE_USER` |
| `bob` | `bob-pass` | `ROLE_USER` |
| `admin` | `admin-pass` | `ROLE_ADMIN` |

Rules:

- Users must authenticate via HTTP Basic.
- Only the **order owner** or **admin** can view/calculate a quote for that order.
- Valid discounts are **0–20%**.
- `SHIPPED` orders cannot receive a discount greater than 0, **even by admin**.
- The API only **reads and calculates** quotes; `GET` mutates neither state nor data.
- Missing order: for callers passing the policy (such as admin), return 404; for callers lacking object access, the policy can return 403 to avoid leaking ID existence.

This model is intentional: authentication is handled by Spring Security and `UserDetailsService`, order-owner permissions live in the policy, and pricing/status rules live in the service. The repository only stores/looks up data.

### 4.2. Dependencies

Create a Spring Boot 3.x project using Java 17+ and Gradle, with the Boot plugin and dependency management configured in `build.gradle`. Required `dependencies` section:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the **dependencies block**, not an entire Gradle file. Do not add `spring-boot-starter-data-jpa` because the example uses an in-memory repository.

### 4.3. Complete Single-File Java Application

Create the exact file `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

enum OrderStatus {
    OPEN, SHIPPED
}

record DemoOrder(
        String id, String owner, OrderStatus status, BigDecimal subtotal) {
}

@Repository
class OrderRepository {
    private final Map<String, DemoOrder> orders = Map.of(
            "A-100", new DemoOrder(
                    "A-100", "alice", OrderStatus.OPEN,
                    new BigDecimal("100.00")),
            "B-200", new DemoOrder(
                    "B-200", "bob", OrderStatus.SHIPPED,
                    new BigDecimal("80.00"))
    );

    Optional<DemoOrder> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}

@Component("orderAccess")
class OrderAccess {
    private final OrderRepository repository;

    OrderAccess(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(Authentication authentication, String orderId) {
        return authentication != null
                && repository.findById(orderId)
                        .map(order -> order.owner()
                                .equals(authentication.getName()))
                        .orElse(false);
    }
}

record PriceQuote(
        String orderId,
        String owner,
        OrderStatus status,
        BigDecimal subtotal,
        int discountPercent,
        BigDecimal payable) {
}

class OrderNotFound extends RuntimeException {
    OrderNotFound(String message) {
        super(message);
    }
}

class BusinessRuleViolation extends RuntimeException {
    BusinessRuleViolation(String message) {
        super(message);
    }
}

@Service
class QuoteService {
    private final OrderRepository repository;

    QuoteService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasRole('ADMIN') or "
            + "@orderAccess.isOwner(authentication, #orderId)")
    public PriceQuote calculate(
            @P("orderId") String orderId,
            int discountPercent) {

        if (discountPercent < 0 || discountPercent > 20) {
            throw new IllegalArgumentException(
                    "discountPercent must be between 0 and 20");
        }

        DemoOrder order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFound(
                        "Order not found"));

        if (order.status() == OrderStatus.SHIPPED
                && discountPercent > 0) {
            throw new BusinessRuleViolation(
                    "Shipped orders cannot receive a discount");
        }

        BigDecimal rate = BigDecimal.valueOf(discountPercent)
                .movePointLeft(2);
        BigDecimal payable = order.subtotal()
                .multiply(BigDecimal.ONE.subtract(rate))
                .setScale(2, RoundingMode.HALF_UP);

        return new PriceQuote(
                order.id(), order.owner(), order.status(),
                order.subtotal(), discountPercent, payable);
    }
}

@RestController
class OrderController {
    private final QuoteService quoteService;

    OrderController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @GetMapping("/orders/{orderId}/quote")
    PriceQuote quote(
            @PathVariable String orderId,
            @RequestParam(defaultValue = "0") int discountPercent) {
        return quoteService.calculate(orderId, discountPercent);
    }
}

@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderNotFound.class)
    ResponseEntity<Map<String, String>> notFound(OrderNotFound error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "not_found",
                        "message", error.getMessage()));
    }

    @ExceptionHandler(BusinessRuleViolation.class)
    ResponseEntity<Map<String, String>> conflict(
            BusinessRuleViolation error) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "business_rule",
                        "message", error.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException error) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid_input",
                        "message", error.getMessage()));
    }
}
```

**Compilation note:** `DemoApplication` is the sole `public` class; `SecurityConfig`, `OrderRepository`, `OrderAccess`, `QuoteService`, `OrderController`, and `ApiErrorHandler` are non-`public` top-level classes in the same `demo` package. `record` requires Java 16+ and works cleanly on Java 17. Spring Boot component scanning starts from package `demo` and discovers all these beans.

**What to observe in the code:**

- `SecurityConfig.users(...)` creates demo accounts with BCrypt; `UserDetailsService` supplies user data to Spring Security's standard username/password authentication. Do not write password checks in controllers.
- `securityFilterChain(...)` requires login at the HTTP layer; `httpBasic(...)` enables Basic authentication.
- `@EnableMethodSecurity` enables method-level protection.
- `@PreAuthorize(...)` is placed on **the public service method**. The policy calls the `orderAccess` bean. The `@P("orderId")` annotation ensures SpEL resolves `#orderId` reliably regardless of compiler parameter-name flags.
- `OrderAccess.isOwner(...)` returns only an ownership decision; it neither calculates prices nor changes order status.
- `QuoteService.calculate(...)` validates inputs and domain invariants after the caller passes the permission check; being allowed to view does not guarantee the discount is valid.
- `ApiErrorHandler` maps only domain/input errors to JSON. There is no `@ExceptionHandler(AccessDeniedException.class)` intercepting security error handling.

### 4.4. Running and Verifying Results

In the Spring Boot project directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

When running at `http://localhost:8080` (unless `server.port` was changed), test these requests:

```bash
curl -i "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u alice:wrong \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u alice:alice-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u bob:bob-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u admin:admin-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=10"
curl -i -u bob:bob-pass \
  "http://localhost:8080/orders/B-200/quote?discountPercent=10"
curl -i -u bob:bob-pass \
  "http://localhost:8080/orders/B-200/quote?discountPercent=0"
curl -i -u alice:alice-pass \
  "http://localhost:8080/orders/A-100/quote?discountPercent=30"
curl -i -u admin:admin-pass \
  "http://localhost:8080/orders/MISSING/quote?discountPercent=0"
```

On PowerShell, use `curl.exe` instead of `curl` if `curl` is aliased to `Invoke-WebRequest`. The trailing `\` characters above are Bash line-continuation syntax; on PowerShell write each `curl.exe` command on **one line**, or use PowerShell backticks per shell rules.

| Scenario | Expected HTTP | Reason |
| --- | --- | --- |
| No credentials | 401 | Unauthenticated; Basic requires credentials |
| `alice` sends wrong password | 401 | Authentication failure |
| `alice` calls `A-100`, 10% discount | 200, `payable=90.00` | Valid owner; valid calculation |
| `bob` calls `A-100` | 403 | Authenticated but neither owner nor admin |
| `admin` calls `A-100`, 10% discount | 200, `payable=90.00` | Admin passes policy, then business rule succeeds |
| `bob` calls `B-200`, 10% discount | 409 | Owner is permitted, yet `SHIPPED` order violates business rule |
| `bob` calls `B-200`, 0% discount | 200, `payable=80.00` | Owner and no discount rule violation |
| `alice` calls `A-100`, 30% discount | 400 | Input outside business range 0..20 |
| `admin` calls ID `MISSING` | 404 | Passes authorization via admin role, but order does not exist |

Example JSON in a successful response (field order may differ):

```json
{
  "orderId": "A-100",
  "owner": "alice",
  "status": "OPEN",
  "subtotal": 100.00,
  "discountPercent": 10,
  "payable": 90.00
}
```

This is a **price-calculating API that does not mutate data**. Because it uses `GET` only, the example does not need to disable CSRF for testing with curl. For `POST`/`PUT`/`DELETE` or cookie/session authentication, design CSRF according to the usage model; never add `csrf.disable()` merely to silence a 403. HTTP Basic still requires HTTPS in real deployments; localhost sample passwords are for learning only.

## 5. Why Not Put Everything in the Controller?

Example lacking separation of responsibilities:

```java
// Illustrating an approach that should not be copied verbatim:
@GetMapping("/orders/{id}/quote")
public Object quote(String id, String username, String password) {
    // Controller checks passwords itself, compares order owners itself,
    // then calculates pricing and chooses HTTP status itself.
    return null;
}
```

This is a **non-standalone anti-pattern fragment**, not part of the runnable program in section 4. It couples authentication, authorization, business logic, and HTTP handling tightly to one endpoint. Consequences:

- A second endpoint might forget to check passwords or permissions.
- Call paths from jobs/other services can bypass checks placed only in the controller.
- Switching authentication from Basic to JWT forces rewriting pricing logic.
- Business rules cannot be unit-tested independently of HTTP/security.
- Error types get tangled, preventing clients from distinguishing 401, 403, and business errors.

In a layered design, the controller receives input and calls a service; Spring Security manages identity; policies evaluate permissions; services/domain enforce pricing rules; repositories persist data; advice handles domain exceptions. Controllers may validate input shape, but never put full identity verification or financial rules there.

**Nor should everything be stuffed into `AuthenticationProvider`.** A provider only needs to know whether credentials authenticate, not whether order `A-100` shipped or whether a discount exceeds 20%. The auth provider returns identity and baseline authorities; per-object access decisions happen later.

## 6. Method Security: Strengths and Limits

### Why protect at the service layer?

If you only place a rule at `requestMatchers("/orders/**").hasRole("USER")`, `bob` also has `ROLE_USER` and can pass the URL layer to view `alice`'s order. A coarse role check **does not replace** resource-ownership checks.

`@PreAuthorize("hasRole('ADMIN') or @orderAccess.isOwner(authentication, #orderId)")` checks each method call and each `orderId`. The admin role satisfies the ownership check, yet **does not bypass the shipped-order rule** inside `QuoteService`.

### Proxy considerations

Method security applies by default via Spring AOP/proxies:

- Methods must be invoked through a Spring-managed bean. Calling `new QuoteService(...)` yourself bypasses interceptors.
- Calls **from one method to another inside the same instance** (`this.calculate(...)`) normally bypass the proxy, so `@PreAuthorize` on the target method may not run. Extract distinct responsibilities into separate beans or structure calls through proxies properly.
- With standard proxy configurations, private/final methods have interception limitations; prefer public service methods and verify with integration tests.
- `@EnableMethodSecurity` must be enabled; adding `@PreAuthorize` without enabling it provides no enforcement.
- Parameter names in SpEL must be discoverable; for example use `@P("orderId")` rather than relying solely on the compiler `-parameters` flag.

### Data and transaction considerations

The policy uses `OrderRepository` to look up the owner, and then the service also reads data. In real systems, permission lookups and data updates can occur at two different moments. For sensitive **write** operations, coordinate with transactions/locking/versioning or conditional database updates so state cannot change between check and write (race condition). A single `@PreAuthorize` call does not guarantee business atomicity.

In multi-tenant systems, tenantId and shared permissions must also be strictly enforced on queries/updates; never conclude that checking owner in the controller alone suffices. You can use identity/tenant-filtered repository queries or service policies depending on requirements, while keeping responsibility boundaries clear.

## 7. Exceptions: Security Errors Differ from Domain Errors

Important exceptions:

| Scenario | Appropriate error type | Handling layer |
| --- | --- | --- |
| Wrong password / invalid credential | `AuthenticationException` and matching subclass | Authentication manager/filter and failure handling |
| Authenticated user lacking resource permission | `AccessDeniedException` or deny result from method security | Authorization, `AccessDeniedHandler` |
| Discount parameter outside 0..20 | `IllegalArgumentException` in demo; real apps may use validation/specific domain errors | Business/validation, `@RestControllerAdvice` |
| Shipped order cannot be discounted | `BusinessRuleViolation` | Service/domain, `@RestControllerAdvice` -> 409 |
| Order not found after passing policy | `OrderNotFound` | Service/repository, `@RestControllerAdvice` -> 404 |
| External auth service timeout | Appropriate infrastructure/auth exception, logged safely | Authentication integration/operations; do not pretend it is a wrong password |
| Database error during pricing | Infrastructure error, timeout, or 5xx API error per contract | Service/repository/observability; do not pretend it is 403 |

Do not catch broad `Exception` to return 401 or 403: this hides programming bugs, database failures, and business errors. Conversely, if a controller `@ExceptionHandler` tries to catch all security errors, many filter-level rejections before the controller will never reach it.

**Processing order matters:** if a caller lacks permission to invoke the method, `@PreAuthorize` blocks before the service calculates pricing. Thus `bob`, who cannot view `A-100`, gets 403 even if he sends a 30% discount; never use a business message like "discount too large" that leaks info about an order he cannot access. If admin queries a missing ID, the example returns 404 because admin passed the policy. For public APIs, decide consistently and test whether to return 403 or 404 to prevent object-existence enumeration.

## 8. Testing Each Responsibility Independently

### Testing behavior through Spring Security and MVC

With the `spring-security-test` dependency from section 4, create `src/test/java/demo/OrderSecurityTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedUserGets401() throws Exception {
        mvc.perform(get("/orders/A-100/quote"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadQuote() throws Exception {
        mvc.perform(get("/orders/A-100/quote")
                        .with(httpBasic("alice", "alice-pass"))
                        .param("discountPercent", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"))
                .andExpect(jsonPath("$.discountPercent").value(10));
    }

    @Test
    void anotherUserGets403() throws Exception {
        mvc.perform(get("/orders/A-100/quote")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void forbiddenBusinessTransitionGets409() throws Exception {
        mvc.perform(get("/orders/B-200/quote")
                        .with(httpBasic("bob", "bob-pass"))
                        .param("discountPercent", "10"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("business_rule"));
    }

    @Test
    void invalidPercentGets400() throws Exception {
        mvc.perform(get("/orders/A-100/quote")
                        .with(httpBasic("alice", "alice-pass"))
                        .param("discountPercent", "30"))
                .andExpect(status().isBadRequest());
    }
}
```

Run in the project via:

```bash
./gradlew test
```

This is an **integration test**: it verifies that filters/HTTP Basic, method security, and business errors work together. Add tests for an authorized admin still subject to business rules, wrong passwords, missing orderIds, and non-controller service call paths.

### Testing each layer independently

- **Authentication**: test right/wrong passwords, locked/disabled accounts, expired credentials, or invalid tokens; never use a discount test to prove bcrypt works.
- **Authorization policy**: unit test `OrderAccess.isOwner(...)` with `alice`, `bob`, and missing IDs; also integration-test `@PreAuthorize` and the admin role so proxies are not bypassed.
- **Business rules**: test discounts -1, 0, 10, 20, 21; `OPEN` and `SHIPPED` states; verify `BigDecimal` results and rounding rules. Keep domain logic decoupled from frameworks so it can be tested without a Spring context as the app grows.
- **HTTP mapping**: verify 401/403 from security handlers, 400/409/404 from domain advice, and JSON bodies free of stack traces/tokens/hashes.
- **Data/integration**: with a real database, test transactions, race conditions, isolation, and tenant/owner constraints in queries.

## 9. Common Design Mistakes

1. **Letting controllers verify passwords manually** and mint authenticated `Authentication` objects. Consequence: duplicated logic, bypassed managers/filters, and heightened risk of forged tokens. Use Spring Security's authentication system.
2. **Putting owner checks inside business validation and returning "invalid order".** Object visibility is an authorization policy; deny properly and limit existence leaks.
3. **Assuming having `ROLE_USER` grants access to every order.** Per-object access needs owner/tenant/resource policies or a fitting permission model.
4. **Assuming admins bypass every transaction rule.** Admins may be authorized to invoke operations; domain logic still enforces state and invariants.
5. **Placing `@PreAuthorize` only on controllers** while jobs/message listeners call services unchecked. Enforce policies at a broad enough service boundary and test alternate callers.
6. **Forgetting `@EnableMethodSecurity` or calling self-methods bypassing the proxy.** Annotations may sit in code without protecting actual call paths.
7. **Catching every error as 403**, including database failures or out-of-range discounts. Classify exceptions and HTTP statuses by responsibility.
8. **Letting controllers/repositories decide all business rules.** Controllers coordinate HTTP, repositories handle data access, and services/domain protect invariants.
9. **Using `double` for money** and comparing directly. The example uses `BigDecimal` and explicit rounding; real products also need currency, taxes, rule versions, and agreed rounding policies.
10. **Disabling CSRF to fix 403 errors** without examining cookie/session usage; this can open vulnerabilities in browser apps. The example uses read-only GETs to focus on layering.
11. **Trusting client-sent username/role/orderOwner** without checking the verified principal and server-side records.
12. **Granting access before checking tenant or resource:** in multi-tenant apps, both global roles and data scoping must be enforced where authoritative data lives.
13. **Writing custom providers for all business logic:** `AuthenticationProvider` is not the layer for deciding discounts, stock, or contract status.

## 10. Practice Exercises

1. A user calls `GET /orders/A-100/quote` without sending HTTP Basic credentials. Which path returns the error and with what code?
2. `bob` has `ROLE_USER` and tries to access `alice`'s order. Why does the HTTP-level `authenticated()` check let him through, while `@PreAuthorize` rejects him?
3. `admin` is allowed to view `B-200`, yet requests a 10% discount. Why does the system still return 409?
4. If you moved the "shipped orders cannot be discounted" rule into `OrderAccess.isOwner`, what design problem would arise?
5. If you switched from HTTP Basic to Bearer JWT while keeping the same owner/admin policy and pricing calculation, which layer should change the most?
6. If a method inside `QuoteService` calls `this.calculate(...)`, is `@PreAuthorize` guaranteed to run? Where should this be verified?
7. For a payment operation writing to the database, is `@PreAuthorize` checking owner before the transaction safe enough if ownership changes concurrently?
8. Given statuses 401, 403, 400, 404, 409, map each status to its responsibility and explain why one status does not always correspond to a single Java exception class.

**Hints:** (1) authentication entry point, usually 401 with Basic; (2) request-level only knows login state, method-level knows the resource; (3) authorization does not erase domain rules; (4) conflating policy and invariants; (5) authentication filter/provider/decoder, while the domain stays intact; (6) self-invocation can bypass proxies, needs integration tests; (7) requires proper transactions/locking/database conditions; (8) distinguish causes and handling layers rather than mechanically inferring status from exception names.

## Official Reference Sources

- [Spring Security 6.5 — Servlet Architecture, SecurityFilterChain and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security, @EnableMethodSecurity and @PreAuthorize](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — Password Storage and PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)