# Testing Reactive Method Security with StepVerifier

## 1. The Problem: Does the Annotation Actually Block Access?

In Spring WebFlux, a service may return `Mono<Document>` and be annotated with:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<String> readDocument(String id) {
    return repository.findTitle(id);
}
```

A developer sees a test for `readDocument("42")` return the expected data and concludes authorization works. That conclusion is **insufficient**: the test only proved business logic returns a result—not that unauthorized users are denied, unauthenticated callers are blocked, an erroring `Mono` never becomes PERMIT, or Spring actually registered the interceptor.

In the reactive model, method security has an additional critical factor: **`Authentication` lives in the subscriber's Reactor Context**, not by default in a ThreadLocal that an ordinary test could inspect via `SecurityContextHolder`. `Mono`/`Flux` are publishers; permission evaluation can happen at subscription time. Therefore, **`StepVerifier`** from `reactor-test` is the right tool to verify the actual signal sequence: values, completion, error-based denial, zero data emitted on deny, and timeouts.

This lesson focuses specifically on **testing Reactive Method Security with `StepVerifier`**, rather than substituting HTTP 401/403 checks alone. We build a real Spring-managed service, enable `@EnableReactiveMethodSecurity`, inject the bean through its Spring AOP proxy, and use `StepVerifier.create(...)` with `ReactiveSecurityContextHolder.withAuthentication(...)`.

### After This Lesson, You Will Be Able To

1. Test `@PreAuthorize` grants and denials on both `Mono` and `Flux`.
2. Inject test `Authentication` into the Reactor Context via `contextWrite`.
3. Assert `AccessDeniedException` and **that no sensitive elements are emitted**.
4. Test `@PostAuthorize` against returned objects.
5. Use a reactive policy bean returning `Mono<Boolean>` and verify fail-closed handling for empty/error signals.
6. Distinguish `@WithMockUser`/test listeners from manual authentication injection.
7. Test side effects and query subscriptions to avoid "403 yet data was already written".
8. Catch self-invocation, manual `new` instantiation, and missing `@EnableReactiveMethodSecurity`.
9. Use `StepVerifier.withVirtualTime(...)` for deterministic virtual-time timeout tests when appropriate.
10. Know when to supplement with `WebTestClient` and JWT decoder integration tests.

## 2. Three Layers to Separate in a Test Suite

```text
              HTTP Tests
WebTestClient / SecurityWebFilterChain
   - 401 unauthenticated
   - 403 forbidden to call route
                    |
                    v
             Method Security Tests
         @EnableReactiveMethodSecurity
              Spring AOP proxy
          @PreAuthorize/@PostAuthorize
                    |
                    v
       Reactive Domain/Repository Tests
       tenant, owner, ACL, query scope
```

- **HTTP security tests** prove the filter chain and route matchers block requests. An HTTP 403 does not prove `@PreAuthorize` on the service ever executed.
- **Method security tests** prove a real Spring bean with an interceptor denies when conditions fail and allows when authorized. This is the core focus of this lesson.
- **Data security tests** prove records belong to the right tenant/owner or policy. A passing `hasAuthority('DOC_READ')` does not automatically add `WHERE tenant_id=...` to database queries.

To isolate method security in HTTP tests, let the controller/HTTP layer accept an authenticated caller lacking the functional authority, then observe the **service method** return 403 or an error. In direct tests with `StepVerifier`, invoke the service bean **from the Spring context**, not the controller.

### Scope of Assertions

```text
PERMIT:
  onNext(expectedData) -> onComplete

DENY:
  onError(AccessDeniedException)
  no onNext protectedData
  no data-side-effect

EMPTY RESULT when caller is permitted:
  onComplete, no onNext

EMPTY POLICY DECISION:
  fail closed, do not treat as permit

POLICY ERROR/TIMEOUT:
  no protectedData or mutation
  error/deny classified per API contract
```

A publisher completing empty when the caller **is permitted** is normal (the document does not exist). However, a publisher that is **empty because no authorization decision was emitted** must never automatically become PERMIT. The two empty signals occur at **two different layers**, and tests must keep them distinct.

## 3. Foundations: Reactor Context and Subscription Time

Reactive Spring Security uses `ReactiveSecurityContextHolder` to read `SecurityContext` from the Reactor Context. The Spring Security 6.5 docs illustrate:

```java
Authentication alice = new TestingAuthenticationToken(
        "alice", "n/a", "DOC_READ");

Mono<String> who = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(who)
        .expectNext("alice")
        .verifyComplete();
```

This is a **unit test snippet**, requiring Spring Security, Reactor, and `reactor-test` imports. It tests context propagation, **not that method security annotations are applied**: no protected Spring bean is called.

### Meaning of `contextWrite`

```text
Publisher declared in test:
    service.read("42")
         |
         v
.contextWrite(withAuthentication(alice))
         |
         v
StepVerifier.subscribe()
         |
         v
Interceptor reads Authentication from Reactor Context
         |
         +-- GRANTED -> Mono<String> emits data
         |
         +-- DENIED  -> Mono errors, emits no data
