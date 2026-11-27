# 30.10. Detecting Blocking Calls and Controlling Subscriptions in Security Flows

## 1. Core Problem: Reactive Security Must Be Right in Both Permissions and Execution

In a **Spring Security OAuth 2.0 OIDC Client application on WebFlux**, a request may already be authenticated properly yet the system still suffers hard-to-reproduce issues: slow logins, timeouts when the provider is under load, disappearing `SecurityContext`, missing audit logs, repeated token refreshes, or tasks continuing to run with stale security info after a request finishes.

Two characteristic causes in Reactive programming are:

1. **Blocking on threads that forbid blocking:** JDBC, `Thread.sleep`, `Future.get`, synchronous HTTP clients, or calling `Mono.block()` inside the Reactor Netty event loop.
2. **Uncontrolled subscriptions:** manually calling `subscribe()` in the middle of a filter/service, forgetting to return a `Mono` that needs execution, triggering side effects before subscription, or losing control over cancellation, errors, and `ReactiveSecurityContextHolder`.

Example:

~~~java
// COUNTEREXAMPLE — code inside request handling.
Mono<Void> onLogin(String userId) {
    auditService.saveAudit(userId).subscribe(); // fire-and-forget
    String role = jdbcRoleRepository.loadRole(userId); // blocking JDBC
    return Mono.empty();
}
~~~

The bug is not only performance: the response can complete before auditing finishes, audit errors are detached from the request's error stream, and authorization decisions can be made by a service that stalls the event loop. If a manually subscribed task does not inherit the right Reactor Context, it may no longer know the authenticated user/tenant.

### Lesson Objectives

Upon completing this lesson, you will be able to:

- Spot blocking calls in Spring WebFlux, OAuth2/OIDC Client, UserInfo processing, authority mapping, and authorized-client persistence.
- Use **BlockHound** properly to detect blocking on non-blocking threads in tests.
- Use **`StepVerifier`**, **`PublisherProbe`**, **`TestPublisher`**, virtual time, and `WebTestClient` to control subscription/cancellation/error paths.
- Write **lazy** reactive pipelines subscribed by the caller/framework; avoid `block()` and `subscribe()` in security components.
- Propagate/read **`ReactiveSecurityContextHolder` in Reactor Context**, without confusing it with `ThreadLocal` security contexts.
- Verify that unauthorized requests never trigger downstream API calls, token refreshes, or unauthorized audit side effects.
- Distinguish schedulers used to isolate blocking libraries from genuine non-blocking solutions.
- Handle race conditions, timeouts, and cancellation properly in token refresh, UserInfo, logout, and security operations.

> **Context:** Spring Boot WebFlux + Spring Security OAuth2 Client/OIDC Login, Reactor Core/Test. Code snippets illustrate common ideas and APIs in the Spring Security 6.x ecosystem; verify exact syntax/support against your locked BOM version. Do not use test mocking to conclude that the entire OIDC protocol has been tested end-to-end.

## 2. Reactive Security Map: Who Subscribes Where?

~~~mermaid
flowchart TD
    A["HTTP request on Reactor Netty"] --> B["SecurityWebFilterChain"]
    B --> C["Authentication WebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["Reactive OAuth2/OIDC services"]
    E --> F["Authorized Client/Token Store"]
    B --> G["Reactive Authorization"]
    G --> H["Handler -> Service -> Repository"]
    H --> I["WebClient calling Resource Server"]
    H --> J["Response Mono"]
    J --> K["Spring WebFlux/HTTP runtime manages subscription"]
    G -->|Denied| L["401/403, protected downstream not called"]
~~~

In a normal WebFlux HTTP request, **the Spring WebFlux/HTTP runtime performs the subscription** on the returned publisher. Application code should **build and return** a `Mono`/`Flux`; never manually subscribe inside a handler, filter, or repository just to "trigger" execution.

### 2.1. Roles

| Component | Reactive contract | What to test |
| --- | --- | --- |
| `SecurityWebFilterChain` | Composes `WebFilter`s | Exact path matching; no auth bypass |
| `ReactiveAuthenticationManager` | `Mono<Authentication>` | Auth success/error/empty; non-blocking |
| `ServerAuthenticationSuccessHandler` | `Mono<Void>` | Side effects composed into response |
| `ServerAuthenticationFailureHandler` | `Mono<Void>` | Error response executed accurately |
| `ReactiveOAuth2UserService` | `Mono<OAuth2User>` | Non-blocking UserInfo/claims; right subject |
| `ReactiveOAuth2AuthorizedClientManager` | `Mono<OAuth2AuthorizedClient>` | Token refresh/success/failure persistence |
| `ReactiveOAuth2AuthorizedClientService` | `Mono<Void>` or related publisher | Save/remove execute upon subscription |
| `ReactiveAuthorizationManager` | Reactive decision publisher | Unauthorized never triggers protected operation |
| `WebClient` | `Mono<ClientResponse>` / `Mono<T>` | Proper timeout, cancellation, 401/403 handling |
| Spring Session reactive | Session operation publisher | Context/session persisted per lifecycle |

### 2.2. Root Causes of Failures

~~~text
blocking JDBC/UserInfo SDK
  -> event loop occupied -> latency spikes -> timeouts

service subscribes manually
  -> request returns early -> side effects/errors not awaited
  -> security context may vanish in separate subscription

service forgets to subscribe/compose
  -> cold publisher never runs -> audit/store not saved

manual token request retries
  -> multiple subscriptions -> may exchange authorization code twice
  -> refresh rotation race or duplicate side effects
~~~

## 3. Reactor Fundamentals to Remember When Testing Security

### 3.1. Publishers Are Usually Lazy

~~~java
import reactor.core.publisher.Mono;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();

Mono<String> tokenLookup = Mono.fromSupplier(() -> {
    calls.incrementAndGet();
    return "token-metadata";
});

// calls is still 0: pipeline built only, no subscription yet.

tokenLookup.subscribe(); // Illustrates semantics; DO NOT use in services.
// calls = 1 after subscription executes.
~~~

In tests, use `StepVerifier` instead of calling `subscribe()` manually and sleeping:

~~~java
StepVerifier.create(tokenLookup)
    .expectNext("token-metadata")
    .verifyComplete();
~~~

### 3.2. Subscription Can Happen Multiple Times

With cold publishers, **each subscription can re-execute upstream**:

~~~text
Mono.defer(refreshTokenOnce)
  -> Subscriber A: calls Token Endpoint
  -> Subscriber B: calls Token Endpoint again
~~~

This is especially dangerous for **single-use authorization codes**, Refresh Token rotation, revocation, and business auditing. Never assume that storing a `Mono` variable guarantees the operation executes only once.

### 3.3. Errors and Cancellation Are Part of the Contract

A reactive stream has:

- `onSubscribe`: subscription begins.
- `onNext`: emits an item.
- `onComplete`: completes.
- `onError`: fails.
- `cancel`: subscriber stops requesting further items.

In security pipelines, **cancellation does not mean backend side effects never happened**. If the Token Endpoint already processed a Refresh Token yet the client timed out, handle the unknown outcome and token rotation rather than blindly retrying.

### 3.4. Schedulers Do Not Determine Security Context

Reactor Context is a **per-subscriber context**, unlike `ThreadLocal`. A pipeline can switch schedulers while preserving Reactor Context properly; a detached subscription can lose context even when running on the same thread.

## 4. Blocking Calls That Easily Slip Into Reactive Security Flows

| Location | Blocking example | Risk |
| --- | --- | --- |
| Custom authentication manager | `JDBC` user/role lookup | Event loop starvation, login timeouts |
| Custom UserInfo client | `RestTemplate` or synchronous HTTP SDK | Hangs handshake/proxy, lowers throughput |
| OAuth2 authorized client service | Sync JDBC/`Thread.sleep` lock wait | Refresh storms, slow token issuance |
| OIDC claim enrichment | Synchronous LDAP/Directory SDK | Blocks event loop before session creation |
| Security audit | Blocking DB/file writer | Unstable response times |
| Token signing/key loading | Synchronous HSM/provider SDK | Latency spikes, contention |
| Session store | Blocking Redis client | Callback `state` not saved in time |
| Role lookup | `CompletableFuture.get()` / `join()` | Blocks waiting on remote lookup |
| Application service | `Mono.block()` / `Flux.blockLast()` | May throw errors on non-blocking threads |
| Retry/backoff | `Thread.sleep(...)` | Occupies thread instead of reactive delay |
| Reflection/legacy library | Hidden I/O inside SDK | Hard to spot in code review |

Blocking does not appear only in controllers. An `OidcUserService` or authority mapper invoked during login can also run on the event loop when composed into the reactive chain.

### 4.1. Blocking vs. CPU-Heavy Computation

Hashing, JWT signature verification, or complex claim processing is **CPU-bound**, not necessarily blocking I/O. BlockHound primarily detects **instrumented blocking APIs**; it does not certify that a 500 ms CPU calculation is safe.

For CPU-bound workloads, optimize/bound concurrency and choose suitable schedulers rather than treating `boundedElastic` as a cure-all.

### 4.2. Reactive vs. Blocking Databases

- **R2DBC** fits non-blocking DB interactions.
- **JDBC/JPA** are synchronous APIs; if you must keep them in WebFlux, isolate them on the right scheduler and bound pools/concurrency.
- A Spring Data repository returning `Mono` does not automatically prove the underlying driver is non-blocking. Understand the implementation.

## 5. BlockHound: Detecting Blocking Calls on Non-Blocking Threads

**BlockHound** is a JVM instrumentation tool that detects certain blocking operations (e.g., `Thread.sleep`) running on Reactor threads marked **non-blocking**. On disallowed calls, it typically throws `reactor.blockhound.BlockingOperationError`.

This improves bug detection in **test/integration environments**; it is not proof that the entire program is non-blocking.

### 5.1. Dependencies

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor.tools:blockhound'
}
~~~

