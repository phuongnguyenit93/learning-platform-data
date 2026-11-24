# StepVerifier for ReactiveAuthenticationManager and Mono Branches

## 1. Objectives and Scope

In Spring Security **WebFlux**, the `ReactiveAuthenticationManager` interface receives an `Authentication` object representing an authentication request and returns `Mono<Authentication>`. When testing this component, calling `authenticate(...)` and merely doing `assertNotNull(mono)` is **insufficient**: a `Mono` represents an asynchronous computation that requires subscribing to observe signals. **Reactor Test**'s `StepVerifier` lets you precisely verify `onSubscribe`, `onNext`, `onComplete`, `onError`, cancellation, timing, and fallback behavior.

This lesson focuses on the **contract and Mono branches of an authentication manager**, then extends to real Spring Security tests. The primary target is Spring Security 6.5.x / Spring Boot 3.x / Java 17+ with Reactor 3.x; Gradle configuration examples assume a project with an appropriate plugin/BOM.

### Learning outcomes

1. Distinguish **`Mono.just(authentication)`**, **`Mono.empty()`**, and **`Mono.error(exception)`** per the `ReactiveAuthenticationManager` contract.
2. Use `StepVerifier.create(...)` to verify successful login, `isAuthenticated()` status, principal/authorities/credentials, and exactly one emitted item.
3. Verify rejection branches with `expectError(...)` and `expectErrorSatisfies(...)` without swallowing `AuthenticationException`.
4. Use `PublisherProbe` for fallbacks between managers, distinguishing empty from error; never treat empty as invalid password automatically.
5. Test cold publishers, multi-subscription behavior, timeouts, virtual time, cancellation, and Reactor Context.
6. Compare **manager unit/component tests** with **`WebTestClient` security filter chain tests** so you do not confuse `Mono` results with HTTP 401/403 or `SecurityContext` state.
7. Avoid hanging tests, blocking calls, virtual scheduler mismatches, unsubscribed publishers, missing completion assertions, or mocks hiding real logic.

**Boundary:** `ReactiveAuthenticationManager` belongs to the **WebFlux** stack; Servlet uses synchronous `AuthenticationManager`. `StepVerifier` cannot replace `WebTestClient`, JWT signature/key integration tests, or real database/concurrency tests.

## 2. Exact Contract of ReactiveAuthenticationManager

API:

~~~java
package org.springframework.security.authentication;

@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

The signature above is **only a pedagogical abbreviation** (excluding imports), not a new Java file to create. Spring Security describes three outcomes:

| Signal | Mono response | Manager meaning | StepVerifier assertion |
| --- | --- | --- | --- |
| **Success** | `onNext(authenticated Authentication)` then `onComplete` | Manager verified credentials and returned `Authentication` | `assertNext(...)` + `verifyComplete()` |
| **Abstain** | `onComplete` only, no `onNext` | Manager cannot authenticate this request type / makes no decision | `verifyComplete()` immediately, or `expectNextCount(0).verifyComplete()` |
| **Failure** | `onError(AuthenticationException)` | Manager accepted the request yet authentication failed | `expectError(BadCredentialsException.class).verify()` |
| **Non-terminating** | Neither completes nor errors, e.g., `Mono.never()` | Publisher may hang due to dependency/logic bug | Test timeout/cancel, never wait indefinitely |

**Decision point:** `Mono.empty()` **does not mean** "wrong password"; it means the manager produced no decision. In a multi-manager chain, empty may allow trying the next manager. Once a manager handles username/password and credentials are wrong, it should normally emit `Mono.error(new BadCredentialsException(...))` so execution does not fall through to a weaker handler.

**A `Mono<Authentication>` may emit at most one item**, because it is a `Mono`. Success results must satisfy `auth.isAuthenticated() == true` and contain principal/authorities per policy. An `Authentication` with `isAuthenticated=false` emitted via `Mono.just(...)` is an item signal, **not automatically equivalent to successful authentication**; tests must inspect properties.

### Visual signal flow

~~~text
Test code calls manager.authenticate(request)
                    |
                    v
             Mono<Authentication>
                    |
              StepVerifier
                 subscribe
                    |
        +-----------+-------------+
        |           |             |
       onNext     onComplete      onError
   Authentication  (no value)   AuthenticationException
        |
     onComplete

Mono.just(authentication)  = onNext -> onComplete
Mono.empty()               = onComplete
Mono.error(exception)      = onError
Mono.never()               = no terminal event
~~~

