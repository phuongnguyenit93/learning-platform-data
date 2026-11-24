# StepVerifier and Testing Publishers Containing Security Decisions

## 1. Why unit testing a single boolean is not enough

In **Spring Security reactive** and **Project Reactor**, authorization logic is commonly represented as a `Mono<AuthorizationResult>`, `Mono<Boolean>`, `Mono<Void>`, or a `Flux` performing per-resource permission checks. The decision is not always available immediately when the method is called; it may arrive after a membership database query, after a timeout, or emit no value at all.

A serious authorization test must be able to answer these questions:

- Was an **allow** decision actually emitted, or did the publisher just emit `Mono.empty()` and complete?
- On a **deny** decision, are you sure the branch that loads sensitive data was never subscribed to?
- If the permission database returns an error, does the request **fail closed**, or does it accidentally turn the error into a granted permission?
- Has the publisher been subscribed to yet? Did the call that creates the `Mono` execute the query yet?
- If the client disconnects while waiting for authorization, does upstream receive `cancel()` and release resources?
- Does the identity from `ReactiveSecurityContextHolder` follow the right subscriber?
- When `@PreAuthorize` denies access, should the test expect `AuthorizationDecision(false)` or `AccessDeniedException`?
- Can policy timeout/TTL be tested using virtual time without waiting in real time?
- Does a `mockJwt()` test prove that the JWT signature was verified?

After this lesson, you will be able to use **StepVerifier**, **TestPublisher**, **PublisherProbe**, **StepVerifierOptions**, and Spring Security reactive test APIs to test allow/deny/empty/error/cancel branches, Reactor Context, backpressure, time, and side effects. There is a **Java 17+ Maven project** with minimal production code and a JUnit Jupiter test suite as a working example.

**Principle:** A passing test only asserts what it actually checks. `StepVerifier` checks publisher signals; it does not automatically verify JWT/IdP, AOP proxies, HTTP 401/403, or data ownership if those layers are not included in the test.

## 2. Reactive Streams: signal order is part of the security contract

~~~text
Caller gets Publisher                  Actual subscription
       |                                       |
       |  Mono<AuthorizationResult>            |
       |-------------------------------------->| onSubscribe
       |                                       | request(n)
       |                                       |
       |                      +----------------+---------------+
       |                      |                |               |
       |                    onNext           onComplete      onError
       |                   decision          (0 value)      exception
       |                      |
       |                  onComplete
       |
       | Client may cancel at any point after onSubscribe
       +--------------------------------------> cancel()
~~~

A `Publisher` is typically **lazy**. Calling `manager.authorize(auth, resource)` only builds a plan; `onSubscribe`/`request` is what triggers processing. The key distinctions:

| Publisher | Signal | Security meaning |
| --- | --- | --- |
| `Mono.just(new AuthorizationDecision(true))` | onNext(true) then onComplete | Manager grants access |
| `Mono.just(new AuthorizationDecision(false))` | onNext(false) then onComplete | Manager denies access |
| `Mono.empty()` | onComplete **without onNext** | No decision/abstain, not equivalent to allow |
| `Mono.error(ex)` | onError, without onNext | Infrastructure error or a layer actively denying |
| `Mono<Void>` completes | onComplete | May be `verify` allowing access |
| `Mono<Void>` errors with `AccessDeniedException` | onError | May be `verify` denying access |
| `Mono.never()` | Does not emit, does not terminate | Check hangs if there is no timeout/cancel |
| `Flux<AuthorizationResult>` | Multiple onNext | Each event/resource can have its own decision |
| Subscription cancelled | cancel() | Processing no longer needed; upstream must clean up |

**Do not confuse Boolean false with an empty publisher.** An operator like `filter(Boolean::booleanValue)` can turn `Mono.just(false)` into `Mono.empty()` and wipe out the deny information. If the caller uses `switchIfEmpty(Mono.just(true))`, that bug can become a vulnerability.

### 2.1. Spring Security 7.x APIs to know

`ReactiveAuthorizationManager<T>` uses these methods:

~~~java
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication, T object);

Mono<Void> verify(
        Mono<Authentication> authentication, T object);
~~~

These are **abbreviated signatures from the Javadoc**, not classes you need to define yourself. `AuthorizationResult` provides `isGranted()`; `AuthorizationDecision` is the common implementation with a constructor taking `boolean`. `authorize` can return a decision or empty if it cannot decide. `verify` completes when access is granted and emits an `AccessDeniedException` error when denied.

Older documentation/versions have `check(Mono<Authentication>, T)` or the synchronous `AuthorizationManager<T>` API taking `Supplier<Authentication>`. With Spring Security 6.4+/7.x, when writing new code, use `authorize` and the proper reactive interface. Do not mistakenly copy the non-reactive Servlet/method-interceptor `AuthorizationManager` into `ReactiveAuthorizationManager`.

### 2.2. Three layers with different outcomes

~~~text
manager.authorize(...):
  allow -> emit AuthorizationResult(true)
  deny  -> emit AuthorizationResult(false)
  empty -> emit no decision
  error -> emit error

manager.verify(...):
  allow -> Mono<Void> completes
  deny  -> emits AccessDeniedException

proxied @PreAuthorize Spring method:
  allow -> business Publisher executes
  deny  -> emits AccessDeniedException before business result
~~~

Therefore, **direct manager tests** should check `result.isGranted()`; **verify/AOP tests** should check completion or error. Do not write `expectError(...)` for an `authorize` method designed to return `AuthorizationDecision(false)`.

## 3. StepVerifier: writing a scenario against actual signals

~~~java
// Snippets inside a test method with Spring Security and reactor-test imports.
Mono<AuthorizationResult> allow =
        Mono.just(new AuthorizationDecision(true));
StepVerifier.create(allow)
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();

Mono<AuthorizationResult> deny =
        Mono.just(new AuthorizationDecision(false));
StepVerifier.create(deny)
        .expectNextMatches(r -> !r.isGranted())
        .verifyComplete();

StepVerifier.create(Mono.<AuthorizationResult>empty())
        .verifyComplete();

StepVerifier.create(
        Mono.<AuthorizationResult>error(
                new AccessDeniedException("denied")))
        .expectError(AccessDeniedException.class)
        .verify();
~~~

