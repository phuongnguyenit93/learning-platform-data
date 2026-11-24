# Retries, Caching, and Cancellation: Security Safety Implications in Spring Security Reactive

## Learning Objectives

In Spring WebFlux, authentication and authorization are part of the **reactive pipeline**. Optimizations that appear purely performance-related — **retrying** on errors, **caching** to cut down reads, and **cancellation** when clients stop waiting — can alter when permissions are checked, which identity is used, how many times tasks execute, and whether security events are recorded.

After this lesson, you will be able to:

1. Explain why `retryWhen` re-subscribes to upstream and can re-execute both permission checks and side effects.
2. Distinguish caching JWKs, token introspection, identity, authorities, and authorization decisions; design cache keys, TTLs, and invalidation aligned with tenant boundaries.
3. Distinguish `onComplete`, `onError`, and `cancel`; understand their effects on cleanup, auditing, I/O queries, and transactions.
4. Use `ReactiveSecurityContextHolder`/Reactor Context per subscriber, avoiding authentication leaks via shared publishers or uncontrolled `subscribe()` calls.
5. Write Java 17+ tests verifying bounded retries, never retrying bad credentials, non-mixing user contexts, and observed cancellation.

**Scope:** Spring Security WebFlux (reactive), Project Reactor `Mono`/`Flux`, JWT or opaque-token Resource Server; examples target Spring Security 6.x, Reactor 3.5+, and Spring Boot 3.x. Servlet `ThreadLocal` semantics cannot substitute for Reactor Context.

## 1. Security Executes When a Publisher Is Subscribed

Simplified diagram:

~~~text
HTTP client
  → SecurityWebFilterChain
      → validate JWT / opaque token / session
      → Authentication and SecurityContext
      → check route-level authorization
  → WebFlux handler
      → service / method security
      → policy service, repository, downstream HTTP
  → response or onError / cancel
~~~

With **cold** publishers, assembling a `Mono`/`Flux` typically does not call databases/HTTP yet. Subscription activates the source; subscribing again can invoke the source again. With **hot/shared publishers** or `Mono.cache()`, data can be shared across multiple subscribers. Spring Security Reactive relies on **per-subscription Reactor Context** to propagate `SecurityContext`, not a global “current user” variable.

- **onComplete:** upstream completes normally, with or without `onNext`.
- **onError:** upstream terminates with an error; downstream may apply a fallback or retry.
- **cancel:** subscriber signals it needs no further data. Cancellation is not equivalent to an exception; an already-committed external operation **does not automatically roll back**.
- **retryWhen:** when upstream emits a matching `onError`, Reactor **re-subscribes** to the source per policy rather than merely re-evaluating a pure function.
- **cache():** caching can alter subscription semantics, replay prior signals, and even keep upstream running after a subscriber cancels.

Misused, these operators can lead to **fail-open** (errors turning into granted access), **stale authorization** (revoked privileges still honored), **cross-user data leaks**, **duplicate side effects**, or **lost audit events**.

## 2. Retry: Repeat Only Safe Operations and Appropriate Errors

A cold source can re-run:

~~~text
subscription 1 → call dependency → error
                      ↓ retryWhen
subscription 2 → call dependency again → error/complete
                      ↓ retry budget remaining
subscription 3 → ...
~~~

Retry does not inherently know whether an operation is idempotent. If a POST already wrote data while the client saw a timeout, retrying can create duplicate orders or repeat a privilege-change request. Placing retry around a sequence that checks permissions, writes to a database, and emits events can repeat the **entire** chain.

### 2.1. Classifying Errors by Security Meaning

| Outcome | Meaning | Should You Retry the Same Credential/Request? |
| --- | --- | --- |
| Invalid JWT signature, wrong issuer, expired; opaque introspection returns `active=false` | Invalid credential; Resource Server typically returns **401** | **Do not** retry the same credential hoping it becomes valid |
| Authentication succeeded but missing scope/role, insufficient ACL/tenant | Unauthorized; typically returns **403** | **Do not** retry to “bypass” a denial decision |
| Identity provider/policy service timeout, connection reset, or transient 5xx | Authorization infrastructure unavailable | May retry **with bounds**, if the operation is idempotent and still fails closed |
| HTTP 429 or `Retry-After` present | Quota/rate limit | Retry only within quota, deadlines, and proper backoff |
| Malformed payload, converter error, misconfigured issuer/JWK | Systemic error | Do not retry blindly; fix root cause |
| Write transaction with unknown commit status | Uncertain side-effect state | Needs idempotency key, transaction/outbox, and reconciliation before retrying |

