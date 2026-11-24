# `ExceptionTranslationWebFilter` and Denial Responses in Spring Security WebFlux

## 1. Lesson goals

In a WebFlux API, a caller can be rejected because they are **unauthenticated** or because they are **authenticated but lack permission**. These two situations differ in meaning, HTTP status, and client handling. Spring Security uses `ExceptionTranslationWebFilter` to translate matching security exceptions inside the reactive `WebFilter` chain into HTTP responses via two components:

- `ServerAuthenticationEntryPoint`: initiates the **authentication** challenge (typically HTTP `401 Unauthorized`, or a login redirect in web apps).
- `ServerAccessDeniedHandler`: handles **authenticated-but-forbidden** requests (typically `403 Forbidden`).

This lesson belongs to the **HTTP on WebFlux** section of Spring Security Authorization. Afterward, you will be able to:

1. Understand the roles of `ExceptionTranslationWebFilter`, `AuthorizationWebFilter`, authentication filters, and `SecurityWebFilterChain`.
2. Distinguish `AuthenticationException`, `AccessDeniedException`, anonymous/unauthenticated callers, and authenticated-but-forbidden callers.
3. Configure `ServerHttpSecurity.exceptionHandling(...)` with custom entry points and access-denied handlers instead of adding extra filters or catching exceptions ad hoc in controllers.
4. Design minimal, consistent JSON error responses that never leak resource names, stack traces, or internal errors.
5. Understand how `httpBasic`, form login, bearer tokens, CSRF, and other filters produce different responses for "not allowed" scenarios.
6. Test end-to-end in WebFlux using `WebTestClient`, `mockUser`, and `csrf()`, separating permission errors from CSRF errors.
7. Recognize limits: this filter is **not a general handler for all Java exceptions**, does not implement service-layer authorization, does not treat every authentication failure identically, and cannot change status once a response is committed.

**Examples:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, and Spring WebFlux. Examples use mock authentication in tests and do not provide a login endpoint or production token system.

## 2. Where does it sit in the reactive security chain?

```text
HTTP request
     |
     v
SecurityWebFilterChain
     |
     +-- Authentication WebFilters (if configured)
     |        |
     |        +-- authentication succeeds -> Authentication/SecurityContext
     |        +-- authentication fails -> authentication failure handling
     |
     v
ExceptionTranslationWebFilter
     |
     v
AuthorizationWebFilter
     |        (authorizeExchange: authenticated/hasAuthority/access)
     |
     +-- ALLOW ------------------------> Controller/handler
     |
     +-- DENY -> AccessDeniedException
                    |
                    v
          ExceptionTranslationWebFilter
                    |
           +--------+-----------+
           |                    |
      Anonymous / missing auth   Authenticated but
      or needs authentication    lacking permission
           |                    |
           v                    v
  ServerAuthenticationEntryPoint  ServerAccessDeniedHandler
           |                    |
      Typically 401/302          Typically 403
```

The diagram shows the **logical flow for exceptions recognized by the filter**. Exact ordering and status sources also depend on configuration. For example, a POST request missing a CSRF token can be blocked by `CsrfWebFilter` **before reaching authorization rules**; a wrong HTTP Basic password can be handled by an authentication failure handler; and data errors in controllers belong to WebFlux exception handling.

### 2.1. The key trio

| Component | Primary input | Responsibility |
| --- | --- | --- |
| `AuthorizationWebFilter` | `ServerWebExchange` and reactive authorization manager | Evaluates allow/deny for HTTP requests per `authorizeExchange` |
| `ExceptionTranslationWebFilter` | `AuthenticationException` / `AccessDeniedException` caught in chain | Chooses whether to handle security exceptions with the entry point or denied handler |
| `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` | Exchange + corresponding exception | Produces the HTTP response or redirect/challenge |

`ExceptionTranslationWebFilter` **does not decide whether a user has READ or DELETE permission**: it handles the outcome when the security layer demands authentication or denies access. Authorization rules live in `authorizeExchange`, custom `ReactiveAuthorizationManager`s, or domain services.

### 2.2. WebFlux differs from Servlet