**Ensure `blockhound`/Reactor/Spring Security versions are compatible with your BOM and JDK.** Some projects require an explicit BlockHound version, runtime instrumentation/Java agent flags, or a dedicated process fork. Do not assume the snippet runs unchanged on every JDK/CI setup without compatible configuration.

### 5.2. Installing Early in Test JVMs

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockHound;

class BlockHoundSmokeTest {

    @BeforeAll
    static void installOnce() {
        BlockHound.install();
    }

    @Test
    void testPlaceholder() {
        // Blocking tests below will subscribe to pipelines.
    }
}
~~~

**Important note:** BlockHound instrumentation is typically **JVM-wide** and must be installed early, before Reactor schedulers/threads are heavily initialized. Avoid calling `BlockHound.install()` repeatedly in every test class expecting the JVM to reset. In parallel test suites, configure a **dedicated suite/JVM fork** or shared bootstrap per BlockHound documentation.

### 5.3. What BlockHound Can and Cannot Do

| Scenario | Expectation |
| --- | --- |
| `Thread.sleep` on `Schedulers.parallel()` | Typically detects `BlockingOperationError` |
| `Thread.sleep` on Reactor Netty event loop | Typically detected if instrumentation is active |
| Blocking I/O on `Schedulers.boundedElastic()` | Typically allowed because `boundedElastic` is for blocking |
| Blocking JDBC driver in an uninstrumented library | May be missed |
| Long CPU spin calling no blocking APIs | Not necessarily detected |
| Direct `Mono.block()` on non-blocking thread | Reactor itself usually throws blocking errors; BlockHound adds a signal |
| Manual `subscribe()` in wrong context | BlockHound **does not automatically detect** lifecycle bugs |
| Lost `SecurityContext` from custom subscription | Cannot rely on BlockHound to detect |

Therefore combine **BlockHound + `StepVerifier`/`PublisherProbe` + `WebTestClient` + observability** rather than substituting one for another.

## 6. Testing a Blocking Call with BlockHound

Example for an **environment with BlockHound properly installed**:

~~~java
import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDetectorTest {

    @Test
    void sleepOnParallelSchedulerIsDetected() {
        Mono<String> source = Mono.fromCallable(() -> {
            Thread.sleep(10); // DELIBERATELY WRONG to demonstrate test.
            return "done";
        }).subscribeOn(Schedulers.parallel());

        StepVerifier.create(source)
            .expectErrorMatches(error ->
                error instanceof BlockingOperationError
                || error.getCause() instanceof BlockingOperationError)
            .verify();
    }
}
~~~

This assumes BlockHound was installed **before the test runs**, rather than installing inside the test method itself. How exceptions are wrapped can depend on operators/frameworks; test on your real JDK/Reactor version and avoid asserting only string error messages.

### 6.1. Why Must the Test Use a Non-Blocking Scheduler?

If you only write:

~~~java
Mono.fromCallable(() -> {
    Thread.sleep(10);
    return "done";
});
~~~

and run the test on a regular JUnit thread, BlockHound may not treat it as a Reactor non-blocking thread. A passing result **does not prove the call is safe on the Netty event loop**.

Tests must use thread schedulers reflecting the protected environment or run through a WebFlux test harness with proper instrumentation.

### 6.2. Never Whitelist Blocking Arbitrary Just to Pass Tests

BlockHound provides `allowBlockingCallsInside(...)` allowlisting for verified cases. Over-broadly allowlisting entire OAuth2/authorization/user-service packages blinds tests to real bugs. Only permit justified, narrowly scoped exceptions with tracked issues for long-term fixes.

## 7. Fixing Blocking: Prefer Reactive APIs, Then Isolate Schedulers

### 7.1. Counterexample: Calling JDBC Directly Inside `map`

~~~java
Mono<String> role = currentUserId()
    .map(userId -> jdbcRoleRepository.loadRole(userId));