**Fail closed** means **never** turning an authentication/authorization failure into ALLOW. It **does not mean** every infrastructure error must masquerade as 403: when an identity provider is unavailable, an app may return 503/5xx depending on exception-handler design. Maintain the distinction between invalid credentials and an impaired authorization service.

### 2.2. Bounded Retry with Filter and Backoff

This is a **service snippet**, assuming `lookupPolicy(...)` is an **idempotent read** request and the adapter maps transient infrastructure errors to `TemporaryPolicyServiceException`:

~~~java
Mono<PolicyDecision> decision = Mono.defer(
        () -> policyClient.lookupPolicy(tenantId, subjectId, resourceId))
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.3)
            .filter(error -> error instanceof TemporaryPolicyServiceException)
    );

Mono<PolicyDecision> bounded = decision.timeout(Duration.ofSeconds(5));
~~~

Explanation:

- `Retry.backoff(2, ...)` allows at most **2 retries**, plus the initial attempt for at most **3 total source invocations**.
- `filter` excludes credential/permission errors from retries. Never use an unfiltered default `retryWhen` on security layers.
- `timeout` **before** `retryWhen` applies per attempt; `timeout` **after** `retryWhen` caps the entire sequence.
- Backoff and jitter reduce synchronized retry storms across requests, but you still need concurrent-call caps and circuit breakers/rate limits where appropriate.
- Control latency budgets and cancellation; never assume a retry runs only once or always succeeds eventually.

The snippet above is **not a standalone Java class**: `PolicyDecision`, `policyClient`, `TemporaryPolicyServiceException`, and parameters belong to the real application.

### 2.3. Retry Placement Determines What Repeats

~~~java
// Focus retry on a read dependency that is safe to call again.
Mono<PolicyDecision> lookup = policyClient.lookupPolicy(key)
    .retryWhen(transientRetry);

// DANGEROUS if the whole chain has already partially executed side effects.
Mono<Result> wholeOperation = authorizeThenCreateOrder()
    .retryWhen(transientRetry);
~~~

In the second example, if the order is created and only event publishing fails, re-subscribing can create the order a second time. Separate policy lookups from transactions, and use idempotency keys, unique constraints, and outboxes at appropriate boundaries. If permissions must hold at commit time, verify permissions **within a consistent business boundary**, not solely at the start of the HTTP request.

### 2.4. Fallbacks That Introduce Security Bugs

~~~java
// ANTI-PATTERN: authorization dependency failure -> converted into granted access.
Mono<Boolean> allowed = policyClient.isAllowed(subject, resource)
    .onErrorReturn(true);
~~~

This turns downtime into unauthorized access. Preserve the error so the security/error handler returns an appropriate failure; only degrade gracefully for content explicitly defined as public. Never apply `onErrorResume(... allow ...)` broadly across endpoints.

### 2.5. Retries and Token Refresh

A Resource Server must reject invalid bearer tokens; never make a bad-signature JWT valid by retrying. On the OAuth2 **client** side, a valid refresh token may be used to obtain a new access token per contract; replaying a request must be bounded and proven replay-safe, especially for mutations. An infinite “401 → refresh/retry” loop can trigger request storms or repeated side effects.

## 3. Caching: Permissions and Identities Have Lifetimes

Security caching spans multiple layers:

- **JWK public keys:** cache signing keys to reduce JWK endpoint load; refresh on key rotation/new `kid`.
- **Opaque-token introspection:** cache `active` status, attributes, and authorities; risks granting access to revoked tokens.
- **User roles/permissions:** risks an account demoted from `ROLE_ADMIN` continuing to use stale cached roles.
- **Authorization decisions:** risks reusing ALLOW from another action, resource, or tenant.
- **HTTP responses/business data:** risks one user receiving another user's data via faulty cache keys or shared HTTP/CDN caches.
- **`Mono.cache()`/`Flux.cache()`:** risks replaying the exact `Authentication` or `SecurityContext` from an earlier subscription.