| Topic | Reactive WebFlux | Servlet MVC |
| --- | --- | --- |
| Security exception translator | `ExceptionTranslationWebFilter` | `ExceptionTranslationFilter` |
| HTTP configuration | `ServerHttpSecurity` | `HttpSecurity` |
| Unauthenticated handler | `ServerAuthenticationEntryPoint` | `AuthenticationEntryPoint` |
| Access-denied handler | `ServerAccessDeniedHandler` | `AccessDeniedHandler` |
| Request/response | `ServerWebExchange` / `ServerHttpResponse` | `HttpServletRequest` / `HttpServletResponse` |
| Result handling | `Mono<Void>` | Synchronous API |

Never mistakenly use `HttpServletResponse.sendError(...)`, Servlet `AuthenticationEntryPoint`, or Servlet `AccessDeniedHandler` inside a WebFlux `SecurityWebFilterChain`.

## 3. 401, 403, and other responses: distinguishing by root cause

### 3.1. `401 Unauthorized` — authentication required

A route requires `authenticated()` or `hasAuthority("DOC_READ")`, yet the request carries no valid authentication. Spring Security can invoke `ServerAuthenticationEntryPoint` to request credentials.

```http
GET /api/docs/read
Accept: application/json

HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED"}
```

This illustrates the **JSON response from this article's configuration**, not the default body of every Spring Security application. With HTTP Basic, 401 usually includes `WWW-Authenticate: Basic ...`; with Bearer tokens, `WWW-Authenticate: Bearer ...` may appear; form login typically redirects to a login page instead of returning JSON 401. Custom handlers must match the authentication scheme.

### 3.2. `403 Forbidden` — authenticated but lacking permission

Alice logs in successfully, yet only holds `DOC_READ` while the endpoint requires `DOC_ADMIN`. `AuthorizationWebFilter` denies access, and `ServerAccessDeniedHandler` may return 403:

```http
GET /api/docs/admin
Accept: application/json

HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED"}
```

HTTP 403 tells the client it **lacks permission for the current operation**. Do not automatically instruct the client to log in again when access was genuinely denied. Nor does 403 prove the account is allowed to know the object ID in the URL exists; an API may choose to hide resources consistently with 404 based on its threat model.

### 3.3. Decision table and important exceptions

| Situation | Typical handler layer | Possible outcome |
| --- | --- | --- |
| Unauthenticated request, protected route | Exception translation + entry point | 401 or 302 redirect depending on mechanism |
| Authenticated user, missing `DOC_READ` | Authorization + access-denied handler | 403 |
| User has `DOC_READ`, missing `DOC_ADMIN` | Authorization + access-denied handler | 403 |
| Authenticated user hit by `denyAll()` | Authorization + access-denied handler | 403 |
| POST without valid CSRF token | `CsrfWebFilter` and CSRF error handling | Usually 403; do not assume custom handler ran |
| HTTP Basic wrong password | Authentication filter / failure handler | Usually 401; body/challenge may differ from entry point by config |
| Invalid Bearer token | Resource Server authentication handling | Usually 401 with appropriate Bearer challenge |
| Controller throws `IllegalArgumentException` | WebFlux application exception handling | Depends on `@ControllerAdvice`/error config, not default auth 403 |
| Handler returns `Mono.empty()` | Controller/handler semantics | Does not mean access denied |
| Document does not exist | Business layer / policy | 404 or deny by design; never treat as auth failure |
| Invalid JSON body | WebFlux validation / codec | 400, not missing permission |
| Response headers/body already committed | System cannot arbitrarily alter status | Avoid writing responses before authorization |

**Rule:** classify by **security state and exception type** rather than catching every exception and returning 403. Doing so hides bugs and prevents clients from distinguishing system failures from missing permissions.

## 4. How does Spring Security apply entry points and access-denied handlers?

### 4.1. Official configuration API

In Spring Security 6.5, `ServerHttpSecurity.ExceptionHandlingSpec` provides:

```java
exceptionHandling(spec -> spec
    .authenticationEntryPoint(authenticationEntryPoint)
    .accessDeniedHandler(accessDeniedHandler)
)
```

This is a **fragment** inside `ServerHttpSecurity` configuration, not a standalone program. The two parameters implement respectively:

```java
ServerAuthenticationEntryPoint:
Mono<Void> commence(
    ServerWebExchange exchange,
    AuthenticationException authenticationException);

ServerAccessDeniedHandler:
Mono<Void> handle(
    ServerWebExchange exchange,
    AccessDeniedException accessDeniedException);
```