These four scenarios are **not the same**. In the allow test, `expectNextMatches(...)` forces a value to be received. If you replace it with only `verifyComplete()`, `Mono.empty()` also passes even though access was never granted.

### 3.1. Methods to use with the right semantics

| API | What it verifies |
| --- | --- |
| `StepVerifier.create(publisher)` | Scenario starting from subscription |
| `expectSubscription()` | Must receive onSubscribe |
| `expectNext(value)` | Exact onNext value |
| `expectNextMatches(predicate)` | Predicate on an onNext matches |
| `assertNext(consumer)` | Custom assertions for the object |
| `expectNextCount(n)` | There are n values, regardless of content |
| `verifyComplete()` | Completes with no unexpected signals |
| `expectError(type).verify()` | Publisher emits an error of the required type |
| `expectErrorMatches(predicate).verify()` | Error has the expected cause/type |
| `then(action)` | Emit test signals or inspect state at a specific step |
| `thenRequest(n)` | Increase demand after subscription |
| `thenCancel().verify()` | Test cancelling the subscription |
| `expectNoEvent(duration)` | No signals within the interval |
| `withVirtualTime(() -> publisher)` | Use virtual scheduler for timed operators |
| `expectAccessibleContext()` | Reactor Context exists and contains expected entries |
| `verifyThenAssertThat()` | Post-verification assertions on state, dropped/discarded elements |
| `StepVerifierOptions.scenarioName(...)` | Name the scenario to aid debugging |

**You must call** `verify()` or a shortcut that executes verification. Simply chaining `expectNext(...)` without calling verify **does not subscribe** to the Publisher and proves nothing.

### 3.2. StepVerifier completing is different from authorize succeeding

~~~java
// ANTI-PATTERN: if manager returns Mono.empty, the test still passes.
StepVerifier.create(manager.authorize(auth, resource))
        .verifyComplete();
~~~

If the goal is allow:

~~~java
StepVerifier.create(manager.authorize(auth, resource))
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
~~~

If the goal is deny:

~~~java
StepVerifier.create(manager.authorize(auth, resource))
        .expectNextMatches(decision -> !decision.isGranted())
        .verifyComplete();
~~~

If the goal is **abstain** per the contract, `verifyComplete()` without `expectNext` is appropriate. In a compositional security policy, downstream must know how to handle abstain; never assume abstain means permit.

## 4. Test case problem: read a report only when scope and membership match

Suppose we have a resource `ReportRequest(tenant, reportId)`. The user must:

1. Be authenticated.
2. Have the `SCOPE_reports.read` authority.
3. Have membership in the report's tenant, verified by a reactive permission service.
4. Only after allow is granted may the publisher loading the report be **subscribed to**.

A membership source may return:

~~~text
membership.belongs("alice", "tenant-a"):
  Mono.just(true)   -> allow if scope matches
  Mono.just(false)  -> deny
  Mono.empty()      -> deny by default per application policy
  Mono.error(...)   -> fail closed, do not load data
  Mono.never()      -> timeout/cancel, do not wait indefinitely
~~~

Diagram:

~~~text
HTTP / verified Authentication
       |
       v
ReactiveAuthorizationManager<ReportRequest>
       |   has SCOPE_reports.read ?
       +--- no -------> AuthorizationDecision(false)
       |
       +--- yes ------> membership.belongs(user, tenant)
                              |
                     true  / false / empty / error
                              |
                    allow / deny / deny / error
                              |
              +---------------+----------------+
              |                                |
            allow                        deny/error
              |                                |
              v                                v
    subscribe repository               NOT subscribe repository
    return sensitive body               emit error / translate status
~~~

Asserting only HTTP 403 without asserting that the repository was not subscribed to is incomplete. The repository might have already read/cached/logged private rows **before** the controller ultimately returned 403.

## 5. Java 17+ Maven project to study and run tests yourself

Structure:

~~~text
reactive-authz-test/
  pom.xml
  src/main/java/com/example/authz/ReportSecurity.java
  src/test/java/com/example/authz/ReportSecurityTest.java
~~~

The project uses the **Spring Boot 4.1.2** BOM to manage Spring Security/Reactor, **Java 17+**, JUnit Jupiter, `reactor-test`, and requires no IdP or HTTP server. Credentials in the unit tests are **mock authentication**, not real JWTs. The project tests the Publisher and service composition directly; HTTP/Method Security integration is covered in later sections.

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-authz-test</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`reactor-test` is a test-only dependency and **must not** be placed in production runtime just to use `StepVerifier`. With the Boot BOM, do not force Spring Security 5.x into the same project when the code uses 7.x `AuthorizationResult` and `authorize`.

### 5.2. ReportSecurity.java — application code

Create `src/main/java/com/example/authz/ReportSecurity.java`:

~~~java
package com.example.authz;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

public final class ReportSecurity {

    private ReportSecurity() {}

    public record ReportRequest(String tenant, String reportId) {}

    @FunctionalInterface
    public interface Membership {
        Mono<Boolean> belongs(String userName, String tenant);
    }

    public static final class ReportAuthorizationManager
            implements ReactiveAuthorizationManager<ReportRequest> {

        private final Membership membership;

        public ReportAuthorizationManager(Membership membership) {
            this.membership = membership;
        }

        @Override
        public Mono<AuthorizationResult> authorize(
                Mono<Authentication> authentication,
                ReportRequest request) {

            return Mono.defer(() -> authentication
                    .filter(Authentication::isAuthenticated)
                    .flatMap(auth -> {
                        boolean hasScope = auth.getAuthorities()
                                .stream()
                                .anyMatch(a -> "SCOPE_reports.read"
                                        .equals(a.getAuthority()));
                        if (!hasScope) {
                            return Mono.just((AuthorizationResult)
                                    new AuthorizationDecision(false));
                        }
                        return membership
                                .belongs(auth.getName(), request.tenant())
                                // Missing membership -> explicit deny.
                                .defaultIfEmpty(false)
                                .map(value -> (AuthorizationResult)
                                        new AuthorizationDecision(value));
                    })
                    // Missing Authentication -> explicit deny.
                    .defaultIfEmpty(new AuthorizationDecision(false)));
        }
    }

