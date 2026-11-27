# 30.5. Testing Principal and Security Context in Reactor

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client on Reactive WebFlux**, once a user logs in, application components need to know who is making the request, what permissions the user has, and whether a `Mono` or `Flux` call still sees the right identity across multiple operators and schedulers.

Unlike Servlet, where `SecurityContextHolder` usually binds `SecurityContext` to the current thread, **Spring Security Reactive uses `ReactiveSecurityContextHolder` and the Reactor `Context`** to associate authentication with the subscription stream. Testing must therefore be organized around **publishers, subscribers, and context propagation**, rather than simply setting a `ThreadLocal` before calling a service.

Core APIs in this lesson:

- **`ReactiveSecurityContextHolder.getContext()`**: accesses the `Mono<SecurityContext>` of the current subscription;
- **`ReactiveSecurityContextHolder.withAuthentication(authentication)`**: creates a Reactor context containing an `Authentication` for a test branch;
- **`StepVerifier`**: subscribes to and verifies `onNext`, `onError`, and `onComplete` of a reactive service;
- **`@WithMockUser` + Reactor test listener**: provides an identity for reactive method-security tests with a Spring Test context;
- **`WebTestClient.mutateWith(mockUser())` / `mockAuthentication()` / `mockOAuth2Login()` / `mockOidcLogin()`**: mocks `SecurityContext` per **WebFlux HTTP request**;
- **`@AuthenticationPrincipal`, `Principal`, `@PreAuthorize`**: tests controller and business authorization.

Minimal example:

```java
Authentication alice = new TestingAuthenticationToken(
    "alice", "not-used", "ROLE_READER");

Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

StepVerifier.create(
        currentName.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

Here, `Authentication` lives inside the **Reactor Context of the subscription created by `StepVerifier`**. There is no network call to an OP, no Authorization Code exchange, and no real ID Token.

> **Scope:** Java 17+, Spring Boot 3.x, Spring Security 6.x (referencing API 6.5), Reactor 3.x, JUnit 5, and `spring-security-test`. This is chapter **30. Reactive Testing**; do not mix `HttpSecurity`, `MockMvc`, or `SecurityMockMvcRequestPostProcessors` from Servlet. Any ID Token/access token strings in examples are fake fixtures only.

---

## 1. The Problem: Same Request, Not Necessarily the Same Thread

Suppose user Alice logged in via Company SSO and calls:

```text
GET /api/me
Cookie: SESSION=<opaque-session-cookie>

WebFlux SecurityWebFilterChain:
    validates session
    Authentication = OAuth2AuthenticationToken(
        principal = OidcUser(Alice),
        authorities = [SCOPE_read, ROLE_REPORT_READER]
    )

Reactive controller:
    return identityService.currentUser()
        .flatMap(user -> reportService.load(user))
        .publishOn(Schedulers.parallel())
        .map(this::toResponse)
```

Execution can switch threads when crossing `publishOn` or during asynchronous I/O. If you write:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

inside an arbitrary reactive operator, the result **may be `null` or the wrong context** if code relies on the default `ThreadLocal`.

What Spring Security Reactive provides is a context **scoped to the subscriber**, accessed as a publisher:

```java
Mono<SecurityContext> securityContext =
    ReactiveSecurityContextHolder.getContext();
```

### 1.1. Quick Comparison: Servlet vs. Reactive

| Aspect | Servlet / MVC | Reactive / WebFlux |
| --- | --- | --- |
| Filter chain config | `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| HTTP test client | `MockMvc` | **`WebTestClient`** |
| Common security context | `SecurityContextHolder` | **`ReactiveSecurityContextHolder`** |
| Where context is stored | Typically bound to a thread via strategy | **Reactor Context of the subscription** |
| Reading context | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` → `Mono<SecurityContext>` |
| OIDC login fixture | `oidcLogin()` | **`mockOidcLogin()`** |
| OAuth2 login fixture | `oauth2Login()` | **`mockOAuth2Login()`** |
| Generic user fixture | `user()` / `@WithMockUser` | `mockUser()` / `@WithMockUser` |
| Testing publisher | Synchronous assertions/`MockMvc` result | **`StepVerifier`** and `WebTestClient` |
| Repository for pending OAuth2 login | `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |

**Do not infer that a unit test seeing context in `ThreadLocal` proves the context is present inside a Reactive pipeline.**

### 1.2. Distinguishing `Authentication`, `Principal`, and `SecurityContext`

`SecurityContext` is the container for `Authentication`. `Authentication` describes the subject, authentication state, and authorities.

```text
Subscriber's Reactor Context
    |
    v
SecurityContext
    |
    +-- Authentication
          |
          +-- principal: UserDetails / OAuth2User / OidcUser / Jwt ...
          +-- authorities: ROLE_*, SCOPE_*, ...
          +-- name: identity per Authentication type
          +-- authenticated: authentication status
```

In OAuth2/OIDC Client, `Authentication` after login is usually **`OAuth2AuthenticationToken`**, and the principal is usually `OAuth2User` or `OidcUser`. In a Resource Server accepting Bearer JWTs, `Authentication` may be `JwtAuthenticationToken` — a different flow type.

---

## 2. How Does Reactor Context Work?

**Reactor Context** is a key–value structure attached to the **subscription** of a Reactor sequence. It is neither a global `Map` nor a mutable field on a service.

A publisher is declared:

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

At the moment `result` is declared, the code does not yet have a context or run any operations. Only when a subscriber subscribes and supplies an appropriate context does the operator chain read the context.

### 2.1. Assembly Time vs. Subscription Time

```text
Test thread:
  Mono<String> result = buildPipeline()
                       [ASSEMBLY]

StepVerifier:
  StepVerifier.create(result)
              [SUBSCRIPTION]
    |
    v
Reactor Context flows into the pipeline
    |
    v
ReactiveSecurityContextHolder.getContext()
    |
    v
Emission / error / completion
```

**Common mistake:** reading `Authentication` via `ThreadLocal` at publisher assembly time and storing it in a field. That destroys the request/subscriber-scoped nature of the security context.

### 2.2. Context Follows the Subscription, Not a Fixed Thread

When using `publishOn` or `subscribeOn` in a pure Reactor chain with proper context propagation, Reactor Context remains available across scheduler boundaries.

```java
Mono<String> pipeline = Mono.just("work")
    .publishOn(Schedulers.parallel())
    .flatMap(ignored ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
```

Key point: **`Thread.currentThread()` can change, yet identity stays attached to the subscription**.

However, crossing into a non-Reactor API or creating an independent subscription without forwarding the Context can lose the value. That is a boundary that must be tested.

### 2.3. `contextWrite` Is Scoped Along the Subscription Direction

A helpful mental model:

```text
upstream publishers/operators  <- Reactor Context supplied by downstream subscriber
                                                     ^
                                                contextWrite()
```

`contextWrite(...)` makes the transformed context visible to operators **upstream of it**. It does not turn the context into a global variable visible from every thread or unrelated branch.

Place `contextWrite` on the exact publisher scope you want to test. If you attach it to a child branch yet read context in another branch, results may differ from expectations.

### 2.4. Context Is Not a Dumping Ground for Arbitrary Tokens

Spring Security manages the security context, whereas an application stuffing client secrets, refresh tokens, authorization codes, or raw ID Tokens into the Reactor Context across every operator is a risky design.

In tests, supply only the **necessary `Authentication`/`SecurityContext`**, avoiding reflecting sensitive data into logs and responses.

---

## 3. Core `ReactiveSecurityContextHolder` API

Class:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Key operations to remember:

| API | Meaning |
| --- | --- |
| `getContext()` | Retrieves `Mono<SecurityContext>` attached to the current subscriber |
| `withAuthentication(Authentication)` | Creates a Reactor `Context` containing a `SecurityContext` with that `Authentication` |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Creates a `Context` using a `SecurityContext` publisher |
| `clearContext()` | Creates a function for `contextWrite` to clear the security context from a branch |

### 3.1. Safely Reading Username in a `Mono`

```java
import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

public final class CurrentIdentityService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(auth -> auth != null && auth.isAuthenticated())
            .map(Authentication::getName);
    }
}
```

If there is no context, the sequence completes **empty** instead of emitting a username. That is `Mono.empty()` behavior, not the string `"null"`.

### 3.2. Handling Anonymous Users Based on Business Needs

```java
public Mono<String> currentUsernameOrGuest() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(auth -> auth != null && auth.isAuthenticated())
        .map(Authentication::getName)
        .defaultIfEmpty("guest");
}
```

