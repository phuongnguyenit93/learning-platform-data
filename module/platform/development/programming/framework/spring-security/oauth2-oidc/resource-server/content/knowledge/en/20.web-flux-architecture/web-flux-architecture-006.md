# SecurityContext in Reactive Chains Differs from Servlet ThreadLocal

In a **Spring MVC Servlet** application, developers routinely read the logged-in caller via `SecurityContextHolder.getContext().getAuthentication()`. This works because a synchronous request typically runs on a single thread, and Spring Security stores the security context using a `ThreadLocal` strategy by default. When moving to **Spring WebFlux + Reactor**, that same assumption easily causes bugs: a request may continue execution across multiple threads, multiple publishers may be composed, and actual execution happens **at subscription time**, not necessarily when the controller constructs a `Mono`/`Flux`.

WebFlux uses **Reactor Context** to carry `SecurityContext` through a *reactive chain*. The primary API for accessing it is **`ReactiveSecurityContextHolder`**, not the imperative `SecurityContextHolder`. Reactor Context is bound to **the subscription and operator chain**, not pinned to a single thread. If `contextWrite` is misplaced, `subscribe()` is called manually, work is detached from the chain, or execution leaves Reactor without preserving context, the identity may disappear where permissions need to be checked.

This lesson explains how to distinguish the two models, how Spring Security authenticates Bearer JWT/opaque tokens in WebFlux, how to read and pass principals safely in `Mono`/`Flux`, subscription-boundary pitfalls, `WebSession` management, reactive method security, and techniques for testing context propagation. Examples use **Spring Boot 3, Spring Security 6, Reactor, and Spring WebFlux**. Exact beans and methods may vary by version, so align dependencies with your Spring Boot version.

## 1. Lesson Objectives

After this lesson, you should be able to distinguish:

1. Servlet's default `ThreadLocal` and Reactor's **subscriber context**.
2. `SecurityContextHolder` and **`ReactiveSecurityContextHolder`**.
3. `SecurityFilterChain` / `HttpSecurity` vs. **`SecurityWebFilterChain` / `ServerHttpSecurity`**.
4. `JwtDecoder` vs. **`ReactiveJwtDecoder`**, `OpaqueTokenIntrospector` vs. **`ReactiveOpaqueTokenIntrospector`**.
5. `HttpSession` and **`WebSession`**, as well as the difference between a session and a subscription's context.
6. Why `publishOn`/`subscribeOn` **do not automatically lose Reactor Context**, whereas creating detached subscriptions or leaving the Reactor pipeline can lose it.
7. How to test authorities, principals, publisher composition, and JWT validation without mistaking mock JWTs for genuinely signed JWTs.

**Guiding principle:** WebFlux does not “lack a SecurityContext”; it has a SecurityContext, but **the context-propagation mechanism differs from Servlet**, so familiar imperative code is not the default way to read principals inside a reactive pipeline.

## 2. Servlet: Why Does `ThreadLocal` Feel Natural?

The traditional Servlet flow looks like:

```text
HTTP request
    |
Servlet Filter Chain
    |
Spring Security sets SecurityContext
    |
Request-processing thread
    |
Controller -> Service -> Repository
    |
Spring Security clears SecurityContext
```

In typical configurations, `SecurityContextHolder` stores the context per thread. Therefore:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

can access the principal across multiple processing layers **executing on the same request thread**. Even in Servlet, however, `@Async` or a separate executor can cause the thread-local context to vanish without propagation support.

`ThreadLocal` operates on a model where **the thread is the unit holding context**. It has no inherent awareness that multiple threads are collaborating on one request.

## 3. WebFlux: A Request Is Not Pinned to One Thread

Reactor structures processing as `Mono<T>` (at most one item) and `Flux<T>` (many items) publishers. Once a client subscription is established, operators can run on an event-loop thread or another scheduler depending on how they are composed.

```mermaid
flowchart LR
    A["HTTP WebFlux request"] --> B["WebFilter chain"]
    B --> C["Reactive Authentication"]
    C --> D["Mono/Flux pipeline"]
    D --> E["WebClient / reactive DB"]
    E --> F["Response publisher"]
    G["Subscription Reactor Context"] -.-> C
    G -.-> D
    G -.-> E
```

Example:

```java
return orderRepository.findById(orderId)
    .publishOn(Schedulers.boundedElastic())
    .map(this::toDto);
```

`publishOn` switches downstream processing to another scheduler. If code relies solely on a `ThreadLocal` populated on the initial HTTP thread, it is **not guaranteed** to see the same Authentication. Reactor Context is designed to travel with the subscription across Reactor operators even when threads change.

**“Switching threads” and “switching subscriptions or leaving the pipeline” are two different issues.** That distinction dictates which API to choose for retrieving identity.

## 4. Comparing `ThreadLocal` and Reactor Context

| Characteristic | Typical Servlet `SecurityContextHolder` | Reactor `ReactiveSecurityContextHolder` |
| --- | --- | --- |
| Where context lives | `ThreadLocal` per default strategy. | Reactor `Context` bound to the subscriber/subscription. |
| How it is read | Synchronous call `SecurityContextHolder.getContext()`. | Publisher `ReactiveSecurityContextHolder.getContext()` returning `Mono<SecurityContext>`. |
| Across thread switches | Requires explicit propagation; not automatic. | Reactor operators preserve context across scheduler switches within the same chain. |
| When `Mono` is created but unsubscribed | Concept does not exist in imperative APIs. | Context access or I/O has not necessarily run yet. |
| On manual `.subscribe()` | Not applicable in the same way. | Can create a detached subscription, losing expected context and error lifecycle. |
| Across callbacks/`CompletableFuture` outside Reactor | Relies on dedicated bridge. | Not guaranteed unless bridged/adapted properly. |
| Setting context | `SecurityContextHolder.setContext(...)` in a controlled scope. | `contextWrite(...)` with a context provided by `ReactiveSecurityContextHolder`. |
| Cleanup | Managed by Security filter lifecycle. | Scoped to subscription lifecycle; no global thread-local variable needs clearing per response. |