**There is no `Mono.just(null)`** in Reactor: `null` is not a valid `onNext`. When a branch has no `Authentication`, use `Mono.empty()` as intended, or `Mono.error(...)` if credentials are rejected. Never return `null` instead of a `Mono`; that violates the contract and can blow up with `NullPointerException` when the caller subscribes.

## 3. Dependencies and File Layout

In a Spring Boot 3.x project already configured with the Spring Boot plugin and dependency management/BOM, add these dependencies to `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

- `spring-boot-starter-webflux` brings Reactor/WebFlux into the app; avoid accidentally adding `spring-boot-starter-web` and assuming the app runs reactive HTTP: when both starters are present, Spring Boot may default to MVC unless the application type is configured.
- `spring-boot-starter-security` provides `ReactiveAuthenticationManager`, `Authentication`, and tokens/exceptions.
- `reactor-test` provides `StepVerifier`, `PublisherProbe`, and `VirtualTimeScheduler`. This is a **test-scope** dependency.
- `spring-boot-starter-test` typically includes JUnit Jupiter and Spring/AssertJ test utilities. Use consistent BOM versions; do not manually mix incompatible Reactor 3.x versions with Boot.
- `spring-security-test` helps with `WebTestClient` and `mockUser`/JWT mocks at the web layer; it does not make a manager authenticate on its own in unit tests.

The main example in Section 4 is **one complete JUnit class**, whose filename must match `ReactiveAuthenticationManagerStepVerifierTest.java`, placed at `src/test/java/example/`. It runs with `./gradlew test --tests "example.ReactiveAuthenticationManagerStepVerifierTest"` given the Gradle wrapper and dependencies above. No database connection or Spring `ApplicationContext` is needed because these are unit/component tests.

## 4. Complete JUnit 5 Suite: Success, Empty, and Error

### 4.1. Dedicated fake manager for unit tests

We create an implementation that accepts only `UsernamePasswordAuthenticationToken`. User `alice` with demo password `correct-password` succeeds; any other username/password returns a generic `BadCredentialsException`; any other token type returns `Mono.empty()`.

**This is a test double for contract testing, not an authentication implementation permitted in production.** The demo code compares raw password strings to simplify the branch, uses **no** password encoder, reads no user database, and has no brute-force protection. Every real app needs `PasswordEncoder`, a user store, and full policies.

### 4.2. Runnable JUnit Java file

~~~java
package example;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveAuthenticationManagerStepVerifierTest {

    private static Authentication login(String username, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            username, password);
    }

    private static Authentication ignoredTokenType() {
        return new AnonymousAuthenticationToken(
            "test-key", "anonymous",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private static Authentication authenticated(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username, null,
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static ReactiveAuthenticationManager sampleManager(
            AtomicInteger subscriptionCount) {

        return request -> Mono.defer(() -> {
            subscriptionCount.incrementAndGet();

            // A manager that does not support this Authentication type
            // must return Mono.empty() rather than silently accepting credentials.
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            String name = request.getName();
            Object credentials = request.getCredentials();
            if ("alice".equals(name)
                    && "correct-password".equals(credentials)) {
                return Mono.just(authenticated("alice"));
            }

            // Test double: any username/password mismatch
            // uses a generic error. Production uses a user store
            // and PasswordEncoder, never plaintext comparison.
            return Mono.error(
                new BadCredentialsException("Invalid credentials"));
        });
    }

    @Test
    void successfulAuthenticationEmitsOneAuthenticatedValueAndCompletes() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(
                login("alice", "correct-password")))
            .assertNext(value -> {
                assertTrue(value.isAuthenticated());
                assertEquals("alice", value.getName());
                assertNull(value.getCredentials());
                assertTrue(value.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void invalidCredentialsProduceAuthenticationErrorNotEmptyCompletion() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(
                login("alice", "incorrect")))
            .expectErrorSatisfies(error -> {
                assertInstanceOf(BadCredentialsException.class, error);
            })
            .verify();
    }

    @Test
    void unknownUsernameAlsoFailsWithGenericAuthenticationError() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(
                login("unknown", "correct-password")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unsupportedTokenTypeCompletesEmptyWithoutAuthenticationValue() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(ignoredTokenType()))
            .verifyComplete();
    }

    @Test
    void coldMonoDefersWorkUntilSubscription() {
        var count = new AtomicInteger();
        var manager = sampleManager(count);

        Mono<Authentication> result =
            manager.authenticate(login("alice", "correct-password"));

        assertEquals(0, count.get());

        StepVerifier.create(result)
            .expectNextMatches(Authentication::isAuthenticated)
            .verifyComplete();
        assertEquals(1, count.get());

        // Resubscribing re-executes the Mono.defer source in the test double.
        StepVerifier.create(result)
            .expectNextCount(1)
            .verifyComplete();
        assertEquals(2, count.get());
    }

    @Test
    void emptyResultCanTriggerFallbackToSecondManager() {
        var first = sampleManager(new AtomicInteger());
        PublisherProbe<Authentication> fallback = PublisherProbe.of(
            Mono.just(authenticated("fallback-user")));

        Mono<Authentication> result =
            first.authenticate(ignoredTokenType())
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
            .assertNext(value -> {
                assertTrue(value.isAuthenticated());
                assertEquals("fallback-user", value.getName());
            })
            .verifyComplete();

        fallback.assertWasSubscribed();
    }

    @Test
    void errorDoesNotTriggerSwitchIfEmptyFallback() {
        var first = sampleManager(new AtomicInteger());
        PublisherProbe<Authentication> fallback = PublisherProbe.of(
            Mono.just(authenticated("fallback-user")));

        Mono<Authentication> result =
            first.authenticate(login("alice", "wrong"))
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
            .expectError(BadCredentialsException.class)
            .verify();

        fallback.assertWasNotSubscribed();
    }

    @Test
    void virtualTimeTestsDelayedAuthenticationWithoutRealWaiting() {
        ReactiveAuthenticationManager delayed = request ->
            Mono.delay(Duration.ofMinutes(5))
                .map(tick -> authenticated("alice"));

        StepVerifier.withVirtualTime(() -> delayed.authenticate(
                login("alice", "correct-password")))
            .expectSubscription()
            .expectNoEvent(Duration.ofMinutes(5))
            .assertNext(value -> {
                assertTrue(value.isAuthenticated());
                assertEquals("alice", value.getName());
            })
            .verifyComplete();
    }

    @Test
    void timeoutErrorIsASeparateBranchFromWrongPassword() {
        ReactiveAuthenticationManager stalled =
            request -> Mono.never();

        StepVerifier.withVirtualTime(() ->
                stalled.authenticate(login("alice", "correct-password"))
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void cancellationNotifiesPublisher() {
        var cancelled = new AtomicBoolean(false);

        ReactiveAuthenticationManager pending = request ->
            Mono.<Authentication>never()
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(pending.authenticate(
                login("alice", "correct-password")))
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }
}
~~~

### 4.3. Interpreting each test's expectations accurately

- `successfulAuthentication...` requires **one `onNext`** containing an authenticated `Authentication`, principal Alice, erased credentials, and `ROLE_USER`, followed by `onComplete`. If the manager returns `Mono.empty()`, `assertNext` fails.
- `invalidCredentials...` requires `onError(BadCredentialsException)`. If the manager returns empty to hide the error, the test fails. This enforces the policy "bad credentials must not fall back".
- `unknownUsername...` ensures the test double creates no special message branch for nonexistent usernames; this is not yet an HTTP timing/user-enumeration test.
- `unsupportedTokenType...` requires completion **with zero items**. `verifyComplete()` as the first step catches any unexpected `onNext`; `expectNextCount(0)` is unnecessary.
- `coldMono...` uses `Mono.defer` so it increments the counter **on subscribe**, not when calling `authenticate`. Resubscribing runs the source again. **Do not** assume every real manager is idempotent: if a source has side effects, two subscriptions can cause two lookups or token issuances.
- `PublisherProbe` lets you assert whether the fallback branch was subscribed, stronger than checking output alone; `switchIfEmpty` falls back only when upstream **completes empty**, never on `onError`.
- `virtualTime...` creates `Mono.delay` **inside the `Supplier`** passed to `withVirtualTime`; the virtual scheduler replaces the default scheduler before the publisher is assembled.
- `timeout...` shows that `TimeoutException` is a system/timeout error, not `BadCredentialsException`. The application can translate it into a transient error (e.g., 503) rather than returning 401 wrong password.
- `cancellation...` cancels a non-terminating source and checks that the cancel signal fires. Cancellation does not prove every driver immediately aborts in-flight network/DB work.

**Output:** the tests print nothing to `System.out`; success means the JUnit runner marks them passing. Never fabricate fixed `./gradlew test` stdout since it depends on Gradle version and logging configuration. The sample tests use JUnit Jupiter `@Test` and all imports are included in the file.

### 4.4. Run commands

~~~bash
./gradlew test --tests "example.ReactiveAuthenticationManagerStepVerifierTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.ReactiveAuthenticationManagerStepVerifierTest"
~~~

This test suite **does not need `@SpringBootTest`**, avoiding the overhead of building an application context; that is the core benefit of component tests checking `Mono` signals. If you need integration tests with the Spring Security filter chain, see Section 9.

## 5. Testing a Real Manager Using ReactiveUserDetailsService

The test double above helps clarify the contract, yet it does not prove Spring Security's `UserDetailsRepositoryReactiveAuthenticationManager` works with a password encoder, account status, and user store. To test the real manager with a **test-only in-memory user store**, create `src/test/java/example/RealReactiveUserDetailsManagerTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealReactiveUserDetailsManagerTest {

    private UserDetailsRepositoryReactiveAuthenticationManager manager() {
        var user = User.withUsername("alice")
            // {noop} is acceptable only in test examples, never in production.
            .password("{noop}correct-password")
            .roles("USER")
            .build();

        var users = new MapReactiveUserDetailsService(user);
        return new UserDetailsRepositoryReactiveAuthenticationManager(users);
    }

    @Test
    void authenticatesExistingUserWithCorrectPassword() {
        var input = UsernamePasswordAuthenticationToken
            .unauthenticated("alice", "correct-password");

        StepVerifier.create(manager().authenticate(input))
            .assertNext(authentication -> {
                assertTrue(authentication.isAuthenticated());
                assertEquals("alice", authentication.getName());
            })
            .verifyComplete();
    }

    @Test
    void rejectsWrongPassword() {
        var input = UsernamePasswordAuthenticationToken
            .unauthenticated("alice", "wrong-password");

        StepVerifier.create(manager().authenticate(input))
            .expectError(AuthenticationException.class)
            .verify();
    }
}
~~~