    public static Mono<String> secureRead(
            Mono<Authentication> authentication,
            ReportRequest request,
            ReactiveAuthorizationManager<ReportRequest> manager,
            Mono<String> repository) {

        return Mono.defer(() -> manager
                .authorize(authentication, request)
                // An external manager may abstain.
                .defaultIfEmpty(new AuthorizationDecision(false))
                .flatMap(decision -> decision.isGranted()
                        ? repository
                        : Mono.error(new AccessDeniedException(
                                "Report access denied"))));
    }
}
~~~

**Design rationale:** when the scope is missing, the membership store **is not called**. When there is no Authentication or no membership record, `defaultIfEmpty` produces an explicit deny. When the membership service errors, the publisher propagates the error without granting access. When denied, `secureRead` does not subscribe to `repository`. `Mono.defer` ensures each new subscription triggers the authorize path.

**Limitations:** this code does not verify JWT issuer/audience and does not check object ownership; those belong to the authentication/resource layer and actual business authorization. The membership store must protect tenants and check the true user from a verified identity, not trust an unverified HTTP `X-User-Id` header value.

### 5.3. ReportSecurityTest.java — full JUnit class

Create `src/test/java/com/example/authz/ReportSecurityTest.java`:

~~~java
package com.example.authz;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static com.example.authz.ReportSecurity.*;

class ReportSecurityTest {

    private static final ReportRequest REQUEST =
            new ReportRequest("tenant-a", "report-7");

    private static Authentication auth(String name, String... scopes) {
        List<GrantedAuthority> authorities = Set.of(scopes)
                .stream()
                .map(SimpleGrantedAuthority::new)
                .map(a -> (GrantedAuthority) a)
                .toList();
        return UsernamePasswordAuthenticationToken.authenticated(
                name, "unused", authorities);
    }

    private static ReportAuthorizationManager manager(boolean allowed) {
        return new ReportAuthorizationManager(
                (name, tenant) -> Mono.just(allowed));
    }

    @Test
    void grantsWhenScopeAndMembershipMatch() {
        StepVerifier.create(manager(true).authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectNextMatches(AuthorizationResult::isGranted)
                .verifyComplete();
    }

    @Test
    void deniesWhenMembershipIsFalse() {
        StepVerifier.create(manager(false).authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }

    @Test
    void skipsMembershipLookupWhenScopeMissing() {
        AtomicInteger calls = new AtomicInteger();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> {
                    calls.incrementAndGet();
                    return Mono.just(true);
                });

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_other")), REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();

        assertEquals(0, calls.get());
    }

    @Test
    void missingAuthenticationIsDenied() {
        StepVerifier.create(
                        manager(true).authorize(Mono.empty(), REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }

    @Test
    void emptyMembershipMeansDeny() {
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> Mono.empty());

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }

    @Test
    void verifyCompletesOnAllow() {
        StepVerifier.create(manager(true).verify(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .verifyComplete();
    }

    @Test
    void verifyErrorsOnDeny() {
        StepVerifier.create(manager(false).verify(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void repositoryNotSubscribedAfterDeny() {
        PublisherProbe<String> repository =
                PublisherProbe.of(Mono.just("PRIVATE_REPORT"));

        StepVerifier.create(secureRead(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST,
                        manager(false),
                        repository.mono()))
                .expectError(AccessDeniedException.class)
                .verify();

        repository.assertWasNotSubscribed();
        repository.assertWasNotRequested();
    }

    @Test
    void repositorySubscribedOnlyWhenAllowed() {
        PublisherProbe<String> repository =
                PublisherProbe.of(Mono.just("SAFE_REPORT"));

        StepVerifier.create(secureRead(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST,
                        manager(true),
                        repository.mono()))
                .expectNext("SAFE_REPORT")
                .verifyComplete();

        repository.assertWasSubscribed();
        repository.assertWasRequested();
    }

    @Test
    void permissionStoreErrorFailsClosed() {
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> Mono.error(
                        new IllegalStateException("permission store down")));
        PublisherProbe<String> repository =
                PublisherProbe.of(Mono.just("PRIVATE_REPORT"));

        StepVerifier.create(secureRead(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST, manager, repository.mono()))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && error.getMessage().contains("store down"))
                .verify();

        repository.assertWasNotSubscribed();
    }

    @Test
    void workStartsOnlyOnSubscription() {
        AtomicInteger count = new AtomicInteger();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> Mono.defer(() -> {
                    count.incrementAndGet();
                    return Mono.just(true);
                }));

        Mono<AuthorizationResult> publisher = manager.authorize(
                Mono.just(auth("alice", "SCOPE_reports.read")),
                REQUEST);

        assertEquals(0, count.get());

        StepVerifier.create(publisher)
                .expectNextMatches(AuthorizationResult::isGranted)
                .verifyComplete();

        assertEquals(1, count.get());
    }

    @Test
    void testPublisherControlsAsyncDenial() {
        TestPublisher<Boolean> permissions = TestPublisher.create();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> permissions.mono());

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .then(() -> permissions.next(false).complete())
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();

        permissions.assertWasSubscribed();
    }

    @Test
    void cancellationCancelsPendingPermissionCheck() {
        TestPublisher<Boolean> permissions = TestPublisher.create();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> permissions.mono());

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectSubscription()
                .then(permissions::assertSubscribers)
                .thenCancel()
                .verify();

        permissions.assertCancelled();
    }

    @Test
    void reactiveSecurityContextHasSubscriberIdentity() {
        Authentication alice = auth("alice", "SCOPE_reports.read");
        Mono<String> name =
                ReactiveSecurityContextHolder.getContext()
                        .map(SecurityContext::getAuthentication)
                        .map(Authentication::getName);

        StepVerifier.create(name.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(alice)))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(name)
                .verifyComplete();
    }

    @Test
    void initialContextCanBeVerified() {
        Mono<String> trace = Mono.deferContextual(ctx ->
                Mono.just((String) ctx.get("traceId")));

        StepVerifier.create(trace,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("traceId", "test-42")))
                .expectAccessibleContext()
                .contains("traceId", "test-42")
                .then()
                .expectNext("test-42")
                .verifyComplete();
    }

    @Test
    void virtualTimeTestsDelayedDecision() {
        StepVerifier.withVirtualTime(() ->
                        Mono.delay(Duration.ofMinutes(5))
                                .map(tick -> (AuthorizationResult)
                                        new org.springframework.security
                                                .authorization
                                                .AuthorizationDecision(false)))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(5))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }
}
~~~