Reactor Context has **immutable transformation semantics**: calling `contextWrite` produces a new context for its upstream segment rather than mutating a global map shared across requests. Context is technical subscription metadata; do not turn it into a dumping ground for arbitrary entities or session state.

## 5. What Does `ReactiveSecurityContextHolder` Return?

Reactive Spring Security provides:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Core API:

```java
Mono<SecurityContext> context =
    ReactiveSecurityContextHolder.getContext();
```

Unlike:

```java
SecurityContext context =
    SecurityContextHolder.getContext();
```

reactive `getContext()` **returns a `Mono`**, because reading the context occurs when a subscription carries a matching Reactor Context. Therefore, never write:

```java
// Anti-pattern: avoid block in WebFlux requests.
SecurityContext context =
    ReactiveSecurityContextHolder.getContext().block();
```

Instead, use operators:

```java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

On an endpoint without a security context, `getContext()` may be an empty publisher. If anonymous Authentication is enabled, a context may exist while the principal is **not a verified JWT**. When a use case requires a JWT, check the Authentication type and policy—not merely “context non-null”.

## 6. Bearer JWT Flow in Spring Security WebFlux

In a reactive Resource Server, an HTTP request carries:

```http
GET /api/orders/101 HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Conceptual flow:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as Reactive Spring Security WebFilters
    participant M as ReactiveAuthenticationManager
    participant D as ReactiveJwtDecoder
    participant R as Reactor Context
    participant A as WebFlux Handler
    C->>F: Authorization: Bearer access token
    F->>M: Authenticate credential
    M->>D: Verify JWT and validators
    alt Invalid token
        D-->>M: Authentication failure
        M-->>C: 401 / Bearer error per policy
    else Valid token
        D-->>M: Verified Jwt
        M-->>F: Authentication + authorities
        F->>R: SecurityContext for reactive chain
        R->>A: Mono/Flux with subscription principal
        A-->>C: Response or 403 per authorization
    end
