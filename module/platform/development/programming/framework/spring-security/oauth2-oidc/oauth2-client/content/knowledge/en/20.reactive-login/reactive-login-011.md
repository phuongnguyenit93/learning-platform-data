# 20.11. ReactiveSecurityContextHolder, Principals, and Reactor Context Propagation

## 1. Why Does the SecurityContext Problem Change When Moving to Reactive?

In a **Spring Security OAuth 2.0/OIDC Client** application running on Spring WebFlux, a user can log in via OAuth2 Login or OpenID Connect (OIDC) and then call endpoints protected by the application. The application needs to know:

- Which **principal** does this request belong to?
- Did authentication succeed or is the user still **anonymous**?
- Which authorities/roles/scopes are attached to the authentication?
- When the request flows through `Mono`, `Flux`, `flatMap`, `publishOn`, `WebClient`, or an asynchronous boundary, is the authentication info still accessible accurately?
- When no HTTP request exists—such as in `@Scheduled` jobs or message consumers—can a principal from an earlier login be assumed?

In Servlet MVC, many developers are used to:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

`SecurityContextHolder` by default stores the context in a **`ThreadLocal`**. The thread-per-request model makes this access pattern feel natural in synchronous Servlet code.

In **Reactive**, a request does not necessarily execute on a single thread from start to finish. Operators can switch threads, wait on non-blocking I/O, merge multiple publishers, and run callbacks after the inbound method has already returned. Treating a `ThreadLocal` as the "owner" of the request can result in **missing context** or, if handled unsafely, **reading the wrong context from another task**.

Spring Security uses:

```java
org.springframework.security.core.context.ReactiveSecurityContextHolder
```

to bind `SecurityContext` to the **subscription's Reactor Context**, instead of relying on `ThreadLocal` for authentication lookup.

> Core idea of this lesson: **`ReactiveSecurityContextHolder` reads/writes `SecurityContext` via the Reactor Context; the context follows the subscription in the reactive chain, not simply the thread.** How you build publishers, subscribe, and cross non-Reactor API boundaries decides whether the context arrives at the right place.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `SecurityContextHolder` from `ReactiveSecurityContextHolder`.
2. Distinguish `SecurityContext`, `Authentication`, `principal`, and `OAuth2AuthorizedClient`.
3. Understand that Reactor `Context` belongs to the **subscriber/subscription**, unlike `ThreadLocal`, method arguments, and HTTP headers.
4. Use `ReactiveSecurityContextHolder.getContext()`, `withAuthentication(...)`, `withSecurityContext(...)`, and `clearContext()` within their proper scopes.
5. Read the principal cleanly in a WebFlux controller or reactive service.
6. Recognize `OidcUser`, `OAuth2User`, and the claims that need verification.
7. Understand the impact of `flatMap`, `publishOn`, `subscribeOn`, `contextWrite`, `deferContextual`, `subscribe()`, and `block()`.
8. Know how to avoid losing or leaking authentication when calling `WebClient`, running async work, sharing `Mono`s, or caching.
9. Write tests with `StepVerifier`, `WebTestClient`, and Spring Security Test.
10. Diagnose "controller sees the user, but service sees anonymous" or "callback cannot read principal" issues.

Domains, users, and tokens in examples are illustrative. Code snippets focus on the **Spring WebFlux + Spring Security reactive stack** using modern Java (Java 17+ for certain pattern matching).

---

## 2. Mental Model: ThreadLocal vs. Reactor Context

### 2.1. How Synchronous Servlet Works

```text
Alice's HTTP request
    |
    v
Servlet Thread T-17
    |
    +-- SecurityContextHolder / ThreadLocal
    |       Authentication(Alice)
    |
    +-- Controller
    +-- Service
    +-- Repository
    |
    v
HTTP response
```

Within a synchronous call chain on the same thread, code can read `SecurityContextHolder`. Even in Servlet, though, offloading work to another executor or task means `ThreadLocal` does not automatically follow onto arbitrary threads.

### 2.2. How Reactor Works

```text
Alice's HTTP request
    |
    v
Reactor subscription S-A
    |
    +-- Reactor Context
    |       SecurityContext(Authentication(Alice))
    |
    +-- Operator 1   [thread reactor-http-1]
    |
    +-- flatMap(...) [non-blocking I/O]
    |
    +-- publishOn(...) [thread parallel-3]
    |
    +-- Operator 2   [still part of the matching subscription/context]
    |
    v
HTTP response
```

Another request:

```text
Bob's HTTP request
    |
    v
Reactor subscription S-B
    |
    +-- Reactor Context
            SecurityContext(Authentication(Bob))
```

Two subscriptions may share threads in the pool, yet **they must never share each other's `SecurityContext`** merely because they ran on the same thread.

### 2.3. Comparison Table

| Aspect | `ThreadLocal` | Reactor `Context` |
|---|---|---|
| Bound to | Specific thread | Subscriber/subscription of the reactive pipeline |
| Typical access | `ThreadLocal.get()` | `Mono.deferContextual(...)`, `ReactiveSecurityContextHolder.getContext()` |
| Thread switching | Does not automatically transfer values to new threads | Standard Reactor operators preserve the subscriber context |
| Immutability | `ThreadLocal` values can be mutated in place | Reactor `Context` is immutable / copy-on-write |
| When meaningful | While the thread holds the value | When the publisher is **subscribed** with that context |
| Common hazards | Missing or leaking values across threads | Detached subscriptions, misplaced `contextWrite`, caching shared user data |
| Role in WebFlux Security | Not the primary source for reactive chains | Core mechanism used by Spring Security |

**There is no rule saying "switching threads loses the Reactor Context."** A normal `publishOn`/`subscribeOn` is not the same as `new Thread()` or a standalone `CompletableFuture`. What matters is the **publisher/subscription boundary and context bridging**, not merely thread names.

## 3. Spring Security Objects to Distinguish

### 3.1. SecurityContext

Interface:

```java
org.springframework.security.core.context.SecurityContext
```

It holds `Authentication`:

```java
Authentication authentication = securityContext.getAuthentication();
```

A `SecurityContext` may contain no authentication (especially outside authenticated request contexts).

### 3.2. Authentication

Interface:

```java
org.springframework.security.core.Authentication
```

Methods to understand:

| API | Meaning |
|---|---|
| `getPrincipal()` | Authenticated subject; concrete type depends on login mechanism |
| `getName()` | Identifier name provided by authentication |
| `getAuthorities()` | `GrantedAuthority` instances used by the application |
| `isAuthenticated()` | Flag on the authentication object; **not enough** on its own to prove non-anonymous |
| `getCredentials()` | Credentials if used by the mechanism; never log |
| `getDetails()` | Auxiliary metadata, dependent on authentication mechanism |

With OAuth2 Login, a common implementation is:

```java
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
```

With OIDC Login, `OAuth2AuthenticationToken.getPrincipal()` typically holds an `OidcUser`. With non-OIDC OAuth2 Login, the principal can be `OAuth2User`.

### 3.3. Principal

`Principal` represents the identity described by authentication, though its runtime type is not always a bare `java.security.Principal`.

Example:

```java
Authentication authentication = ...;

String name = authentication.getName();
Object principal = authentication.getPrincipal();
```

`principal` can be an `OidcUser`, `OAuth2User`, `UserDetails`, a `String`, or a custom object depending on the authentication mechanism. Never cast straight to `OidcUser` if an endpoint also allows other authentication mechanisms.

### 3.4. OAuth2AuthorizedClient Is Not Authentication

An object of type:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
```

holds a client registration, an access token, and optionally a refresh token for a granted authorization.

Distinction:

| Component | Question Answered |
|---|---|
| `SecurityContext` | Which `Authentication` is attached to the current reactive subscription? |
| `Authentication` | Which principal is authenticated, and with what authorities? |
| `OidcUser` / `OAuth2User` | Which attributes/claims describe the user? |
| `OAuth2AuthorizedClient` | Which OAuth2 client holds which access token to call an API? |
| `ReactiveOAuth2AuthorizedClientManager` | Does the authorized client need to acquire or refresh a token? |

**Having Alice's `SecurityContext` does not mean you have a valid access token for every API.** Likewise, holding an access token from the Client Credentials Grant **does not make a background job become user Alice**.

## 4. What Is Reactor Context?

In Reactor, `Context` is an immutable key-value store attached to a subscriber.

Common APIs:

```java
reactor.util.context.Context
reactor.util.context.ContextView
reactor.core.publisher.Mono
reactor.core.publisher.Flux
```

Simple example without security:

```java
import reactor.core.publisher.Mono;