**Why use `expectError(AuthenticationException.class)` instead of asserting the message?** The API may use specific subclasses or change message text across versions/configurations to avoid leaking details. Authentication behavior tests should focus on the **contract exception type**, not hardcoding unguaranteed English strings.

In Spring Security 6.5, `UserDetailsRepositoryReactiveAuthenticationManager` extends `AbstractUserDetailsReactiveAuthenticationManager` and uses `ReactiveUserDetailsService`. The default password encoder supports the `{id}encodedPassword` format via `DelegatingPasswordEncoder`. `{noop}` is only to keep tests simple; production requires bcrypt/argon2/scrypt/PBKDF2 or an appropriately chosen password scheme with safe hash management.

**Never create production account credentials with `{noop}`**, never hardcode real passwords in tests/logs, and never store plaintext passwords in the database.

Run command:

~~~bash
./gradlew test --tests "example.RealReactiveUserDetailsManagerTest"
~~~

If your project uses a reactive `UserDetailsService` backed by R2DBC/LDAP/custom RPC, replace `MapReactiveUserDetailsService` with a test double or test container with controlled latency and errors. Still keep one unit suite for the contract and a separate integration suite to verify interactions, deadlocks, schedulers, transactions, and load.

## 6. Fallbacks Across Multiple ReactiveAuthenticationManagers: Empty vs Error