### 5.4. Running tests and expectations

In the project directory containing `pom.xml`, run:

~~~bash
mvn test
~~~

Or if the Maven wrapper has been generated:

~~~bash
./mvnw test
~~~

Maven will run the JUnit Jupiter tests. **Do not claim the result of a build that has not actually been run.** Detailed Surefire logs depend on JDK, Maven, and plugin versions; do not copy a fake "BUILD SUCCESS" stdout sample and treat it as proof.

When a test fails, read **expected signal vs actual signal**. If an allow test receives `onComplete` without `onNext`, the cause may be that the manager returned `Mono.empty()`, not that the test should be relaxed to `verifyComplete()`. If a deny test receives `onError` instead of `AuthorizationDecision(false)`, determine whether the test is calling `authorize`, `verify`, or an intercepted method.

## 6. Important security assertions in the project

### 6.1. Allow requires a true result, not just completion

~~~java
StepVerifier.create(manager.authorize(auth, REQUEST))
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
~~~

If the publisher is empty, this test fails. That is what distinguishes it from testing `verifyComplete()` alone.

### 6.2. Deny before any side effect

~~~java
PublisherProbe<String> repository =
        PublisherProbe.of(Mono.just("SECRET"));

StepVerifier.create(
        ReportSecurity.secureRead(
                authentication, REQUEST, denyManager,
                repository.mono()))
        .expectError(AccessDeniedException.class)
        .verify();

repository.assertWasNotSubscribed();
~~~

**PublisherProbe** records whether the source was subscribed to/requested/cancelled. It does not automatically know if data was already read in an eager constructor; you must ensure the real repository adapter uses a lazy/reactive API.

### 6.3. A method call alone does not run the Mono

~~~java
Mono<AuthorizationResult> decision =
        manager.authorize(authentication, REQUEST);

// Does not mean the permission database has been queried yet.
// Subscription is what triggers execution:
StepVerifier.create(decision)
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
~~~

If a developer replaces `Mono.defer` with an eager `Mono.just(expensiveLoad())`, the side effect may run **before** StepVerifier subscribes. Laziness tests and probes help uncover this risk.

### 6.4. Errors must not be turned into allow

~~~java
// ANTI-PATTERN:
return membershipStore.belongs(user, tenant)
        .onErrorReturn(true);
~~~

Granting access when the permission store is unavailable is fail-open. It is better to propagate the error so the application refuses to emit data, and then map the appropriate HTTP status (possibly 5xx for an infrastructure outage). Do not misreport an infrastructure error as "expired token".

### 6.5. Missing Authentication and missing membership

`Mono.empty()` from the authentication source can mean unauthenticated or that a component could not decide; in the **sample policy**, it must deny. `Mono.empty()` from the membership store means no record was found, so it also denies. Do not assume every `ReactiveAuthorizationManager` implementation shares the same fallback: composite managers have specific "abstain" semantics that must be tested at the composition layer.

## 7. Testing PublisherProbe for fallback branches and resource cleanup

Some publishers return `Mono<Void>`, so there is no `onNext` to tell whether they ran. `PublisherProbe.empty()` helps verify subscription:

~~~java
PublisherProbe<Void> auditProbe = PublisherProbe.empty();

Mono<Void> result = Mono.<Void>empty()
        .switchIfEmpty(auditProbe.mono());

StepVerifier.create(result)
        .verifyComplete();

auditProbe.assertWasSubscribed();
auditProbe.assertWasRequested();
~~~

In the code above, `Mono.<Void>empty()` is the source, so `switchIfEmpty` switches to `auditProbe`. However, when testing a security workflow, be careful: a fallback on no-decision **must not automatically execute a protected action**. Use probes for expected cleanup/audit branches, and do not let them become a bypass rule.

### 7.1. Eager side effects escaping PublisherProbe

~~~java
// Wrong: expensiveRead() runs immediately before authorize.
Mono<String> result = Mono.just(expensiveRead());
return secureRead(auth, REQUEST, manager, result);
~~~

With blocking I/O sources, this also blocks Netty if created inside a controller. Better to use a reactive adapter and defer side effects:

~~~java
Mono<String> result =
        Mono.defer(() -> reactiveRepository.readReport("report-7"));
return secureRead(auth, REQUEST, manager, result);
~~~

This is a snippet assuming `reactiveRepository` exists; it is not a standalone runnable file. `PublisherProbe.assertWasNotSubscribed()` + a spy repository together verify **no data access before the decision**.

### 7.2. When denied vs when permission store errors

| Case | Manager | Repository |
| --- | --- | --- |
| membership false | Emit `AuthorizationDecision(false)` | Not subscribed |
| membership empty | Explicit deny in sample app | Not subscribed |
| membership error | OnError, do not allow | Not subscribed |
| authentication empty | Deny in sample app | Not subscribed |
| scope missing | Deny, membership not called | Not subscribed |
| member true/scope valid | Grant true | Subscribed once if no retry |

When the backend needs a transaction, ensure the transaction is opened **after** authorization or rolled back on deny, and do not let sensitive data be written to caches/logs before the check.

## 8. TestPublisher: controlling races, errors, and cancellation

`TestPublisher<T>` is a test source that can manually emit `next(...)`, `complete()`, `error(ex)`, along with `assertSubscribers`/`assertCancelled`. It is well suited when the permission store has not responded yet and you want to control the exact timing.

~~~java
TestPublisher<Boolean> permissions = TestPublisher.create();

Mono<AuthorizationResult> decision =
        new ReportAuthorizationManager(
                (user, tenant) -> permissions.mono())
                .authorize(authentication, REQUEST);

StepVerifier.create(decision)
        .then(() -> permissions.next(false).complete())
        .expectNextMatches(r -> !r.isGranted())
        .verifyComplete();

permissions.assertWasSubscribed();
~~~

### 8.1. Why emit signals inside then(...)?

`TestPublisher.create()` is typically **hot**. If you call `permissions.next(false)` **before** `StepVerifier` subscribes to the source, the event may never reach the subscriber, causing the test to hang or see empty. Put `then(...)` after `StepVerifier` has started the subscription.

### 8.2. Cancellation when permission has not returned yet