Mono<String> greeting =
    Mono.deferContextual(contextView -> {
        String language =
            contextView.getOrDefault("language", "en");

        return Mono.just(
            "vi".equals(language) ? "Xin chào" : "Hello"
        );
    });

Mono<String> result =
    greeting.contextWrite(context ->
        context.put("language", "vi")
    );
```

When `result` is subscribed, `deferContextual` reads `"vi"` from the Reactor Context.

### 4.1. Context Is Not a Global Variable

Wrong mental model:

```text
Application singleton Context
    -> Alice logs in
    -> entire application switches to principal Alice
```

Correct:

```text
Alice's Subscription -> Context holds Authentication Alice
Bob's Subscription   -> Context holds Authentication Bob
```

A `Context` is meaningful only when attached to a subscription and operators participating in that exact chain.

### 4.2. Context Is Observed at Subscription Time

A Reactor `Mono` is usually a **cold publisher**: constructing the publisher does not yet run the work.

```java
Mono<String> mono = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName());
```

When `mono` is declared, the user is not necessarily read yet. Reading happens when the publisher is subscribed, inside that subscription's context.

This explains why:

- Constructing a publisher in a controller does not immediately capture the security context.
- Holding onto a publisher and subscribing later under a different context reads that other context (or none).
- Calling `subscribe()` yourself creates a separate subscription that can detach from the inbound request context.

### 4.3. Reactor Context Does Not Automatically Transmit Data Over the Network

Data in Context **does not automatically become an HTTP header**, JWT, SQL parameter, or message attribute.

When using `WebClient`, configure an OAuth2 Client filter or explicit headers to attach the right token. Never treat Reactor Context as an automatic credential-forwarding pipe to every API.

## 5. ReactiveSecurityContextHolder: The Core API

Class:

```java
org.springframework.security.core.context.ReactiveSecurityContextHolder
```

Core methods:

| API | Function |
|---|---|
| `getContext()` | Reads `Mono<SecurityContext>` from the current subscription's Reactor Context |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Builds a Reactor `Context` carrying a publisher supplying `SecurityContext` |
| `withAuthentication(Authentication)` | Builds a Reactor `Context` holding `Authentication` inside a matching `SecurityContext` |
| `clearContext()` | Returns a function removing `SecurityContext` from `Context` per API semantics |

Conceptually:

```java
Mono<SecurityContext> current =
    ReactiveSecurityContextHolder.getContext();
```

Not:

```java
SecurityContext current =
    ReactiveSecurityContextHolder.getContext(); // Wrong type
```

Because the result is a **`Mono`**, not a synchronous object pulled directly from a thread.

### 5.1. Safely Retrieving Authentication

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication -> authentication != null);
}
```

If no context or authentication exists, the publisher completes **without emitting a value**.

Avoid:

```java
Authentication auth = ReactiveSecurityContextHolder
    .getContext()
    .block()
    .getAuthentication();
```

That violates the reactive model by potentially blocking the event-loop, and `block()` creates its own subscription that may lack upstream security context.

### 5.2. Reading the Principal Name

```java
public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication -> authentication != null)
        .map(Authentication::getName);
}
```

On endpoints protected by the security chain, this helps when a business service needs the principal name.

However, on anonymous endpoints, the result may be empty or an anonymous authentication depending on configuration. **Never authorize solely by checking that the name string is non-empty.** Business authorization must rely on `Authentication`/authorities and trusted request authorization policies.

### 5.3. Failing Explicitly When Context Is Missing

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;

public Mono<String> requirePrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication -> authentication != null)
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "Reactive authentication is required"
            )
        ));
}
```

This error can be handled by Spring Security exception translation depending on where in the filter chain the code runs. In practice, protect endpoints upfront in `authorizeExchange()` rather than scattering ad-hoc authentication checks.

## 6. `withAuthentication(...)`: Supplying Context to a Publisher

A simple example illustrating the API in tests or controlled flows:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Authentication alice =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "N/A",
        AuthorityUtils.createAuthorityList("ROLE_USER")
    );

Mono<String> name =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );
```

When subscribed with that context, `getContext()` sees Alice's authentication.

### 6.1. Returns a Reactor Context, Not a Thread-Local Mutation

`withAuthentication(alice)` **is not like**:

```java
SecurityContextHolder.getContext().setAuthentication(alice);
```

It returns a `reactor.util.context.Context` to attach to **a subscription** via `contextWrite(...)`.

Do not write:

```java
ReactiveSecurityContextHolder.withAuthentication(alice);

// Just calls the method and discards the result; not attached to any publisher.
```

Without a configured subscription, nothing causes downstream/upstream operators to read that context.

### 6.2. Never Let the Browser Supply Authentication

Constructing `UsernamePasswordAuthenticationToken.authenticated(...)` in the example simulates **tests or trusted infrastructure**, never a way for public endpoints to authenticate users from request parameters.

Flawed design:

```text
GET /api?user=admin
    -> new authenticated Authentication("admin")
    -> contextWrite(...)
    -> treat as real admin user
```

Authentication must come from an **authentication manager/provider** verifying valid credentials or tokens under Spring Security policies. `contextWrite(...)` does not verify identity itself.

## 7. `withSecurityContext(...)`: Supplying an Entire SecurityContext

Sometimes an app/test already has a `SecurityContext` or wants to pass a context-supplying publisher.

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

SecurityContext securityContext =
    new SecurityContextImpl(aliceAuthentication);

Mono<String> value =
    loadSomething()
        .contextWrite(
            ReactiveSecurityContextHolder.withSecurityContext(
                Mono.just(securityContext)
            )
        );
```

`aliceAuthentication` and `loadSomething()` are placeholders supplied by surrounding illustrative code.

Difference:

- `withAuthentication(authentication)` is convenient when you already have an `Authentication`.
- `withSecurityContext(Mono<? extends SecurityContext>)` fits when you have a publisher producing a `SecurityContext`.

Spring Security uses the lazy publisher form because the security context may be loaded asynchronously from `ServerSecurityContextRepository`.

### 7.1. Do Not Hardcode Internal Keys in Reactor Context

Avoid writing:

```java
context.put("SECURITY_CONTEXT", authentication);
```

expecting `ReactiveSecurityContextHolder.getContext()` to read it automatically.

Spring Security maintains its own internal contract and keys. Always use **`ReactiveSecurityContextHolder`'s public API**, never guess storage keys.

### 7.2. `clearContext()` Scopes Out Inherited Authentication

```java
Mono<String> withoutInheritedContext =
    somePublisher
        .contextWrite(
            ReactiveSecurityContextHolder.clearContext()
        );
```

Use this when you must strip an inherited context within a specific Reactor scope. Never use `clearContext()` as a complete logout or token-revocation solution.

**Logout** may require invalidating the session, updating `ServerSecurityContextRepository`, handling OIDC logout, and managing `OAuth2AuthorizedClient`/tokens per policy. Clearing a single subscription's context **does not log the user out of the application**.

---

## 8. The Most Important Rule of `contextWrite`

Reactor Context flows **from the subscriber upstream** during subscription. Therefore, the **position** of `contextWrite` in the chain determines which operators see the context.

Example:

```java
Mono<String> source =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

Mono<String> result =
    source.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );
```

`source`, being upstream of `contextWrite`, sees Alice's authentication when `result` is subscribed.

### 8.1. Example Placing `contextWrite` in the Middle

```java
Mono<String> pipeline =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        )
        .map(name -> "Hello " + name);
```

`getContext()` upstream sees Alice. The trailing `map` transforms the emitted name; it does not directly read Reactor Context.

If a downstream operator later calls `ReactiveSecurityContextHolder.getContext()` in its own publisher, it reads the subscription's context at that downstream position. Never assume "one `contextWrite` mutates the whole program forever."

### 8.2. Example with Two Branches and Two Contexts

```java
Mono<String> aliceName =
    currentPrincipalName().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );

Mono<String> bobName =
    currentPrincipalName().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)
    );
```

Both publishers can call the same `currentPrincipalName()` method while being subscribed with different contexts. That is the intended behavior: **context belongs to the subscription**, not a singleton method.

### 8.3. `contextWrite` Does Not Mutate the Original Context

Reactor's `Context` has immutable semantics; `contextWrite` creates a **new context view** visible to matching upstream operators. It never changes authentication for requests or users outside that subscription.

## 9. `deferContextual(...)`: Reading Context at the Right Moment

Beyond `ReactiveSecurityContextHolder`, Reactor provides:

```java
Mono.deferContextual(...)
Flux.deferContextual(...)
```

to read context values at **subscription time**.

Example combining a correlation ID with the principal:

```java
import reactor.core.publisher.Mono;

Mono<String> tracedPrincipal =
    Mono.deferContextual(contextView -> {

        String requestId =
            contextView.getOrDefault("request-id", "unknown");

        return ReactiveSecurityContextHolder.getContext()
            .map(securityContext -> {
                Authentication authentication =
                    securityContext.getAuthentication();

                return requestId + ":" + authentication.getName();
            });
    })
    .contextWrite(context ->
        context.put("request-id", "req-001")
    );
```

When subscribed under Alice's security context, the output is:

```text
req-001:alice
```

Never place **access tokens, refresh tokens, or client secrets** into Reactor Context just for logging convenience. Reactor Context is not a secrets vault or an authorized client store.

### 9.1. Read Context When Needed; Do Not Snapshot Too Early

Anti-pattern:

```java
// Never turn SecurityContext in one subscription
// into static/global state shared across other subscriptions.
static Authentication currentUser;
```

Reactive operators can execute after the publisher-creating method returns; global mutable state mixes up principals across concurrent requests.

Instead, read context inside the publisher or pass a verified immutable value—such as a stable user ID—**via method arguments** when business flows need it.

## 10. Principal in a Spring WebFlux Controller

WebFlux can supply the principal from the request context without forcing controllers to query low-level context manually.

Example using:

```java
import java.security.Principal;
import org.springframework.web.server.ServerWebExchange;
```

Controller:

```java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class PrincipalController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            ServerWebExchange exchange) {

        return exchange.getPrincipal()
            .map(principal -> Map.of(
                "name",
                principal.getName()
            ));
    }
}
```

`ServerWebExchange.getPrincipal()` returns a `Mono<Principal>` representing the exchange's principal when present.

To require authentication on an endpoint, protect the path with Spring Security `authorizeExchange()`. On anonymous requests, `getPrincipal()` may be empty or contain an anonymous principal depending on configuration; never assume it is always a real user.

### 10.1. Injecting Authentication or Principal

WebFlux supports resolving several principal/authentication types via method parameters and annotations when configured.

This example avoids coupling to a specific principal class:

```java
@GetMapping("/api/my-name")
public Mono<String> myName(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
```

When authorities are needed, read `Authentication` via `ReactiveSecurityContextHolder` or an appropriate resolver, because `java.security.Principal` exposes only `getName()`.

### 10.2. Never Return the Entire Authentication Directly from an API

Avoid:

```java
@GetMapping("/api/debug-auth")
public Mono<Authentication> debugAuth() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
```

An `Authentication` can contain `details`, `credentials`, or nested principal attributes not meant for the frontend. Return only business-approved fields such as a stable user ID or display name.

---

## 11. Principal After OAuth2 and OIDC Login

With OAuth2 Login, the authentication is typically:

```java
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
```

Principal:

```java
org.springframework.security.oauth2.core.user.OAuth2User
```

With OIDC Login, the principal is typically:

```java
org.springframework.security.oauth2.core.oidc.user.OidcUser
```

`OidcUser` holds the ID Token verified by the OIDC authentication flow, along with relevant claims.

### 11.1. Example Inspecting Principal by Type

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;

public String describe(Authentication authentication) {
    if (!(authentication instanceof OAuth2AuthenticationToken oauth2)) {
        return "Other authentication";
    }

    Object principal = oauth2.getPrincipal();

    if (principal instanceof OidcUser oidcUser) {
        String issuer =
            oidcUser.getIdToken().getIssuer().toString();

        String subject =
            oidcUser.getIdToken().getSubject();

        return "OIDC " + issuer + " | " + subject;
    }

    if (principal instanceof OAuth2User oauth2User) {
        return "OAuth2 " + oauth2User.getName();
    }

    return "Unsupported principal type";
}
```

Here:

- `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` tells you which registration was used to log in.
- `OidcUser` provides access to the ID Token and OIDC claims.
- `OAuth2User` from non-OIDC OAuth2 providers may use provider-specific attribute schemas.
- Never cast every `Authentication.getPrincipal()` unconditionally to `OidcUser`.

### 11.2. Distinguishing Name from External Identity

In OIDC, a trustworthy identity normally relies on **`(iss, sub)`**. Never use email as the sole key to merge accounts across multiple issuers.

An email:

- Can change.
- Might not be returned by the provider.
- Might be unverified.
- Can be reassigned.
- Does not carry an issuer namespace.

`Authentication.getName()` may be the subject or a customized mapped name; check your configuration before treating it as a stable storage identity.

### 11.3. Never Derive an Access Token from the Principal

An OIDC principal holds an ID Token and claims for **identity verification**. When calling a Resource Server API, the app needs an **OAuth2 access token** with matching audience/scopes, normally obtained via `OAuth2AuthorizedClient`.

Never pull the ID Token from `OidcUser` and send:

```http
Authorization: Bearer ID_TOKEN_VALUE
```

just because the API accepts JWTs. An ID Token must never be used as an arbitrary API access token.

## 12. Configuring Spring Security Reactive OAuth2 Login

Dependencies example with Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Illustrative `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://id.example.net
```

URLs and credentials are illustrative. For real deployments, use a secret manager or protected environment variables, and verify provider metadata, redirect URIs, TLS, scopes, and PKCE requirements.

### 12.1. SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Meaning:

1. Spring Security protects exchanges per policy.
2. When a user logs in via OAuth2/OIDC, reactive security filters perform authentication.
3. `SecurityContext` is populated in the reactive execution context.
4. Controllers/services read the context via `ReactiveSecurityContextHolder`.

`oauth2Client()` supports OAuth2 Client features when the app needs authorized clients to call APIs; some apps need only `oauth2Login()` depending on architecture.

**Never use Servlet's `HttpSecurity`/`SecurityFilterChain` for a WebFlux security server.** WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`.

## 13. Where Does Spring Security Place Context into Reactor?

In WebFlux, requests flow through Spring Security's **`WebFilter`** chain.

Architecturally:

```text
HTTP Request
    |
    v
WebFilterChainProxy
    |
    +-- Reactive security filters
    |     |
    |     +-- Authentication mechanism (OAuth2 Login / other)
    |     +-- SecurityContext repository
    |     +-- Reactor Context integration
    |     +-- Authorization checks
    |
    v
DispatcherHandler
    |
    v
Controller -> Mono/Flux -> Service
    |
    v
HTTP Response
```

Components such as `ReactorContextWebFilter` bridge `ServerSecurityContextRepository` and the Reactor Context, while authentication filters perform authentication and persist state where appropriate.

### 13.1. Responsibility of ServerSecurityContextRepository

WebFlux provides the abstraction:

```java
org.springframework.security.web.server.context.ServerSecurityContextRepository
```

It reads and saves `SecurityContext` for a `ServerWebExchange`, for example in session-based authentication or another configured mechanism.

Important distinction:

- **Reactor Context**: scopes context **within one subscription**.
- **ServerSecurityContextRepository**: can persist/restore `SecurityContext` **across HTTP requests** per architecture.

A `contextWrite` on a publisher **does not persist authentication to the next HTTP request**.

### 13.2. What About WebSession?

Web application OIDC/OAuth2 Login typically needs session/state/authorization-request management. After successful login, the security context can be saved via the configured `ServerSecurityContextRepository`.

You cannot replace session management with:

```java
someMono.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication)
);
```

That only attaches context to one subscription scope—it does not create a login session, verify `state`/nonce/PKCE, issue cookies, or handle logout.

### 13.3. Stateless Resource Servers Are a Different Problem

A WebFlux API acting as an OAuth2 **Resource Server** can validate a Bearer token on **every request** without a login session.

When a request arrives with a valid Bearer token, Resource Server authentication is created per config and Reactor Context receives the matching authentication for that request.

That differs from an **OAuth2/OIDC Client** application that logs users in and then calls downstream APIs. An application can act as both client and resource server, with distinct security policies for each.

---

## 14. Propagation Through `map`, `flatMap`, and Chained Publishers

Reactor Context follows the subscription along a normal reactive chain.

Example:

```java
public Mono<String> greetFromSecurityContext() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(name -> Mono.just("Hello " + name));
}
```

When executed within an authenticated WebFlux request context, operators in the chain access the valid subscription principal.

### 14.1. Using flatMap to Compose Business Logic

```java
public Mono<AccountSummary> myAccount() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(accountService::findSummaryByPrincipalName);
}
```

`accountService.findSummaryByPrincipalName` is an illustrative method returning `Mono<AccountSummary>`.

Advantage: `Authentication` is read cleanly inside the reactive pipeline, and the stable principal ID is passed explicitly to the business service.

However:

- `getName()` must map to a stable identity per authentication mechanism.
- If tenant isolation is required, the identity must include or derive from a trusted namespace.
- Reading a principal does not authorize viewing all accounts.
- Business services must still check ownership/authorization against current records.

### 14.2. Never Pull Authorization Checks Out of the Reactive Chain

Wrong:

```java
// Anti-pattern: expecting synchronous authentication outside the subscription.
String currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block();
```

Correct:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .flatMap(accountService::findSummaryByPrincipalName);
```

A single clean pipeline avoids spawning separate subscriptions and avoids blocking the event-loop.

## 15. `publishOn` and `subscribeOn`: Switching Threads Does Not Drop Context

Reactor provides operators:

```java
publishOn(Scheduler scheduler)
subscribeOn(Scheduler scheduler)
```

Example:

```java
import reactor.core.scheduler.Schedulers;

Mono<String> name =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .map(value -> value.toUpperCase())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );
```

When all operators belong to the same valid reactive subscription, `publishOn` changes the thread executing downstream steps without **stripping the Reactor Context**.

### 15.1. Do Not Equate Reactor Context with MDC

Even though Reactor Context remains intact, logging frameworks' **MDC** normally relies on `ThreadLocal`. Logs can therefore lose request IDs or principal labels after a scheduler switch unless a context bridge is configured.

Example:

```text
ReactiveSecurityContextHolder.getContext()
    -> still sees Alice

