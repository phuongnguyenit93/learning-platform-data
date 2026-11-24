# Testing Scheduler Switches, Subscription Cancellation, and Identity Isolation Across Requests

## 1. Goal and Scope

In Spring Security WebFlux, the key question to verify is: **does a request still see its own `Authentication` after execution switches `Scheduler`s, after a subscription is canceled, and when multiple requests share the same threads?**

After this lesson, you can:

1. Explain why `ReactiveSecurityContextHolder` relies on **per-subscription Reactor `Context`**, rather than assuming identity stays permanently attached to a thread.
2. Write tests proving `publishOn` and `subscribeOn` do not lose `SecurityContext` in a properly connected Reactor sequence.
3. Use `StepVerifier.thenCancel()` and `doFinally(CANCEL)` to test subscription cancellation, then confirm subsequent subscriptions do not pick up the wrong identity.
4. Run multiple interleaved subscriptions on the same `Scheduler` and verify each subscription sees its own user.
5. Verify isolation at the HTTP boundary using `WebTestClient` with requests for Alice, Bob, and unauthenticated callers.

**Scope:** authentication context inside Spring Security reactive flows. These tests do not replace tests verifying passwords, authorization, sessions, tokens, cookies, or gateway-level security.

## 2. Mental Model Needed Before Testing

`ReactiveSecurityContextHolder.getContext()` reads `Mono<SecurityContext>` from the current subscriber's Reactor `Context`. In WebFlux, security filters (especially `ReactorContextWebFilter` when applicable) inject the security context into the pipeline; in unit tests, you can explicitly attach context via `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`.

```text
Request A ── Subscription A [Reactor Context: alice]
                  │
              subscribeOn(S1)
                  │
               publishOn(S2)
                  │
              read identity: alice

Request B ── Subscription B [Reactor Context: bob]
                  │
               publishOn(S2)  ← may reuse the same thread
                  │
              read identity: bob
```

**Threads are reused; subscribers and `Context` remain distinct.** `publishOn` switches threads for downstream operators; `subscribeOn` affects subscription and the source side. Neither automatically wipes out Reactor `Context`. By contrast, a `ThreadLocal` holding user info can produce wrong results when threads change or get reused.

`contextWrite(...)` supplies context to operators **upstream** of that exact position in the sequence, following context propagation at subscription time. When `flatMap` creates a normal inner publisher, the subscriber context propagates into the inner publisher. A `contextWrite` placed strictly inside an inner publisher does not mutate the context of outer branches.

| Case | What must be asserted | What must not be inferred |
| --- | --- | --- |
| Switching `Scheduler` | Identity read before and after thread switch is both accurate | Fixed thread names or thread counts |
| Multiple subscriptions | Alice sees only Alice, Bob sees only Bob even when interleaved | Same thread implies same user |
| Canceling a subscription | Receives `CANCEL` signal; subsequent subscription does not see old context | `CANCEL` automatically deletes stored sessions/tokens |
| Independent requests | Alice, Bob, and anonymous requests yield distinct outcomes | `mockUser` tests verify real login logic |

## 3. Test Setup

Examples use **Java 17+**, JUnit Jupiter, Reactor Core/`reactor-test`, and Spring Security reactive. If the project uses Spring Boot with BOM dependency management, declare the required dependencies in `build.gradle` (Groovy DSL):

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

Place the following test class at `src/test/java/example/ReactiveContextIsolationTest.java`. This file self-contains four unit tests; the project needs the corresponding dependencies and compatible Spring Security/Reactor versions from its BOM. Running an HTTP server is not required to execute these four tests.