These types live in different packages:

- `ServerAuthenticationEntryPoint`: `org.springframework.security.web.server`.
- `ServerAccessDeniedHandler`: `org.springframework.security.web.server.authorization`.
- `ExceptionTranslationWebFilter`: `org.springframework.security.web.server.authorization`.

Use `exceptionHandling(Customizer)` instead of the legacy `.exceptionHandling().and()` chaining in new configurations.

### 4.2. Do not register an extra `ExceptionTranslationWebFilter` unnecessarily

When using `ServerHttpSecurity` / Spring Security WebFlux, the framework already builds the security filter chain per your config. Registering an extra `ExceptionTranslationWebFilter` as a `@Bean WebFilter` unintentionally can cause **duplicate exception handling**, handler clashes, or altered security ordering.

Prefer configuring it here:

```java
@Bean
SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
    return http
        .exceptionHandling(spec -> spec
            .authenticationEntryPoint(myEntryPoint)
            .accessDeniedHandler(myAccessDeniedHandler))
        .authorizeExchange(spec -> spec
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .build();
}
```

This is a fragment: `myEntryPoint` and `myAccessDeniedHandler` need matching beans or variables. The project in section 7 provides a complete implementation.

### 4.3. Use HTTP status-only handlers when no body is needed

Spring Security includes built-in implementations:

```java
new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);
new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);
```

These fit when only an HTTP status code is required. When a stable JSON body is needed, implement a custom handler that **never leaks exception details**, as shown below. Some authentication schemes require challenge headers; status-only handlers are not a suitable replacement for all HTTP Basic/Bearer clients.

## 5. Designing denial responses for REST APIs

### 5.1. Minimal JSON contract

An API can standardize:

| Status | Internal code | Meaning for client |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED` | Valid authentication is required |
| 403 | `ACCESS_DENIED` | Lacks permission for the operation |
| 404 | `RESOURCE_NOT_FOUND` | Missing or intentionally hidden per policy |
| 429 | `RATE_LIMITED` | Rate limited, not missing permission |
| 503 | `AUTHORIZATION_BACKEND_UNAVAILABLE` | Policy source unavailable; decision failed closed |

The first two statuses are configured directly in the example; the rest are **API contract suggestions**, not all generated automatically by `ExceptionTranslationWebFilter`.

**Never put** `exception.getMessage()`, subjects/tokens, usernames from other tenants, SQL, ACL expressions, internal roles, or stack traces into 401/403 bodies. Return stable error codes, generic messages (if needed), and a trusted request correlation ID; write diagnostic details only to restricted-access server logs with sensitive data redacted.

### 5.2. CORS, CSRF, and cache headers

- **CORS preflight OPTIONS** must be configured properly, or frontends may receive CORS errors and mistake them for authorization failures. Allow only explicit origins/headers/methods; never carelessly combine `Access-Control-Allow-Origin: *` with credentials.
- **CSRF** protects state-changing requests when browsers attach credentials like cookies automatically; POSTs missing a token can get 403 even when the user holds the authority.
- **`Cache-Control: no-store`** helps prevent intermediaries from caching error bodies tied to a user session.
- **`WWW-Authenticate`** is a key part of HTTP Basic/Bearer 401 responses; the demo disables both login mechanisms to test exception translation in isolation. When real Basic/Bearer is enabled, preserve the scheme's challenge instead of stripping headers.
- On unauthenticated requests, `401` does not mean the backend checked object permissions: it has only asked for authentication.

### 5.3. Why doesn't `@RestControllerAdvice` replace this configuration?

`@RestControllerAdvice` handles exceptions thrown while invoking a handler/controller, whereas **authorization can reject inside the `WebFilter` chain before any handler runs**. Therefore you cannot simply write:

```java
// ANTI-PATTERN: does not replace exceptionHandling for WebFilter.
@ExceptionHandler(AccessDeniedException.class)
public ResponseEntity<?> handle(AccessDeniedException ex) { ... }
```

This snippet is purely conceptual, omitting class and imports. Configure security exception handling on the WebFlux security chain, and use application exception handling for validation/business/domain errors at the right boundary.

## 6. Distinguishing unauthenticated, unauthorized, and CSRF in tests

A trustworthy HTTP test does not check `403` alone; it verifies **who blocked the request** and **whether the controller ran**.

```text
Case A:
  anonymous GET /api/docs/read
    -> 401 AUTHENTICATION_REQUIRED
    -> handler does not run