MDC.get("user")
    -> may be null on another thread
```

These two observations **do not contradict each other** because they read from two different storage mechanisms.

### 15.2. Never Use Schedulers.boundedElastic Just to "Preserve SecurityContext"

`boundedElastic()` helps isolate unavoidable blocking tasks in appropriate parts of a reactive app, yet it **is not a security or authentication propagation mechanism**.

In WebFlux, prefer non-blocking drivers and HTTP clients. When using blocking adapters, define clear boundaries and never expect `ThreadLocal`/security context to update magically.

## 16. A Dangerous Boundary: Calling `subscribe()` Yourself

A common anti-pattern:

```java
@GetMapping("/api/start")
public Mono<String> start() {

    someService.doWork()
        .subscribe(); // Creates an independent subscription.

    return Mono.just("started");
}
```

Manual `subscribe()`:

- Creates a **brand-new subscription**.
- Does not automatically inherit the inbound request's Reactor Context in the way you might expect.
- Detaches error handling from the HTTP response.
- Can run after the request/session lifecycle has ended.
- Continues running even if the user disconnects or logs out.
- Makes tracing, testing, backpressure, and cancellation hard to control.

If `doWork()` needs the principal and calls `ReactiveSecurityContextHolder.getContext()`, the detached subscription will likely see no security context.

### 16.1. Keep Work Inside One Chain

Instead of subscribing manually:

```java
@GetMapping("/api/start")
public Mono<String> start() {
    return someService.doWork()
        .thenReturn("completed");
}
```

Here Spring WebFlux manages the subscription serving the HTTP response, and the security context stays available within the request scope.

### 16.2. What If Work Truly Must Run in the Background?

Do not try to keep an inbound request subscription alive indefinitely.

Instead:

1. Authenticate and authorize upfront at the HTTP boundary.
2. Create a job command/record containing a **stable account ID** and minimal required business payload.
3. Enqueue the job on a managed scheduler or queue.
4. When the worker executes, authorize external API calls using **service authorization or properly stored delegated authorization**, rather than assuming "Alice still has a `ReactiveSecurityContext`."
5. Audit per policy without copying raw access/refresh tokens into message payloads.

An HTTP request's `ReactiveSecurityContextHolder` is not an identity store to reuse for background workers.

## 17. Difference Between a Reactive Chain and `CompletableFuture`

Reactor Context is designed for Reactor subscribers. An external call such as:

```java
CompletableFuture.supplyAsync(() -> {
    // Runs on a different executor.
    return callBlockingApi();
});
```

does not automatically carry Reactor Context into the callback running on that executor.

Example:

```java
Mono<String> result = Mono.fromFuture(
    CompletableFuture.supplyAsync(() -> {
        // Do not rely on SecurityContextHolder.getContext()
        // to identify the WebFlux request user here.
        return "done";
    })
);
```

The `Mono.fromFuture` publisher can sit inside a chain, yet **code executing inside the future supplier** runs under a different execution model and cannot automatically read Reactor Context.

### 17.1. Safer Pattern: Read Identity in Reactor, Pass as Argument

```java
public Mono<String> runLegacyOperation() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(stableName ->
            Mono.fromCallable(() ->
                    legacyService.callFor(stableName)
                )
                .subscribeOn(Schedulers.boundedElastic())
        );
}
```

`legacyService.callFor(stableName)` is an illustrative blocking call. `stableName` is extracted from the authenticated chain before crossing into the adapter.

Important:

- `stableName` must be an appropriate, verified identity.
- Business authorization must still be checked.
- Never pass raw access tokens or `Authentication` objects to an uncontrolled executor just "for convenience."
- When legacy libraries need the principal, prefer passing a stable ID parameter rather than fighting `ThreadLocal`.

### 17.2. What If You Must Bridge ThreadLocal?

Modern Reactor/Micrometer releases offer **context-propagation** integrations that can transfer registered `ThreadLocal` values across specific boundaries.

However, this is **not an automatic guarantee for every executor, callback, HTTP client, and `SecurityContext` object**. You must:

- Check your Reactor/Micrometer/context-propagation versions.
- Register the proper accessors.
- Understand when `contextCapture`, automatic propagation hooks, or `ContextSnapshot` apply.
- Test each async boundary directly.
- Never use propagation bridges as a substitute for authorization checks.

For security logic, **an explicit trusted identity argument** is usually easier to reason about than trying to make every library read `ThreadLocal`.

---

## 18. Hazards from `cache()`, `share()`, and Hot Publishers

A severe bug unrelated to thread switching is **sharing a publisher holding one principal's data across multiple users**.

### 18.1. Anti-Pattern: Caching Current-User Data in a Singleton Service

```java
@Service
public class BadCurrentUserCache {

    private final Mono<UserProfile> sharedProfile;

    public BadCurrentUserCache(ProfileService profiles) {
        this.sharedProfile = profiles.currentUserProfile()
            .cache();
    }

    public Mono<UserProfile> getProfile() {
        return sharedProfile;
    }
}
```

If `currentUserProfile()` reads the principal from Reactor Context, the **first subscription** resolves Alice's profile and `.cache()` retains that result for all subsequent subscribers—including Bob.

Do not assume Reactor Context isolation per subscriber protects a publisher that **already cached the first user's data** in a global field.

### 18.2. Better Approach

Return a fresh publisher per request:

```java
@Service
public class CurrentUserProfileService {