### 3.1. Never Cache `ReactiveSecurityContextHolder` in a Singleton

~~~java
// ANTI-PATTERN: shared field in a singleton service.
private final Mono<String> sharedUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .cache();
~~~

Reactor Context is per-subscriber, yet `Mono.cache()` can retain **the first subscription's value**. If Alice subscribes first, Bob risks receiving Alice's name from `sharedUser`. This is a cross-user vulnerability, not a valid cache optimization.

~~~java
// RIGHT: build principal lookup logic as a cold publisher per subscription.
public Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

If the same request needs to reuse **one** expensive repository lookup, you can create a `Mono.cache()` **scoped inside that request**, after resolving the right principal, ensuring the publisher is never stored globally. This must still satisfy requirements to re-check permissions before sensitive operations.

### 3.2. Cache Keys Must Not Bypass Security Boundaries

The decision “allowed to edit report 42” may depend on:

~~~text
issuer / audience
+ subject / client identity
+ tenant
+ resource id / owner
+ action: read/write/approve
+ role / scope / principal attributes
+ permissionVersion / policyVersion
+ timestamp, resource state, or target environment
~~~

Never reuse a bare key like `"report-42"`, `"ADMIN"`, or `"username"` across tenants or actions. If a token must be represented in a key, never put the raw bearer token into URLs/logs/metrics; use a protected fingerprint (e.g., HMAC with an internal key) combined with identity/issuer/tenant/policy metadata per contract. Avoid logging raw tokens, personal claims, or introspection secrets.

### 3.3. TTL, Revocation, and Invalidation

An illustrative TTL ceiling for token-based caches:

~~~text
effectiveTTL <= min(configuredTTL,
                    tokenExpiresAt - now - clockSkew,
                    maximumPermittedRevocationDelay)
~~~

If the computed TTL is non-positive, do not use the cache. With self-contained JWTs, immediate revocation may require a denylist, session version, very short-lived tokens, or an external check; TTL alone does not guarantee instant revocation.

| Cache Type | Mistake | Fix |
| --- | --- | --- |
| JWK keys | Caching rotated keys forever | Use bounded cache/refresh and detect new `kid`s |
| Opaque introspection | `active=true` retained after revocation | Cap TTL by expiry and revocation SLA; support invalidation |
| Permissions | `ROLE_ADMIN` persists after demotion | `permissionVersion` or event-driven invalidation; re-check at critical points |
| Decisions | One user's ALLOW reused for another | Key by subject, tenant, resource, action, and policy version |
| Responses | Data leak via shared cache/CDN | Proper `Cache-Control`/`Vary`/keys by principal and tenant |
| Errors/empty | Transient infrastructure failures held long | Control negative/error caching separately |

### 3.4. `Mono.cache()` Caches Errors Too and Does Not Necessarily Stop the Source on Cancel

Per Reactor semantics:

- **`Mono.cache()`** can retain results, `onComplete`, or `onError` **indefinitely** while the publisher lives.
- **`Mono.cache(Duration)`** also replays **values, errors, or empty completions** within the TTL. Thus caching can turn a transient failure into repeated failures even after the dependency recovers.
- Once **`Mono.cache()` starts subscribing to its source**, cancelling a downstream subscriber does not necessarily cancel upstream; Reactor documents an active cached source as non-cancellable via normal downstream cancel. This impacts resource costs and cleanup when clients disconnect.
- **`cacheInvalidateIf` / `cacheInvalidateWhen`** can invalidate stored values, but do not inherently understand tenant, revocation, signature, or expiry policies; race conditions between requests must still be evaluated. Those APIs are value-oriented and do not cache errors/empty completions like plain `cache()`.

Operator ordering also matters:

~~~java
// Retry before cache: if budget is exhausted, the final error can still be cached for the TTL.
Mono<String> a = remoteRead()
    .retryWhen(transientRetry)
    .cache(Duration.ofSeconds(30));

// Cache before retry: retry may simply receive the exact cached error,
// without firing a new HTTP call until the cache expires.
Mono<String> b = remoteRead()
    .cache(Duration.ofSeconds(30))
    .retryWhen(transientRetry);
~~~