An architecture may support multiple credential mechanisms (JWT, opaque token, username/password, custom). The first manager returns empty when it **does not support the `Authentication` type**, letting another manager try. A manager that accepted the request yet failed verification typically emits `AuthenticationException` to block falling back to a weaker method.

~~~text
authentication request
     |
     v
manager A.authenticate(request)
     |-- onNext(auth) + complete ---> SUCCESS
     |-- complete empty ----------> try manager B (per chain/policy)
     |-- onError(AuthException) ---> FAIL, no default fallback
     |
     v
manager B.authenticate(request)
     |-- onNext(auth) + complete ---> SUCCESS
     |-- complete empty ----------> no manager handled it
     |-- onError(...) ------------> FAIL
~~~

In Reactor, `switchIfEmpty(alternative)` is a great illustration tool; **however, do not hand-roll authentication chains in production when the framework already provides `DelegatingReactiveAuthenticationManager`** unless you thoroughly understand its semantics, ordering, and auditing. In Spring Security 6.3+, `DelegatingReactiveAuthenticationManager` has `setContinueOnError(boolean)`, defaulting to `false`. Setting `true` lets the next manager try even after an earlier error, so check your threat model—especially downgrade/bypass risks. Never conflate "did not handle" with "authentication failed".

### PublisherProbe verifies which branch was subscribed