**Note:** `isAuthenticated()` alone is not the rule for whether a user is a logged-in end user. Spring Security has `AnonymousAuthenticationToken`; in certain configurations it may also report `isAuthenticated()=true`. If business logic needs to distinguish anonymous users, use an authorization policy/Spring Security trust resolver or proper authorities, not just this boolean.

### 3.3. Accessing an OIDC Principal in the Pipeline

```java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(OAuth2AuthenticationToken.class::isInstance)
        .cast(OAuth2AuthenticationToken.class)
        .map(OAuth2AuthenticationToken::getPrincipal)
        .filter(OidcUser.class::isInstance)
        .cast(OidcUser.class)
        .map(user -> user.getIdToken().getSubject());
}
```

If `Authentication` is not an OAuth2/OIDC Login, the method returns `Mono.empty()`. That is an API design choice; if business logic requires OIDC strictly, return an appropriate domain/authentication error rather than silently treating the user as absent.

### 3.4. `ReactiveSecurityContextHolder` Is Not `SecurityContextHolder`

Wrong in a reactive service:

```java
Mono<String> currentUser() {
    // ANTI-PATTERN: relies on ThreadLocal, not guaranteed per subscription.
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    return Mono.just(auth.getName());
}
```

Right in Reactor:

```java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This way, the same service can handle many concurrent requests without storing a mutable "current user" field.

---

## 4. Dependencies and Test Environment Setup

### 4.1. Maven

```xml
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
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
```

`spring-boot-starter-test` normally already includes `reactor-test` in the appropriate Boot ecosystem; the explicit declaration here highlights the **`StepVerifier`** dependency. Use the dependency management BOM to align versions.

### 4.2. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an illustrative configuration. Writing this Markdown lesson **does not run Gradle or modify project builds**.

### 4.3. Useful Imports

```java
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.authentication.TestingAuthenticationToken;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockAuthentication;
```

If your Java style guide forbids line breaks in imports, place each import on a single line. The key packages here are `org.springframework.security.test.web.reactive.server` and `org.springframework.security.core.context`.

---

## 5. Testing Directly with `StepVerifier` and `withAuthentication`

At the **reactive service unit test** level, there is no need to start an HTTP server, security filter chain, or `WebTestClient`. You can construct an `Authentication` in Java and supply it in the `Context` at subscription time.

### 5.1. Sample Service

```java
package example.identity;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public final class IdentityLookup {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

### 5.2. Happy-Path Test

```java
package example.identity;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

class IdentityLookupTest {

    private final IdentityLookup identity = new IdentityLookup();

    @Test
    void seesAuthenticationFromReactorContext() {
        Authentication alice =
            new TestingAuthenticationToken(
                "alice", "not-used", "ROLE_READER");

        StepVerifier.create(
                identity.currentName()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();
    }
}
```

Why does this work?

1. `identity.currentName()` returns a `Mono<String>` awaiting subscription.
2. `contextWrite(withAuthentication(alice))` attaches `SecurityContext` to that subscription.
3. `StepVerifier.create` subscribes and checks the emission.
4. The service reads the right `Authentication` regardless of which thread runs the test.

### 5.3. Testing When Context Is Absent

```java
@Test
void noSecurityContextCompletesEmpty() {
    StepVerifier.create(identity.currentName())
        .verifyComplete();
}
```

With the sample service, `getContext()` has no value so the chain completes empty. **If the test uses a Spring Security Test listener with class-level `@WithMockUser`**, a context may already be injected automatically; when you need a "truly contextless" test, isolate the test or explicitly clear the context in that branch.

### 5.4. Explicit Failure Instead of Empty

If an API strictly requires `Authentication`:

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;

public Mono<String> requiredName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "Authentication required")));
}
```

Test:

```java
StepVerifier.create(identity.requiredName())
    .expectError(AuthenticationCredentialsNotFoundException.class)
    .verify();
```

**This is service behavior that you design**; Spring Security does not automatically throw an exception on every `ReactiveSecurityContextHolder.getContext()` call with a missing context.

---

## 6. Testing a Full `SecurityContext` with `withSecurityContext()`

When you want to test a specific `SecurityContext` rather than passing `Authentication` directly, build the context:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;

Authentication bob = new TestingAuthenticationToken(
    "bob", "not-used", "ROLE_AUDITOR");

SecurityContext context = new SecurityContextImpl(bob);

Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

StepVerifier.create(
        currentName.contextWrite(
            ReactiveSecurityContextHolder
                .withSecurityContext(Mono.just(context))))
    .expectNext("bob")
    .verifyComplete();
```

### 6.1. Why Does `withSecurityContext` Accept a `Mono`?

In the reactive model, `SecurityContext` can come from a **reactive repository** or deferred load. Spring Security lets you bind a `Mono<? extends SecurityContext>` into the Reactor context.

Example:

```java
Mono<SecurityContext> contextPublisher = Mono.just(context);

Mono<String> result = currentName.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(contextPublisher));
```

**No need to call `block()` to obtain the context before building the pipeline.** The consumer uses `ReactiveSecurityContextHolder.getContext()` to subscribe following the reactive flow.

### 6.2. Testing `clearContext()`

When verifying that a branch has its security context cleared:

```java
Mono<String> result = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .defaultIfEmpty("guest")
    .contextWrite(ReactiveSecurityContextHolder.clearContext());

StepVerifier.create(result)
    .expectNext("guest")
    .verifyComplete();
```

In this standalone test, `clearContext()` makes upstream `SecurityContext` reads empty. It **is not an API that logs out an OP session or revokes access tokens**.

### 6.3. Do Not Mutate a `SecurityContext` Shared Across Multiple Tests

A `SecurityContextImpl` is a mutable object. If you do:

```java
static final SecurityContext SHARED = new SecurityContextImpl();
```

and tests concurrently call `setAuthentication(...)`, results can cross-contaminate. Create separate contexts and `Authentication`s per test/subscription, or use immutable fixtures where appropriate.

---

## 7. Reading and Checking Authorities in Reactor

Suppose a service checks permissions:

```java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.GrantedAuthority;
import reactor.core.publisher.Mono;

public final class AuthorityLookup {

    public Mono<Boolean> has(String authority) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getAuthorities)
            .map(granted -> granted.stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch(authority::equals))
            .defaultIfEmpty(false);
    }
}
```

Test:

```java
@Test
void checksAuthoritiesFromCurrentSubscription() {
    Authentication editor = new TestingAuthenticationToken(
        "editor", "unused", "ROLE_EDITOR", "SCOPE_reports.read");

    Mono<Boolean> allowed = new AuthorityLookup()
        .has("ROLE_EDITOR")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(editor));

    StepVerifier.create(allowed)
        .expectNext(true)
        .verifyComplete();
}
```

Negative test:

```java
@Test
void rejectsWhenRequiredAuthorityIsAbsent() {
    Authentication viewer = new TestingAuthenticationToken(
        "viewer", "unused", "ROLE_VIEWER");

    Mono<Boolean> allowed = new AuthorityLookup()
        .has("ROLE_EDITOR")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer));

    StepVerifier.create(allowed)
        .expectNext(false)
        .verifyComplete();
}
```

**Important:** a `GrantedAuthority` can be `ROLE_EDITOR` or `SCOPE_reports.read`. An OIDC claim named `groups` does not turn into `ROLE_EDITOR` automatically if production has no role mapper.

---

## 8. Simulating a Real OIDC Principal in the Reactor Context

With Spring Security OAuth2 Client, production `Authentication` is typically an `OAuth2AuthenticationToken` carrying an `OidcUser`. To unit-test a service that reads `OidcUser`, you can construct a principal and `Authentication` directly.

### 8.1. Constructing a Mock `OidcUser`

```java
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

OidcIdToken idToken = OidcIdToken.withTokenValue("synthetic-id-token")
    .claim("sub", "employee-42")
    .claim("tenant_id", "tenant-a")
    .claim("preferred_username", "nguyen.an")
    .build();

OidcUser user = new DefaultOidcUser(
    AuthorityUtils.createAuthorityList(
        "SCOPE_read", "ROLE_REPORT_READER"),
    idToken,
    "preferred_username");
```

This is a **mock ID Token object**, not an ID Token signed by an OP or verified by a `JwtDecoder`.

### 8.2. Creating an `OAuth2AuthenticationToken`

```java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;

OAuth2AuthenticationToken authentication =
    new OAuth2AuthenticationToken(
        user,
        user.getAuthorities(),
        "company");
```

The `company` registration ID indicates which client login was used; it **does not prove the real issuer** of the ID Token. When testing multi-provider boundaries, keep `registrationId`, ID Token issuer, subject, and policy consistent independently.