Both snippets are structural examples assuming `remoteRead()` and `transientRetry` exist. If you only want to cache **successful values**, use an appropriate caching API/pattern and test error, empty, race, and cancellation cases. **Never cache `Mono<Authentication>` or `Mono<SecurityContext>` application-wide.**

## 4. Cancellation: Client Departure Does Not Undo Completed Work

Cancellation can come from client disconnects, timeouts, explicit `dispose()`, `take(n)`, `next()`, `switchMap()` cancelling a prior source, or any downstream operator that no longer needs more data.

| Event | Reactor Signal | Considerations |
| --- | --- | --- |
| Success | `onNext` then `onComplete`, or empty completion | Output matches permissions; transaction/audit handled |
| Auth/permission failure | `onError` or HTTP 401/403 after mapping | No data leak, never default-allow |
| Client disconnect / timeout | `cancel` may propagate upstream | Already-sent external I/O may continue; cleanup and audit |
| Shared/cached publisher with other subscribers | Cancel one subscriber | Upstream may keep running; do not assume source stops |

**Cancellation is best effort toward upstream**, not a distributed rollback guarantee. An already-dispatched HTTP POST may have committed; closing a browser tab does not erase a database row. Once a system accepts a sensitive command, it must provide contracts to query status and deduplicate future requests.

### 4.1. `doFinally` Observes All Three Terminal States

~~~java
return securedOperation()
    .doFinally(signal -> {
        // ON_COMPLETE, ON_ERROR, CANCEL
        // Record non-sensitive metrics; do not print tokens or PII.
        metrics.recordTermination(signal);
    });
~~~

`doOnSuccess` does not observe errors or cancellation; for an empty-completing `Mono`, `doOnSuccess` receives `null`. `doFinally` observes `SignalType.CANCEL`, making it suitable for counting cancellations and releasing **synchronous** resources. The callback does not automatically await an asynchronous audit publisher.

**Dangerous anti-pattern:**

~~~java
return securedOperation()
    .doOnSuccess(result -> auditRepository.save(result).subscribe());
~~~

This ignores errors/cancellations and spawns an unlinked `subscribe()` detached from request security context, transactions, cancellation, and error handling. Audit data can be lost, with no reliable retries or deduplication.

### 4.2. Asynchronous Cleanup via `usingWhen`

This is a **Java design snippet**, assuming `leaseService.acquire(...)` returns `Mono<Lease>`, `lease.close()` returns `Mono<Void>`, and `protectedWrite(...)` returns `Mono<WriteResult>`:

~~~java
Mono<WriteResult> result = Mono.usingWhen(
    leaseService.acquire(resourceId),
    lease -> protectedWrite(lease, request),
    lease -> lease.close(),                 // normal completion
    (lease, error) -> lease.close(),        // error
    lease -> lease.close()                  // cancellation
);
~~~

`usingWhen` integrates async cleanup into lifecycle hooks across all terminal branches; cleanup must be idempotent and cleanup errors handled. It **does not** replace DB transactions, distributed lock timeouts, crash recovery, or durable auditing. If the process dies before sending cleanup, you still need TTL/lease expiration or recovery mechanisms.

### 4.3. Auditing and Business State Must Be Durable at the Right Point

Evaluate each operation:

- **Read-only:** allow cancellation to save resources, provided no orphaned resources or temporary privileges remain.
- **Accepted order creation/payment/token revocation:** when the HTTP response cancels, the server still needs a way to determine whether the accepted operation completed. Use idempotency keys, unique constraints, durable queues/jobs, and status endpoints where appropriate.
- **Mandatory audits:** consider an outbox written inside the business transaction, with workers processing events via retries/deduplication. `doFinally` and fire-and-forget `subscribe()` are not durable across crashes.
- **Pre-commit permission checks:** for long-running operations or revocable permissions, policies must define when to re-check/compare versions inside a consistent transaction.

Not every request needs a queue. Only side effects obligated to finish after HTTP disconnect need corresponding durable boundaries.

## 5. Reactor Context: Per-Subscription Identity Boundaries

Spring Security Reactive provides **`ReactiveSecurityContextHolder`**. Example reading the principal name in a flow:

~~~java
public Mono<String> getCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

Without an authenticated context, the `Mono` may complete empty. Enforcing access control still requires `SecurityWebFilterChain` or reactive method security; never fabricate a privileged principal when context is empty. **Never** use a self-declared `userId` from a query/header in place of real authentication.