```

`contextWrite(...)` sets the context for **upstream** operators of that subscription. Never mutate `SecurityContextHolder.getContext()` on the test thread and expect every scheduler to pick it up.

### Why Not Use `block()` for Testing?

```java
// This can check the value, yet misses reactive signal verification.
String value = service.read("42").block();
```

`StepVerifier` lets you assert exact `expectNext`, `verifyComplete`, `expectError`, `expectNoEvent`, `thenCancel`, deadlines, and virtual time. It fits `Mono`/`Flux` APIs better than calling `block()` and catching exceptions synchronously in JUnit. Using `block()` as a helper on a test thread is not always wrong, yet it is not the best tool here and must never be used on the WebFlux event loop.

## 4. Essential Facts About Spring Security Versions

- Spring Security 5.8 introduced `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` for the new infrastructure; in 5.8 this flag defaults to **false**.
- Starting in Spring Security 6.0, `useAuthorizationManager` defaults to **true**. In 6.x, `@EnableReactiveMethodSecurity` is the concise configuration.
- The 7.0 JavaDoc also lists `true` as the default; when upgrading to 7.x, verify the specific minor/BOM APIs and run regression tests.
- In Java reactive method security, protected methods should return a `Publisher`: `Mono<T>` or `Flux<T>`, to integrate with Reactor Context.
- `@EnableWebFluxSecurity`/`SecurityWebFilterChain` **do not replace** `@EnableReactiveMethodSecurity`.
- `@EnableMethodSecurity` is for standard synchronous method security; do not assume it substitutes for reactive WebFlux security.

### Why Version Matters for Tests

A 5.8 project using legacy infrastructure can differ in extension points and reactive expression support compared to the `AuthorizationManager` engine. When testing custom beans returning `Mono<Boolean>`, confirm `useAuthorizationManager = true` is set on 5.8 or that you are running 6.x+.

### Sample Project

Most examples in this lesson use Spring Boot **3.5.16** (Security 6.x managed by the BOM), Java 17, JUnit 5, and `reactor-test`. This is the final OSS-supported release of the Boot 3.5 line per Spring's June 25, 2026 announcement, intended for learning demos. For new production systems, use an actively supported Boot line and verify matching APIs. Never force-override `spring-security-*` artifacts alone to major 7.x inside Boot 3.5.

## 5. `StepVerifier`: Core Assertion Methods

| API | Meaning | Security Use Case |
| --- | --- | --- |
| `StepVerifier.create(publisher)` | Subscribes and records expectations | Required for protected `Mono`/`Flux` |
| `expectNext(value)` | Next emitted item must match | GRANT emits expected document |
| `expectNextMatches(predicate)` | Inspects record/projection | GRANT matches tenant/owner |
| `expectNextCount(n)` | Asserts element count | `Flux` tests; do not replace ID assertions |
| `expectComplete()` + `verify()` | Source completes | Stream authorized and finished |
| `verifyComplete()` | Shorthand for `expectComplete` + `verify` | Successful `Mono`/`Flux` |
| `expectError(AccessDeniedException.class)` | Terminal signal is access error | Method denial |
| `expectErrorMatches(...)` | Inspects subtype/cause/message | Different Spring versions or reasons |
| `verifyError(...)` | Shorthand error assertion | Denied path |
| `expectNoEvent(Duration)` | No signals during interval | Delays/backpressure; watch `onSubscribe` |
| `thenCancel()` | Cancels subscription | Infinite `Flux` / timeouts |
| `withVirtualTime(supplier)` | Virtual clock | Deterministic retries/timeouts/delays |

A common testing mistake:

```java
StepVerifier.create(service.read("42"))
        .expectNext("doc:42")
        .verifyComplete();
```

If the service is invoked via a Spring proxy without a Reactor `SecurityContext`, the test fails due to missing `Authentication`. **Never "fix" this by instantiating the service with `new`**; construct a principal and attach it to the Reactor Context.

Conversely, if a test calls `new DocumentService()`, `@PreAuthorize` never runs; such a passing test proves nothing about Spring Security.

## 6. Complete Project: Java 17 + Spring Boot WebFlux + `StepVerifier`

The following project creates a **real Spring-managed bean** with method annotations and tests it via `@SpringBootTest` without starting an HTTP server. It includes a policy bean returning `Mono<Boolean>` to test tenant rules and fail-closed handling.

```text
reactive-stepverifier-security/
├── pom.xml
└── src/
    ├── main/java/example/security/
    │   ├── ReactiveSecurityApplication.java
    │   ├── DocumentService.java
    │   └── TenantPolicy.java
    └── test/java/example/security/
        └── DocumentMethodSecurityTest.java
```

### 6.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactive-stepverifier-security</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The `reactor-test` dependency provides `StepVerifier`. `spring-boot-starter-test` provides JUnit 5 and Spring test utilities; `spring-security-test` helps with `@WithMockUser` and authentication test helpers. Because the project uses Security 6.x, `useAuthorizationManager=true` is not needed.

### 6.2. `ReactiveSecurityApplication.java`

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;

@SpringBootApplication
@EnableReactiveMethodSecurity
public class ReactiveSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
```

The `EnableReactiveMethodSecurity` import can also be written on one line:

```java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

**Key point:** the annotation sits on a configuration class scanned by Spring Boot; it registers the method interceptors. `@SpringBootApplication` alone does not imply method-level security is active. No HTTP server needs to start inside `@SpringBootTest(webEnvironment=NONE)` unit/integration tests.

### 6.3. `DocumentService.java`

```java
package example.security;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final AtomicInteger readSubscriptions = new AtomicInteger();
    private final AtomicInteger auditSubscriptions = new AtomicInteger();
    private final AtomicInteger tenantSubscriptions = new AtomicInteger();

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> read(String documentId) {
        return Mono.defer(() -> {
            readSubscriptions.incrementAndGet();
            return Mono.just("doc:" + documentId);
        });
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> emptyWhenAllowed() {
        return Mono.empty();
    }

    @PreAuthorize("hasAuthority('AUDIT_READ')")
    public Flux<String> audit() {
        return Flux.defer(() -> {
            auditSubscriptions.incrementAndGet();
            return Flux.just("audit:1", "audit:2");
        });
    }

    @PreAuthorize("@tenantPolicy.canRead(authentication, #p0)")
    public Mono<String> readTenant(String requestedTenant) {
        return Mono.defer(() -> {
            tenantSubscriptions.incrementAndGet();
            return Mono.just("tenant:" + requestedTenant);
        });
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Mono<OwnedDocument> owned(String id) {
        return Mono.defer(() ->
                Mono.just(new OwnedDocument(id, "alice")));
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
    }

    public int getReadSubscriptions() {
        return readSubscriptions.get();
    }

    public int getAuditSubscriptions() {
        return auditSubscriptions.get();
    }

    public int getTenantSubscriptions() {
        return tenantSubscriptions.get();
    }

    public static final class OwnedDocument {

        private final String id;
        private final String owner;

        public OwnedDocument(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }
}
```

**Why `Mono.defer` and `Flux.defer`?**

- `Mono.defer(...)` increments the counter and creates the value only upon subscription.
- If `@PreAuthorize` denies **before the business source is subscribed to**, `readSubscriptions` does not increment.
- `Flux.defer` does the same to prove no audit events are emitted when the caller lacks `AUDIT_READ`.
- Getter counters are not production security proof; they measure side effects in tests.
- `owned` uses `@PostAuthorize` to verify the owner on the returned value. Because it may already have constructed/read the object before checking, it is **not** suitable for protecting side-effecting mutations.
- `currentUser` demonstrates retrieving `Authentication` from Reactor Context during execution.

`readTenant` calls the `tenantPolicy` bean via SpEL. `#p0` refers to the first method parameter positionally, avoiding reliance on parameter-name metadata. Production systems should use richer object-level policies and verify tenants via server-side memberships rather than trusting client-supplied tenant names.

### 6.4. `TenantPolicy.java`

```java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("tenantPolicy")
public class TenantPolicy {

    public Mono<Boolean> canRead(
            Authentication authentication, String requestedTenant) {

        if (authentication == null || requestedTenant == null) {
            return Mono.just(false);
        }

        Mono<Boolean> decision = switch (requestedTenant) {
            case "no-decision" -> Mono.empty();
            case "offline" -> Mono.error(
                    new IllegalStateException("PDP unavailable"));
            default -> Mono.just(
                    "alpha".equals(requestedTenant)
                    && "alice".equals(authentication.getName())
                    && authentication.getAuthorities().stream()
                        .anyMatch(a -> "DOC_READ"
                                .equals(a.getAuthority())));
        };

        // Only an explicit Boolean true may grant permission.
        return decision.defaultIfEmpty(false)
                .onErrorReturn(false);
    }
}
```

This is a **simulated policy**, not a complete production design. It exercises three key branches:

1. `alpha` + Alice + `DOC_READ` → `Mono.just(true)`.
2. `no-decision` → `Mono.empty()`, normalized to `false`.
3. `offline` → `Mono.error(...)`, normalized to `false`.

Real PDP failures should record typed outcomes/metrics separately (never confused with policy-based DENY), yet **must never flip to `true`**. In production, tenancy must rely on verified `Authentication`, trusted memberships/ACLs, resource tenant, and action; the hardcoded `"alpha"` string simply keeps the test transparent.

## 7. Writing `StepVerifier` Tests Against a Real Spring-Managed Service

File `src/test/java/example/security/DocumentMethodSecurityTest.java`:

```java
package example.security;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService service;

    private static Authentication user(String name, String... authorities) {
        return new UsernamePasswordAuthenticationToken(
                name, "n/a",
                AuthorityUtils.createAuthorityList(authorities));
    }

    private static <T> Mono<T> as(
            Mono<T> source, Authentication authentication) {
        return source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication));
    }

    private static <T> Flux<T> as(
            Flux<T> source, Authentication authentication) {
        return source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication));
    }

    @Test
    void readerWithExactAuthorityCanRead() {
        StepVerifier.create(as(
                service.read("42"), user("alice", "DOC_READ")))
            .expectNext("doc:42")
            .verifyComplete();
    }

    @Test
    void viewerDeniedBeforeSourceIsSubscribed() {
        int before = service.getReadSubscriptions();

        StepVerifier.create(as(
                service.read("42"), user("viewer", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, service.getReadSubscriptions());
    }

    @Test
    void rolePrefixIsNotExactDocReadAuthority() {
        StepVerifier.create(as(
                service.read("42"), user("alice", "ROLE_DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void noAuthenticationMustNotGrantAccess() {
        StepVerifier.create(service.read("42"))
            .expectError()
            .verify();
    }

    @Test
    void allowedEmptyResultIsCompletionNotDenial() {
        StepVerifier.create(as(
                service.emptyWhenAllowed(), user("alice", "DOC_READ")))
            .verifyComplete();
    }

    @Test
    void missingAuthorityDoesNotTurnEmptyIntoSuccess() {
        StepVerifier.create(as(
                service.emptyWhenAllowed(), user("viewer", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void auditFluxCanEmitTwoItemsWhenGranted() {
        StepVerifier.create(as(
                service.audit(), user("auditor", "AUDIT_READ")))
            .expectNext("audit:1", "audit:2")
            .verifyComplete();
    }

    @Test
    void auditFluxDenialEmitsNoProtectedItems() {
        int before = service.getAuditSubscriptions();

        StepVerifier.create(as(
                service.audit(), user("viewer", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, service.getAuditSubscriptions());
    }

    @Test
    void postAuthorizeAcceptsRealOwner() {
        StepVerifier.create(as(
                service.owned("42"), user("alice", "DOC_READ")))
            .expectNextMatches(doc ->
                "42".equals(doc.getId())
                    && "alice".equals(doc.getOwner()))
            .verifyComplete();
    }

    @Test
    void postAuthorizeDeniesSomeoneElseDocument() {
        StepVerifier.create(as(
                service.owned("42"), user("bob", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void reactiveTenantPolicyGrantsValidCombination() {
        StepVerifier.create(as(
                service.readTenant("alpha"), user("alice", "DOC_READ")))
            .expectNext("tenant:alpha")
            .verifyComplete();
    }

    @Test
    void reactiveTenantPolicyDeniesWrongTenant() {
        int before = service.getTenantSubscriptions();

        StepVerifier.create(as(
                service.readTenant("beta"), user("alice", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, service.getTenantSubscriptions());
    }

    @Test
    void emptyPolicyDecisionNeverBecomesPermit() {
        StepVerifier.create(as(
                service.readTenant("no-decision"),
                user("alice", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void policyBackendErrorNeverBecomesPermit() {
        StepVerifier.create(as(
                service.readTenant("offline"),
                user("alice", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void contextSurvivesReactiveSchedulerSwitch() {
        StepVerifier.create(as(
                service.currentUser(), user("alice", "DOC_READ"))
                    .publishOn(Schedulers.parallel()))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void sameColdPublisherUsesEachSubscribersAuthentication() {
        Mono<String> source = service.read("shared-id");

        StepVerifier.create(as(
                source, user("alice", "DOC_READ")))
            .expectNext("doc:shared-id")
            .verifyComplete();

        StepVerifier.create(as(
                source, user("bob", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

There are **16 `@Test` methods**, covering grant, deny, role/authority, missing `Authentication`, empty values, `Flux`, `@PostAuthorize`, reactive policy true/empty/error, scheduler switching, and two different subscribers on the same cold publisher.

### Details That Make These Tests Genuinely Valuable

- Tests use `@SpringBootTest` and `@Autowired DocumentService`. This is a **Spring-managed bean**, invoked through its interceptor. Never replace it with `new DocumentService()`.
- `new UsernamePasswordAuthenticationToken(name, "n/a", grantedAuthorities)` with the three-argument constructor produces an `Authentication` marked authenticated. This is a **mock identity for unit/integration tests**, not real password/JWT verification.
- `contextWrite(withAuthentication(authentication))` injects the user into Reactor Context **per subscription**.
- `expectError(AccessDeniedException.class)` also matches `AccessDeniedException` subtypes such as version-specific authorization exceptions.
- Unchanged counters prove the `Mono.defer`/`Flux.defer` data sources were not subscribed when the before-method guard denied. Tests asserting only HTTP 403 fail to catch side effects that already ran.
- `@PostAuthorize` evaluates **after the value is produced**, so you cannot assert zero reads like `@PreAuthorize`. This lesson uses it strictly on a read-only DTO.
- `sameColdPublisher...` verifies the publisher does not remember Alice's PERMIT and replay it to Bob. Never call `.cache()` on a singleton's shared authorization `Publisher`.
- These tests do not rely on an HTTP route guard standing in for the method layer; they exercise the proxy directly.

### Compile/Runtime Notes

This project is **runnable-by-design** with Maven/Java 17 and Spring Security 6.x APIs. If running on a newer Spring branch, verify `@PostAuthorize`/reactive SpEL compatibility and BOM versions. This lesson does not claim the code was compiled and executed in the authoring environment; the assertions describe expected behavior that must be executed in a real project.

## 8. Run Commands and What to Observe

From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn -q clean test
```

Maven/Surefire outputs detailed reports under `target/surefire-reports`. Expected outcomes: grant tests emit expected values, deny tests terminate with the expected errors, the owner test withholds the document from Bob, policy empty/error never become PERMIT, and counters stay unchanged when guards deny.

Do not fabricate Maven stdout because output depends on Maven, plugins, and environment; verify via actual test reports. When the suite fails, **never change `expectError` to `expectNext` to force green tests**: first inspect `@EnableReactiveMethodSecurity`, proxies, Reactor Context, and policy expressions.

### Build Errors to Check

- `reactor.test.StepVerifier` not found → missing test-scoped `reactor-test`.
- `ReactiveSecurityContextHolder` not found → missing or mismatched Spring Security reactive dependencies.
- `@EnableReactiveMethodSecurity` has no effect → configuration class not scanned or test does not load the right application context.
- `@PreAuthorize` SpEL parse error → check method visibility, bean name `tenantPolicy`, and `#p0`.
- Unexpected Context errors → verify the service is proxied and authentication is attached before subscription.
- No tests executed → check test file/class naming, JUnit 5/Surefire, and Maven Surefire reports.
- If Boot 3.5.16 is replaced because the project upgraded to Boot 4.x, update the BOM consistently instead of overriding a single Spring Security artifact.

## 9. How Does `StepVerifier` Test `@PreAuthorize` Under the Hood?

Actual call flow:

```text
1. JUnit creates test
2. Spring test context injects proxied DocumentService
3. Test calls service.read("42") -> publisher with method-security advice
4. Test applies contextWrite(withAuthentication(reader/viewer))
5. StepVerifier subscribes
6. Advice reads Authentication from Reactor Context
7. SpEL evaluates hasAuthority('DOC_READ')
8a. GRANT -> subscribes business Mono.defer -> onNext("doc:42")
8b. DENY  -> signals AccessDeniedException, does not subscribe business Mono.defer
9. StepVerifier asserts onNext/onError/onComplete in exact order
```

**Why have both positive and negative tests?** If method security is disabled, the positive test still passes because the service returns `doc:42`; only the negative test `viewerDenied...` catches the bypass. Likewise, testing only with an over-privileged admin misses unregistered `@PreAuthorize` annotations.

### Deliberate Negative Control

On a temporary test branch, remove `@EnableReactiveMethodSecurity` while keeping HTTP security: the direct method test for `viewer` will stop denying if no other guard exists. This proves the tests **measure the intended layer**. Never make this change in production; use it strictly as an experiment and revert.

### When DENY Is Not `AccessDeniedException`?

If a policy bean throws an unhandled network/timeout exception, upstream can emit a technical error rather than `AccessDeniedException`. Tests must then match the API contract while asserting **zero `onNext` of protected data**. In this lesson, `TenantPolicy` maps empty/error to `false` so the method guard emits `AccessDeniedException`.

## 10. When to Use `@WithMockUser` Instead of Manual `contextWrite`?

Spring Security Test provides `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, and `@WithSecurityContext`. For reactive method security, you need not only `WithSecurityContextTestExecutionListener` for test-thread context, but also `ReactorContextTestExecutionListener` to populate `ReactiveSecurityContextHolder`.

Conceptual example:

```java
@Test
@WithMockUser(username = "alice", authorities = "DOC_READ")
void canReadWithMockUserListener() {
    StepVerifier.create(service.read("42"))
            .expectNext("doc:42")
            .verifyComplete();
}
```

**Condition:** the project's test context must include the matching version of `ReactorContextTestExecutionListener`; if declaring `@TestExecutionListeners` manually, do not accidentally drop this listener. When controlling exact identities **per subscriber**, direct `contextWrite(withAuthentication(...))` as in the project above is often clearer and less listener-dependent.

### Illustrative Test Listeners (Integration Snippet)

```java
@TestExecutionListeners(
    listeners = {
        WithSecurityContextTestExecutionListener.class,
        ReactorContextTestExecutionListener.class
    },
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

This snippet requires importing both listeners from `org.springframework.security.test.context.support` and Spring Test's `TestExecutionListeners`. Under Spring Boot defaults, the required listeners may already be registered; do not duplicate them blindly. For custom authentication/JWT principals, `@WithSecurityContext` or `@WithUserDetails` fits better than default `@WithMockUser`.

### Do Not Confuse Test Identities with Real Authentication

- `@WithMockUser` does not verify JWT signatures, `iss`, `aud`, or real user credentials.
- Test-constructed `TestingAuthenticationToken` or `UsernamePasswordAuthenticationToken` instances do not test the login flow either.
- When testing an OAuth2 Resource Server, add `WebTestClient` or decoder tests with signed test JWTs and the security filter chain.
- When testing tenant access, `@WithMockUser` `"alice"` does not automatically hold `alpha` tenant membership unless test data/policies define it.

**HTTP test distinction:** if calling a live server on another thread/socket, `@WithMockUser` on the JUnit thread does not automatically authenticate HTTP requests. Use `WebTestClient` security test support or send Basic/Bearer credentials on the request.

## 11. `@PostAuthorize`: Testing Result Permissions Without Masking Side Effects

`@PostAuthorize` inspects the value **after** method invocation and before returning it to the caller. Example:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<OwnedDocument> getDocument(String id) {
    return repository.findById(id);
}
```

In our project, `OwnedDocument#getOwner()` lets SpEL evaluate the `owner` property. Having a standard JavaBean getter makes the expression simpler and clearer than assuming parser support for every record accessor form.

`StepVerifier` with Alice:

```java
StepVerifier.create(service.owned("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("alice", "DOC_READ"))))
    .expectNextMatches(doc -> "alice".equals(doc.getOwner()))
    .verifyComplete();
```

`StepVerifier` with Bob:

```java
StepVerifier.create(service.owned("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("bob", "DOC_READ"))))
    .expectError(AccessDeniedException.class)
    .verify();
```

This is a **snippet tied to the section 6–7 project**: `user(...)` is the test's private helper. In real tests, verify Bob's document was not published externally prior to the error.

### What Not to Do

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Receipt> transferMoney(...) {
    // Write operation already executed before post-check.
}
```

Even though the caller receives 403, the funds may already have transferred. Use `@PreAuthorize` before execution along with transactions/conditional updates when needed; `@PostAuthorize` is not a default full-side-effect rollback mechanism.

### When Methods Return `Flux`

When applying `@PostAuthorize`/`@PostFilter` to multiple results, test **per-element behavior as well as errors and partial emissions** under your version's contract. Especially with `@PostFilter` after DB pagination, counts and metadata can break; prefer query-time authorization for search, counts, and stats. This lesson applies `@PreAuthorize` on `Flux` to prove no items emit before the method guard allows access.

## 12. Proving Zero Data Was Read on DENY

Asserting only:

```java
StepVerifier.create(viewerPublisher)
        .expectError(AccessDeniedException.class)
        .verify();
```

proves the stream terminated with an access error, yet **does not prove internal work never ran** if the method performed side effects before returning the `Publisher`.

A proper reactive source:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<String> read(String id) {
    return Mono.defer(() -> {
        readSubscriptions.incrementAndGet();
        return repository.findTitle(id);
    });
}
```

With the test:

```java
int before = service.getReadSubscriptions();

StepVerifier.create(service.read("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer)))
    .expectError(AccessDeniedException.class)
    .verify();

assertEquals(before, service.getReadSubscriptions());
```

Here the counter increments **when subscribing to the business source**. If `@PreAuthorize` denies beforehand, the source is never subscribed to. If a method performs synchronous DB reads/writes **before returning the `Mono`**, subscription counters can miss it; move side effects properly inside the publisher and add transaction/data-level tests.

### Hot Sources and Early Side Effects

A hot `Flux` or non-reactive call triggered immediately upon method invocation can produce data before subscription-time authorization runs. Design protected data paths with cold/deferred publishers:

```java
public Mono<Document> read(String id) {
    return Mono.defer(() -> repository.findById(id));
}
```

If `repository.findById(id)` already returns a cold `Mono`, `Mono.defer` may be redundant; its value here is making side-effect timing explicit.

Never interpret a policy backend's `Mono.empty()` as "no document exists, so permit". One is an authorization decision; the other is a business result. They must be handled separately.

## 13. `StepVerifier` with `Flux` and Multiple Elements

A service:

```java
@PreAuthorize("hasAuthority('AUDIT_READ')")
public Flux<String> audit() {
    return Flux.just("audit:1", "audit:2");
}
```

Authorized caller:

```java
StepVerifier.create(service.audit()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auditor)))
    .expectNext("audit:1", "audit:2")
    .verifyComplete();
```

Unauthorized caller:

```java
StepVerifier.create(service.audit()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer)))
    .expectError(AccessDeniedException.class)
    .verify();
```

`StepVerifier` requires an **immediate terminal error**, accepting zero `onNext` signals before the error in this branch. If the `Flux` emitted partial data before erroring, `expectError` fails because unexpected events arrived first.

### Asserting Counts Is Insufficient to Protect Individual Items

`expectNextCount(2)` proves only that 2 items arrived, not that they belong to the right tenant or owner. For sensitive data, use `expectNextMatches(doc -> ...)`, `recordWith(...)`/`consumeRecordedWith(...)`, or list exact IDs to catch unauthorized records.

### Infinite `Flux`

For streams like `Flux.interval(...)`, tests need `thenCancel` or virtual time rather than hanging on `verifyComplete()`. When method security denies, expect the error before any item emits; when granted, assert a bounded number of items or deadline and then cancel.

## 14. Testing Policy Beans Returning `Mono<Boolean>`

AuthorizationManager-based reactive method security allows method security expressions to invoke beans returning `Mono<Boolean>`, e.g.:

```java
@PreAuthorize("@tenantPolicy.canRead(authentication, #p0)")
public Mono<String> readTenant(String tenant) {
    return repository.loadForTenant(tenant);
}
```

However, **never** assume every `Mono.empty()` from a policy bean automatically means a policy DENY. Per Spring Security, it can signal **abstain**. When a policy is a mandatory guard, the adapter must normalize:

```java
Mono<Boolean> safeDecision = policyClient.check(subject, tenant)
        .defaultIfEmpty(false)
        .onErrorReturn(false);
```

In a real domain model, preserve error/timeout as a typed outcome for monitoring or returning 503 instead of 403; the invariant is never producing PERMIT.

### Three Mandatory Tests

- Valid user/role/tenant: `Mono.just(true)` → emits business value.
- Backend returns empty: `Mono.empty()` normalized to `false` → `AccessDeniedException`, repository never runs.
- Backend returns error: `Mono.error(...)` normalized to `false` → denied; if the project propagates 503, the assertion differs while still emitting zero business values.

In `TenantPolicy`, `"offline"` and `"no-decision"` are fixed test hooks, not valid tenants. Never carry such special strings into production.

### Timeouts with Policy Beans

Integration snippet:

```java
Mono<Boolean> safeRemoteDecision =
        policyClient.checkRead(subject, resource)
            .timeout(Duration.ofMillis(250))
            .defaultIfEmpty(false)
            .onErrorReturn(false);
```

`Duration` requires importing `java.time.Duration`; 250ms is illustrative. Timeouts emit an error; `onErrorReturn(false)` ensures access is never granted. When adding circuit breakers or retries, still bound the overall deadline and never fall back to `true`.

## 15. Testing Timeouts with `StepVerifier.withVirtualTime`

For reactive publishers using `delayElement`/`Mono.delay`/`timeout`, use `withVirtualTime` so tests do not wait on wall-clock time.

Standalone Reactor illustration:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(5))
            .map(ignored -> true)
            .timeout(Duration.ofSeconds(2))
            .onErrorReturn(false))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(false)
    .verifyComplete();
```

This is a **JUnit/`reactor-test` snippet** requiring `Duration`, `Mono`, and `StepVerifier` imports. Construct the publisher **inside the `Supplier`** passed to `withVirtualTime` so the virtual scheduler replaces the clock before sources or operators subscribe.

It proves that if a check does not finish within 2 virtual seconds, the decision becomes `false` rather than PERMIT. This alone does not test the method-security proxy; for integration tests, have the policy bean build its source at subscription time and have `StepVerifier` subscribe to the proxied service.

### `withVirtualTime` Caveats

- Never construct a time-based publisher before `withVirtualTime` installs its virtual scheduler.
- If using a custom scheduler not swapped by virtual time, tests may still wait in real time.
- `thenAwait` advances the virtual clock; sources with backpressure may also need `thenRequest(n)`.
- For real remote HTTP client timeouts, virtual time does not replace testing connect/read timeouts against a stub server; those are two separate test layers.
- Never run `Mono.never()` with `verifyComplete()` and no timeout: it hangs forever.

### Timeouts and HTTP Status Codes

`StepVerifier` on the service observes reactive errors/decisions. HTTP 503/403/401 belong to the WebFlux filter chain and exception mapping, requiring `WebTestClient` to verify. A technical error does not automatically become 403 unless the policy layer converts it into a negative authorization decision.

## 16. Preserving Reactor Context Across Scheduler Switches

Reactor chains can switch threads via `publishOn`/`subscribeOn`. Reactive method security reads `Authentication` from Reactor Context, not servlet ThreadLocals.

A test:

```java
StepVerifier.create(
        service.currentUser()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice", "DOC_READ")))
            .publishOn(Schedulers.parallel()))
    .expectNext("alice")
    .verifyComplete();
```

Snippet tied to the project (requiring the test's `user` helper). Because the subscription context travels along the chain, the method still sees Alice after switching schedulers. Run tests against the actual proxied service bean; if an implementation reads `SecurityContextHolder.getContext()` on the worker thread, it may see the wrong principal or `null`.

### Using Context Does Not Turn a Raw Tenant into a Trusted Tenant

An app can store `AuthorizedTenantScope` in Reactor Context, provided that scope is derived from a verified `Authentication` plus server-side membership—never `X-Tenant-Id` alone. `StepVerifier` tests should verify that altering a raw tenant header never alters the authorized scope, tested against the project's real `TenantResolver`.

### `retry`/`repeat` and Multiple Subscriptions

A cold publisher can be subscribed to multiple times. `retry`/`repeat` create fresh subscriptions that can re-evaluate policies. Never cache a `PERMIT` for user A and serve it to user B; if caching, key by subject/tenant/resource/action/entitlement version with a TTL.

## 17. Two Subscribers on One Publisher: A High-Value Test

`Mono` is normally cold. When the same source is subscribed to under two different Reactor Contexts, method security must evaluate permissions **per subscriber**, never holding a global `Authentication`.

```java
Mono<String> shared = service.read("42");

StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
                user("alice", "DOC_READ"))))
    .expectNext("doc:42")
    .verifyComplete();

StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
                user("bob", "ROLE_VIEWER"))))
    .expectError(AccessDeniedException.class)
    .verify();
```

If the source or decision is mis-scoped with `.cache()`, Bob can receive Alice's result. A singleton service holding a `Mono<Boolean> cachedDecision` initialized on the first request is dangerous. Instead of caching a shared publisher, cache decisions keyed properly by subject/tenant/resource/action/revision with policy-compliant lifetimes.

**Warning:** depending on source design, reusing a `Publisher` created outside context may carry other state. This lesson uses cold sources and does not recommend sharing single publishers for protected production data. The test proves **no cross-subscriber grant leakage**.

## 18. Testing Self-Invocation and Proxy Bypass

Counterexample:

```java
@Service
class DocumentWorkflow {

    public Mono<String> outer(String id) {
        return protectedInner(id);
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> protectedInner(String id) {
        return Mono.just("doc:" + id);
    }
}
```

`outer()` calls `protectedInner()` via `this`; internal calls can bypass the Spring AOP proxy, so `protectedInner`'s interceptor never executes.

**Tests calling only `service.protectedInner(...)` are insufficient** if real routes invoke `service.outer(...)`. Write negative tests along actual runtime call paths.

Better solution:

```java
@Service
class ProtectedDocumentReader {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> read(String id) {
        return Mono.just("doc:" + id);
    }
}

@Service
class DocumentWorkflow {

