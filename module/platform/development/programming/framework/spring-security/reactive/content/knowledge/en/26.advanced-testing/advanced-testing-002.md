# Setting Up Reactor Context in Spring Security Reactive Unit Tests

> **Scope:** Java 17+, Project Reactor, Spring Security 6.x, JUnit 5, and `reactor-test`. The goal is to inject `Authentication` / `SecurityContext` into the **Reactor Context** of each subscription in unit tests, and properly test cases with/without identity, roles/scopes, and context loss/leak prevention. This lesson focuses on **unit testing** without an HTTP server; the end distinguishes it from `@WithMockUser` and `WebTestClient`. Spring Boot 3.3.13 is used in examples to illustrate Java 17-compatible APIs; for production in 2026, choose the latest supported and patched Spring Boot/Security version for your environment.

## 1. Why set up Reactor Context manually when testing?

In a WebFlux application, Spring Security normally installs `SecurityContext` into the Reactor Context during an HTTP flow that passes through the Security WebFilters. For example, a service reading the current user:

```java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

When running inside an authenticated request, the publisher can see the authentication established by Spring Security. However, a **plain JUnit unit test** instantiating the service with `new` has no `SecurityWebFilterChain`, HTTP request, WebSession, `ReactorContextWebFilter`, or Spring Test listener running beforehand. Therefore:

```java
StepVerifier.create(service.whoAmI())
    .expectNext("alice") // WRONG if nobody sets context for the subscription
    .verifyComplete();
```

has no basis to succeed. `ReactiveSecurityContextHolder.getContext()` normally produces an **empty** publisher if the subscription has no security context; if the service turns the empty state into an error, the test receives that error.

How to create an authenticated scenario for a unit test:

```java
Authentication alice =
    new TestingAuthenticationToken(
        "alice", "not-a-real-password", "ROLE_USER");