~~~

`map` runs on the upstream signal's context; when requests run on the event loop, synchronous JDBC can block the event loop.

### 7.2. When a Reactive Repository Exists

~~~java
Mono<String> role = currentUserId()
    .flatMap(userId -> reactiveRoleRepository.findRoleByUserId(userId));
~~~

Here `findRoleByUserId` returns a `Mono<String>` backed by a non-blocking driver. When no role is found, apply business policy: reject or grant a restricted authority—never escalate privileges by default.

### 7.3. When Blocking JDBC Is Unavoidable

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> roleForUser(String userId) {
    return Mono.fromCallable(() ->
            jdbcRoleRepository.loadRole(userId))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`Mono.fromCallable` defers the blocking call until subscription; `subscribeOn(Schedulers.boundedElastic())` runs the source on the scheduler designed to wrap blocking I/O.

**Limitations:**

- `boundedElastic` has finite threads/queues, not infinite capacity.
- Switching schedulers does not turn JDBC into non-blocking I/O.
- Keep timeouts, concurrency bounds, and connection pools sized properly.
- Scheduler isolation must wrap the **blocking operation itself**; never run the dangerous work on the event loop first and only call `publishOn(boundedElastic())` afterward.
- When possible, migrate to R2DBC/non-blocking HTTP clients to simplify.

### 7.4. `subscribeOn` Differs from `publishOn`

| Operator | Primary effect | Common mistake |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Controls where source subscription and upstream execution start | Placed after a side effect already executed at assembly time |
| `publishOn(scheduler)` | Switches where downstream signals are processed afterward | Blocking before `publishOn` still blocks the old thread |

Example:

~~~java
// COUNTEREXAMPLE: blocking call runs IMMEDIATELY when creating Mono.
String value = jdbcRoleRepository.loadRole(userId);
Mono<String> source =
    Mono.just(value).subscribeOn(Schedulers.boundedElastic());

// BETTER if JDBC cannot be replaced yet:
Mono<String> safeSource = Mono
    .fromCallable(() -> jdbcRoleRepository.loadRole(userId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

## 8. Subscriptions Belong to the Caller/Framework, Not the Service

### 8.1. Counterexample: Fire-and-Forget in a Security Service

~~~java
public Mono<Void> recordLogin(String userId) {
    auditRepository.saveEvent(userId).subscribe(); // WRONG.
    return Mono.empty();
}
~~~

Problems:

- Response can complete before auditing finishes.
- No proper error propagation.
- Request cancellation does not control the child subscription.
- Reactor Context (authentication/tenant/correlation) can be detached.
- Tests cannot await audit completion via the returned publisher.
- Framework retries/circuit breakers cannot cover this side effect.

### 8.2. Compose the Publisher Into the Return Value

~~~java
public Mono<Void> recordLogin(String userId) {
    return auditRepository.saveEvent(userId)
        .then();
}
~~~

For a success handler:

~~~java
public Mono<Void> afterLoginSuccess(
        WebFilterExchange exchange,
        Authentication authentication) {

    return auditService.recordSuccess(authentication)
        .then(redirectSuccessHandler.onAuthenticationSuccess(
            exchange, authentication));
}
~~~

This is an **illustrative method body** for `ServerAuthenticationSuccessHandler`, assuming audit policy requires recording before redirecting and dependencies are injected. If auditing must not fail logins, design an **explicit outbox/queue/error policy** rather than hacking with detached `subscribe()`.

### 8.3. When Side Effects Must Not Block Responses

A system can use a **transactional outbox**: persist the event inside a controlled transaction, then have a dedicated worker/queue subscriber process it. That is a **designed, monitored, and owned subscription boundary**—unlike stray `subscribe()` calls inside requests.

You cannot claim auditing is mandatory while calling fire-and-forget `subscribe()` and returning 200 regardless of whether auditing ran.

## 9. Subscriptions and Operators Prone to Security Bugs

| Anti-pattern | Issue | Alternative / check |
| --- | --- | --- |
| `mono.subscribe()` in `WebFilter` | Creates stream unmanaged by request | Return `Mono<Void>` |
| `mono.block()` on event loop | Blocks non-blocking thread | Compose with `flatMap`/`then` |
| `doOnNext(v -> asyncService.save(v).subscribe())` | Detached side effect | `flatMap(v -> asyncService.save(v).thenReturn(v))` |
| `onErrorResume(e -> Mono.empty())` on all errors | Masks authn/authz failures | Handle only classified errors |
| `switchIfEmpty(expensiveFallback())` with eager side effects | Eager assembly side effect | `switchIfEmpty(Mono.defer(() -> expensiveFallback()))` |
| `Mono.when(authCheck, apiCall)` | Subscribed together; API may run before auth check finishes | `authCheck.then(apiCall)` where `authCheck` errors on denial |
| `flatMap` when order is mandatory | Concurrency and reordering | `concatMap` or `flatMapSequential` where appropriate |
| `cache()` on shared user token stream | May cache credentials across wrong subscriber/context | Policy-governed per-principal lifecycle; avoid global cache |
| `retry()` on authorization code exchange | Reuses single-use code | Controlled fresh login retry |
| `timeout(...).onErrorReturn("allow")` | Fail-open authorization | Fail-closed policy |

### 9.1. `Mono.when` Does Not Guarantee Authorization Before Resource Operations

Counterexample:

~~~java
Mono<Void> result = Mono.when(
    authorizeAccess(),      // Even if this fails, downstream work may already start.
    deleteProtectedRecord()
);
~~~

`Mono.when` subscribes to all publishers to coordinate completion; other publishers can start before authorization fails. For protected operations, enforce sequencing:

~~~java
Mono<Void> result = authorizeAccess()
    .then(Mono.defer(() -> deleteProtectedRecord()));
~~~

`authorizeAccess()` here must **error** on denial and complete on approval. If it returns `Mono<Boolean>`, inspect the boolean first before invoking the operation.

### 9.2. Do Not Use `doOn...` to Wire Asynchronous Tasks

~~~java
// WRONG — publisher created by asyncService is never composed.
return authenticate()
    .doOnNext(auth -> asyncAudit.save(auth));

// RIGHT — audit becomes part of the pipeline.
return authenticate()
    .flatMap(auth -> asyncAudit.save(auth).thenReturn(auth));
~~~

`doOnNext` is for synchronous, lightweight, safe observation; not for creating unsubscribed publishers.

## 10. Verifying Authorization Branches with `PublisherProbe`

`PublisherProbe` from `reactor-test` proves whether a publisher was subscribed, requested, or canceled. It is especially useful to confirm that **unauthorized requests never touch a Resource Server**.

### 10.1. Testing That Unauthorized Requests Do Not Call Downstream

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class AuthorizationSubscriptionTest {

    @Test
    void deniedAccessMustNotSubscribeToProtectedOperation() {
        PublisherProbe<String> downstream =
            PublisherProbe.of(Mono.just("sensitive-result"));

        Mono<String> result = Mono.just(false)
            .flatMap(allowed -> allowed
                ? downstream.mono()
                : Mono.error(new AccessDeniedException("Denied")));

        StepVerifier.create(result)
            .expectError(AccessDeniedException.class)
            .verify();

        downstream.assertWasNotSubscribed();
    }

    @Test
    void grantedAccessSubscribesExactlyThroughSelectedBranch() {
        PublisherProbe<String> downstream =
            PublisherProbe.of(Mono.just("allowed"));

        Mono<String> result = Mono.just(true)
            .flatMap(allowed -> allowed
                ? downstream.mono()
                : Mono.error(new AccessDeniedException("Denied")));

        StepVerifier.create(result)
            .expectNext("allowed")
            .verifyComplete();

        downstream.assertWasSubscribed();
        downstream.assertWasRequested();
    }
}
~~~

`PublisherProbe` proves branch subscription/request/cancellation; it does not replace OIDC signature or API policy verification.

### 10.2. Security Checks Must Precede Operations

A service design:

~~~java
Mono<String> readProtectedData(
        String userId, String documentId) {

    return authorizationService
        .assertCanRead(userId, documentId)
        .then(Mono.defer(() ->
            reactiveRepository.readContent(documentId)));
}
~~~

In this design, `assertCanRead` must emit `onError` on denial and `onComplete` on approval. If it returns `Mono<Boolean>`, use `flatMap`/`filter` to handle `false` explicitly; `then` ignores emitted booleans and **does not reject automatically**.

### 10.3. Security Checks May Need Per-Request Re-Evaluation

For sensitive authorization, check user/tenant at request time on the exact resource rather than caching decisions by username across time/tenants/contexts. Probe tests prove branches block API calls, yet application/domain-layer policy tests are still required.

## 11. Using `TestPublisher` to Verify Cancellation

`TestPublisher` lets you emit `next`/`error`/`complete` signals at test-controlled times, useful for detecting when operations **cancel** after receiving enough data or when a subscriber disconnects.

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class CancellationTest {

    @Test
    void takeOneCancelsUpstreamAfterFirstValue() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux().take(1))
            .then(() -> source.next("first"))
            .expectNext("first")
            .verifyComplete();

        source.assertCancelled();
    }
}
~~~

### 11.1. What Does Cancellation Mean in Security Flows?

If a browser disconnects right as the app called the Token Endpoint or Revocation Endpoint:

- The local publisher may be canceled.
- The remote server **may already have processed the request** even though the client never saw the response.
- A Refresh Token may already have rotated.
- Never automatically retry single-use operations like Authorization Code exchange.

Cancellation tests should verify **state consistency/recovery**, not merely thread counts.

### 11.2. `doFinally` Is for Observation, Not Granting Permissions

~~~java
return protectedPipeline()
    .doFinally(signal -> metrics.recordTermination(signal.name()));
~~~

`doFinally` observes `CANCEL`, `ON_COMPLETE`, `ON_ERROR`. Do not use `doFinally` for mandatory blocking revocation/auditing because termination has already occurred and side effects execute under synchronous callback semantics.

## 12. `StepVerifier`: Testing Completion, Errors, and Timeouts Thoroughly

### 12.1. Success Path

~~~java
StepVerifier.create(Mono.just("authenticated"))
    .expectNext("authenticated")
    .verifyComplete();
~~~

### 12.2. Authorization Denied

~~~java
Mono<String> denied = Mono.error(
    new org.springframework.security.access.AccessDeniedException(
        "Policy denied"));

StepVerifier.create(denied)
    .expectError(
        org.springframework.security.access.AccessDeniedException.class)
    .verify();
~~~

### 12.3. Testing Timeouts with Virtual Time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Key point: **construct the publisher inside the `withVirtualTime` supplier** so the virtual scheduler applies at the right moment. Avoid creating sources/timers on old schedulers before virtual time starts. Virtual time avoids `Thread.sleep(5000)` in tests.

### 12.4. Do Not Confuse Timeouts with Authorization Failures

If UserInfo/Token Endpoint times out, never convert it into `Mono.just(approvedUser)` to let login succeed. Policy may allow degraded behavior for **optional profile fields**, but must never skip identity verification or account/tenant authorization.

## 13. Testing Laziness: No Side Effects Without Subscription

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.just("safe-metadata");
});