    private final ProtectedDocumentReader reader;

    DocumentWorkflow(ProtectedDocumentReader reader) {
        this.reader = reader;
    }

    public Mono<String> outer(String id) {
        return reader.read(id); // Calls through another proxied bean.
    }
}
```

This is an **integration snippet**; dependencies and annotations need imports. Tests inject `DocumentWorkflow` and invoke `outer` under reader/viewer `Authentication`: `viewer` must receive `AccessDeniedException`. Never instantiate `new ProtectedDocumentReader()`; Spring applies advisors only to context-managed beans.

### `private`/`final` Methods

Standard Spring AOP proxies do not intercept `private` methods. `final` classes/methods also restrict class-based proxies. Before suspecting `StepVerifier`, check method visibility, proxy class, `proxyTargetClass` configuration, and whether the Java/Kotlin class can be proxied.

## 19. Distinguishing Missing `Authentication` from Missing Authority

An unauthenticated user and an authenticated user lacking `DOC_READ` are different cases:

| Case | Direct `StepVerifier` Method Test | WebFlux HTTP |
| --- | --- | --- |
| No `Authentication` in Reactor Context | Usually an authn/authz terminal error; check version contract | Typically 401 if route requires auth |
| Authenticated viewer lacking `DOC_READ` | `AccessDeniedException` | Typically 403 |
| Authenticated reader with `DOC_READ` | Data + complete | Typically 200 if controller succeeds |
| Policy bean timeout | Error/deny per adapter; no data | 503 or 403 depending on mapping |
| Resource missing within authorized scope | Business `Mono.empty()` or not-found mapping | 404/empty per API contract |
| Resource in another tenant | No access granted / no data disclosed | 403/404 per privacy policy |

In `noAuthenticationMustNotGrantAccess`, we avoid locking too tightly onto a single exception subtype because versions and advice paths can vary; the critical check is **zero protected `onNext` signals** and termination with an error. For an authenticated viewer, expecting `AccessDeniedException` is clearer.

**Never wrap authorization in `onErrorResume(ex -> Mono.empty())` and treat an empty-completing test as safe** if the controller afterward falls back to another data source or turns empty into allow. When returning 404 to mask resources, do so deliberately at the API boundary and test for zero data leaks.

## 20. `@WithMockUser`, `@WithUserDetails`, and Security Test Listeners

Many Spring test suites use annotations rather than building `Authentication` manually:

```java
@Test
@WithMockUser(username = "alice", authorities = {"DOC_READ"})
void readerAuthorizedWithListener() {
    StepVerifier.create(service.read("42"))
        .expectNext("doc:42")
        .verifyComplete();
}
```

To work with reactive method security:

- `@WithMockUser` creates a test `SecurityContext`; `ReactorContextTestExecutionListener` must run to bridge that test context into Reactor.
- If a test class sets `@TestExecutionListeners(listeners=..., mergeMode=REPLACE_DEFAULTS)` and omits the reactive listener, tests can fail with an empty Context.
- `@WithMockUser(roles={"ADMIN"})` creates `ROLE_ADMIN`; `authorities={"DOC_READ"}` creates literal `DOC_READ`. Never confuse `hasRole` with `hasAuthority`.
- `@WithUserDetails` requires the user in a test `UserDetailsService`; `@WithMockUser` does not require a real user.
- `@WithSecurityContext` lets you build custom principals/mock JWT claims in unit tests, yet does not verify real signatures.
- `contextWrite` is explicit when testing two users inside **one test** without relying on JUnit listeners.

### Do Not Mix ThreadLocal Principals

A test could combine `@WithMockUser("alice")` with `contextWrite(withAuthentication(bob))`, making intent murky. If intentionally verifying Reactor Context precedence, state the expectation clearly and isolate the two paths; otherwise pick one way to supply `Authentication` to reduce noise.

## 21. Testing with `WebTestClient` vs. `StepVerifier`

**`StepVerifier`** focuses on publishers and method advice. **`WebTestClient`** focuses on HTTP:

```java
web.get()
   .uri("/api/documents/42")
   .headers(headers ->
        headers.setBasicAuth("viewer", "pass"))
   .exchange()
   .expectStatus().isForbidden();
```

This is an integration snippet requiring a configured `web` client, an HTTP `SecurityWebFilterChain`, and valid credentials. It **does not replace** `StepVerifier` on the bean, because an HTTP filter may return 403 before the service method is ever invoked.

### Designing Integration Tests with Clear Boundaries

1. Enable `SecurityWebFilterChain` requiring authentication on `GET /api/**`.
2. Put `@PreAuthorize("hasAuthority('DOC_READ')")` on the service.
3. Authenticated reader with `DOC_READ` → endpoint returns 200.
4. Authenticated viewer without `DOC_READ` → endpoint returns 403 **from the method**, since HTTP allowed authenticated users through.
5. Anonymous → 401 from HTTP.
6. Requesting another tenant's document → 403/404 or response omitting the record per data policy.
7. Check service invocation counters and DB state to verify zero side effects.
8. For JWT Resource Servers, send test tokens through the security filter or use scoped mock support; `@WithMockUser` does not test decoder/signature/audience checks.

### `WebTestClient` Asserts Responses, Not All Backend Signals

`WebTestClient` verifies API statuses and bodies; it does not always reveal whether a publisher was subscribed to before denial. Use unit/integration `StepVerifier` tests with counters/mock repositories to verify the reactive layer precisely, then add HTTP tests for end-to-end coverage.

## 22. Testing Data Permissions, Tenants, and Object-Level Security

`@PreAuthorize("hasAuthority('DOC_READ')")` does not ensure Alice can view Bob's or tenant `beta`'s documents. Pair method security tests with repository policy tests:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public Mono<DocumentView> read(String id) {
    return repository.findByIdAndAuthorizedTenant(id);
}
```

This is an architectural snippet. `documentPolicy` should rely on verified principal, tenant membership, and server-side document metadata—never raw tenant/owner fields from requests.

Test matrix to seed:

| User | Tenant | Document | Relationship | Expected |
| --- | --- | --- | --- | --- |
| Alice | alpha | Doc 11 alpha | owner | PERMIT |
| Alice | alpha | Doc 12 alpha | shared READ | PERMIT |
| Alice | alpha | Doc 13 alpha | private Bob | DENY |
| Alice | alpha | Doc 21 beta | cross-tenant | DENY |
| Bob | beta | Doc 21 beta | owner | PERMIT |
| Viewer without `DOC_READ` | alpha | Doc 11 alpha | even if owner | DENY per functional policy |

When testing with `StepVerifier`, assert the exact document ID/tenant in emitted results rather than only `expectNextCount(1)`. Use `Mono.defer` in fake repositories with counters to verify queries never run when local guards deny.

### Avoiding TOCTOU on Mutations

If policy permits at T1 yet the document's owner/tenant/version changes at T2, writes may need conditional SQL/transactions to block races. Permission-only `StepVerifier` tests do not replace mutation consistency tests. For critical writes, assert affected row counts and data state after denials/races.

### Pagination and Aggregations

Method security only governs whether a method runs; once called, `Page.totalElements`, `count`, `facets`, and `sum` must be scoped just like lists. A `StepVerifier` test returning a `Flux<Document>` with valid IDs while returning an unscoped total count still leaks data via metadata.

## 23. `StepVerifier` and Reactor Logic Traps

When a policy expression depends on multiple reactive checks, watch carefully for:

| Operator | Authorization Risk |
| --- | --- |
| `Mono.zip(a, b)` | If one branch is empty, `zip` can complete empty; never treat that as permit |
| `defaultIfEmpty(true)` | Missing decision becomes ALLOW |
| `onErrorReturn(true)` | PDP outage becomes ALLOW |
| `filter(Boolean::booleanValue).switchIfEmpty(Mono.just(true))` | `DENY=false` gets filtered into empty and then granted |
| `Flux.all(...)` | On an empty stream, evaluates **`true`** by vacuous truth |
| `Flux.any(...)` | Passes if a single branch grants; never substitutes for mandatory AND |
| `hasElement()` | `Mono.just(false).hasElement()` still emits `true` |
| `thenReturn(true)` | Ignores upstream `Boolean` `false` and emits `true` |
| `Mono.when(...)` | Waits only for completion, does not AND boolean values |
| `Mono.cache()` | Can retain another subscriber's decision if the publisher is shared |
| Unbounded `retry()` | Amplifies load, adds latency, and mixes policy versions |

`StepVerifier` tests should include `Mono.just(true)`, `Mono.just(false)`, `Mono.empty()`, `Mono.error(...)`, and `Mono.never()` with bounded timeouts. Never conclude policy composition is safe from an all-`true` test suite.

Small test example:

```java
StepVerifier.create(
        Flux.<Boolean>empty().all(Boolean::booleanValue))
    .expectNext(true)
    .verifyComplete();
```

This is **accurate Reactor semantics**, yet **wrong if "no checks" is interpreted as PERMIT**. When checks are required, assert the list is non-empty before calling `all` and normalize missing decisions to `false`.

## 24. Regression Test Matrix for Reactive Method Security

| # | Test | Expected |
| --- | --- | --- |
| 1 | Caller with `DOC_READ` reads `Mono` document | Correct value + complete |
| 2 | Authenticated caller lacking `DOC_READ` | `AccessDenied` error |
| 3 | No `Authentication` | Emits no protected data |
| 4 | `ROLE_DOC_READ` differs from `DOC_READ` | DENY |
| 5 | `ADMIN` role does not imply `DOC_READ` | DENY if policy requires exact authority |
| 6 | `DOC_READ`, business `Mono.empty()` | Valid empty completion |
| 7 | Viewer, business `Mono.empty()` | `AccessDenied`, never becomes complete |
| 8 | `AUDIT_READ`, multi-item `Flux` | Exact IDs/items, complete |
| 9 | Viewer, audit `Flux` | Zero items, `AccessDenied` |
| 10 | `@PostAuthorize` matching owner | Emits resource |
| 11 | `@PostAuthorize` different owner | Does not emit resource |
| 12 | Policy bean `Mono.just(true)` | PERMIT |
| 13 | Policy bean `Mono.empty()` | Fail closed |
| 14 | Policy bean `Mono.error(...)` | Fail closed, log operational error |
| 15 | Policy bean timeout | Zero data or side effects |
| 16 | Tenant mismatch | DENY |
| 17 | Resource tenant mismatch | DENY |
| 18 | Self-invocation into protected method | Test detects bypass path |
| 19 | Object created manually via `new` | Do not assume annotation ran |
| 20 | Reactor `publishOn` | Identity stays intact |
| 21 | Same cold `Publisher`, two users | Permissions never reused |
| 22 | Mis-scoped decision cache | Test catches cross-user leakage |
| 23 | `@PostAuthorize` after a write | Test confirms side-effect risk; use pre-check |
| 24 | Authenticated HTTP viewer | 403 from service when HTTP requires authenticated only |
| 25 | Anonymous HTTP | 401 |
| 26 | Invalid JWT issuer/audience/signature | Blocked at auth boundary |
| 27 | `Flux.all` on empty checks | Never treated as PERMIT |
| 28 | `retry`/`repeat` multiple subscriptions | Never reuses stale `Authentication` |
| 29 | Owner changes between check and update | Conditional DB predicate protects |
| 30 | Spring Security version upgrade | Grant/deny semantics unchanged outside intentional migrations |

A production suite does not strictly need one `@Test` per row, yet it needs verifiable coverage. Testing **denial** and **zero side effects** matters just as much as happy-path tests.

## 25. Common Pitfalls When Learning `StepVerifier`

**Mistake 1 — Testing only `Mono.just("ok")`.** Does not test method security.

**Mistake 2 — Calling `new DocumentService()`.** Bypasses the Spring proxy, so `@PreAuthorize` may not apply.

**Mistake 3 — Forgetting `@EnableReactiveMethodSecurity`.** Annotations do not activate automatically just by adding the Spring Security dependency.

**Mistake 4 — Using the test thread's `SecurityContextHolder` inside a reactive chain.** Subscription context may run on another thread.

**Mistake 5 — Forgetting `contextWrite(withAuthentication(...))` in direct `StepVerifier` tests.** The publisher has no caller.

**Mistake 6 — Assuming `@WithMockUser` always populates Reactor Context even when test listeners are overridden.** Check `ReactorContextTestExecutionListener`.

**Mistake 7 — Calling `block()` in a WebFlux service or SpEL.** Can stall the event loop.

**Mistake 8 — Testing only "allowed" cases without DENY tests.** A skipped interceptor still leaves happy paths green.

**Mistake 9 — Having HTTP deny too and concluding the method guard ran.** Separate the HTTP and service boundaries.

**Mistake 10 — Asserting only the error without asserting side effects.** Data may have been written or fetched before denial.

**Mistake 11 — Using `@PostAuthorize` instead of pre-checks for mutations.** Post-checks can run too late.

**Mistake 12 — Confusing the `ROLE_` prefix.** `hasRole('ADMIN')` differs from `hasAuthority('ADMIN')`.

**Mistake 13 — Treating policy `Mono.empty()` as permit.** Absence of a decision is not a grant.

**Mistake 14 — Using `onErrorReturn(true)` for remote policies.** PDP outages open access.

**Mistake 15 — Using `Flux.all(empty)` returning `true` to AND required rules.** Guard against empty lists.

**Mistake 16 — Calling `hasElement()` on `Mono<Boolean>`.** Even `DENY=false` is an emitted element.

**Mistake 17 — Creating hot/shared cached `Publisher`s across multiple users.** Easily mixes `AuthorizationResult`/Context.

**Mistake 18 — Using `expectNextCount` instead of asserting exact IDs/tenants.** Misses unauthorized records.

**Mistake 19 — Using `StepVerifier.withVirtualTime` on an eagerly constructed `Publisher`.** The virtual scheduler may not take effect.

**Mistake 20 — Skipping dependency version checks after migrations.** Changes to method security infrastructure or test listeners can silently break behavior.

## 26. Pre-CI/CD Checklist

- [ ] Application includes `@EnableReactiveMethodSecurity` matching the pinned version.
- [ ] Service methods return `Mono`/`Flux` and reside on Spring-managed proxied beans.
- [ ] Negative tests exercise real call paths, without bypassing via `new` or `this.method()`.
- [ ] `StepVerifier` attaches verified Reactor Context at subscription.
- [ ] Tests cover both GRANT with valid authority and DENY with missing authority.
- [ ] Tests cover unauthenticated callers and role prefixes.
- [ ] Tests distinguish business `Mono.empty()` from policy decision `Mono.empty()`.
- [ ] Tests cover multi-item `Flux` and zero `onNext` emissions on DENY.
- [ ] Tests cover `@PostAuthorize` on read-only resources and side-effect risks.
- [ ] Tests confirm policy backend errors and timeouts fail closed.
- [ ] Assertions verify counters/repositories never execute on pre-check deny.
- [ ] Tenant, owner, ACL, and DB query scoping are tested independently.
- [ ] Reactor Context across schedulers, `retry`/`repeat`, or multiple subscribers is tested if used.
- [ ] Decision caching is tested for subject/tenant/resource/action/TTL scoping.
- [ ] End-to-end `WebTestClient` tests cover HTTP 401/403/503.
- [ ] JWT tests go beyond `@WithMockUser`, verifying issuer/audience/signature at the decoder boundary.
- [ ] `withVirtualTime` is used only for compatible reactive timers/timeouts.
- [ ] Maven/JUnit runs in CI against the pinned Spring Security/Reactor BOM.
- [ ] Tests are never turned green by swallowing errors into empty or falling back to allow.

**Conclusion:** Testing Reactive Method Security with `StepVerifier` goes beyond "reading back a value". By testing through a **real Spring AOP proxy**, injecting `Authentication` into the **Reactor Context**, asserting both **`onNext`/`onComplete` and `onError`**, and verifying **zero side effects on DENY**, you prove that `@PreAuthorize`, `@PostAuthorize`, and reactive policies genuinely enforce access control. Complement this with `WebTestClient` for the HTTP boundary and database/tenant tests to prove zero unauthorized data leaks.

## Official Documentation

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 7.1 — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — ReactiveSecurityContextHolder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — StepVerifier JavaDoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Spring Boot 3.5.16 Release Notes](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