StepVerifier.create(
        service.whoAmI()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

This is a **code snippet** requiring imports and `service.whoAmI()`. It simulates an **already-authenticated** identity. It does **not** run password authentication, JWT signature verification, WebFilters, or CSRF checks. Testing those requires separate integration tests.

## 2. Reactor Context differs from ThreadLocal and Java method parameters

Before testing Spring Security, you must understand Project Reactor:

| Component | Scope / characteristics | Used for |
|---|---|---|
| `ThreadLocal<T>` | Bound to a Java thread; threads may be reused or change between callbacks | Imperative thread-bound code, if lifecycle is managed properly |
| `SecurityContextHolder` | By default strategy uses ThreadLocal | Spring Security Servlet/imperative or bridged integrations |
| `reactor.util.context.Context` | Immutable data attached to a **subscriber** and propagated on subscribe | Correlation ID, tracing metadata, reactive security context |
| `ContextView` | Read-only context data API | Reading values from `Mono.deferContextual` / `Flux.deferContextual` |
| `ReactiveSecurityContextHolder` | Reads/writes Spring `SecurityContext` in Reactor Context | Spring Security WebFlux/method security |
| `Authentication` | Principal, authorities, and authentication status | Describing an identity verified by a trusted mechanism |
| `SecurityContext` | Wraps `Authentication` | Carrying authentication in reactive scope |

In Reactor, **different subscriptions can run on the same thread** and **one subscription can hop across multiple threads**. Therefore, "putting the user into `SecurityContextHolder.getContext()` in `@BeforeEach`" is **not** a reliable way for a reactive service to read the user.

```text
Thread event-loop-1:
  subscription #1 (Alice)  -> Alice's Context
  subscription #2 (Bob)    -> Bob's Context

Thread boundedElastic-2:
  subscription #1 (Alice)  -> still has Alice's Context when passing through
                              Reactor operators that propagate context

Do not assume:
  event-loop-1 carries Alice -> every callback on that thread is Alice
```

### 2.1 Context is immutable and bound to the subscription

`Context` has `put`/`delete`, which return **a new Context**. It is not a mutable global map. When you write:

```java
Mono<String> pipeline = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("traceId", "none")))
    .contextWrite(ctx -> ctx.put("traceId", "t-309"));
```

`contextWrite` creates a new context for **upstream operators**. Context data flows "upward" along the subscription signal from downstream to upstream. It is **not** a value carried alongside each `onNext` or a ThreadLocal variable.

### 2.2 Placing `contextWrite` on the right side

```java
// RIGHT: context reader is upstream of contextWrite.
Mono<String> correct = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("k", "none")))
    .contextWrite(Context.of("k", "visible"));

// WRONG PLACEMENT: flatMap is downstream of contextWrite,
// so the inner publisher cannot see k written upstream.
Mono<String> wrong = Mono.just("go")
    .contextWrite(Context.of("k", "hidden"))
    .flatMap(ignored -> Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("k", "none"))));
```

Expected results:

```text
correct -> "visible"
wrong   -> "none"
```

**Practical rule for unit tests:** place `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))` at the **end of the pipeline under test**, after all relevant `map`/`flatMap`/`publishOn` operators. When you want to test context loss caused by a misplaced operator, intentionally place it elsewhere and assert the failure.

## 3. Spring Security APIs you must know

`org.springframework.security.core.context.ReactiveSecurityContextHolder` has four core APIs:

| Method | Return type | Meaning |
|---|---|---|
| `getContext()` | `Mono<SecurityContext>` | Retrieve the security context from the subscriber's Reactor Context |
| `withAuthentication(Authentication)` | `Context` | Create a Context containing a security context for an Authentication |
| `withSecurityContext(Mono<? extends SecurityContext>)` | `Context` | Create a Context containing a publisher that emits SecurityContext |
| `clearContext()` | `Function<Context, Context>` | Remove the Spring Security entry from the upstream Reactor Context |

Example:

```java
Authentication alice =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice", "unused-in-unit-test",
        List.of(new SimpleGrantedAuthority(
            "SCOPE_documents.read")));

Mono<String> current = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

StepVerifier.create(
        current.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

This is a snippet with implicit imports. `withAuthentication` is **not a login endpoint**: it does not call `ReactiveAuthenticationManager`, check passwords, call an IdP, or verify tokens. Use it only in tests isolating a component that assumes it already received a verified authentication, or in trusted framework code.

### 3.1 Do not guess Spring Security's internal key

`ReactiveSecurityContextHolder` manages its entry in Reactor Context internally. **Do not** write:

```java
// WRONG: not equivalent to the Spring Security API.
Context.of(SecurityContext.class, new SecurityContextImpl(alice));
```

Spring Security uses a key/value defined by its own implementation (including a `Mono<SecurityContext>` publisher). Always use `withAuthentication` or `withSecurityContext`; never hardcode a literal key name like `"SPRING_SECURITY_CONTEXT"` or guess from old blog posts.

### 3.2 `clearContext()` is not a "system-wide logout"

`clearContext` removes the security context **in the upstream Reactor Context of the publisher it is applied to**. It does not invalidate WebSessions, JWTs, cookies, or refresh tokens, emit revocation events, or clear other subscribers. It is very useful for testing a branch **without** a SecurityContext even when an outer branch had one.

### 3.3 With an existing SecurityContext

If you need to represent the full security context object:

```java
SecurityContext context = new SecurityContextImpl();
context.setAuthentication(alice);

Mono<String> pipeline = service.whoAmI()
    .contextWrite(ReactiveSecurityContextHolder
        .withSecurityContext(Mono.just(context)));
```

`withSecurityContext` accepts **`Mono<? extends SecurityContext>`**, not a `SecurityContext` directly. You can use `Mono.defer` / `Mono.fromSupplier` when you want to observe laziness or supply a context created at subscription time.

## 4. What does "no context" mean?

Three situations are often confused:

1. **No Reactor security context entry:** `ReactiveSecurityContextHolder.getContext()` completes empty.
2. **SecurityContext exists but Authentication is missing:** `getAuthentication()` may be `null`; the component must handle it instead of `map(SecurityContext::getAuthentication)` causing Reactor to emit a `NullPointerException`.
3. **AnonymousAuthenticationToken present:** some anonymous Authentication types have `isAuthenticated() == true` in object state; that does **not** prove the user truly authenticated.

When designing a self-checking service in a lab, use `AuthenticationTrustResolverImpl.isAnonymous(...)` or standard Spring Security authorization mechanisms to distinguish anonymous from real users. Never write only:

```java
// INSUFFICIENT to conclude a real user has logged in:
if (authentication.isAuthenticated()) { allow(); }
```

In real applications, prefer `@PreAuthorize`/`ReactiveAuthorizationManager` and business ACLs rather than fabricating authentication by trusting an `"X-User"` header.

## 5. Setting up a Java 17+ project to run unit tests without starting a server

This sample **needs no Spring Boot Application class, no controller/Netty**, and uses a plain Java service importing Spring Security. Spring Boot dependency management supplies compatible Spring Security/Reactor versions.

```text
reactive-context-unit-tests/
  settings.gradle
  build.gradle
  src/main/java/example/context/DocumentService.java
  src/test/java/example/context/DocumentServiceTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'reactive-context-unit-tests'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.context'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

// Do not apply the boot plugin to an application without a main method.
// Only import the BOM to manage dependency versions.
dependencyManagement {
    imports {
        mavenBom org.springframework.boot.gradle.plugin
            .SpringBootPlugin.BOM_COORDINATES
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Build file note:** The syntax `org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES` lives in the Gradle build script and comes from the Spring Boot plugin. Another option is applying `org.springframework.boot` and dependency-management and adding `spring-boot-starter-test`, but when there is no main class, avoid the `bootJar` task looking for a main class. The Java plugin's `test` task does not require running a web server.

Spring Boot 3.3.x BOM documentation manages `spring-security-core`, `reactor-core`, `reactor-test`, and JUnit 5. A shorter alternative is:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}
bootJar { enabled = false }
jar { enabled = true }
```

This is an **alternative build option** that still keeps `dependencies`/`repositories` from the main sample — do not paste both `plugins` blocks at the same time. For a pure unit-test lab, using only the Java plugin and the BOM as in the main sample avoids creating an unnecessary Spring Boot app.

### 5.1 Why is SecurityWebFilterChain not needed?

The tests here do not test HTTP authentication or CSRF. They test **a service reading Reactor SecurityContext**, supplying a simulated verified identity themselves. Therefore `@SpringBootTest`, `@AutoConfigureWebTestClient`, `@EnableWebFluxSecurity`, or `SecurityWebFilterChain` are not needed.

If you want to test real Security WebFilters, write integration tests with `WebTestClient` and `spring-security-test` (see Section 12); **do not** call pure unit tests E2E.

## 6. A service with business logic to test security context

**src/main/java/example/context/DocumentService.java**

```java
package example.context;

import java.util.Objects;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public final class DocumentService {

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public Mono<String> whoAmI() {
        return verifiedAuthentication()
            .map(Authentication::getName);
    }

    public Mono<String> read(String documentId) {
        return requireAuthority("SCOPE_documents.read")
            .map(auth -> "READ|" + documentId + "|" + auth.getName());
    }

    public Mono<String> write(String documentId) {
        return requireAuthority("SCOPE_documents.write")
            .map(auth -> "WRITE|" + documentId + "|" + auth.getName());
    }

    // Does not rely on ThreadLocal: traceId is this lab's context key.
    public Mono<String> whoAmIWithTrace() {
        return Mono.deferContextual(view ->
            whoAmI().map(name ->
                view.getOrDefault("traceId", "none")
                    + ":" + name));
    }

    private Mono<Authentication> verifiedAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(security ->
                Mono.justOrEmpty(security.getAuthentication()))
            .filter(auth -> auth.isAuthenticated()
                && !trust.isAnonymous(auth))
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authenticated Reactor SecurityContext required")));
    }

    private Mono<Authentication> requireAuthority(String authority) {
        return verifiedAuthentication().flatMap(auth -> {
            boolean granted = auth.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
            return granted ? Mono.just(auth)
                : Mono.error(new AccessDeniedException(
                    "Missing authority: " + authority));
        });
    }
}
```

**How to read the service:**

1. `ReactiveSecurityContextHolder.getContext()` is read inside the publisher at subscription time; no global object is captured in the constructor.
2. `flatMap(... Mono.justOrEmpty(...))` properly handles a `SecurityContext` containing a `null` Authentication. Never use `map` returning `null` because Reactor forbids null emissions.
3. `AuthenticationTrustResolverImpl` recognizes standard anonymous tokens; combining it with `isAuthenticated()` makes the lab semantics explicit. Framework method security has fuller logic for each authentication type; prefer built-in APIs in production.
4. `switchIfEmpty(Mono.error(...))` turns the missing-verified-user case into a **testable error**, rather than the service silently returning `Mono.empty()` and letting a controller think nothing went wrong.
5. `SCOPE_documents.read` and `SCOPE_documents.write` are **separate** authorities. A user with read only cannot write; authentication alone does not imply access to every document.
6. `documentId` is included only in the demo string; there is **no object-level authorization/tenant ownership yet**. In production, add ACLs and database query predicates by document ID/tenant.
7. `whoAmIWithTrace()` uses `Mono.deferContextual` to read a **lab** key; it does not touch Spring Security's private key.
8. All methods return `Mono<String>`; no `block()` or manual `subscribe()` inside the service.
9. No credentials are logged; the string output only contains mock user names and lab document IDs.

**Important boundary:** unit tests attach an already-"authenticated" `Authentication` into context to test service behavior. That **does not prove** HTTP bearer JWTs, passwords, or cookies are actually validated. Separate authentication protocol tests from method/business policy tests.

## 7. Complete test suite with StepVerifier and Reactor Context

**src/test/java/example/context/DocumentServiceTest.java**

```java
package example.context;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Arrays;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.context.SecurityContextImpl;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class DocumentServiceTest {

    private final DocumentService service = new DocumentService();

    private static Authentication user(
            String name, String... authorities) {

        List<GrantedAuthority> granted = Arrays.stream(authorities)
            .map(a -> (GrantedAuthority)
                new SimpleGrantedAuthority(a))
            .toList();

        // This factory creates an already-authenticated Authentication.
        // Use only when testing components downstream of authentication.
        return UsernamePasswordAuthenticationToken.authenticated(
            name, "not-a-real-password", granted);
    }

    @Test
    void missingContextFailsClosed() {
        StepVerifier.create(service.whoAmI())
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void aliceInReactorContextCanRead() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");

        StepVerifier.create(
                service.read("doc-1")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectNext("READ|doc-1|alice")
            .verifyComplete();
    }

    @Test
    void readAuthorityDoesNotImplyWriteAuthority() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");

        StepVerifier.create(
                service.write("doc-1")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void bobWithWriteAuthorityCanWrite() {
        Authentication bob = user(
            "bob", "SCOPE_documents.write");

        StepVerifier.create(
                service.write("doc-2")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(bob)))
            .expectNext("WRITE|doc-2|bob")
            .verifyComplete();
    }

    @Test
    void missingWritePermissionAndNoAuthenticationDiffer() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");

        StepVerifier.create(
                service.write("doc-3")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectError(AccessDeniedException.class)
            .verify();

        StepVerifier.create(service.write("doc-3"))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void unauthenticatedObjectIsNotAccepted() {
        Authentication candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "mallory", "unverified-password");

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(candidate)))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void anonymousAuthenticationIsNotARealUser() {
        Authentication anonymous = new AnonymousAuthenticationToken(
            "test-only-key",
            "anonymousUser",
            AuthorityUtils.createAuthorityList(
                "ROLE_ANONYMOUS"));

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(anonymous)))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void emptySecurityContextAlsoFailsClosed() {
        SecurityContext empty = new SecurityContextImpl();

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withSecurityContext(Mono.just(empty))))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void withSecurityContextAcceptsMonoOfSecurityContext() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");
        SecurityContext security = new SecurityContextImpl(alice);

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withSecurityContext(Mono.just(security))))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void samePublisherCanHaveDifferentSubscriberIdentities() {
        Mono<String> reusable = service.whoAmI();
        Authentication alice = user("alice");
        Authentication bob = user("bob");

        StepVerifier.create(
                reusable.contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(
                reusable.contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(bob)))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(reusable)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void flatMapAndFluxInheritSubscriberContext() {
        Authentication alice = user("alice");

        Flux<String> events = Flux.range(1, 3)
            .concatMap(i -> service.whoAmI()
                .map(name -> name + "#" + i))
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(events)
            .expectNext("alice#1", "alice#2", "alice#3")
            .verifyComplete();
    }

    @Test
    void publishOnDoesNotAutomaticallyEraseReactorContext() {
        Authentication alice = user("alice");

        Mono<String> pipeline = Mono.just("event")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> service.whoAmI())
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void subscribeOnCanReadSubscriptionContext() {
        Authentication alice = user("alice");

        Mono<String> pipeline = Mono.defer(service::whoAmI)
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void nestedContextWriteClosestToReaderWins() {
        Authentication alice = user("alice");
        Authentication bob = user("bob");

        Mono<String> pipeline = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(bob))
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void clearContextRemovesAuthenticationForUpstream() {
        Authentication alice = user("alice");

        Mono<String> pipeline = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .clearContext())
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void contextWriteAtWrongPlaceDoesNotReachDownstreamFlatMap() {
        Authentication alice = user("alice");

        Mono<String> wrong = Mono.just("go")
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice))
            .flatMap(ignored -> service.whoAmI());

        StepVerifier.create(wrong)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void stepVerifierOptionsSetsInitialSecurityContext() {
        Authentication alice = user("alice");

        StepVerifierOptions options = StepVerifierOptions.create()
            .scenarioName("initial-authentication")
            .withInitialContext(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(service.whoAmI(), options)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void stepVerifierCanAssertOrdinaryContextKeys() {
        Authentication alice = user("alice");

        Context initial = ReactiveSecurityContextHolder
            .withAuthentication(alice)
            .put("traceId", "test-309");

        StepVerifier.create(
                service.whoAmIWithTrace(),
                StepVerifierOptions.create()
                    .withInitialContext(initial))
            .expectAccessibleContext()
            .contains("traceId", "test-309")
            .then()
            .expectNext("test-309:alice")
            .verifyComplete();
    }

    @Test
    void ordinaryTraceKeyCannotReplaceSecurityContext() {
        Mono<String> pipeline = service.whoAmI()
            .contextWrite(Context.of("traceId", "only-trace"));

        StepVerifier.create(pipeline)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void separateBranchesDoNotShareUser() {
        Mono<String> alice = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(user("alice")));
        Mono<String> bob = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(user("bob")));

        StepVerifier.create(Flux.merge(alice, bob).collectList())
            .assertNext(names -> assertEquals(
                Set.of("alice", "bob"), Set.copyOf(names)))
            .verifyComplete();
    }

    @Test
    void plainThreadLocalIsNotTheReactiveContext() {
        Authentication alice = user("alice");

        SecurityContextHolder.getContext().setAuthentication(alice);
        try {
            StepVerifier.create(service.whoAmI())
                .expectError(
                    AuthenticationCredentialsNotFoundException.class)
                .verify();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

**21 `@Test` methods** using JUnit + `StepVerifier` in **one class**. Each test attaches context directly to its publisher/StepVerifier instead of using a shared `static SecurityContext` field mutated across tests.

### 7.1 What are these tests expected to prove?

| Test | Scenario | Expected |
|---|---|---|
| `missingContextFailsClosed` | No context | AuthenticationCredentialsNotFoundException |
| `aliceInReactorContextCanRead` | Alice has read scope | `READ\|doc-1\|alice` |
| `readAuthorityDoesNotImplyWriteAuthority` | Alice only has read, asks for write | AccessDeniedException |
| `bobWithWriteAuthorityCanWrite` | Bob has write scope | `WRITE\|doc-2\|bob` |
| `unauthenticatedObjectIsNotAccepted` | Object `isAuthenticated()==false` | Rejected |
| `anonymousAuthenticationIsNotARealUser` | AnonymousAuthenticationToken | Rejected |
| `emptySecurityContextAlsoFailsClosed` | SecurityContext with no Authentication | Controlled rejection |
| `samePublisherCanHaveDifferentSubscriberIdentities` | Reuse publisher across two subscriptions | Alice, Bob isolated; unauthenticated run rejected |
| `flatMapAndFluxInheritSubscriberContext` | Multiple inner publishers | All three emissions have Alice |
| `publishOn...` | Switch Reactor scheduler | Still reads Alice in reactive chain |
| `subscribeOn...` | Switch subscription scheduler | Still reads Alice |
| `nestedContextWrite...` | Two contexts with the same key at different positions | Reader receives Bob (scope closer to reader) |
| `clearContext...` | Clear upstream context | Missing authentication → error |
| `contextWriteAtWrongPlace...` | Write context in different upstream | Downstream `flatMap` does not see user |
| `stepVerifierOptions...` | Initial subscriber context | Reader sees Alice |
| `stepVerifierCanAssert...` | Custom key `traceId` and SecurityContext | Context assertion + `test-309:alice` |
| `ordinaryTraceKeyCannotReplace...` | Only trace present | Not automatically authenticated |
| `separateBranches...` | Two merged branches | No user leak between subscriber branches |
| `plainThreadLocal...` | Imperative ThreadLocal set only | Reactive service cannot read it automatically |

The other two tests in the file verify missing auth vs missing write authority together and `withSecurityContext(Mono.just(...))`. The large test count demonstrates both **correct behavior** and common pitfalls; none of the tests validate real passwords or tokens.

### 7.2 Running Gradle

At the project root, with Java 17+ and a compatible Gradle version:

```bash
gradle test
```

If the project includes an appropriate Gradle Wrapper, prefer:

```bash
./gradlew test

# On Windows PowerShell/cmd:
gradlew.bat test
```

When sources and dependencies are valid and tests pass, Gradle reports a successful build/test run. **No actual test stdout was executed while authoring this document**; the `expectNext`/`expectError` values are expectations derived from API semantics. In CI, inspect the XML/HTML reports under `build/test-results/test` and `build/reports/tests/test` to confirm.

## 8. Deep dive into how context propagates

### 8.1 `contextWrite` propagates from subscriber upstream

```text
source:             service.whoAmI() -> map -> flatMap
                                           |
                                           v
downstream:              contextWrite(withAuthentication(Alice))
                                           |
                                      StepVerifier.create(...)
                                           |
                                         subscribe
      Context is established along the subscription path flowing back to source
```

Because of this, reading code top-to-bottom makes many people assume `contextWrite` "runs later" and cannot affect `getContext` before it. In reality, context is attached **on subscription** and becomes visible to upstream operators.

### 8.2 Two `contextWrite` calls with the same security key

Since Spring Security context entries share the same logical key, the scope **closer to the reader** wins:

```java
Mono<String> value = service.whoAmI()
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(userBob))
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(userAlice));
```

Reader `service.whoAmI()` sees Bob, not Alice, because Bob is attached at the `contextWrite` closer to the source (even though Alice's operator sits below). Do not use this pattern as an ad-hoc "impersonation" system; in production, switching users requires authenticated delegation and authorization checks.

### 8.3 `flatMap`, `concatMap`, and multiple inner publishers

If an inner publisher is subscribed to as part of a Reactor pipeline, it normally inherits context from the corresponding operator's subscriber:

```java
Flux<String> result = Flux.just("A", "B", "C")
    .concatMap(label ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> label + "=" + auth.getName()))
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(alice));
```

Expected:

```text
A=alice
B=alice
C=alice
```

There is no need to copy the username into a `ThreadLocal` on each thread. However, if code calls `subscribe()` manually, creating a **new subscription** outside the pipeline under test, the original context may **not be carried over**. Reactive methods should **return Mono/Flux** so callers can compose them, instead of self-subscribing and losing cancellation/error handling.

### 8.4 `publishOn` / `subscribeOn` do not "erase security"

Reactor Context is attached to the subscriber; when using Reactor operators properly, it can cross `publishOn`/`subscribeOn` even when callbacks run on another thread. This does **not** guarantee an arbitrary `CompletableFuture`, raw `Executor`, or blocking library knows about the context.

Distinguish:

```text
Mono -> publishOn(Schedulers.parallel()) -> flatMap(Mono...)
     -> contextWrite(withAuthentication(alice))
     -> StepVerifier               : usually preserves Reactor Context

executor.submit(() -> SecurityContextHolder.getContext())
                                : ThreadLocal on another thread is not
                                  automatically treated as Alice's Reactor Context
```

To bridge to ThreadLocal for tracing/legacy code, study Micrometer Context Propagation, Reactor hooks, and version-specific Spring support. **Do not** enable global `Hooks.enableAutomaticContextPropagation()` in every unit test just to "fix" a publisher with a misplaced `contextWrite`; global hooks can make tests interfere with one another.

## 9. When to use StepVerifierOptions.withInitialContext

Two ways to establish an initial security context:

**Approach A — Attach to the publisher:**

```java
StepVerifier.create(service.whoAmI()
        .contextWrite(ReactiveSecurityContextHolder
            .withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

**Approach B — Attach to the test subscriber:**

```java
StepVerifierOptions options = StepVerifierOptions.create()
    .withInitialContext(
        ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(service.whoAmI(), options)
    .expectNext("alice")
    .verifyComplete();
```

Both are valid for **unit tests**. Choose A when you want to show clearly that the context belongs to the code under test; choose B when testing a framework/operator receiving an initial context from the subscriber, or when applying the same initial context across multiple connected operators.

### 9.1 Context assertion is a different kind of check

`StepVerifier.expectAccessibleContext()` is used to assert that Reactor Context **is accessible**, then switches back to event expectations via `then()`:

```java
StepVerifier.create(
        Mono.deferContextual(view ->
            Mono.just(view.<String>get("traceId"))),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("traceId", "abc")))
    .expectAccessibleContext()
    .contains("traceId", "abc")
    .then()
    .expectNext("abc")
    .verifyComplete();
```

**Do not confuse:** seeing `traceId` in Reactor Context **does not prove** Spring Security context has authentication. For security context, use `ReactiveSecurityContextHolder.getContext()` or service behavior to assert the principal/authorities. Never inspect Spring Security's private key via an unofficial string.

### 9.2 How to interpret `expectNoAccessibleContext()`

`expectNoAccessibleContext()` applies when a publisher has no accessible Reactor context propagation (for example, a non-Reactor Publisher). It is **not** equivalent to "empty security context". A Reactor publisher can have an accessible Context object with no Spring Security entry. To test anonymous/missing authentication, create a test publisher reading `ReactiveSecurityContextHolder.getContext()` and assert empty/error per contract.

## 10. Simulating context-loss bugs in tests

### 10.1 Wrong: writing context before a downstream flatMap

```java
Mono<String> faulty = Mono.just("command")
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(alice))
    .flatMap(command -> service.whoAmI());
```

Because `flatMap` comes **after** `contextWrite`, the inner service sits downstream of where the context was written and will not see Alice from that operator. Move `contextWrite` to the end:

```java
Mono<String> fixed = Mono.just("command")
    .flatMap(command -> service.whoAmI())
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(alice));
```

These are two different publishers in terms of **context scope**, even though they have the same list of operators.

### 10.2 Wrong: trying to set SecurityContextHolder in @BeforeEach

```java
@BeforeEach
void setUp() {
    SecurityContextHolder.getContext()
        .setAuthentication(alice);
}
```

This is a **snippet missing fields/imports**. In Spring Test with listeners/bridges, thread-local data can be copied into reactive context by test support mechanisms. But in **plain JUnit 5** without listener configuration, setting imperative ThreadLocal **does not automatically create** a Reactor SecurityContext for a reactive service. Another risk is leftover state remaining on the test thread if not cleared.

Plain JUnit recommendation: **create per-test authentication and use `contextWrite` or `StepVerifierOptions`**, not global state.

### 10.3 Wrong: storing the user in a static variable

```java
// WRONG: global mutable state shared across test requests/subscribers.
static Authentication CURRENT_USER;
```

Two tests for Alice and Bob running in parallel will read each other's user or become flaky. Per-subscriber Reactor Context isolates better, though you still must not store a mutable `Authentication` object and mutate its authorities between subscriptions.

### 10.4 Wrong: calling block on the WebFlux event loop

```java
// Production ANTI-PATTERN:
String current = service.whoAmI().block();
```

`block()` creates a separate subscription and can block the event loop, breaking the reactive flow or losing context if invoked outside an authenticated pipeline. In **unit tests**, people sometimes use `block()` to inspect results, though `StepVerifier` is usually better because it tests completion/error/cancellation and initial context.

### 10.5 Wrong: self-subscribing outside the main flow

```java
// ANTI-PATTERN:
public Mono<String> wrong() {
    service.whoAmI().subscribe(System.out::println);
    return Mono.just("ok");
}
```

The new subscription does not automatically inherit the caller's context under test; exceptions and cancellation are also detached. The right way:

```java
public Mono<String> correct() {
    return service.whoAmI()
        .map(user -> "ok for " + user);
}
```

Both snippets are **method fragments** without class/imports and are only for comparison. Do not use `System.out` as a principal auditing mechanism or log real user PII.

## 11. Testing non-standard SecurityContext cases

Do not just test Alice with sufficient permissions and declare "unit testing done". Negative states to verify:

| Input context | Behavior to prove |
|---|---|
| No `SecurityContext` entry | Fail closed or Mono.empty per clear contract |
| `SecurityContext` present but `getAuthentication()==null` | No NPE, no access granted |
| `Authentication.isAuthenticated()==false` | Do not grant access |
| `AnonymousAuthenticationToken` | Not treated as a real authenticated user |
| Authenticated without required authority | `AccessDeniedException` or deny result |
| Has READ authority but requests WRITE | Deny |
| Has `ROLE_USER` authority while service requires `SCOPE_documents.read` | Not automatically mapped to scope |
| Alice context attached, then Bob tested | No leak from Alice to Bob |
| One publisher reused across two subscriptions | Identity per subscription, not per Mono object |
| Clear context upstream | No authentication within that scope |
| Independent context key like traceId | Never used as security identity |
| Nested contexts | Closest-to-reader rule, tested explicitly |
| Fake JWT/credentials inside Authentication | Do not infer protocol was verified |
| Token expires after object creation | This unit test does not check expiration; token integration tests must handle it |

In particular, creating a `UsernamePasswordAuthenticationToken.authenticated(...)` in a test **does not** verify passwords. If a test must ensure an invalid JWT cannot log in, test at the `ReactiveJwtDecoder`/Resource Server filter using a JWT signed with the proper test key/issuer.

## 12. Distinguishing pure unit tests from Spring Test, @WithMockUser, and WebTestClient

### 12.1 Plain JUnit + StepVerifier

This lesson uses:

```java
@Test
void aUnitTest() {
    Authentication user = /* test authentication */;
    StepVerifier.create(service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(user)))
        .expectNext("alice")
        .verifyComplete();
}
```

The `test authentication` comment is an **illustrative placeholder**; the compile-ready file in Section 7 already has `user(...)` creating the token. This test needs no Spring context, AOP proxy, or HTTP filters.

**Best suited when:** testing business code calling `ReactiveSecurityContextHolder.getContext()`, Reactor operators, missing/changed context, role/scope logic, and publisher isolation.

### 12.2 Reactive method security @PreAuthorize

If a method carries:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public Mono<String> readDocument(String documentId) {
    return Mono.just(documentId);
}
```

then permissions are checked via Spring Security's **method interceptor/AOP proxy** when `@EnableReactiveMethodSecurity` is enabled. If you test `new DocumentService()` directly, **the annotation is not applied**. Therefore, real method security testing requires a Spring-managed bean/proxy:

```java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfiguration {
    @Bean
    SecuredDocumentService secured() {
        return new SecuredDocumentService();
    }
}
```

These are **two guiding snippets**: the method and configuration must be placed in full classes/packages with the required dependencies when implemented. You can test using `@SpringJUnitConfig(MethodSecurityConfiguration.class)`, `@WithMockUser`/`ReactorContextTestExecutionListener`, or directly attaching `contextWrite` to the publisher returned by the proxy.

**Do not** describe testing a `new`-instantiated class as really testing `@PreAuthorize`.

### 12.3 @WithMockUser and ReactorContextTestExecutionListener

`@WithMockUser(username = "alice", roles = "USER")` comes from Spring Security Test. In Spring Test, `WithSecurityContextTestExecutionListener` builds the context for the test; for reactive method security, `ReactorContextTestExecutionListener` ensures the reactive context can be populated from the test security context.

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MethodSecurityConfiguration.class)
@WithMockUser(username = "alice", roles = "USER")
class MethodSecurityTest {
    // Inject proxied bean, assert result with StepVerifier.
}
```

This is a **test skeleton** without the full class/method body. `@WithMockUser` in a plain JUnit test **without Spring Test listeners** is not magic that pushes authentication into every Reactor subscription. If a project uses custom `@TestExecutionListeners`, ensure default listeners are not accidentally excluded, especially the listener supporting Reactor Context.

`@WithMockUser(roles = "USER")` creates authority `ROLE_USER`. If you need the literal authority `SCOPE_documents.read`, use:

```java
@WithMockUser(
    username = "alice",
    authorities = "SCOPE_documents.read")
```

**Do not** use `roles = "SCOPE_documents.read"` to simulate a scope: for roles, Spring automatically prepends `ROLE_`, breaking the expression `hasAuthority('SCOPE_documents.read')`.

### 12.4 WebTestClient mutateWith(mockUser()) is a different integration layer

For a WebFlux endpoint, Spring Security Test provides:

```java
// SNIPPET: WebTestClient already bound to ApplicationContext,
// with Spring Security test support applied.
webTestClient
    .mutateWith(mockUser().roles("USER"))
    .get()
    .uri("/documents")
    .exchange()
    .expectStatus().isOk();
```

Static import required:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
```

**This is not a standalone runnable file**. When creating the client manually:

```java
WebTestClient client =
    WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .build();
```

`springSecurity()` also comes from `SecurityMockServerConfigurers`. In a Spring Boot test environment, you can use `@AutoConfigureWebTestClient` and then mutate; verify actual setup per version.

Differences:

| Test type | HTTP exchange? | Where is security identity set? | What does it test? |
|---|---|---|---|
| Plain JUnit + StepVerifier | No | Subscription Reactor Context supplied by test | Publisher/service behavior |
| Spring Test + @WithMockUser | Not required | Spring Test listener, can bridge reactive | Reactive method security on a Spring bean |
| WebTestClient + mockUser | Simulated request | Spring Security test WebFlux mutator/request | Route/controller/filter authorization with mock user |
| WebTestClient + real Bearer JWT | Request present | Authorization header and Resource Server filters | Token validation, status, claims when IdP/JWK match |
| End-to-end over network | Real HTTP | Browser/cookie/token/IdP server | Full auth flow and deployment controls |

**Mock user is not evidence of JWT signature validation.** If your threat model requires issuer/audience/expiry checks, test the decoder/JWK/IdP or real signed JWT integration.

## 13. Securing context in unit tests

### 13.1 Do not pass raw secrets through Context

Reactor Context is a per-subscription data carrier; it **does not automatically encrypt** data. Never place passwords, client secrets, or raw bearer tokens into a custom key and log the entire Context.

```java
// Do not create context like this:
Context.of("Authorization", "Bearer real-production-token");
```

Use mock authentication without real credentials. If testing JWT claims, build a test-appropriate mock `Jwt` and distinguish it from the verifier having checked the signature.

### 13.2 Authentication objects can be mutable

`SecurityContextImpl` has a `setAuthentication` setter; an authentication/token can hold details, authorities, and credentials. **Do not** create a static mutable `SecurityContext` where test A sets Alice and test B sets Bob; a publisher might still hold a reference. Create a separate object per test and avoid mutating across subscriptions.

### 13.3 Context is no substitute for object-level authorization

The `service.read("doc-1")` test in this lab only checks read authority. In a multi-tenant product, you must check the owner/tenant of `doc-1` in the business repository:

```text
authenticated user (issuer, sub, tenant)
             |
       hasAuthority("documents.read")?
             |
       document.tenant == user.tenant?
             |
       owner / grant / ABAC policy?
             |
       query DB with tenant predicate
```

`contextWrite(withAuthentication(...))` lets you simulate a principal when unit-testing a permission service, but the identity must be **verified** in the production security chain. Never accept an `X-User-Id` HTTP header as an authenticated user just to make tests pass.

### 13.4 Prevent test state from leaking between cases

- Prefer test-local `Authentication` objects.
- Use `contextWrite` directly on the publisher under test instead of a global ThreadLocal.
- If you must use `SecurityContextHolder` in a mixed imperative test, use `try/finally` and `SecurityContextHolder.clearContext()`.
- Do not enable Reactor global hooks and forget to reset them; this can alter behavior for other tests.
- In JUnit parallel mode, avoid shared mutable contexts, shared counters, and unsynchronized mutations to security test data.
- Never log the entire context or a serialized `Authentication` containing credentials.

## 14. On context propagation across other boundaries

### 14.1 Scheduled tasks

A scheduler has no authenticated HTTP request. If an application needs a service identity to run a job, **design a dedicated service identity/authorization**; do not grab the last user's context and attach it to the job. In tests, you may `contextWrite` a service authentication **only when** the component is truly designed and authorized to run on behalf of the service.

### 14.2 CompletableFuture, Executor, callbacks

Reactor Context is managed inside the reactive subscriber chain. If code jumps into `CompletableFuture.supplyAsync` and then directly calls `SecurityContextHolder.getContext()`, the same user is normally unavailable. To bridge, use a properly designed and tested mechanism, or pass the **verified identity/authorization context** explicitly to the function across the trust boundary.

### 14.3 RxJava/Kotlin Flow/custom Publishers

Do not assume all reactive APIs use Reactor Context with identical semantics. Switching frameworks can lose context. `StepVerifier.expectNoAccessibleContext()` is not a security check; when integrating across adapters, test whether the user is actually seen or not seen where `ReactiveSecurityContextHolder.getContext()` is read.

### 14.4 Cache and share

A publisher using `cache()`, `share()`, or a hot source can have different subscription semantics from a normal cold publisher. In particular, if you **cache personalized data** derived from security context and share it globally, another subscriber risks receiving someone else's data. Never cache `myDocuments` results under a global key without user/tenant in the cache key. Test two subscribers Alice/Bob against any cached publisher and redesign if cross-user leaks occur.

### 14.5 Micrometer Context Propagation

Reactor has a context-propagation mode for bridging with ThreadLocal in certain scenarios when the appropriate dependency is present. `Hooks.enableAutomaticContextPropagation()` is a **global setting**, not a default API you need to call for `ReactiveSecurityContextHolder.withAuthentication(...)`. Basic context tests should use native Reactor Context; if the project bridges tracing/MDC, test separately across threads/schedulers and reset hooks after tests so other suites are unaffected.

## 15. Failure matrix and diagnostics

| Symptom | Common cause | Fix / test |
|---|---|---|
| `ReactiveSecurityContextHolder.getContext()` empty | No context for subscriber | `contextWrite(withAuthentication(auth))` on the pipeline under test |
| Test expects `expectNext` but completes empty | Service does not turn missing auth into error | Define clear contract, `switchIfEmpty(...)` or check empty |
| Unit test passes but production returns 401 | Mock authentication bypassed login/token verification | Add HTTP auth integration/JWT tests |
| User A appears in test B | Static mutable SecurityContext, cached personalized results | Test-local context and subscriber isolation |
| `SecurityContextHolder.getContext()` has Alice but reactive service does not see her | ThreadLocal ≠ Reactor Context | Use reactive API / proper test listener |
| `contextWrite` has no effect on inner `flatMap` | Operator placed in wrong upstream scope | Move `contextWrite` to end of pipeline |
| `publishOn` switches thread, logs lose user | MDC/ThreadLocal not propagated | Read ReactiveSecurityContextHolder; bridge logging if needed |
| `@WithMockUser` in plain JUnit has no effect | No Spring Test listeners | Use `contextWrite`/`StepVerifierOptions` |
| `@PreAuthorize` does not block in unit test | Object created with `new`, bypassing Spring proxy | Test Spring-managed proxied bean |
| `roles="SCOPE_x"` does not match authority | Roles prepend `ROLE_` | Use `authorities="SCOPE_x"` |
| AnonymousAuthenticationToken has `isAuthenticated() == true` | Confusing authenticated flag with real user | Trust resolver / Spring authorization APIs |
| NPE because `SecurityContext.getAuthentication()` is null | Using `map` returning null | `flatMap(ctx -> Mono.justOrEmpty(...))` |
| "Missing authority" error mapped to HTTP 401 wrongly | Unit exceptions differ from HTTP translation | Integration test 401/403 exception mapping |
| Parallel tests are flaky | Shared Auth/SecurityContext or Reactor hooks | Isolate context per subscriber/test |
| Flux emits miss context in nested subscription | Manual `subscribe()` or different library | Compose publishers, test subscription boundary |
| `expectAccessibleContext` passes but identity is wrong | Only tested custom key, not authentication | Assert service principal/authorities |
| JWT test treating constructed Jwt object as "verified" | Skipped cryptographic validation | Resource Server/JWKS integration tests |
| Service `block()` hangs request | Blocking on event loop / new subscription | Return Mono/Flux, use StepVerifier tests |
| Cached publisher returns Alice's data to Bob | Caching context-dependent results globally | Cache per user/tenant or do not cache |
| Old publisher still returns data after role revoked | Snapshot of context identity/auth without rechecking ACL | Current business policy and revocation handling |

## 16. Testing across layers: which layers are needed?

| Test level | Target | Example | Does not prove |
|---|---|---|---|
| **Unit Context** | `ReactiveSecurityContextHolder` and pure Java service | Alice can read, Bob cannot; contextWrite | Valid signed JWT |
| **Unit policy** | `ReactiveAuthorizationManager`/ABAC service | user+tenant+resource+action | HTTP CORS/CSRF |
| **Method security** | Proxied `@PreAuthorize` method | `hasAuthority` in Spring context | Token issuer validation |
| **HTTP/WebFlux slice** | `WebTestClient` + mockUser/mockJwt | 200/401/403, route matching | Real IdP |
| **Resource Server integration** | JWT decoder/opaque introspection | bad signature, exp, aud, iss | Data ACL if untested |
| **Full E2E** | Browser/IdP/session/microservices | login, callbacks, token refresh, logout | Does not replace security review |

The unit test suite in Section 7 intentionally avoids starting an HTTP server so it stays easy to run, fast, and straightforward to debug. Always keep tests with **actually verified credentials** at the integration layer so you do not end up with the gap "unit test allows admin because it forged an admin token itself".

## 17. Checklist when writing unit tests using Reactor Context

1. Identify whether the method returns `Mono`/`Flux` and requires `Authentication` or only a custom context key.
2. Construct a dedicated `Authentication` with clear contract authorities.
3. Attach via `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))` or `StepVerifierOptions.withInitialContext(...)`.
4. Use `StepVerifier` to assert next/completion/error; do not use `block()` in production services.
5. Include tests for missing SecurityContext, context with no Authentication, unauthenticated tokens, and anonymous tokens.
6. Include tests for missing scope/role, read vs write differences, and identities from another tenant.
7. Include tests reusing a publisher across two subscribers and confirming no user remains on a third subscription.
8. Include tests for nested `contextWrite` order, `clearContext`, and `contextWrite` placement.
9. Include tests for `publishOn` / `subscribeOn` if the service uses schedulers/async operators.
10. Use `expectAccessibleContext()` for custom context keys; **never** guess private security keys.
11. For `@PreAuthorize`, verify the bean is Spring-proxied, `@EnableReactiveMethodSecurity` is enabled, and the proper Spring Test listener is active.
12. With `WebTestClient`, use `springSecurity()`/`mockUser()` for the right test scope; test raw JWTs separately.
13. Avoid letting mock auth stand in for a password/JWT/issuer validation test.
14. Never store real tokens/passwords in context or logs.
15. Clean up imperative `SecurityContextHolder` or Reactor global hooks if any test uses them.
16. For hot/cached publishers, prove no data leaks across users or tenants.
17. Assert data-level business ACLs rather than stopping at `isAuthenticated()`.
18. Run CI with the standard JDK/Gradle version and execute the suite after every security config change.

## 18. Advanced exercises

1. Write a `Mono<String>` returning `SecurityContext.getAuthentication().getName()`. Without attaching a context, what does StepVerifier receive?
2. Use `withAuthentication(user("alice","ROLE_USER"))` to verify the principal. Switch to `user("bob","ROLE_ADMIN")` on **the same original publisher** and verify no cross-contamination.
3. Call `service.write("d1")` with only `SCOPE_documents.read`. Why should the test expect `AccessDeniedException` rather than `Mono.empty()`?
4. Create a `SecurityContextImpl()` with no authentication. How does `Mono.justOrEmpty` prevent an NPE?
5. Create an `AnonymousAuthenticationToken`; inspect `isAuthenticated` and `AuthenticationTrustResolver.isAnonymous`. Why is reading only the boolean flag insufficient?
6. Move `contextWrite` before `flatMap` as in the failure test. Explain the propagation direction of subscription context.
7. Add `.publishOn(Schedulers.parallel())` before reading the identity. Why is Alice still returned?
8. Use `StepVerifierOptions.withInitialContext(ReactiveSecurityContextHolder.withAuthentication(...))` instead of `contextWrite`. Compare where the context is attached.
9. Add a `traceId` key via `Context.of(...)` and write `expectAccessibleContext().contains(...)`. Why is that insufficient to prove authentication?
10. Add two `contextWrite` calls for Alice and Bob and swap their order. How does the identity observed upstream change?
11. Clear the context with `ReactiveSecurityContextHolder.clearContext()` between two operations; prove it does not auto-logout the entire server.
12. Wrap `service.whoAmI()` in `.cache()` and subscribe as Alice then Bob; analyze the risk of Alice's data being returned to Bob and fix the cache design.
13. Write `@PreAuthorize("hasAuthority('SCOPE_documents.read')")` on a Spring-managed bean and test how it differs from a plain `new` object.
14. Write `WebTestClient.mutateWith(mockUser().authorities(...))` for an HTTP route and contrast it with pure JUnit StepVerifier.
15. Write a JWT Resource Server test for a token with a wrong issuer/audience (signed JWT), explaining why `withAuthentication` does not check that.
16. Write a composite `Flux.merge` test to assert no identity leaks across concurrent branches.
17. Count subscriptions to a publisher using `AtomicInteger`, proving context is read at subscription time rather than assembly time.
18. Write a helper `testAs(String user, Publisher<?> publisher)` while ensuring `Authentication` is not stored in mutable static state.
19. When using `CompletableFuture`, try reading reactive context inside a callback. Design a safe, bounded bridge.
20. Propose a security regression suite for upgrading Spring Security/Reactor (ThreadLocal bridge, contextWrite order, `@PreAuthorize`, and client mock support).

## Conclusion

In **Spring Security Reactive unit testing**, identity does not live implicitly in the JUnit thread or a global object. It lives in **each subscription's Reactor Context**. Use `ReactiveSecurityContextHolder.withAuthentication(auth)` or `withSecurityContext(Mono<SecurityContext>)` with `contextWrite`, or configure `StepVerifierOptions.withInitialContext(...)`. `StepVerifier` verifies onNext/onComplete/onError and context metadata while enabling negative cases: missing context, anonymous/unauthenticated, missing authority, misplaced scope, nested contexts, and subscriber isolation. Avoid confusing ThreadLocal `SecurityContextHolder` with reactive context; `@WithMockUser` only works automatically inside appropriate Spring Test setups; `@PreAuthorize` requires a proxy, and `WebTestClient` operates at a different testing level. Unit tests attaching mock authentication **do not prove** valid passwords/JWTs/issuers — verify protocol, data permissions, and HTTP security in additional test layers.

## Official References

1. Spring Security — Reactive Method Security, `contextWrite(withAuthentication(...))` and StepVerifier examples: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
2. Spring Security — `ReactiveSecurityContextHolder` Javadoc (`getContext`/`withAuthentication`/`withSecurityContext`/`clearContext` APIs): https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
3. Project Reactor 3.6 — Context, immutable semantics and `contextWrite`: https://projectreactor.io/docs/core/3.6.13/reference/index.html
4. Project Reactor — Testing Reactor Context, `StepVerifierOptions`/`expectAccessibleContext`: https://projectreactor.io/docs/core/3.6.13/reference/index.html#_testing_the_context
5. Reactor Test API — `StepVerifierOptions.withInitialContext`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html
6. Spring Security — Testing Method Security, Spring Test listeners and `@WithMockUser`: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
7. Spring Security — Reactive WebTestClient Authentication tests, `springSecurity`/`mockUser`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
8. Spring Security — WebFlux Security configuration and reactive context: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
9. Spring Security 6.3 — `TestingAuthenticationToken` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/TestingAuthenticationToken.html
