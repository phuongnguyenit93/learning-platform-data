# Concurrency Testing to Detect Context Loss or Identity Leakage in Spring Security Reactive

## 1. Goal and scope

In a Spring WebFlux application using Spring Security Reactive, two concurrent requests can travel through the same event loop, switch schedulers, run asynchronous operations, and complete in any order. A solid test suite must answer two independent questions:

1. **Context loss:** Alice's request was authenticated, yet after an async boundary, downstream code can no longer find Alice's `SecurityContext`/`Authentication` or sees an unauthenticated result.
2. **Identity leakage:** Alice's request reads Bob's identity/permissions/data (or vice versa) because security state is shared across requests.

Desired outcome: every subscription/request sees **its own** exact identity across all async steps; anonymous requests never inherit another request's session; authorization checks evaluate against the right principal; and result counts neither drop nor duplicate. Checking only HTTP 200 or running sequentially is not enough to uncover leaks.

Scope is **Spring Security Reactive + Project Reactor + WebFlux**; never apply Servlet-style `ThreadLocal` `SecurityContextHolder` assumptions to reason about Reactive context.

## 2. Mechanisms to understand before writing tests

### 2.1. Reactor Context follows the subscriber

`ReactiveSecurityContextHolder.getContext()` reads `SecurityContext` from **Reactor Context**, which is bound to the subscription flow. `ReactiveSecurityContextHolder.withAuthentication(authentication)` creates a `Context` holding that authentication to attach to a publisher via `contextWrite(...)`. `contextWrite` applies **upstream** in the chain via subscription-time context propagation.

`publishOn(...)`, `subscribeOn(...)`, `delayElement(...)`, and `flatMap(...)` inside a standard Reactor chain **do not automatically lose Reactor Context** just by switching threads. Bugs usually arise when developers break the subscription chain or use state outside Reactor: nested manual `subscribe()`, hopping onto raw `CompletableFuture`/callbacks without propagating context properly, storing the principal in a `static`/singleton field, using `ThreadLocal` manually on reused threads, or using publishers/caches that share identity-dependent data.

Distinguish **security context** from `ThreadLocal`s used for logging/MDC or other libraries. Micrometer/Reactor context propagation for certain registered `ThreadLocal` accessors does not mean Servlet-style `SecurityContextHolder` can be read across arbitrary Reactive operators.

### 2.2. Security invariants to verify

Suppose three concurrent requests exist: `R-A` (Alice), `R-B` (Bob), and `R-0` (anonymous).

| Request | Expected identity | Invariant to uphold |
| --- | --- | --- |
| `R-A` | `alice` | Every identity read in the pipeline returns `alice`; data/permissions are scoped to Alice |
| `R-B` | `bob` | Every identity read in the pipeline returns `bob`; never sees data meant only for Alice |
| `R-0` | No authenticated user | Rejected on login-required resources (typically HTTP 401 with HTTP Basic/Bearer config); must never receive A or B's principal |

On an endpoint returning the username, the measurable invariant is `actualIdentity(request) == expectedIdentity(request)` for **each individual request**; it is insufficient if the collected results merely contain both names while swapped between requests. On data endpoints, also verify resource ownership and HTTP 403 when a logged-in user lacks permission (exact status depends on system policy).

## 3. Multi-layer test design

- **Layer 1 — publisher/service:** create distinct `Authentication` instances, attach them via `contextWrite`, run multiple `Mono`s concurrently with `flatMap`/`merge`, and compare each expected/actual pair via `StepVerifier`. This layer isolates `Reactor Context` propagation bugs.
- **Layer 2 — WebFlux + security filter chain:** create a `WebTestClient` with `springSecurity()`, apply a separate `mockUser(...)` per **individual request**, execute concurrently, and verify status + response body. This layer catches bugs between filters, controllers, and services.
- **Layer 3 — over HTTP and real authentication:** when the app uses JWT/session/OAuth2, send distinct A/B credentials through a running server; verify signatures/issuer/audience/expiry, sessions, and real data. `mockUser()`/`mockJwt()` help test authorization code, but **do not verify** token signature decoders or real networking.

Never put a single `@WithMockUser` on the whole test to simulate two concurrent identities: that annotation fits testing one security identity per test method, whereas interleaving multiple principals requires per-publisher/per-request context.

## 4. Runnable example: Reactor-layer testing with JUnit 5