## 4. Unit Tests: Scheduler Hop, Concurrent Subscriptions, Cancellation, and Context Scope

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveContextIsolationTest {

    private static Authentication user(String name) {
        return new TestingAuthenticationToken(name, "unused", "ROLE_USER");
    }

    private static Mono<String> nameOrAnonymous() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
    }

    // Identity reading occurs after publishOn, on the designated Scheduler.
    private static Mono<String> readOn(Scheduler scheduler) {
        return Mono.just(1)
                .publishOn(scheduler)
                .flatMap(ignored -> nameOrAnonymous());
    }

    @Test
    void securityContextSurvivesSubscribeOnAndPublishOn() {
        Scheduler subscription = Schedulers.newSingle("subscription");
        Scheduler processing = Schedulers.newSingle("processing");
        try {
            Mono<String> pipeline = Mono.defer(
                        ReactiveContextIsolationTest::nameOrAnonymous)
                    .subscribeOn(subscription)
                    .publishOn(processing)
                    .flatMap(before -> nameOrAnonymous()
                            .map(after -> before + " -> " + after))
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                            user("alice")));

            StepVerifier.create(pipeline)
                    .expectNext("alice -> alice")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        } finally {
            subscription.dispose();
            processing.dispose();
        }
    }

    @Test
    void concurrentSubscriptionsDoNotMixIdentities() {
        Scheduler shared = Schedulers.newSingle("shared");
        try {
            // 100 separate subscriptions interleaved on the same worker thread.
            Flux<Boolean> checks = Flux.range(0, 100)
                    .flatMap(index -> {
                        String expected =
                                index % 2 == 0 ? "alice" : "bob";
                        return readOn(shared)
                                .map(expected::equals)
                                .contextWrite(
                                    ReactiveSecurityContextHolder
                                        .withAuthentication(user(expected)));
                    }, 16);

            StepVerifier.create(checks.collectList())
                    .assertNext(results -> {
                        assertEquals(100, results.size());
                        assertTrue(results.stream()
                                .allMatch(Boolean::booleanValue));
                    })
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            // A fresh subscription with no Authentication attached.
            StepVerifier.create(readOn(shared))
                    .expectNext("anonymous")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        } finally {
            shared.dispose();
        }
    }

    @Test
    void cancellationDoesNotLeakIntoNextSubscription() {
        Scheduler shared = Schedulers.newSingle("cancel-worker");
        AtomicReference<SignalType> termination = new AtomicReference<>();
        try {
            Flux<String> aliceStream =
                    Flux.interval(Duration.ofMillis(10), shared)
                        .concatMap(tick -> nameOrAnonymous())
                        .doFinally(termination::set)
                        .contextWrite(
                            ReactiveSecurityContextHolder
                                .withAuthentication(user("alice")));

            StepVerifier.create(aliceStream)
                    .expectNext("alice")
                    .thenCancel()
                    .verify(Duration.ofSeconds(5));

            assertEquals(SignalType.CANCEL, termination.get());

            // Same Scheduler, yet two new subscriptions have their own Context.
            StepVerifier.create(readOn(shared)
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(user("bob"))))
                    .expectNext("bob")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            StepVerifier.create(readOn(shared))
                    .expectNext("anonymous")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        } finally {
            shared.dispose();
        }
    }

    @Test
    void contextChangeInsideFlatMapStaysInsideThatBranch() {
        Mono<String> pipeline = Mono.just(1)
                .flatMap(i -> nameOrAnonymous()
                        .contextWrite(
                            ReactiveSecurityContextHolder
                                .withAuthentication(user("bob"))))
                .flatMap(innerName -> nameOrAnonymous()
                        .map(outerName -> innerName + "/" + outerName))
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice")));

        StepVerifier.create(pipeline)
                .expectNext("bob/alice")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
```

Run in a module with the test setup above:

```bash
./gradlew test --tests 'example.ReactiveContextIsolationTest'
```

On Windows use `gradlew.bat test --tests "example.ReactiveContextIsolationTest"`. The four tests complete without printing fixed business output lines to stdout; Gradle/JUnit reports pass/fail status. Strings such as `alice -> alice`, `anonymous`, and `bob/alice` in code are **values checked by assertions**, not printed logs.

### Analysis of Each Test

**Test 1 — Switching `Scheduler`:** `Mono.defer(...)` defers reading identity until subscription. `subscribeOn(subscription)` schedules the subscription/source side; `publishOn(processing)` switches subsequent processing to another scheduler. Both the first read and the read inside `flatMap` must return Alice. Asserting on **identity values** is more reliable than asserting on thread names.

**Test 2 — Interleaved subscriptions:** `Flux.range(0, 100)` creates 100 branches; each branch has its own `contextWrite(withAuthentication(...))` and calls `readOn(shared)`. `flatMap(..., 16)` allows up to 16 active inner subscriptions concurrently. Each branch's result must match the user attached to that branch; if any branch accidentally reads the wrong context, a `false` appears. An extra anonymous subscription on the same scheduler is tested to detect misuse of shared memory or `ThreadLocal`.

**Test 3 — Cancellation:** `Flux.interval` emits signals in real time; after the first Alice value, `thenCancel()` explicitly cancels the subscription. `doFinally` records `SignalType.CANCEL`. Next, Bob and an unauthenticated subscription execute on the same scheduler. This test proves behavior at the **subscription boundary**; it does not measure whether memory was garbage-collected or whether a server-stored session was deleted.

**Test 4 — Scope limits of `contextWrite`:** the first `flatMap` branch writes Bob only for its inner publisher, so it returns `bob`. The subsequent branch still reads the outer context Alice, yielding `bob/alice`. If the result were `bob/bob`, application code would likely be storing shared user state outside Reactor's scope.

`Schedulers.newSingle(...)` is `dispose()`d in `finally` so tests do not leave live threads behind after finishing. `verify(Duration.ofSeconds(5))` bounds wait time, catching hung tests instead of waiting forever. The test uses real schedulers to verify thread switching; if testing only time-based logic, `StepVerifier.withVirtualTime(...)` can be considered, provided the publisher is created inside the supplier and virtual vs. real schedulers are clearly distinguished.

## 5. Testing at the HTTP Boundary with WebTestClient

The unit tests above prove isolation across **subscriptions**. To verify **real HTTP requests passing through security filters**, create a probe endpoint returning the visible identity. The snippet below integrates into **an existing Spring Boot WebFlux application**, not a standalone Java program; place the controller/config inside a component-scanned package and permit GET `/identity` for anonymous users.

```java
// Example controller in a WebFlux application (add appropriate imports).
@RestController
class IdentityProbeController {

    @GetMapping("/identity")
    Mono<String> identity() {
        return Mono.just(1)
                .publishOn(Schedulers.parallel())
                .flatMap(ignored ->
                    ReactiveSecurityContextHolder.getContext()
                        .map(SecurityContext::getAuthentication)
                        .filter(authentication ->
                            !(authentication
                                instanceof AnonymousAuthenticationToken))
                        .map(Authentication::getName)
                        .defaultIfEmpty("anonymous"));
    }
}
```

`AnonymousAuthenticationToken` is normalized to the string `anonymous` in the probe endpoint so the output does not depend on whether Spring Security uses an anonymous token or leaves `SecurityContext` absent. In a real application, never treat the name `anonymous` as proof of authentication.

If no other chain handles this route, a minimal configuration for testing can be:

```java
@Configuration
@EnableWebFluxSecurity
class IdentityProbeSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/identity").permitAll()
                    .anyExchange().authenticated())
                .build();
    }
}
```

Use Spring test support to bootstrap `ApplicationContext` and bind Spring Security test configuration to `WebTestClient`. Key imports: `org.springframework.test.web.reactive.server.WebTestClient`, `org.springframework.context.ApplicationContext`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.boot.test.context.SpringBootTest`, `org.junit.jupiter.api.Test`, plus the two static imports shown below.

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class IdentityProbeHttpTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void separateHttpRequestsDoNotShareIdentity() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();

        client.mutateWith(mockUser("alice"))
                .get().uri("/identity").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");

        client.mutateWith(mockUser("bob"))
                .get().uri("/identity").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("bob");

        client.get().uri("/identity").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("anonymous");
    }
}
```

**Note when copying code:** the two `import static` lines in the example above are wrapped for display formatting; in a Java file, each import must be written on a single line, for example:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

`mockUser("alice")` and `mockUser("bob")` apply only to the client returned by `mutateWith`; the base client used in the third request remains unauthenticated. `springSecurity()` adds Spring Security test support when binding the client to `ApplicationContext`. This test checks filters and propagation in a mock server environment; it **does not** prove real Basic Auth/OAuth2/JWT verification, nor is it equivalent to an HTTP test over a real network port.

If your application policy requires authentication for `/identity`, a request without a user must return `401 Unauthorized` (or the corresponding policy result) rather than an `anonymous` body; adjust assertions accordingly rather than relaxing policy just to make a test pass. For systems with sessions/cookies, explicitly test both cases: independent requests do not share cookies; and requests intentionally sharing a session continue using the logged-in identity. These are two different expectations—valid session persistence must not be mislabeled as context leakage.

## 6. Escalating from Unit Tests to Harder Scenarios

| Scenario | Test setup | Expected outcome |
| --- | --- | --- |
| Consecutive thread switches | `subscribeOn` -> `publishOn` -> `flatMap` -> `publishOn` -> read again | Same `Authentication` throughout one subscription |
| High-concurrency requests | Send Alice/Bob with distinct correlation IDs under multi-request load | Every response matches the user of its corresponding request |
| Mid-stream cancellation | Long SSE/stream; client closes connection; server attaches `doFinally` | Observe `CANCEL` when cancellation actually reaches the publisher; next request stays isolated |
| Mid-stream error | Stream emits `onError` before and after scheduler hop | Other requests keep their identities; resources are released |
| Unauthenticated | New request without token/cookie or mock context | Does not inherit previous request's principal |
| Context branching | Inner `flatMap` has its own `contextWrite` | Context changes only inside the owning branch |
| Session/token repository | Test different tokens/cookies, expired tokens, or logout | Enforces persistence/removal authentication policy accurately |

For HTTP cancellation tests, `doFinally(CANCEL)` fires only if the cancellation signal reaches the observed publisher. A fast-completing publisher may emit `ON_COMPLETE` before the client cancels; avoid writing `CANCEL` assertions for streams that already finish immediately. Use a streaming endpoint with explicit synchronization/signals instead of relying on `Thread.sleep`.

When testing concurrency, tag each request with a test-only ID and verify tuples `(requestId, expectedUsername, actualUsername)`. Never log access tokens, passwords, session cookies, or raw `SecurityContext` objects into test reports.

## 7. Common Mistakes and Fixes

**1. Using imperative-style `SecurityContextHolder.getContext()` in a reactive flow.** Traditional holders typically rely on `ThreadLocal`; scheduler switches can yield null or accidentally read another task's data. In reactive pipelines, use `ReactiveSecurityContextHolder.getContext()` or retrieve principal/authentication through appropriate WebFlux APIs.

**2. Storing `Authentication` in a `static` variable, mutable singleton field, or custom `ThreadLocal`.** Concurrent requests can overwrite or misread each other. Pass data via Reactor `Context`, explicit parameters, or framework-supported request-scoped security mechanisms.

**3. Calling `subscribe()` inside `map`/`doOnNext` and hoping context flows into the new task.** An independent `subscribe()` creates a new subscription that may not inherit `Context`. Return inner publishers to `flatMap`/`concatMap` so the framework preserves the link; if an out-of-band subscription is genuinely necessary, manage context and lifecycle explicitly without assuming inheritance.

```java
// Structurally wrong: fire-and-forget detached from the current subscription.
Mono.just("event").doOnNext(value ->
    auditService.record(value).subscribe());