    private final ProfileService profiles;

    public CurrentUserProfileService(ProfileService profiles) {
        this.profiles = profiles;
    }

    public Mono<UserProfile> getProfile() {
        return profiles.currentUserProfile();
    }
}
```

If business caching is required, key the cache explicitly on **stable user/tenant identity and permissions**, with proper TTL and invalidation.

### 18.3. Is `Mono.cache()` Inside a Single Request Always Wrong?

No. When a publisher is created **exclusively for one authenticated request** and never escapes into singleton/global state, request-scoped sharing/caching can legitimately avoid duplicate I/O.

The danger lies in **sharing scope** and whether a publisher or cached result from Alice can ever be subscribed by Bob.

## 19. Principal and Reactor Context in WebClient

A WebFlux OAuth2 Client commonly uses:

```java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
```

It integrates OAuth2 authorized client resolution with `WebClient` when configured alongside an appropriate reactive manager or repository.

Diagram:

```text
Inbound WebFlux request
    |
    +-- Reactor Context: Authentication(Alice)
    |
    v
Controller / Service
    |
    v
WebClient + OAuth2 ExchangeFilterFunction
    |
    +-- Pick matching OAuth2AuthorizedClient
    +-- Use or refresh access token when permitted
    +-- Attach Authorization: Bearer access_token
    |
    v
Downstream Resource Server
```

### 19.1. SecurityContext Does Not Automatically Become a Bearer Header

Wrong assumption:

```text
ReactiveSecurityContextHolder has Alice
    -> every WebClient call automatically gets Alice's Bearer token
```

That does not happen automatically.

You must:

- Configure OAuth2 Client support on `WebClient`.
- Select the right client registration or authorized client.
- Ensure the reactive manager/repository can look up or authorize the token.
- Ensure the outbound API is permitted to receive that token with valid scopes and audience.

### 19.2. Example Configuring Reactive WebClient

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamWebClientConfiguration {

    @Bean("partnerWebClient")
    WebClient partnerWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager
            );

        return WebClient.builder()
            .baseUrl("https://api.partner.example")
            .filter(oauth2)
            .build();
    }
}
```

This shows **WebFlux reactive** wiring; `manager` must be a reactive manager compatible with your app's OAuth2 Login/Client flow and authorized client storage.

### 19.3. Selecting a Registration per Request

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

public Mono<String> readPartnerData(WebClient partnerWebClient) {
    return partnerWebClient.get()
        .uri("/v1/me")
        .attributes(clientRegistrationId("corporate"))
        .retrieve()
        .bodyToMono(String.class);
}
```

Even though the call specifies `clientRegistrationId("corporate")`, the resolved token still depends on the **principal and registration** resolved by the manager. Never assume one registration holds only a single token shared across all users.

### 19.4. Passing a Specific Authorized Client Object

When you already have the right user's authorized client:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

Mono<String> response = partnerWebClient.get()
    .uri("/v1/me")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
```

`authorizedClient` is an `OAuth2AuthorizedClient` retrieved from a trusted source matching the right principal and tenant.

This is a **`WebClient` request attribute**, not data propagated automatically through Reactor Context. Both mechanisms participate in the pipeline, yet they are distinct.

### 19.5. Never Enable a Default Token Unconditionally

Configuring a default OAuth2 authorized client for every `WebClient` request risks attaching a user's token to **hosts not authorized to receive it** if the `WebClient` is shared.

Prefer explicit per-request selection or dedicated `WebClient` instances per Resource Server; restrict absolute URIs and redirects to prevent SSRF and token leaks.

## 20. Why Should Alice's Token Not Be Sent to Service B?

An `OidcUser` may be validly authenticated, yet a token issued for API A may be invalid or forbidden at API B.

Example:

```text
Alice authenticated via corporate OIDC

Authorized client corporate:
    access token audience = inventory-api
    scope = inventory.read

Outgoing call:
    GET https://billing.example/v1/invoices
```

Never forward an inventory access token to billing just because Reactor Context holds Alice's `Authentication`.

Verify:

- Client registration and issuer.
- Token audience/resource binding.
- Scopes granted by the AS.
- Whether the Resource Server API is authorized to receive the token.
- Authorization policies at both the API and business layers.
- Whether token exchange or a separate authorization flow is needed.

**Reactive Context propagation carries authentication context inside the application; it does not expand an OAuth2 token's validity scope.**

## 21. Context Propagation Across Multi-Branch Logic

A service may call multiple publishers:

```java
public Mono<Dashboard> dashboard() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(name -> Mono.zip(
            profileService.findByStableName(name),
            projectService.findVisibleProjects(name)
        ))
        .map(tuple -> new Dashboard(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`Dashboard`, `profileService`, and `projectService` are illustrative types and services.

Benefits of this pattern:

1. Principal is read inside the reactive chain.
2. Stable ID is passed explicitly to both services.
3. `Mono.zip` coordinates non-blocking I/O.
4. No global mutable current-user field exists.
5. Business services remain responsible for authorizing data accessed by that ID.

### 21.1. Does `flatMap` Guarantee Context Never Leaks Across Users?

Normal Reactor subscriptions isolate context per subscription. Still, if a service stashes `Authentication` in singleton mutable fields or globally caches one user's result, data leakage can still happen.

Context propagation **cannot fix bugs caused by shared mutable state**.

### 21.2. Inside a `Flux`, Each Item Is Not a New Security Principal

A `Flux<Order>` created inside Alice's request processes items under the **same subscription authorization context**. If a stream processes events belonging to multiple users/tenants, never assume a shared Reactor Context supplies the right principal for each item.

For multi-tenant streams, enforce:

- Explicit tenant/user identity on each event/record.
- Independent event-source verification and authorization.
- Never relying on one HTTP user context for long-lived multi-tenant event processing.
- Per-resource authorization checks where required.

## 22. When Context Vanishes: Five Common Causes

### 22.1. Calling `subscribe()` Mid-Service

```java
void sendAudit() {
    auditMono.subscribe();
}
```

This creates a new subscription that may lack the caller's context. Return `Mono<Void>` instead and compose it into the managed chain.

### 22.2. Calling `block()` at the Wrong Boundary

```java
String name =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block();
```

A separate blocking subscription is not guaranteed to carry the WebFlux request's context and may be rejected by Reactor on a non-blocking event-loop thread.

### 22.3. Running Tasks via a Standalone Executor

```java
executor.submit(() -> {
    // SecurityContextHolder.getContext() may not hold the context
    // of the WebFlux request from which the task was submitted.
});
```

Pass the verified stable identity as an argument or use a tested propagation bridge rather than blindly reading a global `ThreadLocal`.

### 22.4. Placing `contextWrite` in the Wrong Scope

If you attach context only to one small branch, publishers in another branch will not see it. Know which operators sit upstream of `contextWrite` and which subscription is executing.

### 22.5. Calling a Hot/Shared Publisher Created Under Another User

A globally cached publisher can return Alice's result to Bob regardless of Bob's subscription context. Fix the caching scope rather than just adding `contextWrite`.

## 23. Why Is `SecurityContextHolder.getContext()` Dangerous in WebFlux?

A developer accustomed to Spring MVC might write:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

inside a WebFlux handler.

That is not how Reactor subscribers are designed to read authentication.

### 23.1. Symptoms

- `auth == null` even on an authenticated HTTP request.
- Passes in a single-threaded test yet fails under concurrent production traffic.
- Switching schedulers drops the user.
- Logs show a username belonging to a different request.
- Callbacks from external libraries lack authentication.

### 23.2. How to Fix

Move `Authentication` lookup into the reactive chain:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication ->
        service.handleAuthenticatedUser(authentication)
    );
```

Or read the principal at the controller boundary with `ServerWebExchange.getPrincipal()`/`@AuthenticationPrincipal` and pass a **trusted identity** down to the service.

Never copy `Authentication` into `SecurityContextHolder` inside every Reactor operator to emulate Servlet. When integrating legacy libraries tied to `ThreadLocal`, use a configured and tested context-propagation mechanism, or pass parameters explicitly.

---

## 24. Unit Testing ReactiveSecurityContextHolder with StepVerifier