### 8.3. `StepVerifier` Reading Subject

Service:

```java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public Mono<String> currentOidcSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(auth -> auth instanceof OAuth2AuthenticationToken)
        .map(auth -> (OAuth2AuthenticationToken) auth)
        .map(OAuth2AuthenticationToken::getPrincipal)
        .filter(principal -> principal instanceof OidcUser)
        .map(principal -> ((OidcUser) principal).getIdToken().getSubject());
}
```

Test:

```java
StepVerifier.create(
        identityService.currentOidcSubject()
            .contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(authentication)))
    .expectNext("employee-42")
    .verifyComplete();
```

If the service requires `@PreAuthorize`, test through a **Spring-managed proxy** in a context with reactive method security enabled; instantiating the service with `new` does not apply method interceptors.

### 8.4. When Should You Build the Principal Manually?

- Unit testing a service that reads `Authentication` from the Reactor Context;
- Testing policy depending on `registrationId`, `sub`, `tenant_id`, or authorities;
- Avoiding starting an HTTP server;
- Testing context propagation or cancellation on a publisher.

When the goal is an **HTTP controller test**, `WebTestClient.mutateWith(mockOidcLogin())` is usually shorter and more appropriate.

---

## 9. `WebTestClient` and Spring Security Reactive

`WebTestClient` is the WebFlux HTTP testing tool. Spring Security Test provides `WebTestClientConfigurer`s to inject `Authentication` into test requests.

### 9.1. Helper Selection Table

| Request goal | Spring Security Test Reactive helper |
| --- | --- |
| Generic username/roles | **`mockUser()`** |
| Complete `Authentication` | **`mockAuthentication(authentication)`** |
| OAuth2 login principal + attributes | **`mockOAuth2Login()`** |
| OIDC login principal + ID Token/UserInfo | **`mockOidcLogin()`** |
| Standalone authorized client | `mockOAuth2Client("registration-id")` |
| Resource Server Bearer JWT | **`mockJwt()`** |
| Resource Server opaque token | `mockOpaqueToken()` |
| CSRF on HTTP requests | `csrf()` mutator |

**Do not call Servlet `MockMvc`'s `oidcLogin()` on `WebTestClient`.**

### 9.2. Explicit `WebTestClient` Setup

When binding manually to a Spring `ApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

class ReactiveWebTests {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

This assumes the test class already has a Spring Test context, such as `@SpringJUnitConfig`, `@WebFluxTest`, or `@SpringBootTest` with WebFlux. When using `@WebFluxTest` with an auto-configured `WebTestClient`, you can inject the client directly, but still confirm the Spring Security filter chain is active.

### 9.3. `@WebFluxTest` vs. `@SpringBootTest`

- `@WebFluxTest`: focuses on MVC-equivalent WebFlux controllers, codecs, validators, and configurations loaded by the slice; other services may need mocks/imports.
- `@SpringBootTest`: full application context, suited for broader wiring checks.
- `WebTestClient.bindToApplicationContext`: executes simulated HTTP exchanges **inside the application context**, without opening a TCP port.
- `WebTestClient.bindToServer`: HTTP client talking to a real server; mock mutators that attach `SecurityContext` to an in-memory server exchange **cannot replace real authentication on another server process**.

Do not place `@WithMockUser` on a test thread and assume a server running on another port will observe that test's `ThreadLocal`.

---

## 10. `mockUser()`: Generic Principal and Authorities

When a controller only needs `Principal.getName()`, `Authentication.getName()`, or roles, `mockUser()` is enough.

Controller:

```java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class GreetingController {

    @GetMapping("/api/greet")
    Mono<String> greet(Principal principal) {
        return Mono.just("Hello " + principal.getName());
    }
}
```

Test:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("alice").roles("USER"))
    .get().uri("/api/greet")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("Hello alice");
```

### 10.1. `@WithMockUser` in `WebTestClient` Tests

Spring Security Test also supports:

```java
@Test
@WithMockUser(username = "alice", roles = "USER")
void greetingWithAnnotation() {
    client.get().uri("/api/greet")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("Hello alice");
}
```

This requires the proper **Spring Test context and Spring Security test listeners**. For independent HTTP requests with different fixtures per call, `mutateWith(mockUser(...))` is usually clearer.

### 10.2. `@WithMockUser` Does Not Create `OidcUser`

If a controller declares `@AuthenticationPrincipal OidcUser`, a standard `@WithMockUser` only creates a Spring Security `User` principal, not an `OidcUser`.

Use `mockOidcLogin()` or `mockAuthentication(OAuth2AuthenticationToken)` to test the right principal type.

### 10.3. `authorities` and `roles` Are Not the Same

```java
client.mutateWith(mockUser("bob")
        .authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange();
```

`hasRole("REPORT_READER")` looks for `ROLE_REPORT_READER` (default prefix), not `SCOPE_reports.read`. Tests must supply authorities matching the production authorization policy.

---

## 11. `mockAuthentication()`: Testing Custom `Authentication`

When you want to inject a specific `Authentication` instance, use:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
    "user-42",
    "unused",
    java.util.List.of(
        new SimpleGrantedAuthority("ROLE_REPORT_READER")));

client.mutateWith(mockAuthentication(auth))
    .get().uri("/api/whoami")
    .exchange()
    .expectStatus().isOk();
```

`mockAuthentication(...)` is a **test mutator on Reactive `WebTestClient`**. It does not run password checks, token exchange, issuer validation, or a production `AuthenticationManager`.

### 11.1. Option When You Have a Custom Principal

If code expects:
- A custom `UserDetails`;
- A specific `OAuth2AuthenticationToken`;
- A `JwtAuthenticationToken`;
- A test implementation of `Authentication`;

inject the matching instance via `mockAuthentication`. Do not force a controller to cast a principal to `OidcUser` if the fixture is a `String` or `UserDetails`.

### 11.2. Test Both Allowed and Denied Cases

A policy checking `ROLE_REPORT_READER` needs at least:
- User with the authority → allowed;
- Authenticated user missing the authority → denied;
- No authenticated user → 401/302 per security entry point.

A single passing test does not prove the security filter was actually applied.

---

## 12. `mockOidcLogin()`: Testing OIDC Principal and Claims

For a WebFlux OIDC Client, the standard helper is:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
```

Example:

```java
client.mutateWith(mockOidcLogin())
    .get().uri("/api/oidc-subject")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("user");
```

According to Spring Security Test 6.5 docs, `mockOidcLogin()` provides by default:
- An `OidcUser`;
- `OidcIdToken` with `sub=user`;
- `OidcUserInfo` with no claims;
- Authorities including `SCOPE_read`;
- A linked mock authorized client in the corresponding `ServerOAuth2AuthorizedClientRepository`.

### 12.1. ID Token Claims

```java
client.mutateWith(mockOidcLogin()
        .idToken(idToken -> idToken
            .claim("sub", "employee-42")
            .claim("tenant_id", "tenant-a")
            .claim("preferred_username", "nguyen.an")))
    .get().uri("/api/oidc-tenant")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("tenant-a");
```

`idToken(...)` only edits the **ID Token model in the fixture**. It does not sign a real JWT and does not run `JwtDecoder`/OIDC issuer/nonce validation.

### 12.2. UserInfo — Different Method Name from Servlet

In **Reactive Spring Security Test 6.5**, use:

```java
client.mutateWith(mockOidcLogin()
        .userInfo(info -> info
            .claim("name", "Nguyễn An")
            .claim("locale", "vi-VN")))
    .get().uri("/api/display-name")
    .exchange()
    .expectStatus().isOk();
```

**The Reactive API is `mockOidcLogin().userInfo(...)`**. Do not copy `oidcLogin().userInfoToken(...)` from Servlet `MockMvc` into Reactive tests.

### 12.3. Authorities

```java
client.mutateWith(mockOidcLogin()
        .authorities(
            new SimpleGrantedAuthority("ROLE_REPORT_READER"),
            new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

The specified authorities serve authorization testing. **Claims like `groups` or `roles` in the ID Token are not automatically mapped to `ROLE_*` by the post-processor**. Test production role mapping in the service/mapper separately.

### 12.4. Custom `OidcUser`

If the principal name should use `preferred_username`:

```java
OidcUser custom = new DefaultOidcUser(
    AuthorityUtils.createAuthorityList("SCOPE_read"),
    OidcIdToken.withTokenValue("synthetic-token")
        .claim("sub", "employee-42")
        .claim("preferred_username", "nguyen.an")
        .build(),
    "preferred_username");