// Better: single pipeline where completion/error/cancellation are linked.
Mono.just("event").flatMap(value ->
    auditService.record(value).thenReturn(value));
```

The `auditService.record(...)` snippet is illustrative code assuming it returns `Mono<Void>`; it is not a standalone compilable example. Mandatory auditing should also not be handled with ad-hoc `subscribe()` inside a request handler.

**4. Placing `contextWrite` on the wrong side of the reading operator.** Context is supplied upstream, and does not automatically flow to operators downstream of the write point. Use the `bob/alice` test pattern to verify scope boundaries rather than guessing from code layout.

**5. Checking only `Thread.currentThread().getName()`.** Thread names reflect only where execution ran, not whether context is right. Always assert `Authentication.getName()` (and authorities/tenant if required) at the point actually accessing protected data.

**6. Failing to cancel/dispose resources in tests.** Infinite streams waiting only on `verifyComplete()` can hang; test-created schedulers not `dispose()`d can leak threads. Use `thenCancel()`, finite timeouts, and `finally`.

**7. Equating subscription cancellation with logout.** Cancellation ends a subscription and drops that Reactor `Context` out of scope; it does not automatically revoke JWTs, delete server sessions, clear cookies, or remove data from `ServerSecurityContextRepository`. Write separate tests for logout/revocation policies.

**8. Testing with `mockUser` and concluding real authentication is secure.** `mockUser` bypasses credential verification. Add integration tests using the real authentication mechanism and per-request credentials/cookies when verifying login, token parsing, or session isolation.

**9. Misunderstanding `ThreadLocal` context propagation vs. Reactor `Context`.** Automatic context propagation or MDC/`ThreadLocal` bridges exist for thread-local integration; you do not need to enable them just for `ReactiveSecurityContextHolder` to work across standard Reactor operators.

**10. Testing only sequentially.** A test running Alice then Bob can miss race conditions. Combine interleaved `flatMap` tests, concurrent HTTP tests, and anonymous requests to catch shared-state bugs.

## 8. Completion Criteria and How to Read Results

Mark the test suite as passing when all of the following hold:

- Scheduler-switch tests read the right identity both before and after `subscribeOn`/`publishOn`.
- Concurrent subscriptions on one `Scheduler` always receive the user attached to each; unauthenticated subscriptions return `anonymous` in unit tests.
- Cancellation tests emit `CANCEL`, after which Bob remains Bob and unauthenticated flows do not see Alice.
- `contextWrite` inside an inner publisher does not leak identity to outer branches.
- Properly security-configured HTTP tests return Alice, Bob, and anonymous/unauthorized per policy without accidentally sharing sessions/cookies.
- No uncontrolled detached `subscribe()` calls, mutable global `Authentication` state, hung tests, or leaked test schedulers.

**Limits of evidence:** passing tests show that the tested paths preserve context, not an absolute proof against leaks across every branch, non-Reactor library, authentication type, and session state. Whenever security code changes, re-run tests aligned with your exact security filter chain, token/session repository, and system concurrency load.

## 9. Official Documentation for Reference

- Spring Security — Reactive Method Security and `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Configuring `WebTestClient`: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — `mockUser` for reactive tests: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Project Reactor — Subscriber-attached `Context` and `contextWrite`: https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html
- Reactor Test — `StepVerifier`, `thenCancel()`, and `verify(Duration)`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