Two tests in Section 4 demonstrate:

- `Mono.empty().switchIfEmpty(probe.mono())` → fallback **is subscribed**.
- `Mono.error(BadCredentialsException).switchIfEmpty(probe.mono())` → fallback **is not subscribed**.

If you assert only the success result without checking `PublisherProbe`, a test might still pass even if the fallback always runs or triggers unintended side effects. `PublisherProbe.assertWasSubscribed()` and `assertWasNotSubscribed()` catch this. You can also use `assertWasRequested()` and `assertWasCancelled()` when verifying demand and cancellation.

### When to use onErrorResume?

~~~java
// NOT RECOMMENDED: turns bad credentials into empty,
// creating an opportunity to fall through to a weaker auth branch downstream.
Mono<Authentication> unsafe =
    manager.authenticate(request)
           .onErrorResume(BadCredentialsException.class,
                          error -> Mono.empty());
~~~

This is a **snippet** inside a class that already has `manager` and `request`; it is not standalone code. Turning credential errors into an empty completion is a **security semantic change** that requires review. You can use `onErrorMap` to convert infrastructure errors into a compatible operational error or `doOnError` to record redacted metrics; never use `onErrorResume` recklessly just to make tests pass.

Unexpected `IllegalStateException`, DB timeouts, or network failures must never be silently turned into "wrong password"; classify them so the server returns safe public info while operations receive accurate reasons.

## 7. Virtual Time, Timeouts, Cancellation, and Test Determinism

`StepVerifier.withVirtualTime(Supplier<Publisher<T>>)` lets you test `Mono.delay`, `timeout`, `retryWhen`, and `delayElement` without real sleeps.

**Rule:** construct the publisher **inside the supplier** after the virtual scheduler is activated. This is required for the virtual clock to take effect.

~~~java
// RIGHT: delay is created when the Supplier is invoked
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(5))
    .expectNext(0L)
    .verifyComplete();
~~~

~~~java
// AVOID: building the publisher too early and returning it
Mono<Long> delayed = Mono.delay(Duration.ofMinutes(5));
StepVerifier.withVirtualTime(() -> delayed)
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(5))
    .expectNext(0L)
    .verifyComplete();
~~~

The second snippet **has no guarantee that virtual time works as intended**, because the scheduler may have already been captured before `StepVerifier` installs the virtual scheduler. It illustrates an anti-pattern and should not be run as a real test.

### expectSubscription() before expectNoEvent()

`expectNoEvent(Duration)` treats **subscription itself as an event**. Putting `expectNoEvent` first can fail immediately on the subscription signal. Correct sequence:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

`thenAwait(duration)` merely advances time/waits **without asserting no earlier `onNext` occurred**; `expectNoEvent(duration)` is the stronger assertion when verifying no early signals arrived.

### Testing timeouts without hanging CI

- When the source is intentionally `Mono.never()`, you must include `thenCancel()` or `timeout(...)`. `StepVerifier.create(Mono.never()).verifyComplete()` will hang since there is no terminal event.
- For component tests not using virtual time, pass a finite timeout to `verify(Duration.ofSeconds(3))` or use framework timeouts; never allow infinite hangs.
- `TimeoutException` is not automatically an `AuthenticationException`. At the HTTP layer, infrastructure/timeout errors should be classified and return an appropriate public response (e.g., 503) rather than conflating them with 401.
- When a manager uses a **separately injected scheduler** instead of Reactor's default `Schedulers` factory, virtual time cannot automatically replace all schedulers; inject a matching `VirtualTimeScheduler` into the code under test or use a short, stable real test timeout.
- `Mono.delay`/Schedulers in virtual tests differ from running real external IdPs, bcrypt, Redis, and JDBC concurrently. Never claim virtual time alone proves real-world SLA limits.

### Testing cancellation and side effects