client.mutateWith(mockOidcLogin().oidcUser(custom))
    .get().uri("/api/whoami")
    .exchange();
```

`oidcUser(custom)` replaces the entire principal. Once a custom principal is provided, avoid assuming other `idToken(...)` or `userInfo(...)` calls will merge in your preferred precedence.

### 12.5. Registration and Multi-Provider

`mockOidcLogin().clientRegistration(clientRegistration)` lets you choose the `ClientRegistration` associated with the test authorized client.

For instance, the same `sub=user-42` from two different issuers does not automatically mean the same identity; identity mapping tests should use **`(issuer, subject)`** and an explicit account-linking policy. The post-processor does not verify that the ID Token issuer claim matches the registration.

---

## 13. `mockOAuth2Login()`: Testing Non-OIDC OAuth2 Principals

A controller needing `OAuth2User.getAttribute("user_id")`:

```java
import org.springframework.security.oauth2.core.user.OAuth2User;

@GetMapping("/api/oauth2-user-id")
Mono<String> oauth2UserId(@AuthenticationPrincipal OAuth2User user) {
    return Mono.justOrEmpty(user.getAttribute("user_id"));
}
```

Test:

```java
client.mutateWith(mockOAuth2Login()
        .attributes(attrs -> {
            attrs.put("sub", "user-42");
            attrs.put("user_id", "internal-123");
            attrs.put("email_verified", Boolean.TRUE);
        }))
    .get().uri("/api/oauth2-user-id")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("internal-123");
```

`mockOAuth2Login()` creates an `OAuth2User` with attributes; it **does not automatically include an `OidcIdToken`**.

### 13.1. Custom `OAuth2User`

```java
OAuth2User custom = new DefaultOAuth2User(
    AuthorityUtils.createAuthorityList("SCOPE_read"),
    java.util.Map.of(
        "user_name", "partner-01",
        "user_id", "partner-123"),
    "user_name");

client.mutateWith(mockOAuth2Login().oauth2User(custom))
    .get().uri("/api/whoami")
    .exchange();
```

`oauth2User(custom)` is useful when testing `getName()` or a custom principal implementation.

### 13.2. Use Accurate Claim Data Types

An `email_verified` attribute is normally a `Boolean`. If a test passes the string `"true"`, a `Boolean` cast in production can fail.

For list/group claims, use the right types such as `List<String>` or `Map<String, Object>`. Do not assume all OPs return identical raw types.

---

## 14. WebFlux Controller Reading `Authentication` from Reactor Context

To clearly see that context is read at **subscription time**, create a controller:

```java
package example.web;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    Mono<Map<String, String>> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> Map.of(
                "name", auth.getName(),
                "authenticationType",
                    auth.getClass().getSimpleName()));
    }

    @GetMapping("/api/oidc-subject")
    Mono<String> subject(@AuthenticationPrincipal OidcUser user) {
        return Mono.just(user.getIdToken().getSubject());
    }

    @GetMapping("/api/oidc-tenant")
    Mono<String> tenant(@AuthenticationPrincipal OidcUser user) {
        return Mono.justOrEmpty(
            user.getIdToken().getClaimAsString("tenant_id"));
    }
}
```

This assumes the endpoints are protected and `/api/oidc-*` is only invoked when `Authentication` actually carries an `OidcUser`. In apps accepting multiple user types, check principal type and missing claims to avoid `NullPointerException`.

### 14.1. Configuring `SecurityWebFilterChain`

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class WebSecurityConfiguration {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public", "/error").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This configuration **intentionally uses HTTP Basic in test/demo** so anonymous requests clearly return 401. When a production app enables `oauth2Login()`, the browser entry point may return **302 to the login page** rather than 401.

### 14.2. Testing with `@WebFluxTest`

```java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@WebFluxTest(controllers = IdentityController.class)
@Import(WebSecurityConfiguration.class)
class IdentityControllerWebTest {

    @Autowired
    WebTestClient client;

    @Test
    void currentAuthenticationComesFromRequest() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/api/whoami")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice");
    }

    @Test
    void oidcSubjectIsAvailable() {
        client.mutateWith(mockOidcLogin()
                .idToken(token ->
                    token.claim("sub", "employee-42")))
            .get().uri("/api/oidc-subject")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("employee-42");
    }

    @Test
    void oidcCustomClaimIsAvailable() {
        client.mutateWith(mockOidcLogin()
                .idToken(token ->
                    token.claim("tenant_id", "tenant-a")))
            .get().uri("/api/oidc-tenant")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("tenant-a");
    }

    @Test
    void anonymousRequestIsRejected() {
        client.get().uri("/api/whoami")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Requirement:** the test must have Spring Security filters genuinely integrated with `WebTestClient`. With a standard `@WebFluxTest`, Spring Boot usually auto-configures `WebTestClient`; when building the client manually or altering slice configuration, you may need `.apply(springSecurity())` explicitly as in section 9.

**Note:** importing `WebSecurityConfiguration` from another package requires adjusting the Java import in actual source code. Separating classes into files by package illustrates architecture, not a single copy-paste Java file.

---

## 15. Testing Reactive Method Security with `@WithMockUser`

This section matters because a reactive service may be protected by `@PreAuthorize`.

Sample service:

```java
package example.reports;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('ROLE_REPORT_READER')")
    public Mono<String> summary() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "summary-for:" + auth.getName());
    }
}
```

Method security configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReportMethodSecurityConfiguration {
}
```

### 15.1. Testing with `@WithMockUser` and `StepVerifier`

```java
package example.reports;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = {
    ReportMethodSecurityConfiguration.class,
    ReportService.class
})
class ReportServiceSecurityTest {

    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "ROLE_REPORT_READER")
    void readerCanRead() {
        StepVerifier.create(reports.summary())
            .expectNext("summary-for:alice")
            .verifyComplete();
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "ROLE_VIEWER")
    void viewerCannotRead() {
        StepVerifier.create(reports.summary())
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void anonymousCannotRead() {
        StepVerifier.create(reports.summary())
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

Spring Security reactive method testing docs use **`@WithMockUser`** with `StepVerifier`. For this to work, you need:
- Spring Test extension/listeners;
- A Spring-managed bean/proxy of the service;
- `@EnableReactiveMethodSecurity`;
- `ReactorContextTestExecutionListener` when the test environment does not auto-register it;
- The publisher to be **subscribed to**, e.g., via `StepVerifier`.

### 15.2. What Does `ReactorContextTestExecutionListener` Do?

Spring Security test infrastructure has two related listeners:

| Listener | Role |
| --- | --- |
| `WithSecurityContextTestExecutionListener` | Sets up test `Authentication` from `@WithMockUser` / `@WithSecurityContext` |
| **`ReactorContextTestExecutionListener`** | Bridges the test security context to **`ReactiveSecurityContextHolder`/Reactor context** for reactive tests |

If only `ThreadLocal` `TestSecurityContextHolder` is active without the Reactor listener, synchronous Java code in a unit test may see the user while reactive publishers may not.

### 15.3. When Test Listeners Are Configured Manually

```java
@TestExecutionListeners(
    listeners = {
        WithSecurityContextTestExecutionListener.class,
        ReactorContextTestExecutionListener.class
    },
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

This is a **supplemental pattern when listener configuration is missing**, not advice to always register duplicate listeners in every test. With standard Spring Security Test + Spring Test, listeners may already be discovered/registered. If configuring manually, check listener ordering and merge semantics for your version.

### 15.4. Why Are Both Positive and Negative Cases Needed?

If you only test:

```java
@WithMockUser(authorities = "ROLE_REPORT_READER")
```

and observe the expected result, there could still be a bug where `@EnableReactiveMethodSecurity` is not enabled: the method is never blocked, and the positive case still passes.

A negative test lacking permission (expecting `AccessDeniedException`) is essential to prove the method interceptor is actually active.

### 15.5. Do Not Instantiate Services with `new` When Testing `@PreAuthorize`

Wrong:

```java
ReportService service = new ReportService();
StepVerifier.create(service.summary()) ...;
```

An object created via `new` outside the Spring context **has no method-security AOP proxy**. When testing annotations, inject the bean from the Spring Test context.

---

## 16. Testing Method Security with `contextWrite` Instead of Annotations

In some cases you need a complex principal such as `OidcUser` that `@WithMockUser` does not supply. You can pass an `OAuth2AuthenticationToken` via `contextWrite` directly on the publisher returned by the Spring-managed bean:

```java
OidcUser oidcUser = new DefaultOidcUser(
    AuthorityUtils.createAuthorityList(
        "ROLE_REPORT_READER"),
    OidcIdToken.withTokenValue("synthetic")
        .claim("sub", "employee-42")
        .build());

Authentication authentication = new OAuth2AuthenticationToken(
    oidcUser,
    oidcUser.getAuthorities(),
    "company");

Mono<String> result = reportService.summary()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));

