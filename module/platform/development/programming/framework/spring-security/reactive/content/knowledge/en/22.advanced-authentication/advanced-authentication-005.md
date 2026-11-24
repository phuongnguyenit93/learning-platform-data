# Placing Custom Filters with addFilterAt, addFilterBefore, and addFilterAfter

**Module: Spring Security Reactive · Advanced Authentication · Java 17+ / Spring WebFlux**

## 1. Objectives and Scenario

A Spring WebFlux application already has Spring Security validating HTTP Basic, JWT, or form login. When you need to attach a correlation ID, observe the caller identity, handle a new authentication scheme, or measure request latency, you may want to add a `WebFilter`. The issue is that **filter placement determines whether `Authentication`, 401/403 responses, and the response lifecycle are visible**. Placed incorrectly, a custom filter might run before credentials are verified, be skipped when an earlier filter rejects the request, or accidentally execute twice.

Spring Security Reactive provides three configuration methods on `ServerHttpSecurity`:

- **addFilterBefore(WebFilter, SecurityWebFiltersOrder)**: inserts a filter before a milestone.
- **addFilterAt(WebFilter, SecurityWebFiltersOrder)**: inserts a filter at that exact milestone.
- **addFilterAfter(WebFilter, SecurityWebFiltersOrder)**: inserts a filter after a milestone.

After this lesson, you will be able to explain the exact difference among the three methods, choose milestones based on the active authentication mechanisms, write a **compilable Java 17+ example**, test with `WebTestClient`, and avoid critical pitfalls: confusing Servlet APIs, mistaking placement for replacement, trusting unverified `X-User` headers, losing Reactor `SecurityContext`, double-registration, manual `subscribe()`/`block()`, and modifying responses after commit.

**Key rule:** `addFilterAt` **does not automatically replace an existing WebFilter**. Placing a filter in the right order also **does not** turn unverified credentials into a trusted identity.

## 2. Distinguishing WebFilter, SecurityWebFilterChain, and Servlet Filters

Spring WebFlux uses:

~~~java
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
~~~

Contract:

~~~java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
~~~

This is the library's illustrative signature, not an interface you declare in your project. `WebFilter` operates on **ServerWebExchange**, reading requests, responses, and attributes, and returning a **Mono<Void>** representing asynchronous work.

| Difference | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Filter | jakarta.servlet.Filter | org.springframework.web.server.WebFilter |
| Request | HttpServletRequest | ServerWebExchange |
| Security config | HttpSecurity | ServerHttpSecurity |
| Chain | SecurityFilterChain | SecurityWebFilterChain |
| addFilter anchor | Filter class | SecurityWebFiltersOrder enum |
| Security context | Typically ThreadLocal | Reactor Context via ReactiveSecurityContextHolder |
| Execution model | Servlet pipeline | Publisher, non-blocking, cancellation |

**The following is wrong in WebFlux:**

~~~java
// Servlet API, not reactive ServerHttpSecurity.
http.addFilterBefore(myFilter,
        UsernamePasswordAuthenticationFilter.class);
~~~

Correct in WebFlux:

~~~java
http.addFilterBefore(
        myWebFilter,
        SecurityWebFiltersOrder.AUTHENTICATION);
~~~

These snippets illustrate the API; the complete configuration file is in Section 7.

### 2.1. Where Does the Filter Run?

~~~text
HTTP request (Reactor Netty)
        |
        v
Global WebFlux WebFilters (if any)
        |
        v
Spring Security WebFilterChainProxy
        |
        +-- selects one SecurityWebFilterChain by securityMatcher/@Order
        |
        v
Internal security chain
        |
        +-- HTTP_HEADERS_WRITER
        +-- CORS / CSRF
        +-- REACTOR_CONTEXT
        +-- HTTP_BASIC / FORM_LOGIN / AUTHENTICATION
        +-- ANONYMOUS_AUTHENTICATION
        +-- EXCEPTION_TRANSLATION / AUTHORIZATION
        +-- added custom WebFilters
        |
        v
Controller / RouterFunction
~~~

This diagram is conceptual; **exact ordering must be checked against `SecurityWebFiltersOrder` in your version**, and certain milestones appear only when the corresponding feature is enabled. A Spring WebFlux global `WebFilter` lives in a **different layer** from a filter inside `SecurityWebFilterChain`. A filter inside the chain does not run on requests blocked earlier by a proxy/gateway or routed to another chain.

## 3. Semantics of the Three Methods in Spring Security 6.5

Signatures:

~~~java
ServerHttpSecurity addFilterBefore(
        WebFilter webFilter,
        SecurityWebFiltersOrder order);