`StepVerifier.create(publisher).thenCancel().verify()` guarantees the subscriber emits cancel. If the producer already started a non-cancellable DB request, external effects may still complete; tests must verify whether **business effects** (token revocation, OTP issuance, login attempt increments) are idempotent and transactionally protected. Never treat cancellation as proof that all external operations rolled back.

## 8. Reactor Context and ReactiveSecurityContextHolder

`ReactiveAuthenticationManager.authenticate(...)` returns `Mono<Authentication>`; that **does not by itself prove** WebFlux stored the `Authentication` in `SecurityContext`. In WebFlux, `ReactiveSecurityContextHolder` reads `SecurityContext` from **Reactor Context**, not the Servlet ThreadLocal `SecurityContextHolder`.

A dedicated test can verify `SecurityContext` propagation in a reactive chain; **it does not test the manager**, it tests context wiring:

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    @Test
    void authenticationIsReadFromReactorContext() {
        var auth = UsernamePasswordAuthenticationToken.authenticated(
            "alice", null,
            List.of(new SimpleGrantedAuthority("ROLE_USER")));

        Mono<String> name =
            ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName())
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(auth));

        StepVerifier.create(name)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void withoutContextThereIsNoSecurityContextValue() {
        Mono<String> name =
            ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());

        StepVerifier.create(name)
            .verifyComplete();
    }
}
~~~

With `ReactiveSecurityContextHolder.getContext()`, if no context is set, the `Mono` can complete empty as shown in the example. When integrating method security, place `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))` **at the right point** in the reactive composition and verify the service method receives the expected `Authentication`. **Never use ThreadLocal `SecurityContextHolder` to infer identity inside a stream hopping across threads**; Reactor Context belongs to the subscriber chain.

In a properly configured WebFlux app, security filters are responsible for putting `Authentication`/`SecurityContext` into context for downstream handlers. Unit tests calling the manager directly do not prove that.

## 9. Component Tests vs WebTestClient: Testing at the Right Layer

| What to verify | Primary tool | Why |
| --- | --- | --- |
| Manager returns right `onNext`/`onComplete`/`onError` | `StepVerifier` | Directly observes the Publisher contract |
| Password encoder/`ReactiveUserDetailsService` | `StepVerifier` + real manager | No need to boot an HTTP server |
| Whether second manager branch is called | `PublisherProbe` / Mockito verify | Distinguishes fallback from error |
| Timeout/backoff/delay | `withVirtualTime` / controlled scheduler | Fast tests, no sleeps |
| Reactive `SecurityContext` | `StepVerifier` + `ReactiveSecurityContextHolder` | Subscription-scoped context |
| HTTP Basic/WebFlux login returns 401 or 302? | `WebTestClient` + `SecurityWebFilterChain` | Status/challenge/redirect belong to filters |
| Real JWT validates signature, `iss`, `aud` | Integration with decoder/keys/test IdP | Mock auth does not prove cryptographic validation |
| Cookies, CSRF, anonymous vs authenticated HTTP | `WebTestClient` + `spring-security-test` | Tests client behavior |
| Event loop stays non-blocking under load | Integration/load/blocking detector | `StepVerifier` unit tests alone do not prove non-blocking |

### WebTestClient snippet (not a standalone test class)

This snippet assumes a `WebTestClient client` bound to an `ApplicationContext` or WebFlux server, a `SecurityWebFilterChain` protecting `/api/private`, and HTTP Basic configured:

~~~java
client.get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isUnauthorized();

// Wrong credentials go through the HTTP Basic filter and manager:
client.get()
      .uri("/api/private")
      .headers(headers -> headers.setBasicAuth("alice", "wrong"))
      .exchange()
      .expectStatus().isUnauthorized();
~~~

On authentication success, you can assert 200 on a specific endpoint when the account has permission; if lacking a role, an authenticated request may return 403. **Never assume a fixed status solely because the manager emitted `Mono.empty()`**: the HTTP entry point, error handler, method security, and policy define the response.

Using `mockUser()` or `mockJwt()`/JWT test post-processors **simulates `SecurityContext`/`Authentication`** without verifying passwords, signatures, or invoking the full manager. Use the right test type so "green tests" do not skip real mechanisms.

### Catching unexpected bugs

A `StepVerifier` unit test can pass because a mock always returns `Mono.just(authenticated)` while real code fails on lookup or timing; keep at least one test suite with a real manager (Section 5) and one with HTTP filters. You do not need a Spring context in every test: favor fast signal-contract tests and place integration tests at real boundaries.