Case B:
  alice (ROLE_USER) GET /api/docs/read
    -> 403 ACCESS_DENIED
    -> handler does not run

Case C:
  alice (DOC_READ) GET /api/docs/read
    -> 200
    -> handler runs

Case D:
  alice (DOC_CREATE) POST /api/docs
  without CSRF token
    -> 403 (CSRF)
    -> handler does not run

Case E:
  alice (DOC_CREATE) POST /api/docs
  with CSRF token
    -> 200
    -> handler runs
```

**Specifically:** if you omit `csrf()` in a POST test, you cannot conclude `@PreAuthorize` or `hasAuthority("DOC_CREATE")` denied the request. CSRF can block before authorization rules are evaluated.

## 7. Java 17+ project using WebFlux Security and `WebTestClient`

The project contains **a single standalone Java test file** under `src/test/java`, boots a Spring Boot WebFlux context, and routes `WebTestClient` calls through real security filters. No production accounts are created; `mockUser` is injected onto the **test exchange** by Spring Security Test to simulate an authenticated principal.

### 7.1. File structure

```text
webflux-denial-response/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ExceptionTranslationWebFilterTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'webflux-denial-response'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

The Spring Boot BOM manages compatible dependency versions. When adapting into a production module, move the starters from `testImplementation` to `implementation` and wire real authentication; the demo does not provide a production authentication provider.

### 7.2. Complete Java test