~~~java
TestPublisher<Boolean> permissions = TestPublisher.create();

StepVerifier.create(
        new ReportAuthorizationManager(
                (user, tenant) -> permissions.mono())
            .authorize(authentication, REQUEST))
        .expectSubscription()
        .then(permissions::assertSubscribers)
        .thenCancel()
        .verify();

permissions.assertCancelled();
~~~

When an HTTP client disconnects, a pending permission query should not hold resources indefinitely. Testing cancellation at the source alone is not enough to prove real DB driver/SDK cleanup; integration tests must verify actual connections/listeners/transactions.

### 8.3. Is a network error a deny result?

If the backend policy service returns `Mono.error(new TimeoutException(...))`, the manager may emit an error rather than `AuthorizationDecision(false)`. In a fail-closed design, **do not emit protected data**. The API layer can map outages to 503/500 (and alert) instead of masking them as 401/403; status choice depends on the contract, and it never means grant.

### 8.4. Noncompliant TestPublisher

`TestPublisher.createNoncompliant(...)` creates a publisher that intentionally violates Reactive Streams rules to test operator adapters against non-standard sources. Use it only for specialized resilience tests; never treat a noncompliant stream emitting multiple onNext signals as normal contract behavior for `Mono<AuthorizationResult>`.

## 9. ReactiveSecurityContextHolder and StepVerifier

In Spring Security reactive, identity travels via the **Reactor Context**, not a global `ThreadLocal`. When unit-testing logic that reads the principal:

~~~java
Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_reports.read")));

Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

StepVerifier.create(name.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();
~~~

This is a snippet inside a test with the appropriate imports. Without `contextWrite(...)` in a plain unit test, `getContext()` may have no security context. The Spring WebFlux Security filter sets up the context automatically for authenticated HTTP subscriptions; unit tests outside HTTP must establish the context explicitly.

### 9.1. Verifying two subscribers do not mix users

~~~java
Mono<String> who = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

StepVerifier.create(who.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();

StepVerifier.create(who.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
        .expectNext("bob")
        .verifyComplete();
~~~

If a service stores the user in a static field, one request can overwrite another. Test two subscribers as a baseline as above, and add concurrent tests when scheduler transitions or external callbacks are involved. Do not assume `publishOn` by itself drops Reactor Context: in a standard Reactor pipeline, Context follows the subscriber; the real risk is usually **splitting the subscription** with an ad-hoc `subscribe()` or non-Reactor code that does not propagate context.

### 9.2. StepVerifierOptions and expectAccessibleContext

~~~java
Mono<String> trace = Mono.deferContextual(ctx ->
        Mono.just((String) ctx.get("traceId")));

StepVerifier.create(trace,
                StepVerifierOptions.create()
                        .scenarioName("reactor-context")
                        .withInitialContext(
                                Context.of("traceId", "test-42")))
        .expectAccessibleContext()
        .contains("traceId", "test-42")
        .then()
        .expectNext("test-42")
        .verifyComplete();
~~~

`expectAccessibleContext()` proves context propagation, **not that tenant/issuer has been verified**. A `tenant-a` value placed into the context by the client remains untrusted if the application has not verified membership or the token.

### 9.3. @WithMockUser and reactive method security

`@WithMockUser` from Spring Security Test can populate SecurityContext in tests with Spring test integration. For **reactive method security**, Spring Security documentation mentions `ReactorContextTestExecutionListener` to populate `ReactiveSecurityContextHolder` properly. A plain JUnit test with only the annotation and without the right listener/Context may not see the Authentication inside the reactive pipeline.

For unit tests, explicit `contextWrite(...)` is easy to understand. For AOP/WebFlux integration tests, configure Spring Security Test properly and avoid mixing Servlet ThreadLocal `SecurityContextHolder` with Reactor Context.

## 10. Method security @PreAuthorize must be tested through the Spring proxy

Spring Security reactive supports `@EnableReactiveMethodSecurity` and `@PreAuthorize` on methods returning `Mono`/`Flux`. For example:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfig {
}

@Service
class ReportsService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<String> read() {
        return Mono.just("SAFE_REPORT");
    }
}
~~~

This is a **snippet inside a Spring application**, requiring the proper imports and AOP/method-security dependencies. What you must test is not calling `new ReportsService().read()`, but calling the **Spring-injected bean proxy**.

~~~java
Mono<String> allowed = reportsService.read().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(reader));

StepVerifier.create(allowed)
        .expectNext("SAFE_REPORT")
        .verifyComplete();

Mono<String> denied = reportsService.read().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(noScopeUser));

StepVerifier.create(denied)
        .expectError(AccessDeniedException.class)
        .verify();
~~~

**Difference:** a `@PreAuthorize` denial typically emits **AccessDeniedException** from the interceptor. A unit test for `manager.authorize` denial in this lesson's project only returns a false decision. You must test the right layer.

### 10.1. Self-invocation bypass

If bean A calls `this.securedMethod()` internally, the Spring AOP proxy may not intercept that call. A test calling the proxy method directly does not prove the self-invocation path is protected. When methods call each other in practice, test the HTTP/service call graph or extract the secured method into another bean. Do not treat `@PreAuthorize` as a decorative annotation and skip testing the AOP route.

### 10.2. Policies returning Mono<Boolean> in SpEL

Spring Security supports referencing an authorization bean via SpEL, which can return `Mono<Boolean>`:

~~~java
@PreAuthorize("@reportPolicy.allowed(#tenant)")
public Mono<String> readForTenant(String tenant) {
    return reactiveRepository.readForTenant(tenant);
}
~~~

`reportPolicy.allowed(...)` is a custom method provided by the application. When testing, verify the policy publisher returning true/false/empty/error and verify how the AOP proxy handles it. Current Spring Security documentation states that empty can represent abstain in custom authorization logic; **do not rely on empty to grant access**. For sensitive business rules, fail closed explicitly.

## 11. Virtual time for timeouts and delayed decisions

### 11.1. withVirtualTime requires building the Publisher inside the Supplier

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(5))
                .map(tick -> new AuthorizationDecision(false)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(5))
        .expectNextMatches(result -> !result.isGranted())
        .verifyComplete();
~~~

`withVirtualTime` replaces the scheduler of Reactor timed operators so you do not have to wait 5 real minutes. The lambda must **create the source after the virtual scheduler is activated**. Anti-pattern:

~~~java
// Source created too early; virtual scheduler may not be used.
Mono<Long> delayed = Mono.delay(Duration.ofMinutes(5));
StepVerifier.withVirtualTime(() -> delayed)
        .thenAwait(Duration.ofMinutes(5))
        .expectNext(0L)
        .verifyComplete();
~~~

In this case the source may capture the real scheduler, causing the test to wait a long time or hang. Always create the timed source inside the Supplier and avoid mixing in uncontrolled custom schedulers.

### 11.2. expectNoEvent counts subscription as well

`expectNoEvent(Duration)` checks that no signal occurs during the interval. `onSubscribe` also counts as a signal, so:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(30)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(30))
        .expectNext(0L)
        .verifyComplete();
~~~

Put `expectSubscription()` before asserting no events.

### 11.3. VirtualTimeScheduler does not advance the JVM Clock

If expiration code uses `Instant.now()`, advancing the virtual scheduler does not make the JVM clock jump forward. When testing JWT `exp` or stream leases, inject a `Clock`:

~~~java
Instant expiration = Instant.parse("2026-11-07T00:00:10Z");
Clock clock = Clock.fixed(
        Instant.parse("2026-11-07T00:00:11Z"), ZoneOffset.UTC);
boolean expired = !Instant.now(clock).isBefore(expiration);
~~~

This snippet requires `java.time.Clock/Instant/ZoneOffset` imports. Virtual time controls `Mono.delay`/`Flux.interval`; `Clock` controls **policy wall time**. You may need both to test expiration without depending on CI machine speed.

### 11.4. Bounding an infinite permission check

~~~java
Mono<AuthorizationResult> bounded =
        manager.authorize(authentication, request)
                .timeout(Duration.ofSeconds(2));
~~~

If the check does not complete, the publisher errors with a timeout. Do not use `onErrorResume(ex -> Mono.just(new AuthorizationDecision(true)))`, because that is fail-open. The HTTP layer should set appropriate deadlines/circuit breakers and infrastructure error statuses. If testing timeout on a virtual scheduler, ensure all involved operators use the injected scheduler.

## 12. Cancellation and backpressure

### 12.1. thenCancel to test a non-completing source

~~~java
TestPublisher<Boolean> pending = TestPublisher.create();

StepVerifier.create(pending.mono())
        .expectSubscription()
        .thenCancel()
        .verify();

pending.assertCancelled();
~~~

Cancellation is **not** `onError` or `onComplete`. If a pending query was already dispatched to an external SDK, the test must verify the SDK/resource is cleaned up on cancel; operators like `doFinally(SignalType.CANCEL)` or `usingWhen` can help with cleanup.

### 12.2. Testing request(n) according to demand

~~~java
StepVerifier.create(
                Flux.just("grant-a", "grant-b"),
                StepVerifierOptions.create().initialRequest(0))
        .expectSubscription()
        .thenRequest(1)
        .expectNext("grant-a")
        .thenRequest(1)
        .expectNext("grant-b")
        .verifyComplete();
~~~

A publisher must not emit `onNext` when downstream has not requested it. A per-item authorization `Flux` may run during streaming; test backpressure when permission checks interact with broker data to avoid unbounded buffers and cross-tenant events.

### 12.3. Per-event/resource decisions

~~~java
Flux<Event> secured = events.concatMap(event ->
        policy.canRead(user, tenant, event.resourceId())
                .flatMap(allowed ->
                        allowed ? Mono.just(event)
                                : Mono.error(
                                        new AccessDeniedException(
                                                "access revoked"))));
~~~

This is an **architecture snippet**; `events`, `policy`, `Event`, and user/tenant are not declared. It illustrates that each event must be authorized before being emitted. `concatMap` preserves order, though throughput may be bounded by the policy service. If the policy service errors, do not allow subsequent events to be emitted. If an SSE response has already committed HTTP 200, it cannot be changed to 403; the stream must be terminated/closed per protocol and reconnected with fresh auth.

### 12.4. Cancellation and onComplete depend on operator placement

`Flux.take(2)` completes **downstream** after two values, but can cancel upstream. If `doFinally` is placed **before** `take`, upstream observes `CANCEL`; if placed **after**, the outer subscriber usually observes `ON_COMPLETE`. Place test assertions at the right publisher boundary, and do not assume every completion means "client cancelled".

## 13. WebTestClient and JWT: do not use one test to replace the whole system

`StepVerifier` tests the Publisher; `WebTestClient` tests the HTTP/WebFlux Security chain:

| Test layer | What it proves |
| --- | --- |
| Unit manager | Grant/deny/empty/error/timeout/laziness |
| Service composition | Repository is not subscribed before allow |
| Spring AOP method security | `@PreAuthorize` actually intercepts the bean proxy |
| WebFlux + WebTestClient | HTTP 401/403, route rules, and response mapping |
| JWT integration | Signature, issuer, audience, expiry/JWKS with real or test keys |
| DB/business isolation | Returned data actually matches tenant/user ownership |

A WebFlux snippet:

~~~java
// Test snippet in a project with WebTestClient and Spring Security Test.
webTestClient.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_reports.read")))
        .get().uri("/api/reports/report-7")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_other")))
        .get().uri("/api/reports/report-7")
        .exchange()
        .expectStatus().isForbidden();
~~~

`mockJwt()` creates a mock JWT/Authentication to test authorization. It **does not** prove that JWT signature/issuer/audience/JWK Set has been verified. For a real resource server, you must test JWTs signed with a test private key and a compatible decoder validator or a controlled fake IdP/JWKS endpoint.

### 13.1. HTTP status and security signals

- Missing/invalid Bearer authentication: usually HTTP **401**.
- Authenticated but insufficient scope: usually HTTP **403**.
- Custom manager returns false and service emits `AccessDeniedException`: usually HTTP 403 in the appropriate WebFlux security handler.
- Permission database timeout/connection failure: infrastructure error, possibly HTTP **5xx**; must still fail closed.
- `Mono.empty()` in a controller/business layer may turn into HTTP 200 with an empty body or 404 depending on the handler. Never let **no decision** accidentally become a success response.

### 13.2. @WithMockUser does not automatically populate Reactor Context in every test

