# Auditing Servlet Filters, HttpSession, and Blocking Libraries When Migrating to WebFlux

> **Scope:** Migrating and debugging Spring Security applications moving from Spring MVC/Servlet to Spring WebFlux (reactive). The goal is to identify code still depending on `Filter`, `HttpServletRequest`, `HttpSession`, or blocking I/O APIs, and transition to an execution, security, and state-storage model suitable for WebFlux. Examples use Java 17+ and Spring Boot 3.x/Spring Security 6.x aligned via BOM; when using Boot 4+/Security 7+, verify exact packages and auto-configuration for your specific version.

## 1. Expected Outcomes

After this lesson, you will be able to:

1. Distinguish the **Servlet Filter Chain** from **WebFlux `WebFilter`/`SecurityWebFilterChain`**, avoiding porting Servlet filters verbatim into a reactive application.
2. Inventory dependencies on `HttpSession`, `HttpServletRequest`, `SecurityContextHolder`, and `ThreadLocal`, and decide whether sessions are truly required.
3. Distinguish `WebSession`, `ServerSecurityContextRepository`, and `ReactiveSecurityContextHolder`, without inferring authentication from the current thread.
4. Locate blocking operations such as JDBC/JPA, `RestTemplate`, `Thread.sleep`, `Future.get`, and `Mono.block()`; choose non-blocking APIs or isolate legacy libraries onto `Schedulers.boundedElastic()`.
5. Build a reactive security configuration using `ServerHttpSecurity` and a simple `WebFilter`, and test public routes, protected routes, and session behavior.
6. Isolate post-migration bugs: filters not executing, unexpected `401/403` statuses, leaked principal data, broken CSRF/CORS, event-loop slowdowns, or lost sessions when scaling across multiple instances.

## 2. Where Do the Two Execution Models Differ?

In a traditional Servlet application:

```text
HTTP request
   → Servlet container (Tomcat/Jetty/Undertow)
   → javax.servlet.Filter / jakarta.servlet.Filter
   → Spring Security servlet FilterChainProxy
   → DispatcherServlet → MVC Controller
   → blocking service / JDBC / RestTemplate
   → HTTP response
```

A request is typically bound to a single Servlet thread while the handler executes. Legacy code commonly accesses `HttpServletRequest`, `HttpSession`, or stores context in `ThreadLocal` under that assumption.

In WebFlux:

```text
HTTP request
   → reactive HTTP server (typically Reactor Netty)
   → WebFilter chain
   → Spring Security reactive securityWebFilterChain
   → DispatcherHandler / HandlerFunction
   → Mono/Flux + reactive service / WebClient / R2DBC
   → HTTP response (reactive signals)
```

WebFlux can run on certain Servlet containers via an adapter, yet **still uses WebFlux APIs**. Swapping the server does not turn `Filter`/`HttpSession` code into `WebFilter`/`WebSession`.

Differences that directly affect safety and performance:

- WebFlux uses **a small number of event-loop worker threads**; they must serve many connections, so no request may block a thread for long.
- Reactor pipelines can switch threads via `publishOn`/`subscribeOn` or on asynchronous completion. **The current thread is not a stable identity for a request**.
- `Mono`/`Flux` describes work to be subscribed to; many operations only begin upon subscription. Pay close attention to permission checks and error handling at subscription time.
- Spring Security for WebFlux uses `WebFilter` and **Reactor Context** to propagate security context rather than Servlet `FilterChainProxy` or assuming `SecurityContextHolder` holds the identity on every thread.

**Common mistake:** Changing a return type from `User` to `Mono<User>` while still calling JPA, `Thread.sleep`, or `.block()` on the event loop. Such code remains blocking despite its reactive outer signature.

## 3. API Migration Map and Architectural Decisions