Create `src/test/java/demo/ExceptionTranslationWebFilterTest.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    classes = ExceptionTranslationWebFilterTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
public class ExceptionTranslationWebFilterTest {

    public static class Probe {
        private final Map<String, AtomicInteger> hits =
            new ConcurrentHashMap<>();

        void hit(String route) {
            hits.computeIfAbsent(
                route, ignored -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String route) {
            AtomicInteger n = hits.get(route);
            return n == null ? 0 : n.get();
        }

        void reset() {
            hits.clear();
        }
    }

    @RestController
    public static class DemoController {
        private final Probe probe;

        public DemoController(Probe probe) {
            this.probe = probe;
        }

        @GetMapping("/public/ping")
        public Mono<Map<String, String>> publicPing() {
            probe.hit("public");
            return Mono.just(Map.of("ok", "true"));
        }

        @GetMapping("/api/docs/read")
        public Mono<Map<String, String>> read() {
            probe.hit("read");
            return Mono.just(Map.of("document", "D42"));
        }

        @GetMapping("/api/docs/admin")
        public Mono<Map<String, String>> admin() {
            probe.hit("admin");
            return Mono.just(Map.of("admin", "true"));
        }

        @GetMapping("/api/docs/account")
        public Mono<Map<String, String>> account() {
            probe.hit("account");
            return Mono.just(Map.of("authenticated", "true"));
        }

        @GetMapping("/api/docs/blocked")
        public Mono<Map<String, String>> blocked() {
            probe.hit("blocked");
            return Mono.just(Map.of("blocked", "false"));
        }

        @PostMapping("/api/docs")
        public Mono<Map<String, String>> create() {
            probe.hit("create");
            return Mono.just(Map.of("created", "true"));
        }
    }

    private static Mono<Void> jsonError(
            ServerWebExchange exchange,
            HttpStatus status,
            String fixedCode) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_JSON);
        response.getHeaders().setCacheControl("no-store");

        // fixedCode ONLY accepts server-defined constants.
        // Never reflect exception messages/client input into JSON.
        byte[] payload = (
            "{\"code\":\"" + fixedCode + "\"}"
        ).getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(payload)));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableWebFluxSecurity
    public static class Config {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DemoController demoController(Probe probe) {
            return new DemoController(probe);
        }

        @Bean
        SecurityWebFilterChain securityWebFilterChain(
                ServerHttpSecurity http) {
            return http
                .exceptionHandling(errors -> errors
                    .authenticationEntryPoint(
                        (exchange, authenticationException) ->
                            jsonError(
                                exchange,
                                HttpStatus.UNAUTHORIZED,
                                "AUTHENTICATION_REQUIRED"))
                    .accessDeniedHandler(
                        (exchange, deniedException) ->
                            jsonError(
                                exchange,
                                HttpStatus.FORBIDDEN,
                                "ACCESS_DENIED"))
                )
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/ping").permitAll()
                    .pathMatchers("/api/docs/read")
                        .hasAuthority("DOC_READ")
                    .pathMatchers("/api/docs/admin")
                        .hasAuthority("DOC_ADMIN")
                    .pathMatchers("/api/docs/account")
                        .authenticated()
                    .pathMatchers("/api/docs/blocked")
                        .denyAll()
                    .pathMatchers(
                        org.springframework.http.HttpMethod.POST,
                        "/api/docs")
                        .hasAuthority("DOC_CREATE")
                    .anyExchange().denyAll()
                )
                // This test checks exception translation only with
                // mockUser; it does not simulate HTTP Basic/login mechanisms.
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .csrf(Customizer.withDefaults())
                .build();
        }
    }

    @Autowired ApplicationContext applicationContext;
    @Autowired Probe probe;

    private WebTestClient web;

    @BeforeEach
    void setUp() {
        probe.reset();

        web = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient as(String name, String authority) {
        return web.mutateWith(
            mockUser(name).authorities(
                new SimpleGrantedAuthority(authority)));
    }

    @Test
    void publicEndpointPermitsAnonymous() {
        web.get().uri("/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ok").isEqualTo("true");
        assertThat(probe.count("public")).isEqualTo(1);
    }

    @Test
    void anonymousReadTriggersAuthenticationEntryPoint() {
        web.get().uri("/api/docs/read").exchange()
            .expectStatus().isUnauthorized()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
        assertThat(probe.count("read")).isZero();
    }

    @Test
    void authenticatedWithoutReadGets403Json() {
        as("alice", "ROLE_USER")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
        assertThat(probe.count("read")).isZero();
    }

    @Test
    void authenticatedWithReadRunsHandler() {
        as("alice", "DOC_READ")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.document").isEqualTo("D42");
        assertThat(probe.count("read")).isEqualTo(1);
    }

    @Test
    void roleAdminDoesNotImplicitlyGrantDocRead() {
        as("admin", "ROLE_ADMIN")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isForbidden();
        assertThat(probe.count("read")).isZero();
    }

    @Test
    void accountRequiresOnlyAuthentication() {
        as("bob", "ROLE_USER")
            .get().uri("/api/docs/account").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.authenticated").isEqualTo("true");
        assertThat(probe.count("account")).isEqualTo(1);
    }

    @Test
    void anonymousAccountRequiresAuthentication() {
        web.get().uri("/api/docs/account").exchange()
            .expectStatus().isUnauthorized();
        assertThat(probe.count("account")).isZero();
    }

    @Test
    void docReadDoesNotGrantDocAdmin() {
        as("alice", "DOC_READ")
            .get().uri("/api/docs/admin").exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
        assertThat(probe.count("admin")).isZero();
    }

    @Test
    void docAdminAuthorityAllowsAdminRoute() {
        as("alice", "DOC_ADMIN")
            .get().uri("/api/docs/admin").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.admin").isEqualTo("true");
        assertThat(probe.count("admin")).isEqualTo(1);
    }

    @Test
    void denyAllRouteRejectsAuthenticatedCaller() {
        as("alice", "DOC_ADMIN")
            .get().uri("/api/docs/blocked").exchange()
            .expectStatus().isForbidden();
        assertThat(probe.count("blocked")).isZero();
    }

    @Test
    void unknownPathUsesDenyAllInsteadOfOpenAccess() {
        as("alice", "DOC_READ")
            .get().uri("/internal/debug").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenWithAuthority() {
        as("alice", "DOC_CREATE")
            .post().uri("/api/docs").exchange()
            .expectStatus().isForbidden();
        assertThat(probe.count("create")).isZero();
    }

    @Test
    void postWithCsrfAndAuthorityRunsHandler() {
        as("alice", "DOC_CREATE")
            .mutateWith(csrf())
            .post().uri("/api/docs").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.created").isEqualTo("true");
        assertThat(probe.count("create")).isEqualTo(1);
    }

    @Test
    void postWithCsrfButWrongAuthorityGets403() {
        as("alice", "DOC_READ")
            .mutateWith(csrf())
            .post().uri("/api/docs").exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
        assertThat(probe.count("create")).isZero();
    }

    @Test
    void anAllowedCallDoesNotAuthorizeLaterWrongPrincipal() {
        as("alice", "DOC_READ")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isOk();

        as("bob", "ROLE_USER")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isForbidden();

        assertThat(probe.count("read")).isEqualTo(1);
    }
}
```