ServerHttpSecurity addFilterAt(
        WebFilter webFilter,
        SecurityWebFiltersOrder order);

ServerHttpSecurity addFilterAfter(
        WebFilter webFilter,
        SecurityWebFiltersOrder order);
~~~

The current implementation positions custom filters based on the enum's order value:

~~~text
addFilterBefore(f, X): position(X) - 1
addFilterAt(f, X):     position(X)
addFilterAfter(f, X):  position(X) + 1
~~~

This explains the implementation behavior; **hardcoding numeric orders is discouraged**. Always use the enum provided by Spring Security.

| Method | Intent | What Must Not Be Assumed |
| --- | --- | --- |
| addFilterBefore | Place WebFilter before a slot | Runs before every other filter |
| addFilterAt | Place WebFilter at the same slot | Replaces, disables, or overrides built-in filter |
| addFilterAfter | Place WebFilter after a slot | Always runs, even if blocked earlier |

### 3.1. addFilterAt Is Not Replace

Example:

~~~java
http.httpBasic(Customizer.withDefaults());
http.addFilterAt(
        customFilter, SecurityWebFiltersOrder.HTTP_BASIC);
~~~

Spring Security **does not remove the HTTP Basic `AuthenticationWebFilter`**. A custom `WebFilter` at the same order coexists with the built-in filter, and **there is no ordering guarantee** between filters at the exact same position. If one filter depends on another having already run, place them before/after at **distinct appropriate milestones**, or build a dedicated authentication mechanism with explicit matchers.

If you genuinely intend to replace an authentication mechanism, you must **intentionally disable the built-in mechanism** while registering a proper `AuthenticationWebFilter`/`ReactiveAuthenticationManager` with success/failure handling, context repository, and 401/403 behavior. Never use `addFilterAt` as a shortcut to disable security.

### 3.2. addFilterBefore Is Only Relative to the Specified Milestone

`addFilterBefore(custom, HTTP_BASIC)` means `custom` runs before the **`HTTP_BASIC` slot**, not necessarily before CORS, CSRF, security headers, or other OAuth2 filters. Requests rejected early by CORS/CSRF may never reach the custom filter.

### 3.3. addFilterAfter Is Not Equivalent to doFinally

`addFilterAfter` sets the **invocation position** in the chain. By contrast, a Publisher's `doOnSuccess`/`doFinally` concerns **completion** of the reactive sequence. Those are two different concepts.

~~~java
// This snippet illustrates the reactive lifecycle.
// Metric recording lives in an application helper.
return chain.filter(exchange)
        .doFinally(signal -> metrics.record(signal.name()));
~~~

Do not use `doFinally` to write response headers: the response may already be committed. For headers, prefer the `headers.writer` DSL or `ServerHttpResponse.beforeCommit` registered early. Never call `subscribe()` or `block()` inside a `WebFilter`.

## 4. SecurityWebFiltersOrder and Choosing a Milestone

The `SecurityWebFiltersOrder` enum lives in **org.springframework.security.config.web.server.SecurityWebFiltersOrder**.

| Milestone | Meaning | Guidance |
| --- | --- | --- |
| FIRST | Early position in security chain | Early observer, does not replace global ingress |
| HTTP_HEADERS_WRITER | Security headers | Usually prefer HeaderSpec writer |
| HTTPS_REDIRECT | Supports HTTPS redirection | Do not roll ad-hoc redirects |
| CORS | Handles CORS/preflight | Use CorsConfigurationSource |
| CSRF | Protects requests using browser credentials | Keep standard mechanism |
| REACTOR_CONTEXT | Loads SecurityContext in Reactor | Read Context along the pipeline |
| HTTP_BASIC | Basic AuthenticationWebFilter | Before Basic for tracing, after auth to observe |
| FORM_LOGIN | Form AuthenticationWebFilter | Suited for login pages/cookies |
| AUTHENTICATION | Slot for authentication extensions | Insert custom AuthenticationWebFilter here |
| ANONYMOUS_AUTHENTICATION | Anonymous support | Do not mistake anonymous for logged-in user |
| EXCEPTION_TRANSLATION | Translates security exceptions to HTTP responses | Do not bypass 401/403 |
| AUTHORIZATION | Access decision via authorizeExchange | Filters after this may miss blocked requests |
| LAST | Final slot in security chain | Not guaranteed to see gateway errors |

Other milestones cover logout, OAuth2 authorization code, request cache, and security context. Do not pick a milestone by guessing numeric values; **pick based on the actual mechanisms enabled in your app**.

### 4.1. Choosing Order by Trust Boundary