| Servlet/Spring MVC Component | WebFlux/Reactive Equivalent | Migration Notes |
| --- | --- | --- |
| `jakarta.servlet.Filter`, `OncePerRequestFilter` | `org.springframework.web.server.WebFilter` | Return `Mono<Void>` via `WebFilterChain.filter(exchange)`; do not write Servlet filters into a WebFlux chain |
| `FilterRegistrationBean` | Spring-managed `WebFilter`; `@Order` when appropriate | Check ordering relative to Spring Security; security logic belongs in the security chain |
| `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse` | Reactive request/response; do not use Servlet input streams |
| `HttpSession` | `WebSession` via `ServerWebExchange.getSession()` | Different session API and persistence timing; do not treat as automatically stateless |
| `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` or `NoOpServerSecurityContextRepository` | Choose according to stateful login vs. stateless bearer token architecture |
| `SecurityContextHolder` (ThreadLocal) | `ReactiveSecurityContextHolder` (Reactor Context), `Mono<Principal>` | Do not assume context follows a thread pool |
| `HttpSecurity` | `ServerHttpSecurity` | Configure `SecurityWebFilterChain` instead of Servlet `SecurityFilterChain` |
| `UsernamePasswordAuthenticationFilter`, Servlet authentication filters | `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, `ServerAuthenticationConverter` | Do not copy a Servlet filter and force it to run in WebFlux |
| `HandlerInterceptor` | `WebFilter` or appropriate reactive handler/route mechanism | Migrate only needed responsibilities; avoid overlapping filters |
| `RestTemplate` / synchronous HTTP clients | `WebClient` | `WebClient` is non-blocking when used purely reactively; calling `block()` still blocks threads |
| `JdbcTemplate` / Hibernate/JPA | R2DBC/suitable async driver or `boundedElastic` adapter | R2DBC does not replace every JPA feature; choose based on business needs |
| `JpaTransactionManager` / imperative `@Transactional` | `ReactiveTransactionManager` for reactive data access | Do not mix thread-bound transaction context with reactive transactions |
| Servlet `HttpServletRequest.getInputStream()` | `Flux<DataBuffer>` / WebFlux codecs | Never perform long `InputStream.read()` calls on the event loop |
| Scattered Servlet `@Async` / `ExecutorService` | Reactor composition, explicit schedulers | Never call `subscribe()` inside a service just to "run in the background" |

Distinguish three categories of requirements:

1. **Security:** authentication, authorization, `401/403` handling, login, CSRF, saving `SecurityContext`. Prefer reactive Spring Security mechanisms.
2. **Cross-cutting HTTP concerns:** request IDs, metric tags, safe header adjustments, size/time limits, and redacted logging. `WebFilter` is suitable here.
3. **Business logic/I/O:** DB, HTTP, SDK, file, and message-broker calls. These belong in services using non-blocking APIs or explicit offload boundaries, not inside security filters.

## 4. Inventory Step Before Editing Code

Inside the application repository **assigned for migration** (not across unrelated modules), search for lingering Servlet dependencies. Example `rg` commands—these are **suggested commands for learners to run on their own project**, not inventory results from a specific repository:

```bash
rg -n "javax\.servlet|jakarta\.servlet|OncePerRequestFilter|FilterRegistrationBean|HttpServletRequest|HttpServletResponse|HttpSession" src
rg -n "SecurityFilterChain|HttpSecurity|SecurityContextHolder|RequestContextHolder|HandlerInterceptor" src
rg -n "RestTemplate|RestClient|JdbcTemplate|EntityManager|JpaRepository|Future\.get|Thread\.sleep|\.block\(|\.toFuture\(" src
rg -n "synchronized|ThreadLocal|MDC\.|\.join\(|InputStream|OutputStream" src
```

A search match **is not automatically a bug**: `.block()` in synchronous tests or controlled bootstrap code may be acceptable, and Java I/O during startup differs from I/O on the Netty event loop. Always trace the call graph to the actual execution site.

Check dependency configuration:

- Pure WebFlux projects typically include `spring-boot-starter-webflux` and `spring-boot-starter-security`.
- If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot usually favors Servlet/MVC. Check the **actual `WebApplicationType`**, handler mappings, and which server started; do not conclude "we are reactive" merely because `WebClient` is used.
- A library transitively pulling in the Servlet API does not necessarily make the application blocking; what matters is which code path executes and which server/stack is selected.
- Remove servlet-specific dependencies only after replacing needed features; adapters intentionally supporting Servlet are a separate case and do not always have to be deleted at all costs.

**Inventory record template per item:**

| Field to record | Question |
| --- | --- |
| Component/call site | Class, bean, annotation, actual call location |
| Role | Authentication, authorization, session, audit, logging, network, or DB? |
| Execution | On the event loop, `boundedElastic`, a dedicated thread pool, or startup? |
| State | Which `HttpSession`, `SecurityContextHolder`, `ThreadLocal`, or request attributes are read? |
| Dependency | Servlet-only, blocking I/O, supports reactive API, or has an adapter? |
| Replacement | Remove completely, `WebFilter`, reactive Spring Security, `WebSession`, `WebClient`/R2DBC, or offload |
| Testing | Endpoints, status codes, sessions/cookies, identity, headers, latency/load tests |
| Risk | Auth bypass, token mishandling, cross-request state leakage, event-loop starvation |

Prioritize **login/authorization and request-state leakage** items first; optimize throughput afterwards.

## 5. Migrating `OncePerRequestFilter` to `WebFilter` with Clear Responsibilities

### 5.1. Legacy Logic Example for Reference Only

```java
// Servlet MVC: reference snippet; DO NOT place in a WebFlux application.
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {
    String correlationId = UUID.randomUUID().toString();
    request.setAttribute("correlationId", correlationId);
    response.setHeader("X-Correlation-Id", correlationId);
    chain.doFilter(request, response);
}
```

Legacy code relies on Servlet request/response and a synchronous `FilterChain.doFilter` call. You cannot simply change the return type to `Mono<Void>` while keeping `HttpServletRequest` or `FilterChain`.

### 5.2. An Equivalent `WebFilter` for Request IDs

Create `src/main/java/demo/migration/CorrelationIdWebFilter.java`:

```java
package demo.migration;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class CorrelationIdWebFilter implements WebFilter {
    private static final String HEADER = "X-Correlation-Id";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String supplied = exchange.getRequest().getHeaders().getFirst(HEADER);

        // Echo caller-supplied ID only if it passes validation.
        String correlationId =
                supplied != null && supplied.matches("[A-Za-z0-9_-]{1,64}")
                        ? supplied
                        : UUID.randomUUID().toString();

        exchange.getAttributes().put("correlationId", correlationId);
        exchange.getResponse().getHeaders().set(HEADER, correlationId);

        return chain.filter(exchange);
    }
}
```

Explanation:

- `ServerWebExchange` replaces Servlet request/response. `exchange.getAttributes()` is suitable for sharing metadata **within a single request**, without needing `ThreadLocal`.
- `WebFilterChain.filter(exchange)` returns a `Mono<Void>` publisher for the downstream pipeline. Call `chain` **once** on normal paths; never call `subscribe()` yourself.
- The filter validates characters and length of the incoming header to prevent reflecting CRLF sequences or oversized payloads into responses.
- `@Order(-100)` illustrates **application `WebFilter`** ordering; do not treat this magic number as a guarantee that the filter runs before/after a specific Spring Security phase. For authentication logic, choose placement using `SecurityWebFiltersOrder` or security DSL configuration and test actual behavior.
- Headers can be added before the response is committed; to modify headers later in the pipeline, use `response.beforeCommit(...)`, respecting publisher semantics and never blocking.

**Do not adapt this pattern to parse Authorization headers manually and set `SecurityContextHolder`.** A correlation-ID filter and an authentication filter have distinct responsibilities; hand-rolling authentication outside Spring Security easily bypasses exception handling, authorization, and context management.

### 5.3. Migrating Authentication and Authorization Filters

Servlet configurations often look like this:

```java
// Servlet/MVC: pre-migration illustration
@Bean
SecurityFilterChain servletChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().authenticated())
            .build();
}
```

In WebFlux, use `SecurityWebFilterChain`, `ServerHttpSecurity`, and `authorizeExchange`. Migrate every important semantic: route matchers, HTTP methods, authentication type, filter order, access-denied handling, CSRF, CORS, sessions, HTTPS, and logout. **There is no 1:1 class rename** for every Servlet security filter.

Examples:

- Servlet JWT bearer authentication → `oauth2ResourceServer(o -> o.jwt(...))` on `ServerHttpSecurity` (requires a reactive JWT decoder and valid issuer/JWKS).
- Custom login authentication → `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, and `ServerAuthenticationConverter`, along with tests for invalid/missing credentials.
- Custom principal in `ThreadLocal` → keep `Authentication` in Reactor Context via Spring Security and read it with `ReactiveSecurityContextHolder` or a `Principal` controller argument.
- Servlet `AccessDeniedHandler` / `AuthenticationEntryPoint` → reactive equivalents `ServerAccessDeniedHandler` / `ServerAuthenticationEntryPoint`.
- Header policies, CORS, CSRF, and HTTPS redirects → use the WebFlux security DSL and WebFlux-native configuration, not copied Servlet filters.