**Why is this test valuable?** `bindToApplicationContext(...).apply(springSecurity())` sends requests through reactive Spring Security filters; `mockUser` attaches a trusted `Authentication` **only inside tests**. When a handler is blocked, `Probe` stays unchanged, proving zero controller side effects ran. Do not conclude from this alone that the controller protects itself if called via a non-HTTP path.

**Import note:** this project intentionally **does not use `MapReactiveUserDetailsService`** since authentication is mocked via Spring Security Test. When adding a reactive user store to a real application, use the package matching your Spring Security version rather than copying class names from old/Servlet docs.

### 7.3. Running the tests

```bash
gradle test --tests demo.ExceptionTranslationWebFilterTest
```

If using the Gradle Wrapper: `./gradlew test --tests demo.ExceptionTranslationWebFilterTest` on Linux/macOS, or `gradlew.bat test --tests demo.ExceptionTranslationWebFilterTest` on Windows.

**Expected result:** **15 JUnit tests** pass once JDK, Gradle, and dependencies are properly configured, ending with `BUILD SUCCESSFUL`. This is an **expected design outcome, not observed stdout from a Java execution**. HTML JUnit report: `build/reports/tests/test/index.html`.

### 7.4. What was tested, and what was not tested

| Test group | Evidence |
| --- | --- |
| Public route | `permitAll()` requires no authentication |
| Anonymous + protected | `ServerAuthenticationEntryPoint` returns 401 JSON |
| Authenticated, missing authority | `ServerAccessDeniedHandler` returns 403 JSON |
| Has authority | Handler actually executes |
| `ROLE_ADMIN` ≠ `DOC_READ` | Authority is not inferred from a broad role |
| `authenticated()` | Not synonymous with `hasAuthority(...)` |
| Admin route | `DOC_READ` does not grant `DOC_ADMIN` |
| `denyAll` and `anyExchange` | Does not accidentally expose unknown routes |
| POST without CSRF | 403, yet **does not conclude** custom access-denied handler ran |
| POST with CSRF, valid authority | Handler executes successfully |
| POST with CSRF, wrong authority | 403 from authorization, policy JSON body |
| Switching principal between requests | Alice's permissions do not carry over to Bob |
| `Probe` | Denied requests never execute controller bodies |

This test suite **does not run a real network server**, and does not include JWT Bearer filters, OIDC login, HTTP Basic credentials, browser cookies, a multi-tenant database, R2DBC, or distributed authz. Those layers must be added when used in production. `WebTestClient` bound to `ApplicationContext` still exercises WebFlux's `WebFilter`/handler path rather than calling Java methods directly.

## 8. Production configuration with Basic, Bearer, or form login

### 8.1. With HTTP Basic

When using HTTP Basic alongside a custom `ServerAuthenticationEntryPoint`, return **401** with a `WWW-Authenticate: Basic realm="..."` header so clients know how to supply credentials, or reuse `HttpBasicServerAuthenticationEntryPoint`. Never copy this lesson's JSON handler verbatim and omit the challenge header on systems requiring HTTP Basic.

If a client sends a wrong Basic password, the authentication failure handler may return 401 **before the request is ever considered authenticated**; do not force every 401 case to share the exact same JSON body unless you configure authentication failure handlers too.

### 8.2. With OAuth2 Resource Server / Bearer

Bearer-token APIs should use Spring Security Resource Server and server handlers supporting the **Bearer challenge**, following RFC 6750. Configuration skeleton:

```java
// Fragment: requires configuring a JWT decoder, issuer/audience, and
// actual OAuth2 Resource Server dependencies.
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()));
```

Never catch all JWT errors and return `403`: missing/invalid tokens are typically **401** scenarios, whereas valid tokens lacking scopes/permissions lead to **403**. `WWW-Authenticate` headers carry protocol semantics and can be emitted by resource server handlers.

### 8.3. With form login and browsers

