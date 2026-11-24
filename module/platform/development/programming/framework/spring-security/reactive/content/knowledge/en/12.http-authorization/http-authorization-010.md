# Designing Deny-by-Default Rules and Handling Unmatched Paths

## 1. The Problem: A New URL Must Not Automatically Open Access

In a Spring Security Reactive application running on Spring WebFlux, the system may have dozens or hundreds of endpoints: public, for logged-in users, admin-only, and paths that must never be accessed directly. New endpoints can appear later when developers add a controller, `RouterFunction`, Actuator, or another module.

If the configuration only states:

~~~java
// Configuration NOT strict enough if the goal is per-endpoint allowlisting.
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated())
~~~

then **every remaining path is accepted after authentication**, including a future endpoint that has not undergone authorization review. This is a "login-required by default" policy, distinct from **"deny by default"**.

When you want to actively allow only approved functionality, use a **deny-by-default** policy:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .pathMatchers(HttpMethod.GET, "/api/admin/summary").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

The second block is a configuration snippet to place inside `ServerHttpSecurity` with `org.springframework.http.HttpMethod` imported. Any request not matching the preceding rules will be denied, **even if the caller has an administrator account**.

This lesson belongs to **HTTP Authorization**. The focus is not on password hashing or JWT creation, but on building rules for HTTP requests so an undeclared path or HTTP method **is never accidentally usable**.

### Objectives

After this lesson, you can:

1. Distinguish `denyAll()`, `permitAll()`, `authenticated()`, `hasRole()`, and `hasAuthority()`.
2. Understand **matcher order** and why specific rules must precede `anyExchange()`.
3. Distinguish **security-chain matchers**, **authorization matchers**, and **WebFlux handler mapping**.
4. Explain when a URL without a handler receives 403 instead of 404, and why 401/403/404/405 depend on which layer handles the request.
5. Create an "allowlist + default deny" configuration for both paths and HTTP methods.
6. Handle multiple `SecurityWebFilterChain`s, routes outside security chains, actuator/static resources, CORS preflight, and reverse proxies properly.
7. Run a Java 17+ application with Spring Boot/WebFlux/Spring Security and verify with `curl` and `WebTestClient`.
8. Build a rule-evaluation checklist for code reviews and regression testing.

## 2. The "Default Deny" and "Least Privilege" Principles

**Default deny** means an HTTP request proceeds only if the policy contains a matching **permitting** rule. Any request not on the allowlist is denied.

**Least privilege** means permitting rules grant the minimum permissions required for the feature. For example:
- `GET /public/ping`: public, no authentication required.
- `GET /api/reports`: requires `ROLE_READER`.
- `GET /api/admin/summary`: requires `ROLE_ADMIN`.
- `GET /api/debug`: may exist in code, yet is **not permitted** by the current configuration.
- `GET /api/something-new`: new unapproved endpoint, denied by default.

Four commonly confused ending rules:

| Ending Rule | Meaning When Request Matches No Prior Rule | Risk |
| --- | --- | --- |
| `anyExchange().permitAll()` | Requires no permissions at all | Easily exposes all endpoints unintentionally |
| `anyExchange().authenticated()` | Requires a valid `Authentication` | Every new endpoint becomes accessible to any logged-in user |
| `anyExchange().hasRole("USER")` | Requires a generic role | Still automatically opens new endpoints to that generic role |
| `anyExchange().denyAll()` | No identity is permitted | Every new endpoint requires an explicit decision |

`authenticated()` can be valid if **that is the intentional policy for all endpoints**. However, when strict control over new paths and methods is required, `denyAll()` creates a clear boundary: adding a feature requires updating rules and tests.

**There is no automatic "superuser" that bypasses `denyAll()`.** Even if a user has `ROLE_ADMIN`, a final `denyAll()` rule still denies access if the URL does not match any preceding rule.

## 3. Three Path-Matching Layers: Distinguish Them Clearly

This is the most important part of "handling unmatched paths." In WebFlux Security there are **three distinct matching decisions**:

### Layer A — Selecting the SecurityWebFilterChain

An application can declare one or more `SecurityWebFilterChain` beans. Each chain has a `securityMatcher` defining which requests it applies to. Spring Security evaluates chains in order and selects the first matching chain.

Example:

~~~java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

This snippet belongs to **chain configuration**: requests outside `/api/**` will not use this chain. If no other chain protects those requests, policies inside this chain **do not apply** to out-of-scope paths.

### Layer B — Selecting a Rule in authorizeExchange