StepVerifier.create(result)
    .expectNext("summary-for:employee-42")
    .verifyComplete();
```

Requirements:
- `reportService` must be a **Spring-managed proxy** if `@PreAuthorize` is needed;
- The method must return a publisher and the interceptor reads context during subscription;
- Default `OidcUser.getName()` is typically based on subject, so the expected username from the fixture is `employee-42`;
- The goal is testing **authorization with an `Authentication` holding a specific principal type**, not testing ID Token signatures.

### 16.1. Combined Tenant/Role Testing

If a method policy is:

```java
@PreAuthorize("hasAuthority('ROLE_REPORT_READER') and @tenantGuard.allowed(#tenantId)")
public Mono<String> report(String tenantId) { ... }
```

tests must verify all of:
- User with role in tenant A calling tenant A → pass;
- User with role in tenant A calling tenant B → denied;
- User lacking role in tenant A → denied;
- Anonymous → denied.

`withAuthentication` passes the principal with the `tenant_id` test fixture into the service, yet **does not run the tenant guard** if the service is not managed by Spring AOP.

---

## 17. How Do Spring-Managed `@WithMockUser` and Direct `contextWrite` Differ?

| Test approach | Suited for | Depends on |
| --- | --- | --- |
| **`@WithMockUser`** | Reactive method security with generic `UserDetails` + roles | Spring Test + Security test listeners |
| **`.contextWrite(withAuthentication(...))`** | Unit-testing publishers or services needing custom `Authentication` | Reactor Context on the publisher |
| **`.contextWrite(withSecurityContext(Mono.just(...)))`** | Testing custom/deferred `SecurityContext` | `SecurityContext` publisher |
| **`WebTestClient.mutateWith(mockUser())`** | Generic HTTP WebFlux requests | Spring Security `WebTestClient` support |
| **`WebTestClient.mutateWith(mockOidcLogin())`** | OIDC HTTP principal, claims, authorities | Spring Security reactive test config |
| **`WebTestClient.mutateWith(mockAuthentication(...))`** | HTTP requests with custom `Authentication` | Spring Security reactive test config |

**No single approach is always better.** Choose based on the boundary:
- Publisher unit test: `StepVerifier + contextWrite`;
- Spring AOP method test: `@WithMockUser` or `contextWrite` on a proxied service;
- WebFlux HTTP test: `WebTestClient.mutateWith`;
- Real OIDC redirect/PKCE/JWT validation: integration test with a mock OP.

---

## 18. Testing Context Propagation Across Reactor Operators

A practical question is **"when switching schedulers, is `Authentication` still preserved?"**.

### 18.1. With `publishOn`

```java
@Test
void keepsIdentityAcrossPublishOn() {
    Authentication alice = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_USER");

    Mono<String> pipeline = Mono.just("request")
        .publishOn(Schedulers.parallel())
        .flatMap(ignored ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName))
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

    StepVerifier.create(pipeline)
        .expectNext("alice")
        .verifyComplete();
}
```

This tests **native Reactor Context propagation**. You do not manually copy `ThreadLocal` from the test thread onto `Schedulers.parallel()`.

### 18.2. With Concurrent `Flux.flatMap`

```java
@Test
void multipleElementsSeeSameSubscriberIdentity() {
    Authentication alice = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_USER");

    Flux<String> values = Flux.range(1, 3)
        .flatMap(i ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(auth -> auth.getName() + ":" + i))
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

    StepVerifier.create(values.collectList())
        .assertNext(list -> {
            org.assertj.core.api.Assertions.assertThat(list)
                .containsExactlyInAnyOrder(
                    "alice:1", "alice:2", "alice:3");
        })
        .verifyComplete();
}
```

`flatMap` can reorder emissions, so use `containsExactlyInAnyOrder` instead of assuming a fixed order.

### 18.3. Testing Two Subscriptions with Different Identities

```java
@Test
void subscriptionsDoNotShareCurrentUser() {
    Mono<String> current = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

    Authentication alice = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_USER");
    Authentication bob = new TestingAuthenticationToken(
        "bob", "unused", "ROLE_USER");

    StepVerifier.create(current.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(current.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(bob)))
        .expectNext("bob")
        .verifyComplete();
}
```

Both subscriptions share the same **publisher blueprint** yet have separate contexts. Never create a `static String currentUsername` and overwrite it on every request.

### 18.4. Do Not Use `Thread.sleep()` to "Wait for Context to Appear"

Reactor Context is determined by subscription, not by elapsed time. If a test is missing context, sleeping 1 second will not supply `Authentication`. Check `contextWrite` placement, `WebTestClient` config, and test listeners.

---

## 19. Boundaries That Can Lose `SecurityContext`

Reactor Context persists across composed operators, but external asynchronous mechanisms do not automatically inherit it.

### 19.1. Manual `subscribe()`

Anti-pattern in a service:

```java
public Mono<String> process() {
    downstreamCall()
        .subscribe(result -> audit(result)); // Detached subscription!
    return Mono.just("accepted");
}
```

The new subscription has its own lifecycle and Context; the caller cannot use `StepVerifier` on the returned publisher to control or fully assert the side effect. `SecurityContext` may not propagate properly to the detached subscription.

Better:

```java
public Mono<String> process() {
    return downstreamCall()
        .flatMap(result -> audit(result)
            .thenReturn("accepted"));
}
```

In this example, `audit(result)` returns `Mono<Void>`; composing it into the same chain keeps context, errors, and cancellation under control.

### 19.2. Switching to `CompletableFuture`/Executor

```java
CompletableFuture.supplyAsync(() ->
    SecurityContextHolder.getContext().getAuthentication());
```

This runs on another thread using `ThreadLocal`. It does not automatically see the subscription's `ReactiveSecurityContextHolder`.

If you must call a blocking API:
- Prefer keeping the flow inside a publisher on `boundedElastic` appropriately;
- Pass minimal verified identity fields as arguments to the callable when needed;
- Consider a context propagation bridge/instrumentation suited to your Reactor version;
- Never copy the entire `SecurityContext` into a global mutable variable;
- Never block on the event loop.

### 19.3. Enabling Automatic Context Propagation Does Not Replace Authentication

Reactor supports automatic context propagation across certain `ThreadLocal` bridges when configured. That is an **interoperability mechanism**—it does not mean you can revert to `SecurityContextHolder` everywhere or abandon `ReactiveSecurityContextHolder`.

Tests should treat **reactive security APIs** as the source of truth. If integrating a legacy `ThreadLocal` library, write dedicated tests for that boundary and document the assumptions/tooling clearly.

### 19.4. Losing Context Because a Branch Is Not Composed

Example:

```java
Mono<String> createPublisher() {
    Mono<String> inner = someOperation()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

    return otherOperation(); // inner is never returned/subscribed.
}
```

Merely declaring a publisher does not ensure it runs. In Reactor, composition is essential to preserve lifecycle and context.

---

## 20. Testing Context at Subscription Time

Rule: **never capture `Authentication` at publisher construction time** if it must depend on the subscriber.

### 20.1. Wrong: Snapshotting a Global Value

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

Mono<String> response = Mono.just(auth.getName());
```

Problems:
- `auth` may be `null` before a request is subscribed;
- It may capture the wrong user;
- It does not reflect each subscription's user.

### 20.2. Right: Deferred/Reactive Lookup

```java
Mono<String> response =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

The **subscriber's** context determines the result.

### 20.3. `Mono.deferContextual` When General Reactor Context Is Needed

```java
Mono<String> traceId = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("traceId", "none")));
```

This is for **application-defined Reactor Context keys**. For Spring Security `Authentication`, prefer **`ReactiveSecurityContextHolder.getContext()`** rather than poking around for Spring Security's internal key in `ContextView`.

### 20.4. Do Not Store `Authentication` in an Instance Field

```java
@Service
class BadCurrentUserService {
    private Authentication current; // Wrong: shared mutable state on a singleton.

    Mono<String> name() {
        return Mono.just(current.getName());
    }
}
```

Spring services are typically singletons; if each request updates this field, users can see another request's identity. Reactor Context prevents this broken design.

---

## 21. Testing Zero Identity Leakage Across Multiple Users

Suppose the application handles two concurrent requests:
- Alice: `ROLE_REPORT_READER`;
- Bob: `ROLE_VIEWER`.

A useful test subscribes to the **same service publisher** under two contexts.

```java
Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Authentication alice = new TestingAuthenticationToken(
    "alice", "unused", "ROLE_REPORT_READER");