When multiple `SecurityWebFilterChain` beans exist, security matchers and `@Order` decide which chain handles a request; **the first matching chain is selected**. Never put a catch-all chain ahead of a chain protecting `/api/admin/**` or leave paths uncovered. Test every endpoint after changing matchers.

## 6. Minimal Example: Runnable and Testable WebFlux Security

The example uses Spring Boot 3.x, Java 17+, and Gradle Kotlin DSL; dependency versions are managed by the project's Spring Boot BOM/Gradle plugin. This section forms a **complete demo application given an existing Spring Boot build**, with files under package `demo.migration`.

Add the starters in `build.gradle.kts` (`dependencies` snippet, not the full build script):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Do not add `spring-boot-starter-web` to this demo. Create `src/main/java/demo/migration/MigrationApplication.java`:

```java
package demo.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MigrationApplication.class, args);
    }
}
```

Create `src/main/java/demo/migration/ReactiveSecurityConfig.java`:

```java
package demo.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}test-only-password")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
```

**Only use `{noop}` and fixed passwords in demo/test applications.** Production must use adaptive password hashing (such as `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, bcrypt/Argon2 per policy) or OAuth2/OIDC with an identity provider; never commit real usernames or passwords.

Create `src/main/java/demo/migration/DemoController.java`:

```java
package demo.migration;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/private/hello")
    public Mono<String> hello(Mono<Principal> principal) {
        return principal.map(user -> "hello " + user.getName());
    }
}
```

Here the username comes from the **reactive request** principal, without touching `HttpSession` or `SecurityContextHolder.getContext()`.

Create `src/test/java/demo/migration/ReactiveSecurityMigrationTest.java`:

```java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveSecurityMigrationTest {
    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointNeedsNoLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void privateEndpointRejectsAnonymousRequest() {
        client.get().uri("/private/hello")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAcceptsValidTestCredentials() {
        client.get().uri("/private/hello")
                .headers(headers -> headers.setBasicAuth(
                        "learner", "test-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("hello learner");
    }
}
```

Run: `./gradlew test --tests demo.migration.ReactiveSecurityMigrationTest`; on Windows use `gradlew.bat test --tests demo.migration.ReactiveSecurityMigrationTest`. **Expected outcome:** three tests pass, with no mandatory application stdout; an anonymous request to `/private/hello` returns `401` because HTTP Basic is enabled. This result assumes only the demo configuration is active with no external routes, filters, or security chains interfering. If your project uses Boot 4+, test auto-configuration packages may differ: update them per your version's documentation rather than rewriting security logic just to fix import errors.

This is a simple example testing migration of the **security boundary**. To verify `CorrelationIdWebFilter` ordering, add tests with valid/invalid `X-Correlation-Id` headers across both successful and failing requests; do not rely on `@Order` alone as proof of actual runtime order.

## 7. `HttpSession` Is No Longer a WebFlux API

### 7.1. `WebSession` Handles State Reactively

In Servlet, code can do:

```java
// Servlet MVC, illustrative snippet
HttpSession session = request.getSession();
session.setAttribute("locale", "vi");
String locale = (String) session.getAttribute("locale");
```

WebFlux uses `ServerWebExchange.getSession()`, returning `Mono<WebSession>`. The controller example below is a **separate Java class** in the demo package:

```java
package demo.migration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class SessionCounterController {
    @GetMapping("/session/visits")
    public Mono<String> visits(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer previous = session.getAttribute("visits");
            int current = (previous == null ? 0 : previous) + 1;
            session.getAttributes().put("visits", current);
            return "visits=" + current;
        });
    }
}
```

Meaning: the app reads/writes attributes in `WebSession` and responds via a publisher. Depending on configuration, the client must retain and resend the session cookie for the visit counter to increment across requests. In manual tests, the first request returns `visits=1`; a subsequent request **only** returns `visits=2` if the same session is restored. This is a small illustration and **does not guarantee safe concurrent updates**: multiple concurrent requests performing read-modify-write on a session counter can lose updates. In production, use appropriate storage or atomic operations when accurate counting matters.

`WebSession` is also not `HttpSession` under a different name: APIs and persistence lifecycles are not strictly identical. Do not assume a session has been persisted or lives long just because `getSession()` was called; verify start, mutation, expiration, session cookies, and the session store.

### 7.2. Stateful Login or Stateless API?

- **Cookie-based browser login:** May require `WebSession`, session fixation protection, `Secure`/`HttpOnly`/`SameSite` session cookies, CSRF protection, proper logout, and session invalidation. Spring Security defaults do not replace deliberate cookie/session design.
- **APIs using Bearer/JWT in `Authorization`:** Usually best kept **stateless**, without persisting `SecurityContext` across requests. `NoOpServerSecurityContextRepository` can be used for this policy; tokens are re-verified on every request.
- **Multi-pod deployments:** in-memory sessions do not synchronize across instances. Consider Spring Session with a `ReactiveSessionRepository` (e.g., reactive Redis integration), cookies, key TTLs, and network resilience—or eliminate sessions if business rules permit.
- **OAuth2 client credentials/tokens:** Outbound `WebClient` may use `OAuth2AuthorizedClient`; storing authorized clients differs from a session holding a login principal. Do not dump every token into `WebSession` for convenience.

Configuration snippet **specifically for a bearer-only resource server**—do not merge it into the HTTP Basic demo above:

```java
@Bean
SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
    return http
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .oauth2ResourceServer(spec -> spec.jwt(withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
}
```

This is a **method snippet**, requiring imports for `NoOpServerSecurityContextRepository`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `withDefaults`, plus `spring-boot-starter-oauth2-resource-server` and valid issuer/JWK configuration. Only disable CSRF when the API truly uses credentials never sent automatically by browsers (such as bearer tokens in the `Authorization` header) and has no cookie-based browser flow; if browser sessions or cookie auth exist, retain CSRF defenses per your threat model. Test this policy separately from the Basic demo.

### 7.3. Security Context and Reactor Context

In Servlet, legacy code often does:

```java
// Do not use this to get the principal of a reactive request:
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

In WebFlux, you can accept `Mono<Principal>` directly as a controller parameter (as in `DemoController`), or use `ReactiveSecurityContextHolder` inside services:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

// Method placed in a service or bean running inside a reactive pipeline:
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

This reads authentication from the **subscriber context** populated by Spring Security. When no context or authentication exists, the pipeline can be empty; callers must handle `switchIfEmpty` or authorization per business rules. Never call `block()` to read the username, and never use a temporary `ThreadLocal` to "hold the principal".

**Distinguish security context from `WebSession`:** Reactor Context carries identity along a reactive chain; `WebSession` is where state may be stored across multiple HTTP requests. Having an authenticated request does not imply all that information is automatically stored in a session.

## 8. ThreadLocal, MDC, and Request Info Across Thread Switches

Servlet code commonly uses `RequestContextHolder`, `SecurityContextHolder`, `MDC.put("user", ...)`, or custom `ThreadLocal` fields to hold request IDs or the current user. In WebFlux, a thread can serve multiple requests and pipelines can switch threads. As a result:

- Request A's info can **disappear** after a scheduler switch.
- Leftover ThreadLocal data can cause Request B's logs to carry the wrong user or request ID without exact cleanup.
- Even when development appears to "work", stress tests or asynchronous pipelines can expose the bug.

Replacements:

1. For state needed only within one HTTP exchange, use `exchange.getAttributes()`, local variables passed through methods, or request-scoped context.
2. For data that must travel across reactive operators, use **Reactor Context** (typically `contextWrite`/`deferContextual`) and supported framework integrations.
3. For authentication, use **`ReactiveSecurityContextHolder`** from Spring Security rather than building a parallel mechanism.
4. For MDC, use supported context-propagation bridges and proper configuration; never assume Reactor automatically copies all `ThreadLocal`/MDC entries. Enforce scoping/cleanup and test across thread switches.
5. Never place passwords, tokens, or private data into MDC, Reactor Context, request attributes, or logs just for debugging.

Standalone **Reactor Core** example in a project that already includes Reactor:

```java
import reactor.core.publisher.Mono;

Mono<String> message = Mono.deferContextual(context -> Mono.just(
        "request-id=" + context.get("requestId")))
        .contextWrite(context -> context.put("requestId", "req-123"));
```

When subscribed and read, `message` emits `request-id=req-123`. This Java snippet (place inside a method and subscribe/test) shows that context data attaches to the **subscriber**, independent of the Java thread. It does not replace Spring Security context; use `ReactiveSecurityContextHolder` for the principal.

## 9. Investigating Blocking Libraries on the Request Path

### 9.1. High-Risk Categories

| Category | Examples | Why it must be reviewed |
| --- | --- | --- |
| Database | `JdbcTemplate`, Hibernate/JPA, JDBC `DriverManager` | Typically waits on sockets/connections and blocks threads |
| HTTP | `RestTemplate`, `RestClient`, sync SDK clients | Waits for responses on the calling thread; can cascade across services |
| Filesystem | `Files.readAllBytes` on large files, blocking streams | Disk I/O can block and consume large heap memory |
| Sleep/locks | `Thread.sleep`, `Future.get`, `CompletableFuture.join`, long locks | Halts the thread; event loop cannot serve other requests |
| Reactor | `Mono.block()`, `Flux.blockFirst()` inside handlers/filters | Breaks non-blocking chains; may throw `IllegalStateException` on non-blocking threads |
| Third-party SDKs | Synchronous JDBC, cloud/LDAP/crypto/HSM SDKs | Method signatures do not reveal blocking; inspect docs/call graphs |
| Serialization | Heavy CPU compression/decompression or signing/verification | Not blocking I/O, yet monopolizes the event loop; consider CPU-bounded schedulers |

**Using `Mono`/`Flux` types alone guarantees no safety.** Wrong examples:

```java
// Wrong: legacyDao.load(id) executes immediately when the method is called.
Mono<Account> wrong(String id) {
    return Mono.just(legacyDao.load(id));
}

// Wrong: block() inside a WebFlux handler still blocks the thread.
Mono<Account> alsoWrong(String id) {
    return Mono.just(webClient.get()
            .uri("/accounts/{id}", id)
            .retrieve()
            .bodyToMono(Account.class)
            .block());
}
```

These are **illustrative snippets**, requiring `legacyDao`, `Account`, and `webClient` to compile; their purpose is recognizing anti-patterns, not serving as a standalone app.

### 9.2. Prefer Non-Blocking APIs

- Outbound HTTP: `WebClient`, handling results via `flatMap`/`map`/`onErrorResume` without calling `block()`.
- Database: R2DBC drivers and Spring Data R2DBC (where feature-compatible), invoked via `Mono`/`Flux`.
- Cache/Redis/broker: use true reactive clients when available rather than wrapping blocking SDKs in `Mono.just`.
- Data streaming: use WebFlux codecs/reactive publishers, enforce body-size limits, and avoid buffering huge payloads on the heap unnecessarily.
- Reactive transactions: use reactive transaction managers and reactive data access; transactions follow Reactor Context rather than ThreadLocal as in imperative JDBC.

Reactive `WebClient` service example (class/method snippet with injected `WebClient`):

```java
Mono<String> loadSummary(String accountId) {
    return webClient.get()
            .uri("/accounts/{id}/summary", accountId)
            .retrieve()
            .bodyToMono(String.class);
}
```

The method returns the publisher to its caller without calling `block()`; the framework subscribes when the HTTP request needs the response. Configure base URLs, timeouts, codec size limits, and error mapping for the real system; never treat stubbed responses as proof of production connectivity.

### 9.3. When Synchronous JDBC/SDKs Must Stay: Isolate with `boundedElastic`

For libraries that **do not yet have** a reactive API equivalent, use `Mono.fromCallable` to defer blocking work until subscription time, and `subscribeOn(Schedulers.boundedElastic())` to run off the event loop:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// Service method; legacyDao.load(id) is a blocking call.
Mono<Account> loadViaLegacyDao(String id) {
    return Mono.fromCallable(() -> legacyDao.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

If `legacyDao.load(id)` returns `null`, `Mono.fromCallable` completes **empty**; handle `switchIfEmpty` when `null` represents a domain error. If the library throws an exception, the publisher signals `onError`. This **isolates blocking** without making JDBC non-blocking; throughput remains bounded by thread pools, queues, and connection pools.

Place `subscribeOn` close to the **blocking source** so the source is scheduled on the right pool. `Mono.defer(() -> Mono.just(legacyDao.load(id)))` only defers evaluation, without switching threads. `publishOn` switches the execution context for operators **downstream** of it; if the blocking source runs before `publishOn`, the event loop is still blocked.

Additional notes:

- Never allocate `Schedulers.newBoundedElastic(...)` per HTTP request; use a shared scheduler with suitable capacity, metrics, and clean shutdown lifecycle.
- Bound concurrency to match DB/HTTP connection pools; excess requests can pile up in queues even if the event loop stays unblocked.
- `Mono.timeout` does not necessarily **interrupt** blocking I/O that ignores thread interruption; configure timeouts on the JDBC/socket/SDK layer itself.
- `subscribeOn` does not automatically carry security/MDC ThreadLocals onto workers. Pass needed values as arguments or use proper context propagation.
- Never call `.block()` inside a `WebFilter`, `ReactiveAuthenticationManager`, WebFlux `@RestController`, or `WebClient` callback.

A small JUnit 5 test for the scheduler boundary. Create `src/test/java/demo/migration/BlockingBoundaryTest.java`:

```java
package demo.migration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotSame;

class BlockingBoundaryTest {
    @Test
    void blockingCallableRunsOffTheSubscriberThread() {
        Thread testThread = Thread.currentThread();

        Mono<String> pipeline = Mono.fromCallable(() -> {
                    assertNotSame(testThread, Thread.currentThread());
                    return "result-ok";
                })
                .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(pipeline)
                .expectNext("result-ok")
                .verifyComplete();
    }
}
```

Run: `./gradlew test --tests demo.migration.BlockingBoundaryTest` (Windows: `gradlew.bat test --tests demo.migration.BlockingBoundaryTest`). **Expected result:** the test passes with no mandatory application stdout. It proves the callable was scheduled onto another thread under test conditions; it **does not** prove a JDBC driver became async, prove latency at 1,000 requests, or confirm every call site is offloaded.

## 10. Sessions, Cookies, CSRF, CORS: Behaviors Likely to Shift After Migration

Never treat "returns 200 locally" as the definition of migration completion. For applications using sessions, cookies, or login flows, verify:

**Sessions and authentication**

- After login, is the principal persisted and restored on subsequent requests as required?
- Do cookie name, path, domain, `Secure`, `HttpOnly`, `SameSite`, and expiration match the reverse proxy/HTTPS origin?
- Does logout clear the session and cookie via the WebFlux flow, rather than clearing an unused legacy `HttpSession`?
- With multiple instances, do clients routed to a different instance lose their session? Are Spring Session reactive + Redis configured properly?
- Are session fixation protection and session ID renewal on login tested?

**CSRF**

- Browsers using cookie sessions are exposed to CSRF, even on endpoints returning JSON. Never disable CSRF across the board simply because WebFlux serves APIs.
- If transitioning from server-rendered HTML forms to an SPA, check the CSRF token repository, token delivery headers/cookies, state-changing HTTP methods, and browser requests.
- Bearer-only APIs without automatic browser credential sending may use a different design; also check whether those same endpoints still accept cookies.

**CORS and preflight**

- CORS handles `OPTIONS` preflight requests; ensure Spring WebFlux/Security does not reject requests **before** CORS has a chance to respond.
- Never combine `allowedOrigins("*")` with credentialed cookies; configure explicit origins, methods, headers, `allowCredentials`, and preflight caching per environment.
- Distinguish browser CORS errors from backend `401/403` errors: inspect network traces and preflight responses rather than guessing from UI error messages.

**Forwarded headers and proxies**

- Applications behind TLS termination need accurate scheme, host, and port/path when issuing redirects or building URLs; configure forwarded headers and trusted proxies narrowly.
- Avoid trusting external `X-Forwarded-*` headers directly when proxies do not strip or overwrite them; this affects redirect URIs, cookies, and HTTPS enforcement.

## 11. Filter Ordering and Where Security Logic Belongs

In Servlet, developers commonly use `FilterRegistrationBean#setOrder` and `OncePerRequestFilter` to run before or after Spring Security. In WebFlux, there are **two orchestration layers**:

1. Spring WebFlux `WebFilter` beans wrap the handler; order generally comes from `@Order`/`Ordered` on the beans.
2. Inside Spring Security reactive, `SecurityWebFilterChain` contains authentication/authorization steps ordered by `SecurityWebFiltersOrder` and configurers.

Never assume `@Order(-1)` on a `WebFilter` corresponds to a Servlet order such as `UsernamePasswordAuthenticationFilter`. When adding a custom authentication filter:

- Use Spring Security reactive `AuthenticationWebFilter` with `ReactiveAuthenticationManager` and `ServerAuthenticationConverter`.
- Register the filter via `ServerHttpSecurity.addFilterAt(webFilter, SecurityWebFiltersOrder.AUTHENTICATION)` or another appropriate position **after understanding existing filters**; do not push authentication into a global `WebFilter` and re-implement `401/403` handling manually.
- Verify security matchers, multiple chains, Bearer/basic/form/OAuth2 handlers, and exception semantics; add controlled logging at error-handling points.
- Ensure every success/failure publisher branch is returned for the framework to subscribe; calling `subscribe()` manually can cause races, context loss, or responses committed before authentication finishes.

**Ordering bug examples:**

- An audit filter reads `SecurityContextHolder` and sees `null` on the Reactor event loop; you cannot "fix" this by shifting the filter to `@Order(0)` based on Servlet habit. Use `ReactiveSecurityContextHolder` in the right context or extract the principal at the appropriate phase.
- `/api/admin/**` returns `200` bypassing authentication because a global `permitAll()` chain matched before the admin chain. Add `403` tests for under-privileged users and test route matchers.
- A custom `WebFilter` rewrites the response status to `401` whenever downstream `WebClient` returns `401`, conflating inbound authorization with another service's failure. Handle downstream errors in services/handlers instead of treating all HTTP 401s identically.

## 12. Mandatory Tests When Switching Stacks

| Case | Setup | What must be verified |
| --- | --- | --- |
| Public route | Unauthenticated request | `200` for declared public routes |
| Private route anonymous | No session/token/Basic | `401` or mechanism-appropriate login redirect; never unexpectedly `200` |
| Authenticated user lacking permissions | User without required role | `403` per actual policy, no resource leakage |
| Valid role/scope | Test principal/token with right authority | Endpoint allows access and returns user-scoped data |
| Session after login | Retain cookie across multiple requests | Login persists, timeout/logout work, no cross-client leaks |
| Stateless Bearer | Valid/expired/bad-signature token | 200/401 per JWT decoder, no accidental session reliance |
| Browser CSRF | `POST`/`PUT`/`DELETE` without token under cookie auth | Request blocked; accepted only when valid token is sent |
| CORS preflight | `OPTIONS` with Origin and Access-Control-Request-* | Response matches CORS policy, not wrongly blocked by auth filter |
| Correlation header | Valid/invalid header | Response echoes validated ID, never reflects dangerous strings |
| Downstream HTTP | Mock server returning 2xx/4xx/5xx and delays | Proper `WebClient` mapping, no `block()`, timeouts configured |
| Blocking integration | Load test with legacy DAO | Monitor event loop, `boundedElastic` queue, connection pools, latency |
| Multi-instance state | Multiple pods, requests routed across instances | Distributed sessions or truly stateless design as intended |
| Cancellation | Client disconnects while processing is pending | No indefinitely retained resources or dangling callbacks |
| Errors/timeouts | Downstream IdP/DB/HTTP slow or unavailable | Error signals handled cleanly without stalling the whole server |

Use `WebTestClient` for reactive HTTP and `StepVerifier` for publisher logic. With Spring Security Test, `mockUser()`, `mockJwt()`, and `mockOAuth2Login()` serve each authentication type **when the Spring Security `WebTestClient` configurer is properly applied**; never use Servlet `MockMvc`/`with(user(...))` for a WebFlux controller.

Place **rejection-branch tests** alongside happy paths. Also verify cookies, response headers, and security context across thread/scheduler switches; tests checking HTTP status codes alone can miss misconfigured session persistence or skipped filters.

## 13. Safe Step-by-Step Migration Workflow

1. **Verify the running stack.** Check Boot `WebApplicationType`, dependency tree, server logs, and WebFlux handler mappings; discard assumptions like "having `WebClient` means WebFlux".
2. **Preserve HTTP contracts.** List endpoints, verbs, auth requirements, scopes/roles, sessions/cookies, redirects, error payloads, and headers. Capture existing Servlet behavior tests as a baseline.
3. **Split each Servlet filter's responsibility.** Audit/correlation filters → `WebFilter`; authentication/authorization → Spring Security reactive DSL; request body handling → appropriate codecs/handlers. Avoid porting complex filters verbatim to `WebFilter`.
4. **Migrate authentication and security context.** Use `SecurityWebFilterChain`/`ServerHttpSecurity` and reactive managers/repositories. Eliminate code relying on Servlet `SecurityContextHolder` ThreadLocal.
5. **Decide on sessions.** Token APIs are typically stateless; browser logins may retain `WebSession`. Explicitly configure persistence, TTL, cookies, and security context repositories.
6. **Audit blocking call graphs from controllers/filters.** Move HTTP/DB calls to reactive clients where possible; offload legacy libraries with `fromCallable + boundedElastic` using bounded concurrency and timeouts.
7. **Migrate tests before rollout.** Verify allow/deny rules, CORS, CSRF, sessions, filter order, exception mapping, and timeouts. Reactive security tests should not blindly copy Servlet Mockito tests.
8. **Stage-test under load and across multiple instances.** Measure throughput, p95/p99, event-loop delay, `boundedElastic` saturation, connection pools, Reactor scheduling, and thread leaks.
9. **Roll out with a rollback plan.** Use canary or feature flags at routing/service boundaries; monitor 401/403, 5xx, latency, login errors, and session churn. When rolling back, ensure session/cookie/data contracts remain compatible.

A migration is complete only when **security requirements remain intact and blocking has been deliberately addressed**, not merely when the compiler stops reporting missing imports.

## 14. Symptoms and Debugging Guide

| Symptom | Common cause | Verification steps |
| --- | --- | --- |
| `@Component OncePerRequestFilter` never runs | App runs on WebFlux; filter uses Servlet API | Inspect runtime stack; switch to `WebFilter` or reactive security config |
| `HttpSession` cannot be injected | Controller runs under WebFlux | Use `WebSession`/`ServerWebExchange.getSession()` if state is needed |
| `SecurityContextHolder.getContext()` is empty | Principal lives in Reactor Context; execution switched threads | Use `ReactiveSecurityContextHolder` or reactive `Principal` parameter |
| App still shows Tomcat/DispatcherServlet | Both MVC and WebFlux starters present; Boot picked Servlet | Inspect dependencies/`WebApplicationType` and stack selection config |
| Public endpoint returns 401 | Matcher mismatch, wrong multi-chain order, Basic/JWT filter misapplied | Trace which `SecurityWebFilterChain` matched the endpoint; test each matcher |
| Request with role still returns 403 | Wrong authority format, method security, scope mapping | Compare actual authorities with `hasRole`/`hasAuthority` without logging raw tokens |
| Login succeeds, but next request loses login | Cookie not sent or session store/bean uses wrong stack | Inspect `Set-Cookie`/`Cookie`, TTL, `WebSession`, and Spring Session setup |
| Browser POST returns 403 | Missing CSRF token while cookie session is active | Check CSRF token repository, request headers/cookies, and actual policy |
| Preflight OPTIONS is blocked | Wrong CORS filter/security ordering | Inspect OPTIONS responses and allowed origins/headers/methods |
| `block()/blockFirst() are blocking` | `block()` called on a Reactor non-blocking thread | Inspect stack trace for the blocking call; rewrite reactively or offload |
| Slow responses despite low CPU | Sync JDBC/HTTP/locks running on the event loop | Capture categorized thread dumps, event-loop queue depth, and latency profiles |
| `boundedElastic` queue keeps growing | Blocking workload exceeds capacity/connection pool | Set concurrency limits/timeouts, measure, and incrementally adopt non-blocking drivers |
| Logger prints another request's user | Stale MDC/ThreadLocal or broken propagation | Reproduce with concurrent thread-switching requests; verify scope cleanup |
| Errors from manual `subscribe()` inside filter | Detached `subscribe()` loses context and races responses | Return proper `Mono<Void>`, compose via `then`/`flatMap`, and handle error signals |
| Container switched Tomcat→Netty; health OK, endpoints 5xx | Unmigrated blocking dependency/Servlet filter or changed default resource policy | Test protected HTTP flows and real DB/IdP/HTTP integrations |

### When Monitoring Performance

Track event-loop/Reactor scheduler metrics, percentile request latency, Netty connection pools, database pools, and queued request counts. Thread dumps under heavy load reveal `reactor-http-*` threads stalled on JDBC, sockets, or locks. Tools like BlockHound can help detect certain blocking calls in test environments, though instrumentation/Java version support must be verified; they do not replace profiling, load testing, and code review. Never enable DEBUG dumps of request bodies or `Authorization` headers in production while debugging authentication.

## 15. Acceptance Checklist for a WebFlux Module

- [ ] Verified runtime uses WebFlux/reactive, not merely a `WebClient` dependency.
- [ ] No Servlet `Filter`/`HttpServletRequest`/`HttpSession` remains on migrated request paths; any intentional Servlet adapter has a documented justification.
- [ ] Authentication/authorization logic resides in `SecurityWebFilterChain` and reactive security components; every matcher has allow and deny tests.
- [ ] Filters never use `block()`, manual `subscribe()`, or `ThreadLocal` to hold authentication or request state.
- [ ] CORS, CSRF, session fixation, logout, headers, and HTTPS/forwarded hosts are tested against realistic browser/API flows.
- [ ] All remaining blocking APIs are inventoried with explicit mitigation: reactive replacement or offloaded execution with concurrency/timeout bounds.
- [ ] Resource Server token validation/authority mapping or OAuth2 login has been re-verified on the reactive stack without mixing Servlet test utilities.
- [ ] Session store/cookie behavior works across multiple instances, or stateless APIs do not accidentally persist security contexts.
- [ ] Automated tests cover `401`, `403`, `200`, errors/timeouts, principal isolation, concurrent requests, and event-loop health.
- [ ] Metrics and alerts are deployed for latency, event-loop saturation, `boundedElastic` queues, DB connection pools, and auth failures, with a rollback path ready.

## 16. Self-Check Questions

1. Why does `OncePerRequestFilter` fail to execute automatically when an application runs on Spring WebFlux?
2. When should HTTP middleware be a `WebFilter`, and when should it be `AuthenticationWebFilter`/`ServerHttpSecurity`?
3. Is replacing `HttpSession` with `WebSession` enough by itself to share sessions across multiple pods?
4. Why can `SecurityContextHolder` be empty inside a reactive chain even when the request is authenticated?
5. Compare `Mono.just(dao.load())` and `Mono.fromCallable(() -> dao.load()).subscribeOn(boundedElastic())` regarding when the blocking call executes.
6. Why does placing `publishOn(boundedElastic())` after a blocking source fail to fix blocking that occurred upstream?
7. If an app has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, what must you verify before modifying Servlet filters?
8. Which two tests are mandatory to catch an admin route accidentally becoming public after migration?
9. When can `NoOpServerSecurityContextRepository` be considered, and why should CSRF not be disabled while cookie authentication is still in use?
10. To prove the system is not stalling the event loop, what metrics or tests are needed beyond HTTP `200`?

## Official Documentation

- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – Reactive Authentication Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security – Reactive HTTP/CORS/CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/index.html
- Spring Framework – WebFlux Concurrency Model and Blocking APIs: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework – WebFlux Filters: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Spring Framework – WebSession: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Session – WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Project Reactor – FAQ: Wrapping a Synchronous, Blocking Call: https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking

> When deploying for real, cross-check the APIs and configuration of your **exact Spring Boot/Spring Security/Framework versions**. Demo examples do not replace your production OAuth2/OIDC policies, session stores, proxies, drivers, and test suites.