```

In WebFlux, Spring Security uses a **`WebFilter` chain** instead of a Servlet Filter chain; components such as `AuthenticationWebFilter` and context-propagation web filters participate in authenticating and restoring context as configured. Controllers never need to construct Authentication manually from HTTP headers.

For a JWT Resource Server, the provider/manager uses `ReactiveJwtDecoder` to verify the token. Once accepted, `Jwt` is attached to a `JwtAuthenticationToken`. For opaque tokens, a reactive introspector provides the principal; scope interpretation depends on the authentication converter.

### An Important Note About “Reactive”

JWT signature verification can require CPU cycles, reading cached keys, or fetching JWKS. A reactive API **does not mean cryptographic computations take zero time**, but network and resource operations must use non-blocking APIs and appropriate schedulers rather than carelessly invoking blocking HTTP clients on the event loop.

## 7. Minimal Dependencies and Configuration for a WebFlux Resource Server

Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

This directs Spring Boot to create a `ReactiveJwtDecoder` from the issuer if the application provides no custom decoder bean. Default issuer/clock validators and additional properties depend on your version; **the `orders-api` audience must be verified if required by the API's security contract**, rather than checking signatures alone and accepting tokens meant for other services.

When using WebFlux, avoid accidentally pulling `spring-boot-starter-web` onto the classpath without understanding how Spring Boot selects the web application type. With both MVC and WebFlux starters present, Spring Boot defaults to Servlet MVC. When migrating to true reactive execution, inspect the application type and dependency tree—not just the presence of `Mono` classes.

## 8. `SecurityWebFilterChain` Instead of `SecurityFilterChain`

A WebFlux JWT API configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
public class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health/liveness")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Meaning:

- **`ServerHttpSecurity`** is the reactive DSL, not Servlet `HttpSecurity`.
- **`SecurityWebFilterChain`** contains the corresponding security WebFilters.
- `authorizeExchange`/`pathMatchers` define HTTP access rules in WebFlux.
- `oauth2ResourceServer().jwt()` accepts Bearer access tokens via reactive JWT authentication.
- `NoOpServerSecurityContextRepository` avoids saving/loading SecurityContext in a session repository; Bearer APIs authenticate credentials per request.
- `anyExchange().denyAll()` locks down undeclared endpoints under this chain.
- `csrf.disable()` is only appropriate when the API is purely Bearer-authenticated in the **Authorization header** and never relies on auto-sent cookies as credentials. Web/BFF cookie routes require dedicated CSRF protection.

This is a **global chain**, not a narrow chain matching only `/api/**`. Applications must add rules for real endpoints such as readiness probes, OpenAPI, or internal admin routes—or split into ordered chains with clear fallback protection.

## 9. Commonly Confused Class Pairs When Moving from MVC to WebFlux

| Purpose | Servlet/MVC | Reactive/WebFlux |
| --- | --- | --- |
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Enable web security | `@EnableWebSecurity` when needed | `@EnableWebFluxSecurity` when needed |
| HTTP rules | `authorizeHttpRequests`, `requestMatchers` | `authorizeExchange`, `pathMatchers` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Retrieve SecurityContext | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Security context persistence | `SecurityContextRepository` | `ServerSecurityContextRepository` |
| Session | `HttpSession` | `WebSession` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP integration tests | `MockMvc` | `WebTestClient` |

This does not mean every MVC-column class is forbidden from existing in a WebFlux app, but **they are not the default APIs for reactive requests**. For example, adding `@EnableMethodSecurity` instead of `@EnableReactiveMethodSecurity` can cause method security not to work as intended on reactive publishers.

## 10. Reading the Principal in a Reactive Controller

On an endpoint protected by Spring Security with JWT, you can retrieve Authentication from Reactor Context:

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CallerController {

    @GetMapping("/api/caller")
    public Mono<String> callerName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required")))
            .map(Authentication::getName);
    }
}
```

This snippet assumes `/api/caller` **is permitted** by `SecurityWebFilterChain`; if the chain from Section 8 still uses `anyExchange().denyAll()` without a matching rule, requests will be blocked before reaching the controller.

To obtain a **specific JWT identity**, distinguish explicitly:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication -> {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !jwtAuth.isAuthenticated()) {
            return Mono.error(new AccessDeniedException(
                "Verified JWT caller required"));
        }
        Jwt jwt = jwtAuth.getToken();
        return Mono.just(jwt.getSubject());
    });
```

The second example requires imports for `JwtAuthenticationToken`, `Jwt`, `AccessDeniedException`, and `Mono`. For JWT-only endpoints with a framework-provided principal, a controller may also use `@AuthenticationPrincipal Jwt jwt` when the argument resolver applies; it simplifies reading claims, though **it does not replace API authorization rules**.

## 11. `ReactiveSecurityContextHolder.getContext()` Is a Publisher

Rather than reading context the instant a method is invoked:

```java
Mono<SecurityContext> securityContext =
    ReactiveSecurityContextHolder.getContext();
```

this `Mono` is **subscribed by the WebFlux runtime** while handling the response. The Reactor Context present at subscription time supplies the data.

An incorrect pattern:

```java
// ANTI-PATTERN: do not do this in a WebFlux request handler.
SecurityContext context =
    ReactiveSecurityContextHolder.getContext().block();
```

`block()` on the event loop can throw an exception or stall the thread, and it can create a subscription detached from the main chain so it misses the expected context. Similarly:

```java
ReactiveSecurityContextHolder.getContext()
    .subscribe(context -> someField = context);
```

is not a valid way to capture the caller for a response: it spawns side work with uncontrolled lifecycle and errors, and `someField` risks shared mutable state across requests.

**Always return and compose publishers**—never subscribe manually or use mutable variables to “pull values out of a Mono”.

## 12. Using `flatMap` to Stay in the Same Subscription

A proper pattern:

```java
@GetMapping("/api/me/orders")
public Flux<OrderDto> myOrders() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMapMany(authentication ->
            orderService.findVisibleOrders(authentication));
}
```

`flatMapMany` chains the service publisher into the **same pipeline**. Inside the service, reactive repository or `WebClient` calls can access the subscription's context if needed.

An anti-pattern:

```java
@GetMapping("/api/me/orders")
public Flux<OrderDto> myOrders() {
    ReactiveSecurityContextHolder.getContext()
        .subscribe(ctx -> auditCaller(ctx));
    return orderService.findAllOrders();
}
```

This snippet **does not await the audit**, may not see the same context, and `findAllOrders()` is not scoped to the caller. A test returning HTTP 200 proves nothing about owner/tenant authorization.

When both auditing and querying are required:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMapMany(auth ->
        auditService.recordAccess(auth)
            .thenMany(orderService.findVisibleOrders(auth)));
```

Whether a failed audit should block proceeding depends on your business/security policy, but it must be **an explicit choice**, not an accidental consequence of fire-and-forget `subscribe()`.

## 13. `contextWrite(...)` Propagates Context per Subscription

Reactor provides:

```java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("traceId", "missing")));

Mono<String> pipeline =
    source.contextWrite(context ->
        context.put("traceId", "trace-123"));
```

In this pipeline, `source` reads `traceId` via Reactor Context. Context is not `ThreadLocal`, and `contextWrite` does not mutate a global map.

**Ordering semantics matter:** `contextWrite` adds or modifies context visible to **operators upstream of that call** within the subscription. Never assume it behaves like “setting a global variable for all lines written below it”.

Example:

```java
Mono<String> first =
    Mono.deferContextual(ctx -> Mono.just(
        ctx.getOrDefault("flag", "none")))
        .contextWrite(ctx -> ctx.put("flag", "A"));

Mono<String> second =
    Mono.deferContextual(ctx -> Mono.just(
        ctx.getOrDefault("flag", "none")));
```

`first` sees `flag = A`; `second` does not automatically see `flag = A` simply because it sits in the same Java method. Each pipeline/subscription has its own context boundary.

In a real Spring Security app, **the framework sets SecurityContext** after authenticating the request. Normal controllers only read it; they should not manipulate context to “mint a user” from request data.

## 14. `ReactiveSecurityContextHolder.withAuthentication(...)`

Spring Security provides a helper to place an Authentication into Reactor Context:

```java
ReactiveSecurityContextHolder.withAuthentication(authentication)
```

Used with `contextWrite`:

```java
Mono<String> task =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(testAuth));
```

`testAuth` is an Authentication **prepared in a trusted unit test**. This is useful for testing reactive services **without running the full HTTP filter chain**.

In production, never do this:

```java
// ANTI-PATTERN: building a principal from unauthenticated input.
Authentication auth = new TestingAuthenticationToken(
    requestUserName, "ignored", "ROLE_ADMIN");

return businessService.run()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

A caller supplying `requestUserName` must not become an authenticated user via a helper method. **The source of Authentication must be trusted**, such as Spring Security WebFlux verifying a Bearer token. `contextWrite` is a propagation mechanism, **not an authentication mechanism**.

## 15. `withSecurityContext(...)` and `clearContext()`

Additional APIs:

```java
ReactiveSecurityContextHolder.withSecurityContext(
    Mono.just(securityContext));
```

and:

```java
ReactiveSecurityContextHolder.clearContext();
```

are used inside `contextWrite(...)` when **trusted code authorized to establish or clear** SecurityContext needs to do so. `withSecurityContext(...)` takes a `Mono<? extends SecurityContext>`, not a bare imperative `SecurityContext`.

In normal controllers, you **do not need to call** these methods: the framework handles them at the web security boundary. They are useful in tests, specialized adapters, or reviewed custom authentication filters.

Clearing Reactor Context inside a publisher does not revoke a JWT or log out clients; just like Servlet `SecurityContextHolder.clearContext()`, it only alters the current execution context and **does not invalidate an issued Bearer token**.

## 16. `publishOn` and `subscribeOn` Do Not Automatically Lose Reactor Context

Example with a scheduler switch:

```java
Mono<String> callerName =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel());
```

If `callerName` is subscribed as part of **the same reactive chain carrying a security context**, the context remains accessible via Reactor's mechanism even when the processing thread changes.

`publishOn(scheduler)` affects the thread of downstream operators. `subscribeOn(scheduler)` affects where subscription/source work is scheduled. **Neither operator copies `SecurityContext` into ThreadLocal by default**, yet Reactor Context propagates properly through the subscription.

An incorrect claim:

> Because the publisher switched to another thread, Reactor SecurityContext must have disappeared.

A more accurate statement:

> As long as execution stays within Reactor operators of the same chain/subscription, Reactor Context propagates with the subscription; when detaching work or crossing into non-Reactor APIs, check propagation explicitly.

Note that custom operators, third-party libraries, or improper interop can complicate context propagation. Test real adapters whenever identity drives authorization.

## 17. How Context Is Lost: Calling `subscribe()` Manually in a Service

Anti-pattern:

```java
public Mono<Void> processOrder(long orderId) {
    updateAuditTrail(orderId).subscribe();
    return orderRepository.process(orderId);
}
```

Calling `.subscribe()` creates an independent subscription running outside the response publisher's lifecycle, easily losing Reactor Context, bypassing HTTP error handling, and potentially executing side effects **after the API has already sent its response**.

Correct composition:

```java
public Mono<Void> processOrder(long orderId) {
    return updateAuditTrail(orderId)
        .then(orderRepository.process(orderId));
}
```

Here both operations stay inside the returned pipeline. If database atomicity or outbox/event guarantees are needed, use reactive transactions and proper side-effect design; chaining `then` alone does not turn two independent systems into a distributed transaction.

**Rule:** In reactive services and controllers, never call `subscribe()` yourself “just to make sure it runs”. The framework subscribes to the response publisher at the appropriate boundary.

## 18. Leaving Reactor via Callbacks, Threads, or `CompletableFuture`

Example:

```java
new Thread(() -> {
    // Do not assume Reactor SecurityContext is present here.
    callExternalSystem();
}).start();
```

This is a fresh execution path that does not automatically inherit Reactor Context. Similarly, callbacks from imperative libraries or external executors **do not necessarily carry** the subscription context.

If you must invoke a blocking API from WebFlux, consider a proper adapter:

```java
Mono<Result> result =
    Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

This avoids blocking the event loop by shifting blocking work onto an appropriate scheduler. However, **never call `SecurityContextHolder.getContext()` inside `legacyClient.fetch()` assuming it holds the current caller**: that would still be ThreadLocal on a worker thread.

A less fragile approach:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(auth ->
        Mono.fromCallable(() ->
                legacyClient.fetchFor(auth.getName()))
            .subscribeOn(Schedulers.boundedElastic()));
```

Pass the minimal **authenticated** identity explicitly into the adapter rather than expecting a blocking library to query Reactor Context itself.

## 19. ThreadLocal Bridging Is Not the Primary Replacement for Reactor Context

The Reactor/Micrometer ecosystem offers **context propagation** capabilities to bridge certain `ThreadLocal`s (like tracing/MDC) with Reactor Context when configured. While helpful for logging and tracing, do not use it as an excuse to read principals via imperative `SecurityContextHolder` everywhere in WebFlux.

Reasons:

- Not every ThreadLocal is registered for propagation.
- Context snapshot scope and timing depend on adapters and configuration.
- Out-of-chain callbacks or custom executors still require explicit propagation.
- Reading stale ThreadLocal values under concurrent requests can cause data corruption or authorization bugs.

**The primary API for reactive security identity remains `ReactiveSecurityContextHolder` or framework-injected handler principals**, not an implicit bridge.

## 20. Reactor Context Is Not Where a Web Login Session Is Stored

In WebFlux, `WebSession` can be used when an application must remember login state across requests. However, Reactor Context is used to **carry SecurityContext within a single request/subscription's reactive chain**; it is not the same concept as a session cookie.

| Component | Role |
| --- | --- |
| **Reactor Context** | Subscription-attached metadata that may hold a SecurityContext publisher. |
| **`SecurityContext`** | Authenticated Authentication and principal. |
| **`WebSession`** | Cross-request web state when the application requires sessions. |
| **`ServerSecurityContextRepository`** | Strategy for loading/saving SecurityContext for reactive requests. |
| **`NoOpServerSecurityContextRepository`** | Uses no repository to store/restore context. |
| **`WebSessionServerSecurityContextRepository`** | Repository that can store/restore SecurityContext using WebSession. |

A WebFlux JWT Resource Server can use `NoOpServerSecurityContextRepository` and verify tokens per request. A WebFlux web login/OIDC Client may need a web session and appropriate repository. **Reactive does not mean stateless**; WebFlux supports both Bearer APIs and web sessions, though the APIs for creating/restoring context differ from Servlet.

### Do Not Look for `SessionCreationPolicy` in the Wrong Place

`SessionCreationPolicy` belongs to the Servlet `HttpSecurity` DSL. For WebFlux, configure sessions and context via **`ServerHttpSecurity` and `ServerSecurityContextRepository`**; do not copy `HttpSecurity.sessionManagement(...SessionCreationPolicy.STATELESS)` into a WebFlux security chain.

## 21. Reading SecurityContext from a Functional WebFlux Handler

WebFlux does not require annotated controllers. In functional endpoints, `ServerRequest.principal()` returns `Mono<Principal>`:

```java
public Mono<ServerResponse> caller(ServerRequest request) {
    return request.principal()
        .cast(Authentication.class)
        .flatMap(auth ->
            ServerResponse.ok()
                .bodyValue(auth.getName()));
}
```

This snippet requires imports for `ServerRequest`, `ServerResponse`, `Authentication`, and `Mono`. It assumes the route is protected and the actual principal is a Spring Security `Authentication`; if multiple authentication mechanisms or public routes exist, check types and handle empty publishers.

Alternatively, read via `ReactiveSecurityContextHolder.getContext()` instead of trying to fetch `SecurityContextHolder.getContext()` from the current thread.

Note that `ServerRequest.principal()` **does not automatically ensure the caller holds the right scopes**. Authorization in `SecurityWebFilterChain`, method security, and domain policies remain mandatory.

## 22. Service Pattern: Extracting Identity and Querying Scoped Data

Suppose only the owner may read an order. Illustrative reactive repository API:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Mono<Order> findByIdAndTenantIdAndOwnerIssuerAndOwnerSubject(
        Long id,
        String tenantId,
        String ownerIssuer,
        String ownerSubject
    );
}
```

A membership service:

```java
public interface TenantMemberships {
    Mono<Boolean> canReadOrders(
        String issuer,
        String subject,
        String tenantId
    );
}
```

Use case:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderQueryService {

    private final TenantMemberships memberships;
    private final OrderRepository orders;

    public OrderQueryService(
            TenantMemberships memberships,
            OrderRepository orders) {
        this.memberships = memberships;
        this.orders = orders;
    }

    public Mono<OrderDto> getVisibleOrder(
            String tenantId,
            Long orderId) {

        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "JWT authentication required")))
            .flatMap(auth -> {
                if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                        || !jwtAuth.isAuthenticated()) {
                    return Mono.error(new AccessDeniedException(
                        "JWT authentication required"));
                }

                boolean canRead = jwtAuth.getAuthorities().stream()
                    .anyMatch(a ->
                        "SCOPE_orders.read".equals(a.getAuthority()));
                if (!canRead) {
                    return Mono.error(new AccessDeniedException(
                        "Missing orders.read"));
                }

                Jwt jwt = jwtAuth.getToken();
                if (jwt.getIssuer() == null
                        || jwt.getSubject() == null) {
                    return Mono.error(new AccessDeniedException(
                        "Invalid caller identity"));
                }

                String issuer = jwt.getIssuer().toString();
                String subject = jwt.getSubject();

                return memberships.canReadOrders(
                        issuer, subject, tenantId)
                    .flatMap(allowed -> {
                        if (!allowed) {
                            return Mono.error(
                                new AccessDeniedException(
                                    "Tenant denied"));
                        }
                        return orders
                            .findByIdAndTenantIdAndOwnerIssuerAndOwnerSubject(
                                orderId, tenantId, issuer, subject)
                            .map(OrderDto::from)
                            .switchIfEmpty(Mono.error(
                                new ResponseStatusException(
                                    HttpStatus.NOT_FOUND)));
                    });
            });
    }
}
```

`Order`, `OrderDto`, and the repository schema are illustrative types to implement; the example assumes `canReadOrders` returns a non-empty `Mono<Boolean>` enforcing membership policy from a trusted source.

Here:

1. The service reads the trusted Authentication from **the current subscription's Reactor Context**.
2. It verifies `JwtAuthenticationToken`, scope, and issuer/subject.
3. It checks tenant membership via a **reactive publisher**.
4. It queries the order constrained by **tenant + owner issuer + owner subject**.
5. It never returns another tenant's or owner's order merely because the token carries `orders.read`.

Replace this owner-only check with explicit ACL/sharing/admin policies if business rules allow exceptions. Never accept a client-sent `tenantId` header as proof of membership.

## 23. Why Does Reading Context at Subscription Time Matter?

A controller may create:

```java
Mono<OrderDto> pending =
    orderQueryService.getVisibleOrder(tenantId, orderId);
```

When `getVisibleOrder` is called, the `flatMap` steps inside **have not necessarily executed yet**. The pipeline typically runs when WebFlux subscribes to produce the HTTP response. At that moment, the Reactor Context holding the request's Authentication must be present in the pipeline.

An incorrect pattern is saving the context into a singleton field:

```java
@Service
public class UnsafeCallerHolder {
    private Authentication lastCaller;

    public Mono<Void> save() {
        return ReactiveSecurityContextHolder.getContext()
            .doOnNext(ctx ->
                lastCaller = ctx.getAuthentication())
            .then();
    }
}
```

Because service beans are shared across requests, `lastCaller` can be overwritten by concurrent requests, causing a **cross-user identity leak**. Use Reactor Context or pass an immutable identity DTO to publishers that need it—**never use mutable singleton state**.

## 24. `Mono.cache()` and Caching Per-User Results

Reactor `Mono.cache()` is useful for memoizing a publisher, but if the same publisher instance is **shared across requests**, it risks caching the first subscriber's result and replaying it to later subscribers without re-checking the principal.

Anti-pattern:

```java
// Do not store a caller-dependent Mono as an application-wide singleton field.
private final Mono<OrderDto> cachedOrder =
    loadOrderForCurrentCaller().cache();
```

Caller Alice subscribes first; the publisher loads Alice's order and caches `OrderDto`. Caller Bob subscribing to that same publisher may receive cached data without re-running authorization lookups, depending on the design.

Distinguish:

- `cache()` **scoped to a single unshared request/publisher** is usually a valid local optimization.
- `cache()` held in a **singleton or shared registry** must account for principal, tenant, and policy scoping.
- Application caches like Redis or Caffeine must also be namespaced by identity and policy whenever data depends on permissions.
- Caching the result of `ReactiveSecurityContextHolder.getContext()` on a shared publisher can **freeze one subscription's Authentication** if poorly designed.

Test every memoization optimization with **two distinct users** and different owner/tenant data.

## 25. Reactive Method Security Uses Reactor Context

To enable method security in WebFlux:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {}
```

A service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<ReportDto> report(String reportId) {
    return reportRepository.findById(reportId)
        .map(ReportDto::from);
}
```

With **reactive method security**, Spring Security retrieves Authentication from Reactor Context via integration with `ReactiveSecurityContextHolder`, rather than requiring controllers to populate `SecurityContextHolder.getContext()` on a thread.

Key points:

- Guarded methods generally need to return `Mono`, `Flux`, or a supported Publisher type so security checks occur within the right reactive context.
- Must invoke through a **Spring-managed bean/proxy**; self-invocation can bypass the method security interceptor just like other Spring AOP scenarios.
- Scope `reports.read` **does not prove permission on every individual report**; tenant/owner/ACL checks are still required.
- A plain unit test calling `new Service(...)` does not trigger `@PreAuthorize`; test through the Spring context for annotations, and test domain policies separately.

If a service supports both HTTP JWTs and machine-initiated work, define an explicit way to supply trusted identity. Never inject a fake admin user into Reactor Context just to bypass an annotation.

## 26. Reactive Transactions Also Depend on Subscription Context

WebFlux is commonly paired with R2DBC or reactive database drivers. In reactive transactions, Spring uses **Reactor Context** to maintain transaction state instead of binding everything to a JDBC ThreadLocal.

Example `@Transactional` on a method returning `Mono`:

```java
@Transactional
public Mono<Void> updateOrder(...) {
    return repository.findById(...)
        .flatMap(order -> repository.save(order))
        .then();
}
```

This is a simplified snippet omitting full authorization; it requires a **`ReactiveTransactionManager`** compatible with a reactive database. Never use `@Transactional` with blocking JDBC/JPA and assume it is a reactive transaction simply because the method returns `Mono`.

Reactor Context can carry both security and transaction metadata under **separate keys**, though a transaction does not automatically wrap external side effects or guarantee owner authorization.

If code calls `subscribe()` in the middle, the detached work may execute outside the main pipeline's transaction and context—a bug for both correctness and security when permission checks and writes must belong to the same use case.

## 27. WebFlux Must Not Perform Reckless Blocking Calls

An anti-pattern:

```java
@GetMapping("/api/reports")
public Mono<ReportDto> reports() {
    ReportDto dto = jdbcRepository.findBigReport();
    return Mono.just(dto);
}
```

This executes blocking JDBC **directly inside the method**, tying up the event-loop thread and slowing down other requests. Even if SecurityContext is retrieved properly, the application can still exhaust its threads.

If migrating to R2DBC/reactive drivers isn't feasible yet, isolate blocking work onto an appropriate scheduler with bounded concurrency:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication ->
        Mono.fromCallable(() ->
                legacyService.reportFor(authentication.getName()))
            .subscribeOn(Schedulers.boundedElastic()));
```

Note that `authentication.getName()` is not automatically a business user ID: when owner/tenant checks are required, use trusted identity mapping and domain policies. `boundedElastic` keeps work off the event loop, but **does not make JDBC non-blocking** and does not eliminate the need for backpressure, connection limits, or timeouts.

## 28. Custom WebFilters Must Access Context at the Right Stage

For custom logging, tracing, or policy filters, a `WebFilter` can observe context in the pipeline:

```java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    return chain.filter(exchange)
        .doOnEach(signal -> {
            // Use Reactor signals/context per the Reactor contract.
            // Do not read a ThreadLocal assuming it is the JWT caller.
        });
}
```

This is a **conceptual sketch**, not a complete custom filter: you must define imports, ordering, error paths, context access, and avoid logging sensitive data. A `WebFilter` ordered too early may execute **before authentication** and therefore see no authenticated Authentication.

When reading the caller after authentication, it is usually simpler to do so in controllers/services via `ReactiveSecurityContextHolder` or in a filter with well-understood ordering. Never write a custom WebFilter that parses JWTs from `Authorization` headers to mint Authentication unless implementing a thoroughly vetted custom authentication mechanism.

## 29. Tracing and MDC Are Not Sources of Identity Authority

A pipeline may carry a trace ID or tenant hint in MDC/Reactor Context for logging:

```text
traceId = 1234
tenantHint = tenant-a
```

However, a gateway- or header-supplied `tenantHint` does not prove the user has rights in `tenant-a`. Tracing context and security context serve different purposes:

- Trace context correlates logs and spans.
- SecurityContext holds the Authentication produced by a trusted authentication mechanism.
- Domain policy verifies tenant/owner permissions from authoritative sources.

Even if an application propagates trace IDs via ThreadLocal/MDC, it must never propagate “isAdmin” or “ownerId” from unverified headers into Authentication.

When logging reactive code, avoid raw access tokens, cookies, client secrets, and full JWT claims. If logging usernames/subjects, weigh privacy and issuer namespacing.

## 30. Testing `ReactiveSecurityContextHolder` with `StepVerifier`

A non-HTTP unit test can verify that context follows the Reactor pipeline even across scheduler switches:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextTest {

    @Test
    void authenticationIsReadAcrossSchedulerSwitch() {
        Authentication alice = new TestingAuthenticationToken(
            "alice", "unused", "SCOPE_orders.read");

        Mono<String> result =
            ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .publishOn(Schedulers.parallel())
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice));

        StepVerifier.create(result)
            .expectNext("alice")
            .verifyComplete();
    }
}
```

This test requires `reactor-test` and compatible Spring Security Test dependencies. `TestingAuthenticationToken` is strictly for tests and does not prove a real access token's signature was verified. What the test proves is that **context travels with the Reactor subscription**, rather than sitting in a ThreadLocal on an event-loop thread.

You can also add a negative test:

```java
Mono<Boolean> missing =
    ReactiveSecurityContextHolder.getContext()
        .hasElement();

StepVerifier.create(missing)
    .expectNext(false)
    .verifyComplete();
```

This assumes the pipeline **has no `contextWrite` supplying a SecurityContext**. It confirms the publisher does not accidentally pick up a principal from a global field or a previous test.

## 31. `WebTestClient`: Testing WebFlux Authorization

Spring Security Test provides `mockJwt()` for WebFlux. Example creating a client bound to the application context and security filters:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();

client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.read")))
    .get()
    .uri("/api/orders/101")
    .exchange()
    .expectStatus().isOk();
```

Static imports in Markdown may wrap across two lines for readability; **in Java source, each `import` must be a valid single-line statement**. Add imports for `WebTestClient`, `ApplicationContext`, and `SimpleGrantedAuthority`, and ensure fixtures/controllers/services for order 101 return 200 for the test caller.

`mockJwt()` provides **mock authentication** and typically bypasses the production `ReactiveJwtDecoder` that verifies real JWT signatures. When `.authorities(...)` is passed directly, the test also skips verifying the real scope converter configuration. It is ideal for testing HTTP/method policies, not as proof of JWT cryptography.

## 32. Test Matrix for Context and Authorization

| Case | Test | What to Prove |
| --- | --- | --- |
| Valid JWT with `orders.read` | WebFlux integration + `mockJwt` or real JWT | Read route proceeds to domain policy. |
| Missing Bearer | `WebTestClient` on protected route | No verified principal; typically 401. |
| Valid JWT missing scope | `WebTestClient` with insufficient authorities | Authorization denies; typically 403. |
| Same token with wrong audience | Real signed JWT, real `ReactiveJwtDecoder` | Authentication rejects. |
| Publisher switching via `publishOn` | `StepVerifier` + `withAuthentication` | Reactor Context remains readable after scheduler switch. |
| Imperative `SecurityContextHolder` access | Unit/integration inside pipeline | Must not rely on ThreadLocal to find caller. |
| `getContext()` without context | `StepVerifier` | Empty publisher / no unexpected identity. |
| Direct service call with `withAuthentication` | `StepVerifier` + mock repo | Service reads principal from subscription context. |
| Wrong tenant, or same tenant different owner | Service + reactive repo fixture | No object leakage. |
| Two-user shared `Mono.cache()` | Two subscriptions with two principals | First user's authorized result is not replayed. |
| Existing `WebSession` without Bearer | HTTP integration test | Bearer-only API does not grant access from web login session. |
| Reactive `@PreAuthorize` | Spring context + reactive method security | Method blocked per authorities in Reactor Context. |
| Detached `subscribe()` | Controlled test / pipeline review | Does not rely on side effects outside main subscription. |

For end-to-end JWT verification, use a test issuer/JWK Set, a JWT signed by a test private key, a real `ReactiveJwtDecoder`, and real HTTP requests. A `mockJwt()` test returning 200 **does not prove signature, issuer, audience, or expiry checks ran**.

## 33. Testing Permissions in Reactive Services, Not Just HTTP Filters

A common oversight:

```text
GET /api/orders/101 -> HTTP security confirms scope is valid
Controller -> repository.findById(orderId)
```

With a valid-scope JWT targeting someone else's order, the API suffers from BOLA/IDOR. WebFlux does not automatically enforce object-level authorization.

Testing the service directly:

```java
Mono<OrderDto> result =
    service.getVisibleOrder("tenant-b", 201L)
        .contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(aliceJwtAuthentication));

StepVerifier.create(result)
    .expectError(AccessDeniedException.class)
    .verify();
```

`aliceJwtAuthentication` in the test must represent Alice's JWT principal with accurate issuer/subject/authorities; repository and membership fixtures confirm Alice has no access in `tenant-b`. This test **needs no HTTP controller** and verifies the service enforces tenant checks inside the reactive chain.

Continue testing owner mismatches within the same tenant, identical `sub` across different issuers, revoked membership while a token is still unexpired, and identity-scoped caching. When `@PreAuthorize` guards a method, test **through the Spring-managed proxy** because calling `new Service(...)` skips AOP; keep direct unit tests for domain policies as well.

## 34. WebSession vs. Per-Request Bearer APIs

In WebFlux, when client authentication must persist across requests (such as OAuth2/OIDC web login), `WebSession` can store the security context via `WebSessionServerSecurityContextRepository`. In pure Bearer APIs, we typically avoid using a session repository for authentication:

```java
.securityContextRepository(
    NoOpServerSecurityContextRepository.getInstance())
```

An API request carrying a Bearer token is authenticated and its context is attached to the chain. A subsequent request **without a Bearer token** must not be permitted simply because the browser carries a `SESSION` cookie from another web login.

**Reactive WebFlux does not mandate being stateless.** Applications using web sessions still use Reactor Context per request. The distinction:

```text
WebSession = state restored across multiple requests
Reactor Context = context carrying Authentication within the current subscriber chain
```

When using multiple `SecurityWebFilterChain` beans, verify matchers, ordering, and fallbacks so APIs never accidentally accept web-route session authentication. For cookie-based logins or BFFs, keep CSRF, cookie security, logout, and session fixation protections aligned with your threat model.

## 35. Anti-Patterns to Remember When Moving from MVC to WebFlux

### 35.1. Using `SecurityContextHolder` Like in MVC

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

In a WebFlux reactive chain, this **is not a reliable way** to read the principal. Use `ReactiveSecurityContextHolder.getContext()` or the appropriate reactive argument resolver.

### 35.2. Calling `.block()` to Retrieve Authentication

```java
Authentication auth =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .block();
```

Can block the event loop or spawn a detached subscription, losing context and breaking the non-blocking model.

### 35.3. Calling `.subscribe()` in Controllers or Services

```java
saveAudit().subscribe();
return updateOrder();
```

Creates detached work whose lifecycle and context are no longer tied to the response. Chain publishers using `flatMap`, `then`, or `concatMap` per semantics.

### 35.4. Treating `publishOn` as a Security Bug by Itself

Reactor Context travels with the subscription; switching schedulers does not inherently lose SecurityContext. The real danger is detaching from the chain, unsafe interop, or uncontrolled bridging.

### 35.5. Holding Authentication in a Singleton Field

`private Authentication currentCaller;` risks mixing callers across requests. Use Reactor Context or explicit immutable identity parameters.

### 35.6. Using Global `Mono.cache()` on Principal-Dependent Data

Publishers shared across requests can replay the first caller's result to subsequent callers. Caches must enforce identity/tenant/policy scoping and proper invalidation.

### 35.7. Setting `withAuthentication` from Unverified HTTP Headers

`contextWrite` does not verify signatures or tokens; only set security context at a trusted authentication boundary or in tests.

### 35.8. Copying `HttpSecurity.sessionManagement` into WebFlux

WebFlux uses `ServerHttpSecurity` and `ServerSecurityContextRepository`. `SessionCreationPolicy` belongs to the Servlet stack.

### 35.9. Calling Blocking JDBC/JPA Directly on the Event Loop

Defeats non-blocking scalability and risks thread starvation. Use reactive drivers or isolate blocking calls in a controlled manner.

### 35.10. Treating Scope as Permission to Read Every Record

A reactive JWT with `SCOPE_orders.read` is insufficient to read orders across all tenants or owners. Enforce scoped queries and domain policies.

## 36. Runbook When WebFlux Reports a Missing SecurityContext

If a reactive service reports a missing principal or unexpected authorization results:

1. **Verify the stack**: Is the app actually running WebFlux, or did `spring-boot-starter-web` switch it to MVC?
2. **Check the chain**: Does `SecurityWebFilterChain` match the route and enable a JWT/opaque Resource Server?
3. **Check the Bearer credential**: Does the request carry a valid `Authorization: Bearer` header? Never log raw tokens.
4. **Check decoder/introspector**: Are issuer, audience, expiry, and JWKS/introspection responses valid?
5. **Check access points**: Is code calling imperative `SecurityContextHolder` or `ThreadLocal`?
6. **Search for `.block()` and `.subscribe()`**: Are detached subscriptions breaking context, error, or transaction lifecycles?
7. **Inspect non-Reactor adapters**: Do executors, `CompletableFuture`s, callbacks, or legacy clients need explicit identity arguments?
8. **Inspect `contextWrite` placement**: Is context added downstream of the upstream segment that reads it, or on an unrelated branch?
9. **Inspect `Mono.cache()` and static fields**: Are results or principals shared across callers?
10. **Check method security**: Is `@EnableReactiveMethodSecurity` active and are calls going through proxies?
11. **Check WebSession**: Is a Bearer-only route accidentally accepting web session authentication?
12. **Write targeted `StepVerifier`/`WebTestClient` tests** covering subscriber context, scheduler switches, missing tokens, scopes, tenants, and distinct callers.

When logging for diagnostics, include request/trace IDs, authentication type, route, and authorization outcomes. Omit raw tokens, client secrets, session IDs, and full JWT claims.

## 37. API Selection Decision Diagram

```mermaid
flowchart TD
    A["Need caller access in Spring WebFlux"] --> B{"Inside a reactive handler/service?"}
    B -- "Yes" --> C["ReactiveSecurityContextHolder.getContext()"]
    C --> D["map / flatMap / flatMapMany in same pipeline"]
    D --> E["Verify Authentication + scope + tenant/owner"]
    B -- "Functional ServerRequest" --> F["request.principal()"]
    F --> E
    B -- "Publisher unit test" --> G["contextWrite(withAuthentication(testAuth))"]
    G --> H["StepVerifier"]
    B -- "Custom auth filter" --> I["Trusted authentication + framework Reactor context"]
    I --> E
    E --> J{"Blocking legacy API involved?"}
    J -- "Yes" --> K["Explicit identity + boundedElastic + limits"]
    J -- "No" --> L["Reactive repository / WebClient"]
```

This is a programming decision flow and **does not replace Spring Security configuration for verifying Bearer access tokens**. `withAuthentication` on the unit-test branch is a testing helper, not a way to elevate unauthenticated requests.

## 38. Summary of Core Takeaways

1. **Servlet propagates SecurityContext via ThreadLocal by default; WebFlux propagates it via per-subscription Reactor Context.**
2. **`ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`**, so compose with `map`/`flatMap` instead of calling `.block()`.
3. `publishOn`/`subscribeOn` do not lose Reactor Context while staying in the same chain; manual `.subscribe()` or leaving Reactor APIs are the boundaries to watch.
4. `contextWrite` applies context to **operators upstream of its placement**, not globally; never construct Authentication from untrusted inputs.
5. WebFlux Resource Servers are configured with **`ServerHttpSecurity` and `SecurityWebFilterChain`**, backed by `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`.
6. **WebSession is distinct from Reactor Context**. Bearer APIs can use `NoOpServerSecurityContextRepository` and authenticate every request, while web logins can still use sessions by design.
7. `@EnableReactiveMethodSecurity` evaluates method checks using Reactor Context, but does not replace domain owner/tenant authorization and remains subject to Spring proxy rules.
8. Identity-dependent publishers must never be cached or shared globally without scoping, as that can cause **cross-user data leaks**.
9. Never block the event loop or rely on `ThreadLocal` inside blocking adapters; pass verified identities explicitly.
10. Test with **`StepVerifier` and `WebTestClient`**, keeping authorization tests using `mockJwt()` distinct from real signed JWT tests flowing through the production decoder.

**Key takeaway:** In Spring Security WebFlux, `SecurityContext` does not “follow the thread”—it **follows the subscription inside Reactor Context**. The right approach is **keeping the reactive flow intact, reading identity via `ReactiveSecurityContextHolder`, avoiding ad-hoc `block()`/`subscribe()` calls, and enforcing scope/tenant/owner checks inside the publisher itself**. This ensures a Bearer Resource Server authenticates every request accurately without ever mixing identities across concurrent reactive flows.