// assertEquals(0, attempts.get()) before creating StepVerifier.

StepVerifier.create(source)
    .expectNext("safe-metadata")
    .verifyComplete();

// assertEquals(1, attempts.get()) after verification.
~~~

In production, an async operation triggering side effects eagerly at method call time **without waiting for subscription** breaks lazy semantics. For example, `Mono.just(blockingCall())` runs `blockingCall()` immediately, whereas `Mono.fromCallable(() -> blockingCall())` defers it.

### 13.1. Deferred Fallback

~~~java
return primaryLookup()
    .switchIfEmpty(Mono.defer(() -> fallbackLookup()));
~~~

If `fallbackLookup()` has side effects when invoked to construct a `Publisher`, `Mono.defer` ensures it is only built when primary completes empty. Still, fallbacks must obey authorization policy—never a "fallback to admin."

## 14. Reactor `SecurityContext`: Do Not Use `ThreadLocal` Like Servlet

In Servlet, much code reads:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

In Reactive WebFlux, security propagates via **Reactor Context**, so prefer:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authentication =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication());
~~~

`ReactiveSecurityContextHolder.getContext()` can be `Mono.empty()` when no security context exists; handle missing `Authentication` per policy.

### 14.1. Why Can Context Be Lost?

- Calling `subscribe()` manually starts a new subscriber without the expected context.
- Using `CompletableFuture` or SDK callbacks without bridging context.
- Spawning a new thread and reading `SecurityContextHolder` `ThreadLocal`.
- Reading `Authentication` before security filters populate context.
- Background jobs lacking a request principal.
- Tests constructing sources under a different context or placing `contextWrite` in the wrong direction.

### 14.2. Switching Schedulers Does Not Automatically Lose Reactor Context

With properly composed Reactor publishers, context propagation flows across operators and schedulers. Do not assume `publishOn` loses `Authentication`; inspect **subscription boundaries** and where context is attached.