An HTML application using `formLogin` may redirect `302` to `/login` when unauthenticated. If the same app serves both JSON APIs and HTML pages, you may need **multiple `SecurityWebFilterChain`s** with clear `securityMatcher`s or a `ServerWebExchangeMatcher`-based entry-point strategy, avoiding JSON 401s for web logins or HTML redirects for API clients.

### 8.4. Never let custom handlers break the rest of security

- Preserve security headers and authentication scheme challenges.
- Never drop CSRF on cookie-credential endpoints just because a POST test returned 403.
- Never turn every `AccessDeniedException` into 200 with `{"allowed":false}`, because 2xx statuses can be treated as success by clients/intermediaries.
- Never put exception messages or stack traces into user responses.
- Never call `block()` or synchronous I/O inside custom handlers; write results via `Mono<Void>`.
- Never write a response body after the response is committed; log server-side and follow WebFlux error policies.
- Never turn `Mono.empty()` in reactive authorization into ALLOW when policy data is missing.

## 9. Real data access and object-level authorization bugs

`ExceptionTranslationWebFilter` only **translates denials to HTTP**. A `.hasAuthority("DOC_READ")` route **does not prove** a user may read every `Document`. In multi-tenant systems, enforce object checks:

```java
// Policy fragment inside a ReactiveAuthorizationManager:
// authentication is Mono<Authentication>, exchange/context
// supplies tenant and docId from path variables (do not trust blindly).
return authentication.flatMap(auth ->
    repository.findByTenantAndId(
        trustedTenant(auth), requestedId)
      .map(doc -> allowedByOwnerAndState(auth, doc))
      .defaultIfEmpty(false));
```

This is conceptual code requiring application-specific methods. `requestedId` must never query another tenant on its own; `trustedTenant(auth)` must be verified from identity/membership. Returning `403` or `404` on denial is a response policy choice, not a substitute for tenant-scoped SQL/RLS and data checks at point of use.

If an HTTP manager checks permissions before a DELETE handler runs, the object's state can change from DRAFT to APPROVED in between. Perform **conditional DELETE/UPDATE** by tenant/owner/status inside a transaction; the exception translator does not prevent TOCTOU.

## 10. Troubleshooting

| Symptom | What to check | Fix |
| --- | --- | --- |
| Unauthenticated caller gets 403 instead of 401 | CSRF, custom anonymous config, selected entry point/chain | Identify which filter rejected rather than guessing from status |
| Credentials sent yet still gets 401 | Invalid token/password, authentication filter/failure handler | Test authentication separately before authz |
| Logged in successfully yet gets 403 | Missing authority, role prefix, tenant, policy, or CSRF | Inspect `Authentication.getAuthorities()` and filter path |
| Authorized POST still gets 403 | Missing CSRF token | Test with `csrf()`, then verify authz |
| Custom body does not appear | Exception bypassed this handler or blocked by another filter | Separate permission denial tests from CSRF/auth failure tests |
| 302 instead of JSON 401 | Form login entry point triggered | Separate security chains or pick entry point per API |
| 401 missing `WWW-Authenticate` | Custom JSON entry point replaced Basic/Bearer challenge | Use scheme-aware entry point/headers |
| 500 instead of 403 | Business exception (not `AccessDeniedException`), committed response, JSON bug | Use WebFlux error handling without swallowing all exceptions |
| 404 on undeclared route when 403 expected | Another matcher/chain handled it; `anyExchange` didn't apply | Test exact request mapping and `securityMatcher` |
| Permission handler runs yet controller still has side effects | Authz ran after side effects, controller self-called, missing precheck | Guard in service, verify ordering and `Probe` |
| Client sees resource name despite lacking permission | Data leaked via exception body/logs | Return generic codes; never reflect `exception.message` |
| CORS preflight blocked | Wrong CORS config or chain match | Configure controlled CORS and test OPTIONS |
| Other routes stay open after adding endpoint | `anyExchange().permitAll()` or chain ordering | Use least privilege / default `denyAll` |
| HTTP tests pass yet job accesses unauthorized data | Jobs skip `WebFilter` | Guard domain services and SQL separately |

## 11. Pre-production testing recommendations