This is a very effective unit test style—requiring neither an HTTP server nor an Authorization Server.

### 24.1. Testing When Authentication Exists in Context

JUnit 5 + Reactor Test example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextExampleTest {

    @Test
    void canReadAuthenticationFromReactorContext() {
        Authentication alice =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "N/A",
                AuthorityUtils.createAuthorityList("ROLE_USER")
            );

        Mono<String> principalName =
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(alice)
                );

        StepVerifier.create(principalName)
            .expectNext("alice")
            .verifyComplete();
    }
}
```

This confirms that when a subscription carries authentication, `ReactiveSecurityContextHolder.getContext()` reads the exact principal.

**Never test by calling `SecurityContextHolder.setContext(...)` and expecting the reactive holder to read from `ThreadLocal`.** The two APIs target different mechanisms.

### 24.2. Testing When Context Is Missing

```java
@Test
void missingContextProducesNoUser() {
    Mono<String> principalName =
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);

    StepVerifier.create(principalName)
        .verifyComplete();
}
```

This shows the publisher completes empty when no Reactor `SecurityContext` is provided.

If a business method requires authentication, express that explicitly with `.switchIfEmpty(Mono.error(...))` instead of calling `.block()` and hitting a `NullPointerException`.

### 24.3. Testing Isolation Between Alice and Bob

```java
@Test
void separateSubscriptionsHaveSeparatePrincipals() {
    Mono<String> source =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());

    Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

    Authentication bob =
        UsernamePasswordAuthenticationToken.authenticated(
            "bob", "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

    StepVerifier.create(
        source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        )
    )
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(
        source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(bob)
        )
    )
        .expectNext("bob")
        .verifyComplete();
}
```

This proves the exact same source publisher logic can execute under two distinct contexts cleanly.

### 24.4. Testing Scheduler Switches

```java
@Test
void reactorContextSurvivesPublishOn() {
    Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

    Mono<String> pipeline =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .publishOn(reactor.core.scheduler.Schedulers.parallel())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)
            );

    StepVerifier.create(pipeline)
        .expectNext("alice")
        .verifyComplete();
}
```

This tests **normal Reactor propagation** across `publishOn`, not `ThreadLocal` MDC.

## 25. Testing Endpoints with WebTestClient

Spring Security Test supports mocking reactive authentication and OAuth2 Login.

A WebFlux test can use:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
```

Conceptual example with an application-bound `WebTestClient`:

```java
webTestClient
    .mutateWith(mockOidcLogin())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
```

Key points:

- `mockOidcLogin()` mocks an authenticated OIDC principal for testing.
- It **does not** run browser redirects, code exchange, or real ID Token verification against an AS.
- If the endpoint needs an `OAuth2AuthorizedClient` or calls a downstream API, mock the authorization/repository/HTTP server appropriately.
- If the endpoint reads Reactor Context, ensure the test executes through the Spring Security `WebFilterChain` or supplies the context explicitly.

### 25.1. mockOAuth2Login vs. mockOidcLogin

Spring Security Test offers separate helpers for OAuth2 Login and OIDC Login.

- Non-OIDC OAuth2 Login: principal is typically `OAuth2User`.
- OIDC Login: principal is typically `OidcUser`, including illustrative ID Token claims.

If your code casts every principal to `OidcUser`, a `mockOAuth2Login()` test can expose that bug and help enforce the right contract.

### 25.2. Test Security Context Propagation and Authorization Separately

An endpoint returning the principal name in a test does not prove:

- The user has permission to read business resources.
- `WebClient` sends an access token with the right audience and scopes.
- Refresh token rotation is free of race conditions.
- Context propagates across external executors.
- User identities stay isolated across multi-tenant subscriptions.

Test each boundary against its real functional requirements.

---

## 26. Observability and Logging: Never Log the Entire SecurityContext

During debugging, a developer might try:

```java
log.info("securityContext={}", securityContext);
```

Never do this in production. An `Authentication`/principal can contain:

- Emails, profile attributes, and identifiers.
- Credentials or `details`.
- ID Token claims.
- Authentication metadata.
- Data that must stay out of logs.

Log only minimal permitted fields, for example:

```text
event=authorized_api_call
requestId=req-001
registrationId=corporate
principalRef=<pseudonymized>
result=success
```

Never log:

```text
access_token
refresh_token
id_token
client_secret
Authorization header
full Authentication object
full OidcUser attributes
```

### 26.1. Reactor Context and MDC

For per-request logging, you can keep a request ID in Reactor Context and configure a bridge to MDC matching your Reactor/Micrometer versions.

Notes:

- MDC is not Reactor Context.
- `ThreadLocal` values do not automatically follow subscribers.
- Missing or misconfigured logging bridges can drop or mix labels across requests.
- Never use MDC as a source for business authorization decisions.
- Never put raw principals or emails into high-cardinality metric labels.

### 26.2. Tracing Does Not Prove Authorization

A span carrying `user.id` does not mean the user is authorized to view an order. Enforce authorization at business and resource boundaries, never from tracing tags.

## 27. Multi-Tenancy and Reactor Context

In multi-tenant applications, the same `sub` value can mean different people across issuers.

Example:

```text
Issuer A:
    iss = https://id.tenant-a.example
    sub = 123

Issuer B:
    iss = https://id.tenant-b.example
    sub = 123
```

If an app uses `sub` alone as a cache key or account ID, two distinct subjects can collide.

### 27.1. Reliable Stable Key

In OIDC:

```text
(iss, sub)
```

anchors the external identity, or maps that pair to a governed stable local account ID.

If the app places a custom tenant ID in Reactor Context:

```java
.contextWrite(context -> context.put("tenant-id", tenantId))
```

`tenantId` must be verified from a trusted source and matched against the principal's permissions. Never let an HTTP query parameter set `tenant-id` and treat it as authorization proof.

### 27.2. Context Does Not Replace Ownership Checks

Even when `ReactiveSecurityContextHolder` returns Alice, code must verify whether the requested resource belongs to Alice's tenant or permitted scope.

```text
Authentication(Alice)
    |
    +-- Authenticated
    |
    +-- Does not necessarily have permission to view Bob's invoice
```

Never let a bare `authentication.isAuthenticated()` check grant access to all records.

## 28. Scheduled Jobs Have No WebFlux Request Principal

A scheduled job:

```java
@Scheduled(fixedDelay = 60000)
public void synchronize() {
    // No default reason for an HTTP user principal to exist.
}
```

does not execute inside an authenticated inbound WebFlux request subscription. Therefore, do not write:

```java
ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
```

assuming a user is always present.

### 28.1. If the Job Calls APIs Using Application Credentials

Use the OAuth2 Client Credentials Grant and an appropriate reactive authorized client manager, such as:

```java
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

with:

```java
ReactiveOAuth2AuthorizedClientService
```

and a stable principal name acting as the **storage key for the service's authorized client**. That name does not turn the access token into an End-User token.

### 28.2. If the Job Acts on Behalf of a User

The job requires:

- Prior authorization validly granted per policy.
- A stable external/local identity.
- An authorized client stored for the right user/tenant.
- Refresh token handling if permitted by the AS.
- Cleanup/revocation rules when the user disconnects.
- Concurrency control when multiple workers refresh simultaneously.
- A re-authorization flow when the refresh token is no longer valid.

Never copy an old request's `ReactiveSecurityContextHolder` into a job and treat it as proof that Alice is still online and authorized everything.

## 29. Common Pitfalls and How to Diagnose Them

| Symptom | Common Cause | How to Address |
|---|---|---|
| Controller sees principal, reactive service sees empty | Service creates a new subscription or reads wrong scope | Keep inside one reactive chain; avoid `.subscribe()` |
| `SecurityContextHolder.getContext()` returns null/anonymous | Using `ThreadLocal` API in WebFlux | Read via `ReactiveSecurityContextHolder` |
| After `publishOn`, MDC logs lose username | MDC uses `ThreadLocal` | Configure context-propagation/logging bridge; do not blame `SecurityContext` |
| After `publishOn`, code reading Reactor Context still works | Normal Reactor propagation working as designed | Do not assume thread switching is automatically a bug |
| `.block()` fails to read current user | Separate subscription / blocks event-loop | Compose with `flatMap`, never block |
| `CompletableFuture` lacks principal | Executor does not automatically inherit Reactor Context | Pass stable identity argument or use a tested bridge |
| User A sees User B's data | Shared mutable state or globally cached publisher | Cache keyed by authenticated identity/tenant; never cache a global current-user `Mono` |
| Anonymous treated as authenticated | Checked only `isAuthenticated()` | Enforce security authorization policy and anonymous trust rules |
| OIDC user cast fails | Different `Authentication` or principal is not `OidcUser` | Check runtime types and support matching login flows |
| ID Token used to call API | Confused identity token with access token | Use authorized client's access token |
| `WebClient` lacks Bearer header | Missing OAuth2 filter or authorized client selection | Configure reactive `WebClient` OAuth2 integration |
| `WebClient` sends token to wrong host | Overbroad default token or unrestricted URLs | Select token per request; restrict hosts/redirects |
| API returns 403 even with Alice in context | Authentication does not equal authorization | Check scopes, roles, and business ownership |
| Job lacks security context | Job is outside any inbound request subscription | Use service identity or delegated authorization |
| Unit test passes only with `ThreadLocal` | Test does not exercise Reactor Context | Use `StepVerifier` with `contextWrite` |
| Next HTTP request loses login | `SecurityContext` not persisted or session broken | Check `ServerSecurityContextRepository`, session, cookies, and login |
| `contextWrite` invisible to operator | Misplaced operator/subscription scope | Check operator ordering and upstream Context flow |
| Test uses `mockOidcLogin` without calling AS | It is a mock authentication | Write separate OAuth2/OIDC integration tests |
| Token refresh fails under concurrent requests | Concurrent refresh token rotation | Synchronize by authorized client, not just propagation |

### 29.1. Workflow for Isolating Context Bugs

If code sees anonymous despite an authenticated request:

1. Verify the endpoint uses a Spring WebFlux `SecurityWebFilterChain`.
2. Verify the request actually authenticated; check `authorizeExchange` policy.
3. Check whether the controller sees the principal via `ServerWebExchange.getPrincipal()`.
4. Check whether reactive services read `ReactiveSecurityContextHolder.getContext()` instead of `ThreadLocal`.
5. Search for manual `.subscribe()` or `.block()` calls in business code.
6. Search for `CompletableFuture`, `new Thread`, raw `ExecutorService`, or non-Reactor callbacks.
7. Verify `contextWrite` sits in the right subscription scope.
8. Check for `cache()`, `share()`, or global mutable state shared across users.
9. If involving `WebClient`, check authorized client selection/filter rather than only security context.
10. Re-test with `StepVerifier`/`WebTestClient` under explicit authentication.

Use only non-sensitive metadata during every step; you never need to log tokens to verify whether the right principal is present.

## 30. Practice: Service Reading the Current Principal Properly

Suppose the application needs an `/api/my-projects` endpoint returning projects visible to the current user.

### 30.1. Illustrative DTO

```java
public record ProjectDto(
    String projectId,
    String displayName
) {}
```

### 30.2. Service Reading SecurityContext in the Chain

```java
import java.util.List;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MyProjectService {

    private final ProjectRepository repository;

    public MyProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    public Mono<List<ProjectDto>> myProjects() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(authentication -> authentication != null)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required"
                )
            ))
            .flatMap(authentication ->
                repository.findVisibleFor(
                    authentication.getName(),
                    authentication.getAuthorities()
                )
            );
    }
}
```

`ProjectRepository.findVisibleFor(...)` is an illustrative method requiring a real implementation enforcing **policy-compliant tenant/resource authorization**.

Strengths:

- No static/global current-user state.
- Non-blocking.
- No detached subscriptions.
- Identity and authorities are read within the request's context.
- Repository receives the data needed to enforce access policy.

### 30.3. Reactive Controller

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MyProjectsController {

    private final MyProjectService service;

    public MyProjectsController(MyProjectService service) {
        this.service = service;
    }

    @GetMapping("/api/my-projects")
    public Mono<List<ProjectDto>> myProjects() {
        return service.myProjects();
    }
}
```

The controller **returns the publisher** for Spring WebFlux to manage. Never call `subscribe()` or read `SecurityContextHolder` synchronously in the controller.