- Need tracing before Basic authentication: **before HTTP_BASIC**.
- Need to run a new auth mechanism: **at AUTHENTICATION**, using an `AuthenticationWebFilter` backed by a real verifying manager.
- Need to read the principal after Basic and before `authorizeExchange`: **after AUTHENTICATION** can work because in this demo `HTTP_BASIC` runs before the `AUTHENTICATION` slot.
- Need to observe every blocked request: a `WebFilter` after `AUTHORIZATION` is **not enough**, because authorization may return 403 without invoking downstream filters.
- Need response headers: `HeaderSpec` or `beforeCommit`, never mutating headers after commit.
- Need per-user rate limiting: use only the verified principal, never a client-supplied `X-User` header.

## 5. Flow in the Lab Exercise

The demo has one `SecurityWebFilterChain`:

~~~text
GET /api/me
     |
     v
Spring defaults: headers, CSRF, context...
     |
     v
TraceMarkerFilter("before-basic")
  addFilterBefore(..., HTTP_BASIC)
     |
     v
HTTP Basic AuthenticationWebFilter
  valid credential -> Authentication in Reactor Context
  invalid credential -> may return 401, does not continue
     |
     v
TraceMarkerFilter("at-authentication")
  addFilterAt(..., AUTHENTICATION)
     |
     v
VerifiedPrincipalObserverFilter
  addFilterAfter(..., AUTHENTICATION)
  reads ReactiveSecurityContextHolder, ignores X-User
     |
     v
Spring authorization filter
     |
     +-- 401 if unauthenticated, 403 if insufficient authority
     |
     v
Controller if permitted
~~~

**Note:** In other architectures, `AuthenticationWebFilter` runs at a different milestone—such as OAuth2, form login, or bearer tokens. Do not assume an observer after `AUTHENTICATION` sees **every** authenticated mechanism if that mechanism lives at another slot. Real tests must match your configuration model.

### 5.1. Endpoint Matrix

| Method/URL | Who May Call | Result |
| --- | --- | --- |
| GET /public/ping | Anyone | 200 |
| GET /api/me | Authenticated | 200 or 401 |
| GET /api/admin | ROLE_ADMIN | 200 or 401/403 |
| GET /unknown | denyAll | 403 for authenticated user |

Local fixtures:
- alice / alice-pass → ROLE_USER
- admin / admin-pass → ROLE_USER, ROLE_ADMIN

Observable goal via the lab header:

~~~http
X-Lab-Filter-Trace: before-basic > at-authentication > after-authentication
~~~

This trace line appears only on **requests that pass through all three filters**. When a Basic password fails or CSRF blocks early, downstream filters may not execute. The lab header is **not** a production security header; it is strictly for teaching and testing and should be removed in production.

## 6. Complete Java 17+ Spring Boot WebFlux Project

Structure:

~~~text
webflux-filter-placement/
├── settings.gradle
├── build.gradle
├── src/main/java/example/filterorder/FilterPlacementApplication.java
├── src/main/java/example/filterorder/TraceMarkerFilter.java
├── src/main/java/example/filterorder/VerifiedPrincipalObserverFilter.java
├── src/main/java/example/filterorder/SecurityConfig.java
├── src/main/java/example/filterorder/DemoController.java
└── src/test/java/example/filterorder/FilterPlacementTest.java
~~~

Uses **Spring Boot 3.5.16**, Java 17+, and compatible Gradle 8.x. The Spring Boot BOM manages Spring Security/Reactor. This is a WebFlux project—**do not add Servlet `spring-boot-starter-web`**.

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-filter-placement'
~~~

### 6.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 6.3. FilterPlacementApplication.java

~~~java
package example.filterorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterPlacementApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterPlacementApplication.class, args);
    }
}
~~~

### 6.4. TraceMarkerFilter.java

~~~java
package example.filterorder;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class TraceMarkerFilter implements WebFilter {

    public static final String TRACE_HEADER =
            "X-Lab-Filter-Trace";

    private static final String TRACE_ATTRIBUTE =
            TraceMarkerFilter.class.getName() + ".steps";

    private final String marker;

    public TraceMarkerFilter(String marker) {
        this.marker = Objects.requireNonNull(marker);
    }

    static void record(
            ServerWebExchange exchange,
            String marker) {

        @SuppressWarnings("unchecked")
        List<String> steps =
                (List<String>) exchange.getAttribute(TRACE_ATTRIBUTE);

        if (steps == null) {
            steps = new ArrayList<>();
            exchange.getAttributes().put(TRACE_ATTRIBUTE, steps);

            List<String> stepsRef = steps;
            exchange.getResponse().beforeCommit(() -> {
                exchange.getResponse().getHeaders().set(
                        TRACE_HEADER, String.join(" > ", stepsRef));
                return Mono.empty();
            });
        }

        steps.add(marker);
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        record(exchange, marker);
        return chain.filter(exchange);
    }
}
~~~