## 15. Unit Testing `ReactiveSecurityContextHolder` with `StepVerifier`

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    Mono<String> principalName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No security context")));
    }

    @Test
    void contextIsVisibleInsideReactiveChain() {
        Authentication auth = new TestingAuthenticationToken(
            "alice", "unused", "ROLE_USER");

        StepVerifier.create(
                principalName().contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(auth)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void missingContextIsNotTreatedAsAuthenticated() {
        StepVerifier.create(principalName())
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

This tests service-level context directly; it does not prove an ID Token was validly signed. `TestingAuthenticationToken` is purely a controlled test authentication.

### 15.1. `contextWrite` Placement Matters

Reactor Context propagates from **downstream subscriber to upstream**; placing `contextWrite` where it does not wrap the operation reading `Authentication` prevents that upstream branch from seeing the context.

Assuming every operator sees a global `ThreadLocal` user is the wrong mental model. When testing context, include both a negative path with **no `Authentication`** and a path with **another user/tenant's `Authentication`**.

### 15.2. Never Put Raw ID Tokens in Reactor Context

Context should hold framework-managed security context/principals and needed correlation/tracing metadata—never raw client secrets or Refresh Tokens for global convenience.

## 16. Testing Reactive Method Security

`@EnableReactiveMethodSecurity` enables reactive method security on eligible methods, e.g.:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class ReportService {

    private final ReactiveReportRepository repository;

    public ReportService(ReactiveReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('ROLE_REPORT_VIEWER')")
    public Mono<String> readReport(String reportId) {
        return repository.readContent(reportId);
    }
}
~~~

In a real app, method security must be enabled via `@EnableReactiveMethodSecurity` and methods must be invoked through the **Spring proxy** (self-invocation can bypass interceptors). On denial, tests should assert:

1. The publisher terminates with access denied, not a fallback allow.
2. The reactive repository is never subscribed to.
3. HTTP/WebFlux exception translation returns the right status for the authentication state.
4. Report contents never leak in error messages or logs.

### 16.1. Do Not Mix Return Types

If a method uses a blocking repository and returns `Mono.just(blockingCall())`, reactive method-security annotations do not eliminate the blocking call. Use a reactive repository or proper isolation.

### 16.2. Authorization Check Before Side Effects Inside Publishers

An easy pitfall: method assembly runs before the interceptor decides on subscription. To protect side effects, avoid executing them immediately upon method entry:

~~~java
// WRONG if invoked before authorization check.
public Mono<String> readReport(String id) {
    String content = jdbcRepo.loadReport(id); // side effect/blocking at assembly.
    return Mono.just(content);
}

// Safer for lazy semantics, though JDBC still needs scheduler isolation.
public Mono<String> readReport(String id) {
    return Mono.fromCallable(() -> jdbcRepo.loadReport(id))
        .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
}
~~~

## 17. `WebTestClient`: Testing the Security Filter Chain Without Manual Subscription

`WebTestClient` provides the test harness for WebFlux. With Spring Security Test, configure `springSecurity()` on `WebTestClient` and mock authentication of the right type.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
class OidcReactiveWebTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void authenticatedOidcUserCanReachProtectedPage() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/account")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Assume the application has a `GET /account` route that returns HTTP 200 when logged in with appropriate OIDC/authorization configuration. If the route does not exist or requires different authorities, update test expectations/fixtures to match the business contract.

### 17.1. What Does `mockOidcLogin()` Test?

It mocks an OIDC authenticated principal to verify:

- `SecurityWebFilterChain` and route authorization.
- Authorities and principal claims used by the application.
- Reactive SecurityContext propagation across handlers/services.
- Response/HTTP errors when a user is authenticated/unauthenticated.

It **does not actually perform** Authorization Code exchange, PKCE, ID Token signature/JWKS, UserInfo `sub` matching, or Token Endpoint HTTP calls. Those parts require protocol integration tests with a mock/test OP.

### 17.2. Anonymous Request Responses Can Differ

With an `oauth2Login()` browser flow, an unauthenticated request can commonly receive a **302 login redirect**; an API configured as bearer/resource-server may return **401**. Tests should not hardcode every anonymous request as 401 without accounting for `ServerAuthenticationEntryPoint` and the route.

### 17.3. Security Test Fixtures Must Only Be Built Properly Once

If a test uses `mockOidcLogin()` and then manually `subscribe()`s to a service under a different subscriber, Authentication may not propagate the way a WebTestClient request does. Assert via the HTTP exchange or use `StepVerifier` with an explicitly configured Reactor Context.

## 18. Mock Login Tests Differ From OIDC Protocol Integration Tests

A comprehensive test suite typically needs:

| Test layer | Goal | Executes OIDC protocol? |
| --- | --- | --- |
| Unit `StepVerifier` | Service context, signals, errors, cancellation | No |
| `PublisherProbe` | Whether downstream is subscribed | No |
| `BlockHound` JVM test | Blocking calls on non-blocking schedulers | No |
| `WebTestClient + mockOidcLogin` | Filter chain/routes/authorities | No |
| Mock OP integration | Authorization Code, PKCE, ID Token, JWKS, UserInfo | Yes, when fully set up |
| Browser E2E + Test OP | Redirect/callback/cookies/session | Yes |
| Load/perf test | Event-loop saturation and throughput | Depends on test system |

### 18.1. What Mock OP Tests Need to Verify

- Authorization request has the right `state`, code challenge, and issuer.
- Callback code/state is correlated with the session.
- Token Endpoint is not called twice due to duplicate subscription.
- ID Token signature/issuer/audience/nonce are verified.
- UserInfo `sub` matches ID Token.
- The newly authorized client is saved.
- The reactive chain does not call blocking APIs on the event loop.
- OIDC login result has the right authorities/session.

Do not use production user tokens/credentials in CI or test fixtures.

## 19. Testing Reactive `OAuth2AuthorizedClientManager`

A reactive client manager typically provides:

~~~java
Mono<OAuth2AuthorizedClient> authorizedClient =
    reactiveAuthorizedClientManager.authorize(authorizationRequest);
~~~

You must **return/compose** this Mono—do not call `subscribe()` inside a service and proceed with a token value that is not ready yet.

### 19.1. Counterexample: Access Token Not Yet Issued

~~~java
// WRONG: out-of-band subscription.
AtomicReference<OAuth2AuthorizedClient> ref =
    new AtomicReference<>();

manager.authorize(request).subscribe(ref::set);
OAuth2AuthorizedClient client = ref.get(); // May be null/race.
~~~

### 19.2. Composing Token Authorization with an API Call

~~~java
Mono<Report> loadReport(OAuth2AuthorizeRequest request) {
    return manager.authorize(request)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Authorized client unavailable")))
        .flatMap(client ->
            reportsGateway.fetchReport(client));
}
~~~

This is an **illustrative fragment** with `Report`, `reportsGateway`, and `manager` defined in the application. The gateway must send the Access Token to the right Resource Server/audience/scope over HTTPS; never log or return tokens to the frontend.

### 19.3. One Subscription per Refresh?

Not by default. If multiple requests subscribe concurrently when the Access Token expires, the manager/store may need concurrency protection. With Refresh Token rotation, two concurrent refreshes using the same token can cause `invalid_grant` and mistakenly delete the newer token.

Tests should simulate concurrent refresh, persistence versioning/CAS, and failure-handler cleanup; do not use a shared `Mono.cache()` across all principals to "solve" races, as that easily mixes user/tenant credentials.

### 19.4. Background Jobs Without `ServerWebExchange`

For scheduled jobs outside an HTTP exchange, consider `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with `ReactiveOAuth2AuthorizedClientService` and a stable application principal. Do not expect a WebSession-bound `ServerOAuth2AuthorizedClientRepository` to magically have a user session inside a background worker.

## 20. When an HTTP Request Is Canceled: Unknown Token Exchange Outcome

A timeout/cancellation can happen right while the Token Endpoint is processing:

~~~mermaid
sequenceDiagram
    participant App as Reactive OAuth2 Client
    participant OP as Authorization Server
    App->>OP: Refresh R1
    Note over App: Local timeout/cancel
    OP-->>App: A2 + R2 (response may not be received)
    App->>App: Store still has R1
    App->>OP: Retry R1
    OP-->>App: invalid_grant
~~~

This error does not necessarily prove an attacker stole the Refresh Token. Understand token rotation, persistence, and unknown outcomes. Blindly retrying after a timeout can break the entire token family.

### 20.1. Measure Cancellation Without Guessing the Remote Outcome

In tests, you can simulate an API using `Mono.never()` + `timeout`, record `CANCEL` events, and inspect connection state. Never conclude the remote server did nothing simply because the local publisher was canceled.

### 20.2. Never Auto-Retry Authorization Code Exchange

Authorization codes are typically single-use. A blanket `retryWhen` across all WebClient calls can resend the same code after a timeout and receive `invalid_grant`. For login, restarting the authorization flow safely is usually more appropriate than endlessly retrying an old code.

## 21. Testing HTTP 401/403: Fail-Closed Without Privilege Escalation

In a WebFlux OAuth2 Client, a Resource Server can return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

### 21.1. Important Assertions

- `401 invalid_token`: stale tokens can be cleaned up via an appropriate failure handler; do not automatically assume token theft.
- `403 insufficient_scope`: do not resend the request with machine admin client credentials to bypass it.
- Business 403: do not automatically delete the Refresh Token; verify tenant/ACL.
- API 503: do not continuously refresh Access Tokens to "fix API errors."
- Timeout: bound retries and maintain proper connection state.

### 21.2. Checking the WebClient Filter Failure Handler

`ServerOAuth2AuthorizedClientExchangeFilterFunction` attaches an authorized client's Access Token to WebClient requests. When initialized with `ReactiveClientRegistrationRepository` and `ServerOAuth2AuthorizedClientRepository`, it can provide default failure handling for Bearer errors where applicable. When initialized with `ReactiveOAuth2AuthorizedClientManager`, it **does not automatically include** a failure handler for Resource Server 401/403 responses; configure `setAuthorizationFailureHandler(...)` when you want stale-token cleanup driven by API responses.

Do not confuse the failure handler for **Token Endpoint authorization** with the failure handler for **Resource Server HTTP responses**.

### 21.3. Probing to Prevent API Calls After Denial

In tests, wrap gateway calls with `PublisherProbe` and require `assertWasNotSubscribed()` when the user lacks a role or tenant membership.

Checking HTTP status 403 alone is insufficient if the code already called the downstream API before returning forbidden.

## 22. Testing Custom Non-Blocking OIDC UserInfo Services

`ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` handles reactive OIDC user loading. When customizing it, delegate to Spring Security's reactive implementation, then apply business policy/claim mapping inside the pipeline.

An anti-pattern:

~~~java
// COUNTEREXAMPLE: synchronous HTTP client inside reactive mapping.
return delegate.loadUser(request)
    .map(user -> {
        String groups = restTemplate.getForObject(
            "https://directory.example.net/groups", String.class);
        return enrich(user, groups);
    });
~~~

This can block the event loop. Moreover, source URLs and Access Tokens must come from trusted config rather than request input, avoiding token exfiltration.

### 22.1. Using a Properly Configured WebClient

~~~java
return delegate.loadUser(request)
    .flatMap(user ->
        directoryGateway.fetchAllowedGroups(user)
            .map(groups -> enrich(user, groups)));
~~~

`directoryGateway` is a hypothetical reactive gateway; it must have:

- An Access Token with the right resource audience/scope per the provider contract.
- TLS/host allowlist, timeout/rate limit/backoff.
- No logging of raw groups/tokens/PII.
- Fail-closed policy if groups are used to grant permissions.
- No automatic role grants when the Directory API returns 503.

### 22.2. UserInfo `sub` Equality Must Not Be Skipped

If a custom service performs UserInfo HTTP calls itself, the `sub` claim in the response **must match** the `sub` in the ID Token **exactly**. Test both the happy path and mismatch; **do not use UserInfo claims on mismatch**.

### 22.3. BlockHound Does Not Test Business Logic

Even when a UserInfo gateway is non-blocking, it could still return another user's claims or arbitrarily map `admin` to `ROLE_ADMIN`. Protocol, identity, and authorization tests are still needed separately.

## 23. Testing Reactive Logout and Session Persistence

A WebFlux OIDC application may involve:

- RP `WebSession`.
- OP SSO session.
- `ReactiveOAuth2AuthorizedClientService`.
- OIDC Session Registry for Back-Channel Logout.
- Access/Refresh Tokens remaining at the OP or Resource Server.

### 23.1. Logout Publishers Must Be Composed

Counterexample:

~~~java
session.invalidate().subscribe(); // WRONG in a WebFilter/handler.
return Mono.empty();
~~~

Better:

~~~java
return session.invalidate()
    .then(auditService.recordLogout(userAlias));
~~~

Assume the audit service has its own policy and `recordLogout` returns `Mono<Void>`. If auditing fails, apply an explicit policy; do not arbitrarily swallow errors on a mandatory security event.

### 23.2. Subscription Audit for Back-Channel Logout

The OP sends a signed Logout Token server-to-server. The RP must verify the token, look up sessions by `sid`/`sub`, invalidate sessions via the reactive store, and **return the Mono to the request pipeline**, rather than calling `subscribe()` on session cleanup and returning 200 early.

Tests:

1. Invalid signature/issuer/audience/events -> do not delete sessions.
2. Valid `sid` -> invalidate only the matching session.
3. Session store fails -> error is observed/handled per contract, never returning fake success.
4. Cluster -> registry/session state takes effect across nodes.
5. Do not confuse the OP `sid` with the RP `SESSION` cookie.

### 23.3. Local Logout Does Not Mean Token Revocation

`removeAuthorizedClient(...)` in the store only deletes the local token record. RFC 7009 token revocation is a separate request to the OP. Tests should distinguish the two and never promise that local session invalidation has revoked every Access Token.

## 24. Subscriptions, Transactions, and Persistence

Reactive transactions often rely on **Reactor Context**. A detached child `subscribe()` may fail to participate in the request's transaction/security context.

### 24.1. Counterexample

~~~java
public Mono<Void> updatePermissions(UserId id) {
    roleRepository.saveRoles(id).subscribe();
    return auditRepository.recordRoleChange(id).then();
}
~~~

`saveRoles` and auditing can run independently, fail asynchronously, or execute in different transactions.

### 24.2. Composing in Order

~~~java
public Mono<Void> updatePermissions(UserId id) {
    return roleRepository.saveRoles(id)
        .then(auditRepository.recordRoleChange(id));
}
~~~

If business rules require atomicity, add store-appropriate reactive transaction management and `TransactionalOperator`. Do not assume blocking JDBC `@Transactional` automatically spans detached child subscriptions.

### 24.3. Multiple Database Operations

`Mono.when` runs multiple publishers concurrently; if ordering matters or authorization must precede writes, use `then`/`flatMap`/`concatMap`. If independent parallel reads are desired after authorization succeeds, evaluate bounded concurrency and context propagation.

## 25. Real-World Blocking Analysis Scenarios

### Scenario A — Slow OIDC Login When a User Belongs to Many Groups

A custom claims mapper invokes a synchronous Directory SDK and blocks the event loop.

**Symptoms:** event-loop latency spikes, request timeouts, CPU not necessarily high, throughput drops.

**Diagnosis:** BlockHound test with mock Directory SDK, thread dumps, scheduler metrics; inspect the UserInfo/authority enrichment path.

**Fix:** migrate to reactive HTTP/API or isolate temporarily on `boundedElastic`; bound concurrency and API permissions.

### Scenario B — Login Audits Vanish on Some Requests

`audit.save(...).subscribe()` runs fire-and-forget.

**Diagnosis:** `PublisherProbe` sees auditing is absent from the returned Mono; audit errors do not fail or alert on the request.

**Fix:** compose `audit.save(...).then(redirect())` or use a transactional outbox when asynchronous auditing is acceptable.

### Scenario C — API Called Even Though User Received 403

The code uses `Mono.when(authorize(), callApi())`.

**Diagnosis:** `PublisherProbe` on `callApi()` shows subscription happened before authorization failed.

**Fix:** `authorize().then(Mono.defer(() -> callApi()))` when authorization signals via complete/error; with `Mono<Boolean>`, use `flatMap` to inspect `false`.

### Scenario D — Empty `ReactiveSecurityContextHolder`

A service manually subscribes to a `Mono` from a web filter and reads the current user in the callback.

**Diagnosis:** `StepVerifier` with/without context, safe stage logging. Inspect subscription boundaries.

**Fix:** keep the pipeline composed, use `ReactiveSecurityContextHolder.getContext()`, and do not rely on Servlet `ThreadLocal`.

### Scenario E — Token Refresh Token Rotation Race

Two requests subscribe to the same old refresh source concurrently.

**Diagnosis:** mock token endpoint counts refresh requests, race tested via `TestPublisher` or controlled responses, versioned persistence.

**Fix:** per-user/registration single-flight, optimistic locking, and a failure handler that does not delete the newer token.

### Scenario F — `Mono.block()` in a Reactive Controller

A developer tries to fetch a token synchronously:

~~~java
// COUNTEREXAMPLE in event loop:
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

**Symptoms:** Reactor throws a blocking error or event-loop latency spikes; BlockHound may detect it.

**Fix:** `return manager.authorize(request).flatMap(client -> ...)`.

### Scenario G — Green Tests but Slow Production

BlockHound tests run on a JUnit thread not marked non-blocking; blocking JDBC goes undetected.

**Diagnosis:** run tests on `Schedulers.parallel()` / a BlockHound-instrumented WebFlux harness, supplemented by load tests and traces.

**Fix:** never treat a single smoke test as an absolute guarantee.

### Scenario H — Mock OIDC Login Passes but Real Callback Fails

`WebTestClient.mutateWith(mockOidcLogin())` skips Token Endpoint/PKCE/JWKS.

**Diagnosis:** protocol integration tests with a Test OP and browser callback.

**Fix:** keep unit/filter tests while adding full OIDC flow tests.

### Scenario I — WebFlux Logout Returns 200 Before Session Invalidated

A success handler manually subscribes to `session.invalidate()` and returns `Mono.empty()`.

**Diagnosis:** `PublisherProbe`, controlled delayed session store.

**Fix:** compose session invalidation into the returned `Mono<Void>` and check HTTP/OP logout semantics.

### Scenario J — Provider Timeout Wipes Tokens for All Users

An `onErrorResume` handles every error by calling `removeAuthorizedClient()`.

**Diagnosis:** `TestPublisher`/WebClient mock returning 503, verifying the authorized client store is not wiped.

**Fix:** distinguish transient timeouts/503 from permanent `invalid_grant`; apply bounded retries and preserve security state.

### Scenario K — JDBC Moved to `boundedElastic` Yet Still Bottlenecks

Thread pool/queue/DB connection counts are insufficient while every request executes long blocking queries.

**Diagnosis:** `boundedElastic` queue depth, DB pool latency, request backlog, thread dumps.

**Fix:** reduce blocking work, migrate to R2DBC or permitted caching, add bulkheads and timeouts.

### Scenario L — Claim Mapper Triggers Side Effects Before Authorization

`Mono.just(loadSensitiveGroupData())` runs as soon as the method is called, even when authorization later denies access.

**Diagnosis:** `AtomicInteger` counter checked before subscription, `PublisherProbe` negative test.

**Fix:** `Mono.defer`/`fromCallable` and proper authorization sequencing; do not read sensitive data before permission checks.

## 26. Layer-by-Layer Testing Checklist

| Layer | Question to answer | Tools |
| --- | --- | --- |
| Reactor semantics | Are publishers lazy, cold, and retried safely? | `StepVerifier`, counters |
| Subscription | Does a denied branch touch downstream? | `PublisherProbe` |
| Cancellation | When the client disconnects, does upstream cancel? | `TestPublisher`, `doFinally` |
| Blocking | Is there sleep/JDBC/sync SDK on non-blocking threads? | BlockHound, thread dumps |
| Scheduler | Is blocking isolated with bounded capacity? | Metrics, `boundedElastic` instrumentation |
| Security Context | Is Authentication in Reactor Context for the right user? | `StepVerifier.contextWrite` |
| Reactive method security | Does denial skip subscribing to the repository? | Method security + `PublisherProbe` |
| HTTP filter chain | Do anonymous/OIDC users get the right statuses? | `WebTestClient` |
| OIDC protocol | Are PKCE/ID Token/UserInfo validated for real? | Test OP + browser integration |
| Authorized client | Are token save/load and refresh race-free? | Mock provider + store |
| API | Are `invalid_token`/`insufficient_scope` handled right? | Mock Resource Server |
| Logout | Is session invalidation properly awaited? | Reactive session integration tests |
| Operations | Event-loop latency, retry storms, pool backlog? | Tracing/load tests |

## 27. Pre-Merge Production Code Checklist

1. Never call `Mono.block()`/`Flux.blockLast()` on the Netty event loop.
2. No stray `subscribe()` calls inside WebFilters, authentication managers, user services, authorized-client managers, controllers, or repositories.
3. Blocking libraries are replaced with reactive drivers or isolated within bounds on `boundedElastic`.
4. BlockHound tests run on non-blocking schedulers with proper JVM configuration.
5. Never whitelist BlockHound blocking calls broadly just to make tests pass.
6. Authorization decisions execute **before** protected downstream publishers.
7. Unauthorized branches have `PublisherProbe.assertWasNotSubscribed()`.
8. Publishers writing audit/session/authorized-client state are **composed** with an explicit error policy.
9. Reactive `SecurityContext` is read via `ReactiveSecurityContextHolder`, never relying on `ThreadLocal`.
10. Tests cover missing context, wrong user, wrong tenant, and missing role.
11. Timeout/cancellation tests never assume the remote operation did not occur.
12. One-time authorization codes and Refresh Token rotation cannot suffer accidental duplicate retries/subscriptions.
13. Success/failure handlers do not mistakenly delete a newer token after concurrent refresh.
14. UserInfo `sub` must match ID Token `sub` in protocol integration.
15. `WebTestClient.mockOidcLogin` is not mistaken for a real OIDC Token Endpoint test.
16. Never log ID/Access/Refresh Tokens, client secrets, codes, verifiers, or session cookies.
17. Token-bearing WebClients enforce trusted host/audience/scope allowlists rather than arbitrary URLs.
18. HTTP 401/403/503 responses are classified accurately without fail-open authorization.
19. Reactive transactions and `WebSession` persistence are never detached by manual subscriptions.
20. Monitoring tracks event-loop latency, scheduler backlog, provider timeouts, refresh failures, and audit failures.

## 28. Review Questions

**1. Why doesn't `Mono.just(jdbcRepository.load())` protect the event loop?**

Because `jdbcRepository.load()` executes immediately when constructing the Mono. Use a reactive repository or `Mono.fromCallable(...).subscribeOn(boundedElastic())` to defer and isolate the blocking operation when the driver cannot be replaced.

**2. Does BlockHound detect every blocking API?**

No. It instruments a set of blocking methods and detects when they execute on eligible non-blocking threads. It does not replace performance tests, code review, or context/subscription tests.

**3. Why shouldn't you call `subscribe()` inside `ServerAuthenticationSuccessHandler`?**

Because the framework already subscribes to the returned `Mono<Void>`. Manually subscribing creates a child stream whose errors/cancellation/context are hard to control and may return the response before audit/session persistence finishes.

**4. What does `PublisherProbe.assertWasNotSubscribed()` verify?**

It verifies that the protected downstream branch's publisher was never subscribed to, which helps prove authorization denial did not trigger an API call.

**5. Does placing `subscribeOn(boundedElastic())` after `Mono.just(blockingCall())` solve blocking?**

No. The blocking call already ran before `Mono.just` was created; the scheduler only affects a publisher when it is subscribed afterward.

**6. Does `Mono.when(authorize(), delete())` guarantee authorization happens before deletion?**

No. Publishers may be subscribed concurrently. For protected operations, enforce sequencing and explicit denial semantics, e.g., `authorize().then(Mono.defer(() -> delete()))`.

**7. Why can `SecurityContext` be lost when subscribing manually?**

Reactive `SecurityContext` lives in Reactor Context attached to the subscriber chain; a separate manual subscription does not automatically inherit the request's context.

**8. Does `mockOidcLogin()` prove ID Token signatures and nonces were validated?**

No. It mocks `Authentication` for HTTP/filter/authorization tests. Full protocol coverage requires testing against an OP with callbacks/tokens/JWKS/UserInfo.

**9. Does a timeout during refresh prove the provider did not rotate the Refresh Token?**

No. The OP may have processed the request even though the client never received the response. Retrying the old token can yield `invalid_grant` or invalidate the token family.

**10. Why test cancellation in logout flows?**

Because if an HTTP request is canceled or a handler returns early, session cleanup/auditing might remain incomplete. The returned publisher must manage completion and an appropriate error policy.

## 29. References

- Reactor — Reference Guide, Schedulers and Threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Reactor — Reference Guide, Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor — Testing Reactor (`StepVerifier`, `TestPublisher`, `PublisherProbe`): https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor — BlockHound repository/documentation: https://github.com/reactor/BlockHound
- Spring Security — Reactive Architecture: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Reactive Testing: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- Spring Security — WebTestClient Security Test Support: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — `ReactiveSecurityContextHolder` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Framework — WebFlux Reference: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Data R2DBC — Reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

## 30. Summary: Proper Reactive Security Requires Controlling the Execution Lifecycle

~~~text
HTTP request
   |
   v
Spring Security WebFlux
   |
   +-- Reactive Authentication / OIDC Login
   +-- Reactive Authorization / Method Security
   +-- OAuth2 Authorized Client Manager
   |
   v
Compose one Publisher graph
   |
   +-- Lazy source: Mono.defer / fromCallable
   +-- Non-blocking I/O or boundedElastic if mandatory
   +-- SecurityContext in Reactor Context
   +-- Authorization before protected side effects
   +-- Correct error, cancellation, timeout handling
   |
   v
Spring WebFlux runtime subscribes
   |
   +-- StepVerifier checks signals
   +-- PublisherProbe checks branch subscription
   +-- TestPublisher checks cancellation
   +-- BlockHound detects blocking on non-blocking threads
   +-- WebTestClient checks filter/security boundaries
   +-- Test OP checks real OIDC protocol
~~~

**Six principles to remember:**

1. **Blocking in WebFlux is dangerous even when Authentication is right.** Look for JDBC, synchronous HTTP SDKs, `Thread.sleep`, and `block()` inside custom OIDC/security services; use BlockHound and load/latency telemetry to detect them.
2. **Never manually subscribe inside request/security services.** Return and compose `Mono`/`Flux` so the framework owns error, cancellation, context, and persistence lifecycles.
3. **Authorization must happen before protected operations.** `PublisherProbe` should prove the denied path does not subscribe to the API/repository; `Mono.when` is not a substitute for sequencing.
4. **`ReactiveSecurityContextHolder` belongs to Reactor Context.** Never rely on Servlet `ThreadLocal`; test context under the right subscriber and across missing/wrong Authentication branches.
5. **Timeouts/cancellations and concurrent subscriptions can trigger security side effects.** Especially single-use authorization codes, Refresh Token rotation, revocation, and logout; apply idempotency/conditional persistence and protocol-aligned retry policies.
6. **Multi-layer testing is necessary for confidence.** BlockHound, `StepVerifier`, `TestPublisher`, `WebTestClient`, and mock OIDC Login catch different classes of bugs; you still need OP/JWKS/UserInfo tests and multi-instance testing.

The ultimate goal is not merely getting WebFlux to return HTTP 200, but **ensuring every security decision triggers only authorized operations, in the right execution context, without blocking the event loop and without spawning subscriptions outside system control**.