Authentication bob = new TestingAuthenticationToken(
    "bob", "unused", "ROLE_VIEWER");

Mono<String> aliceCall = currentName
    .delayElement(java.time.Duration.ofMillis(10))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));

Mono<String> bobCall = currentName
    .delayElement(java.time.Duration.ofMillis(5))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob));

StepVerifier.create(Mono.zip(aliceCall, bobCall))
    .expectNextMatches(tuple ->
        tuple.getT1().equals("alice")
            && tuple.getT2().equals("bob"))
    .verifyComplete();
```

`Mono.zip` creates separate subscriptions for both sources, each with its own `contextWrite`. Delays/threads are incidental, **not the safety mechanism**. The goal is to verify identity isolation.

### 21.1. Do Not Read `userName` from a Raw Request Header

```java
String current = request.getHeaders().getFirst("X-User");
```

If an external client can send that header itself, it is not a verified identity. Controllers/services should read identity from the `Authentication` established by Spring Security, never from a self-declared header unless behind a strictly protected, trusted gateway contract.

### 21.2. Multi-Tenant Apps Require Testing Beyond Global Roles

A user with `ROLE_REPORT_READER` who belongs only to tenant A does not automatically have permission to read tenant B's reports.

In tests, keep `issuer`, `sub`, `tenant_id`, and authorities consistent and verify the domain authorization policy separately, not just `hasRole`.

---

## 22. Testing Anonymous and Authenticated: Common Pitfalls

### 22.1. Reactor Context Lacks `Authentication`

If `ReactiveSecurityContextHolder.getContext()` is empty, a service returning `Mono.empty()` can lead to HTTP 200 with an empty body if the controller does not enforce authentication itself.

To ensure an endpoint is **truly protected**, configure Spring Security `SecurityWebFilterChain`:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .anyExchange().permitAll());
```

Or the corresponding method security. Calling `getContext()` in a controller does not automatically turn every missing `Authentication` into HTTP 401.

### 22.2. `AnonymousAuthenticationToken` in WebFlux

Depending on the filter chain, an anonymous request may hold an `AnonymousAuthenticationToken`. Never rely solely on `auth != null` or `auth.isAuthenticated()` to conclude "logged in via OIDC".

Use the `.authenticated()` authorization matcher or proper principal type checks.

### 22.3. 401, 403, and 302

- **401**: HTTP API with an entry point returning Unauthorized, e.g., HTTP Basic;
- **403**: Authenticated user lacking authority, or CSRF failure;
- **302**: Browser OAuth2 Login entry point redirecting to the login page/OP.

A `WebTestClient.expectStatus().isUnauthorized()` test is only valid if the security chain and endpoint are designed to return 401. Never infer production browser login behavior from a test-only chain's expected status.

---

## 23. Testing Reactor Context in Publishers That Emit Errors

A pipeline may fail after reading `Authentication`. Tests must check **error signals**, not only the happy path.

### 23.1. Failing When Permission Is Missing

```java
import org.springframework.security.access.AccessDeniedException;

Mono<String> guarded = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(auth -> {
        boolean allowed = auth.getAuthorities().stream()
            .anyMatch(granted ->
                "ROLE_REPORT_READER".equals(granted.getAuthority()));

        return allowed
            ? Mono.just("ok")
            : Mono.error(
                new AccessDeniedException("forbidden"));
    })
    .switchIfEmpty(
        Mono.error(new AccessDeniedException("no authentication")));

Authentication viewer = new TestingAuthenticationToken(
    "viewer", "unused", "ROLE_VIEWER");

StepVerifier.create(guarded.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(viewer)))
    .expectError(AccessDeniedException.class)
    .verify();
```

### 23.2. Do Not Mask Errors with `onErrorResume` Granting Default Privileges

Wrong:

```java
return securityCheck()
    .onErrorResume(error -> Mono.just("ADMIN"));
```

If `securityCheck()` fails due to missing authentication/authorization, `onErrorResume` must never turn the error into a privileged principal/role.

Always fail closed and return the right error code, rather than opening permissions to "reduce test flakes".

### 23.3. Testing Cancellation

```java
Flux<String> securedStream = Flux.interval(
        java.time.Duration.ofMillis(10))
    .flatMap(i ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(securedStream)
    .expectNext("alice")
    .thenCancel()
    .verify();
```

With an infinite source such as `Flux.interval`, `thenCancel()` keeps the test from waiting forever for completion. Remember that cancellation also affects resource cleanup, not just `SecurityContext`.

### 23.4. Do Not Block the Event Loop in Tests

```java
String name = securedStream.blockLast();
```

This is inappropriate for an infinite `Flux` and can block the event loop if used in the wrong context. `StepVerifier` lets you verify bounded signals with explicit termination.

---

## 24. Principal from Controller Method Argument or from `ReactiveSecurityContextHolder`?

A WebFlux controller can accept a principal via arguments:

```java
@GetMapping("/api/me")
Mono<String> me(Principal principal) {
    return Mono.just(principal.getName());
}
```

Or use:

```java
@GetMapping("/api/subject")
Mono<String> subject(@AuthenticationPrincipal OidcUser user) {
    return Mono.just(user.getIdToken().getSubject());
}
```

Or read inside a service via:

```java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

**When to use which?**

| Location | Appropriate way to obtain identity |
| --- | --- |
| Controller only needs name | `Principal` or `Authentication` argument |
| Controller needs ID Token/UserInfo | `@AuthenticationPrincipal OidcUser` |
| Reactive service deep in pipeline | **`ReactiveSecurityContextHolder.getContext()`**, or pass identity explicitly |
| Pure Java domain service | Pass verified `userId`/`tenantId` as parameters, avoiding framework coupling where suitable |
| Outbound `WebClient` needing OAuth2 token | `ServerOAuth2AuthorizedClientExchangeFilterFunction` / authorized-client infrastructure, not raw ID Token |
| Resource Server API | `Authentication` from Bearer token, usually `JwtAuthenticationToken` |

A domain service taking explicit identity arguments is easier to unit-test. However, if a service must check permissions in the subscription context, testing `ReactiveSecurityContextHolder` is necessary.

---

## 25. `@RegisteredOAuth2AuthorizedClient` in WebFlux Tests

In an OAuth2/OIDC Client, a controller sometimes needs an authorized client to call a downstream API:

```java
@GetMapping("/api/connection")
Mono<String> connection(
    @RegisteredOAuth2AuthorizedClient("reports")
    OAuth2AuthorizedClient authorizedClient) {

    return Mono.just(
        authorizedClient.getClientRegistration().getRegistrationId());
}
```

Reactive test helper:

```java
client.mutateWith(mockOAuth2Client("reports"))
    .get().uri("/api/connection")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("reports");
```

The context needs the WebFlux OAuth2 Client argument resolver/authorized-client infrastructure. In a tiny `@WebFluxTest` slice lacking that resolver, `mockOAuth2Client` alone cannot fabricate the missing infrastructure.

### 25.1. `Authentication` and Authorized Client Differ

- **`Authentication`**: current authenticated user, roles/authorities;
- **`OAuth2AuthorizedClient`**: registration + access token/refresh token for outbound resource access;
- **`ReactiveClientRegistrationRepository`**: metadata of OAuth2/OIDC clients.

`mockOidcLogin()` can set up a convenient mock authorized client, yet if a service uses `client_credentials` independently of a user, use the corresponding authorized-client helper.

### 25.2. Mock Authorized Client Does Not Refresh Tokens

`mockOAuth2Client` does not automatically:
- Send an Authorization Code token request;
- Refresh an access token;
- Validate OP/JWKS;
- Revoke credentials;
- Call a real API.

If the goal is testing refresh failure/`invalid_grant`, test `ReactiveOAuth2AuthorizedClientManager`/provider or write a separate token endpoint integration test.

---

## 26. Testing Resource Server Differs from OIDC Client Login

A WebFlux service can act as both an OAuth2 Client and a Resource Server. Two request patterns:

```text
Browser OIDC Login:
  SecurityWebFilterChain -> OAuth2AuthenticationToken(OidcUser)

API Bearer:
  Authorization: Bearer <access-token>
  SecurityWebFilterChain -> JwtAuthenticationToken / BearerTokenAuthentication
