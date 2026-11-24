# Combining Multiple Authorization Conditions per Business Policy in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Topic Group:** HTTP Authorization  
> **Problem:** Combining multiple authorization conditions according to business policy.  
> **Learning Goal:** Design and test a policy with AND, OR, and resource checks, rather than assigning a single fixed role to every request. Example code uses Java 17+, Spring Boot WebFlux, Spring Security, and WebTestClient.

## 1. The Problem: authenticated or a Single Role Is Usually Insufficient

Suppose a multi-tenant order management system needs to protect `GET /api/orders/{id}`. Business rules state:

1. The caller must be **authenticated**.
2. The caller needs the technical permission `SCOPE_orders.read`.
3. The caller must belong to **at least one** of `ROLE_MEMBER` or `ROLE_AUDITOR`.
4. The order must belong to a **tenant granted to the caller**.
5. The order must be in `OPEN` status.
6. Within that tenant, the caller may only read **their own** orders, **or** an auditor may read OPEN orders in the tenant.

If you only use `.authenticated()`, a logged-in Bob can access Alice's orders. If you only use `.hasRole("AUDITOR")`, regular members cannot read their own orders. If parentheses are placed in the wrong spot, an auditor could accidentally bypass tenant or scope checks.

The right policy is a testable logical expression:

~~~text
ALLOW =
    authenticated
    AND has("SCOPE_orders.read")
    AND (has("ROLE_MEMBER") OR has("ROLE_AUDITOR"))
    AND sameTenant
    AND orderStatus == OPEN
    AND (isOwner OR has("ROLE_AUDITOR"))
~~~

**Important:** these two groups of conditions belong at **two appropriate layers**. General request-level permissions (authenticated, scope, role) can be checked early in **HTTP authorization**. Conditions depending on real data (order tenant, owner, status) should be checked in **service/domain authorization**, where the resource has been loaded from a trusted repository. Adding HTTP rules does not make business rules automatically hold for every service call path.

## 2. Concepts: Authentication, Authorization, Permissions, and Attributes

- **Authentication:** verifies the caller's identity; Spring Security places an `Authentication` in the `SecurityContext`. Having an `Authentication` does not necessarily mean sufficient permission to read an order.
- **Authorization:** decides whether a specific operation is allowed on a specific resource.
- **Role / RBAC:** role-based permission groups, e.g., `ROLE_MEMBER`, `ROLE_AUDITOR`, `ROLE_ADMIN`.
- **Authority / Scope:** fine-grained permissions, e.g., `SCOPE_orders.read` or `SCOPE_orders.approve`. In a JWT Resource Server, Spring Security typically maps scopes to `SCOPE_`-prefixed authorities under default configuration.
- **ABAC (attribute-based access control):** decisions based on attributes of the caller, resource, or environment, e.g., tenant, owner, department, time, or transaction state.
- **ReBAC (relationship-based access control):** decisions based on relationships, e.g., whether the user is an owner, collaborator, or shared through an authorized group.
- **Policy decision:** returns an allow or deny outcome; business flows may also need an internal reason for auditing, though sensitive data must **never** be leaked in public error messages.

A URL route can have general HTTP rules, but an order record needs **object-specific authorization**. Do not confuse a `ROLE_ADMIN` or global scope with permission to read every tenant: that is a privileged capability that must be defined and audited separately.

## 3. AND, OR, NOT, and Evaluation Order

| Business Expression | Expression | Meaning |
| --- | --- | --- |
| Has both permissions | `A && B` | Missing either condition denies access |
| Has either role | `A || B` | At least one condition is true |
| Not in locked state | `!locked` | Negation of a condition |
| Has scope and (owner or auditor) | `scope && (owner || auditor)` | Scope applies to **both branches** |
| Owner or (auditor with scope) | `owner || (auditor && scope)` | **Wrong** if owner must also have scope |
| Same tenant and (owner or auditor) | `tenant && (owner || auditor)` | Auditor **cannot** cross tenant boundaries |

Common mistake:

~~~java
boolean allowed =
    isOwner || (isAuditor && hasReadScope && sameTenant);
~~~

In this expression, if `isOwner` is true, then the scope and tenant conditions do not need to be true. If business rules require every branch to have scope and matching tenant, place those conditions outside the parentheses:

~~~java
boolean allowed =
    hasReadScope && sameTenant && (isOwner || isAuditor);
~~~

**Deny by default:** if the user is missing, role is missing, order is not found, tenant is undetermined, status is unsupported, or policy result is unclear, **do not grant permission**. In production apps, errors from a policy service must never silently turn into allow.

## 4. Two Authorization Tiers: Route First, Object Second

~~~mermaid
flowchart TD
    R["GET /api/orders/{id}"] --> C["SecurityWebFilterChain"]
    C --> A{"Has Authentication?"}
    A -->|"No"| U["401: unauthenticated"]
    A -->|"Yes"| S{"Scope orders.read?"}
    S -->|"No"| F["403: lacks HTTP permission"]
    S -->|"Yes"| T{"ROLE_MEMBER OR ROLE_AUDITOR?"}
    T -->|"No"| F
    T -->|"Yes"| D["Controller → OrderService → OrderStore"]
    D --> E{"Order exists?"}
    E -->|"No"| N["404: resource not found"]
    E -->|"Yes"| G{"Order tenant granted?"}
    G -->|"No"| N
    G -->|"Yes"| H{"Status OPEN?"}
    H -->|"No"| N
    H -->|"Yes"| O{"Owner OR Auditor?"}
    O -->|"No"| N
    O -->|"Yes"| P["200: return permitted data"]