## 10. Common Mistakes When Testing ReactiveAuthenticationManager

1. **Asserting only that `Mono` is non-null:** without subscribing, logic inside `Mono.defer`/cold publishers never runs. Use `StepVerifier.create(...)`.
2. **Confusing `Mono.empty()` with wrong password:** empty = manager abstained; wrong password is normally `Mono.error(AuthenticationException)`.
3. **Using `expectNextCount(1)` without checking `isAuthenticated`:** an emitted `Authentication` might still be unauthenticated.
4. **Using `expectErrorMessage("...")` on unstable internal exceptions:** tests break when framework/localization strings change. Prefer type and policy.
5. **Using `expectNext(...)` without `verifyComplete()`:** misses publishers that emit trailing errors or never complete.
6. **Calling `.block()` in WebFlux production code:** can block the event loop; blocking only on the verifier thread inside tests is valid. `StepVerifier` does not require `.block()`.
7. **Using `onErrorResume(... -> Mono.empty())` to "fix" tests:** easily turns authentication failures into fallbacks/downgrades.
8. **Constructing `Mono.delay` before `withVirtualTime`:** virtual scheduler does not take effect as expected.
9. **Placing `expectNoEvent` before subscription:** subscription counts as an event and fails the test.
10. **Not bounding verify timeouts on potentially hanging sources:** hangs CI indefinitely. Use explicit timeouts/cancellations.
11. **Assuming cancel rolls back external side effects:** subscriber cancellation is not an IdP/DB transaction rollback.
12. **Treating Servlet `SecurityContextHolder` as Reactor Context:** leads to leaks or lost identity across thread switches.
13. **Stubbing Mockito only for the happy path:** misses testing ordering, fallbacks, auth errors, and real managers.
14. **Omitting negative tests for disabled/locked users:** must emit `AuthenticationException` or enforce policy, never emit an authenticated `Authentication`.
15. **Letting a manager support every token type:** risks processing mismatched tokens through weak credential checks; enforce empty or error branches per policy.
16. **Failing to separate authentication and authorization:** a manager returning an authenticated `Authentication` does not guarantee the request has sufficient scope/roles in `AuthorizationWebFilter`.
17. **Turning runtime/timeout errors into `BadCredentialsException`:** clients get a misleading 401 and ops misses outages.
18. **Creating a new `Authentication` that still holds a raw password in credentials:** avoid keeping raw credentials in results and logs; tests can assert `getCredentials()==null` per design.

## 11. Self-Assessment Checklist

- [ ] All three branches `Mono.just(authenticated)` / `Mono.empty()` / `Mono.error(AuthenticationException)` have separate `StepVerifier` tests.
- [ ] Success tests check principal, `isAuthenticated`, authorities, credential handling, single item, and completion.
- [ ] Wrong credentials never become empty/fallback; exact `AuthenticationException` type is asserted.
- [ ] Unsupported authentication types are tested to never produce an authenticated user.
- [ ] `PublisherProbe` proves the fallback branch subscribes only on empty.
- [ ] Cold/resubscribe behavior is tested and side effects are reviewed.
- [ ] Virtual time builds publishers inside the `Supplier`, avoiding sleeps; timeout and cancellation tests have terminal conditions.
- [ ] Unexpected infrastructure failures are not misreported as bad credentials.
- [ ] Reactive `SecurityContext` is tested via Reactor Context; Servlet ThreadLocal is not misused.
- [ ] At least one component test uses a real manager and test user store, not mocks alone.
- [ ] `WebTestClient` integration tests cover HTTP statuses, headers, CSRF, and JWT/password flows as applicable.
- [ ] Tests are independent, hardcode no production secrets, and never log credentials or tokens.

**Takeaway:** `StepVerifier` tests **Publisher signals**. For `ReactiveAuthenticationManager`, success is an authenticated `Authentication` followed by completion; "not handled" is an empty completion; invalid credentials is an error. Separating these three branches prevents unsafe fallbacks and produces unit tests that reflect real authentication behavior.

## 12. Official Documentation

- Spring Security 6.5 — `ReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security 6.5 — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Reactive method security and Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security — `DelegatingReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html
- Project Reactor — Testing with `StepVerifier` / `PublisherProbe` / Virtual Time: https://projectreactor.io/docs/core/release/reference/testing.html
- Project Reactor — `StepVerifier` API: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