Common mistakes:

1. Storing `Authentication` in a static field or mutable singleton field across requests.
2. Caching `SecurityContext`/username in a global `Mono` field.
3. Calling `subscribe()` arbitrarily inside services, detaching request context and errors.
4. Using `ThreadLocal` to read principals in other schedulers/callbacks assuming equivalence with Reactor Context.
5. Manually calling `contextWrite(withAuthentication(...))` from untrusted input to “restore” identity.
6. Relying on coarse authorities like `SCOPE_read` while forgetting **resource ownership and tenant** checks.

In a properly composed Reactor chain, `publishOn`/`subscribeOn` do not silently drop Reactor Context; risks come from **splitting subscriptions, bridging to APIs unaware of Reactor Context, or sharing data across subscribers**.

Example **method security snippet**:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.write')")
public Mono<Report> updateReport(String id, ReportChange change) {
    return repository.findById(id)
        .flatMap(report -> verifyTenantAndUpdate(report, change));
}
~~~

You must enable `@EnableReactiveMethodSecurity` and invoke through a Spring bean proxy for annotations to run; the snippet above is not a standalone class. `hasAuthority` checks only the authority string; preventing cross-tenant access requires checking the resource itself. For operations executed later from a queue, the user authenticated on the initial request does not automatically carry perpetual privileges into deferred jobs.

## 6. Runnable Java 17+ Example: Testing Retries, Identity, and Cancellation

The test below is a **JUnit unit test exercising Reactor**, requiring no HTTP server. It clarifies operator semantics before adding `WebTestClient` integration tests.

In a Gradle Spring Boot 3.x project with WebFlux/Security, the required dependencies look like (a `build.gradle` snippet, not a standalone file):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
test {
    useJUnitPlatform()
}
~~~

File **`src/test/java/example/security/ReactiveSecurityOperatorTest.java`**:

~~~java
package example.security;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveSecurityOperatorTest {

    static class TemporaryAuthServiceException extends RuntimeException {
    }

    static class InvalidCredentialException extends RuntimeException {
    }

    static Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
    }

    @Test
    void retriesOnlyTemporaryDependencyFailures() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> lookup = Mono.defer(() -> {
            int attempt = calls.incrementAndGet();
            if (attempt < 3) {
                return Mono.<String>error(
                        new TemporaryAuthServiceException());
            }
            return Mono.just("policy-allow");
        }).retryWhen(
            Retry.backoff(2, Duration.ofMillis(1))
                    .jitter(0.0)
                    .filter(TemporaryAuthServiceException.class::isInstance));

        StepVerifier.create(lookup)
                .expectNext("policy-allow")
                .verifyComplete();
        assertEquals(3, calls.get());
    }

    @Test
    void doesNotRetryAnInvalidCredential() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> validation = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.<String>error(new InvalidCredentialException());
        }).retryWhen(
            Retry.backoff(2, Duration.ofMillis(1))
                    .filter(TemporaryAuthServiceException.class::isInstance));

        StepVerifier.create(validation)
                .expectError(InvalidCredentialException.class)
                .verify();
        assertEquals(1, calls.get());
    }

    @Test
    void eachSubscriberGetsItsOwnSecurityContext() {
        Authentication alice =
                new TestingAuthenticationToken("alice", "unused", "SCOPE_read");
        Authentication bob =
                new TestingAuthenticationToken("bob", "unused", "SCOPE_read");

        Mono<String> current = currentName(); // cold, no cache

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void observesCancellation() {
        AtomicInteger cancellations = new AtomicInteger();

        Mono<String> pending = Mono.<String>never()
                .doOnCancel(cancellations::incrementAndGet);

        StepVerifier.create(pending)
                .thenCancel()
                .verify();

        assertEquals(1, cancellations.get());
    }
}
~~~

Run in a Gradle project with Spring Boot/dependency management configured:

~~~bash
./gradlew test --tests example.security.ReactiveSecurityOperatorTest
~~~

With Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.security.ReactiveSecurityOperatorTest
~~~

**Expected outcome:** 4 tests PASS. Tests verify respectively 3 transient attempts, only 1 attempt on invalid credentials, Alice and Bob reading their own Reactor Contexts, and the cancel callback invoked once. The class prints no stdout; results are reported by JUnit/Gradle with no assumed fixed console string.

