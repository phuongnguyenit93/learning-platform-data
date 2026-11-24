# Creating a Fallback Chain to Avoid Leaving Unprotected Paths Exposed

**Module:** Spring Security – Reactive (Spring WebFlux)  
**Context:** Configuring security with multiple `SecurityWebFilterChain` beans.  
**Goal:** For every HTTP request going through a WebFlux application, a security policy is always selected. Paths not explicitly permitted must be rejected under the **fail-closed** principle.

When an application has distinct endpoint groups such as public, user API, admin API, and internal endpoints, we often declare multiple `SecurityWebFilterChain` beans. Each bean has its own request-matching scope. If you only create a chain for `/api/**`, an endpoint outside `/api/**` may **fail to match any Spring Security chain**. Having `@EnableWebFluxSecurity` does not automatically guarantee all requests remain protected once you replace the default configuration with scope-limited chains. A **fallback chain applying to all remaining requests**, placed last in the list, closes this gap.

This lesson implements a Java 17+ configuration with `ServerHttpSecurity`, explains matching order and protection boundaries, and then tests with `WebTestClient` and `curl`. The example uses HTTP Basic with two *localhost-only* accounts to keep focus on the chain selection mechanism; with OAuth2/JWT, the fallback chain principle remains identical.

## 1. Two easily confused request-matching layers

In Reactive Spring Security, distinguish **selecting a chain** from **making permission decisions inside a chain**:

| Component | Function | Example |
| --- | --- | --- |
| `http.securityMatcher(...)` | Determines whether the **entire SecurityWebFilterChain** applies to a request. | API chain accepts only `/api/**`. |
| `http.authorizeExchange(ex -> ex.pathMatchers(...))` | Once the chain is selected, decides who has access to a group of requests inside that chain. | `GET /api/reports/**` requires `ROLE_READER`. |
| `anyExchange().denyAll()` inside a chain | Denies requests that **already selected this chain** but matched no prior allow rule. | `/api/experimental` is not opened automatically. |
| **Fallback** chain without calling `securityMatcher` | Uses `ServerHttpSecurity`'s default matcher, applying to all requests that did not enter a higher-priority chain. | `/internal/diag`, `/new-feature`, and paths outside `/api/**`. |

**Selection rule:** Spring Security inspects `SecurityWebFilterChain` beans in priority order, picks the **first matching chain**, and executes that chain's filters. A request rejected by `denyAll()` in the first chain **does not fall through to** a second chain. This is the key point: the fallback chain only handles requests **that did not match an earlier chain**; it cannot fix an overly permissive rule inside an earlier chain.

Dangerous example of a **missing fallback**:

```java
@Bean
SecurityWebFilterChain onlyApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is only a fragment: imports, configuration class, and remaining beans are omitted. This chain inspects only `/api/**`. If the application has a controller `GET /internal/diag`, that request is **not protected by this chain**. When no other chain matches, the request does not pass through the expected Spring Security filters; the controller may be invoked unless an independent mechanism blocks it.

## 2. Designing fail-closed before writing code

We build three explicitly ordered chains:

| Order | Chain name | Request selection via `securityMatcher` | Rules inside the chain |
| --- | --- | --- | --- |
| `@Order(1)` | `publicChain` | Only `GET /public/ping` | Anonymous access allowed |
| `@Order(2)` | `apiChain` | `/api/**` for all HTTP methods | Only grants access to listed methods/paths; ends with `denyAll` |
| `@Order(Ordered.LOWEST_PRECEDENCE)` | `fallbackChain` | No `securityMatcher` call: matches all remaining requests | `anyExchange().denyAll()` |

Two different protective properties:

1. **Fallback closes gaps between chains:** `/internal/diag` matches neither `/public/ping` nor `/api/**`, so it enters the final chain and is denied.
2. **Default deny closes gaps inside each chain:** `/api/experimental` matches `apiChain`, so the fallback **will not run**. `apiChain` itself must end with `anyExchange().denyAll()`.

Do not use `anyExchange().permitAll()` in the fallback. `authenticated()` in the fallback is safer than "no control at all", yet it can still accidentally expose a new endpoint to **every logged-in user**, even if that path has no authorization rules yet. For a *deny unless declared* policy, `denyAll()` is the stricter choice; open legitimate routes through deliberate configuration changes and tests.

### Chain selection flow

```text
HTTP Request
    |
    v
Order(1) publicChain: GET /public/ping ?
    | YES -> permitAll -> public controller
    |
    NO
    v
Order(2) apiChain: /api/** ?
    | YES -> match METHOD + PATH rules
    |        | permitted -> API controller
    |        | no rule match / insufficient role -> deny immediately
    |
    NO
    v
LOWEST_PRECEDENCE fallbackChain: match-all
    |
    v
anyExchange().denyAll() -> block invocation of remaining handlers
```

Smaller order numbers run first. Never place the fallback before the API chain; because the fallback matches all requests, it would "swallow" all traffic and subsequent chains would never get a chance to run.

## 3. Building a Spring Boot WebFlux example with a fallback chain

### 3.1. Structure and dependencies

The example runs standalone with **JDK 17+**, Maven 3.9+, and an available localhost port. Spring Boot `3.5.7` is a version available on Maven Central used to illustrate reproducibility; in real deployments, choose a supported newer patch release per project policy.

```text
reactive-security-fallback/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/fallback/
    │   │   ├── FallbackApplication.java
    │   │   ├── SecurityChains.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/fallback/
        └── FallbackSecurityTests.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>reactive-security-fallback</artifactId>
    <version>1.0.0</version>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-security-fallback
server.port=8080
```

Use only the WebFlux starter for this lesson; adding the Servlet MVC starter too can change which web application type Spring Boot selects. Do not use Servlet's `HttpSecurity`/`SecurityFilterChain` configuration to replace the corresponding WebFlux APIs: here you must use **`ServerHttpSecurity` and `SecurityWebFilterChain`**.

`src/main/java/demo/fallback/FallbackApplication.java`:

```java
package demo.fallback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(FallbackApplication.class, args);
    }
}
```

### 3.2. Configuring three SecurityWebFilterChain beans

`src/main/java/demo/fallback/SecurityChains.java`:

```java
package demo.fallback;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityChains {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain publicChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(new PathPatternParserServerWebExchangeMatcher(
                "/public/ping", HttpMethod.GET))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports/**").hasRole("READER")
                .pathMatchers(HttpMethod.GET, "/api/admin/dashboard")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    @Order(Ordered.LOWEST_PRECEDENCE)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            // Do not call securityMatcher: use the default matcher (all requests).
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

Explanation of important choices:

- `@Order(1)` is for a **specific** public path and exact HTTP method. If you chose an overly broad `/public/**` pattern with `permitAll()`, any endpoint added later under `/public` could become unintentionally public.
- `@Order(2)` applies only to `/api/**`. Three allow rules require exact GET, path, and role; a POST request to the same path will not be granted automatically. `anyExchange().denyAll()` at the end blocks all other APIs even if they have controllers.
- `@Order(Ordered.LOWEST_PRECEDENCE)` places the final chain after specialized chains. Because `securityMatcher` is not called, `ServerHttpSecurity` keeps the default matcher matching every request. This is a true **match-all fallback**, not `securityMatcher("/misc/**")`.
- `httpBasic` is enabled on the two protected chains so HTTP clients can authenticate. `formLogin` is disabled to avoid redirecting API requests to a login page; real systems should select an appropriate mechanism (session, OAuth2 resource server, etc.).
- `{noop}` accepts plaintext passwords **strictly for the localhost demo**. Never hardcode production accounts and never use `{noop}` in real configurations.
- The fallback's `.anyExchange().denyAll()` grants no special ADMIN exemption: **even `admin` is denied** for unlisted routes. "Admin" does not imply permission to access arbitrary endpoints.

### 3.3. Controller to observe the fallback in action

`src/main/java/demo/fallback/DemoController.java`:

```java
package demo.fallback;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/api/reports/{id}")
    public Mono<String> report(@PathVariable String id) {
        return Mono.just("report-" + id);
    }

    @GetMapping("/api/admin/dashboard")
    public Mono<String> adminDashboard() {
        return Mono.just("admin-ok");
    }

    @GetMapping("/api/experimental")
    public Mono<String> experimental() {
        // Real route exists, but has not been permitted in apiChain.
        return Mono.just("experimental-route");
    }

    @GetMapping("/internal/diag")
    public Mono<String> internalDiag() {
        // Real route exists, but does not belong to public or api chains.
        return Mono.just("internal-route");
    }
}
```

The two endpoints `/api/experimental` and `/internal/diag` are added **intentionally in the demo to verify denial**; you should not expose real internal endpoints and rely on a single defense layer alone. `/api/me` reads the principal from the Reactor Context in a reactive-appropriate way. Controllers return `Mono` for WebFlux to manage subscriptions; never call `subscribe()` directly.

## 4. When a request runs, which chain does Spring select?

| Request | Selected chain | Active rule | Demo result |
| --- | --- | --- | --- |
| `GET /public/ping`, no credentials | `publicChain` | `permitAll` | `200`, `pong` |
| `GET /api/me`, no credentials | `apiChain` | `authenticated` | Normally `401` (Basic challenge) |
| `GET /api/me`, valid reader | `apiChain` | `authenticated` | `200`, `reader` |
| `GET /api/reports/42`, valid reader | `apiChain` | `hasRole("READER")` | `200`, `report-42` |
| `GET /api/admin/dashboard`, valid reader | `apiChain` | `hasRole("ADMIN")` | `403` |
| `GET /api/admin/dashboard`, valid admin | `apiChain` | `hasRole("ADMIN")` | `200`, `admin-ok` |
| `GET /api/experimental`, valid admin | `apiChain` | `anyExchange().denyAll()` | `403`, even though the controller exists |
| `GET /internal/diag`, valid admin | **`fallbackChain`** | `anyExchange().denyAll()` | `403`, even though the controller exists |
| `GET /unknown`, valid admin | **`fallbackChain`** | `anyExchange().denyAll()` | `403` before checking handler mappings |
| `POST /public/ping` | **`fallbackChain`** due to method-aware matcher | `denyAll` / possibly CSRF as well | `4xx` |

Why `403` for `/unknown` instead of `404`? Authorization filters can reject a request **before** the router looks up a controller. Hence `403` does not prove the URL actually exists. Conversely, a `404` does not prove a route is properly protected if the request never passed through the right chain.

**401 vs. 403:** With HTTP Basic and this example's setup, a client with missing or invalid credentials on a protected endpoint typically receives `401 Unauthorized` with `WWW-Authenticate`, while an authenticated user lacking permissions or hitting `denyAll` receives `403 Forbidden`. Custom authentication entry points, access denied handlers, login forms, token schemes, or already-committed responses can change the actual response. To prove the fallback works, test **valid login still returning 403**, alongside verifying unauthenticated requests do not return 2xx.

## 5. Running and quick-checking with curl

Run inside the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

To run Maven, you need JDK 17+, Maven, and dependency download access. Wait for the log indicating the Netty server started on port 8080. In another terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user reader:reader123 http://localhost:8080/api/me
curl -i --user reader:reader123 http://localhost:8080/api/reports/42
curl -i --user reader:reader123 http://localhost:8080/api/admin/dashboard
curl -i --user admin:admin123 http://localhost:8080/api/admin/dashboard
curl -i --user admin:admin123 http://localhost:8080/api/experimental
curl -i --user admin:admin123 http://localhost:8080/internal/diag
curl -i --user admin:admin123 http://localhost:8080/unknown
```

Expected statuses in order: **200, 401, 200, 200, 403, 200, 403, 403, 403**. Successful bodies are `pong`, `reader`, `report-42`, `admin-ok` respectively. In Windows PowerShell where `curl` is an alias, call `curl.exe`. `curl -i` shows both status and headers; do not inspect only the body.

In particular, the last two commands confirm the fallback's role: **even a fully authenticated admin cannot access** endpoints outside the permitted zones. The `/api/experimental` command confirms the role of `anyExchange().denyAll()` *inside apiChain*. Without a fallback, `/internal/diag` might no longer pass through Spring Security; if `denyAll` inside `apiChain` were replaced by an overly broad rule, `/api/experimental` could be opened accidentally.

You can check the HTTP code concisely on a Unix-like shell:

```bash
curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}\n' \
  --user admin:admin123 \
  http://localhost:8080/internal/diag
```

Output:

```text
403
```

Do not equate **curl exit code 0** with HTTP status 200: by default `curl` still exits 0 when the server returns 403. Read `%{http_code}` or the status line. Never use demo passwords as real passwords; Basic only uses Base64 and does not replace HTTPS transport encryption.

## 6. WebTestClient: locking down rules with automated tests

A fallback configuration is only trustworthy when tests prove: public paths remain open; permitted endpoints work; wrong roles are blocked; **routes that have controllers outside specialized chains are blocked**; and routes under the API prefix without an explicit rule are still blocked.

With WebFlux and Spring Boot `RANDOM_PORT`, `@SpringBootTest` starts a real HTTP server on a random port, and `WebTestClient` sends requests to that server. You do not need to run `mvn spring-boot:run` before executing tests. The tests use Basic headers to exercise the real HTTP pipeline rather than mocking a `SecurityContext` in an isolated session.

`src/test/java/demo/fallback/FallbackSecurityTests.java`:

```java
package demo.fallback;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FallbackSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicGetIsAnonymous() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void apiNeedsAuthentication() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void readerCanReadOwnName() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void readerCanReadReport() {
        client.get().uri("/api/reports/42")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-42");
    }

    @Test
    void readerCannotAccessAdmin() {
        client.get().uri("/api/admin/dashboard")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/api/admin/dashboard")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void unknownApiPathIsDeniedWithinApiChain() {
        client.get().uri("/api/experimental")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void internalEndpointIsDeniedByFallback() {
        client.get().uri("/internal/diag")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownTopLevelPathIsDeniedByFallback() {
        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousCannotReachInternalEndpoint() {
        client.get().uri("/internal/diag")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
```

Run:

```bash
mvn test
```

If the project contains only this test class, **10 tests are expected to pass**; do not rely on a fixed Maven log output. `.isForbidden()` assertions use authenticated accounts, distinguishing permission-based denial from unauthenticated rejection. `anonymousCannotReachInternalEndpoint` only requires `4xx` because some authentication handler setups return 401 or 403; what is mandatory is **never returning 2xx/3xx leading to protected content**.

The most valuable tests are `unknownApiPathIsDeniedWithinApiChain` and `internalEndpointIsDeniedByFallback`: both controllers **actually exist**, yet they are blocked at two different places. If someone accidentally changes the fallback to `permitAll()`, `internalEndpointIsDeniedByFallback` fails. If someone loosens the API to `anyExchange().authenticated()`, `unknownApiPathIsDeniedWithinApiChain` catches that an unapproved path was opened to users.

### 6.1. Ensuring tests actually run through security WebFilters

- With `@SpringBootTest(RANDOM_PORT)`, tests run over HTTP and through all filters configured in the application context. Never replace them with unit tests calling `controller.internalDiag()` directly: that bypasses `SecurityWebFilterChain`.
- If using `@WebFluxTest` slices, verify the chain beans are loaded and dependencies are properly mocked/imported. A test running through WebFlux without loading security config does not prove the system fails closed.
- With plain `WebTestClient.bindToController(...)`, security filters are not included by default; bind to the `WebApplicationContext` or configure appropriately to test policies.
- Do not use client-side `mockUser` when testing a real server via `RANDOM_PORT`; `mockUser` is meant for appropriate mock web context tests. Over real HTTP, send Basic, Bearer tokens, or cookies/sessions matching what the server uses.
- Run the entire test suite after adding paths or changing matchers. Passing a single test on `/api/me` is not enough to detect `/internal/diag` being left exposed.

## 7. Choosing denyAll vs. authenticated as the default

A fallback chain can use:

```java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated())
```

This enforces a valid identity, yet **it can expose every newly added endpoint to all logged-in users**. Whenever an internal, admin, or experimental endpoint appears before being listed, `authenticated()` lacks the corresponding role or domain permission check. The fail-closed approach for this lesson is:

```java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().denyAll())
```

These are **two configuration fragments**, not two complete Java programs. `denyAll()` turns adding a new route into an event that requires deliberate rule updates and testing. For user-facing apps, you may configure a fallback of `authenticated()` **only if** the product requirement truly states that every route outside special groups is meant for all logged-in users; in that case, control scope via reviews, tests, and service-layer permissions. Choose the policy based on the permission model, not on whether 401 or 403 "looks nicer".

**Do not broaden `permitAll` to fix 404 errors.** Doing so can expose endpoints unintentionally. Returning 403 for nonexistent URLs is a valid consequence of fail-closed. If the product requires returning 404 for a set of URLs, design that explicitly in routing/error handling and assess the security impact; never weaken the global default.

## 8. Real-world mistakes when configuring fallbacks

### 8.1. Placing the catch-all chain too early

**Wrong:**

```java
@Bean
@Order(1)
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().denyAll())
        .build();
}
```

Because its default matcher is match-all, both `/public/ping` and `/api/me` match this chain first; later API/public chains are never selected. Put the fallback last (`Ordered.LOWEST_PRECEDENCE`, or omit `@Order` when specialized chains are guaranteed higher priority); explicit ordering makes maintenance easier.

### 8.2. Having only a single chain with a narrow securityMatcher

Sometimes a configuration specifies `securityMatcher("/api/**")` and assumes `anyExchange()` inside it means "every request arriving at the server". In reality, it only means **every request that matched `/api/**` and entered that chain**. Paths outside scope need a match-all fallback.

### 8.3. Thinking the fallback continues running after an earlier chain denies

Spring Security does not look for a "next allowing chain" once the policy inside the selected chain returns deny. A request `/api/experimental` that already matched `apiChain` never touches the fallback; hence **every specialized chain must also have an appropriate final default**. That final rule must come after specific rules because rule ordering inside `authorizeExchange` matters.

### 8.4. Overly broad or overlapping matchers

For example, `/api/**` placed before `/api/admin/**` captures admin requests too if those two are separate ordered chains. The dedicated admin chain never runs. There are two proper fixes: place the admin matcher before the general matcher, or use **a single API chain** and declare `/api/admin/**` before broader rules in `authorizeExchange`. Never carelessly use `/public/**` + `permitAll` when intending a single URL. For method-dependent matchers, test actual GET/POST/PUT/DELETE/OPTIONS requests.

### 8.5. Using the wrong Spring Security stack

In WebFlux, use `SecurityWebFilterChain` + `ServerHttpSecurity` + `ServerWebExchangeMatcher`. Examples using `SecurityFilterChain` + `HttpSecurity` + `RequestMatcher` belong to the **Servlet** API and cannot be copied verbatim into a reactive app.

### 8.6. Loosening permissions just to "fix" a 403

403 can be caused by `denyAll` (default), a missing role, or CSRF on state-changing methods; 401 can be caused by missing Basic/Bearer tokens; CORS can make browsers block scripts even when curl succeeds. Inspect the request method, path, status, challenge headers, chain configuration, and logs before changing policies. Never change `anyExchange().denyAll()` to `permitAll()` just to make a failing 403 test turn green.

### 8.7. Assuming a fallback guarantees data is always protected

The fallback operates at the HTTP boundary of the corresponding WebFlux application. It **does not replace** service-layer permission checks, per-record permissions, `@EnableReactiveMethodSecurity`/`@PreAuthorize`, multi-tenant isolation, or upstream validation. For instance, an allowed route `GET /api/reports/42` must still verify whether the current reader has access to **report 42**. `ROLE_READER` alone does not prove access to all data.

## 9. Exceptions and scope to review before production deployment

**Health, readiness, metrics, and actuator:** Never blindly open all of `/actuator/**` with `permitAll`. Permit only endpoints that truly need to be public (such as readiness), keeping metrics/env/heapdump and sensitive info authenticated, restricted, or unexposed. If Actuator runs on a **separate management port/ApplicationContext**, inspect that context's security configuration separately; a fallback in the main web context does not automatically protect other servers/ports.

**CORS and preflight:** Browsers can send `OPTIONS` preflight requests before making cross-origin API calls; if `apiChain` only allows GET and has `anyExchange().denyAll()`, `OPTIONS` preflights may be blocked. When legitimate cross-origin clients exist, define CORS and an explicit `OPTIONS` policy and test specific origins/headers; never `permitAll` every method/path just to fix CORS. `OPTIONS` and `GET` are two distinct requests.

**CSRF:** Spring Security WebFlux enables CSRF protection under common default setups; POST/PUT/PATCH/DELETE may receive 403 due to a missing token before reaching expected authorization rules. Our GET-only example does not need to disable CSRF. With pure token-based APIs, you can design CSRF handling accordingly if appropriate, but you must understand your credential/cookie model before disabling it.

**Login, logout, and framework endpoints:** Enabling form login, OAuth2 login, or logout may introduce framework-handled endpoints. An overly narrow matcher or a deny-all fallback can block login/callback flows before their dedicated filters run. Assign `/login`, `/logout`, `/oauth2/**`, callbacks, and error pages cleanly to the appropriate chain; avoid opening entire prefixes indiscriminately.

**Proxy, gateway, and forwarding:** Test both external paths and the actual paths received by the WebFlux app after proxy/gateway rewrites. Matchers run on the request details **actually arriving at the application**, not on API gateway documentation assumptions. Context paths, base paths, forwarded headers, URL encoding, and trailing slashes can make match results differ from expectations. Avoid treating firewall URL normalization as a substitute for security matchers.

**Functional routes and static resources:** `RouterFunction` routes, WebSocket handshakes, static assets, or new controllers also pass through the HTTP boundary if in the same WebFlux context, so test their URLs and methods. If static assets are public, expose **only the exact paths needed**, avoiding accidentally placing new APIs inside a broad public prefix.

**Other `SecurityWebFilterChain` beans:** Another plugin or module configuration might declare a catch-all chain or broad-matcher chain with higher `@Order` and shadow your fallback. Audit all chain beans across the entire application in effective order during integration; never assume only the three demo beans exist.

## 10. Process for adopting this in an existing project

1. **List existing security chains:** Every `SecurityWebFilterChain` bean, `@Order`, `securityMatcher`, authentication mechanism, `authorizeExchange` rules, and `anyExchange` placement. This is a design-audit step during integration, not an instruction to copy another app's rules.
2. **Group real URLs:** Identify public, admin, permitted API, and internal paths. Record HTTP methods, required permissions, and authentication mechanisms rather than listing prefixes alone.
3. **Place specialized chains first:** Use sufficiently specific matchers without overlap; end each chain fail-closed if unlisted routes should not be open.
4. **Add a match-all fallback last:** Omit `securityMatcher` on the fallback; use `anyExchange().denyAll()` to reject any leftover paths. Ensure no higher-priority chain accidentally matches everything.
5. **Write negative tests before opening new routes:** A real endpoint outside specialized matchers must be blocked even with a valid user; an endpoint under the API prefix without a rule must be blocked. Test valid/invalid roles and different HTTP methods.
6. **Open routes per product requirements:** Add the matcher/rule and tests confirming the permitted route; then re-run all out-of-scope denial tests.
7. **Check the next layers:** Protect permissions on data, services, and reactive flows; handle CORS/CSRF/login/logout, actuator, and proxies per deployment model.

You can maintain a review policy table:

| Category | Method | Pattern | Chain | Desired outcome |
| --- | --- | --- | --- | --- |
| Public | GET | `/public/ping` | Public | Anonymous 200 |
| User | GET | `/api/me` | API | Anonymous 401; authenticated 200 |
| Report | GET | `/api/reports/**` | API | READER 200; missing role 403 |
| Admin | GET | `/api/admin/dashboard` | API | ADMIN 200; READER 403 |
| Undeclared API | Any | `/api/experimental` | API default deny | Denied |
| Out-of-group path | Any | `/internal/diag` | Fallback | Denied |
| New URL | Any | Outside permitted groups | Fallback | Denied |

## 11. Self-assessment questions

**Question 1:** A request `GET /api/experimental` matches `apiChain`, but matches no allow rule. Does it move on to the fallback?  
**No.** The chain is chosen by matcher first, and then that chain's policy decides; API's `anyExchange().denyAll()` rejects it.

**Question 2:** Is a fallback that does not declare `securityMatcher` truly match-all?  
**Yes, under `ServerHttpSecurity`'s default** in the example. If you manually give the fallback a narrow matcher, it stops protecting all remaining requests.

**Question 3:** Why is `@Order(1)` unsuitable for the fallback?  
Because a match-all fallback captures every request before specialized chains, preventing public/API chains from being chosen.

**Question 4:** If the fallback is changed to `authenticated()`, can a logged-in user call `/internal/diag`?  
**Yes, potentially**, because that user satisfies `authenticated()`, even though the endpoint was never specifically authorized. That is why `denyAll()` is chosen when fail-closed is required.

**Question 5:** Does a test getting 403 on `/unknown` prove a controller exists?  
**No.** Security can reject before routing; use an **actually existing** endpoint like `/internal/diag` to prove the fallback blocks controllers.

**Question 6:** Once a fallback chain exists, can per-record authorization tests be skipped?  
**No.** The fallback protects unlisted HTTP boundaries; permitted routes still require authorization per user, resource, and business context.

### Official references

- Spring Security, *WebFlux Security — Multiple Chains Support*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security, `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security, `PathPatternParserServerWebExchangeMatcher` API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html
- Spring Boot, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html

**Must remember:** To avoid leaving paths exposed, you need **two locks**: (1) `anyExchange().denyAll()` inside every specialized chain that has selective rules, to block new routes *inside* that chain's scope; (2) a match-all `SecurityWebFilterChain` with the lowest priority and `denyAll()`, to block routes *outside* all specialized chains. Verify with tests containing both real blocked controllers and permitted requests taking the right path.