1. **Anonymous:** call each sensitive route unauthenticated; verify 401/challenge or redirect matching the auth scheme.
2. **Authenticated, missing authority:** verify 403 and that the handler does not execute.
3. **Authenticated, valid authority:** verify 200/201/204 and expected side effects.
4. **CSRF:** with browser credentials, test POST/PUT/PATCH/DELETE with and without tokens; separate 403 sources.
5. **Error contract:** verify content type, JSON schema, `Cache-Control: no-store` where applicable, and zero leaked exception messages, tokens, or SQL.
6. **Wrong tenant/object:** users with functional authority but no object permission are still blocked.
7. **Method/route mismatch:** an endpoint supporting both `GET` and `DELETE` enforces distinct permissions; `anyExchange` never opens unintended routes.
8. **Authentication failure:** wrong Basic password, invalid/expired Bearer token, wrong issuer/audience; verify 401 differs from authorization denial.
9. **Multiple filter chains:** API vs browser, verifying entry points and request matchers per chain.
10. **Error source:** policy backend down never becomes ALLOW; choose 403/503 per contract and log/alert.
11. **Cross-cutting:** CORS preflight, cache-control, security headers, rate limits, request sizes, and proxy headers.
12. **Reactive correctness:** no `block()`, no manual `subscribe()`, and no writing errors after response commit.
13. **Method/repository-level security:** background jobs and message consumers must not rely solely on HTTP filters.
14. **Audit:** safely log correlation IDs and denial types; avoid logging PII, tokens, or sensitive internal policies.

## 12. Exercises

**Exercise A — Basic challenge:** Switch the demo to real HTTP Basic with `MapReactiveUserDetailsService` and a version-appropriate `PasswordEncoder`. Write tests for missing credentials and bad passwords, verifying `WWW-Authenticate`.

**Exercise B — Bearer:** Configure Resource Server JWT, generating a valid test token lacking `documents:read` and an invalid token. Distinguish 403 from 401/Bearer challenges.

**Exercise C — JSON Problem Details:** Use RFC 9457 `application/problem+json`, returning valid `type`, `title`, and `status` without reflecting internal messages. Test content type and schema.

**Exercise D — Tenant:** Add `/api/tenants/{tenantId}/docs/{id}` and a reactive policy. Anonymous gets 401, valid tenant/authority gets 200, and same authority in wrong tenant gets 403 or 404 per spec.

**Exercise E — CSRF:** Keep cookie sessions, POST with and without `csrf()`, and verify the controller does not run on the tokenless path.

**Exercise F — Two security chains:** Distinguish `/api/**` returning JSON 401 from `/web/**` redirecting to login; test `securityMatcher` order and entry points.

**Exercise G — Controller error:** Create an allowed route that throws `IllegalArgumentException`. Prove the error response goes through application exception handling rather than being randomly mapped to 403.

**Exercise H — Race condition:** A DELETE is allowed by HTTP authorization, yet the record transitions to APPROVED before write. Use conditional SQL DELETE and confirm zero side effects.

## 13. Summary

`ExceptionTranslationWebFilter` is the component that **translates security exceptions into appropriate HTTP responses** in Spring Security WebFlux:

- Missing authentication: handled by **`ServerAuthenticationEntryPoint`**, typically 401/challenge or redirect.
- Authenticated yet unauthorized: handled by **`ServerAccessDeniedHandler`**, typically 403.
- CSRF or authentication failures in other filters can also yield 401/403 without **necessarily passing through these custom handlers**.
- Business exceptions, validation, resource-not-found, and server failures need proper error handling rather than **collapsing everything into 403**.

Configure via `ServerHttpSecurity.exceptionHandling(...)` without registering duplicate `WebFilter` beans. Test with `WebTestClient` to prove **exact status codes, safe JSON bodies, and that denied controllers never execute**, while keeping real authorization in services and repositories.

## References

- Spring Security 6.5 API — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Security 6.5 API — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.5 API — `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security 6.5 API — `HttpStatusServerEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/HttpStatusServerEntryPoint.html
- Spring Security 6.5 — WebFlux HTTP Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — WebFlux CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — WebFlux Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/index.html
- HTTP Semantics — 401, 403 (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110
- HTTP Authentication — Basic (RFC 7617) and Bearer (RFC 6750): https://www.rfc-editor.org/rfc/rfc7617 ; https://www.rfc-editor.org/rfc/rfc6750