~~~

**The HTTP layer** filters out requests missing broad permissions early, reducing heavy logic execution and producing sensible 401/403 responses. **The business layer** decides access to **a real object**; when a URL contains `{id}`, relying solely on the client-sent ID is insufficient to determine access.

Benefits of separating layers:

1. Avoids querying the DB for requests lacking basic read permissions.
2. Tenant/owner/state checks live close to the use case and can be reused across adapters: HTTP, message consumers, internal jobs, GraphQL.
3. Policies can be unit-tested independently of the HTTP layer.
4. A 404 rule hiding resources owned by others can be enforced consistently in the service.
5. If extra rules such as "locked record", "dual approval", or "transaction limit" are needed, domain-layer logic fits much better than a simple HTTP expression.

However, **protecting every HTTP endpoint remains essential**. Service-level policies do not replace URL configuration, and URL policies do not replace object checks.

## 5. How Spring Security Reactive Selects Rules in authorizeExchange

Spring Security Reactive uses `ServerHttpSecurity` and `SecurityWebFilterChain`. `pathMatchers` inside `authorizeExchange` are evaluated in **declaration order**. When a matcher matches, **its corresponding authorization manager** decides; Spring does not combine all rules matching the same URL into an automatic AND.

**Wrong example — two identical matchers do not form AND:**

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/api/orders/**").hasRole("MEMBER")
    .pathMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
    .anyExchange().denyAll()
)
~~~

The first matching role rule handles the URL; the subsequent scope rule **does not** act as a second condition for the same request. If a `MEMBER` lacks the scope and only the first rule applies, there is a risk of overly broad access.

**Right example — one matcher, one composite policy:**

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/orders/{id}")
        .access(orderReadRoutePolicy)
    .anyExchange().denyAll()
)
~~~

`orderReadRoutePolicy` is a `ReactiveAuthorizationManager<AuthorizationContext>` implementing explicit condition composition. You can use built-in managers like `AuthorityReactiveAuthorizationManager.hasRole(...)` and `hasAuthority(...)` and combine their results, or write a clean, testable Java policy as in the example below.

**Additional distinction:** `securityMatcher` selects the **SecurityWebFilterChain** when multiple chains exist; `pathMatchers` selects the rule **inside the chosen chain**. A high-priority chain with a broad matcher can shadow another chain. This lesson uses **one chain** to focus on policy composition without mixing in chain-ordering bugs.

## 6. Designing the Sample Policy and Test Data

The sample app manages orders readable via HTTP GET. There are 4 orders:

| Order ID | Tenant | Owner | Status |
| --- | --- | --- | --- |
| `ord-100` | `acme` | `alice` | OPEN |
| `ord-101` | `acme` | `charlie` | OPEN |
| `ord-200` | `beta` | `bob` | OPEN |
| `ord-300` | `acme` | `alice` | SEALED |

Sample authentication data (passwords for localhost only):

| User | Authorities | Meaning |
| --- | --- | --- |
| `alice` | `ROLE_MEMBER`, `SCOPE_orders.read`, `TENANT_acme` | Owner of ord-100 and ord-300 |
| `charlie` | `ROLE_MEMBER`, `SCOPE_orders.read`, `TENANT_acme` | Owner of ord-101 |
| `bob` | `ROLE_MEMBER`, `SCOPE_orders.read`, `TENANT_beta` | Owner of ord-200 |
| `auditor` | `ROLE_AUDITOR`, `SCOPE_orders.read`, `TENANT_acme` | Reads OPEN orders in acme |
| `observer` | `ROLE_MEMBER`, `TENANT_acme` | Missing read scope |
| `external` | `ROLE_GUEST`, `SCOPE_orders.read`, `TENANT_acme` | Has scope but lacks both MEMBER and AUDITOR |

**Route conditions:** authenticated AND scope read AND (MEMBER OR AUDITOR). **Service conditions:** order's tenant is among the principal's granted tenants AND status is OPEN AND (principal is owner OR principal has role AUDITOR).

In the lab, `TENANT_acme` is an authority generated by the server from the user store. In real life, tenants must come from verified identity systems/claims and be mapped consistently, or verified against DB membership; **never trust client-set `X-Tenant` headers or query parameters as proof of tenant membership**.

## 7. Runnable Project Structure

Requires **Java 17+**, Maven, and an unused port 8080. This lesson uses Spring Boot **3.3.13** and Spring Security 6.x APIs as a stable instructional baseline; the 3.3 branch has reached end of OSS support, so when creating new systems, pick a supported Spring Boot/Spring Security version, update code, and test on your target version.

~~~text
reactive-business-authz/
├── pom.xml
└── src/
    ├── main/java/example/authz/
    │   ├── AuthzApplication.java
    │   ├── SecurityConfig.java
    │   ├── OrderReadRoutePolicy.java
    │   ├── OrderService.java
    │   └── OrderController.java
    └── test/java/example/authz/
        └── OrderAuthorizationTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactive-business-authz</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

`spring-boot-starter-webflux` provides WebFlux/Project Reactor; `spring-boot-starter-security` provides reactive security; `spring-boot-starter-test` provides JUnit 5 and `WebTestClient`. **Do not add `spring-boot-starter-web`** in this example because the lab uses WebFlux without mixing Servlet MVC.

### 7.2. Entry Point

File `src/main/java/example/authz/AuthzApplication.java`:

~~~java
package example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzApplication.class, args);
    }
}
~~~

`@SpringBootApplication` auto-configures and scans beans in the same package. No real database is needed; orders and users reside in memory so learners can focus on policy logic. Production requires tenant-protected repositories and a trusted identity system.

## 8. SecurityConfig: Defining Sample Users and HTTP Authorization

File `src/main/java/example/authz/SecurityConfig.java`:

~~~java
package example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    private UserDetails user(
            PasswordEncoder encoder,
            String name,
            String password,
            String... authorities) {

        return User.withUsername(name)
            .password(encoder.encode(password))
            .authorities(authorities)
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            user(encoder, "alice", "alice-pass",
                "ROLE_MEMBER", "SCOPE_orders.read", "TENANT_acme"),
            user(encoder, "charlie", "charlie-pass",
                "ROLE_MEMBER", "SCOPE_orders.read", "TENANT_acme"),
            user(encoder, "bob", "bob-pass",
                "ROLE_MEMBER", "SCOPE_orders.read", "TENANT_beta"),
            user(encoder, "auditor", "auditor-pass",
                "ROLE_AUDITOR", "SCOPE_orders.read", "TENANT_acme"),
            user(encoder, "observer", "observer-pass",
                "ROLE_MEMBER", "TENANT_acme"),
            user(encoder, "external", "external-pass",
                "ROLE_GUEST", "SCOPE_orders.read", "TENANT_acme")
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            OrderReadRoutePolicy readPolicy) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .access(readPolicy)
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
~~~

**What is checked here?**

- Specific rule for `GET /api/public` permits anonymous access.
- Only `GET /api/orders/{id}` enters `readPolicy`. Having an `id` in the URL does not prove the caller is allowed to view that ID.
- `anyExchange().denyAll()` denies undeclared paths/methods. Do not leave `/api/**` overly open.
- HTTP Basic is used to simulate simple per-request authentication; raw passwords exist in the demo source, so use it **only on localhost**. Outside local environments, HTTP Basic requires HTTPS and an identity/token mechanism suited to your architecture.
- The user store explicitly creates authorities prefixed with `ROLE_`, `SCOPE_`, and `TENANT_`; they **are never chosen by the client** when calling endpoints.
- `formLogin` is disabled in the API lab so unauthenticated requests receive an HTTP Basic challenge instead of redirecting to an HTML login page.
- Default CSRF is not disabled. The lesson only performs **data-reading GETs**, so no CSRF token is needed for test requests. If you open POST/PUT/DELETE, evaluate CSRF based on how clients carry credentials rather than disabling CSRF unconditionally.

**When using a JWT Resource Server:** replace HTTP Basic and the user store with `oauth2ResourceServer(...jwt(...))`, configuring issuer, signature/audience/expiry, and claim-to-authorities mapping. The AND/OR logic still applies, but only has value when authorities come from a **verified token issued for the right audience**; never copy roles directly from the request body.

## 9. Custom ReactiveAuthorizationManager Combining AND/OR

File `src/main/java/example/authz/OrderReadRoutePolicy.java`:

~~~java
package example.authz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class OrderReadRoutePolicy
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        return authentication
            .map(auth -> {
                boolean loggedIn = auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken);

                boolean mayRead = has(auth, "SCOPE_orders.read");

                boolean actorType = has(auth, "ROLE_MEMBER")
                    || has(auth, "ROLE_AUDITOR");

                return new AuthorizationDecision(
                    loggedIn && mayRead && actorType);
            })
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private static boolean has(Authentication auth, String authority) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority::equals);
    }
}
~~~

### 9.1. How to Read This Expression?

~~~text
loggedIn && mayRead && (isMember || isAuditor)
~~~

- `loggedIn`: `Authentication` is authenticated and not an `AnonymousAuthenticationToken`.
- `mayRead`: has exact authority `SCOPE_orders.read`.
- `actorType`: has `ROLE_MEMBER` **or** `ROLE_AUDITOR`.
- Missing any mandatory condition → `new AuthorizationDecision(false)`. If `Authentication` is absent, `defaultIfEmpty(...)` also denies.
- The policy does not look up the resource or trust the URL ID to guess ownership. Dynamic attributes belong to `OrderService`.
- The `AuthorizationContext` parameter is passed by the interface and can expose path/path variables, but in this lesson they **are not proof of ownership**.

Because this is Spring Security 6.x API, `ReactiveAuthorizationManager.check(Mono<Authentication>, T)` returns `Mono<AuthorizationDecision>` and is accepted by `access(...)`. Newer Spring Security versions also offer `authorize(...)/AuthorizationResult`; when upgrading, consult the matching API docs rather than mixing examples across major versions.

### 9.2. Why Not Use a Long URL Expression?

A policy can be written as an expression, but when multiple conditions exist, a dedicated Java policy offers advantages: type checking, unit tests, easy auditing, and no operator-precedence mistakes. For single-condition rules, still prefer the built-in DSL:

~~~java
.pathMatchers("/admin/**").hasRole("ADMIN")
.pathMatchers("/public/**").permitAll()
~~~

**There is no need to write a custom manager for every URL.** Create a dedicated policy when multiple conditions must be combined or when logic should be reused and tested independently. Avoid turning every rule into scattered boolean `if` checks inside controllers.

## 10. OrderService: Checking Permissions on Real Records

File `src/main/java/example/authz/OrderService.java`:

~~~java
package example.authz;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

record OrderRecord(
    String id,
    String tenant,
    String owner,
    String status
) {}

@Service
public class OrderService {

    private final Map<String, OrderRecord> orders = Map.of(
        "ord-100", new OrderRecord(
            "ord-100", "acme", "alice", "OPEN"),
        "ord-101", new OrderRecord(
            "ord-101", "acme", "charlie", "OPEN"),
        "ord-200", new OrderRecord(
            "ord-200", "beta", "bob", "OPEN"),
        "ord-300", new OrderRecord(
            "ord-300", "acme", "alice", "SEALED")
    );

    public Mono<OrderRecord> findReadable(
            String id,
            Authentication authentication) {

        return Mono.justOrEmpty(orders.get(id))
            .switchIfEmpty(Mono.error(hidden()))
            .flatMap(order -> {
                boolean sameTenant = has(authentication,
                    "TENANT_" + order.tenant());

                boolean isOwner = order.owner()
                    .equals(authentication.getName());

                boolean auditor = has(authentication, "ROLE_AUDITOR");

                boolean open = "OPEN".equals(order.status());

                boolean allowed = sameTenant
                    && open
                    && (isOwner || auditor);

                return allowed
                    ? Mono.just(order)
                    : Mono.error(hidden());
            });
    }

    private static boolean has(Authentication auth, String authority) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority::equals);
    }

    private static ResponseStatusException hidden() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
}
~~~

### 10.1. Why Must the Service Authorize Again Too?

The route policy already proved `SCOPE_orders.read` and the role. However, only upon loading `OrderRecord` do we learn which tenant the order belongs to, who the owner is, and whether the status is OPEN or SEALED. If the service skips those three checks, someone who knows `ord-200` could try reading tenant `beta`'s data while only holding `acme` permission: this is a form of **Broken Object Level Authorization (BOLA/IDOR)**.

`OrderService` evaluates **one combination**:

~~~text
sameTenant
AND isOpen
AND (isOwner OR isAuditor)
~~~

- Alice can view `ord-100` because tenant matches, owner matches, and it is OPEN.
- Charlie **cannot** view `ord-100` despite sharing the tenant and having the scope, because he is neither owner nor auditor.
- The `acme` auditor can view `ord-100` and `ord-101`, but cannot view `beta`'s `ord-200`.
- Alice **cannot** view her own `ord-300` because its status is SEALED. The status condition applies to both member and auditor.
- If the order is not found or viewing is not permitted, the lab returns the **same 404** to avoid directly confirming the existence of another user's order.

**Choosing 404 vs. 403 is an API/threat-model decision.** 403 signals authenticated without permission; 404 can hide resource existence when identifiers are sensitive. In the example, **route-level denial** returns 403 when missing scope/role, while **object-level denial** returns 404. If production uses 404 to hide objects, keep response bodies, timing, logs, and caching behavior consistent so no new oracle is introduced.

### 10.2. Never Use Client-Asserted Tenant as Evidence

This is a dangerous bug:

~~~java
boolean allowed = request.headers().getFirst("X-Tenant")
    .equals(order.tenant());
~~~

The `X-Tenant` header can be forged by the client. In the lab, membership lives in server-created authorities. In production, fetch tenant membership from verified identity/DB/permission services and re-verify against the record. If a user belongs to multiple tenants, resolve the active-tenant policy cleanly, scope data to that tenant, and protect tenant-switching requests.

### 10.3. Policies Must Accompany Data Queries When Needed

With a real database, list queries should **filter tenant, status, and permissions before pagination**. Do not load 100 records across multiple tenants, filter them in Java, and return the list; otherwise pagination/counts/caching can leak data or cause unnecessary load.

For state-changing operations (e.g., approving an order), verify conditions **at write time** within a transaction or conditional update to avoid TOCTOU: order status can change between check and update. Never let a request skip rules merely because a prior GET was allowed.

## 11. Controller Coordinates Only, Never Guessing Permissions

File `src/main/java/example/authz/OrderController.java`:

~~~java
package example.authz;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/orders/{id}")
    public Mono<Map<String, String>> order(@PathVariable String id) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .flatMap(auth -> orders.findReadable(id, auth))
            .map(record -> Map.of(
                "id", record.id(),
                "tenant", record.tenant(),
                "owner", record.owner(),
                "status", record.status()
            ));
    }
}
~~~

`ReactiveSecurityContextHolder.getContext()` retrieves the `SecurityContext` from the **Reactor Context** in a WebFlux request. It differs from using Servlet's ThreadLocal-based `SecurityContextHolder.getContext()`. The code returns `Mono`, never calls `block()`, never calls `subscribe()` manually, and never parses Basic headers manually.

**Why not check tenant in the controller?** The controller's job is HTTP mapping and returning data; domain object checks belong in the service so other flows can reuse them. When adding GraphQL, event consumers, or scheduled jobs, ensure callers always go through the authorization-enforced use case instead of accessing repositories directly and bypassing service policies.

## 12. Expected Access Matrix

| Request to `/api/orders/{id}` | Route checks | Object checks | Result |
| --- | --- | --- | --- |
| Anonymous reads ord-100 | Not authenticated | Not run | **401** |
| Alice reads ord-100 | Scope + MEMBER pass | Tenant acme, owner Alice, OPEN | **200** |
| Charlie reads ord-100 | Scope + MEMBER pass | Same tenant, different owner | **404** |
| Auditor acme reads ord-100 | Scope + AUDITOR pass | Same tenant, auditor, OPEN | **200** |
| Auditor acme reads ord-200 | Scope + AUDITOR pass | Wrong tenant beta | **404** |
| Bob beta reads ord-100 | Scope + MEMBER pass | Wrong tenant acme | **404** |
| Bob beta reads ord-200 | Scope + MEMBER pass | Matching tenant and owner | **200** |
| Alice reads ord-300 | Scope + MEMBER pass | Order status SEALED | **404** |
| Observer reads ord-100 | Missing `SCOPE_orders.read` | Not run | **403** |
| External reads ord-100 | Has scope, lacks MEMBER/AUDITOR | Not run | **403** |
| Alice reads nonexistent ID | Route pass | No object | **404** |
| GET `/api/public` anonymous | `permitAll()` | Not applicable | **200** |

**HTTP status differs by layer:** unauthenticated with HTTP Basic usually returns 401; authenticated but missing scope/role at HTTP usually returns 403; the service intentionally returns 404 when the object is missing or hidden. When switching authentication mechanisms to form login or Bearer JWT, entry points and error bodies may differ. Enforce security with negative tests rather than relying on a single predicted status.

## 13. WebTestClient Testing with Real Lab Data

File `src/test/java/example/authz/OrderAuthorizationTest.java`:

~~~java
package example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderAuthorizationTest {

    @Autowired
    WebTestClient client;

    private WebTestClient.ResponseSpec getAs(
            String uri, String user, String password) {
        return client.get()
            .uri(uri)
            .headers(headers -> headers.setBasicAuth(user, password))
            .exchange();
    }

    @Test
    void publicEndpointIsAccessibleWithoutLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void anonymousCannotReadOrders() {
        client.get().uri("/api/orders/ord-100")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void memberCanReadOwnOpenOrder() {
        getAs("/api/orders/ord-100", "alice", "alice-pass")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void anotherMemberInSameTenantCannotReadOrder() {
        getAs("/api/orders/ord-100", "charlie", "charlie-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void auditorMayReadOpenOrderInsideOwnTenant() {
        getAs("/api/orders/ord-101", "auditor", "auditor-pass")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("charlie");
    }

    @Test
    void auditorMustNotCrossTenantBoundary() {
        getAs("/api/orders/ord-200", "auditor", "auditor-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void memberMustNotCrossTenantBoundary() {
        getAs("/api/orders/ord-100", "bob", "bob-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void memberCanReadOwnOrderInBetaTenant() {
        getAs("/api/orders/ord-200", "bob", "bob-pass")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("beta");
    }

    @Test
    void sealedOrderIsNotReadableEvenByOwner() {
        getAs("/api/orders/ord-300", "alice", "alice-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void memberWithoutReadScopeIsForbiddenAtHttpLayer() {
        getAs("/api/orders/ord-100", "observer", "observer-pass")
            .expectStatus().isForbidden();
    }

    @Test
    void readScopeWithoutAllowedRoleIsForbidden() {
        getAs("/api/orders/ord-100", "external", "external-pass")
            .expectStatus().isForbidden();
    }

    @Test
    void unknownOrderUsesSameStatusAsHiddenOrder() {
        getAs("/api/orders/missing", "alice", "alice-pass")
            .expectStatus().isNotFound();

        getAs("/api/orders/ord-101", "alice", "alice-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void unexpectedRouteIsDenied() {
        getAs("/api/admin/debug", "alice", "alice-pass")
            .expectStatus().isForbidden();
    }
}
~~~

Run:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Maven runs the unit/integration web tests. The method names express the **exact conditions** to prove: not only "Alice receives 200", but also **Charlie is blocked within the same tenant**, **auditor cannot cross tenants**, **users missing scope are blocked at HTTP**, and **SEALED orders are blocked even for the owner**.

**Do not treat `mvn test` as proof of production security:** this is a lab test with fixed users/orders. Real systems need tests with signed and verified tokens, real databases, transactions, multiple real tenants, proxies/gateways, caches, and other use-case entry points.

## 14. Manual Testing with curl

Start the app, then use another terminal. In PowerShell where `curl` is an alias, use `curl.exe` if needed.

~~~bash
# Public API
curl -i http://localhost:8080/api/public

# No credentials → 401
curl -i http://localhost:8080/api/orders/ord-100

# Alice reads her own order; curl prompts for alice-pass
curl -i -u alice http://localhost:8080/api/orders/ord-100

# Charlie tries reading Alice's order; enter charlie-pass, expect 404
curl -i -u charlie http://localhost:8080/api/orders/ord-100

# Auditor views acme order; enter auditor-pass, expect 200
curl -i -u auditor http://localhost:8080/api/orders/ord-101

# Auditor tries beta order; expect 404
curl -i -u auditor http://localhost:8080/api/orders/ord-200
~~~

`curl -u username` avoids writing the password directly into shell history; after running, enter the demo password when prompted. Never put real passwords or Bearer tokens into logs or shared docs. HTTP Basic on `http://localhost:8080` is only suitable for local practice; on real networks, **HTTPS** is mandatory.

When valid, a sample JSON response from `GET /api/orders/ord-100` as Alice:

~~~json
{
  "id": "ord-100",
  "tenant": "acme",
  "owner": "alice",
  "status": "OPEN"
}
~~~

JSON field order is not a security contract; tests use JSONPath so they do not depend on `Map.of(...)` ordering.

## 15. Why Not Move the Owner Condition into a Simple URL Rule?

A URL `/api/orders/{id}` only provides the ID from the client. `id` carries no trustworthy information about tenant/owner. If the controller also accepts `?tenant=acme&owner=alice` or an `X-User: alice` header, clients can alter those values. You cannot determine object access by comparing two client-controlled values.

When it could live entirely in HTTP: a custom policy manager can extract the path variable and **query a trusted repository** inside `ReactiveAuthorizationManager<AuthorizationContext>`. However, consider:

- The manager might have to query the DB before selecting the controller, causing duplicate queries if the controller loads the object again.
- Consistency is needed between the checked object and the object actually modified, especially on writes.
- Errors/timeouts from the policy store must be bounded and never converted into allow.
- Decisions may need reuse in non-HTTP use cases; if all policy lives only in HTTP, another adapter can bypass it.
- For collections, filtering item-by-item after loading everything can leak counts and break pagination.

Thus the sample architecture places **coarse authorization at HTTP** and **fine-grained authorization near data**. In large systems, standardize decisions through a centralized policy service/gate/permission evaluator while still enforcing checks in key use cases.

## 16. Extending the Policy: Approving Orders with Multiple Constraints

Suppose later there is `POST /api/orders/{id}/approve`. Business rules:

- Authenticated user, holding `SCOPE_orders.approve`.
- Has `ROLE_MANAGER` or `ROLE_ADMIN`.
- Matching tenant and order currently in `PENDING_APPROVAL`.
- Approver **is not the order creator** (four-eyes / separation of duties).
- Amount is within the user's approval limit; high-value orders require an extra approval level.
- Request has proper idempotency key/transaction semantics and CSRF if using auto-sent browser credentials.

Correct expression:

~~~text
ALLOW_APPROVE =
    authenticated
    AND has(SCOPE_orders.approve)
    AND (ROLE_MANAGER OR ROLE_ADMIN)
    AND sameTenant
    AND status == PENDING_APPROVAL
    AND (actorUserId != creatorUserId)
    AND withinApprovalLimit
    AND approvalWindowOpen
~~~

**These conditions must apply simultaneously.** A parentheses mistake like `ROLE_ADMIN || (ROLE_MANAGER && withinApprovalLimit)` could accidentally remove limits for admins when policy requires limits on both. If admins are exempt from limits, document that explicitly as **an approved business exception**, with dedicated auditing and tests.

**Note on TOCTOU:** for mutating endpoints, never do: read state → check state → update later without race protection. Use transactions/optimistic locking, conditional updates on version/state, and consistent permission checks at commit time. Two concurrent approvers must never exceed limits or overwrite state incorrectly.

The sample lab only implements GET so CSRF and transactions do not obscure the core topic; the approval expression above is a **policy model**, not an already-implemented route in the project.

## 17. Should You Use hasRole, hasAuthority, hasAnyRole, or a Custom Manager?

| Need | Appropriate Approach | Example |
| --- | --- | --- |
| Only requires login | `authenticated()` | User profile |
| Single role | `hasRole("ADMIN")` | Admin console |
| One of several roles | `hasAnyRole("MANAGER", "ADMIN")` | Internal reports page |
| Specific scope | `hasAuthority("SCOPE_orders.read")` | Read orders API |
| Scope **and** role group | `access(customReactiveAuthorizationManager)` | API requiring scope + (member/auditor) |
| Record/tenant-dependent permission | Service/domain policy after loading object | Owner, tenant, status |
| Service method check | `@PreAuthorize` + `@EnableReactiveMethodSecurity` | Protecting `Mono`/`Flux` methods |
| Very complex / cross-service rules | Policy component/engine with clear contract | Approval threshold, SoD, tenant delegation |

**Roles and scopes may overlap in small systems, yet should follow a clear convention.** For instance, roles describe job functions while scopes describe API capabilities. In a JWT Resource Server, scope mapping depends on the issuer/claim converter; never assume roles automatically appear as `ROLE_` without configuration.

**Do not confuse `hasRole("MEMBER")` with `hasAuthority("ROLE_MEMBER")`:** Spring Security typically adds the `ROLE_` prefix for `hasRole`, while `hasAuthority` checks the exact string. The lab uses `"ROLE_MEMBER"` and `"SCOPE_orders.read"` directly in Java to make the checks explicit.

## 18. Method Security: Additional Defense Layer

When multiple entry points invoke a use case (HTTP, GraphQL, scheduled tasks, message consumers), URL blocking alone is not enough. Spring Security Reactive supports method security integrated with Reactor Context.

Additional method configuration (excerpt to place inside a Spring `@Configuration`):

~~~java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfig {
}
~~~

Example adding a **coarse role/scope** condition to a service method returning `Mono`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "(hasRole('MEMBER') or hasRole('AUDITOR'))")
public Mono<OrderRecord> findReadableForCurrentUser(String id) {
    // Business logic must load the order, obtain Authentication from Reactor Context,
    // and then check tenant, owner, and status like OrderService.
    return Mono.empty(); // Illustrates annotation placement only, not a real runnable method.
}
~~~

**This snippet illustrates annotation syntax and does not replace `OrderService` in Section 10.** In real method security, you must run actual logic rather than returning `Mono.empty()` as in the sketch. Spring Security Reactive applies method authorization to `Mono` / `Flux` publishers and the Reactor security context. Calling a method on the same bean directly (self-invocation) can bypass AOP proxies, so if policies live solely on annotations, design calls to go through the bean proxy and test that scenario.

**Even with `@PreAuthorize`, object-level permissions must still be checked.** The annotation cannot automatically infer tenant or owner from an ID. You can invoke a policy bean inside SpEL, though with async DB access and complex business rules, dedicated Java policy code is often easier to test, audit, and handle timeouts.

## 19. Authorization and Authentication Do Not Replace Each Other

With HTTP Basic, every successful request has an `Authentication` with user/authorities verified from server-side passwords. If switching to JWT:

- The Resource Server must verify JWT signature or introspection, issuer, expiration, audience, and token type per contract.
- Scopes/roles/tenants must come from verified claims or trusted membership stores and be mapped consistently.
- If a user's permissions change during a token's lifetime, old claims can become stale; define SLAs for revocation, TTL, introspection/versioning, or dynamic permission lookup.
- A request's active tenant must never be decided solely by an `X-Tenant` header if users can spoof it; verify membership and resource scope.
- Valid authentication **does not** imply policy allow, even when a token carries `ADMIN`.

In reactive flows, never call `SecurityContextHolder.getContext()` like a Servlet `ThreadLocal` assuming the right principal is always there. Use `ReactiveSecurityContextHolder` inside publishers, or pass a **verified** principal into the service across an explicit boundary.

## 20. 401, 403, 404, and Safe Error Responses

**401 Unauthorized:** missing or invalid authentication credentials. With HTTP Basic, the server usually sends a `WWW-Authenticate` challenge.

**403 Forbidden:** authenticated user lacks the route's required scope/role, or is denied by an authorization policy. For some HTTP methods, a missing CSRF token can also cause 403; distinguish causes via safe logs and tests.

**404 Not Found:** resource does not exist or its existence is intentionally hidden when the user lacks viewing permission, per API contract. Never assume 404 means the object was never created; it may be a policy to prevent BOLA enumeration.

If choosing 404 for object denials, avoid differing messages between "not found" and "not authorized", avoid leaks via counts/lists/caching, and inspect timing side channels when risks warrant it. In internal logs, record denial reasons with a correlation ID while protecting sensitive data and keeping object/customer PII out of error responses.

**Never leak order contents before granting permission.** Bad example:

~~~java
return repository.findById(id)
    .doOnNext(order -> log.info("Order payload: {}", order))
    .flatMap(order -> checkAuthorization(order, auth));
~~~

Logging raw orders before deciding permissions can expose sensitive data. In real services, log only minimal metadata, avoid logging tokens/`Authorization` headers, and enforce policies close to queries.

## 21. Common Mistakes When Combining Policies

1. **Thinking multiple `pathMatchers` for the same URL form an AND.** In reality, the first matching rule governs; use one `.access(policy)` to combine.
2. **Placing overly broad public URLs before private rules.** `/api/**.permitAll()` can shadow routes requiring authentication.
3. **Confusing AND/OR and parentheses.** `owner || auditor && tenant` differs from `tenant && (owner || auditor)`; write tests for every branch.
4. **Letting auditors bypass all conditions.** If tenant/scope/status remain mandatory, never write `auditor || (scope && tenant && owner)`.
5. **Using request parameters as proof of tenant/owner.** Attackers can alter URLs, bodies, queries, and headers.
6. **Checking roles only at HTTP, leaving IDOR in the service.** Logged-in users can access others' IDs.
7. **Checking records only on read, not protecting updates.** Changing state creates race/TOCTOU bugs.
8. **Fetching full lists and filtering permissions after pagination.** Leaks counts, corrupts results, and leaks tenant data.
9. **Trusting JWT scopes without verifying issuer/audience/signature.** Unverified claims are not trustworthy authorities.
10. **Allowing access when the policy service errors/times out.** Authorization must fail closed; return 5xx/503 appropriately instead of auto-allowing.
11. **Caching authorization decisions too long.** Changing roles/tenants/statuses leaves stale cache entries granting excess access.
12. **Using `ThreadLocal` in WebFlux.** Drops or reads the wrong `SecurityContext` across scheduler switches.
13. **Disabling CSRF to test POST with browser cookies/Basic.** Understand credential transport and threat model first.
14. **Testing only authorized users, missing negative tests.** Cannot tell whether policies cross tenants or bypass scopes.
15. **Relying solely on controller-level policies.** Jobs, GraphQL, or other adapters can bypass controllers when calling services.
16. **Using `ADMIN` as a blanket bypass.** If break-glass access exists, it needs explicit conditions, auditing, and minimal privileges.

## 22. Applied Exercises

### Exercise A — Write a Truth Table

Create a table of at least 12 combinations of `authenticated`, `SCOPE_orders.read`, `ROLE_MEMBER`, and `ROLE_AUDITOR`. Fill in ALLOW/DENY for the HTTP rule. Prove that without the scope, **both member and auditor** are denied.

### Exercise B — Fix an Operator Precedence Bug

Suppose legacy code says:

~~~java
boolean allowed = isOwner || isAuditor && sameTenant && isOpen;
~~~

Identify at least two requests that are wrongly permitted; fix the expression with clear parentheses. Then add dedicated tests for an auditor in another tenant, an owner of a `SEALED` order, and a member in the wrong tenant.

### Exercise C — Add an HTTP Policy Condition

Business rules allow reading orders only when feature flag `orders.read.enabled` is active, **even for auditors**. Build a `ReadPolicySettings` bean or trusted policy service, combining into `authenticated && scope && roleGroup && featureEnabled`. Write a negative test when the flag is off. Never take the feature flag directly from a client-sent header.

### Exercise D — Add Collection Authorization

Create `GET /api/orders` to read multiple orders. Return only OPEN orders in the same tenant that the user owns or is allowed to view as an auditor. Filter in the repository/database **before pagination**; verify total counts/caching do not leak other tenants' order counts.

### Exercise E — Open an Approval Flow

Design a policy for `POST /api/orders/{id}/approve` with approve scope, manager/admin role, matching tenant, pending-approval status, creator distinct from approver, and approval limit. Write tests for concurrent approvals and denial when CSRF token is missing in a suitable cookie/session model.

### Exercise F — Time- and Environment-Based Authorization

Add a working-hours condition using an injected `Clock` for deterministic testing. If the policy calls an external service to check "currently on shift", enforce explicit timeouts and fail closed. Never rely directly on `LocalDateTime.now()` in tests, which causes flakiness.

### Exercise G — BOLA/IDOR Testing

Use user Charlie to attempt reading Alice's order by swapping `id` in the URL. Prove that same tenant + same role + same scope is still **insufficient**, because the owner differs. Add a valid `acme` auditor read and then test that auditor against a `beta` order; tenant must remain a strict barrier for both branches.

### Self-Evaluation Checklist

- [ ] Clearly define the entire `ALLOW` condition using AND/OR/NOT and parentheses.
- [ ] Distinguish authenticated, authority/scope, role, tenant, owner, and resource status.
- [ ] Understand `authorizeExchange` picks one rule by order; it does not AND two `pathMatchers`.
- [ ] Use `ReactiveAuthorizationManager<AuthorizationContext>` to combine scope + role at HTTP.
- [ ] Check ownership/tenant/status in the service against real objects.
- [ ] Never trust client-declared ID/tenant/owner without verification.
- [ ] Use deny-by-default for unlisted routes and never allow when policy is uncertain.
- [ ] Have tests for 401, 403, object-hiding 404, and valid 200 across permission branches.
- [ ] Auditors cannot cross tenants, owners cannot bypass status, and members cannot bypass scopes.
- [ ] Do not leak data through listings, counts, caches, or logs before authorization.
- [ ] Recognize race/TOCTOU risks when permissions depend on mutable state.
- [ ] Have a way to enforce the same domain policy when services are called outside HTTP controllers.

## 23. Self-Check Questions

1. Do two lines `pathMatchers("/api/**").hasRole("MEMBER")` and `pathMatchers("/api/**").hasAuthority("SCOPE_orders.read")` create an AND condition? Why or why not?
2. Why should route policies typically check roles/scopes while owner/tenant checks live near the database/use case?
3. Which expression is right when auditors still need the scope and same tenant: `auditor || (scope && tenant)` or `scope && tenant && (owner || auditor)`?
4. If a user has `SCOPE_orders.read` but lacks `ROLE_MEMBER`/`ROLE_AUDITOR`, what does the HTTP layer return?
5. If Alice has `ROLE_MEMBER`/scope and a `SEALED` order belongs to Alice, is data returned?
6. Why does merely having `ROLE_ADMIN` not automatically prove permission across all tenants?
7. What is the difference between 401, 403, and an "object-hiding" 404?
8. When migrating from the HTTP Basic demo to JWT, how must authorities and tenant membership be verified?
9. If an object was checked as `OPEN` and another request transitions it to `SEALED` before update, what category of bug is this?
10. Why must list queries filter permissions **before** pagination and caching?
11. If an external policy engine does not respond, should you allow by default or fail closed?
12. Which test most strongly proves that an auditor allowed in one tenant is **not** automatically allowed to read another tenant?

## 24. Official Documentation and Security Guides

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange` rule ordering and custom `ReactiveAuthorizationManager` with `.access(...)`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and Reactor Context.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `ServerHttpSecurity`, and chain selection.
- [Spring Security — ReactiveAuthorizationManager API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): `check` and `authorize` interfaces across version transitions.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): encoders for demo and production accounts.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): risks of checking routes without checking object IDs.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny-by-default, validating every request, and data-level authorization.
- [OWASP — Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html): object-level access control and policy governance.

**Conclusion:** Real-world access control is typically a **combination** of identity, scope, role, tenant, owner relationship, and resource status. With Spring Security Reactive, place **one composite policy** inside `.access(ReactiveAuthorizationManager)` at HTTP instead of expecting multiple `pathMatchers` to stack; then check **record-dependent** conditions inside the domain service. Write parenthesized expressions, deny by default, test both allowed and blocked branches, and never let role exceptions accidentally cross tenant/owner boundaries.