**Explanation:**

- Trace markers live in **per-request `ServerWebExchange` attributes**. Never use a shared static `List` across all requests.
- Both `TraceMarkerFilter` instances are instantiated inside `SecurityConfig`, not declared as global Spring `WebFilter` beans.
- The response header is written in `response.beforeCommit`; by the time `doFinally` runs, the response may already be committed.
- The filter neither extracts credentials nor fabricates Authentication, and always forwards exactly once.
- `ArrayList` is sufficient for a linear demo; if concurrent branches mutate the same collection, handle concurrency explicitly.
- `X-Lab-Filter-Trace` is strictly for learning; never expose chain internals in public production.

### 6.5. VerifiedPrincipalObserverFilter.java

~~~java
package example.filterorder;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class VerifiedPrincipalObserverFilter
        implements WebFilter {

    public static final String PRINCIPAL_ATTRIBUTE =
            VerifiedPrincipalObserverFilter.class.getName()
                    + ".verifiedPrincipal";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(auth -> auth != null
                        && auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .defaultIfEmpty("guest")
                .flatMap(name -> {
                    exchange.getAttributes().put(
                            PRINCIPAL_ATTRIBUTE, name);
                    TraceMarkerFilter.record(
                            exchange, "after-authentication");
                    return chain.filter(exchange);
                });
    }
}
~~~

Here **ReactiveSecurityContextHolder** retrieves Authentication from the Reactor subscriber Context. Never use Servlet's thread-local `SecurityContextHolder` as the default identity source. Once HTTP Basic verifies `alice`, the observer sees `alice`. When no Authentication is present, the demo uses `guest`; anonymous is not treated as a logged-in user.

If you need accurate auditing of login success/failure, prefer `ServerAuthenticationSuccessHandler`/`FailureHandler` instead of assuming an observer runs on every branch. Never log passwords, Authorization tokens, or cookie/session IDs.

### 6.6. SecurityConfig.java

~~~java
package example.filterorder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(
            PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/admin").hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)

                // Before HTTP Basic; Basic is still executed by Spring.
                .addFilterBefore(
                        new TraceMarkerFilter("before-basic"),
                        SecurityWebFiltersOrder.HTTP_BASIC)

                // Same AUTHENTICATION slot; does not replace the existing filter.
                .addFilterAt(
                        new TraceMarkerFilter("at-authentication"),
                        SecurityWebFiltersOrder.AUTHENTICATION)

                // Observe Principal after the AUTHENTICATION slot.
                .addFilterAfter(
                        new VerifiedPrincipalObserverFilter(),
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

**Configuration takeaways:**

1. Filters are instantiated with `new` **strictly inside `SecurityWebFilterChain`**, avoiding double-registration as global `WebFilter`s.
2. HTTP Basic is a built-in auth mechanism and is not replaced by `addFilterAt(AUTHENTICATION)`.
3. The admin rule comes before general rules; roles come from `UserDetailsService` verified through the password encoder.
4. `formLogin` is intentionally disabled because this is an HTTP Basic lab; **do not disable CSRF** or default security headers.
5. When a request is rejected with 401 at HTTP Basic, downstream `WebFilter`s do not necessarily run.
6. Mechanisms sharing the same `AUTHENTICATION` order slot have **no guaranteed relative ordering**; the demo writes no logic depending on order relative to a built-in filter in that slot.
7. Never use these filters to replace `authorizeExchange` or assign authorities from client headers.

### 6.7. DemoController.java

~~~java
package example.filterorder;

import java.security.Principal;
import java.util.Map;
import java.util.Objects;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            Mono<Principal> principal,
            ServerWebExchange exchange) {

        Object observed = exchange.getAttribute(
                VerifiedPrincipalObserverFilter.PRINCIPAL_ATTRIBUTE);

        return principal.map(actor -> Map.of(
                "principal", actor.getName(),
                "observer",
                Objects.toString(observed, "missing")));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("result", "admin-ok"));
    }
}
~~~

`DemoController` receives the **Spring Security-verified `Principal`** from the reactive argument resolver; it never trusts client-supplied `X-User`/`X-Role`. The `observer` field exists solely to prove filter placement in this lesson and should be omitted from production endpoints unless needed by business logic.

### 6.8. Running the Application

~~~bash
gradle bootRun
~~~