### 30.4. Security Chain Protecting the Endpoint

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/", "/public/**").permitAll()
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

This snippet is part of a `ServerHttpSecurity` configuration. Policies may grow richer when checking scopes/roles, yet **filter-chain protection** and ownership checks in services/repositories complement each other.

---

## 31. Distinguishing SecurityContext Propagation from Persistence

A frequent question: "I called `withAuthentication()`, so why is the next HTTP request still anonymous?"

Because:

```text
Reactor Context:
    Carries SecurityContext within the current subscription.

ServerSecurityContextRepository:
    Can persist SecurityContext for subsequent requests.
```

Calling:

```java
publisher.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication)
);
```

only attaches context to that publisher. It does **not** mean:

```text
Spring Security saved a login session
Browser received a session cookie
Refresh token was stored
Authorization Server maintained SSO
```

For real user logins, use the OAuth2/OIDC authentication flow and appropriate security infrastructure.

## 32. Applied Scenarios

### Scenario A — Controller Sees User, Service Does Not

`ServerWebExchange.getPrincipal()` sees Alice, yet an inner service calls `SecurityContextHolder.getContext()` and receives null.

**Cause:** the service used Servlet's `ThreadLocal` API inside WebFlux.

**Fix:** read `ReactiveSecurityContextHolder` in the reactive chain or pass a stable user ID from the controller.

### Scenario B — After `publishOn`, Principal Is Still Alice

The publisher switches to `Schedulers.parallel()`, yet `ReactiveSecurityContextHolder.getContext()` still sees Alice.

**Explanation:** Reactor Context travels with the subscription; switching threads via standard operators preserves it.

### Scenario C — `CompletableFuture` Has No User

Code uses `CompletableFuture.supplyAsync()` and calls `SecurityContextHolder` inside the future.

**Cause:** executor tasks do not automatically receive Reactor Context.

**Fix:** resolve the trusted ID in the reactive chain and pass it into the future/legacy service, or use a verified propagation bridge.

### Scenario D — `subscribe()` Runs Fire-and-Forget

A controller returns `Mono.just("OK")` after manually subscribing to a workflow needing the principal.

**Cause:** the workflow runs in a detached subscription outside the HTTP response lifecycle.

**Fix:** compose the publisher into the response or dispatch a background job with its own authentication/authorization model.

### Scenario E — Bob Sees Alice's Data

A singleton service stores `Mono<UserProfile>.cache()` built for the current user.

**Cause:** a shared publisher cached the first subscriber's data.

**Fix:** build publishers per request or cache keyed by stable identity/tenant with authorization checks.

### Scenario F — OIDC Principal Exists Yet API Returns 403

Alice has a valid `OidcUser` and `SecurityContext`, yet `WebClient` calls an API requiring a different scope.

**Cause:** an authenticated user does not mean the access token holds every scope.

**Fix:** pick the authorized client meant for that API and verify scopes, audience, and resource policy.

### Scenario G — Using `contextWrite` to Impersonate Admin

An endpoint reads `?role=admin`, constructs an authenticated `Authentication`, and applies `contextWrite`.

**Cause:** fabricating authentication without verifying credentials.

**Fix:** allow only authentication infrastructure that verifies credentials/tokens to construct trusted `Authentication`.

### Scenario H — Queue Worker Sees No ReactiveSecurityContext

An event consumer executes independently of Alice's HTTP request.

**Explanation:** there is no inbound login subscription.

**Fix:** use service tokens or stored/policy-governed delegated authorization rather than relying on an old session context.

### Scenario I — Multi-Tenant `sub=123` Collides

Two issuers both emit subject `123`.

**Cause:** using `sub` without an issuer namespace.

**Fix:** key identities by `(iss, sub)` or a governed mapped local identity.

### Scenario J — Reactor Context Has User, MDC Log Does Not

On a different scheduler thread, `MDC.get("principal")` returns null.

**Explanation:** MDC is `ThreadLocal`, not Reactor Context.

**Fix:** configure logging bridges per Reactor/Micrometer version; never rely on MDC for authorization.

### Scenario K — User Logs Out Yet Detached Job Keeps Running

A manual subscription keeps calling APIs past the HTTP session lifetime.

**Cause:** the self-managed subscription lives outside the session lifecycle.

**Fix:** manage job cancellation, authorization, and token lifecycles properly; never treat logout as merely clearing Reactor Context.

### Scenario L — Testing Reactivity via `@WithMockUser`

A test sets `SecurityContextHolder` on the test thread and expects `ReactiveSecurityContextHolder.getContext()` to see the user.

**Cause:** the test setup did not attach authentication to Reactor Context or run through WebFlux test integration.

**Fix:** use `StepVerifier` + `contextWrite` for unit tests or `WebTestClient` + Spring Security Test for web tests.

## 33. Self-Check Questions

**Question 1.** What type does `ReactiveSecurityContextHolder.getContext()` return?

**Answer:** `Mono<SecurityContext>`; never a synchronous `SecurityContext`.

**Question 2.** Is Reactor Context bound to a thread or a subscription?

**Answer:** Bound to the subscriber/subscription; operators can switch threads without losing context under normal Reactor mechanics.

**Question 3.** Should `SecurityContextHolder.getContext()` be the primary way to read principals in WebFlux?

**Answer:** No. In reactive chains, use `ReactiveSecurityContextHolder` or principal resolvers at the request boundary.

**Question 4.** Does `withAuthentication(authentication)` persist login to the next HTTP request?

**Answer:** No. It builds a Reactor Context for one subscription; persistence is handled by the security repository/session flow.

**Question 5.** Does `contextWrite` mutate a global context?

**Answer:** No. It creates a new scoped context within the subscription for matching upstream operators.

**Question 6.** Why can manual `.subscribe()` lose the principal?

**Answer:** It creates a new subscription that does not automatically inherit the inbound request's Reactor Context.

**Question 7.** Does `publishOn()` always lose the security context?

**Answer:** No. Reactor Context is normally preserved across that operator within the reactive chain.

**Question 8.** Why is `CompletableFuture.supplyAsync()` different from `publishOn()`?

**Answer:** A future supplier executed on a thread pool is not an operator in the Reactor subscription and does not automatically carry subscriber context.

**Question 9.** How should a reactive service read the principal name?

**Answer:** `ReactiveSecurityContextHolder.getContext().map(SecurityContext::getAuthentication).map(Authentication::getName)` inside the chain, with missing/anonymous checks per policy.

**Question 10.** How do `OidcUser` and `OAuth2AuthorizedClient` differ?

**Answer:** `OidcUser` is the principal/claims from OIDC authentication; an authorized client holds OAuth2 access/refresh tokens for a client registration.

**Question 11.** Why can `Mono.cache()` in a singleton leak data?

**Answer:** It can retain the result computed for Alice's first subscription and return it to Bob.

**Question 12.** If Reactor Context holds Alice, does `WebClient` automatically attach Alice's Bearer token?

**Answer:** No. You must configure OAuth2 `WebClient` integration and select the right authorized client.

**Question 13.** Can one access token call every API once the user is authenticated?

**Answer:** No. It must match the Resource Server's issuer, audience, scopes, and authorization policy.

**Question 14.** Is `clearContext()` equivalent to OIDC logout or revoking refresh tokens?

**Answer:** No. It only alters Reactor Context inside a subscription; logout and token lifecycles are separate processes.

**Question 15.** Does a background job have a user principal in Reactor Context by default?

**Answer:** No. Jobs require a service identity or an explicit delegated authorization model.

**Question 16.** What tool is used to unit-test reactive security context?

**Answer:** `StepVerifier` with `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`.

**Question 17.** What is used to test HTTP endpoints with a simulated OIDC user?

**Answer:** `WebTestClient` with Spring Security Test, such as `mockOidcLogin()`; note that it is a mock, not a real OIDC flow.

**Question 18.** In multi-tenant OIDC, how should identities be namespaced?

**Answer:** By `(iss, sub)` or a securely mapped local ID, never solely by email or un-namespaced `sub`.

**Question 19.** Why should MDC never be used as an authorization source?

**Answer:** MDC is `ThreadLocal`-based logging state that may fail to propagate; authorization must rely on trusted `SecurityContext`/`Authentication` and policy.

**Question 20.** When a reactive service cannot read context, which boundaries should you check?

**Answer:** Check the chain, manual subscriptions, `block`, external futures/executors, `contextWrite` placement, hot/cached publishers, and web filter security configuration.

## 34. Key Takeaways Summary

| Component | Meaning |
|---|---|
| **`ReactiveSecurityContextHolder`** | API to access `SecurityContext` via Reactor Context. |
| **`getContext()`** | Returns `Mono<SecurityContext>` for the current subscription. |
| **`withAuthentication(Authentication)`** | Builds a Reactor Context holding trusted `Authentication` for a subscription scope. |
| **`withSecurityContext(Mono<SecurityContext>)`** | Attaches a publisher providing `SecurityContext`. |
| **`clearContext()`** | Removes security context within a Reactor Context scope. |
| **Reactor `Context`** | Immutable per-subscriber data, not a global variable. |
| **`contextWrite(...)`** | Adds/overrides context seen by upstream operators at subscribe time. |
| **`deferContextual(...)`** | Reads context at subscription time. |
| **`publishOn`/`subscribeOn`** | Switches execution scheduling; does not strip Reactor Context by default. |
| **Manual `subscribe()`** | Creates a separate subscription, easily detaching from the inbound request and losing context. |
| **`block()`** | Blocking/subscription boundary; unsuitable on the WebFlux event-loop. |
| **`ServerWebExchange.getPrincipal()`** | Way to read the principal from the exchange in WebFlux. |
| **`OAuth2AuthenticationToken`** | `Authentication` tied to OAuth2/OIDC Login. |
| **`OidcUser`** | OIDC principal with ID Token/claims; distinguish `iss` and `sub`. |
| **`OAuth2AuthorizedClient`** | Authorization tokens for calling APIs, not `SecurityContext`. |
| **`ServerSecurityContextRepository`** | Persists/restores context across requests per configured mechanism. |
| **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** | Attaches OAuth2 access tokens to `WebClient` for matching clients/registrations. |
| **Global `Mono.cache()`** | Can leak data across users if caching a shared current-user publisher. |
| **`WebTestClient` / `StepVerifier`** | Tools for testing reactive web security and context propagation. |

### Conclusion

With **Spring Security OAuth 2.0/OIDC Client in WebFlux**, user authentication should never be treated as a fixed `ThreadLocal` tied to an HTTP request. Spring Security provides **`ReactiveSecurityContextHolder`** to read and attach `SecurityContext` via the subscription's **Reactor Context**.

To write correct code:

1. Read principals inside the reactive pipeline or at a trusted controller boundary.
2. Keep work inside the chain, avoiding manual `.subscribe()` and `.block()` on the event-loop.
3. Understand that `publishOn`/`subscribeOn` preserve Reactor Context, whereas external executors/futures need explicit identity passing.
4. Never globally cache a publisher or object holding current-user data.
5. Never treat `SecurityContext` as an access token; when calling APIs, choose an `OAuth2AuthorizedClient` matching registration, principal, issuer, audience, and scopes.
6. Test context properly with `StepVerifier`/`WebTestClient` and never use logging `ThreadLocal`s as authorization proof.

**Proper propagation keeps identity accurate within a reactive execution. Proper authorization still requires checking resources, tenants, tokens, and business policies.**

## References

- [Spring Security — Reactive Security Context Holder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext`, `withAuthentication`, `withSecurityContext`, `clearContext`.
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): OAuth2/OIDC Login flow in WebFlux.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `ServerHttpSecurity`.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): authorized clients, managers, and `WebClient` integration.
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient`, `mockOidcLogin`, `mockOAuth2Login`, and security testing.
- [Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor `Context`, `ContextView`, `contextWrite`, `deferContextual`.
- [Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): interaction between Reactor Context and `ThreadLocal` with Micrometer context-propagation.