Spring Security Test supports `@WithMockUser` with test listeners. For **reactive method security**, appropriate context support (`ReactorContextTestExecutionListener`) is required. In unit tests without a Spring context, using `ReactiveSecurityContextHolder.withAuthentication` is clearer.

### 13.3. Do not block on the Netty event loop

`StepVerifier` is used in **test code**. Never put `policy.canRead(...).block()` in a production security manager; it can cause deadlocks/latency and break the reactive chain. If a repository uses blocking JDBC, use a dedicated adapter/scheduler or switch to a reactive driver; do not call blocking code inside a `flatMap` running on the event loop.

## 14. Debugging failing tests: understand expected vs actual signals

Common situations:

| Expected | Actual | Cause to investigate |
| --- | --- | --- |
| `expectNextMatches(true)` | onComplete without value | `Mono.empty()`, filter dropped false, missing Authentication |
| `expectNextMatches(false)` | onError | Test mistakenly called `verify`/interceptor instead of `authorize` or policy source errored |
| `expectError(AccessDeniedException)` | onNext(report) | Policy bypass, fail-open, AOP proxy did not run |
| `expectError(AccessDeniedException)` | onError(NullPointerException) | Bug in test/implementation, not a standard denial |
| `verifyComplete()` | Hangs forever | `Mono.never()`, pending source, missing timeout, virtual clock not advanced |
| PublisherProbe not subscribed | Was subscribed | Protected repository started before allow |
| TestPublisher no subscribers | Test expected subscription | Publisher not subscribed yet, hot event sent too early |
| Context expected user alice | empty or bob | Wrong `contextWrite`, split subscription, global mutable state |
| withVirtualTime timeout | Time does not advance | Publisher created before virtual scheduler or uses its own scheduler |
| StepVerifier cancellation expected | Source still running | Adapter ignores cancel; separate subscribe exists |
| Test expected 403 | HTTP 401 | Authentication failed, never reached authorization |
| Test expected 401 | HTTP 403 | Token authenticated but missing authority |
| `mockJwt()` success | Real JWT fails | Missing audience/issuer/keys/expiry; test mocks do not verify cryptography |

### 14.1. scenarioName and as

~~~java
StepVerifier.create(decision,
                StepVerifierOptions.create()
                        .scenarioName("tenant-a / report-read / deny"))
        .expectNextMatches(result -> !result.isGranted())
        .as("explicit denial expected")
        .verifyComplete();
~~~

Scenario names should use **fake fixture IDs**; do not put bearer tokens, emails, raw user subjects, or sensitive reports in assertion messages/logs.

### 14.2. verifyThenAssertThat

~~~java
StepVerifier.create(Flux.just(1, 2).take(1))
        .expectNext(1)
        .expectComplete()
        .verifyThenAssertThat();
~~~

This illustrates the post-verification API. Subsequent assertions on the returned object can check dropped/discarded items when an operator exhibits that behavior. However, `verifyThenAssertThat` **does not by itself** prove data did not reach a repository/cache/log; you need a `PublisherProbe`/spy and side-effect checks.

### 14.3. Reasonable test timeouts

By default, `verify()` and `verifyComplete()` can wait indefinitely if no timeout is configured. For a Publisher that never completes:

~~~java
StepVerifier.create(Mono.never())
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

The test above cancels and verifies without waiting for completion. `StepVerifier.setDefaultTimeout(...)` changes global configuration and can affect parallel tests, so prefer per-scenario timeouts whenever possible.

## 15. Risks with custom ReactiveAuthorizationManager

### 15.1. Errors from the permission service are not permission denied

A network error and a false decision have different semantics. The API may map false to 403 and infrastructure errors to 503; neither **may return private data**. Use separate metrics for `authorization.denied` and `authorization.backend.error`; do not log claims/tokens.

### 15.2. Decision caching must be protected

A globally reused `Mono<AuthorizationResult>.cache()` can grant user A's allow to user B. If caching permissions, the key must include verified issuer/subject/tenant/resource/action, plus TTL and invalidation on revocation. Never cache allow indefinitely, especially with multi-tenant and streaming systems.

### 15.3. Retries can multiply permission lookups

`retryWhen` resubscribes to the source. If the permission store errors and retries indefinitely, the system can create a query storm; if policy changes between retries, results become even less predictable. Use deadlines, retry budgets for transient faults, and fail closed. Do not replay business requests with side effects just because the authorization service timed out.

### 15.4. Self-invocation and eager publishers

Security proxies can be bypassed via `this.method()`, while eager `Mono.just(expensiveCall())` can execute side effects before the interceptor decides. Test actual method invocations through the Spring bean + check laziness on the adapter, not just policy units.

### 15.5. Dynamic authorization for long-lived Flux streams

A single allow at subscription time does not guarantee the user still has access later. If the user is revoked, entitlements must be re-checked per event/periodically or the stream terminated at lease/expiry; test with `TestPublisher`/virtual time to simulate revocation mid-stream. If even a single cross-tenant event leaks before the check, the test must fail.

## 16. Recommended test matrix

| Scenario | Manager / Publisher | Assertion then |
| --- | --- | --- |
| Auth present, valid scope and membership | Emit granted=true | Repository subscribed |
| Missing scope | Emit granted=false | Membership not called, repository not subscribed |
| Membership false | Emit false | Denied path |
| Membership empty | False per sample app | Never auto-allow |
| Authentication empty | False per sample app | Never rely on empty |
| Membership throws error | onError | Do not subscribe sensitive data |
| `verify` allowed | Mono<Void> complete | Business logic may proceed |
| `verify` denied | AccessDeniedException | Business logic blocked |
| @PreAuthorize allowed | Business Mono emits | Via injected proxy |
| @PreAuthorize denied | AccessDeniedException | No business result |
| Client cancels during query | cancel | Upstream cleanup |
| Policy timeout | onError(timeout) | Fail closed |
| 2 users Reactor Context | Two separate identities | No leak across subscriptions |
| Per-event revoke | Denied/error/complete | No sensitive event emitted after revoke |
| Source no demand | No onNext before request(n) | Backpressure preserved |
| JWT invalid issuer/aud/signature | HTTP 401 | Decoder rejects |
| JWT valid, wrong scope | HTTP 403 | Route denies |
| WebTestClient mockJwt pass | Only authorization passes | Do not assume JWT really verified |
| Repository eager call before allow | Test must fail | Refactor to defer/reactive source |
| Re-subscribe policy Mono | Multiple checks if uncached | Check concurrency/rate limits |