The Java 17+ example below creates **100 Alice/Bob pairs**, each with a distinct username. `IdentityService` reads identity **after** `Mono.delay` and `publishOn` to verify context survives async boundaries. Assertions pair `expected` with `observed` inside each publisher so both context loss and identity swaps are caught.

File `src/test/java/example/security/ReactiveIdentityServiceTest.java`:

```java
package example.security;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveIdentityServiceTest {

    static final class IdentityService {
        Mono<String> currentNameAfterAsyncBoundary() {
            return Mono.delay(Duration.ofMillis(2))
                    .publishOn(Schedulers.parallel())
                    .then(ReactiveSecurityContextHolder.getContext())
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("security context missing")))
                    .map(context -> context.getAuthentication().getName());
        }
    }

    record Observation(String expected, String observed) {}

    private final IdentityService service = new IdentityService();

    private Mono<Observation> requestAs(String username) {
        Authentication authentication = new UsernamePasswordAuthenticationToken(
                username, "ignored", AuthorityUtils.createAuthorityList("ROLE_USER"));

        return service.currentNameAfterAsyncBoundary()
                .map(actual -> new Observation(username, actual))
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(authentication));
    }

    @Test
    void concurrentSubscribersKeepTheirOwnIdentity() {
        int pairs = 100;

        Flux<Observation> requests = Flux.range(0, pairs)
                .flatMap(i -> Flux.merge(
                        requestAs("alice-" + i),
                        requestAs("bob-" + i)), 32);

        StepVerifier.create(requests.collectList())
                .assertNext(items -> {
                    assertEquals(pairs * 2, items.size());
                    Set<String> uniqueRequests = new HashSet<>();

                    for (Observation item : items) {
                        assertEquals(item.expected(), item.observed(),
                                "Cross-user identity or lost context");
                        assertTrue(uniqueRequests.add(item.expected()),
                                "Duplicated request: " + item.expected());
                    }
                })
                .verifyComplete();
    }

    @Test
    void missingContextDoesNotReuseLastUser() {
        StepVerifier.create(service.currentNameAfterAsyncBoundary())
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "security context missing".equals(error.getMessage()))
                .verify();
    }
}
```

**Why is this test meaningful?** `Mono.delay` introduces an async signal, `publishOn` forces the downstream step onto a scheduler, `flatMap(..., 32)` keeps multiple inner publishers active concurrently, and `contextWrite` binds a separate `Authentication` at subscribe time. `StepVerifier` does not depend on completion order; it catches errors per request pair. The negative test confirms a publisher lacking a security context errors as specified rather than accidentally seeing a previous run's principal.

**How to run:** add the test dependencies from Section 6, then run Gradle with the JUnit Platform test suite:

```bash
./gradlew test --tests 'example.security.ReactiveIdentityServiceTest'
```

On Windows, use `gradlew.bat` instead of `./gradlew`. Both tests must pass; the test does not enforce a fixed result order and prints no identities to stdout.

## 5. Integration example: multiple concurrent WebTestClient requests with distinct principals

This is a standalone Spring Boot WebFlux test fixture with a sample `GET /whoami` controller, a security chain requiring login, and a test client wired to the `ApplicationContext`. In a real product, use your existing controllers/services instead of the test fixture. **Note:** `mockUser(...)` operates through `WebTestClient`'s in-memory Spring Security test config; it is not credentials sent over HTTP to a separate server.

File `src/test/java/example/security/ConcurrentIdentityWebTest.java`:

```java
package example.security;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ConcurrentIdentityWebTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ConcurrentIdentityWebTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    record Attempt(String expected, String observed) {}

    @Test
    void concurrentUsersNeverReceiveAnotherUsersPrincipal() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<String> users = IntStream.range(0, 40)
                    .boxed()
                    .flatMap(i -> Stream.of("alice-" + i, "bob-" + i))
                    .toList();

            List<CompletableFuture<Attempt>> tasks = users.stream()
                    .map(user -> CompletableFuture.supplyAsync(() -> {
                        String response = client.mutateWith(mockUser(user))
                                .get().uri("/whoami")
                                .exchange()
                                .expectStatus().isOk()
                                .expectBody(String.class)
                                .returnResult().getResponseBody();
                        return new Attempt(user, response);
                    }, pool))
                    .toList();

            CompletableFuture.allOf(tasks.toArray(new CompletableFuture[0]))
                    .get(60, TimeUnit.SECONDS);

            for (CompletableFuture<Attempt> task : tasks) {
                Attempt attempt = task.join();
                assertEquals(attempt.expected(), attempt.observed(),
                        "The response belongs to a different principal");
            }

            client.get().uri("/whoami")
                    .exchange()
                    .expectStatus().isUnauthorized();
        } finally {
            pool.shutdownNow();
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({IdentityController.class, SecurityConfig.class})
    static class TestApplication {}

    @RestController
    static class IdentityController {
        @GetMapping("/whoami")
        Mono<String> whoami() {
            return Mono.delay(Duration.ofMillis(5))
                    .then(ReactiveSecurityContextHolder.getContext())
                    .map(context -> context.getAuthentication().getName());
        }
    }

    @Configuration
    @EnableWebFluxSecurity
    static class SecurityConfig {
        @Bean
        SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
            return http
                    .authorizeExchange(exchange ->
                            exchange.anyExchange().authenticated())
                    .httpBasic(Customizer.withDefaults())
                    .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                    .build();
        }
    }
}
```

**Avoiding fake concurrency tests:** each call uses `client.mutateWith(mockUser(user))` for its own per-request config instead of mutating a shared `currentUser` variable; `ExecutorService` lets 8 requests genuinely run in parallel, `Mono.delay` creates overlap inside the controller, and the check compares the body against the **exact future's** original username. `exchange()` is a blocking test API, so it runs on the test pool; never put such blocking calls inside the application's event loop. The `finally` block shuts down the pool even if assertions/timeouts fail.

Run the fixture with:

```bash
./gradlew test --tests 'example.security.ConcurrentIdentityWebTest'
```

If the real app has complex authorization rules, replace `/whoami` with an endpoint requiring specific tenant/owner checks and also verify Alice's request for Bob's resource is denied per policy; comparing usernames alone is a baseline check and does not prove full authorization.

## 6. Dependencies and runtime environment

Gradle Groovy example for a Spring Boot project managing dependency versions (snippet to merge into an existing `build.gradle`, not a standalone build file):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Requires Java 17+ and compatible Spring Boot/Spring Security/Reactor versions via the Spring Boot BOM. If your module already declares these dependencies, do not duplicate them. Section 4 tests the service directly; Section 5 loads a minimal WebFlux app and filter chain in tests. No production server, database, real accounts, or real tokens are needed for either fixture.

## 7. Minimum test suite when moving to a real application

| Scenario | How to trigger | Mandatory assertion |
| --- | --- | --- |
| Two users with same role | Interleave 50–100 A/B requests, varying username/subject each time | Principal, resource owner, and tenant match per request |
| Two users with different roles | Interleave USER/ADMIN requests to an authorized endpoint | 200/403 responses match each credential; B never gains A's permissions |
| Anonymous interleaved with A/B | Mix in unauthenticated requests | 401 or defined policy result; never leaks a prior user's body |
| Scheduler switches | `delay`, `publishOn`, async I/O inside pipeline | Identity preserved; no unexpected `Mono.empty()` |
| Errors / cancellation / retries | One request times out/cancels/errors while another is in flight | Never shifts principal to another subscriber; proper cleanup |
| Real tokens/sessions | A and B use independent credentials over the network | AuthN + AuthZ + tenant isolation all hold; verify expired/invalid tokens |
| Repeated load | Run multiple rounds with same seed/parameters and bounded concurrency | Zero mismatches; record completed/timed-out request counts |

To test JWTs in `WebTestClient` at the mock layer, you can use `mockJwt().jwt(jwt -> jwt.subject("alice"))` (with an appropriate resource-server test setup). When you need to prove real authentication, issue two validly signed test JWTs and send `Authorization: Bearer ...` headers; mock JWTs do not test the signature decoder.

## 8. Common bugs, detection, and fixes

### 8.1. Losing `SecurityContext` by splitting subscriptions

Symptom: a single Alice test passes, but once moved into a callback/`CompletableFuture` or manual `subscribe()`, `ReactiveSecurityContextHolder.getContext()` is empty. Every `subscribe()` creates a new subscription; never assume a new subscription inherits Context from a parent subscription.