Inside the chosen chain, `authorizeExchange` defines `pathMatchers`/`matchers` for each permission:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .anyExchange().denyAll())
~~~

Rules are evaluated in order. **The first matching rule decides the permission**, and `anyExchange()` catches the remainder of the **selected chain**.

### Layer C — Finding a WebFlux Handler

After a request passes security, WebFlux must still find a controller method or `RouterFunction` matching the URL and HTTP method. If no handler exists:
- HTTP 404 usually means "route not found".
- HTTP 405 can appear when the URL is supported, yet the **method** is not accepted by the handler.
- Exception handlers, routers, static resources, and proxies can also affect the response.

**Security can deny before WebFlux reaches a 404/405 decision.** That is why a URL that does not even exist can still return 403 (or 401 depending on the entry point and authentication state).

### 3.1. Three-Layer Diagram

~~~text
HTTP request
    |
    v
Select SecurityWebFilterChain by securityMatcher + @Order
    |
    +-- No matching chain:
    |      Not protected by that Spring Security chain
    |      (other layers may still handle or deny)
    |
    +-- Matching chain found:
           |
           v
     Evaluate authorizeExchange top-down
           |
           +-- path/method match --> permitAll / role / authority / deny
           |
           +-- no specific rule matches --> anyExchange().denyAll()
                                             |
                                       403/401 depending on handling
           |
           +-- permitted
                    |
                    v
             WebFlux HandlerMapping
                    |
                    +-- Handler exists --> handler executes
                    |
                    +-- No handler --> usually 404
                    |
                    +-- Path has handler but method unsupported
                                                --> may return 405
~~~

This diagram is a conceptual model: filters handling authentication, CSRF, CORS, and exception translation have their own positions and behaviors, so never deduce an absolute status from a single DSL line alone.

## 4. Rule Order in authorizeExchange

Correct example:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .pathMatchers(HttpMethod.GET, "/api/admin/summary").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

The line `anyExchange().denyAll()` is the **final fallback**, not a rule meant to override existing rules. When a request matches an earlier specific rule, that rule's policy is applied.

### 4.1. Wrong Order Renders Specific Rules Ineffective

The following shows **flawed reasoning**:

~~~java
// WRONG: broad rule swallows requests needing specific control.
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

For `GET /api/admin/summary`, `/api/**` matches first and requires only a logged-in user. The `ADMIN` rule below is not applied as intended.

Fix by placing specific rules first:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/reports").hasRole("READER")
        .anyExchange().denyAll())
~~~

If you need to let all users read a fixed set of routes, declare **a narrow, method-specific route set** rather than permitting all of `/api/**`.

### 4.2. Why Not Put anyExchange First?

`anyExchange()` is the catch-all matcher for the remainder. It belongs after specific rules. A configuration with a catch-all at the start may be rejected by the framework when trying to add rules after it, or render subsequent rules ineffective; never build policies around that ordering.

### 4.3. Roles and Authorities

`hasRole("ADMIN")` checks the authority `ROLE_ADMIN` by default. Therefore:

~~~java
.pathMatchers("/api/admin/**").hasRole("ADMIN")
~~~

is not equivalent to:

~~~java
.pathMatchers("/api/admin/**").hasAuthority("ADMIN")
~~~

The latter requires the exact authority string `ADMIN`; `ROLE_ADMIN` does not match it directly. With an OAuth2 Resource Server, scopes are usually mapped to authorities like `SCOPE_read` or equivalent depending on configuration. Keep conventions aligned between authentication mapping and authorization.

## 5. Handling Unmatched Paths: 403 or 404?