## 17. Common mistakes

1. Using only `verifyComplete()` to test "allow" when the publisher could emit `Mono.empty()`.
2. Expecting `expectError` on an `authorize` method whose contract returns `AuthorizationDecision(false)`.
3. Confusing `verify` returning `Mono<Void>` with `authorize` returning a decision object.
4. Forgetting to call `verify()`, so `StepVerifier` never subscribes.
5. Allowing access on an empty/abstain publisher without an explicit composition policy.
6. Using `onErrorReturn(true)` when the permission store fails: fail-open.
7. Failing to assert the repository was not subscribed to before deny.
8. Querying data eagerly with `Mono.just(expensiveRead())` before authorization.
9. Reading the principal from `SecurityContextHolder` ThreadLocal instead of Reactor Context.
10. Assuming `@WithMockUser` works in all reactive unit tests without the test listener.
11. Testing `@PreAuthorize` via `new Service()`, bypassing the Spring proxy.
12. Reading JWT claims in a `mockJwt` test and treating it as signature/JWKS verification.
13. Creating `Mono.delay` before `withVirtualTime`, causing virtual time to have no effect.
14. Assuming the virtual scheduler changes `Instant.now()`; an injectable `Clock` is required.
15. Calling `expectNoEvent` before `expectSubscription`.
16. Emitting `TestPublisher` signals before the subscriber is ready.
17. Confusing cancel with complete/error in `doFinally`.
18. Omitting timeouts so infinite/pending Publishers hang CI.
19. Using unbounded `Flux.onBackpressureBuffer()` for permission/event streams.
20. Caching authorization decisions without tenant/user/resource/expiry.
21. Asserting only HTTP 403 without measuring data side effects.
22. Retrying failed authorization infinitely and causing a request storm.
23. Emitting events to the client before the per-item policy `Mono` completes.
24. Putting raw bearer tokens/subjects/PII in scenario names/logs/probes.
25. Skipping tests for the real path through Spring AOP/HTTP/token validation/data ownership.

## 18. Project adoption checklist

1. Document the API version and Publisher contract of each security layer.
2. Test all five signal classes: value granted, value denied, empty, error, cancel.
3. Every allow test must assert onNext granted, not just onComplete.
4. Every deny must prove the protected Publisher was not subscribed to.
5. A permission database error always fails closed.
6. All membership/tenant lookups take the user from verified identity.
7. Include a laziness test before subscription.
8. Include `TestPublisher` tests for pending results, cancellation, and permission store failure.
9. Include `StepVerifierOptions`/`contextWrite` tests verifying the principal matches the subscriber.
10. Include `withVirtualTime` + `Clock` tests for timeouts and expiry if used.
11. Test backpressure and bounded resources if long-lived `Flux` streams exist.
12. Test `@PreAuthorize` on the Spring-managed proxy and self-invocation paths.
13. Test WebFlux HTTP 401/403 with `WebTestClient`.
14. Test JWT cryptography/issuer/audience separately, not just `mockJwt`.
15. Test ownership/tenant isolation against the real repository.
16. Set timeouts for tests that might never complete.
17. Do not use blocking I/O in the reactive authorization flow.
18. Do not globally cache allow results beyond permission TTL/revocation policy.
19. Have distinct observability for denied/error/cancel without logging tokens.
20. Run Maven tests in CI and inspect actual Surefire reports.

## 19. Self-check questions

**Question 1.** Why does `StepVerifier.create(Mono.empty()).verifyComplete()` not prove access was allowed?

**Answer:** Because the publisher only completes without emitting an `AuthorizationResult(true)` decision.

**Question 2.** What does `ReactiveAuthorizationManager.authorize` return on deny?

**Answer:** It can emit `AuthorizationResult(false)` and then complete; it does not necessarily emit `onError`.

**Question 3.** What signal does `verify` usually emit on deny?

**Answer:** `onError(AccessDeniedException)`, with no `onNext`.

**Question 4.** Why is `PublisherProbe` needed when testing read access to a private report?

**Answer:** To prove the repository Publisher was not subscribed to or requested on deny/error.

**Question 5.** Should a membership database error turn `Mono.error` into `true` to preserve availability?

**Answer:** No. That is fail-open and can grant unauthorized access.

**Question 6.** When should `TestPublisher.next(false)` be emitted?

**Answer:** After `StepVerifier` has subscribed, typically inside a `then(...)` callback.

**Question 7.** Why does testing `@PreAuthorize` require a Spring bean proxy?

**Answer:** Interception relies on AOP; `new Service()` and self-invocation can bypass it.

**Question 8.** Does `withVirtualTime` replace `Instant.now()`?

**Answer:** No. An injectable `Clock` is required for security wall time.

**Question 9.** What does `mockJwt()` prove?

**Answer:** It tests authorization with a mock JWT/Authentication, not real signature/issuer/audience verification.

**Question 10.** If an HTTP 403 test passes, but the repository already queried data before denying, is it safe?

**Answer:** Not yet. You must verify subscription order and side effects at the service/data boundary.

**Question 11.** What is needed if a permission publisher is `Mono.never()`?

**Answer:** A timeout/deadline and cancellation, rather than waiting indefinitely or auto-granting access.

**Question 12.** Why must authorization decisions on a `Flux` stream be re-checked per event?

**Answer:** Permissions/tenants/objects may differ across events or be revoked after initial subscription; policy must be enforced per SLA.

## 20. Official documentation

- [Project Reactor — Testing with StepVerifier, TestPublisher and PublisherProbe](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Reactor Test API — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Reactor Test API — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html)
- [Reactor Test API — TestPublisher](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Reactor Test API — PublisherProbe](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security Javadoc — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security Javadoc — AuthorizationResult](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html)
- [Spring Security Javadoc — AuthorizationDecision](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html)
- [Spring Security Javadoc — AuthorizationDeniedException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDeniedException.html)
- [Spring Security — Reactive WebTestClient Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Testing WebFlux JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Boot — Testing and Test-Scope Dependencies](https://docs.spring.io/spring-boot/reference/testing/test-scope-dependencies.html)