With Java 17+ and compatible Gradle, Spring Boot listens on `http://localhost:8080` by default. Accounts:

~~~text
alice : alice-pass  → ROLE_USER
admin : admin-pass  → ROLE_USER, ROLE_ADMIN
~~~

These are local fixtures. HTTP Basic only Base64-encodes credentials; it **does not encrypt transport**. Production requires HTTPS and a real identity store; never use sample passwords.

## 7. Testing with curl and Status Codes

### 7.1. Public Endpoint

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expected status 200 and trace header:

~~~http
HTTP/1.1 200 OK
X-Lab-Filter-Trace: before-basic > at-authentication > after-authentication
X-Content-Type-Options: nosniff

{"status":"ok"}
~~~

Additional headers and ordering may vary; these are the primary markers to check.

### 7.2. Successful Authentication

~~~bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/me
~~~

Expected status 200 and body containing two fields:

~~~json
{"principal":"alice","observer":"alice"}
~~~

JSON key ordering is not guaranteed; `WebTestClient` uses JSONPath. This proves the observer reads the **authenticated principal** from Reactor Context.

### 7.3. Spoofed Headers Do Not Elevate Privileges

~~~bash
curl -i -u alice:alice-pass \
  -H 'X-User: admin' -H 'X-Role: ADMIN' \
  http://localhost:8080/api/me
~~~

Expected output remains `principal=alice`, `observer=alice`. A client cannot become admin through self-declared headers.

### 7.4. Missing Credentials → 401

~~~bash
curl -i http://localhost:8080/api/me
~~~

Expected HTTP 401 and `WWW-Authenticate` Basic. Trace filters do not grant login access.

### 7.5. Wrong Password → 401

~~~bash
curl -i -u alice:wrong \
  http://localhost:8080/api/me
~~~

Expected 401. The Basic filter can terminate the flow before custom filters placed after `HTTP_BASIC`; do not assert that all trace markers appear on failed requests.

### 7.6. User Without ROLE_ADMIN → 403

~~~bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/admin
~~~

Expected 403, not 200. Custom filters do not override `authorizeExchange` rules.

### 7.7. Valid Admin → 200

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
~~~

Expected:

~~~json
{"result":"admin-ok"}
~~~

When you only want headers from a **GET**, use `curl -sS -D - -o /dev/null` rather than `curl -I` assuming it sends GET: `curl -I` sends HEAD. Avoid logging `Authorization`/`Cookie`. On Windows PowerShell use `curl.exe`; the line continuations above follow Bash syntax.

## 8. Testing with WebTestClient

File **src/test/java/example/filterorder/FilterPlacementTest.java**:

~~~java
package example.filterorder;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterPlacementTest {

    @Autowired
    WebTestClient client;

    private static final String FULL_TRACE =
            "before-basic > at-authentication > after-authentication";

    @Test
    void publicEndpointHasThreeMarkersInOrder() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE)
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void basicUserIsVisibleInReactiveSecurityContext() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE)
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice")
                .jsonPath("$.observer").isEqualTo("alice");
    }

    @Test
    void forgedUserHeaderCannotOverridePrincipal() {
        client.get().uri("/api/me")
                .headers(h -> {
                    h.setBasicAuth("alice", "alice-pass");
                    h.set("X-User", "admin");
                    h.set("X-Role", "ADMIN");
                })
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice")
                .jsonPath("$.observer").isEqualTo("alice");
    }

    @Test
    void anonymousPrivateRequestGets401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void spoofedHeadersWithoutCredentialGet401() {
        client.get().uri("/api/me")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ordinaryUserGets403ForAdmin() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminHasAccess() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE)
                .expectBody()
                .jsonPath("$.result").isEqualTo("admin-ok");
    }

    @Test
    void unknownUrlRemainsDenied() {
        client.get().uri("/unknown")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void builtInSecurityHeadersRemainPresent() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff")
                .expectHeader().value(
                        HttpHeaders.CACHE_CONTROL,
                        value -> assertTrue(
                                value.contains("no-store")));
    }

    @Test
    void traceContainsOneOccurrenceOfEachMarker() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        TraceMarkerFilter.TRACE_HEADER, FULL_TRACE);
    }
}
~~~

Run tests:

~~~bash
gradle test
~~~

**Expected result** is **11 JUnit tests PASS** given compatible code, JDK, and dependencies. This is an expected result from the design; **not a claim that Gradle was executed while authoring this content**.

Test cases were chosen because:

- Public 200 verifies markers from all three filters and their order through the chain.
- Successful HTTP Basic verifies the observer sees the authenticated `Principal`.
- Spoofed `X-User`/`X-Role` do not alter `Authentication`.
- Missing credentials or wrong passwords still return 401.
- Alice without `ROLE_ADMIN` still gets 403; valid admin gets 200.
- Unknown URLs are not turned public by custom filters.
- Default `no-sniff`/`no-store` security headers remain present.
- No duplicate trace markers from accidentally registering a filter twice.

**Do not assert all three markers on every 401/403**: an authentication, authorization, CSRF, or CORS filter can short-circuit before some custom filters. Status codes and security semantics must be the primary proof.

### 8.1. Testing vs Production Proof

`WebTestClient` runs the application and Spring Security chain, whereas production introduces proxies, multiple chains, TLS termination, event loop errors, and different tracing setups. Monitor metrics, latency, response headers, and concurrent requests as well; never log raw credentials to debug.

## 9. Choosing Filter Placement Based on Requirements

| Goal | Recommended Placement or API | Reason |
| --- | --- | --- |
| Attach request correlation ID before HTTP Basic | `addFilterBefore(..., HTTP_BASIC)` | ID exists before Basic challenge/failure |
| Custom partner credential mechanism | `AuthenticationWebFilter` at `AUTHENTICATION` | AuthManager must verify credentials |
| Observe authenticated principal | `addFilterAfter` relative to the right auth anchor | Reactor context may hold Authentication |
| HTTP security headers | `ServerHttpSecurity.headers` / writer | Never mutate after response commit |
| CORS preflight | `ServerHttpSecurity.cors` / `CorsConfigurationSource` | Applies standard CORS |
| CSRF | `ServerHttpSecurity.csrf` | Never disable because of a custom observer |
| Owner/tenant authorization | Service/domain checks and method security | Scope/role alone is insufficient per object |
| Log all requests even before security | Global observation/gateway | Independent of selected security chain |
| URL authorization | `authorizeExchange` | Never replace with `if` on raw headers |
| Audit login success/failure | Authentication success/failure handlers | Cleaner event semantics than an arbitrary filter |

### 9.1. When True Custom Authentication Is Needed

A custom authentication scheme should use **`AuthenticationWebFilter`**:

~~~java
// Integration snippet, not a standalone Java program.
AuthenticationWebFilter filter =
        new AuthenticationWebFilter(trustedManager);

filter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers("/partner/**"));
filter.setServerAuthenticationConverter(
        partnerCredentialConverter);
filter.setSecurityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());