```

In `WebTestClient`:
- **`mockOidcLogin()`** is for OIDC login sessions;
- **`mockOAuth2Login()`** is for generic OAuth2 logins;
- **`mockJwt()`** is for Resource Server JWTs;
- **`mockOpaqueToken()`** is for opaque-token Resource Servers.

If a controller requires `OidcUser`, `mockJwt()` creates the wrong principal type. Conversely, an API service expecting `JwtAuthenticationToken` should not be tested with an OIDC session fixture just to get 200.

### 26.1. Token Signature Validation Is Not Executed by `mockJwt()`

`mockJwt()` provides a mock `Authentication` for testing authorization/controllers. It **does not prove a JWT was validly signed**. If the goal is testing the decoder's issuer/audience/signature/expiry checks, test the real decoder/integration path.

Similarly, `mockOidcLogin()` does not perform OP authorization, PKCE, `nonce`, or ID Token validation.

---

## 27. Common Test Configuration Errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `ReactiveSecurityContextHolder.getContext()` is empty | Context not attached to subscription | `contextWrite(withAuthentication(...))` / test listener |
| Test sees user via `ThreadLocal` yet publisher is empty | Used `SecurityContextHolder` instead of reactive | Use `ReactiveSecurityContextHolder` and Reactor listener |
| `@WithMockUser` has no effect in `StepVerifier` | Missing `ReactorContextTestExecutionListener` or Spring Test context | Register listeners properly |
| `mockOidcLogin()` does not compile | Wrong static import / missing `spring-security-test` | Use reactive `SecurityMockServerConfigurers` |
| `oidcLogin()` cannot be used with `WebTestClient` | Using Servlet helper | Switch to `mockOidcLogin()` |
| `userInfoToken()` missing on reactive helper | Different from Servlet API | Reactive uses **`userInfo(...)`** |
| `@AuthenticationPrincipal OidcUser` is null | Used `mockUser` or `mockJwt` (wrong type) | Use `mockOidcLogin` |
| Controller reads `tenant_id` = null | Claim set on wrong source or absent | Set `idToken(...).claim(...)` |
| `Authentication` changes user on another request | Shared mutable field/`SecurityContext` | Create fixtures per subscription |
| `@PreAuthorize` does not block viewer | Reactive method security disabled, bean not proxied | `@EnableReactiveMethodSecurity` + Spring bean + negative test |
| Test expects 401 yet gets 302 | OAuth2 browser login entry point | Assert per actual chain |
| Test gets 403 on POST despite role | CSRF filter rejects before method security | Add `mutateWith(csrf())` when testing policy past CSRF |
| `WebTestClient` mutator has no effect | Missing `.apply(springSecurity())` or connected to live server | Use mock binding/in-memory context properly |
| `StepVerifier` sees no emissions | Did not subscribe to right publisher, or source never completes | Use `StepVerifier` and termination/cancel |
| Context lost when switching threads | Code left Reactor or used detached subscription | Compose publishers, inspect boundaries |
| `publishOn` works yet `CompletableFuture` loses user | `ThreadLocal`/Context does not auto-propagate across non-Reactor APIs | Pass identity explicitly or use a safe bridge |
| Test passes despite wrong ID Token issuer | Mock OIDC bypasses cryptographic validation | Write OIDC decoder/callback integration test |
| Group claim lacks `ROLE_*` authority | Mock login does not run role mapper automatically | Test mapper separately or set authorities |
| Test has role yet cross-tenant access still passes | Only checking global role | Test domain ACL/tenant guard |
| One test affects the next | Shared context or sticky `@WithMockUser` | Isolate fixtures, listener cleanup, no mutable static |
| Fails when running on a real port | `@WithMockUser` only lives in test context | Send real HTTP auth or use mock server binding |
| `AuthenticationCredentialsNotFound` vs `AccessDenied` | Different exception translation/policy location | Distinguish method vs HTTP layer and assert right type |
| WebFlux test runs MVC stack | Both `web` & `webflux` starters present, Boot picks Servlet | Confirm reactive application type/config |
| Empty body returned instead of 401 | Service returns `Mono.empty`, HTTP filter is `permitAll` | Protect route/method properly |
| Scheduled job lacks user context | No HTTP subscriber/session | Supply service identity or explicit auth policy |

### 27.1. Do Not Fix Tests by Removing Security

```java
// Anti-pattern when the goal is testing authorization:
http.authorizeExchange(exchanges ->
    exchanges.anyExchange().permitAll());
```

A test returning 200 does not prove `Authentication` was checked. Ensure the security chain/method interceptors are active and add negative tests.

### 27.2. Do Not Call `block()` to "Catch" Identity

```java
// Do NOT do this in a request-processing reactive service:
String user = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .block();
```

Blocking can fail on a non-blocking event loop and breaks reactive architecture. Keep `Mono<String>` in the service and use `StepVerifier` at the test boundary.

---

## 28. Practice Scenarios

### Scenario A — Empty Context After Calling Service

Test:

```java
StepVerifier.create(identity.currentName())
    .expectNext("alice")
    .verifyComplete();
```

**Issue:** No `Authentication` was supplied to the subscription.

**Fix:** Use `contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))` or the appropriate Spring Test listener if the test uses `@WithMockUser`.

### Scenario B — `@WithMockUser` Works in Regular Tests Yet Reactive Service Returns Empty

**Hint:** `ReactorContextTestExecutionListener` may be missing, or the test uses a publisher not subscribed within the injected context. Check test configuration; do not switch the service to `SecurityContextHolder` `ThreadLocal`.

### Scenario C — Controller Needs `OidcUser`

Controller:

```java
Mono<String> subject(@AuthenticationPrincipal OidcUser user)
```

Test uses `mockUser("alice")`.

**Issue:** The principal is not an `OidcUser`. Use `mockOidcLogin()` with the appropriate ID Token claims.

### Scenario D — Changing UserInfo Claims

Test writes `mockOidcLogin().userInfoToken(...)`.

**Issue:** That is the method name for Servlet's `oidcLogin()` in Spring Security 6.5. Reactive tests use **`mockOidcLogin().userInfo(...)`**.

### Scenario E — Group Claim Present Yet Method Still Returns 403

```java
mockOidcLogin().idToken(token ->
    token.claim("groups", List.of("report-readers")))