### 6.1. Experiment demonstrating a cross-user cache bug

The snippet below intentionally demonstrates an **anti-pattern**; never store a shared publisher like this in an application:

~~~java
Mono<String> shared = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .cache();

// Alice subscribes first; shared cache is populated with "alice".
StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();

// Bob subscribes later, but shared replays "alice": security bug.
StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
    .expectNext("alice")
    .verifyComplete();
~~~

`alice`/`bob` `Authentication` variables are assumed to be declared as in the main test. This is a **test exposing an intentional defect**, not a desired production assertion. Fix with a per-subscription cold publisher, or a request-scoped cache with boundary controls.

### 6.2. Cancellation with a cached source

~~~java
Mono<String> sharedPending = Mono.<String>never()
    .doOnCancel(() -> metrics.recordUpstreamCancel())
    .cache();
~~~

Once the cache begins loading, cancelling a downstream subscriber **does not necessarily cancel upstream**. You cannot rely on `recordUpstreamCancel` equaling 0 to conclude all work stopped; check active connections/outstanding I/O and enforce adapter timeouts. This is an illustrative snippet; `metrics` is a hypothetical dependency.

## 7. When Three Operators Interact: Event Ordering and Races

Suppose:

~~~text
t0  Alice currently holds ROLE_EDITOR.
t1  Alice calls to update report; cached decision returns ALLOW.
t2  Admin revokes Alice's ROLE_EDITOR.
t3  Dependency times out; retry triggers a new subscription.
t4  Client closes connection, downstream cancels.
t5  Already-sent write may still commit; audit inside doOnSuccess does not run.
~~~

This is a **conditional risk**, not a claim that Spring WebFlux always executes this exact sequence. It depends on transaction separation, cache key/TTL, retry placement, and dependency behavior on cancel. You must explicitly define:

- **Freshness** policy: how long may a permission checked at t1 remain valid? Do critical mutations need a re-check or `policyVersion` comparison at commit?
- **Idempotency:** how many records can a retry after timeout create? How do unique constraints, request IDs, and transactions/outboxes handle it?
- **Revocation:** which caches does a permission change at t2 invalidate, and across how many instances?
- **Cancellation contract:** which operations can safely cancel, and which accepted operations must complete or expose traceable status?
- **Context isolation:** do new retries/subscriptions pull the right request's principal rather than a shared stale `Authentication`?

No single operator solves retry, caching, identity, and durability simultaneously.

## 8. Observing and Measuring Errors Properly

A pipeline should typically separate:

~~~text
SecurityWebFilterChain
 ├─ validate token / resolve Authentication
 ├─ reject invalid credential
 └─ check basic authority
      ↓
Application handler/service
 ├─ read principal from Reactor Context
 ├─ check tenant + resource ownership
 ├─ policy lookup: bounded retry for transient errors only
 ├─ mutation: idempotency, transaction, audit/outbox
 ├─ response
 └─ doFinally: metrics for COMPLETE/ERROR/CANCEL
~~~

Metrics to measure separately:

1. **Authentication fail (401)**, **authorization deny (403)**, **dependency unavailable (5xx/503)**. Never lump all of them into “bad token”.
2. Retries per dependency, exhausted retries, total backoff, latency, and infrastructure pressure.
3. Cache hits/misses, cache age, invalidations, `permissionVersion` sync lag, and detected stale decisions.
4. Cancellation count, cleanup duration, and downstream requests still running after disconnect.
5. Idempotency key collisions/deduplication, durable job states, and audit outbox backlog.

Never log raw `Authorization` headers, JWT/opaque tokens, session cookies, private claims, or introspection responses. Use correlation/request IDs with appropriate log access control and watch metric label cardinality.

## 9. Integration Testing Matrix with Spring Security WebFlux

The unit tests above prove operator behavior, **not** that `SecurityWebFilterChain` returns the right HTTP statuses. With `WebTestClient` and appropriate test doubles for `ReactiveJwtDecoder` / `ReactiveOpaqueTokenIntrospector`, verify further:

| Case | Setup | What to Verify |
| --- | --- | --- |
| No Authentication | Request without bearer/session | HTTP 401 per app entry point |
| Invalid JWT/opaque token | Decoder/introspector rejects credentials | 401, no unbounded retries, no allow fallback |
| Logged in but missing authority | Principal lacks privilege | HTTP 403 and mutation does not run |
| Policy service transiently fails twice then OK | Fake returns transient errors twice | 3 total calls, right user/tenant privileges |
| Policy service prolonged outage | Fake always fails infrastructure | Must not allow; returns proper failure after retry budget |
| Permission revoked after cache fill | Change `permissionVersion`/invalidate | Next access obeys freshness contract |
| Two concurrent principals | Alice/Bob, two tenants | No cross-leaked cache or SecurityContext |
| Cached source then client cancels | Controlled Publisher/`StepVerifier` | Actual cancel semantics and resource budgets observed |
| Mutation retry after timeout | Downstream commits while response times out | Only one business outcome via idempotency |
| Cache stores error | Initial 5xx, then recovery | Error caching does not block recovery beyond policy |
| Scheduler switch/async bridge | `publishOn` and non-Reactor callbacks | Principal stays accurate, no `ThreadLocal` dependency |

When using **`mockJwt()`** or **`mockOpaqueToken()`**, you can test roles/scopes on rules/method security; they typically inject a mock `Authentication` and **bypass signature, `exp`/issuer, and HTTP introspection checks**. To test decoders and token caches, send a bearer header to the real Resource Server with a stubbed decoder/introspector at the right layer, or use a mock server if testing JWK rotation and the introspection protocol too. Avoid using `mockJwt().authorities(...)` and claiming the real converter was tested.

When testing races/timing, prefer controllable publishers, `StepVerifier` virtual time, or synchronization latches; avoid flaky `Thread.sleep`. If `doFinally` emits signals downstream before a callback finishes, verify metrics/cleanup after a proper synchronization point rather than asserting prematurely.

## 10. Pre-Production Safety Checklist

- [ ] Retries have an error filter, max attempts, backoff/jitter, and overall deadline; **never** retry authentication/authorization denials.
- [ ] No `onErrorReturn(true)` or ALLOW fallbacks when authorization checks fail.
- [ ] Replayable mutations are protected by **idempotency keys + transactions/unique constraints**.
- [ ] Cache keys properly separate **principal, issuer, tenant, resource, action, and `policyVersion`** whenever those affect decisions.
- [ ] Token-based caches never exceed token expiry or allowed revocation lag; invalidation and negative/error caching are designed.
- [ ] Never cache `SecurityContext`/`Authentication` or principal-lookup publishers in shared singletons.
- [ ] Never read principals from `ThreadLocal` or untrusted request input inside reactive authorization.
- [ ] Never depend on fire-and-forget `subscribe()` or `doOnSuccess` to guarantee audits.
- [ ] Cleanup handles success/error/cancel; critical tasks use durable queues/outboxes or recovery mechanisms.
- [ ] Tests cover 401, 403, 5xx, revocation after cache fill, two users/tenants, duplicate retries, and cancellation.

## 11. Self-Check Questions

1. How many total calls does `Retry.backoff(2, ...)` allow at most? **3**: one initial call and two retries.
2. Should a bad-signature JWT be retried automatically with the same token? **No**; it is an invalid credential, not a transient network failure.
3. Why is caching a `Mono` reading `ReactiveSecurityContextHolder` in a singleton dangerous? **It can replay the first subscriber's context to other users.**
4. Does `Mono.cache(Duration)` cache `onError`? **Yes**, for the duration of the TTL.
5. Does client cancellation roll back an already-committed transaction? **No**.
6. Does `doFinally(CANCEL)` guarantee durable auditing across crashes? **No**; a durable boundary is needed.
7. Can you test token signatures/expiry using only `mockJwt()`? **No**; you must test the decoder/validator or real bearer flow.
8. Why does a role cache need `permissionVersion` or invalidation? **To limit continued use of demoted/revoked privileges.**

## 12. References

- Spring Security — Reactive: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Reactive OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- Spring Security — `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Project Reactor — Error Handling / Retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Mono API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Project Reactor — RetryBackoffSpec API: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html

Code examples distinguish pieces runnable standalone as JUnit tests from illustrative snippets dependent on application code. Specific retry/cache/revocation/audit policies must follow your system's security and consistency contracts.