http.addFilterAt(
        filter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

In this snippet, **`trustedManager`** must be a `ReactiveAuthenticationManager` that genuinely verifies credentials; **`partnerCredentialConverter`** is a `ServerAuthenticationConverter` that builds only an **unauthenticated** `Authentication` from the request without attaching `ROLE_ADMIN`. Add proper imports, registration, success/failure handling, credential lookup/key rotation, replay protection, rate limiting, and tests. `NoOpServerSecurityContextRepository` is appropriate only when you truly want stateless per-request credentials.

Never construct a `UsernamePasswordAuthenticationToken` with authorities read from unverified `X-User`/`X-Role` headers and write it to `SecurityContext`. That is an authentication bypass even when placed at `AUTHENTICATION`.

### 9.2. Multiple Authentication Mechanisms

If an app supports Basic, OAuth2 Bearer, and form login simultaneously, a single `AUTHENTICATION` milestone does not guarantee all authentication types have executed before an observer. Evaluate the position and matchers of each mechanism and test 200/401/403 for every type. For debugging or auditing, prefer authentication success/failure handlers over relying on one filter's position.

## 10. Double-Registration Pitfalls and Global WebFilters

Common mistake:

~~~java
@Component
public class AuditFilter implements WebFilter {
    // ...
}
~~~

and also:

~~~java
http.addFilterBefore(auditFilter,
        SecurityWebFiltersOrder.AUTHENTICATION);
~~~

If WebFlux auto-detects `@Component`/`@Bean` `WebFilter` as a **global WebFilter** and you also add that same filter to `SecurityWebFilterChain`, requests can pass through it **twice**: once outside and once inside the security chain. Consequences include duplicate audit logs, double-counted rate limits, duplicated response headers, missing principal context, or unexpected ordering.

The demo deliberately instantiates filters with **`new`** inside `SecurityConfig`, without annotating them as `@Component` or `@Bean WebFilter`. With DI in production, use a factory/config object instead of registering a global `WebFilter`, or clearly enforce a single registration point.

### 10.1. Two Separate Ordering Systems

- `@Order` / `Ordered` on **global WebFilters** controls ordering at the WebFlux level.
- **`SecurityWebFiltersOrder`** controls WebFilters **inside `SecurityWebFilterChain`**.

An `@Order(1)` annotation on a global `WebFilter` is not equivalent to `AUTHENTICATION` or `AUTHORIZATION`. Never mechanically equate the two systems.

### 10.2. Tests That Catch Double Execution

If the trace outputs:

~~~http
X-Lab-Filter-Trace: before-basic > before-basic > at-authentication > after-authentication
~~~

check for global registration, multiple filters sharing a label, a filter calling `chain.filter(exchange)` twice, retried requests, or duplicate middleware. Never fix it with a server-wide static `AtomicBoolean`: that mixes concurrent requests. Fix the registration config and use per-exchange attributes when needed.

## 11. Short-Circuiting, Exceptions, and Response Commit

A `WebFilter` forwards only when it calls `chain.filter(exchange)`. Returning `Mono.empty()` or writing the response and completing stops downstream execution. Intentional denials should go through security rules/handlers so status codes and `WWW-Authenticate`/403 are consistent; do not stop requests arbitrarily.

Cases:

| Request | Which Filter May Terminate Early? |
| --- | --- |
| Public GET, no credentials | Usually passes through to Controller |
| Private GET, no credentials | Authorization/entry point may return 401 |
| HTTP Basic wrong password | HTTP Basic filter returns 401; later filters may not run |
| Authenticated USER accessing admin | Authorization returns 403 |
| POST missing CSRF | CSRF may block before HTTP Basic |
| Disallowed CORS preflight | CORS may handle and skip auth |
| Request blocked by gateway | `SecurityWebFilterChain` never runs |
| URL routed to another chain | Filters registered only on the old chain do not run |

**Entering a filter** in chain order differs from **completion/response** timing. To add headers, use `beforeCommit` early or Security's `HeaderSpec`. Never set headers inside `doFinally`; the response may already be committed. With Reactor cancellation, `doFinally` can receive `CANCEL` even without a normal HTTP 200/401/403.

## 12. Multiple SecurityWebFilterChains

Spring Security Reactive allows multiple `SecurityWebFilterChain` beans using `@Order` and `securityMatcher`, e.g., a first chain for `/api/**` with bearer tokens and a second for browser form login. **A request enters only the first matching chain**, not all security chains sequentially. Therefore:

- Custom `WebFilter`s in the browser chain do not automatically apply to the API chain.
- Each chain needs its own appropriate authentication, authorization, headers, CSRF, and CORS configuration.
- Misordering a broad chain matcher can route sensitive APIs into a permissive chain.
- Choose anchors matching that chain's actual authentication mechanism.
- Test every URL/method/credential and 401/403 path rather than merely checking bean creation.
- Never expect `addFilterAt` on chain A to replace a filter in chain B.

If you need telemetry across **every** request including gateway errors, place an observation layer outside the chain or at the edge. If you need URL protection, place rules in `authorizeExchange`/service method security rather than hand-rolled routing filters.

## 13. Common Mistakes

| Mistake | Harm | Remedy |
| --- | --- | --- |
| Copying Servlet `Filter` into WebFlux | Wrong API / fails to compile | Use `WebFilter`, `ServerWebExchange` |
| Using a Filter class as anchor | Wrong parameter type in `addFilterBefore` | `SecurityWebFiltersOrder` |
| Assuming `addFilterAt` replaces Basic/CSRF | Missed or duplicated old mechanism | `addFilterAt` only shares the slot |
| Relying on same-order ties | Order is not guaranteed | Pick distinct before/after anchors |
| Reading ThreadLocal `SecurityContextHolder` | Wrong/missing principal in Reactor | `ReactiveSecurityContextHolder` |
| Trusting `X-User`/`X-Role` | Authentication bypass | `AuthManager` verifies credentials |
| Putting observer after `AUTHORIZATION` to log all 403s | Skipped on 403 short-circuit | Auth/denied handlers or earlier observer |
| Failing to call `chain.filter` | Controller never runs | Forward properly when permitted |
| Calling `chain.filter` twice | Duplicate handler side effects | Forward/subscribe exactly once |
| Calling `subscribe()` manually | Detached reactive operation | Compose `Mono` |
| Calling `block()` on Netty event loop | Starvation / high latency | Non-blocking I/O |
| Setting headers in `doFinally` | Response already committed | `beforeCommit` or `headers.writer` |
| `WebFilter` both `@Component` and `addFilter` | Executes twice | Single registration point |
| Assuming global `@Order` equals Security order | Wrong layer | Distinguish the two chain levels |
| Forgetting `securityMatcher` with multiple chains | Custom filter misses URLs | Test chain selection |
| Filter after auth while auth runs at another slot | Unexpected context state | Align order and matcher |
| Testing only 200 status | Misses bypasses/error paths | Test 200, 401, 403 |
| Disabling CSRF due to POST error | Loses browser credential protection | Use proper CSRF config |
| Logging `Authorization`/cookies | Secret leak | Redact and enforce least privilege |
| Hardcoding numeric orders | Fragile across upgrades | Use the enum and integration tests |

## 14. Review and QA Checklist

1. Code runs on WebFlux without mixing Servlet types.
2. Custom filters implement `WebFilter` and return `Mono<Void>`.
3. Before choosing Before/At/After, you identified **what you need to observe**.
4. `addFilterAt` is never treated as replacement.
5. No relative ordering dependency on same-order filters.
6. Active authentication mechanisms and their positions are known.
7. `SecurityContext` is read via `ReactiveSecurityContextHolder` in the right Reactor subscriber.
8. Raw headers never become `Authentication`.
9. New auth mechanisms use `AuthenticationWebFilter` + a real `ReactiveAuthenticationManager`.
10. No manual `subscribe()`/`block()` and no double `chain.filter` calls.
11. Response headers are set before commit.
12. No double-registration between global and internal `WebFilter`s.
13. `SecurityWebFilterChain` matchers/`@Order` are accurate when multiple chains exist.
14. CSRF, CORS, or security headers are never disabled for a custom observer.
15. Never log secrets, `sessionId`, Bearer tokens, or passwords.
16. Test public 200, private 401, denied 403, and spoofed headers.
17. Test wrong-credential short-circuiting without assuming traces are always complete.
18. Verify default `no-sniff`/`no-store` headers remain intact.
19. Observe latency/errors/cancellations and concurrency in staging.
20. Remove demo-only headers/credentials and observer responses before production.

## 15. Self-Assessment Exercises

1. Does WebFlux use `WebFilter` or `jakarta.servlet.Filter`? **WebFilter.**
2. Does `addFilterAt` replace an existing filter automatically? **No.**
3. When two filters share the same order, should you rely on their relative order? **No.**
4. Is `addFilterBefore(HTTP_BASIC)` guaranteed to run before CSRF? **No.**
5. Where should trusted `Authentication` values come from? **Verified `SecurityContext`.**
6. Why not use ThreadLocal `SecurityContextHolder` in Reactor? **Execution is not pinned to a single thread.**
7. Does header `X-Role: ADMIN` grant `ROLE_ADMIN`? **No.**
8. Why might a wrong Basic password skip a downstream observer? **401 short-circuit.**
9. Why might a filter after `AUTHORIZATION` miss a 403? **Authorization does not forward.**
10. Difference between `addFilterAfter` and `doFinally`? **Position vs reactive completion.**
11. Why is setting headers in `doFinally` dangerous? **The response may already be committed.**
12. What can `@Component WebFilter` plus `addFilterAt` on the same instance cause? **Double invocation.**
13. Does global `@Order` mean the same as `SecurityWebFiltersOrder`? **No.**
14. Chain A has a filter, and a URL matches chain B—what happens? **Filter A does not run.**
15. How should a custom API key be authenticated? **`AuthenticationWebFilter` + trusted `ReactiveAuthenticationManager`.**
16. What happens if `chain.filter(exchange)` is not called? **Downstream/controller never runs.**
17. If Alice sends `X-User=admin` with valid Basic credentials for Alice, who is the principal? **Alice.**
18. If the CSRF filter blocks before HTTP Basic, will the `before-basic` marker always appear? **No.**
19. Why do the sample tests check 401 and 403? **To ensure custom filters do not bypass security.**
20. Can a static `ArrayList` across all requests be used for tracing? **No, it mixes requests and causes races.**

## 16. References

- Spring Security 6.5 — ServerHttpSecurity Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 — SecurityWebFiltersOrder: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security 6.5 — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — AuthenticationWebFilter Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Framework — WebFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebFilter.html
- Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

**Conclusion:** In Spring Security Reactive, use `addFilterBefore`/`At`/`After` with **`WebFilter` + `SecurityWebFiltersOrder`** to place observation logic or custom authentication at the right boundary. `addFilterAt` **does not replace** built-in `WebFilter`s. To inspect identity, read Reactor `SecurityContext` after credentials are verified; for new authentication schemes, use `AuthenticationWebFilter` with `ReactiveAuthenticationManager`. Test 200/401/403, short-circuiting, and double-registration with `WebTestClient` instead of relying on config inspection alone.