- Wrong approach: calling `someMono.subscribe(...)` inside a service for a side effect and returning `Mono.just(...)`; the detached branch is no longer inside the pipeline where the caller attached `contextWrite`.
- Fix: return the publisher and compose with `flatMap`, `then`, `zipWhen`, or appropriate Reactor operators; let the framework/caller subscribe once at the system boundary.
- When forced to use non-Reactive APIs, pass identity/authorization data explicitly to the callback, or use a context propagation bridge designed and tested for that library. Never assume security context exists automatically just because code runs on the same thread.

### 8.2. Leakage via shared mutable state

The **intentionally broken** example below can return `bob` to Alice when two requests interleave. `AtomicReference` only makes memory access thread-safe; it does not make state request-scoped.

```java
// ANTI-PATTERN: global principal state
static final java.util.concurrent.atomic.AtomicReference<String> LAST_USER =
        new java.util.concurrent.atomic.AtomicReference<>();

static Mono<String> broken(String username) {
    return Mono.defer(() -> {
        LAST_USER.set(username);
        return Mono.delay(Duration.ofMillis(10))
                .map(ignored -> LAST_USER.get());
    });
}
```

Fix: never store request `Authentication`/principal/tenant in singletons, `static` fields, mutable fields, or caches not keyed by identity. Read from `ReactiveSecurityContextHolder` per subscription, or pass the resource owner as an immutable parameter when business logic needs it. If you place a mutable object inside `Context`, that object can still be shared by reference; `Context` immutability does not make its values immutable.

### 8.3. Tests giving false-green passes

- Asserting only `isOk()`: A can receive B's data and the test still PASSES.
- Sharing one mock principal across all requests: fails to create identity-crossover conditions.
- Sequential calls: unlikely to trigger bugs when callbacks/schedulers interleave.
- Relying on `Thread.sleep` to force races: hard to reproduce and flaky; prefer latches/barriers or controlled overlapping pipelines.
- Checking results in fixed completion order: `flatMap` can complete in any order; verify expected/actual pairs.
- Blaming `publishOn` or `delayElement` without finding the real split-subscription or shared-state boundary.
- Reading Servlet/ThreadLocal `SecurityContextHolder` in WebFlux and concluding Reactor Context is broken.

## 9. Increasing reliability and diagnosing failures

1. Use distinct principals (`alice-0`, `bob-0`, ...), iteration counts, and bounded concurrency. Each test case should have an independent `requestId`/`correlationId` tied to its expected principal.
2. On FAIL, record: `requestId`, expected principal/tenant/role, actual principal/tenant/role, the operator/endpoint where detected, iteration count, and concurrency. **Never log raw JWTs, passwords, cookies, or sensitive PII.**
3. Minimize reproduction down to 2 requests / 2 principals. Use `CountDownLatch` in tests or a mock barrier to reproduce the exact overlap once a race is found; never block the production event loop.
4. Audit subscription creation, every `contextWrite`, manual `subscribe()`, `cache/share`, callbacks into non-Reactor libraries, and singleton mutable state. Place identity reads **after** suspected boundaries to pinpoint the exact bug location.
5. After fixing, re-run unit tests, WebFlux tests, real-credential tests, and repeated runs. Passing fixture tests only assert the conditions tested in that test config; they do not automatically prove every runtime path is safe.

## 10. Lesson completion checklist

- [ ] Distinguish context loss from identity leakage, recognizing data leakage is more severe than a 401 error.
- [ ] Explain why Reactor Context follows the subscriber; never tie identity permissions to a thread.
- [ ] Tests create ≥2 distinct principals with genuinely overlapping publishers/requests.
- [ ] Each response is paired with its original expected identity and checks principal, role, and owner/tenant where applicable.
- [ ] Include anonymous and deny branches; never equate mock authentication with real credentials.
- [ ] Include async boundaries (`delay`/scheduler/I/O) and avoid nested `subscribe()` calls that drop context.
- [ ] Tests run repeatedly, failures include reproducible diagnostics, and assertions do not rely on response order or lucky `sleep`s.
- [ ] Never store or retain request principals in uncontrolled static/singleton/ThreadLocal state.

## References

- Spring Security — [Testing Authentication in Reactive WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html) and [Setting up WebTestClient with springSecurity()](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html).
- Spring Security — [Reactive Method Security and Reactor Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html), [Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html).
- Project Reactor — [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) and [Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