```

**Explanation:** Having a claim alone does not grant `ROLE_REPORT_READER`. Either pass `authorities(...)` to test the policy, or test the real production mapper.

### Scenario F — Method Security Test Has Only One Positive Case

The admin role test returns 200, yet a viewer also gets 200.

**Cause:** The bean may not be proxied or `@EnableReactiveMethodSecurity` is not enabled. Add a negative test and use a Spring-managed bean.

### Scenario G — `Flux.flatMap` Runs Out of Order

`Flux.range(1,3).flatMap(...)` emits 2, 1, 3.

**How to assert:** If ordering is not part of the business contract, use `containsExactlyInAnyOrder`. Reactor Context remains valid even when scheduling varies.

### Scenario H — Detached Subscription Loses Identity

A service manually calls `subscribe()` on another publisher and returns. The `StepVerifier` test on the main publisher sees neither the side effect nor the context in the child publisher.

**Fix:** Compose publishers using `flatMap`/`then`; avoid fire-and-forget in business request paths.

### Scenario I — Two HTTP Requests Cross-Contaminate Principals

The application has `static Authentication current`; Alice and Bob call the endpoint together.

**Issue:** Shared mutable `Authentication` is not per-subscriber; user data can leak across requests. Use `ReactiveSecurityContextHolder` or pass verified user IDs down the pipeline.

### Scenario J — Testing `WebTestClient` Over Real Network

A test puts `@WithMockUser` on the test class while calling an application server running on another port.

**Explanation:** A server in a different process/thread cannot see the client's test context. Use real HTTP credentials/real login/a test identity provider, or in-memory application-context binding.

### Scenario K — Client and Resource Server in the Same App

A controller expects `JwtAuthenticationToken` yet the test uses `mockOidcLogin()`.

**Fix:** Use `mockJwt()` to test inbound JWTs; do not confuse it with an OIDC Login principal.

### Scenario L — "Expired" OIDC ID Token Still Passes Mock Test

**Explanation:** `mockOidcLogin` supplies a mocked `Authentication`, bypassing OP/JWT validation. Test decoder/token/issuer/nonce validation with an appropriate integration test.

### Scenario M — Anonymous Service Returns `Mono.empty`

The client expects 401, yet the controller returns `Mono.empty()` on a `permitAll` route and receives an empty 200.

**Fix:** Enforce authorization at the filter/method level or explicitly emit an error in the service. A missing context does not turn into Unauthorized by itself.

### Scenario N — Scope Authority and Role Confused

`hasRole("ADMIN")` requires `ROLE_ADMIN` (default prefix). The mock user has `SCOPE_admin`.

**Result:** Denied. Test with the exact authorities and policy; do not arbitrarily turn scopes into roles.

### Scenario O — Multi-Tenant Role Leakage

A test has `ROLE_REPORT_READER` and tenant claim A, yet the API allows viewing tenant B.

**Explanation:** A global role is insufficient. A domain tenant guard must check tenant/ownership; test a user with a valid role yet the wrong tenant.

### Scenario P — Async Boundary Using `CompletableFuture`

A service reads `SecurityContextHolder` inside `CompletableFuture.supplyAsync()` and sees `null`.

**How to handle:** Do not rely on `ThreadLocal`. Pass the verified identity across the boundary or use an explicitly tested context propagation bridge; keep most of the flow inside Reactor when possible.

### Scenario Q — No Spring Security Filter with `WebTestClient`

`mutateWith(mockUser())` fails to inject a principal into the controller.

**Hint:** Check `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` or Boot test security setup; do not use mutators when talking to a real server over the network.

### Scenario R — Test Needs OIDC Authorization Code/PKCE

**Question:** Does `mockOidcLogin()` check `state`, PKCE, or `nonce` on the authorization callback?

> No. It is a helper simulating an already logged-in user. Testing the real flow requires a mock OP/token endpoint/JWKS and a redirect-callback integration test.

---

## 29. Recommended Test Matrix

| Layer | Fixture | Verification |
| --- | --- | --- |
| Reactive service unit | `withAuthentication(alice)` + `StepVerifier` | Current user in subscription |
| Reactive service unit | No context / `clearContext` | Empty/fail closed |
| Reactive service unit | `withSecurityContext(Mono.just(context))` | Full context |
| Reactor pipeline | `publishOn` / `flatMap` | Identity preserved in Reactor |
| Concurrent requests | Two contexts + `Mono.zip` | No Alice/Bob mix-up |
| Reactive method security | `@WithMockUser` + Spring AOP + `StepVerifier` | `@PreAuthorize` allow/deny |
| OIDC method security | `OAuth2AuthenticationToken` + `contextWrite` | Permissions + right principal type |
| WebFlux controller | `WebTestClient.mutateWith(mockUser())` | Generic identity |
| WebFlux controller | `mockOidcLogin().idToken(...)` | OIDC claims |
| WebFlux controller | `mockOidcLogin().userInfo(...)` | UserInfo claims |
| WebFlux controller | `mockOAuth2Login().attributes(...)` | Generic OAuth2 attributes |
| WebFlux controller | `mockAuthentication(custom)` | Custom `Authentication` |
| WebFlux authorized client | `mockOAuth2Client(...)` | Registration/token metadata mocking |
| Resource Server API | `mockJwt()` | JWT principal/authorization |
| Authorization Code protocol | Mock OP + token endpoint + JWKS | `state`/PKCE/`nonce`/token validation |
| External HTTP server | Real test credentials/OP | Full network/browser contract |

### 29.1. Should Cancellation Be Tested?

Yes, if the application uses streaming or long-running publishers. `StepVerifier.thenCancel()` prevents tests from hanging, and you should verify resource cleanup/cancellation occurs. However, cancellation is not a way to log out a user or delete a session.

### 29.2. Should `StepVerifier.withVirtualTime` Be Tested?

If logic involves retries, delays, or timeouts, `StepVerifier.withVirtualTime(...)` can help. However, it does not alter `SecurityContext` semantics. You still need to verify identity is present in the subscription and preserved across time/scheduler changes.

### 29.3. Should Every ID Token Claim Be Tested?

Not necessarily. Focus on claims actually used by business code, along with negative cases for missing/type-mismatched values. Validating signatures/issuer/audience belongs to a separate integration layer.

---

## 30. Checklist for Debugging "Principal Null" in Reactive Tests

1. Are you running **WebFlux** or Servlet? Check which filter chain type is actually created.
2. Does code use `ReactiveSecurityContextHolder` or `ThreadLocal` `SecurityContextHolder`?
3. Is there an actual subscription (`StepVerifier`/`WebTestClient`)?
4. Is `contextWrite` placed on the right publisher/upstream branch that reads the context?
5. Does the constructed `Authentication` have the right principal type and authorities?
6. With Spring Test `@WithMockUser`, are the Reactive context listeners registered?
7. Do `@PreAuthorize` tests use a Spring-managed proxy and `@EnableReactiveMethodSecurity`?
8. With a manually built `WebTestClient`, is `.apply(springSecurity())` called?
9. Are `mockOidcLogin()`/`mockOAuth2Login()` imported from the right stack?
10. Does `@AuthenticationPrincipal` require OIDC while the fixture uses `mockUser` or `mockJwt`?
11. Does the pipeline use a detached `subscribe()` or cross into a non-Reactor async API?
12. Is a static/global mutable `Authentication` causing requests to collide?
13. When context is missing, should the service return empty or an error by design?
14. Does the expected HTTP status match a Basic vs. OAuth2 Login entry point?
15. Are test claims and authorities placed on the right source/mapping?
16. Do you need a real ID Token signature or authorization code test instead of mock login?
17. If running tests in parallel, are fixtures/`SecurityContext` created fresh per subscription?
18. With multiple providers, are `registrationId`, `iss`, `sub`, and tenant/roles consistent?

---

## 31. Final Decision Diagram

```text
Need to test principal / security context in Reactor
                |
                v
Which layer are you testing?
                |
                +-- Reactive service / Mono / Flux
                |       |
                |       +-- Create Authentication / SecurityContext
                |       +-- contextWrite(withAuthentication(...))
                |       +-- StepVerifier:
                |             expectNext / expectError / verifyComplete
                |       +-- Test empty context, concurrency, schedulers
                |
                +-- Spring @PreAuthorize method security
                |       |
                |       +-- @EnableReactiveMethodSecurity
                |       +-- Spring-managed proxy
                |       +-- @WithMockUser + ReactorContextTestExecutionListener
                |       |      or contextWrite(custom Authentication)
                |       +-- Positive + negative StepVerifier tests
                |
                +-- WebFlux HTTP controller
                |       |
                |       +-- WebTestClient + springSecurity()
                |       +-- mockUser()                   [generic user]
                |       +-- mockAuthentication(custom)  [custom auth]
                |       +-- mockOAuth2Login()           [OAuth2User]
                |       +-- mockOidcLogin()             [OidcUser]
                |       +-- mockJwt()                   [Bearer JWT]
                |       +-- Assert status + response + authorization
                |
                +-- Real OIDC authorization protocol
                        |
                        +-- Mock/test OP + token endpoint + JWKS
                        +-- Redirect/state/PKCE/nonce/issuer validation
                        +-- DO NOT rely solely on mockOidcLogin()

When context is missing:
    -> Never drop method-security checks
    -> Never build Authentication from untrusted input
    -> Never use a global ThreadLocal as a workaround
    -> Pick the right subscription/test infrastructure
```

### Core Takeaways

1. **`ReactiveSecurityContextHolder` reads context from the Reactor subscription**, rather than relying on a fixed request `ThreadLocal`.
2. **`contextWrite(withAuthentication(...))` + `StepVerifier`** is the simplest way to unit-test a `Mono`/`Flux` depending on the current user.
3. **`withSecurityContext(Mono.just(...))`** injects a full `SecurityContext`; `clearContext()` helps test empty-context branches.
4. **`@WithMockUser` on reactive method security requires Spring Test + `ReactorContextTestExecutionListener`** and an AOP-proxied bean.
5. **`WebTestClient` with `springSecurity()` and `mutateWith(...)`** is the WebFlux HTTP testing path; do not use `MockMvc` `RequestPostProcessors`.
6. **`mockOidcLogin()` creates an `OidcUser`**, whereas `mockOAuth2Login()` creates an `OAuth2User`, and `mockJwt()` is for Resource Servers.
7. **The reactive helper uses `mockOidcLogin().userInfo(...)`**, unlike Servlet's `oidcLogin().userInfoToken(...)`.
8. **Authorities and claims are not automatically equivalent**: role mapping is separate logic that must be tested on its own.
9. **Reactor Context survives properly composed operators**, while detached subscriptions and non-Reactor async boundaries need explicit handling.
10. **Mock authentication does not prove real OP/JWT validation**, and production data/tokens must never be used in test fixtures.

### Official References

- [Spring Security 6.5 — Reactive Testing OAuth2, OIDC Login, JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — Reactive WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — Reactive Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — ReactorContextTestExecutionListener API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/ReactorContextTestExecutionListener.html)
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/index.html)
- [Project Reactor — Context: Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