Suppose a chain protects every URL and has:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/public/catalog/**").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .anyExchange().denyAll())
~~~

Consider two requests:

**A. `GET /public/catalog/not-existing`:** matches the `permitAll` rule even without a real controller. Security lets the request proceed. If no handler/static resource exists, WebFlux usually returns **404 Not Found**.

**B. `GET /api/not-existing`:** matches no permitting rule and falls into `denyAll`. Security denies **before** `HandlerMapping` determines 404. With an authenticated client and standard Basic config, you can observe **403 Forbidden**.

Crucially, **403 does not prove an endpoint exists**, and **404 does not always prove the request passed authorization**. Inspect the entire chain.

### 5.1. 401, 403, 404, 405: Practical Meaning

| Status | What Usually Happened | What Can Influence It |
| --- | --- | --- |
| **401 Unauthorized** | Endpoint requires authentication, but request has missing or invalid credentials | HTTP Basic/Bearer entry point and auth filter |
| **403 Forbidden** | Request is authenticated yet lacks permission, or hit deny-by-default; POST missing CSRF token can also return 403 | Authorization, CSRF, exception handling |
| **404 Not Found** | Request passed filters, yet no matching handler/resource exists | WebFlux router/handler/static resources |
| **405 Method Not Allowed** | URL has a handler, yet does not support the requested HTTP method | Method mapping; may not be reached if security blocks earlier |

The actual status depends on which filter rejects earliest. For an anonymous request hitting a deny rule, the entry point may produce 401 in some configurations; for an authenticated request, 403 is the typical outcome. Do not write tests expecting 404 for a path covered by deny-by-default.

### 5.2. Should You "Permit Nonexistent Routes" Just to See 404?

**Never do this casually.** Adding a `permitAll()` wildcard solely so a mistyped URL returns 404 can accidentally make real new endpoints registered under that wildcard public.

If a product requires 404 for a public namespace, you can permit **an evaluated public scope** and let WebFlux return 404 for nonexistent routes inside it. However, that namespace must genuinely be allowed to stay public even as developers add new endpoints. When in doubt, keep deny-by-default.

Some systems intentionally return 404 instead of 403 for resources a caller should not know exist. That is an **authorization/exception policy decision**, not a reason to open wildcards. Hiding existence cannot replace real access control and must be tested to avoid timing/cache/log leaks.

## 6. Combining HTTP Method and Path: "GET Only" Differs from "All Methods"

Compare:

~~~java
// Rule 1: allow GET at /api/reports.
.pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
~~~

with:

~~~java
// Rule 2: allow all HTTP methods at /api/reports.
.pathMatchers("/api/reports").hasRole("READER")
~~~

Rule 2 is broader: a user with `READER` can pass authorization for POST/PUT/DELETE on the same path, if permitted by other filters. If a developer later adds `@DeleteMapping("/api/reports")`, Rule 2 already grants permission to that new capability. Rule 1 does not.

Example read/write policy:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/items/**")
            .hasAuthority("SCOPE_items.read")
        .pathMatchers(HttpMethod.POST, "/api/items")
            .hasAuthority("SCOPE_items.write")
        .anyExchange().denyAll())
~~~

This snippet is for an API with exact scope mapping, **not a standalone program**. For POST/PUT/PATCH/DELETE from browsers with ambient credentials, CSRF protection is still required where appropriate. Never disable CSRF just to get a 200.

### 6.1. HEAD and OPTIONS

- HTTP `HEAD` has semantics close to GET yet is a **distinct HTTP method**. A rule matching only `HttpMethod.GET` does not automatically permit HEAD. If HEAD is needed, declare an explicit policy and test the result.
- `OPTIONS` may be used for CORS preflight. If the app needs cross-origin browsers, configure CORS to handle preflight properly with an allowlist of origins/methods/headers. Never unconditionally open `OPTIONS /** permitAll` without reviewing CORS and the security chain.
- Uncommon HTTP methods should also be denied by default rather than relying solely on controller method mappings.

### 6.2. Query Strings and Path Variables

Path/method-based authorization matchers do not automatically check permissions by query parameter or resource ID. For example:

~~~text
GET /api/orders/123?expand=items
GET /api/orders/999?expand=items
~~~

Both can match `GET /api/orders/**`, yet a user should only view orders belonging to them. **HTTP rules are the first barrier; data ownership must be checked in service/method authorization** based on user, resource, and tenant. Never treat a generic role as proof that a user may view every object.

When a custom matcher inspects queries/headers, handle normalization/encoding and security invariants explicitly; never assume URL values are normalized identically across proxy, framework, and application.

## 7. Designing a Rule Table Before Writing Java

A template that makes code reviews easy to follow:

| Method | Path or Route Group | Who Is Permitted | Reason |
| --- | --- | --- | --- |
| GET | `/public/ping` | Anyone | Demo health-like endpoint with no secrets |
| GET | `/public/catalog/**` | Anyone | Public catalog per product policy |
| GET | `/api/reports` | `ROLE_READER` | View reports |
| GET | `/api/admin/summary` | `ROLE_ADMIN` | Admin only |
| GET | `/api/debug` | **Nobody through this HTTP policy** | Route exists in code to illustrate default deny |
| Any other method | Any other path | **Deny** | Do not auto-open unapproved endpoints |

Notice `/public/catalog/**` is a **decision permitting both current and future endpoints** inside that namespace; it is only appropriate when everything under it is genuinely meant to be public. For sensitive systems, allowing exact individual paths is safer.

Good practice links this table to tickets/API designs and tests. When adding a route, developers specify method, path, role/authority, CSRF/CORS, and data ownership. Never let a sweeping wildcard turn review into a formality.

## 8. Complete Java 17+ Example: WebFlux Default Deny

The example uses Java 17, Gradle, Spring Boot 3.5.7, Spring WebFlux, and Spring Security Reactive. It intentionally declares only GET endpoints to focus on authorization and 403/404; Spring Security's default CSRF protection remains active for unsafe methods.

**Demo accounts (for local use only):**
- `reader / localpass` has `ROLE_READER`.
- `admin / adminpass` has `ROLE_ADMIN`.
- The two roles **do not include each other**. An admin in the demo is not automatically allowed into routes restricted to `READER`.

Structure:

~~~text
webflux-default-deny/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── DefaultDenySecurityTest.java
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-default-deny'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.3. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/public/catalog/**")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasRole("READER")
                        .pathMatchers(HttpMethod.GET, "/api/admin/summary")
                            .hasRole("ADMIN")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}localpass")
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

Meaning:
1. `securityMatcher(...)` is not called, so this chain can match any request by default. In the example there is only **one** security chain.
2. Public rules are listed first, specifying the GET method.
3. The report route requires only `ROLE_READER`; the admin route requires only `ROLE_ADMIN`.
4. `anyExchange().denyAll()` blocks every path/method not declared in earlier rules.
5. HTTP Basic makes running `curl` commands simple. Form login is disabled so 401 responses can be observed cleanly.
6. CSRF remains enabled by default. Do not use a tokenless POST as sole proof of `denyAll`, because CSRF can also return 403.
7. `{noop}` does not hash passwords and is **only for local demos**. Production must use a strong `PasswordEncoder`, HTTPS, secrets management, and an appropriate login mechanism.

**Never deploy these hardcoded accounts/passwords to the Internet.** In real products, HTTP Basic is only transport-safe over HTTPS; Base64 is not encryption. With JWT, Resource Server validation and corresponding authority mapping are needed, while authorization rules still follow the same principles.

### 8.5. DemoController.java

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/public/catalog/items")
    public Mono<String> catalog() {
        return Mono.just("catalog");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("report");
    }

    @GetMapping("/api/admin/summary")
    public Mono<String> adminSummary() {
        return Mono.just("admin-summary");
    }

    @GetMapping("/api/debug")
    public Mono<String> debug() {
        return Mono.just("debug-should-not-be-public");
    }
}
~~~

Notice `/api/debug` **has a real handler**, yet no permitting rule. It will be denied by `denyAll()` before the controller runs. Conversely, `/public/catalog/missing` has no handler, yet falls under the permitted public scope; WebFlux is allowed to handle it and return 404.

### 8.6. Running the Application

From the project directory:

~~~bash
gradle bootRun
~~~

If a Gradle Wrapper is present, use `./gradlew bootRun` on macOS/Linux or `gradlew.bat bootRun` on Windows. By default the server listens on `localhost:8080`; never expose this demo port to a public network.

In another terminal:

~~~bash
# Public exact route
curl -i http://localhost:8080/public/ping

# Public catalog with handler
curl -i http://localhost:8080/public/catalog/items

# Permitted by security, but no handler exists
curl -i http://localhost:8080/public/catalog/missing

# Protected route, missing credentials
curl -i http://localhost:8080/api/reports

# Valid READER role
curl -i -u reader:localpass http://localhost:8080/api/reports

# READER role is not ADMIN
curl -i -u reader:localpass http://localhost:8080/api/admin/summary

# Valid ADMIN role
curl -i -u admin:adminpass http://localhost:8080/api/admin/summary

# Route actually exists, but is unlisted in policy
curl -i -u admin:adminpass http://localhost:8080/api/debug

# Route does not exist, and is not permitted by policy
curl -i -u admin:adminpass http://localhost:8080/api/ghost

# Admin is not automatically READER
curl -i -u admin:adminpass http://localhost:8080/api/reports
~~~

Expected when using the exact code and data:

| Request | HTTP | Explanation |
| --- | --- | --- |
| GET `/public/ping` | **200** | Exact public rule; body `pong` |
| GET `/public/catalog/items` | **200** | Public namespace; body `catalog` |
| GET `/public/catalog/missing` | **404** | Security permits, yet no handler exists |
| GET `/api/reports` no auth | **401** | Rule requires READER but unauthenticated; Basic challenge |
| GET `/api/reports` as reader | **200** | Has role; body `report` |
| GET `/api/admin/summary` as reader | **403** | Authenticated user lacking ADMIN |
| GET `/api/admin/summary` as admin | **200** | Has role; body `admin-summary` |
| GET `/api/debug` as admin | **403** | Route has handler yet falls into default deny |
| GET `/api/ghost` as admin | **403** | Security denies before WebFlux returns 404 |
| GET `/api/reports` as admin | **403** | Demo admin has only ADMIN, not READER |

**Exact JSON error bodies and headers may vary by version/configuration; the statuses above are expected for the demo.** The catalog 404 case assumes no other resource/route matches that name, as in the project above.

Do not conclude that a 403 proves a controller exists. For instance, `/api/ghost` has no handler at all and still receives 403 due to default deny.

## 9. Testing WebFlux with WebTestClient

Testing with `curl` is an empirical check, but matcher changes in code need **regression tests** to prevent new endpoints from accidentally opening.

Spring Security Test for Reactive integrates with `WebTestClient`. Create:

`src/test/java/demo/DefaultDenySecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class DefaultDenySecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicPingIsAccessibleWithoutAuthentication() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingRouteInsideExplicitlyPublicNamespaceIs404() {
        client.get().uri("/public/catalog/missing")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void readerRouteWithoutAuthenticationIs401() {
        client.get().uri("/api/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerRoleCanReadReports() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "localpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report");
    }

    @Test
    void readerRoleCannotAccessAdminEndpoint() {
        client.get().uri("/api/admin/summary")
                .headers(h -> h.setBasicAuth("reader", "localpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() {
        client.get().uri("/api/admin/summary")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-summary");
    }

    @Test
    void registeredButUnlistedDebugRouteIsDenied() {
        client.get().uri("/api/debug")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownPathIsDeniedBeforeRouterCanReturn404() {
        client.get().uri("/api/ghost")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminRoleDoesNotAutomaticallyIncludeReaderRole() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postIsDeniedEvenWhenCsrfIsPresent() {
        client.mutateWith(csrf())
                .post().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("attempt")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

All tests are expected to PASS once all files and dependencies are created properly. This is the **expected outcome from the source code**, not a claim that Gradle was actually executed.

The tests distinguish three phenomena:
1. **403 even though a handler exists** (`debug` hit default deny).
2. **403 even though no handler exists** (`ghost` hit default deny).
3. **404 because no handler exists yet security permits** (`public catalog` namespace).

The POST test includes `csrf()` intentionally to avoid attributing 403 to a missing CSRF token. When a valid token is present yet POST is still denied, that proves the rule does not allow that method. `csrf()` is a **test-environment-only** helper, not a way to "disable CSRF" in production.

**Do not abuse public namespaces in real products just to get 404 tests.** The public namespace in the demo is an intentionally permitted condition; in sensitive systems, list truly public routes narrowly.

## 10. Splitting Multiple SecurityWebFilterChains

When an application has two authentication groups, e.g.:
- `/api/**` using Bearer JWT with a resource server.
- Web UI using form login/session.
- Public routes needing a different mechanism.

You can create **multiple `SecurityWebFilterChain`s** to separate authentication mechanisms and policies. Crucially, **Spring Security selects one matching chain in order** rather than summing rules across all chains.

Example **alternative configuration**—do not place alongside the previous demo's `SecurityWebFilterChain` bean:

~~~java
// Illustrative excerpt: must be inside @Configuration, with imports and
// real authentication/JWT configuration for each chain.

@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                    .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET, "/public/ping")
                        .permitAll()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This is an architectural snippet, **not a standalone runnable project**. It requires Spring imports, the OAuth2 Resource Server starter, issuer/JWK/JWT validation, proper CSRF/CORS configuration, and concrete namespace design. In production, do not enable unnecessary HTTP Basic just to have a fallback; the fallback can simply deny.

Explanation:
- The API chain has `securityMatcher("/api/**")`, evaluated first.
- Inside the API chain, any path/method not matching the report rule hits `denyAll()`.
- The fallback chain has no restricting `securityMatcher`, so it receives remaining requests; only public ping is allowed.
- If a route **does not match the API chain** and matches the fallback, it is governed by the **fallback policy**, not the API chain's `anyExchange`.
- If you create only the API chain **without a fallback chain**, requests outside the API scope may **not be protected by that Spring Security chain**. Never treat `anyExchange().denyAll()` inside a scoped chain as an app-wide policy.

### 10.1. Issues with `/api` and `/api/**`

Patterns have specific semantics applied by `PathPatternParser` and matchers. Do not assume `/api`, `/api/`, and `/api/users` always match identically across every pattern. Test boundary paths and trailing slashes per your version.

In particular, a reverse proxy may add or strip prefixes before forwarding to WebFlux. What developers see externally (`/gateway/api/users`) may differ from the path `ServerWebExchange` sees internally. Configure matchers for **the path Spring Security actually evaluates**, and ensure proxies do not let clients spoof forwarded headers.

### 10.2. @Order Is Chain Order, Not Rule Order

- `@Order` on chain beans controls **which chain is evaluated first**.
- The order of `pathMatchers` inside `authorizeExchange` controls **which rule applies** inside the selected chain.

These are two independent priority axes; fixing one does not fix the other. Never put a catch-all chain at `@Order(1)` before an API-only chain if you want the API chain selected.

## 11. Special Paths: Actuator, Static Resources, Swagger, CORS

### 11.1. Actuator and Health Checks

When adding Spring Boot Actuator, health/metrics endpoints can have their own matchers and exposure settings. A default-deny policy does not know on its own whether health endpoints should be public or restricted to monitoring agents.

Never blindly add:

~~~java
// RISKY: opens all management endpoints.
.pathMatchers("/actuator/**").permitAll()
~~~

unless you have audited every exposed endpoint, port, and management policy. Usually only a limited health/probe endpoint is public, while metrics/config/env remain protected. When using a separate management port/context, also review the management context's security chain and network policy.

### 11.2. Static Resources and Documentation

A `/static/** permitAll` rule can make sense if every file under that namespace is public. However, do not open `/docs/**` or `/swagger-ui/**` merely thinking "docs hold no secrets"; OpenAPI schemas can expose internal endpoints or operational details.

When allowing a public namespace, maintain a **namespace content governance rule**: whenever adding a route under a public prefix, developers know it is immediately public.

### 11.3. CORS Preflight

Cross-origin browsers typically send `OPTIONS` with `Origin` and `Access-Control-Request-Method` before certain requests. When using CORS, configure CORS properly to handle preflight according to an origin/method/header allowlist, rather than adding `pathMatchers("/api/**").permitAll()`.

An `OPTIONS` request returning 403 can be caused by the security fallback, CORS policy, or route/matcher. Test both allowed origins and disallowed origins for `OPTIONS`. **Permitting CORS preflight does not authorize the real request**: the actual GET/POST must still pass its own authentication and authorization.

### 11.4. Error Routes and Health Proxies

When a request is denied, error handling may pass through infrastructure/framework handlers. Do not open `/error/**` publicly without verifying framework behavior and error payloads. API error responses may return JSON, yet must never leak stack traces, exception details, `SecurityContext`, or credentials.

### 11.5. WebSocket / Functional Routes

WebFlux provides `RouterFunction` and WebSocket support. HTTP authorization configuration must account for HTTP handshakes, functional routes, and message/application-layer permissions where needed. `anyExchange().denyAll()` blocks unapproved handshakes at the HTTP layer, yet does not replace message-level authorization or business data permissions.

## 12. Why Not Use 404 as a Security Barrier?

An endpoint returning 404 does not itself prove data is protected. For example:
- The API failed to match the route due to a wrong path.
- Security allowed the request, yet no controller exists.
- A policy intentionally hides resources using 404.
- A proxy or upstream service returned 404 before reaching the application.
- A route exists, yet the app maps "data not found" to 404.

**You cannot infer authorization solely from a 404 status.** When testing security:
1. Test an endpoint that **actually exists** yet is not allowlisted.
2. Test a URL with no handler.
3. Test a URL inside an allowlisted public area that has no handler.
4. Test with anonymous and multiple different roles.
5. Test undeclared HTTP methods.
6. Verify which chain matches the request before drawing conclusions.

If a product needs to hide a resource's existence from unauthorized users, service-layer policy can return 404 instead of 403 as required. Internally you must still **check permissions**; merely changing the status code does not create security.

### 12.1. Do Not Leak Paths Through Error Bodies

Whether returning 403 or 404, never return stack traces, internal endpoint lists, or hints like "admin route exists, please elevate privileges" to untrusted callers. Use a consistent error payload structure and proper correlation IDs. Internal logging can record route templates, error codes, and decision types for investigation while avoiding secrets and unnecessary PII.

## 13. HTTP Authorization Does Not Replace Data-Level Authorization

Even if `GET /api/reports` requires `ROLE_READER`, User A is not necessarily allowed to view User B's report. When a route has path variables:

~~~text
GET /api/reports/42
GET /api/reports/99
~~~

a `/api/reports/**` matcher only controls the **route type**, not ownership of each individual report. Add checks in the service:

~~~java
// Illustrative snippet in a reactive service/controller.
// Not a standalone runnable class; requires ReportRepository and business permissions.
return reportRepository.findById(reportId)
        .filter(report -> report.getOwnerId().equals(currentUserId))
        .switchIfEmpty(Mono.error(
                new AccessDeniedException("Not allowed")))
        .map(this::toDto);
~~~

If tenant/user IDs come from request parameters, compare them against verified authentication rather than trusting client-supplied values. Whether to return 403 or 404 for unowned resources is a dedicated security/API design decision.

With Spring Security Reactive, you can use reactive method security or `ReactiveAuthorizationManager` as needed, while request-layer authorization should still deny undeclared routes before controllers execute.

## 14. Common Configuration Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| `anyExchange().authenticated()` in a system needing an allowlist | New endpoints open automatically to every logged-in user | Use `anyExchange().denyAll()` and narrow rules |
| `pathMatchers("/api/**").authenticated()` before ADMIN | Broad rule swallows specific rule | Place ADMIN/specific role rules first |
| Overly broad `permitAll()` wildcard | Internal endpoints can become public | Permit only approved paths/methods |
| Single chain with `securityMatcher("/api/**")` and no fallback | Routes outside API scope may bypass Spring Security | Add a catch-all chain with a default policy |
| Catch-all chain placed before API chain | API chain is never selected | Use proper `@Order` and test matchers |
| Thinking `anyExchange` matches every URL app-wide | Only matches the remainder **in the selected chain** | Distinguish chain matchers from rule matchers |
| Expecting nonexistent URLs to always return 404 | Security may deny before `HandlerMapping` | Understand the 403/404 boundary; do not open routes to fix status |
| Using `hasRole("ADMIN")` while granting authority `ADMIN` | Permission mismatch due to prefix | Standardize `ROLE_ADMIN` or use `hasAuthority` |
| Checking only path, forgetting HTTP method | New POST/DELETE may open via wildcard | Use `pathMatchers(HttpMethod.X, ...)` |
| Using `GET` to delete data | Default CSRF typically does not check GET | Fix method semantics and protect unsafe methods |
| Disabling CSRF on POST 403 | Loses an independent defense layer | Keep CSRF if clients/browsers require it |
| Allowing all `OPTIONS` unconditionally | May open wrong policies or mask CORS issues | Handle preflight via CORS + security |
| Confusing Servlet `HttpSecurity` with Reactive `ServerHttpSecurity` | Config does not apply to WebFlux properly | Use `SecurityWebFilterChain`/`authorizeExchange` |
| Testing only 200 happy paths | Misses wildcards and forgotten routes | Test 401/403/404 + new routes/methods |
| Treating ADMIN as a default super-role | Can accidentally grant other groups' permissions | Define role hierarchies explicitly if needed |
| Catching `AccessDeniedException` and returning 200 | Bypasses access control enforcement | Return proper HTTP errors and observe internally |

**Never fix a 403 by widening `permitAll` until tests turn green.** First inspect chains, matchers, authentication, and specific rules.

## 15. Code Review / Security QA Process

A practical checklist:

- [ ] Write a table of expected HTTP methods, paths, and roles/authorities.
- [ ] Place `anyExchange().denyAll()` at the end of chains requiring an allowlist.
- [ ] Ensure no `permitAll()` wildcard is broader than the policy.
- [ ] Specific rules take precedence before broad rules.
- [ ] Verify `hasRole` vs. `hasAuthority` and prefix/claims mapping.
- [ ] If multiple chains exist, verify `@Order` and `securityMatcher` leave no out-of-scope routes exposed.
- [ ] Ensure a catch-all security chain or appropriate protection covers the rest.
- [ ] Test `/api`, `/api/`, trailing slashes, prefixes, path variables, and URL encoding as needed.
- [ ] GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS methods are governed by policy.
- [ ] GET/HEAD cause no side effects; CSRF/CORS are evaluated independently.
- [ ] Actuator, docs, static assets, and health checks have separate allowlists where required.
- [ ] Test at least one route **that has a controller yet is denied**.
- [ ] Test a URL **with no controller that is denied**.
- [ ] Test a URL **permitted by security that has no handler**.
- [ ] Test anonymous, valid role, wrong role, and invalid credentials.
- [ ] Review network/routes as seen by reverse proxies and load balancers.
- [ ] HTTP rules do not replace object-ownership/multi-tenant checks in services.
- [ ] Error responses never leak secrets, stack traces, or sensitive endpoint inventories.

### 15.1. Regression Scenario When Adding an Endpoint

Suppose a developer adds:

~~~java
@GetMapping("/api/export/all")
public Mono<String> exportAll() {
    return Mono.just("sensitive-export");
}
~~~

This is an illustrative snippet. With the lesson's default-deny config, the new endpoint is immediately denied—users do not gain access simply because they are logged in. To open it intentionally, the developer must:
1. Define who may view the export.
2. Specify the exact HTTP method and path.
3. Add a rule with appropriate permissions **before `anyExchange().denyAll()`**.
4. Write tests for both authorized and unauthorized callers.
5. Verify whether export data is scoped by tenant/user.

That is the operational value of default deny: an API change never silently expands privileges for existing user groups.

## 16. Self-Check Questions

**Question 1.** How do `anyExchange().authenticated()` and `anyExchange().denyAll()` differ?

> The first permits any remaining request if authenticated; the second denies all remaining requests regardless of role.

**Question 2.** If `pathMatchers("/api/**").authenticated()` stands before `/api/admin/** hasRole("ADMIN")`, what can happen?

> Admin requests match the broad rule first and bypass the ADMIN rule, resulting in overly permissive access control.

**Question 3.** Can a URL without a controller return 403?

> Yes. Default-deny authorization can reject before WebFlux determines the route does not exist.

**Question 4.** What does a URL under `/public/catalog/** permitAll` with no controller usually return?

> 404, because security lets it proceed, yet WebFlux finds no handler.

**Question 5.** If a chain matches only `/api/**` and ends with `anyExchange().denyAll()`, is `/admin/secret` protected by that rule?

> No. That rule only operates inside the selected chain. A fallback chain or independent protection is needed for other routes.

**Question 6.** Are `@Order` and `pathMatchers` order the same thing?

> No. `@Order` decides which chain is checked first; `pathMatchers` order decides which rule applies inside the chain.

**Question 7.** Does the `ADMIN` role automatically match `hasRole("READER")`?

> No, unless authentication grants both authorities or the organization configures a corresponding role hierarchy.

**Question 8.** Why does `GET /api/orders/123` still need an object-level check even though the HTTP rule matched?

> The HTTP rule authorizes the operation type; it does not verify that the user owns order ID 123.

**Question 9.** If a POST without a CSRF token returns 403, does that prove default deny is working?

> Not yet. The CSRF filter can also produce 403; test with a valid token or use GET to isolate the cause.

**Question 10.** Why not make `/actuator/**` public just to let the health check work?

> Because the wildcard may expose sensitive management/metrics endpoints and future actuator endpoints.

**Question 11.** Why is a 404 status not proof that an endpoint is secured?

> 404 can occur because WebFlux found no handler or a proxy returned it; test an endpoint with a real handler and verify chains/rules.

**Question 12.** An API permits GET, yet HEAD is not declared in matchers. Should you assume HEAD is also permitted?

> No. HEAD is a distinct HTTP method; an explicit policy and tests are required if you want to support it.

## 17. Conclusion

A secure HTTP authorization policy in Spring Security Reactive should follow these principles:

~~~text
Select security chain matching scope
      |
Evaluate specific rules by HTTP method + path
      |
Grant least-privilege role/authority
      |
Does not match approved rule --> DENY
      |
Only permitted requests reach WebFlux router
~~~

Typical configuration:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .pathMatchers(HttpMethod.GET, "/api/admin/summary").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Remember:
- `denyAll()` does not mean "require login"; it means "do not permit".
- A nonexistent URL can return **403 before 404**.
- `anyExchange()` applies only inside the **matched `SecurityWebFilterChain`**.
- HTTP method and rule order matter just as much as path.
- CORS, CSRF, method security, and object-level authorization are complementary layers and must not be skipped just because default deny is present.
- Deny-by-default only protects you when tested for **registered**, **unregistered**, and **out-of-security-matcher** paths.

### Official Documentation

- Spring Security Reference — Authorize ServerHttpRequest (WebFlux): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security Reference — WebFlux Security / Multiple Chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security Javadoc — ServerHttpSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Reference — Testing Authentication in WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security Reference — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Framework Reference — WebFlux Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html